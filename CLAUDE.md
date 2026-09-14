# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PlantGPT (package name `chatgpt_alt_db`) is a Flutter chat client modeled on ChatGPT's UI, purpose-built
as a domain assistant for **industrial plant operations** — cement plants, steel plants, and
manufacturing plants ("plant" as in facility, not botany). It's paired with a FastAPI backend
(`backend/`, see `backend/README.md`) that owns the LLM Gateway, Auth Module, RAG, and an MCP tool broker —
the client no longer talks to any LLM provider or holds any provider API key directly. All chat screens
depend only on the `ChatRepository` abstract interface (`lib/features/chat/domain/chat_repository.dart`),
never on a concrete data source directly, so the backend can keep evolving without touching the UI.

## Commands

```powershell
flutter pub get                     # install dependencies
flutter run                         # run the app (uses LocalChatRepository mock, no backend needed)
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000   # run wired to a local backend instance
flutter test                        # run all tests
flutter test test/chat_repository_test.dart          # run a single test file
flutter analyze                     # lint/static analysis (flutter_lints + analysis_options.yaml)
```

For the backend: see `backend/README.md` (venv setup, `uvicorn app.main:app`, Auth0 config, tests).
`run_local_backend.bat` launches the Flutter client in Chrome pre-wired to `http://127.0.0.1:8000` — start
the backend first.

There is no separate build/lint script beyond the standard Flutter CLI; this is a normal `flutter create`-based
project (Android + Web scaffolding present, iOS/others not set up).

## Architecture

- **Repository pattern boundary**: `lib/features/chat/domain/chat_repository.dart` defines the contract
  (`loadMessages`, `clearMessages`, `saveUserMessage`, `createAssistantReply`). The UI (`chat_page.dart`) is
  constructed with a `ChatRepository` injected via constructor — it has zero knowledge of HTTP, SQL, or any
  specific backend. Any new persistence/AI backend is added as a new implementation in
  `lib/features/chat/data/` and swapped in at the single call site in `lib/main.dart`.
- **Active implementations** (`lib/features/chat/data/`):
  - `LocalChatRepository` — in-memory mock, used when no backend URL is configured. Default for local dev.
  - `ApiChatRepository` — the production path. Calls the FastAPI backend's `/v1/conversations` and
    `/v1/auth/session` endpoints; holds no LLM provider key at all (that lives server-side in the backend's
    LLM Gateway). Resumes the authenticated identity's most recent conversation on load rather than always
    starting fresh (`_resolveBackendConversationId`), and sends either a real backend session token or the
    backend's dev-mode `X-Dev-Tenant-Id`/`X-Dev-User-Id` headers (see `API_DEV_TENANT_ID`/`API_DEV_USER_ID`
    below — a stand-in until real Auth0 login exists client-side).
  - `DatabaseChatRepository` — unimplemented placeholder (`throw UnimplementedError`); superseded by
    `ApiChatRepository` now that a real backend exists, kept only as the original template/reference.
- **Legacy implementations, retained but not wired into `main.dart`** (`lib/features/chat/data/`):
  `OpenAiChatRepository`, `OpenRouterChatRepository`, `FreeRouterChatRepository` — these called LLM
  providers directly from the client with an API key embedded at build time via `--dart-define`, which is
  exactly the risk `ApiChatRepository` was built to close. Their tests still exist and still pass; the
  classes themselves are unreachable from `main.dart` and should stay that way — extend the backend's LLM
  Gateway (`backend/app/modules/llm_gateway/`) instead of resurrecting one of these.
- **Backend selection happens in `lib/main.dart`**: `ChatApp` reads config via `String.fromEnvironment`
  (Dart defines, not `.env` files — those exist only in `backend/`). If `API_BASE_URL` is set →
  `ApiChatRepository`; otherwise → `LocalChatRepository`. That's the entire priority chain now. There is no
  runtime config UI for any of this — it's all compile-time via `--dart-define`.
