import 'package:flutter/material.dart';

import 'core/app_theme.dart';
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
    final ChatRepository repository = _freeRouterEnabled
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
                siteUrl: _openRouterSiteUrl.isEmpty ? null : _openRouterSiteUrl,
                siteName:
                    _openRouterSiteName.isEmpty ? null : _openRouterSiteName,
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
