import 'package:flutter/material.dart';

import 'core/app_theme.dart';
import 'features/chat/data/api_chat_repository.dart';
import 'features/chat/data/local_chat_repository.dart';
import 'features/chat/domain/chat_repository.dart';
import 'features/chat/presentation/chat_page.dart';
import 'features/documents/data/documents_api_client.dart';

void main() {
  runApp(const ChatApp());
}

class ChatApp extends StatelessWidget {
  const ChatApp({super.key});

  // The real PlantGPT backend (plan Section C.3) is the only wired-in
  // network path - no provider API key is ever embedded in this client
  // (plan risk B1). All LLM calls, retry/backoff/circuit-breaker, and
  // provider secrets live server-side in the LLM Gateway
  // (backend/app/modules/llm_gateway/). Without API_BASE_URL set, the app
  // falls back to the in-memory LocalChatRepository mock for offline dev.
  static const _apiBaseUrl = String.fromEnvironment('API_BASE_URL');

  // TODO: replace with real Auth0 login in the client (a separate task) -
  // these dev headers are a stand-in until then, mirroring the backend's
  // own documented dev-mode fallback (backend/app/modules/auth/service.py).
  // Delete this path, don't just stop passing it, once real login lands.
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

  @override
  Widget build(BuildContext context) {
    final ChatRepository repository = _apiBaseUrl.isNotEmpty
        ? ApiChatRepository(
            baseUrl: _apiBaseUrl,
            sessionToken: _apiSessionToken.isEmpty ? null : _apiSessionToken,
            devTenantId: _apiSessionToken.isEmpty ? _apiDevTenantId : null,
            devUserId: _apiSessionToken.isEmpty ? _apiDevUserId : null,
          )
        : LocalChatRepository();

    // Document upload (Phase 3 RAG) only has a real backend to talk to when
    // API_BASE_URL is set - same condition as the repository choice above.
    final documentsClient = _apiBaseUrl.isEmpty
        ? null
        : DocumentsApiClient(
            baseUrl: _apiBaseUrl,
            sessionToken: _apiSessionToken.isEmpty ? null : _apiSessionToken,
            devTenantId: _apiSessionToken.isEmpty ? _apiDevTenantId : null,
            devUserId: _apiSessionToken.isEmpty ? _apiDevUserId : null,
          );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlantGPT',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: ChatPage(repository: repository, documentsClient: documentsClient),
    );
  }
}
