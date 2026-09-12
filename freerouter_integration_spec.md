# FreeRouter Integration — Product Specification & Design Plan

## 1. Purpose

Integrate **FreeRouter** into the existing application so that a user's natural-language question is sent through a local/self-hosted model router and the application returns the best available **free / zero-cost model response**.

Reference project:
- FreeRouter: https://github.com/openfreerouter/freerouter
- Expected local endpoint: `http://localhost:18800`
- OpenAI-compatible chat endpoint: `/v1/chat/completions`

> Important: FreeRouter is a router/proxy, not itself a provider of unlimited free inference. The implementation must configure providers/models that are actually free or have a zero-cost/free-tier allowance. Do not assume that a model is free merely because FreeRouter can route to it.

The implementation should preserve the existing application's user experience and introduce FreeRouter as the model-inference layer with minimal coupling.

---

# 2. Primary User Experience

The desired flow is:

```text
User
  |
  | asks a question
  v
Existing App
  |
  | normalized chat request
  v
FreeRouter
  |  http://localhost:18800/v1/chat/completions
  |
  | classifier selects configured free model
  v
Free / Free-tier LLM Provider
  |
  v
FreeRouter
  |
  v
Existing App
  |
  v
Answer shown to user
```

Example:

```text
User: "Explain photosynthesis in simple words."

App -> FreeRouter:
{
  "model": "auto",
  "messages": [
    {
      "role": "user",
      "content": "Explain photosynthesis in simple words."
    }
  ]
}

FreeRouter -> configured free model -> response

App -> User:
"Photosynthesis is the process by which..."
```

The application should NOT expose FreeRouter internals to the end user unless a developer/debug mode is enabled.

---

# 3. Goals

## Functional goals

1. Send normal user questions to FreeRouter.
2. Use the OpenAI-compatible `/v1/chat/completions` interface.
3. Use `model: "auto"` unless a deliberate override is required.
4. Allow FreeRouter to select the appropriate configured model/tier.
5. Prefer models/providers with a genuine free/free-tier allowance.
6. Support normal non-streaming responses initially.
7. Support streaming as a second implementation phase if the current application UX benefits from it.
8. Preserve conversation history where the existing application already supports it.
9. Support system prompts if the current application uses them.
10. Return a clean assistant response to the existing UI.
11. Add graceful timeout, retry, and user-friendly error handling.
12. Keep provider API keys outside source code.
13. Make the FreeRouter URL configurable through environment variables.
14. Make the feature easy to disable and fall back to the application's existing model provider if one exists.

## Engineering goals

- Minimal architectural disruption.
- Clear separation between UI/business logic and LLM transport.
- No FreeRouter-specific code scattered throughout the application.
- Testable integration.
- Easy future replacement of FreeRouter.
- No secrets committed to Git.
- Good logging without logging sensitive user prompts by default.

---

# 4. Non-Goals

Do NOT:

- Rewrite the application's existing UI unnecessarily.
- Reimplement FreeRouter's classifier inside the application.
- Fork or substantially modify FreeRouter unless a concrete integration blocker is discovered.
- Hard-code provider API keys.
- Assume all FreeRouter models are free.
- Build a new agent framework as part of this task.
- Add unnecessary database infrastructure.
- Replace the application's existing state-management architecture unless required.
- Add streaming before the basic request/response path is proven.

---

# 5. Key FreeRouter Capabilities to Use

FreeRouter provides an OpenAI-compatible endpoint:

```text
POST http://localhost:18800/v1/chat/completions
```

The documented request shape is compatible with:

```json
{
  "model": "auto",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    }
  ]
}
```

FreeRouter supports automatic routing using a multi-dimensional classifier and can route requests to configured tiers/models.

It also provides useful operational endpoints:

```text
GET  /health
GET  /stats
GET  /v1/models
GET  /config
POST /reload
POST /reload-config
```

Use `/health` for connectivity checks and `/stats` only where diagnostics are useful.

Do not make application functionality depend on `/stats`.

---

# 6. Important Design Decision: Free Models

The implementation must introduce an explicit concept of a **free-model policy**.

Recommended configuration:

```env
FREEROUTER_BASE_URL=http://localhost:18800
FREEROUTER_MODEL=auto
FREEROUTER_ENABLED=true
FREEROUTER_TIMEOUT_MS=30000
FREEROUTER_MAX_RETRIES=2
```

