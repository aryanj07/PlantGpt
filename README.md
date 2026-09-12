# PlantGPT Flutter Starter

A ChatGPT-style Flutter app with the database linkage isolated behind a repository contract.

## What is included

- Chat screen with assistant/user bubbles
- Message composer with loading state
- OpenAI Responses API repository that can behave like ChatGPT when an API key is supplied
- FreeRouter repository for routing chat requests through a self-hosted free-model router
- OpenRouter repository for routing chat requests through OpenRouter.ai's hosted free-model router
- Plant background image asset for the chat screen
- Material 3 light/dark theme
- `ChatRepository` interface for storage and assistant responses
- `LocalChatRepository` mock implementation for development
- `DatabaseChatRepository` placeholder for your real database/API linkage

## Database linkage

The UI only talks to `ChatRepository`:

```dart
abstract class ChatRepository {
  Future<List<ChatMessage>> loadMessages(String conversationId);
  Future<void> clearMessages(String conversationId);
  Future<ChatMessage> saveUserMessage({required String conversationId, required String content});
  Future<ChatMessage> createAssistantReply({required String conversationId, required String userMessage});
}
```

To connect a real database, add another implementation in `lib/features/chat/data/`, for example:

- `ApiChatRepository` for your own backend
- `FirebaseChatRepository` for Firestore
- `SupabaseChatRepository` for Supabase
- `SqliteChatRepository` for local/offline storage

Then replace this line in `lib/main.dart`:

```dart
home: ChatPage(repository: LocalChatRepository()),
```

with your real repository.

## OpenAI setup

The app reads the API key at build/run time with Dart defines. Do not commit a
real key into source code.

```powershell
flutter run --dart-define=OPENAI_API_KEY=your_api_key_here
```

By default the app uses `gpt-5`, matching OpenAI's current quickstart examples.
You can override it:

```powershell
flutter run --dart-define=OPENAI_API_KEY=your_api_key_here --dart-define=OPENAI_MODEL=gpt-5-mini
```

For production apps, route requests through your own backend so the API key is
not exposed in the mobile or web client.

## FreeRouter setup (optional free-model backend)

