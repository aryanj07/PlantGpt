# PlantGPT

A ChatGPT-style Flutter assistant for **industrial plant operations** — cement plants, steel
plants, and manufacturing plants — paired with a FastAPI backend that owns auth, the LLM Gateway,
and (eventually) RAG/MCP. ("Plant" here means an industrial facility, not a houseplant.)

## What is included

- Chat screen with assistant/user bubbles, system-prompted for cement/steel/manufacturing
  plant-operations questions (process parameters, equipment troubleshooting, production-line
  optimization, maintenance, safety)
- Message composer with loading state and optional image attachment (via `image_picker`) — handy
  for sharing a photo of equipment or a gauge reading (not yet forwarded to the model — see
  `ApiChatRepository`'s doc comment)
- `ApiChatRepository` — the production `ChatRepository` implementation, talking to the FastAPI
  backend in `backend/`. No LLM provider API key is embedded in this client at all.
- Material 3 light/dark theme
- `ChatRepository` interface for storage and assistant responses
- `LocalChatRepository` mock implementation for offline development (no backend required)
- `DatabaseChatRepository` — unimplemented placeholder, superseded by `ApiChatRepository` now that
  a real backend exists; kept only as the original template/reference

## Backend setup

The client has nothing to talk to without the backend running. See `backend/README.md` for full
setup (Python venv, `.env`, Auth0 config, tests). Quick version:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Then run the Flutter client wired to it:

```powershell
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Or double-click/run `run_local_backend.bat`, which does the same thing for Chrome. Without
`API_BASE_URL` set, the app falls back to `LocalChatRepository` (in-memory mock, no network).

Auth: real Auth0 login isn't wired into the Flutter client yet. Until then, `ApiChatRepository`
sends the backend's dev-mode `X-Dev-Tenant-Id`/`X-Dev-User-Id` headers, configurable via
`--dart-define=API_DEV_TENANT_ID=...`/`API_DEV_USER_ID=...` (defaults: `default`/`dev-user`) — or
pass a real session token from `POST /v1/auth/session` via `--dart-define=API_SESSION_TOKEN=...`.

## Database/repository contract

The UI only talks to `ChatRepository`:

```dart
abstract class ChatRepository {
  Future<List<ChatMessage>> loadMessages(String conversationId);
  Future<void> clearMessages(String conversationId);
  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  });
  Future<ChatMessage> createAssistantReply({required String conversationId, required String userMessage});
}
```

`conversationId` here is just a local cache key (see `chat_page.dart`'s
`_generateLocalConversationId`) — it carries no meaning to the backend, which resolves "your"
conversation from the authenticated identity instead. To point the app at a different backend
entirely, add another implementation in `lib/features/chat/data/` and swap the repository passed
into `ChatPage` in `lib/main.dart` (`ChatApp.build`).

## Legacy direct-provider repositories (not wired in)

`OpenAiChatRepository`, `OpenRouterChatRepository`, and `FreeRouterChatRepository`
(`lib/features/chat/data/`) predate the backend and called LLM providers directly from the client,
with a provider API key embedded at build time via `--dart-define` — exactly the risk
`ApiChatRepository` was built to close. They're kept only because their tests are still useful
reference for the retry/backoff/fallback pattern the backend's LLM Gateway ported server-side
(`backend/app/modules/llm_gateway/`); the classes themselves are unreachable from `main.dart` and
should stay that way. Extend the backend's LLM Gateway instead of wiring one of these back in.

## Run

```powershell
flutter pub get
flutter run                                                    # LocalChatRepository mock
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000   # wired to a local backend
flutter test
```
