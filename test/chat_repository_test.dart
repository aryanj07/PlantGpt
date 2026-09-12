import 'package:flutter_test/flutter_test.dart';
import 'package:chatgpt_alt_db/features/chat/data/local_chat_repository.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_message.dart';

void main() {
  test('stores user and assistant messages behind repository contract',
      () async {
    final repository = LocalChatRepository();

    final userMessage = await repository.saveUserMessage(
      conversationId: 'conversation-1',
      content: 'Hello',
    );
    final assistantMessage = await repository.createAssistantReply(
      conversationId: 'conversation-1',
      userMessage: 'Hello',
    );

    final messages = await repository.loadMessages('conversation-1');

    expect(userMessage.role, ChatRole.user);
    expect(assistantMessage.role, ChatRole.assistant);
    expect(messages, containsAll([userMessage, assistantMessage]));
  });

  test('clears a conversation through the repository boundary', () async {
    final repository = LocalChatRepository();

    await repository.saveUserMessage(
      conversationId: 'conversation-1',
      content: 'Delete me',
    );
    await repository.clearMessages('conversation-1');

    final messages = await repository.loadMessages('conversation-1');

    expect(messages.length, 1);
    expect(messages.single.role, ChatRole.assistant);
  });
}
