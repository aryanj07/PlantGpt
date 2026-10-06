# PlantGPT — Database Issues

**Prepared:** 2026-10-06
**Codebase state reviewed:** commit `d11644f` ("Phase 5: migrate chat/auth/cost to Postgres, add Render Blueprint")

This document lists the database issues found in the PlantGPT backend (`backend/`). It is split into
three groups:

- **A. Confirmed issues**: shown by the code, by git history, or by reproducing the error.
- **B. Configuration and deployment issues**.
- **C. Possible risks**: weaknesses in the code that have not been seen to cause a problem.

## How this was checked

- I read the database code: the database setup in `app/db.py` and `app/config.py`, the Alembic
  config and migrations `0001`–`0003`, the models, the data-access code, the RAG and pgvector code,
  the tests, and the deployment files (`render.yaml`, `docker-compose.dev.yml`, `.env.example`).
- I read the commit messages and change history of every database-related file.
- I reproduced errors against throwaway SQLite databases outside the repository: Alembic migrations,
  the chat data layer, and the full test suite.
- I did **not** connect to the hosted Supabase database. I did not read or record any connection
  string, password or API key; for the local `.env` I checked only which database type it points to.

---

## A. Confirmed issues

### Unresolved

#### C1. The backend's chat, login and cost features don't work on the default local setup

| | |
|---|---|
| **Error / problem** | Every chat, login and cost endpoint fails with `sqlite3.OperationalError: no such table: conversations` (reproduced on a fresh SQLite database). |
| **Location** | `backend/app/config.py:16` (default `sqlite:///./dev.db`), `backend/.env.example:11`, `backend/README.md:53-54,63` ("defaults work out of the box"). |
| **Root cause** | Commit `d11644f` moved chat, auth and cost onto database tables. Those tables can only be created by Alembic, which only works on Postgres (see C2), and the app has no `create_all()` fallback. The default database is still SQLite. |
| **Impact** | The documented local setup is broken. The local `backend/.env` currently points at SQLite too, so the local backend can't serve chat. There is no Postgres URL anywhere in the local environment. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commit `d11644f` |

#### C2. The migrations can't run on SQLite

| | |
|---|---|
| **Error / problem** | `sqlite3.OperationalError: near "EXTENSION": syntax error [SQL: CREATE EXTENSION IF NOT EXISTS vector]` (reproduced with `alembic upgrade head`). |
| **Location** | `backend/alembic/versions/0001_documents_and_chunks.py:29`. The same migration also uses the pgvector `Vector` type and an `ivfflat` index. |
| **Root cause** | Migration 0001 is Postgres + pgvector only. |
| **Impact** | On SQLite, no schema can be created at all. `backend/dev.db` holds only an empty `alembic_version` table, which fits an upgrade that was attempted and failed. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Migration `0001`, commit `000ea07` |

#### C3. 24 of the 106 tests fail without a live Postgres

| | |
|---|---|
| **Error / problem** | On SQLite the run ends `4 failed, 82 passed, 20 errors`. Every failure is `OperationalError: no such table`. |
| **Location** | `backend/tests/test_chat_flow.py`, `test_streaming.py`, `test_auth.py`, `test_cost.py` |
| **Root cause** | The data-access code always uses the shared session set up in `app/db.py` from `DATABASE_URL`. The tests have no separate test database and nothing that creates tables for them. |
| **Impact** | CI or a new developer can't run the tests without real database credentials. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commit `d11644f` (its message says the suite was verified "against real Supabase") |

#### C4. The tests delete every row in `users` and `tenant_usage` in whatever database is configured

| | |
|---|---|
| **Error / problem** | The test setup and teardown call `clear_all()`, which runs `db.query(...).delete()` with no WHERE clause. |
| **Location** | `backend/tests/test_auth.py:75-79` calls `app/modules/auth/users.py:48-55`; `backend/tests/test_cost.py:25-29` calls `app/modules/cost/store.py:91-98`. |
| **Root cause** | These test helpers were written for the old in-memory stores and kept after the move to a real database. |
| **Impact** | Per commit `d11644f`, the suite ran against Supabase, so these deletes ran there. Whether real data was lost isn't recorded. Each wipe gives every login identity a new random ID on its next login, so it loses access to its earlier conversations, and resets every tenant's budget usage to zero. Separately, the chat tests leave their test conversations in the database permanently. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commit `d11644f` |

