from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    title: str
    status: str
    error_detail: str | None = None
    created_at: datetime
    ingested_at: datetime | None = None
