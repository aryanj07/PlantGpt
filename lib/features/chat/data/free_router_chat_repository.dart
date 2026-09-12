import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

/// Categories of failure a FreeRouter request can end in. Used to decide
/// whether a failure is worth retrying and/or worth falling back to another
/// [ChatRepository].
enum FreeRouterErrorType {
  unavailable,
  timeout,
  rateLimit,
  providerFailure,
  invalidResponse,
  badRequest,
}

class FreeRouterChatException implements Exception {
  const FreeRouterChatException(
    this.type,
    this.message, {
    this.technicalDetails,
  });

  final FreeRouterErrorType type;

  /// User-facing message. Never contains API keys or raw upstream payloads.
  final String message;

  /// Developer-only detail for logs. Never surfaced to the UI.
  final String? technicalDetails;

  bool get isTransient =>
      type == FreeRouterErrorType.unavailable ||
      type == FreeRouterErrorType.timeout ||
      type == FreeRouterErrorType.rateLimit ||
      type == FreeRouterErrorType.providerFailure;

  @override
  String toString() => message;
}

/// Talks to a self-hosted FreeRouter instance
/// (https://github.com/openfreerouter/freerouter) through its
/// OpenAI-compatible `/v1/chat/completions` endpoint.
///
/// FreeRouter is a router/proxy, not a guaranteed-free provider: whether a
/// response is actually free depends entirely on how FreeRouter's own
/// tiers/providers are configured. This class only knows how to talk to
/// FreeRouter; it never decides which upstream model is "free".
class FreeRouterChatRepository extends ChatRepository {
  FreeRouterChatRepository({
    required this.baseUrl,
    this.model = 'auto',
    this.timeout = const Duration(seconds: 30),
    this.maxRetries = 2,
    this.apiKey,
    ChatRepository? fallback,
    http.Client? client,
  })  : _fallback = fallback,
        _client = client ?? http.Client();

  /// e.g. http://localhost:18800 (no trailing slash).
  final String baseUrl;

  /// FreeRouter routing mode/model, e.g. "auto", or an explicit tier prefix.
  final String model;

  final Duration timeout;
  final int maxRetries;

  /// Optional bearer token for FreeRouter's own endpoint auth (not a
  /// provider API key — those live in FreeRouter's own config).
  final String? apiKey;

  final ChatRepository? _fallback;
  final http.Client _client;
  final Map<String, List<ChatMessage>> _messagesByConversation = {};
  final Random _random = Random();

  static const _systemPrompt =
      'You are PlantGPT, a domain expert assistant for industrial plant '
      'operations — cement plants, steel plants, and manufacturing plants. '
      'Help with process parameters, equipment troubleshooting, production-line '
      'optimization, maintenance, and safety questions. Answer clearly, ask '
      'concise follow-up questions when needed, and keep context from the '
      'current chat.';