- **Domain model**: `ChatMessage` (`lib/features/chat/domain/chat_message.dart`) is an immutable value type
  with `copyWith`; `ChatRole` is `user` or `assistant`. Pending/in-flight assistant messages use
  `isPending: true` so the UI can find-and-remove the "Thinking..." bubble once the real reply arrives.
  `imageBytes`/`imageMimeType` optionally carry a user-attached image (picked via `image_picker` in
  `chat_page.dart`); only populated on user messages. `ApiChatRepository` doesn't forward it to the backend
  yet (the Chat Module doesn't accept images server-side — RAG/multimodal ingestion is a later phase), so
  it currently only affects local display.
- **Security note**: no LLM provider API key is embedded in this client at all (plan risk B1, closed). All
  provider calls, retry/backoff/circuit-breaker, and secrets live server-side in `backend/app/modules/llm_gateway/`
  — see `backend/README.md` and `backend/.env.example`. The legacy `OpenAiChatRepository`/
  `OpenRouterChatRepository` classes still demonstrate the old client-embedded-key pattern in their own
  files/tests; don't reintroduce it by wiring them back into `main.dart`.
- **RAG module (backend, done)**: `backend/app/modules/rag/` — `models.py` (SQLAlchemy `Document`/
  `DocumentChunk`, the first genuinely persistent schema in this project, backed by real Postgres+pgvector
  on Supabase via Alembic under `backend/alembic/`, not `create_all()`), `object_store.py`
  (`LocalObjectStore`, local filesystem under `backend/data/`, gitignored — deliberately not S3/MinIO yet),
  `embeddings.py` (local `BAAI/bge-small-en-v1.5` via `fastembed`/Hugging Face — switched from the original
  OpenAI plan specifically to avoid needing `OPENAI_API_KEY`; no key, no cost, model cached under
  `backend/data/fastembed_cache/`), `ingestion.py` + `router.py` (`POST`/`GET /v1/documents`, chunking +
  embedding via FastAPI `BackgroundTasks`, no Arq/Redis), and `service.py`'s real `RAGService.retrieve()`
  (pgvector cosine search filtered by `tenant_id`). Wired into `chat/service.py` for both the streaming and
  non-streaming paths; citations flow through to `Message.citations`/`MessageOut` and the Flutter
  `_MessageBubble`'s "Source: ..." line. Client-side upload UI: `lib/features/documents/`, a "Documents"
  icon in the chat AppBar. Chat/auth/cost still stay on their existing in-memory stores — migrating them to
  Postgres is an explicitly separate, deferred task, not part of RAG.
- **MCP tool broker (backend, done)**: `backend/app/modules/mcp/` — `broker.py`'s `MCPToolBroker.run()`
  dispatches heuristically (not LLM function-calling, a deliberate scope choice - see the module
  docstring) based on `router/classifier.py`'s `classify_tool_kind()`: a self-hosted, zero-dependency
  simulated sensor reading (`tools/sensor_simulator.py` - always explicitly labeled `simulated=True`,
  never fabricates a number for a metric it doesn't know), or real web search/scrape via Tavily
  (`tools/web_tool.py`, `TAVILY_API_KEY` in `backend/.env`, permanent free tier). Both produce the same
  `{"document_id", "title", "source_uri"}` citation shape RAG uses, so the Flutter "Source: ..." UI shows
  tool results too with no client changes. `dispatch(tool_name, arguments)` is an unused stub kept only
  for a possible future real function-calling migration. v1 ships zero WRITE tools.
- **Theming**: `lib/core/app_theme.dart` provides Material 3 light/dark `ThemeData` via `ColorScheme.fromSeed`;
  `main.dart` wires both into `MaterialApp` with `themeMode: ThemeMode.system`.
- **Testing pattern**: `ApiChatRepository`, and the legacy `OpenAiChatRepository`/`OpenRouterChatRepository`/
  `FreeRouterChatRepository`, all accept an injectable `http.Client`, which is how
  `test/api_chat_repository_test.dart` and the legacy repos' test files swap in `MockClient` from
  `package:http/testing.dart` to assert on outgoing request bodies/headers without hitting the network.
- **`run_local_backend.bat`**: a Windows convenience launcher that runs `flutter run -d chrome` with
  `API_BASE_URL` pointed at `http://127.0.0.1:8000`. Start the backend (`backend/README.md`) first.
- **`freerouter/`** (git-ignored) and **`freerouter_integration_spec.md`**: a local clone of the
  self-hosted FreeRouter project used during development of the now-legacy `FreeRouterChatRepository`, plus
  the design spec that integration was built from. Neither is part of this app's build; `freerouter/` is
  excluded from version control because it's its own separate git repository.
