"""RAG Module (plan Section H.2, D). Phase 3, owner: Prince."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.modules.rag.embeddings import EmbeddingsClient, get_embeddings_client
from app.modules.rag.models import Document, DocumentChunk


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float  # cosine similarity (1 - cosine distance); higher is better
    source_uri: str
    document_id: str
    title: str


class RAGService:
    def __init__(self, *, db: Session | None = None, embeddings: EmbeddingsClient | None = None) -> None:
        self._db = db
        self._embeddings = embeddings or get_embeddings_client()

    async def retrieve(self, *, tenant_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        vectors = await self._embeddings.embed([query])
        if not vectors:
            return []
        query_vector = vectors[0]

        db = self._db or SessionLocal()
        try:
            distance = DocumentChunk.embedding.cosine_distance(query_vector)
            stmt = (
                select(DocumentChunk, Document.title, Document.source_uri, distance.label("distance"))
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.tenant_id == tenant_id, Document.status == "ready")
                .order_by(distance)
                .limit(top_k)
            )
            rows = db.execute(stmt).all()
        finally:
            if self._db is None:
                db.close()

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                text=chunk.chunk_text,
                score=1.0 - dist,
                source_uri=source_uri,
                document_id=chunk.document_id,
                title=title,
            )
            for chunk, title, source_uri, dist in rows
        ]


def get_rag_service() -> RAGService:
    return RAGService()
