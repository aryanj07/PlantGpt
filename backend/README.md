# PlantGPT Backend

FastAPI modular monolith for PlantGPT — the production backend that replaces the
current client-only architecture where the Flutter app calls LLM providers directly.
See the "PlantGPT — Production Architecture & Implementation Plan" for full context
(current-state risks, target architecture, roadmap, ADRs). This directory is the
**Phase 0 (Architecture Foundation) scaffold** from that plan: module boundaries and
a runnable skeleton, not a finished implementation.

## Status

Everything under `app/modules/` other than `chat` is a stub — method signatures and
docstrings matching the plan's component responsibilities, bodies raising
`NotImplementedError` until the phase that owns them lands. `chat` is wired
end-to-end against an **in-memory store** (not Postgres yet) so the request
lifecycle is runnable and testable locally before the real schema (a Phase 1 task,
owned by Rimsha) exists.

Do not treat anything here as production-ready: there is no real auth, no real
persistence, no real LLM calls, and no RLS/tenant isolation enforcement yet.

## Layout

```
app/
  main.py            FastAPI app factory, router wiring, /health
  config.py          Settings (env-driven, safe local defaults)
  db.py              SQLAlchemy engine/session scaffold (models land in Phase 1)
  observability.py   request_id/trace_id middleware (OTel wiring is a Phase 5 task)
  modules/
    auth/            Auth Module stub (real impl: Phase 1, owner Rimsha)
    chat/            Chat/Conversation Module — in-memory, runnable
    llm_gateway/      LLM Gateway Module stub (real impl: Phase 1-2, owner Prince)
    rag/             RAG Module stub (Phase 3, owner Prince)
    mcp/             MCP Tool Broker stub (Phase 4, owner Prince/Rimsha)
    rate_limit/      Rate Limit Module stub (Phase 1, owner Rimsha)
    cost/            Cost/Quota Module stub (Phase 2, owner Rimsha/Prince)
worker/              Arq worker entrypoint scaffold (Phase 3+ jobs land here)
tests/               pytest suite
```

## Dev infrastructure (Postgres / Redis / object storage)

`docker-compose.dev.yml` stands up local Postgres, Redis, and MinIO
(S3-compatible object storage) — the V1 dev environment per plan ADR 12.
Docker isn't installed on the machine this was scaffolded on, so this hasn't
been run yet; it's ready to go once Docker is available:

```powershell
docker compose -f docker-compose.dev.yml up -d
```

Until then, the app runs against the zero-setup defaults in `.env.example`
(SQLite + in-memory store) — see "Running locally" below.

## Running locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # defaults work out of the box, no external services needed
uvicorn app.main:app --reload
```

Then:
- `GET http://127.0.0.1:8000/health` → `{"status": "ok"}`
- `POST http://127.0.0.1:8000/v1/conversations` with header `X-Dev-Tenant-Id: t1` and
  `X-Dev-User-Id: u1` (see "Dev-mode auth" below) → creates an in-memory conversation
- `POST http://127.0.0.1:8000/v1/conversations/{id}/messages` with the same headers
  and `{"content": "..."}` → persists the user message and returns a stub assistant
  reply (the real LLM Gateway call is a Phase 1 task)

## Setting up Auth0

`app/modules/auth/` verifies Auth0-issued access tokens (plan Section J.2) and mints its
own short-lived session JWT from them — it never re-implements login itself. To wire up a
real Auth0 tenant:

1. Sign up at https://auth0.com (free tier is enough for dev).
2. **Dashboard → Applications → APIs → Create API** — Name: `PlantGPT Backend`, Identifier:
   any URI-like string, e.g. `https://plantgpt.api` (doesn't need to resolve), Signing
   Algorithm: RS256. This Identifier is your `AUTH0_AUDIENCE`.
3. Your tenant's domain (shown in the dashboard, looks like `dev-xxxx.us.auth0.com`) is your
   `AUTH0_DOMAIN`.
4. Put both in `.env`: `AUTH0_DOMAIN=...` and `AUTH0_AUDIENCE=...`.
5. To get a real token to test with before the Flutter client has a login flow: **Dashboard
   → Applications → Applications → Create Application → Machine to Machine**, authorize it
   for the API from step 2, then use the Client ID/Secret it gives you with the Client
   Credentials grant:
   ```powershell
   curl -X POST https://YOUR_DOMAIN/oauth/token -H "Content-Type: application/json" -d '{
     "client_id": "...", "client_secret": "...",
     "audience": "https://plantgpt.api", "grant_type": "client_credentials"
   }'
   ```
   POST the resulting `access_token` to `/v1/auth/session` to get a PlantGPT session token.
6. Real end-user login (Authorization Code + PKCE in the Flutter client, e.g. via the
   `auth0_flutter` package) is separate client-side work — this module only verifies
   whatever token the client hands it.

Until `AUTH0_DOMAIN`/`AUTH0_AUDIENCE` are set, `/v1/auth/session` returns 401 for any token;
`DEV_MODE` headers remain available as a fallback (see below).

**Tenant mapping (V1):** the first time any Auth0 subject calls `/v1/auth/session`, it's
auto-provisioned as `tenant_id="default"`, `roles=["admin"]` (`app/modules/auth/users.py`) —
correct for solo use right now. Real per-customer tenant assignment replaces this once the
Postgres `users` table exists (Phase 1 schema task, still blocked on Postgres being stood
up locally).

## Dev-mode auth

There is no real auth yet (Phase 1). `app/modules/auth/service.py` currently trusts
`X-Dev-Tenant-Id`/`X-Dev-User-Id` request headers when `DEV_MODE=true` (the default
in `.env.example`). This exists purely so the rest of the skeleton is runnable end
to end locally — it is explicitly not something to ever enable outside local dev,
and it must be removed, not just disabled, when the real Auth Module lands.

## API contract

`openapi.json` is the schema FastAPI generates from the routes that exist
right now (exported from a live-running instance, not hand-written) — the
Phase 0 draft contract for Aranj to review before building `ApiChatRepository`
against it. It'll go stale as routes change; regenerate with:

```powershell
curl http://127.0.0.1:8000/openapi.json -o openapi.json
```

Interactive version (same schema, browsable): `http://127.0.0.1:8000/docs`.

## Tests

```powershell
pytest
```
