"""shrink document_chunks.embedding to 384 dims (switch to local fastembed
model instead of OpenAI text-embedding-3-small)

Table is live but empty (no ingestion has run yet), so this is a straight
column-type swap - drop the dimension-specific index, alter the column,
recreate the index.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_DIMENSIONS = 384  # BAAI/bge-small-en-v1.5
OLD_DIMENSIONS = 1536  # text-embedding-3-small


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_cosine")
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({NEW_DIMENSIONS})")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_cosine ON document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_cosine")
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({OLD_DIMENSIONS})")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_cosine ON document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