  static const _historyLimit = 16;

  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) async {
    return List.unmodifiable(
      _messagesByConversation[conversationId] ??
          [
            ChatMessage(
              id: 'welcome',
              conversationId: conversationId,
              role: ChatRole.assistant,
              content:
                  'Hi. I am PlantGPT, routed through FreeRouter to a free model. Ask me '
                  'about cement, steel, or manufacturing plant operations.',
              createdAt: DateTime.now(),
            ),
          ],
    );
  }

  @override
  Future<void> clearMessages(String conversationId) async {
    _messagesByConversation.remove(conversationId);
  }

  @override
  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  }) async {
    final message = ChatMessage(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      conversationId: conversationId,
      role: ChatRole.user,
      content: content,
      createdAt: DateTime.now(),
      imageBytes: imageBytes,
      imageMimeType: imageMimeType,
    );
    _store(message);
    return message;
  }

  @override
  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async {
    String replyText;
    try {
      replyText = await _requestWithRetry(conversationId);
    } on FreeRouterChatException catch (error) {
      final fallback = _fallback;
      if (fallback != null && error.isTransient) {
        _log(
          'freerouter_fallback',
          success: false,
          retryCount: maxRetries,
          extra: error.type.name,
        );
        await fallback.saveUserMessage(
          conversationId: conversationId,
          content: userMessage,
        );
        final fallbackReply = await fallback.createAssistantReply(
          conversationId: conversationId,
          userMessage: userMessage,
        );
        _store(fallbackReply);
        return fallbackReply;
      }
      rethrow;
    }

    final message = ChatMessage(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      conversationId: conversationId,
      role: ChatRole.assistant,
      content: replyText,
      createdAt: DateTime.now(),
    );
    _store(message);
    return message;
  }

  /// Connectivity check against FreeRouter's `/health` endpoint. Not wired
  /// into the request path automatically (see README) — callers may use it
  /// for a startup or on-demand check.
  Future<bool> healthCheck() async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode >= 200 && response.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  Future<String> _requestWithRetry(String conversationId) async {
    var attempt = 0;
    while (true) {
      final start = DateTime.now();
      try {
        final text = await _requestOnce(conversationId);
        _log(
          'freerouter_request',
          success: true,
          statusCode: 200,
          retryCount: attempt,
          latencyMs: DateTime.now().difference(start).inMilliseconds,
        );
        return text;
      } on FreeRouterChatException catch (error) {
        _log(
          'freerouter_request',
          success: false,
          retryCount: attempt,
          latencyMs: DateTime.now().difference(start).inMilliseconds,
          extra: error.type.name,
        );
        final canRetry = attempt < maxRetries && error.isTransient;
        if (!canRetry) rethrow;
        attempt++;
        await Future<void>.delayed(_backoff(attempt));
      }
    }
  }

  Duration _backoff(int attempt) {
    final baseMs = 300 * pow(2, attempt - 1).toInt();
    final jitterMs = _random.nextInt(200);
    return Duration(milliseconds: baseMs + jitterMs);
  }

  Future<String> _requestOnce(String conversationId) async {
    final history = (_messagesByConversation[conversationId] ?? const [])
        .where((message) => !message.isPending)
        .toList();
    final recentHistory = history.length > _historyLimit
        ? history.sublist(history.length - _historyLimit)
        : history;

    final uri = Uri.parse('$baseUrl/v1/chat/completions');
    final headers = {
      'Content-Type': 'application/json',
      if (apiKey != null && apiKey!.isNotEmpty)
        'Authorization': 'Bearer $apiKey',
    };
    final body = jsonEncode({
      'model': model,
      'messages': [
        {'role': 'system', 'content': _systemPrompt},
        ...recentHistory.map(
          (message) => {
            'role': message.role == ChatRole.user ? 'user' : 'assistant',
            'content': message.content,
          },
        ),
      ],
    });

    http.Response response;
    try {
      response = await _client
          .post(uri, headers: headers, body: body)
          .timeout(timeout);
    } on TimeoutException {
      throw const FreeRouterChatException(
        FreeRouterErrorType.timeout,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'FreeRouter request timed out',
      );
    } catch (error) {
      throw FreeRouterChatException(
        FreeRouterErrorType.unavailable,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'FreeRouter unavailable: $error',
      );
    }

    return _parseResponse(response);
  }

  String _parseResponse(http.Response response) {
    final statusCode = response.statusCode;

    if (statusCode == 429) {
      throw const FreeRouterChatException(
        FreeRouterErrorType.rateLimit,
        'The AI service is busy right now. Please try again in a moment.',
      );
    }
    if (statusCode == 502 || statusCode == 503 || statusCode == 504) {
      throw FreeRouterChatException(
        FreeRouterErrorType.providerFailure,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'FreeRouter upstream failure: HTTP $statusCode',
      );
    }
    if (statusCode == 401 || statusCode == 403) {
      throw FreeRouterChatException(
        FreeRouterErrorType.badRequest,
        'AI service is not configured correctly. Please contact support.',
        technicalDetails: 'FreeRouter auth failure: HTTP $statusCode',
      );
    }
    if (statusCode >= 400 && statusCode < 500) {
      throw FreeRouterChatException(
        FreeRouterErrorType.badRequest,
        'Something went wrong processing your request.',
        technicalDetails: 'FreeRouter rejected the request: HTTP $statusCode',
      );
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw FreeRouterChatException(
        FreeRouterErrorType.providerFailure,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'FreeRouter returned HTTP $statusCode',
      );
    }

    Map<String, dynamic> data;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) throw const FormatException();
      data = decoded;
    } on FormatException {
      throw const FreeRouterChatException(
        FreeRouterErrorType.invalidResponse,
        'AI service returned an unexpected response. Please try again.',
        technicalDetails: 'FreeRouter returned a non-JSON body',
      );
    }

    final text = _extractContent(data);
    if (text == null || text.trim().isEmpty) {
      throw const FreeRouterChatException(
        FreeRouterErrorType.invalidResponse,
        'AI service returned an empty response. Please try again.',
        technicalDetails:
            'FreeRouter response missing choices[0].message.content',
      );
    }

    return text.trim();
  }

  String? _extractContent(Map<String, dynamic> data) {
    final choices = data['choices'];
    if (choices is! List || choices.isEmpty) return null;
    final first = choices.first;
    if (first is! Map<String, dynamic>) return null;
    final message = first['message'];
    if (message is! Map<String, dynamic>) return null;
    final content = message['content'];
    return content is String ? content : null;
  }

  void _store(ChatMessage message) {
    final messages = _messagesByConversation.putIfAbsent(
      message.conversationId,
      () => <ChatMessage>[],
    );
    messages.add(message);
  }

  void _log(
    String event, {
    required bool success,
    int? statusCode,
    required int retryCount,
    int? latencyMs,
    String? extra,
  }) {
    // Deliberately omits prompts, responses, and API keys — see spec section 25.
    final buffer = StringBuffer(
      '[$event] route=freerouter model=$model success=$success '
      'retry_count=$retryCount',
    );
    if (statusCode != null) buffer.write(' status=$statusCode');
    if (latencyMs != null) buffer.write(' latency_ms=$latencyMs');
    if (extra != null) buffer.write(' detail=$extra');
    debugPrint(buffer.toString());
  }
}