If the application has an existing configuration system, use that instead of introducing a second configuration mechanism.

FreeRouter's own configuration should contain the provider/model mapping.

Example conceptual configuration:

```json
{
  "providers": {
    "freeProvider": {
      "baseUrl": "<provider-base-url>",
      "api": "openai"
    }
  },
  "tiers": {
    "SIMPLE": {
      "model": "<verified-free-model>",
      "provider": "freeProvider"
    },
    "MEDIUM": {
      "model": "<verified-free-model>",
      "provider": "freeProvider"
    },
    "COMPLEX": {
      "model": "<verified-free-or-free-tier-model>",
      "provider": "freeProvider"
    },
    "REASONING": {
      "model": "<verified-free-or-free-tier-model>",
      "provider": "freeProvider"
    }
  }
}
```

Do NOT copy model names from an old FreeRouter example blindly. Verify the currently supported provider/model identifiers before deployment.

The final implementation should document exactly which provider/model is being used and what "free" means for that provider.

---

# 7. Proposed Application Architecture

Introduce an abstraction:

```text
UI / Controller
       |
       v
Question / Chat Service
       |
       v
LLMClient interface
       |
       +--------------------+
       |                    |
       v                    v
FreeRouterClient      ExistingLLMClient
       |
       v
FreeRouter
```

Recommended interface:

```ts
interface LLMClient {
  chat(request: ChatRequest): Promise<ChatResponse>;
}
```

If the project is JavaScript rather than TypeScript, implement the same abstraction using plain objects/functions.

Recommended FreeRouter adapter:

```text
FreeRouterClient
  - baseUrl
  - model
  - timeout
  - retry policy
  - headers
  - chat()
  - healthCheck()
```

The rest of the application should depend on `LLMClient`, not directly on Axios/fetch calls to FreeRouter.

---

# 8. Request Contract

Normalize application requests into an internal structure:

```ts
type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

type ChatRequest = {
  messages: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
};
```

Convert this internal contract to FreeRouter's OpenAI-compatible format.

Example:

```json
{
  "model": "auto",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What is machine learning?"
    }
  ],
  "temperature": 0.2
}
```

Only send parameters that are actually supported by the current FreeRouter/provider combination.

Do not blindly forward every UI option.

---

# 9. Response Contract

Normalize the provider response back into the application's internal response:

```ts
type ChatResponse = {
  content: string;
  model?: string;
  finishReason?: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };
};
```

The UI should primarily consume:

```text
response.content
```

Provider-specific response structures must remain inside the FreeRouter adapter.

---

# 10. Error Handling

Implement explicit error categories:

### A. FreeRouter unavailable

Examples:

- connection refused
- DNS failure
- process not running
- `/health` unavailable

User-facing behavior:

```text
AI service is temporarily unavailable. Please try again.
```

Developer log:

```text
FreeRouter unavailable: <technical error>
```

### B. Provider/model failure

If FreeRouter reports an upstream provider failure:

- allow FreeRouter's configured fallback mechanism to work;
- do not implement competing routing logic in the application;
- surface a clean error if all configured routes fail.

### C. Timeout

Use a configurable timeout.

Recommended initial value:

```text
30 seconds
```

Make it configurable.

### D. Rate limit

Return a user-friendly message and preserve the ability to retry.

### E. Invalid response

If the response does not contain a usable assistant message:

- log the response metadata;
- do not crash the application;
- return a controlled error.

Never expose API keys or full upstream error payloads to users.

---

# 11. Retry Strategy

Do not create aggressive retries.

Recommended:

```text
max retries = 2
```

Retry only transient failures:

- connection reset
- timeout
- 502
- 503
- 504
- potentially 429 with controlled backoff

Do NOT retry:

- malformed request
- authentication failure
- unsupported model
- invalid configuration
- 400-level validation errors

Use exponential backoff with jitter.

---

# 12. Health Check

Add a FreeRouter health-check function.

Example:

```text
GET /health
```

Expected behavior:

```text
healthy -> application can use FreeRouter
unhealthy -> fail gracefully / use fallback
```

Health checks should NOT run before every user request if this adds noticeable latency.

Preferred options:

1. Startup check.
2. Optional periodic background check.
3. On-demand check after a connection failure.

---

# 13. Fallback Strategy

Preferred hierarchy:

