# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independent projects share this repo:

- **Flutter client** (repo root: `lib/`, `test/`, `pubspec.yaml`): a ChatGPT-style chat app ("PlantGPT", package name `chatgpt_alt_db`).
- **FastAPI backend** (`backend/`): a modular monolith meant to replace the client calling LLM providers directly. It is built in phases (Phase 0–5) from an external "PlantGPT — Production Architecture & Implementation Plan"; code comments refer to its sections ("plan Section H.3", "ADR 12"), which are not in this repo.

Known database problems are tracked in `docs/DATABASE_ISSUES.md` (issue IDs C1–C8, D1–D3). Commits that fix one are titled `Fix C<n> ...`. Read it before touching DB, migrations, or tests.

## Flutter client

```powershell
flutter pub get
flutter run                                                  # uses LocalChatRepository (mock)
flutter run --dart-define=OPENAI_API_KEY=... --dart-define=OPENAI_MODEL=gpt-5-mini
flutter analyze                                              # flutter_lints + prefer_single_quotes
flutter test
flutter test test/chat_repository_test.dart                  # single file
flutter test --plain-name "test name"                        # single test
```

Architecture: the UI (`lib/features/chat/presentation/chat_page.dart`) depends only on the abstract `ChatRepository` (`domain/chat_repository.dart`). `lib/main.dart` picks the implementation: `OpenAiChatRepository` (OpenAI Responses API) if `OPENAI_API_KEY` is set as a dart-define, otherwise `LocalChatRepository`. `DatabaseChatRepository` is a placeholder. New backends (e.g. an `ApiChatRepository` against `backend/openapi.json`) are added as another implementation in `lib/features/chat/data/` and swapped in at `main.dart`.

## Backend

Run all commands from `backend/` (settings read `.env` relative to the CWD).

```powershell
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload            # http://127.0.0.1:8000/health, /docs
pytest                                   # all tests
pytest tests/test_router.py              # single file
pytest tests/test_router.py::test_name   # single test
alembic upgrade head                     # Postgres only
curl http://127.0.0.1:8000/openapi.json -o openapi.json   # regenerate API contract after route changes
```

### Database

- Default `DATABASE_URL` is `sqlite:///./dev.db`. On SQLite, `app/dev_schema.py` creates the `users`, `conversations`, `messages`, `tenant_usage` tables at app construction (`create_app()`); RAG tables (`documents`, `document_chunks`) need Postgres + pgvector and are not created.
- Alembic (`alembic/versions/`) is the schema source of truth for Postgres. `alembic/env.py` refuses to run on non-Postgres URLs on purpose. New models must be imported in `alembic/env.py` (and added to `SQLITE_DEV_TABLES` if SQLite-compatible).
- The installed driver is psycopg 3, so Postgres URLs should use `postgresql+psycopg://`, not the `+psycopg2` shown in `.env.example`/`docker-compose.dev.yml` (issue C5). The `postgres:16-alpine` compose image lacks pgvector (D2).
- **Tests use whatever `DATABASE_URL` is configured; there is no separate test DB, and some tests delete all rows in `users`/`tenant_usage` (C4).** Never run `pytest` with `.env` pointing at a shared/hosted database (e.g. Supabase).
- DB access is sync SQLAlchemy throughout: each store method opens its own `SessionLocal()` (see `app/modules/chat/store.py`), not an async engine.

### Request flow (chat)

`app/main.py:create_app()` wires routers under `/v1` (`auth`, `chat`, `cost`, `rag`) plus `RequestContextMiddleware`. A message POST goes through `app/modules/chat/service.py:post_user_message`:

1. Persist the user message.
2. `router/classifier.py:classify()` — a deterministic keyword/phrase heuristic (not a model call) returning `SIMPLE_CHAT | NEEDS_RAG | NEEDS_TOOL | NEEDS_RAG_AND_TOOL`. Extend its phrase lists rather than adding an LLM call.
3. `cost/tracker.py` budget check → HTTP 402 when over `DEFAULT_MONTHLY_BUDGET_USD`, before any provider call.
4. `_augment_context`: RAG retrieval (`rag/service.py`, local fastembed `BAAI/bge-small-en-v1.5` embeddings, pgvector) and/or an MCP tool (`mcp/broker.py`: simulated sensor readings, Tavily web search/extract). Failures here are logged and skipped, never fail the reply.
5. `llm_gateway/gateway.py:LLMGateway` — an ordered fallback chain built from whichever provider keys are configured (adapters in `llm_gateway/adapters/`), each route with retry + circuit breaker (`reliability.py`). If every route fails it returns a degraded reply instead of raising. Streaming is also supported (`tests/test_streaming.py`).

Services take their collaborators as optional keyword args (`llm_gateway=`, `cost_tracker=`, `rag_service=`, `tool_broker=`) falling back to `get_*()` factories — this is the injection point tests use for fakes.

### Auth

`auth/service.py:get_current_identity` resolves tenant/user from either a backend-issued HS256 session JWT (minted by `/v1/auth/session` from a verified Auth0 token) or, when `DEV_MODE=true`, the `X-Dev-Tenant-Id` / `X-Dev-User-Id` headers. Every data access is scoped by `tenant_id`. First-time Auth0 subjects are auto-provisioned as tenant `default` with role `admin` (`auth/users.py`).

### Other

- `worker/` is an Arq worker scaffold (`arq worker.main.WorkerSettings`); it is not wired to Redis yet.
- `rate_limit/` is not wired into the request flow yet.
- Deployment is Render via `backend/render.yaml` (no Dockerfile; `DEV_MODE=false`; secrets set in the dashboard). It does not run migrations (D1).
- Parts of `backend/README.md` and module docstrings are stale (e.g. they still describe chat as an in-memory Phase 0 stub); trust the code (C7).
