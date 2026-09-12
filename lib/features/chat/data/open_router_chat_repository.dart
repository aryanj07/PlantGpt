import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

/// Categories of failure an OpenRouter request can end in. Used to decide
/// whether a failure is worth retrying and/or worth falling back to another
/// [ChatRepository].
enum OpenRouterErrorType {
  unavailable,
  timeout,
  rateLimit,
  providerFailure,
  invalidResponse,
  badRequest,
}

class OpenRouterChatException implements Exception {
  const OpenRouterChatException(
    this.type,
    this.message, {
    this.technicalDetails,
  });

  final OpenRouterErrorType type;

  /// User-facing message. Never contains API keys or raw upstream payloads.
  final String message;

  /// Developer-only detail for logs. Never surfaced to the UI.
  final String? technicalDetails;

  bool get isTransient =>
      type == OpenRouterErrorType.unavailable ||
      type == OpenRouterErrorType.timeout ||
      type == OpenRouterErrorType.rateLimit ||
      type == OpenRouterErrorType.providerFailure;

  @override
  String toString() => message;
}

/// Calls OpenRouter.ai's hosted "Free Models Router"
/// (https://openrouter.ai/api/v1/chat/completions, model "openrouter/free"),
/// which auto-selects a random free model on OpenRouter's own platform.
///
/// This is a separate, hosted OpenRouter.ai feature — unrelated to the
/// self-hosted openfreerouter/freerouter project used by
/// [FreeRouterChatRepository]. Requires a real OpenRouter.ai API key.
class OpenRouterChatRepository implements ChatRepository {
  OpenRouterChatRepository({
    required this.apiKey,
    this.model = 'openrouter/free',
    this.timeout = const Duration(seconds: 30),
    this.maxRetries = 2,
    this.siteUrl,
    this.siteName,
    ChatRepository? fallback,
    http.Client? client,
  })  : _fallback = fallback,
        _client = client ?? http.Client();

  static const _endpoint = 'https://openrouter.ai/api/v1/chat/completions';

  final String apiKey;
  final String model;
  final Duration timeout;
  final int maxRetries;

  /// Optional attribution headers OpenRouter shows on its public leaderboard.
  /// Harmless to omit; never required for the request to work.
  final String? siteUrl;
  final String? siteName;

  final ChatRepository? _fallback;
  final http.Client _client;
  final Map<String, List<ChatMessage>> _messagesByConversation = {};
  final Random _random = Random();