```text
Application
   |
   v
FreeRouter
   |
   +--> Free Model A
   |
   +--> Free Model B
   |
   +--> Free Model C
```

FreeRouter should handle model/provider fallback where possible.

If the application already has another LLM provider:

```text
Application
   |
   v
FreeRouter
   |
   +--> success -> response
   |
   +--> failure
          |
          v
   Existing LLM client
```

Do not add a paid fallback if the product requirement is strictly "free model only."

If no valid free fallback exists, return a clear service-unavailable response.

---

# 14. Streaming

### Phase 1

Implement:

```text
stream = false
```

First prove:

- request works;
- model routing works;
- response parsing works;
- errors work;
- conversation history works.

### Phase 2

If the application requires a ChatGPT-like experience, implement:

```text
stream = true
```

The adapter should translate the SSE response into the application's existing streaming abstraction.

Do not expose provider-specific SSE parsing to the UI.

---

# 15. Conversation Context

FreeRouter's classifier can use recent context, but the application remains responsible for constructing the actual conversation sent to the model.

For every request:

```text
system message
+
relevant conversation history
+
latest user question
```

Do not send unlimited history.

If the existing application has a context-window strategy, preserve it.

If there is no strategy, introduce a simple configurable history limit rather than blindly sending every historical message.

---

# 16. Mode Overrides

FreeRouter supports explicit routing prefixes such as:

```text
/simple
/medium
/complex
/max
/reasoning
```

Do not automatically add these prefixes to normal user questions.

Default behavior:

```text
model = auto
```

Only support explicit mode selection if the product actually needs it.

If supported by the UI, map it separately:

```text
UI: "Fast"
   -> /simple

UI: "Balanced"
   -> /medium

UI: "Best"
   -> /complex
```

Do not expose internal routing terminology unless useful to users.

---

# 17. Security

## API keys

Never:

- commit API keys;
- put API keys in frontend code;
- send provider API keys to the browser;
- log provider API keys.

Keys belong in:

```text
environment variables
or
FreeRouter configuration
```

## Browser architecture

If this is a browser application:

```text
Browser
   |
   v
Application backend
   |
   v
FreeRouter
```

Do NOT:

```text
Browser -> FreeRouter with provider secrets
```

If the application is currently frontend-only, add the smallest possible backend/server layer required to safely proxy requests.

---

# 18. Repository Inspection Instructions for Claude

Before changing code, Claude must inspect the existing repository.

Required inspection:

1. Identify application type:
   - Node.js
   - TypeScript
   - JavaScript
   - Flutter
   - Python backend
   - other

2. Inspect:
   - `package.json`
   - source tree
   - existing API/client layer
   - existing LLM integration
   - environment/config files
   - application entry point
   - tests
   - README

3. Find:
   - current question submission flow
   - current LLM request implementation
   - response parsing
   - chat history/state
   - error handling
   - streaming support

4. Do not assume the architecture described in this document exactly matches the repository.

5. Adapt the design to the repository while preserving the requirements in this specification.

6. Before implementation, produce a short implementation map:

```text
Existing component -> change
Existing component -> no change
New component -> add
Config -> change
Tests -> add
```

Then implement.

---

# 19. Expected File-Level Design

The exact paths depend on the repository.

Preferred conceptual structure:

```text
src/
  llm/
    LLMClient.*
    FreeRouterClient.*
    types.*
  config/
    ...
  services/
    ChatService.*
```

If the repository already has an equivalent structure, extend it instead of creating parallel architecture.

Example:

```text
src/llm/FreeRouterClient.ts
```

Responsibilities:

- construct FreeRouter URL;
- construct request;
- send request;
- parse response;
- timeout;
- retry;
- normalize errors.

It should NOT:

- update UI;
- manipulate application state;
- decide business logic;
- implement its own model classifier.

---

# 20. Configuration

Preferred environment configuration:

```env
FREEROUTER_ENABLED=true
FREEROUTER_BASE_URL=http://localhost:18800
FREEROUTER_MODEL=auto
FREEROUTER_TIMEOUT_MS=30000
FREEROUTER_MAX_RETRIES=2
```

If a fallback LLM exists:

```env
LLM_FALLBACK_ENABLED=true
```

Never commit actual secret values.

Add/update:

```text
.env.example
```

with placeholders.

---

# 21. Local Development Setup

FreeRouter's documented setup is approximately:

