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
  `lib/features/chat/data/` and swapped in at the single call site in `lib/main.dart`
  (`home: ChatPage(repository: ...)`).
- **Existing implementations**:
  - `LocalChatRepository` — in-memory mock, used when no API key is supplied. Default for local dev.
  - `OpenAiChatRepository` — calls OpenAI's Responses API (`POST /v1/responses`) directly from the client,
    truncates history to the last 16 non-pending messages, and prepends a fixed `_systemPrompt` as a
    `developer` role message. Selected automatically in `main.dart` when `OPENAI_API_KEY` is non-empty.
  - `DatabaseChatRepository` — unimplemented placeholder (`throw UnimplementedError`) intended as the
    template for wiring a real backend (Firestore, Supabase, custom API, SQLite, etc.).
- **Backend selection happens in `lib/main.dart`**: `ChatApp` reads `OPENAI_API_KEY`/`OPENAI_MODEL` via
  `String.fromEnvironment` (Dart defines, not `.env` files) and picks `LocalChatRepository` vs
  `OpenAiChatRepository` accordingly. There is no runtime config UI for this — it's compile-time via
  `--dart-define`.
- **Domain model**: `ChatMessage` (`lib/features/chat/domain/chat_message.dart`) is an immutable value type
  with `copyWith`; `ChatRole` is `user` or `assistant`. Pending/in-flight assistant messages use
  `isPending: true` so the UI can find-and-remove the "Thinking..." bubble once the real reply arrives.
- **Security note**: `OpenAiChatRepository` calls OpenAI directly from the client with the API key embedded
  at build time via `--dart-define`. The README explicitly flags that production apps should proxy through
  a backend instead of shipping the key in the client — keep this in mind before extending
  `OpenAiChatRepository` further rather than treating it as production-ready as-is.
- **Theming**: `lib/core/app_theme.dart` provides Material 3 light/dark `ThemeData` via `ColorScheme.fromSeed`;
  `main.dart` wires both into `MaterialApp` with `themeMode: ThemeMode.system`.
- **Testing pattern**: `OpenAiChatRepository` accepts an injectable `http.Client`, which is how
  `test/openai_chat_repository_test.dart` swaps in `MockClient` from `package:http/testing.dart` to assert on
  outgoing request bodies/headers without hitting the network.
