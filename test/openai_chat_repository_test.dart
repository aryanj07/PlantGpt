import 'dart:convert';

import 'package:chatgpt_alt_db/features/chat/data/openai_chat_repository.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_message.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('sends conversation history to the OpenAI Responses API', () async {
    late Map<String, dynamic> requestBody;
    late Map<String, String> requestHeaders;

    final repository = OpenAiChatRepository(
      apiKey: '', // enter api key here
      model: 'gpt-5',
      client: MockClient((request) async {
        requestHeaders = request.headers;
        requestBody = jsonDecode(request.body) as Map<String, dynamic>;

        return http.Response(
          jsonEncode({
            'output': [
              {
                'content': [
                  {'text': 'Hello from OpenAI'},
                ],
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    await repository.saveUserMessage(
      conversationId: 'conversation-1',
      content: 'Hello',
    );
    final reply = await repository.createAssistantReply(
      conversationId: 'conversation-1',
      userMessage: 'Hello',
    );

    expect(reply.role, ChatRole.assistant);
    expect(reply.content, 'Hello from OpenAI');
    expect(requestHeaders['Authorization'], 'Bearer test-api-key');
    expect(requestBody['model'], 'gpt-5');
    expect(requestBody['input'], isA<List<dynamic>>());
    expect(
      requestBody['input'],
      contains(
        {'role': 'user', 'content': 'Hello'},
      ),
    );
  });
}
