"""Ingestion pipeline (Phase 3 plan, sub-task 4): parse -> chunk -> embed ->
store. Runs off the request path via FastAPI BackgroundTasks (see router.py) -
no Arq/Redis in V1 (plan's stated ADR), so there's no cross-restart retry: a
document stuck in "processing" after a backend crash needs a manual re-upload.
"""

import io
import logging
from datetime import UTC, datetime

from pypdf import PdfReader

from app.db import SessionLocal
from app.modules.rag.embeddings import get_embeddings_client
from app.modules.rag.models import Document, DocumentChunk
from app.modules.rag.object_store import get_object_store

logger = logging.getLogger("plantgpt")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def extract_text(*, content: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if lower.endswith((".txt", ".md")):
        return content.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {filename}")


def chunk_text(text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


async def ingest_document(document_id: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("ingest_document: document %s not found", document_id)
            return

        document.status = "processing"
        db.commit()

        try:
            content = get_object_store().read(document.source_uri)
            text = extract_text(content=content, filename=document.title)
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("document had no extractable text")

            vectors = await get_embeddings_client().embed(chunks)

            for chunk_body, vector in zip(chunks, vectors, strict=True):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        tenant_id=document.tenant_id,
                        chunk_text=chunk_body,
                        embedding=vector,
                    )
                )

            document.status = "ready"
            document.ingested_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - always land in a terminal, visible state
            db.rollback()
            document.status = "failed"
            document.error_detail = str(exc)[:2000]
            db.commit()
            logger.exception("ingest_document failed for %s", document_id)
    finally:
        db.close()
