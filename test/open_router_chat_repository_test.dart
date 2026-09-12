import 'dart:convert';
import 'dart:typed_data';

import 'package:chatgpt_alt_db/features/chat/data/open_router_chat_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _okResponse(String content) {
  return http.Response(
    jsonEncode({
      'choices': [
        {
          'message': {'role': 'assistant', 'content': content},
        },
      ],
    }),
    200,
    headers: {'content-type': 'application/json'},
  );
}

void main() {
  test('sends bearer auth, default free model, and history', () async {
    late Map<String, dynamic> body;
    late Map<String, String> headers;

    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient((request) async {
        headers = request.headers;
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return _okResponse('Hello from OpenRouter');
      }),
    );

    await repository.saveUserMessage(conversationId: 'c1', content: 'Hello');
    final reply = await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'Hello',
    );

    expect(reply.content, 'Hello from OpenRouter');
    expect(headers['Authorization'], 'Bearer test-key');
    expect(body['model'], 'openrouter/free');
    expect(
      body['messages'],
      contains(equals({'role': 'user', 'content': 'Hello'})),
    );
  });

  test('sends optional attribution headers when configured', () async {
    late Map<String, String> headers;

    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      siteUrl: 'https://example.com',
      siteName: 'PlantGPT',
      client: MockClient((request) async {
        headers = request.headers;
        return _okResponse('ok');
      }),
    );

    await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'hi',
    );

    expect(headers['HTTP-Referer'], 'https://example.com');
    expect(headers['X-Title'], 'PlantGPT');
  });

  test('handles unicode content', () async {
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient((request) async => _okResponse('こんにちは 🌱')),
    );

    final reply = await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'こんにちは',
    );

    expect(reply.content, 'こんにちは 🌱');
  });

  test('empty choices throws invalidResponse', () async {
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient(
        (request) async => http.Response(jsonEncode({'choices': []}), 200),
      ),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(
        isA<OpenRouterChatException>().having(
          (e) => e.type,
          'type',
          OpenRouterErrorType.invalidResponse,
        ),
      ),
    );
  });

  test('401 throws badRequest and does not retry', () async {
    var callCount = 0;
    final repository = OpenRouterChatRepository(
      apiKey: 'bad-key',
      maxRetries: 2,
      client: MockClient((request) async {
        callCount++;
        return http.Response('{}', 401);
      }),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(
        isA<OpenRouterChatException>().having(
          (e) => e.type,
          'type',
          OpenRouterErrorType.badRequest,
        ),
      ),
    );
    expect(callCount, 1);
  });

  test('429 is retried then throws rateLimit when exhausted', () async {
    var callCount = 0;
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      maxRetries: 2,
      client: MockClient((request) async {
        callCount++;
        return http.Response('{}', 429);
      }),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(
        isA<OpenRouterChatException>().having(
          (e) => e.type,
          'type',
          OpenRouterErrorType.rateLimit,
        ),
      ),
    );
    expect(callCount, 3);
  });

  test('500 throws providerFailure', () async {
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      maxRetries: 0,
      client: MockClient((request) async => http.Response('{}', 500)),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(isA<OpenRouterChatException>()),
    );
  });

  test('timeout throws timeout error', () async {
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      timeout: const Duration(milliseconds: 10),
      maxRetries: 0,
      client: MockClient((request) async {
        await Future<void>.delayed(const Duration(milliseconds: 50));
        return _okResponse('too late');
      }),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(
        isA<OpenRouterChatException>().having(
          (e) => e.type,
          'type',
          OpenRouterErrorType.timeout,
        ),
      ),
    );
  });

  test('connection failure throws unavailable', () async {
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      maxRetries: 0,
      client: MockClient((request) async {
        throw http.ClientException('Connection refused');
      }),
    );

    await expectLater(
      () => repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      ),
      throwsA(
        isA<OpenRouterChatException>().having(
          (e) => e.type,
          'type',
          OpenRouterErrorType.unavailable,
        ),
      ),
    );
  });

  test('retry succeeds after a transient failure', () async {
    var callCount = 0;
    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      maxRetries: 2,
      client: MockClient((request) async {
        callCount++;
        if (callCount == 1) return http.Response('{}', 503);
        return _okResponse('recovered');
      }),
    );

    final reply = await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'hi',
    );

    expect(reply.content, 'recovered');
    expect(callCount, 2);
  });

  test('sends multimodal content when an image is attached', () async {
    late Map<String, dynamic> body;
    final imageBytes = Uint8List.fromList([1, 2, 3, 4]);

    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return _okResponse('nice plant');
      }),
    );

    await repository.saveUserMessage(
      conversationId: 'c1',
      content: 'what is wrong with this leaf?',
      imageBytes: imageBytes,
      imageMimeType: 'image/png',
    );
    await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'what is wrong with this leaf?',
    );

    final messages = (body['messages'] as List).cast<Map<String, dynamic>>();
    final userMessage = messages.last;
    expect(userMessage['role'], 'user');
    final contentParts =
        (userMessage['content'] as List).cast<Map<String, dynamic>>();
    expect(contentParts[0], {
      'type': 'text',
      'text': 'what is wrong with this leaf?',
    });
    expect(contentParts[1]['type'], 'image_url');
    expect(
      contentParts[1]['image_url']['url'],
      'data:image/png;base64,${base64Encode(imageBytes)}',
    );
  });

  test('sends plain string content when no image is attached', () async {
    late Map<String, dynamic> body;

    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return _okResponse('ok');
      }),
    );

    await repository.saveUserMessage(conversationId: 'c1', content: 'hi');
    await repository.createAssistantReply(
      conversationId: 'c1',
      userMessage: 'hi',
    );

    final messages = (body['messages'] as List).cast<Map<String, dynamic>>();
    expect(messages.last['content'], 'hi');
  });

  test('truncates history to the last 16 non-pending messages', () async {
    late Map<String, dynamic> body;

    final repository = OpenRouterChatRepository(
      apiKey: 'test-key',
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return _okResponse('ok');
      }),
    );

    for (var i = 0; i < 10; i++) {
      await repository.saveUserMessage(conversationId: 'c1', content: 'msg $i');
      await repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'msg $i',
      );
    }

    final messages = (body['messages'] as List).cast<Map<String, dynamic>>();
    expect(messages.length, 17); // system + last 16 of 20 stored messages
  });
}