[FreeRouter](https://github.com/openfreerouter/freerouter) is a self-hosted, OpenAI-compatible
router/proxy. It classifies each request and routes it to whichever provider/model you've
configured *in FreeRouter itself* — it is not itself a source of free inference. Whether a
response is actually free depends entirely on the providers/models you configure FreeRouter with.

### 1. What it does

`FreeRouterChatRepository` (`lib/features/chat/data/free_router_chat_repository.dart`) sends chat
requests to FreeRouter's `POST /v1/chat/completions` endpoint with `model: "auto"` and lets
FreeRouter's classifier pick a configured tier/model. The app never talks to upstream providers
directly in this mode — FreeRouter holds those provider API keys in its own config, not in this
client.

### 2. Install and run FreeRouter

```bash
git clone https://github.com/openfreerouter/freerouter.git
cd freerouter
npm install
npx tsc
node dist/src/server.js
```

It listens on `http://localhost:18800` by default. Verify it before wiring up the app:

```bash
curl http://localhost:18800/health
curl http://localhost:18800/v1/models
```

### 3. Configure the free model in FreeRouter

Edit FreeRouter's own config so each tier points at a provider/model you have **verified** is
free or within a genuine free-tier allowance — do not copy example model names blindly:

```json
{
  "providers": {
    "freeProvider": { "baseUrl": "<provider-base-url>", "api": "openai" }
  },
  "tiers": {
    "SIMPLE": { "model": "<verified-free-model>", "provider": "freeProvider" },
    "MEDIUM": { "model": "<verified-free-model>", "provider": "freeProvider" },
    "COMPLEX": { "model": "<verified-free-or-free-tier-model>", "provider": "freeProvider" },
    "REASONING": { "model": "<verified-free-or-free-tier-model>", "provider": "freeProvider" }
  }
}
```

> Document which exact provider/model you end up using and what "free" means for it (e.g. a
> monthly quota vs. unlimited). This project makes no assumption about that for you.

### 4. Configure the app

This app has no `.env`/dotenv mechanism — all configuration (including the existing
`OPENAI_API_KEY`) is passed at build/run time via `--dart-define`, so FreeRouter follows the same
pattern rather than introducing a second config system:

```powershell
flutter run --dart-define=FREEROUTER_ENABLED=true
```

Available flags (all optional except `FREEROUTER_ENABLED`):

| Flag | Default | Purpose |
| --- | --- | --- |
| `FREEROUTER_ENABLED` | `false` | Turns on the FreeRouter backend. When `false`, behavior is unchanged (falls back to `OPENAI_API_KEY` or the local mock). |
| `FREEROUTER_BASE_URL` | `http://localhost:18800` | FreeRouter's base URL. Use a Docker service name (e.g. `http://freerouter:18800`) if the app and FreeRouter run in the same Docker network. |
| `FREEROUTER_MODEL` | `auto` | Passed as `model` in the request. Leave as `auto` unless you deliberately want to force a routing mode. |
| `FREEROUTER_TIMEOUT_MS` | `30000` | Per-request timeout. |
| `FREEROUTER_MAX_RETRIES` | `2` | Retries only on timeouts, connection failures, 429, 502/503/504, with exponential backoff + jitter. Never retries 400/401/403 or malformed responses. |
| `FREEROUTER_API_KEY` | *(empty)* | Optional bearer token for FreeRouter's **own** endpoint auth, if you've put it behind one. This is not a provider API key. |
| `LLM_FALLBACK_ENABLED` | `false` | If `true` **and** `OPENAI_API_KEY` is also supplied, a transient FreeRouter failure (unavailable/timeout/rate-limited/upstream 5xx) falls back to `OpenAiChatRepository` for that turn. Do not enable this if the product requirement is strictly free-only. |

Example wired to FreeRouter with an OpenAI fallback:

```powershell
flutter run --dart-define=FREEROUTER_ENABLED=true --dart-define=LLM_FALLBACK_ENABLED=true --dart-define=OPENAI_API_KEY=your_api_key_here
```

### 5. Start the application

```powershell
flutter pub get
flutter run --dart-define=FREEROUTER_ENABLED=true
```

### 6. Verify the integration

1. Confirm FreeRouter is up: `curl http://localhost:18800/health`.
2. In the app, ask a simple question (e.g. "What is 2 + 2?") and confirm a reply appears.
3. Check FreeRouter's own logs/`/stats` to confirm the request landed on the free tier/model you
   configured, not an unexpected paid one.

### 7. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "AI service is temporarily unavailable" immediately | FreeRouter isn't running, wrong `FREEROUTER_BASE_URL`, or (on a real device/emulator) `localhost` doesn't resolve to your host machine — use your machine's LAN IP or an Android emulator alias (`10.0.2.2`) instead of `localhost`. |
| "AI service is not configured correctly" | FreeRouter (or a provider behind it) rejected auth — check FreeRouter's provider API keys, or `FREEROUTER_API_KEY` if FreeRouter itself requires one. |
| "The AI service is busy right now" | FreeRouter/provider rate limit; retries were exhausted. Retry later or check FreeRouter's tier configuration. |
| Response never leaves the "Thinking..." state on web | Confirm FreeRouter allows CORS from your web origin, or proxy through a backend if not (see Security note below). |

### Security note

Provider API keys belong in FreeRouter's own configuration, never in this Flutter client or in
source control. `FREEROUTER_API_KEY` (if used) authenticates the app to FreeRouter itself, not to
any upstream provider. If you deploy this app as a public web build talking to a FreeRouter
instance that is not otherwise access-controlled, put FreeRouter behind your own
auth/rate-limiting layer rather than exposing it directly to the internet.

## OpenRouter.ai setup (hosted free-model backend)

[OpenRouter.ai](https://openrouter.ai) is a separate, **hosted** service — unrelated to the
self-hosted FreeRouter above, despite the similar name. It has a built-in "Free Models Router"
feature that auto-selects a random free model from the ones it hosts. No local server to run;
it's just another hosted HTTPS API, the same shape as the existing OpenAI integration.

### 1. What it does

`OpenRouterChatRepository` (`lib/features/chat/data/open_router_chat_repository.dart`) sends chat
requests to `https://openrouter.ai/api/v1/chat/completions` with `model: "openrouter/free"`.
OpenRouter picks a random free model per request and reports which one it used in the response
(useful for debugging, not currently surfaced in the UI).

### 2. Get an API key

Sign up at [openrouter.ai](https://openrouter.ai) and create an API key. The Free Models Router
itself costs nothing to call, but you still need a real OpenRouter API key tied to your account.

### 3. Configure the app

Same `--dart-define` convention as `OPENAI_API_KEY` — OpenRouter is selected automatically when
`OPENROUTER_API_KEY` is supplied (no separate enabled flag needed):

```powershell
flutter run --dart-define=OPENROUTER_API_KEY=your_openrouter_api_key_here
```

| Flag | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | *(empty)* | Your OpenRouter.ai API key. Setting this selects `OpenRouterChatRepository`. |
| `OPENROUTER_MODEL` | `openrouter/free` | The model/router id. Leave as `openrouter/free` for auto free-model selection, or set a specific `<provider>/<model>:free` id for deterministic routing. |
| `OPENROUTER_SITE_URL` | *(empty)* | Optional attribution header (`HTTP-Referer`) OpenRouter shows on its public leaderboard. Safe to omit. |
| `OPENROUTER_SITE_NAME` | *(empty)* | Optional attribution header (`X-Title`), same purpose as above. |

`LLM_FALLBACK_ENABLED` (see the FreeRouter section above) also applies here: if `true` and
`OPENAI_API_KEY` is set, a transient OpenRouter failure falls back to `OpenAiChatRepository`.

If both `FREEROUTER_ENABLED=true` and `OPENROUTER_API_KEY` are set, FreeRouter takes priority.

### 4. Run it — including on the Android emulator

Because this is a plain hosted HTTPS endpoint (not `localhost`), there is no `10.0.2.2` networking
trick needed — it works the same on desktop, web, a real device, or the Android emulator:

```powershell
flutter run --dart-define=OPENROUTER_API_KEY=your_openrouter_api_key_here
```

### 5. Verify

Ask a question in the app. If you want to confirm which specific free model answered, check the
app's debug console for the `[openrouter_request]` log line, or inspect the raw response's
`model` field (not currently shown in the UI).

### Security note

Same caveat as the OpenAI integration: this embeds `OPENROUTER_API_KEY` in the client at build
time via `--dart-define`. Fine for local development; for a production/public build, proxy through
your own backend instead so the key isn't shipped in the client bundle.

## Run

```powershell
flutter pub get
flutter run
```