#### C5. The documented Postgres URL needs a driver that isn't installed

| | |
|---|---|
| **Error / problem** | `ModuleNotFoundError: No module named 'psycopg2'` (reproduced with SQLAlchemy's `create_engine`). |
| **Location** | `backend/.env.example:10`, `backend/docker-compose.dev.yml:10`, and a commented-out line in the local `.env`. |
| **Root cause** | The docs use `postgresql+psycopg2://`, but `requirements.txt` only installs `psycopg` version 3, which needs `postgresql+psycopg://`. |
| **Impact** | Anyone following the docs gets a startup crash. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commit `a949b65` added this URL; `000ea07` then installed psycopg 3 instead without updating it. |

#### C6. A crash can leave documents stuck in "processing"

| | |
|---|---|
| **Error / problem** | If the backend crashes or restarts during ingestion, `documents.status` stays `processing` forever. |
| **Location** | `backend/app/modules/rag/ingestion.py:2-4,57-58` |
| **Root cause** | Ingestion runs as a FastAPI `BackgroundTasks` job with no queue and no retry. |
| **Impact** | The document never becomes searchable, and it has to be uploaded again by hand. |
| **Status** | Unresolved (the code documents it as a known limitation) |
| **How addressed** | — |
| **Related** | Commit `4e6e041` |

#### C7. Database docs and docstrings contradict the code

| | |
|---|---|
| **Error / problem** | `app/db.py:3-6` says "No models are defined here yet… chat's in-memory store does not use this". `app/modules/rag/models.py:1-3` says chat, auth and cost are "still in-memory". `backend/README.md` says "in-memory store", "no real persistence", and that the users table is "still blocked" (lines 14-20, 28, 53-54, 106-110). |
| **Location** | As listed above |
| **Root cause** | These weren't updated in `000ea07` / `d11644f`. |
| **Impact** | Readers are misled about how data is actually stored. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commits `000ea07`, `d11644f` |

#### C8. Uploaded documents are stored as absolute local file paths

| | |
|---|---|
| **Error / problem** | `documents.source_uri` stores a full path on the server's disk, and that path is also returned to clients in API responses and citations. |
| **Location** | `backend/app/modules/rag/object_store.py:27`, `backend/app/modules/rag/router.py:29-36` |
| **Root cause** | `LocalObjectStore.save()` returns the full file path instead of a relative key. |
| **Impact** | Database rows break if the data folder or machine changes. It also shows the server's directory layout to clients. |
| **Status** | Unresolved |
| **How addressed** | — |
| **Related** | Commits `000ea07`, `4e6e041` |

### Resolved

| # | Issue | Root cause | How it was fixed | Related |
|---|---|---|---|---|
| C9 | Embedding size mismatch: 1536-dim column vs 384-dim vectors | Embeddings switched from OpenAI `text-embedding-3-small` to local fastembed `BAAI/bge-small-en-v1.5` | Migration 0002 changed the column to `vector(384)` and rebuilt the index while the table was still empty | Migration `0002`, commit `4e6e041` |
| C10 | All chat, user and budget data was lost on every restart | Chat, auth and cost were stored in memory | Moved to Postgres tables; per the commit, verified by killing and restarting the backend | Migration `0003`, commit `d11644f` |
| C11 | A tenant that hit its budget was locked out permanently | The usage record never reset | Added `period_start` with a monthly reset (`cost/store.py:29-30,44-48,65-68`) | Migration `0003`, commit `d11644f` |
| C12 | Converting DB objects to API responses via `__dict__` picked up SQLAlchemy's internal `_sa_instance_state` | Code written for plain Python objects was reused on database objects | Switched to reading `__table__.columns` (`chat/service.py`, `chat/router.py`) | Commit `d11644f` (exact error text isn't in the history) |
| C13 | A `%` in `DATABASE_URL` (e.g. an encoded password) broke Alembic's config parsing | Alembic's config file format treats `%` as special | `alembic/env.py:21-23` escapes `%` as `%%` | Commit `4e6e041` (exact error text isn't in the history) |

---

## B. Database configuration and deployment issues

#### D1. The Render deployment never creates the database tables

| | |
|---|---|
| **Problem** | Neither the build nor the start command runs `alembic upgrade head`. |
| **Location** | `backend/render.yaml:14-15` |
| **Impact** | On a fresh database every endpoint fails with missing tables. |
| **Status** | Unresolved. It hasn't happened yet because the app isn't deployed. |
| **Related** | Commit `d11644f` |

#### D2. The local Docker Postgres image doesn't include pgvector

| | |
|---|---|
| **Problem** | `postgres:16-alpine` doesn't ship pgvector, so migration 0001's `CREATE EXTENSION vector` would fail. |
| **Location** | `backend/docker-compose.dev.yml:18` |
| **Impact** | The documented local Postgres setup can't run the migrations. |
| **Status** | Unresolved. Confirmed by reading the config only; it was never run, because the compose file says Docker isn't installed. |
| **Related** | Commit `a949b65` (compose file), migration `0001` |

#### D3. Document rows outlive their files on Render

| | |
|---|---|
| **Problem** | Uploaded files are saved under `backend/data/`, and `render.yaml` attaches no persistent disk. On Render's default, non-persistent filesystem, each redeploy would remove the files while the `documents` rows and their absolute paths (C8) stay. |
| **Location** | `backend/app/modules/rag/object_store.py:14`, `backend/render.yaml` |
| **Impact** | Database rows would point at files that no longer exist. |
| **Status** | Unresolved; not yet deployed. |
| **Related** | Commits `000ea07`, `d11644f` |

---

## C. Possible risks (none observed)

These are weaknesses in the code that have not been seen to cause a problem.

| # | Risk | Evidence |
|---|---|---|
| R1 | **Lost updates in the budget ledger.** The code reads the row, adds to it in Python and writes it back, with no row lock or SQL increment. The docstring calls it "atomic", but concurrent requests can undercount spending. | `backend/app/modules/cost/store.py:54-72` |
| R2 | **Errors when two requests arrive together.** Two first requests for the same tenant (primary key on `tenant_usage`) or the same Auth0 login (unique `auth0_sub`) can both try to insert. The second gets an `IntegrityError` that nothing catches. | `cost/store.py:39-43,62-64`; `auth/users.py:34-43` |
| R3 | **Raw 500 errors on database failures.** No route handles SQLAlchemy errors; only ingestion and RAG retrieval catch exceptions. | `chat/router.py`, `rag/router.py`, `auth/router.py`, `cost/router.py` |
| R4 | **Stale connections.** `pool_pre_ping` and pool limits aren't set, which matters with a hosted Postgres. | `backend/app/db.py:18-21` |
| R5 | **Weak vector search index.** The IVFFlat index was built on an empty table in both 0001 and 0002. pgvector's guidance is to build it after loading data, so search accuracy may be poor. | `0001_documents_and_chunks.py:61-64`, `0002_embedding_dim_384.py:4-6,27-30` |
| R6 | **Blocked server.** Async handlers make blocking database calls, which blocks FastAPI's request loop. | `rag/service.py:28-48`, `chat/service.py`, `rag/router.py:22-40` |
| R7 | **No row-level security.** Tenant isolation relies only on WHERE clauses in the app. | `backend/README.md:20` |
| R8 | **No delete or cascade rules.** No foreign key has ON DELETE rules, there's no delete path for documents or conversations, and `conversations.user_id` isn't a foreign key to `users`. | Migrations `0001`, `0003` |
| R9 | **Downgrading 0002 breaks once data exists.** Converting `vector(384)` back to `vector(1536)` fails when rows are present. | `0002_embedding_dim_384.py:33-39` |
| R10 | **Duplicate index.** `users.auth0_sub` gets both a unique constraint and a separate unique index. | `0003_chat_auth_cost_tables.py:25,30` |
