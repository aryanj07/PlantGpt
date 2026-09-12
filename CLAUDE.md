# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PlantGPT (package name `chatgpt_alt_db`) is a Flutter chat app modeled on ChatGPT's UI, built so the
database/AI backend can be swapped without touching the UI. All chat screens depend only on the
`ChatRepository` abstract interface (`lib/features/chat/domain/chat_repository.dart`), never on a
concrete data source directly.

## Commands

```powershell
flutter pub get                     # install dependencies
flutter run                         # run the app (uses LocalChatRepository mock by default)
flutter run --dart-define=OPENAI_API_KEY=your_key    # run wired to OpenAI instead of the mock
flutter run --dart-define=OPENAI_API_KEY=your_key --dart-define=OPENAI_MODEL=gpt-5-mini  # override model
flutter run --dart-define=OPENROUTER_API_KEY=your_key       # run wired to OpenRouter.ai's free-model router
flutter run --dart-define=FREEROUTER_ENABLED=true            # run wired to a self-hosted FreeRouter instance
flutter test                        # run all tests
flutter test test/chat_repository_test.dart          # run a single test file
flutter analyze                     # lint/static analysis (flutter_lints + analysis_options.yaml)
```

There is no separate build/lint script beyond the standard Flutter CLI; this is a normal `flutter create`-based
project (Android + Web scaffolding present, iOS/others not set up).

## Architecture

- **Repository pattern boundary**: `lib/features/chat/domain/chat_repository.dart` defines the contract
  (`loadMessages`, `clearMessages`, `saveUserMessage`, `createAssistantReply`). The UI (`chat_page.dart`) is
  constructed with a `ChatRepository` injected via constructor — it has zero knowledge of HTTP, SQL, or any
  specific backend. Any new persistence/AI backend is added as a new implementation in
  `lib/features/chat/data/` and swapped in at the single call site in `lib/main.dart`.
- **Existing implementations** (`lib/features/chat/data/`):
  - `LocalChatRepository` — in-memory mock, used when no other backend is selected. Default for local dev.
  - `OpenAiChatRepository` — calls OpenAI's Responses API (`POST /v1/responses`) directly from the client,
    truncates history to the last 16 non-pending messages, and prepends a fixed `_systemPrompt` as a
    `developer` role message. Selected when `OPENAI_API_KEY` is non-empty (and no other backend takes
    priority — see below). Also used as the optional fallback target for the two router repositories.
  - `OpenRouterChatRepository` — calls OpenRouter.ai's hosted "Free Models Router"
    (`POST https://openrouter.ai/api/v1/chat/completions`, default model `openrouter/free`), a separate
    hosted HTTPS service with its own API key. Selected when `OPENROUTER_API_KEY` is non-empty. Supports
    retry with exponential backoff + jitter on transient failures (timeout/429/5xx) and an optional
    `fallback` repository (see `LLM_FALLBACK_ENABLED` below). Sends image attachments as multimodal
    `image_url` content parts.
  - `FreeRouterChatRepository` — talks to a self-hosted [FreeRouter](https://github.com/openfreerouter/freerouter)
    instance's OpenAI-compatible `/v1/chat/completions` endpoint (default `http://localhost:18800`). It is a
    router/proxy only — "free" depends entirely on how FreeRouter's own tiers/providers are configured, not
    on anything this client does. Selected when `FREEROUTER_ENABLED=true`; same retry/backoff and optional
    `fallback` support as `OpenRouterChatRepository`. Has a `healthCheck()` helper (not auto-wired into the
    request path).
  - `DatabaseChatRepository` — unimplemented placeholder (`throw UnimplementedError`) intended as the
    template for wiring a real backend (Firestore, Supabase, custom API, SQLite, etc.).
- **Backend selection happens in `lib/main.dart`**: `ChatApp` reads all config via `String.fromEnvironment` /
  `bool.fromEnvironment` / `int.fromEnvironment` (Dart defines, not `.env` files). Priority order, highest
  first: `FREEROUTER_ENABLED=true` → `FreeRouterChatRepository`; else `OPENROUTER_API_KEY` set →
  `OpenRouterChatRepository`; else `OPENAI_API_KEY` set → `OpenAiChatRepository`; else `LocalChatRepository`.
  If `LLM_FALLBACK_ENABLED=true` and `OPENAI_API_KEY` is also set, both router repositories are constructed
  with `OpenAiChatRepository` as their `fallback`, used only for transient failures. There is no runtime
  config UI for any of this — it's all compile-time via `--dart-define`. See the README's FreeRouter/
  OpenRouter sections for the full flag tables.
- **Domain model**: `ChatMessage` (`lib/features/chat/domain/chat_message.dart`) is an immutable value type
  with `copyWith`; `ChatRole` is `user` or `assistant`. Pending/in-flight assistant messages use
  `isPending: true` so the UI can find-and-remove the "Thinking..." bubble once the real reply arrives.
  `imageBytes`/`imageMimeType` optionally carry a user-attached image (picked via `image_picker` in
  `chat_page.dart`); only populated on user messages, and only `OpenAiChatRepository`/
  `OpenRouterChatRepository` currently forward it to the model as multimodal content.
- **Security note**: `OpenAiChatRepository` and `OpenRouterChatRepository` call their respective APIs
  directly from the client with the API key embedded at build time via `--dart-define`. The README
  explicitly flags that production apps should proxy through a backend instead of shipping the key in the
  client — keep this in mind before extending these further rather than treating them as production-ready
  as-is. `FreeRouterChatRepository` keeps provider API keys out of the client entirely (they live in
  FreeRouter's own config), but if `FREEROUTER_API_KEY` is used for FreeRouter's own endpoint auth, the same
  "don't ship secrets in a public client build" caveat applies to it too.
- **Theming**: `lib/core/app_theme.dart` provides Material 3 light/dark `ThemeData` via `ColorScheme.fromSeed`;
  `main.dart` wires both into `MaterialApp` with `themeMode: ThemeMode.system`.
- **Testing pattern**: `OpenAiChatRepository`, `OpenRouterChatRepository`, and `FreeRouterChatRepository` all
  accept an injectable `http.Client`, which is how `test/openai_chat_repository_test.dart`,
  `test/open_router_chat_repository_test.dart`, and `test/free_router_chat_repository_test.dart` swap in
  `MockClient` from `package:http/testing.dart` to assert on outgoing request bodies/headers (and exercise
  retry/fallback behavior) without hitting the network.
- **`run_openrouter.bat`**: a Windows convenience launcher that runs `flutter run -d chrome` with
  `OPENROUTER_API_KEY` set. The committed copy uses a placeholder (`YOUR_API_KEY_HERE`) — fill in a real key
  locally only, and never commit one back into this file.
- **`freerouter/`** (git-ignored) and **`freerouter_integration_spec.md`**: a local clone of the
  self-hosted FreeRouter project used during development of `FreeRouterChatRepository`, plus the design spec
  that integration was built from. Neither is part of this app's build; `freerouter/` is excluded from
  version control because it's its own separate git repository.
