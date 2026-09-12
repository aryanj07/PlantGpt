import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

class ApiChatException implements Exception {
  const ApiChatException(this.message, {this.technicalDetails});

  /// User-facing message. Never contains tokens or raw backend payloads.
  final String message;

  /// Developer-only detail for logs. Never surfaced to the UI.
  final String? technicalDetails;

  @override
  String toString() => message;
}

/// Talks to the real PlantGPT backend (plan Section C.3) instead of an LLM
/// provider directly — the client no longer holds a provider API key or any
/// retry/circuit-breaker logic; that all moved server-side into the LLM
/// Gateway (plan Section H.1). This repository is intentionally thin.
///
/// Auth: real Auth0 login in the Flutter client doesn't exist yet (a
/// separate, later task). Until then, this repository sends either a
/// pre-obtained backend session token as `sessionToken` (once something
/// upstream has called `POST /v1/auth/session`), or falls back to the
/// backend's dev-mode `X-Dev-Tenant-Id`/`X-Dev-User-Id` headers — the exact
/// same fallback the backend's Auth Module documents as temporary
/// (`app/modules/auth/service.py`). Delete the dev-header path, don't just
/// stop using it, once real login lands client-side.
///
/// Conversation IDs: the backend issues its own UUIDs via
/// `POST /v1/conversations`; the [ChatRepository] interface only ever gives
/// this class a client-chosen `conversationId` string (an arbitrary
/// per-session value from `chat_page.dart` - it carries no meaning to the
/// backend). This class resolves that to a real backend conversation by
/// resuming the authenticated identity's most recent existing conversation,
/// creating one only if none exists yet (`_resolveBackendConversationId`) -
/// so chat history survives an app restart based on who you are, not on
/// which local string happened to be passed in.
class ApiChatRepository extends ChatRepository {
  ApiChatRepository({
    required String baseUrl,
    this.sessionToken,
    this.devTenantId,
    this.devUserId,
    this.timeout = const Duration(seconds: 45),
    http.Client? client,
  })  : baseUrl = baseUrl.endsWith('/')
            ? baseUrl.substring(0, baseUrl.length - 1)
            : baseUrl,
        _client = client ?? http.Client();

  final String baseUrl;
  final String? sessionToken;
  final String? devTenantId;
  final String? devUserId;
  final Duration timeout;

  final http.Client _client;
  final Map<String, String> _backendConversationIds = {};