```bash
git clone https://github.com/openfreerouter/freerouter.git
cd freerouter
npm install
npx tsc
node dist/src/server.js
```

It listens by default on:

```text
http://localhost:18800
```

The integration implementation must verify the actual repository version being used before relying on exact commands or configuration fields.

Verify:

```bash
curl http://localhost:18800/health
```

Then verify:

```bash
curl http://localhost:18800/v1/models
```

Then send a minimal chat request.

---

# 22. Docker Option

If the application is containerized, prefer:

```text
application container
       |
       | Docker network
       v
freerouter container
       |
       v
provider
```

Do not use:

```text
localhost:18800
```

from inside the application container unless FreeRouter actually runs inside the same container/network namespace.

Use the Docker service name, for example:

```env
FREEROUTER_BASE_URL=http://freerouter:18800
```

Only use this if the repository's Docker setup supports it.

---

# 23. Testing Plan

## Unit tests

Test `FreeRouterClient` with mocked HTTP responses.

Required cases:

1. Successful response.
2. Empty response.
3. Malformed response.
4. 400 error.
5. 401/403 error.
6. 429 error.
7. 500 error.
8. 502 error.
9. 503 error.
10. Timeout.
11. Connection refused.
12. Retry succeeds.
13. Retry exhausted.
14. System + user + assistant messages.
15. Unicode.
16. Long prompt.

## Integration tests

When FreeRouter is available:

1. `/health` works.
2. `/v1/models` works.
3. `model=auto` works.
4. Basic question receives response.
5. Conversation context works.
6. Configured free model is actually selected.
7. Provider fallback works if configured.

## UI tests

Verify:

1. User enters question.
2. Submit button works.
3. Loading state appears.
4. Response appears.
5. Error state appears.
6. Multiple sequential questions work.
7. Conversation history remains correct.

---

# 24. Acceptance Criteria

The feature is complete only when all of the following are true:

### Core

- [ ] Application can send a user question through FreeRouter.
- [ ] FreeRouter is configurable through environment/config.
- [ ] `model=auto` works.
- [ ] Response is rendered in the existing application.
- [ ] Existing application behavior is not unnecessarily broken.

### Free-model requirement

- [ ] At least one configured provider/model has been verified as free or has a documented free-tier allowance.
- [ ] The exact model/provider is documented.
- [ ] The application does not silently route to a paid model if strict free-only mode is enabled.
- [ ] FreeRouter fallback configuration is reviewed for the same requirement.

### Reliability

- [ ] Timeout is implemented.
- [ ] Transient retry is implemented.
- [ ] User-friendly error handling exists.
- [ ] FreeRouter unavailable state is handled.
- [ ] Provider failure is handled.

### Security

- [ ] No secrets in source code.
- [ ] No provider secrets in browser/client bundles.
- [ ] Sensitive prompts/errors are not unnecessarily logged.

### Testing

- [ ] Unit tests pass.
- [ ] Integration test passes against a running FreeRouter.
- [ ] Existing test suite passes.
- [ ] Build/lint/typecheck passes.

---

# 25. Observability

Log only useful metadata.

Recommended:

```text
request_id
timestamp
route = freerouter
configured_model = auto
latency_ms
success/failure
status_code
retry_count
```

Optional debug-only metadata:

```text
selected tier
selected provider
selected model
```

Never log:

```text
API keys
authorization headers
full conversation history
sensitive user content
```

unless explicitly enabled for local development.

---

# 26. Performance Targets

Initial targets:

```text
Application overhead introduced by adapter: <100ms
Connection setup: reused where possible
Timeout: configurable, default 30s
Retries: max 2
```

Do not optimize prematurely.

Measure:

```text
request start
FreeRouter request start
FreeRouter response
application response rendered
```

This will make it possible to distinguish:

```text
app latency
vs
FreeRouter latency
vs
provider/model latency
```

---

# 27. Implementation Phases

## Phase 0 — Repository Discovery

Claude must:

- inspect repository;
- identify current LLM flow;
- identify backend/frontend boundaries;
- identify configuration approach;
- identify test framework;
- identify whether streaming already exists.

Deliverable:

```text
implementation map
```

No code changes yet.

---

## Phase 1 — FreeRouter Connectivity

Implement:

- configuration;
- FreeRouter client;
- health check;
- basic `/v1/chat/completions` call;
- response parsing.

