import 'chat_message.dart';

abstract class ChatRepository {
  Future<List<ChatMessage>> loadMessages(String conversationId);

  Future<void> clearMessages(String conversationId);

  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
  });

  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  });
}
