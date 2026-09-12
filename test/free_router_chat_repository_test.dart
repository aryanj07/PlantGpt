import 'dart:convert';
import 'dart:typed_data';

import 'package:chatgpt_alt_db/features/chat/data/free_router_chat_repository.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_message.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_repository.dart';
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

class _FakeFallback implements ChatRepository {
  final List<ChatMessage> stored = [];

  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) async =>
      List.unmodifiable(stored);

  @override
  Future<void> clearMessages(String conversationId) async => stored.clear();

  @override
  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  }) async {
    final message = ChatMessage(
      id: 'fallback-user',
      conversationId: conversationId,
      role: ChatRole.user,
      content: content,
      createdAt: DateTime.now(),
      imageBytes: imageBytes,
      imageMimeType: imageMimeType,
    );
    stored.add(message);
    return message;
  }

  @override
  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async {
    final message = ChatMessage(
      id: 'fallback-assistant',
      conversationId: conversationId,
      role: ChatRole.assistant,
      content: 'fallback response',
      createdAt: DateTime.now(),
    );
    stored.add(message);
    return message;
  }
}

void main() {
  group('successful requests', () {
    test('sends system + history + user messages and parses reply', () async {
      late Map<String, dynamic> body;

      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async {
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return _okResponse('Hello from FreeRouter');
        }),
      );

      await repository.saveUserMessage(
        conversationId: 'c1',
        content: 'Hello',
      );
      final reply = await repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'Hello',
      );

      expect(reply.role, ChatRole.assistant);
      expect(reply.content, 'Hello from FreeRouter');
      expect(body['model'], 'auto');
      expect(body['messages'][0]['role'], 'system');
      expect(
        body['messages'],
        contains(equals({'role': 'user', 'content': 'Hello'})),
      );
    });

    test('handles unicode content', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async => _okResponse('こんにちは 🌱')),
      );

      final reply = await repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'こんにちは',
      );

      expect(reply.content, 'こんにちは 🌱');
    });

    test('handles a long prompt without failing', () async {
      final longPrompt = 'a' * 20000;
      late Map<String, dynamic> body;

      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async {
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return _okResponse('ok');
        }),
      );

      await repository.saveUserMessage(conversationId: 'c1', content: longPrompt);
      await repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: longPrompt,
      );

      final messages = (body['messages'] as List).cast<Map<String, dynamic>>();
      expect(messages.any((m) => m['content'] == longPrompt), isTrue);
    });

    test('truncates history to the last 16 non-pending messages', () async {
      late Map<String, dynamic> body;
      var callCount = 0;

      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async {
          callCount++;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return _okResponse('reply $callCount');
        }),
      );

      for (var i = 0; i < 10; i++) {
        await repository.saveUserMessage(conversationId: 'c1', content: 'msg $i');
        await repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'msg $i',
        );
      }

      // 10 user + 10 assistant = 20 stored messages, but only 16 sent + 1 system.
      final messages = (body['messages'] as List).cast<Map<String, dynamic>>();
      expect(messages.length, 17);
    });
  });

  group('error responses', () {
    test('empty choices throws invalidResponse', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
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
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.invalidResponse,
          ),
        ),
      );
    });

    test('malformed JSON throws invalidResponse', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async => http.Response('not json', 200)),
      );

      await expectLater(
        () => repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        ),
        throwsA(
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.invalidResponse,
          ),
        ),
      );
    });

    test('400 throws badRequest and does not retry', () async {
      var callCount = 0;
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        maxRetries: 2,
        client: MockClient((request) async {
          callCount++;
          return http.Response('{}', 400);
        }),
      );

      await expectLater(
        () => repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        ),
        throwsA(
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.badRequest,
          ),
        ),
      );
      expect(callCount, 1);
    });

    test('401/403 throws badRequest without leaking details to message', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async => http.Response('{}', 401)),
      );

      try {
        await repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        );
        fail('expected exception');
      } on FreeRouterChatException catch (e) {
        expect(e.type, FreeRouterErrorType.badRequest);
        expect(e.message.toLowerCase(), isNot(contains('401')));
      }
    });

    test('429 is retried then throws rateLimit when exhausted', () async {
      var callCount = 0;
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
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
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.rateLimit,
          ),
        ),
      );
      expect(callCount, 3); // 1 initial + 2 retries
    });

    test('500 throws providerFailure', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        maxRetries: 0,
        client: MockClient((request) async => http.Response('{}', 500)),
      );

      await expectLater(
        () => repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        ),
        throwsA(
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.providerFailure,
          ),
        ),
      );
    });

    for (final status in [502, 503, 504]) {
      test('$status is retried as providerFailure', () async {
        var callCount = 0;
        final repository = FreeRouterChatRepository(
          baseUrl: 'http://localhost:18800',
          maxRetries: 2,
          client: MockClient((request) async {
            callCount++;
            return http.Response('{}', status);
          }),
        );

        await expectLater(
          () => repository.createAssistantReply(
            conversationId: 'c1',
            userMessage: 'hi',
          ),
          throwsA(isA<FreeRouterChatException>()),
        );
        expect(callCount, 3);
      });
    }

    test('timeout throws timeout error', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
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
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.timeout,
          ),
        ),
      );
    });

    test('connection failure throws unavailable', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
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
          isA<FreeRouterChatException>().having(
            (e) => e.type,
            'type',
            FreeRouterErrorType.unavailable,
          ),
        ),
      );
    });

    test('retry succeeds after a transient failure', () async {
      var callCount = 0;
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
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

    test('retries are exhausted after maxRetries', () async {
      var callCount = 0;
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        maxRetries: 2,
        client: MockClient((request) async {
          callCount++;
          return http.Response('{}', 503);
        }),
      );

      await expectLater(
        () => repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        ),
        throwsA(isA<FreeRouterChatException>()),
      );
      expect(callCount, 3);
    });
  });

  group('fallback', () {
    test('delegates to fallback repository after transient failure', () async {
      final fallback = _FakeFallback();
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        maxRetries: 0,
        fallback: fallback,
        client: MockClient((request) async => http.Response('{}', 503)),
      );

      final reply = await repository.createAssistantReply(
        conversationId: 'c1',
        userMessage: 'hi',
      );

      expect(reply.content, 'fallback response');
      expect(fallback.stored, isNotEmpty);
    });

    test('does not fall back on a non-transient (badRequest) failure', () async {
      final fallback = _FakeFallback();
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        maxRetries: 0,
        fallback: fallback,
        client: MockClient((request) async => http.Response('{}', 400)),
      );

      await expectLater(
        () => repository.createAssistantReply(
          conversationId: 'c1',
          userMessage: 'hi',
        ),
        throwsA(isA<FreeRouterChatException>()),
      );
      expect(fallback.stored, isEmpty);
    });
  });

  group('health check', () {
    test('returns true on a healthy 200', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async => http.Response('ok', 200)),
      );

      expect(await repository.healthCheck(), isTrue);
    });

    test('returns false when unreachable', () async {
      final repository = FreeRouterChatRepository(
        baseUrl: 'http://localhost:18800',
        client: MockClient((request) async {
          throw http.ClientException('Connection refused');
        }),
      );

      expect(await repository.healthCheck(), isFalse);
    });
  });
}
