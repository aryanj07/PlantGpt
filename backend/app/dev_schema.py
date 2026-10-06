"""SQLite-only local-dev schema bootstrap.

The Alembic chain (alembic/versions/) is the schema source of truth, but it's
Postgres-specific - 0001 needs the pgvector extension - so it can't run
against the zero-setup `sqlite:///./dev.db` default. Without this, a fresh
SQLite dev database has no chat/auth/cost tables and the first request fails
with `no such table: conversations`.

Only the tables that work on plain SQLite are created here. documents/
document_chunks are deliberately left out: RAG needs Postgres + pgvector.
On any non-SQLite database this is a no-op - Postgres keeps using
`alembic upgrade head`, never create_all().
"""

from app.db import Base, engine
from app.modules.auth.models import User
from app.modules.chat.models import Conversation, Message
from app.modules.cost.models import TenantUsage

SQLITE_DEV_TABLES = [
    User.__table__,
    Conversation.__table__,
    Message.__table__,
    TenantUsage.__table__,
]


def init_sqlite_dev_schema() -> None:
    if engine.dialect.name != "sqlite":
        return
    # checkfirst (create_all's default) makes this idempotent - existing
    # tables and their rows are left untouched on every restart.
    Base.metadata.create_all(engine, tables=SQLITE_DEV_TABLES)
