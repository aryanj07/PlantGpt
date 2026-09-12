import 'dart:typed_data';

import 'chat_message.dart';

abstract class ChatRepository {
  Future<List<ChatMessage>> loadMessages(String conversationId);

  Future<void> clearMessages(String conversationId);

  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  });

  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  });
}