  static const _systemPrompt =
      'You are PlantGPT, a helpful, conversational assistant. Answer clearly, '
      'ask concise follow-up questions when needed, and keep context from the '
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
                  'Hi. I am routed through OpenRouter.ai to a free model. Ask me anything.',
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
    } on OpenRouterChatException catch (error) {
      final fallback = _fallback;
      if (fallback != null && error.isTransient) {
        _log(
          'openrouter_fallback',
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

  Future<String> _requestWithRetry(String conversationId) async {
    var attempt = 0;
    while (true) {
      final start = DateTime.now();
      try {
        final (text, resolvedModel) = await _requestOnce(conversationId);
        _log(
          'openrouter_request',
          success: true,
          statusCode: 200,
          retryCount: attempt,
          latencyMs: DateTime.now().difference(start).inMilliseconds,
          extra: resolvedModel != null ? 'model_used=$resolvedModel' : null,
        );
        return text;
      } on OpenRouterChatException catch (error) {
        _log(
          'openrouter_request',
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

  Future<(String, String?)> _requestOnce(String conversationId) async {
    final history = (_messagesByConversation[conversationId] ?? const [])
        .where((message) => !message.isPending)
        .toList();
    final recentHistory = history.length > _historyLimit
        ? history.sublist(history.length - _historyLimit)
        : history;

    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
      if (siteUrl != null && siteUrl!.isNotEmpty) 'HTTP-Referer': siteUrl!,
      if (siteName != null && siteName!.isNotEmpty) 'X-Title': siteName!,
    };
    final body = jsonEncode({
      'model': model,
      'messages': [
        {'role': 'system', 'content': _systemPrompt},
        ...recentHistory.map(_toRequestMessage),
      ],
    });

    http.Response response;
    try {
      response = await _client
          .post(Uri.parse(_endpoint), headers: headers, body: body)
          .timeout(timeout);
    } on TimeoutException {
      throw const OpenRouterChatException(
        OpenRouterErrorType.timeout,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'OpenRouter request timed out',
      );
    } catch (error) {
      throw OpenRouterChatException(
        OpenRouterErrorType.unavailable,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'OpenRouter unavailable: $error',
      );
    }

    return _parseResponse(response);
  }

  /// OpenAI-compatible message shape. A user message with an attached image
  /// becomes multimodal `content` (text + image_url parts) instead of a
  /// plain string, which is what lets OpenRouter's free-model auto-router
  /// pick a vision-capable model for that turn.
  Map<String, dynamic> _toRequestMessage(ChatMessage message) {
    final role = message.role == ChatRole.user ? 'user' : 'assistant';
    final imageBytes = message.imageBytes;
    if (imageBytes == null) {
      return {'role': role, 'content': message.content};
    }

    final mimeType = message.imageMimeType ?? 'image/jpeg';
    final dataUri = 'data:$mimeType;base64,${base64Encode(imageBytes)}';
    return {
      'role': role,
      'content': [
        {'type': 'text', 'text': message.content},
        {
          'type': 'image_url',
          'image_url': {'url': dataUri},
        },
      ],
    };
  }

  (String, String?) _parseResponse(http.Response response) {
    final statusCode = response.statusCode;

    if (statusCode == 429) {
      throw const OpenRouterChatException(
        OpenRouterErrorType.rateLimit,
        'The AI service is busy right now. Please try again in a moment.',
      );
    }
    if (statusCode == 502 || statusCode == 503 || statusCode == 504) {
      throw OpenRouterChatException(
        OpenRouterErrorType.providerFailure,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'OpenRouter upstream failure: HTTP $statusCode',
      );
    }
    if (statusCode == 401 || statusCode == 403) {
      throw OpenRouterChatException(
        OpenRouterErrorType.badRequest,
        'AI service is not configured correctly. Please contact support.',
        technicalDetails: 'OpenRouter auth failure: HTTP $statusCode',
      );
    }
    if (statusCode >= 400 && statusCode < 500) {
      throw OpenRouterChatException(
        OpenRouterErrorType.badRequest,
        'Something went wrong processing your request.',
        technicalDetails: 'OpenRouter rejected the request: HTTP $statusCode',
      );
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw OpenRouterChatException(
        OpenRouterErrorType.providerFailure,
        'AI service is temporarily unavailable. Please try again.',
        technicalDetails: 'OpenRouter returned HTTP $statusCode',
      );
    }

    Map<String, dynamic> data;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) throw const FormatException();
      data = decoded;
    } on FormatException {
      throw const OpenRouterChatException(
        OpenRouterErrorType.invalidResponse,
        'AI service returned an unexpected response. Please try again.',
        technicalDetails: 'OpenRouter returned a non-JSON body',
      );
    }

    final text = _extractContent(data);
    if (text == null || text.trim().isEmpty) {
      throw const OpenRouterChatException(
        OpenRouterErrorType.invalidResponse,
        'AI service returned an empty response. Please try again.',
        technicalDetails:
            'OpenRouter response missing choices[0].message.content',
      );
    }

    final resolvedModel = data['model'];
    return (text.trim(), resolvedModel is String ? resolvedModel : null);
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
    // Deliberately omits prompts, responses, and API keys.
    final buffer = StringBuffer(
      '[$event] route=openrouter model=$model success=$success '
      'retry_count=$retryCount',
    );
    if (statusCode != null) buffer.write(' status=$statusCode');
    if (latencyMs != null) buffer.write(' latency_ms=$latencyMs');
    if (extra != null) buffer.write(' detail=$extra');
    debugPrint(buffer.toString());
  }
}
