import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

class LocalChatRepository implements ChatRepository {
  final Map<String, List<ChatMessage>> _messagesByConversation = {};

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
                  'Hi. Ask me anything, and this app will keep the database layer separate from the chat UI.',
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
  }) async {
    final message = ChatMessage(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      conversationId: conversationId,
      role: ChatRole.user,
      content: content,
      createdAt: DateTime.now(),
    );
    _store(message);
    return message;
  }

  @override
  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    final message = ChatMessage(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      conversationId: conversationId,
      role: ChatRole.assistant,
      content:
          'Mock response for: "$userMessage"\n\nReplace LocalChatRepository with your database/API adapter when ready.',
      createdAt: DateTime.now(),
    );
    _store(message);
    return message;
  }

  void _store(ChatMessage message) {
    final messages = _messagesByConversation.putIfAbsent(
      message.conversationId,
      () => <ChatMessage>[],
    );
    messages.add(message);
  }
}
