"""Local filesystem object storage (Phase 3 plan's object-storage ADR): a
real object-storage service (MinIO/S3/R2) is infra with no current
justification at solo/dev-stage scale, so uploaded documents just live on
disk under `backend/data/documents/`. This class is the entire interface
other code depends on - swapping to real S3-compatible storage later (the
architecture plan's Section G.4) means implementing this same `save`/`read`
shape against a different backend, not rewriting every caller.
"""

import uuid
from pathlib import Path

# backend/app/modules/rag/object_store.py -> parents[3] == backend/
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "documents"


class LocalObjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DEFAULT_ROOT

    def save(self, *, tenant_id: str, filename: str, content: bytes) -> str:
        tenant_dir = self._root / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4()}-{filename}"
        path = tenant_dir / key
        path.write_bytes(content)
        return str(path)

    def read(self, uri: str) -> bytes:
        return Path(uri).read_bytes()


def get_object_store() -> LocalObjectStore:
    return LocalObjectStore()
