"""Tests for the PostgreSQL-only guard in alembic/env.py (database issue C2).

Runs the real alembic CLI in a subprocess with its own DATABASE_URL, so the
check is independent of the app's cached settings and never touches the
database the rest of the suite uses.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_upgrade_refuses_sqlite_with_clear_message(tmp_path) -> None:
    db_path = tmp_path / "guard.db"

    result = _run_alembic(f"sqlite:///{db_path.as_posix()}", "upgrade", "head")

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "PostgreSQL + pgvector only" in output
    assert "near \"EXTENSION\"" not in output
    # Refused before connecting: no database file, so no stray alembic_version table.
    assert not db_path.exists()


def test_postgres_offline_sql_still_generated() -> None:
    # --sql renders the migrations without connecting, so no live Postgres is needed.
    result = _run_alembic("postgresql+psycopg://user:pass@127.0.0.1:1/db", "upgrade", "head", "--sql")

    assert result.returncode == 0, result.stderr
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "CREATE TABLE conversations" in result.stdout
