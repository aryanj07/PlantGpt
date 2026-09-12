import 'package:flutter/material.dart';

import 'core/app_theme.dart';
import 'features/chat/data/api_chat_repository.dart';
import 'features/chat/data/free_router_chat_repository.dart';
import 'features/chat/data/local_chat_repository.dart';
import 'features/chat/data/open_router_chat_repository.dart';
import 'features/chat/data/openai_chat_repository.dart';
import 'features/chat/domain/chat_repository.dart';
import 'features/chat/presentation/chat_page.dart';

void main() {
  runApp(const ChatApp());
}

class ChatApp extends StatelessWidget {
  const ChatApp({super.key});

  // The real PlantGPT backend (plan Section C.3) - when set, this takes
  // priority over every direct-to-provider repository below, since it's
  // the actual target architecture rather than a dev/legacy fallback.
  static const _apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  // TODO: replace with real Auth0 login in the client (a separate task) -
  // these dev headers are a stand-in until then, mirroring the backend's
  // own documented dev-mode fallback (app/modules/auth/service.py). Delete
  // this path, don't just stop passing it, once real login lands.
  static const _apiDevTenantId = String.fromEnvironment(
    'API_DEV_TENANT_ID',
    defaultValue: 'default',
  );
  static const _apiDevUserId = String.fromEnvironment(
    'API_DEV_USER_ID',
    defaultValue: 'dev-user',
  );
  // Optional: a real backend session token (from POST /v1/auth/session),
  // if you have one already, in place of the dev headers above.
  static const _apiSessionToken = String.fromEnvironment('API_SESSION_TOKEN');

  static const _openAiApiKey = String.fromEnvironment('OPENAI_API_KEY');
  static const _openAiModel = String.fromEnvironment(
    'OPENAI_MODEL',
    defaultValue: 'gpt-5',
  );

  // FreeRouter (https://github.com/openfreerouter/freerouter) is an
  // optional self-hosted router; it is off by default so existing behavior
  // (OPENAI_API_KEY -> OpenAI, otherwise -> the local mock) is unchanged.
  static const _freeRouterEnabled = bool.fromEnvironment('FREEROUTER_ENABLED');
  static const _freeRouterBaseUrl = String.fromEnvironment(
    'FREEROUTER_BASE_URL',
    defaultValue: 'http://localhost:18800',
  );
  static const _freeRouterModel = String.fromEnvironment(
    'FREEROUTER_MODEL',
    defaultValue: 'auto',
  );
  static const _freeRouterTimeoutMs = int.fromEnvironment(
    'FREEROUTER_TIMEOUT_MS',
    defaultValue: 30000,
  );
  static const _freeRouterMaxRetries = int.fromEnvironment(
    'FREEROUTER_MAX_RETRIES',
    defaultValue: 2,
  );
  // Optional bearer token for FreeRouter's own endpoint auth — not a
  // provider API key, those stay in FreeRouter's own config.
  static const _freeRouterApiKey = String.fromEnvironment('FREEROUTER_API_KEY');
  static const _llmFallbackEnabled = bool.fromEnvironment(
    'LLM_FALLBACK_ENABLED',
  );

  // OpenRouter.ai's hosted Free Models Router (https://openrouter.ai) — a
  // separate, hosted service, unrelated to the self-hosted FreeRouter above.
  // Selected automatically when an API key is supplied, same convention as
  // OPENAI_API_KEY below.
  static const _openRouterApiKey = String.fromEnvironment('OPENROUTER_API_KEY');
  static const _openRouterModel = String.fromEnvironment(
    'OPENROUTER_MODEL',
    defaultValue: 'openrouter/free',
  );
  static const _openRouterSiteUrl = String.fromEnvironment(
    'OPENROUTER_SITE_URL',
  );
  static const _openRouterSiteName = String.fromEnvironment(
    'OPENROUTER_SITE_NAME',
  );

  @override
  Widget build(BuildContext context) {
    final ChatRepository repository = _apiBaseUrl.isNotEmpty
        ? ApiChatRepository(
            baseUrl: _apiBaseUrl,
            sessionToken: _apiSessionToken.isEmpty ? null : _apiSessionToken,
            devTenantId: _apiSessionToken.isEmpty ? _apiDevTenantId : null,
            devUserId: _apiSessionToken.isEmpty ? _apiDevUserId : null,
          )
        : _freeRouterEnabled
            ? FreeRouterChatRepository(
                baseUrl: _freeRouterBaseUrl,
                model: _freeRouterModel,
                timeout: const Duration(milliseconds: _freeRouterTimeoutMs),
                maxRetries: _freeRouterMaxRetries,
                apiKey: _freeRouterApiKey.isEmpty ? null : _freeRouterApiKey,
                fallback: (_llmFallbackEnabled && _openAiApiKey.isNotEmpty)
                    ? OpenAiChatRepository(
                        apiKey: _openAiApiKey,
                        model: _openAiModel,
                      )
                    : null,
              )
            : _openRouterApiKey.isNotEmpty
                ? OpenRouterChatRepository(
                    apiKey: _openRouterApiKey,
                    model: _openRouterModel,
                    siteUrl:
                        _openRouterSiteUrl.isEmpty ? null : _openRouterSiteUrl,
                    siteName: _openRouterSiteName.isEmpty
                        ? null
                        : _openRouterSiteName,
                    fallback: (_llmFallbackEnabled && _openAiApiKey.isNotEmpty)
                        ? OpenAiChatRepository(
                            apiKey: _openAiApiKey,
                            model: _openAiModel,
                          )
                        : null,
                  )
                : _openAiApiKey.isEmpty
                    ? LocalChatRepository()
                    : OpenAiChatRepository(
                        apiKey: _openAiApiKey,
                        model: _openAiModel,
                      );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlantGPT',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: ChatPage(repository: repository),
    );
  }
}