Validate manually with:

```text
"What is 2 + 2?"
```

---

## Phase 2 — Application Integration

Connect:

```text
User question
   ->
existing ChatService
   ->
FreeRouterClient
   ->
response
   ->
existing UI
```

Keep the UI changes minimal.

---

## Phase 3 — Reliability

Add:

- timeout;
- retry;
- error normalization;
- fallback behavior;
- logging.

---

## Phase 4 — Tests

Add:

- unit tests;
- integration tests;
- UI tests where applicable.

Run all existing tests.

---

## Phase 5 — Streaming

Only if required by the application.

Implement SSE streaming without leaking provider-specific implementation details into UI code.

---

## Phase 6 — Production Hardening

Validate:

- secrets;
- CORS;
- authentication;
- rate limiting;
- logging;
- Docker/networking;
- health checks;
- free-model policy;
- provider fallback.

---

# 28. Claude Code Execution Rules

Claude should follow these rules while implementing:

### Rule 1 — Inspect first

Never start by creating files based only on this specification.

### Rule 2 — Reuse existing abstractions

If the project already has an LLM client/service, extend it.

### Rule 3 — Smallest safe change

Avoid unrelated refactoring.

### Rule 4 — Keep FreeRouter isolated

Only the FreeRouter adapter should know that FreeRouter exists.

### Rule 5 — Preserve compatibility

Existing application functionality must continue to work.

### Rule 6 — Test incrementally

After each major change:

```text
typecheck/build
tests
integration test
```

### Rule 7 — No fake success

Do not claim FreeRouter integration works until an actual request reaches:

```text
/v1/chat/completions
```

and receives a valid response.

### Rule 8 — Verify free-model assumptions

Before declaring the implementation "free", verify the configured provider/model's current pricing/free-tier terms.

### Rule 9 — Do not modify FreeRouter unnecessarily

Prefer configuring FreeRouter rather than changing its source.

### Rule 10 — Explain deviations

If repository constraints require deviating from this specification, document:

```text
Requirement
Original design
Repository constraint
Implemented alternative
Reason
```

---

# 29. Final Deliverables Expected From Claude

At completion Claude must provide:

## Code

- FreeRouter integration.
- Configuration.
- Error handling.
- Tests.
- Documentation.

## Documentation

Update the project README with:

```text
1. What FreeRouter does
2. How to install/run FreeRouter
3. How to configure the application
4. How to configure the free model
5. How to start the application
6. How to verify integration
7. Troubleshooting
```

## Final implementation report

Claude should report:

```text
### Implemented
- ...

### Files changed
- ...

### Configuration added
- ...

### Tests
- ...

### Free model/provider used
- ...

### Verification
- ...

### Known limitations
- ...

### Next steps
- ...
```

---

# 30. Recommended Final Architecture

The target architecture is:

```text
                 +----------------------+
                 |      User / UI       |
                 +----------+-----------+
                            |
                            | Question
                            v
                 +----------------------+
                 |   Existing App       |
                 |   Chat/AI Service    |
                 +----------+-----------+
                            |
                            | LLMClient
                            v
                 +----------------------+
                 |   FreeRouterClient   |
                 |----------------------|
                 | timeout              |
                 | retry                |
                 | request mapping      |
                 | response mapping     |
                 | error normalization  |
                 +----------+-----------+
                            |
                            | HTTP
                            v
                 +----------------------+
                 |      FreeRouter      |
                 |      :18800          |
                 |----------------------|
                 | 14-dim classification|
                 | tier routing         |
                 | fallback             |
                 +----------+-----------+
                            |
               +------------+------------+
               |            |            |
               v            v            v
          Free Model A  Free Model B  Free Model C
               |
               v
            Response
               |
               v
        Existing Application
               |
               v
             User
```

---

# 31. Definition of Done

The implementation is considered DONE when a fresh developer can clone the application, configure the documented FreeRouter/free-model settings, start the services, enter:

```text
Explain what an AI agent is.
```

and receive a valid answer through:

```text
Application
    -> FreeRouter
    -> verified free/free-tier model
    -> FreeRouter
    -> Application UI
```

without requiring changes to application source code for provider/model configuration.

The integration must be maintainable, testable, secure, and isolated enough that FreeRouter can later be replaced by another OpenAI-compatible router/client with minimal application changes.
