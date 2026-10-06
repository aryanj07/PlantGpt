"""RAG Module HTTP surface (plan Section H.2, sub-task 4): document upload +
status polling. Upload returns immediately (status=pending); ingest_document
runs via BackgroundTasks off the request path (plan's stated no-Arq-in-V1
ADR) - GET /v1/documents is how a client polls for "is it ready yet"."""

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.modules.auth.schemas import CurrentIdentity
from app.modules.auth.service import get_current_identity
from app.modules.rag.ingestion import ingest_document
from app.modules.rag.models import Document
from app.modules.rag.object_store import get_object_store
from app.modules.rag.schemas import DocumentOut

router = APIRouter()


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> DocumentOut:
    content = await file.read()
    source_uri = get_object_store().save(
        tenant_id=identity.tenant_id, filename=file.filename or "upload", content=content
    )

    document = Document(
        tenant_id=identity.tenant_id,
        source_uri=source_uri,
        title=file.filename or "upload",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(ingest_document, document.id)

    return DocumentOut(**{c.name: getattr(document, c.name) for c in document.__table__.columns})


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)
) -> list[DocumentOut]:
    documents = db.scalars(
        select(Document).where(Document.tenant_id == identity.tenant_id).order_by(Document.created_at.desc())
    ).all()
    return [
        DocumentOut(**{c.name: getattr(d, c.name) for c in d.__table__.columns}) for d in documents
    ]