  Map<String, String> get _headers {
    final headers = {'Content-Type': 'application/json'};
    final token = sessionToken;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
      return headers;
    }
    final tenant = devTenantId;
    final user = devUserId;
    if (tenant != null && tenant.isNotEmpty) {
      headers['X-Dev-Tenant-Id'] = tenant;
    }
    if (user != null && user.isNotEmpty) headers['X-Dev-User-Id'] = user;
    return headers;
  }

  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) async {
    final backendId = await _resolveBackendConversationId(conversationId);
    final response = await _get('/v1/conversations/$backendId/messages');

    if (response.statusCode != 200) {
      throw ApiChatException(
        'Failed to load conversation history (status ${response.statusCode}).',
        technicalDetails: response.body,
      );
    }

    final decoded = jsonDecode(response.body) as List<dynamic>;
    if (decoded.isEmpty) {
      return [_welcomeMessage(conversationId)];
    }
    return decoded
        .map((raw) =>
            _messageFromJson(raw as Map<String, dynamic>, conversationId))
        .toList();
  }

  @override
  Future<void> clearMessages(String conversationId) async {
    // Unlike the initial resolve below (which resumes the most recent
    // existing backend conversation, so a restart doesn't lose history),
    // "New chat" must always start a genuinely new one - so this creates
    // directly rather than going through the resume-or-create path. No
    // delete/archive endpoint exists yet (Phase 1 scope), so the old
    // conversation row is left behind server-side, just no longer reachable
    // from this client until real conversation listing/history UI exists.
    final backendId = await _createBackendConversation();
    _backendConversationIds[conversationId] = backendId;
  }

  @override
  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  }) async {
    // The backend persists the user message and generates the assistant
    // reply together, atomically, in one POST (plan Section E: the user
    // message is durably stored before any LLM call) - that round trip
    // happens in createAssistantReply, called right after this by
    // ChatPage. This just returns an optimistic local copy for immediate
    // UI feedback, matching every other ChatRepository implementation's
    // shape (see OpenRouterChatRepository.saveUserMessage).
    //
    // Image attachments aren't forwarded to the backend yet - the Chat
    // Module doesn't accept them server-side (RAG/multimodal ingestion is
    // a later phase) - so imageBytes only affects local display here, the
    // same gap OpenAiChatRepository/FreeRouterChatRepository already have.
    return ChatMessage(
      id: 'local-${DateTime.now().microsecondsSinceEpoch}',
      conversationId: conversationId,
      role: ChatRole.user,
      content: content,
      createdAt: DateTime.now(),
      imageBytes: imageBytes,
      imageMimeType: imageMimeType,
    );
  }

  @override
  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async {
    final backendId = await _resolveBackendConversationId(conversationId);
    final response = await _post(
      '/v1/conversations/$backendId/messages',
      body: {'content': userMessage},
    );

    if (response.statusCode == 401) {
      throw const ApiChatException('Not authenticated. Please sign in again.');
    }
    if (response.statusCode != 200) {
      throw ApiChatException(
        'Backend request failed with status ${response.statusCode}.',
        technicalDetails: response.body,
      );
    }

    final decoded = jsonDecode(response.body) as List<dynamic>;
    if (decoded.isEmpty) {
      throw const ApiChatException('Unexpected empty response from backend.');
    }
    // The backend returns [userMessage, assistantMessage] - the assistant
    // reply is always last, whether or not this endpoint later gains tool
    // calls or multi-turn continuations in between.
    final assistantJson = decoded.last as Map<String, dynamic>;
    return _messageFromJson(assistantJson, conversationId);
  }

  @override
  Stream<String> streamAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async* {
    final backendId = await _resolveBackendConversationId(conversationId);
    final request = http.Request(
      'POST',
      Uri.parse('$baseUrl/v1/conversations/$backendId/messages/stream'),
    )
      ..headers.addAll(_headers)
      ..body = jsonEncode({'content': userMessage});

    final http.StreamedResponse response;
    try {
      response = await _client.send(request).timeout(timeout);
    } on TimeoutException {
      throw const ApiChatException('The backend took too long to respond.');
    } catch (error) {
      throw ApiChatException('Could not reach the backend: $error');
    }

    if (response.statusCode == 401) {
      throw const ApiChatException('Not authenticated. Please sign in again.');
    }
    if (response.statusCode != 200) {
      final body = await response.stream.bytesToString();
      throw ApiChatException(
        'Backend request failed with status ${response.statusCode}.',
        technicalDetails: body,
      );
    }

    // The backend only ever emits single-line JSON per "data:" line (see
    // backend/app/modules/chat/service.py's _sse helper) - no multi-line
    // data, no other SSE fields (event:/id:/retry:) - so this simple
    // line-by-line parse is enough; it doesn't need to be a general SSE
    // client.
    final lines =
        response.stream.transform(utf8.decoder).transform(const LineSplitter());

    await for (final line in lines) {
      if (!line.startsWith('data:')) continue;
      final payload = line.substring(5).trim();
      if (payload.isEmpty) continue;

      final event = jsonDecode(payload) as Map<String, dynamic>;
      switch (event['type']) {
        case 'delta':
          final content = event['content'] as String?;
          if (content != null && content.isNotEmpty) yield content;
        case 'error':
          throw ApiChatException(
            event['detail'] as String? ??
                'The backend reported a streaming error.',
          );
        case 'done':
          return;
      }
    }
  }

  /// Resumes the caller's most recent existing backend conversation, or
  /// creates one if none exists. The backend already scopes
  /// `GET /v1/conversations` by the authenticated identity's tenant_id
  /// (never by this [localConversationId], which is purely a local cache
  /// key) - so this is what actually makes conversation history survive an
  /// app restart, independent of whatever string the client happens to pass
  /// in. That's the real fix behind removing the old hardcoded
  /// `'default-conversation'` literal from `chat_page.dart`: identity, not
  /// a magic shared string, is what the backend uses to find "your" chat.
  Future<String> _resolveBackendConversationId(
      String localConversationId) async {
    final cached = _backendConversationIds[localConversationId];
    if (cached != null) return cached;

    final listResponse = await _get('/v1/conversations');
    if (listResponse.statusCode == 401) {
      throw const ApiChatException('Not authenticated. Please sign in again.');
    }
    if (listResponse.statusCode != 200) {
      throw ApiChatException(
        'Failed to list conversations (status ${listResponse.statusCode}).',
        technicalDetails: listResponse.body,
      );
    }

    final existing = (jsonDecode(listResponse.body) as List<dynamic>)
        .cast<Map<String, dynamic>>();
    if (existing.isNotEmpty) {
      final mostRecent = existing.reduce((a, b) {
        final aTime =
            DateTime.tryParse(a['updated_at'] as String? ?? '') ?? DateTime(0);
        final bTime =
            DateTime.tryParse(b['updated_at'] as String? ?? '') ?? DateTime(0);
        return bTime.isAfter(aTime) ? b : a;
      });
      final backendId = mostRecent['id'] as String;
      _backendConversationIds[localConversationId] = backendId;
      return backendId;
    }

    final backendId = await _createBackendConversation();
    _backendConversationIds[localConversationId] = backendId;
    return backendId;
  }

  Future<String> _createBackendConversation() async {
    final response = await _post('/v1/conversations');

    if (response.statusCode == 401) {
      throw const ApiChatException('Not authenticated. Please sign in again.');
    }
    if (response.statusCode != 200) {
      throw ApiChatException(
        'Failed to start a conversation (status ${response.statusCode}).',
        technicalDetails: response.body,
      );
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return decoded['id'] as String;
  }

  Future<http.Response> _get(String path) async {
    try {
      return await _client
          .get(Uri.parse('$baseUrl$path'), headers: _headers)
          .timeout(timeout);
    } on TimeoutException {
      throw const ApiChatException('The backend took too long to respond.');
    } on ApiChatException {
      rethrow;
    } catch (error) {
      throw ApiChatException('Could not reach the backend: $error');
    }
  }

  Future<http.Response> _post(String path, {Map<String, dynamic>? body}) async {
    try {
      return await _client
          .post(
            Uri.parse('$baseUrl$path'),
            headers: _headers,
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(timeout);
    } on TimeoutException {
      throw const ApiChatException('The backend took too long to respond.');
    } on ApiChatException {
      rethrow;
    } catch (error) {
      throw ApiChatException('Could not reach the backend: $error');
    }
  }

  ChatMessage _messageFromJson(
      Map<String, dynamic> json, String localConversationId) {
    return ChatMessage(
      id: json['id'] as String,
      conversationId: localConversationId,
      role: (json['role'] as String?) == 'user'
          ? ChatRole.user
          : ChatRole.assistant,
      content: json['content'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.now(),
      isPending: json['is_pending'] as bool? ?? false,
    );
  }

  ChatMessage _welcomeMessage(String conversationId) {
    return ChatMessage(
      id: 'welcome',
      conversationId: conversationId,
      role: ChatRole.assistant,
      content:
          'Hi. I am PlantGPT, connected to the PlantGPT backend. Ask me about '
          'cement, steel, or manufacturing plant operations.',
      createdAt: DateTime.now(),
    );
  }
}
