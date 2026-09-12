import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

class OpenAiChatRepository implements ChatRepository {
  OpenAiChatRepository({
    required this.apiKey,
    this.model = 'gpt-5',
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String apiKey;
  final String model;
  final http.Client _client;
  final Map<String, List<ChatMessage>> _messagesByConversation = {};

  static const _systemPrompt =
      'You are PlantGPT, a helpful, conversational assistant. Answer clearly, '
      'ask concise follow-up questions when needed, and keep context from the '
      'current chat.';

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
                  'Hi. I am connected to OpenAI when you run the app with an API key. Ask me anything.',
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
    final reply = await _createResponse(conversationId);
    final message = ChatMessage(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      conversationId: conversationId,
      role: ChatRole.assistant,
      content: reply,
      createdAt: DateTime.now(),
    );
    _store(message);
    return message;
  }

  Future<String> _createResponse(String conversationId) async {
    final history = (_messagesByConversation[conversationId] ?? const [])
        .where((message) => !message.isPending)
        .toList();
    final recentHistory =
        history.length > 16 ? history.sublist(history.length - 16) : history;

    final response = await _client
        .post(
          Uri.parse('https://api.openai.com/v1/responses'),
          headers: {
            'Authorization': 'Bearer $apiKey',
            'Content-Type': 'application/json',
          },
          body: jsonEncode({
            'model': model,
            'input': [
              {'role': 'developer', 'content': _systemPrompt},
              ...recentHistory.map(
                (message) => {
                  'role': message.role == ChatRole.user ? 'user' : 'assistant',
                  'content': message.content,
                },
              ),
            ],
            'max_output_tokens': 1200,
          }),
        )
        .timeout(const Duration(seconds: 45));

    final data = _decodeResponse(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = data['error'];
      final message =
          error is Map<String, dynamic> ? error['message']?.toString() : null;
      throw OpenAiChatException(
        message ?? 'OpenAI request failed with status ${response.statusCode}.',
      );
    }

    final text = _extractOutputText(data);
    if (text == null || text.trim().isEmpty) {
      throw const OpenAiChatException('OpenAI returned an empty response.');
    }

    return text.trim();
  }

  Map<String, dynamic> _decodeResponse(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) return decoded;
    } on FormatException {
      throw const OpenAiChatException('OpenAI returned an invalid response.');
    }

    throw const OpenAiChatException('OpenAI returned an unexpected response.');
  }

  String? _extractOutputText(Map<String, dynamic> data) {
    final outputText = data['output_text'];
    if (outputText is String && outputText.isNotEmpty) return outputText;

    final output = data['output'];
    if (output is! List) return null;

    final parts = <String>[];
    for (final item in output) {
      if (item is! Map<String, dynamic>) continue;
      final content = item['content'];
      if (content is! List) continue;
      for (final block in content) {
        if (block is! Map<String, dynamic>) continue;
        final text = block['text'];
        if (text is String && text.isNotEmpty) {
          parts.add(text);
        }
      }
    }

    return parts.isEmpty ? null : parts.join('\n');
  }

  void _store(ChatMessage message) {
    final messages = _messagesByConversation.putIfAbsent(
      message.conversationId,
      () => <ChatMessage>[],
    );
    messages.add(message);
  }
}

class OpenAiChatException implements Exception {
  const OpenAiChatException(this.message);

  final String message;

  @override
  String toString() => message;
}
