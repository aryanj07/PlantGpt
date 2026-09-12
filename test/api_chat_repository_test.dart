import 'dart:convert';

import 'package:chatgpt_alt_db/features/chat/data/api_chat_repository.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_message.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _conversationResponse(String id,
    {String updatedAt = '2026-01-01T00:00:00Z'}) {
  return http.Response(
    jsonEncode({
      'id': id,
      'tenant_id': 'default',
      'user_id': 'dev-user',
      'title': null,
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': updatedAt,
    }),
    200,
    headers: {'content-type': 'application/json'},
  );
}

http.Response _conversationListResponse(
    List<Map<String, dynamic>> conversations) {
  return http.Response(
    jsonEncode(conversations),
    200,
    headers: {'content-type': 'application/json'},
  );
}

http.Response _messagesResponse(List<Map<String, dynamic>> messages) {
  return http.Response(
    jsonEncode(messages),
    200,
    headers: {'content-type': 'application/json'},
  );
}

Map<String, dynamic> _conversationJson(String id,
    {String updatedAt = '2026-01-01T00:00:00Z'}) {
  return {
    'id': id,
    'tenant_id': 'default',
    'user_id': 'dev-user',
    'title': null,
    'created_at': '2026-01-01T00:00:00Z',
    'updated_at': updatedAt,
  };
}

Map<String, dynamic> _messageJson({
  required String id,
  required String role,
  required String content,
}) {
  return {
    'id': id,
    'conversation_id': 'backend-conv-1',
    'role': role,
    'content': content,
    'created_at': '2026-01-01T00:00:01Z',
    'is_pending': false,
  };
}

http.StreamedResponse _sseStream(
  List<Map<String, dynamic>> events, {
  int statusCode = 200,
}) {
  final body = events.map((e) => 'data: ${jsonEncode(e)}\n\n').join();
  return http.StreamedResponse(
    Stream.value(utf8.encode(body)),
    statusCode,
    headers: {'content-type': 'text/event-stream'},
  );
}

void main() {
  test(
      'loadMessages creates a backend conversation when none exist yet, then returns a welcome message',
      () async {
    final requests = <http.Request>[];
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          return _conversationListResponse([]);
        }
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          return _conversationResponse('backend-conv-1');
        }
        return _messagesResponse([]);
      }),
    );

    final messages = await repository.loadMessages('local-session-1');

    expect(requests, hasLength(3));
    expect(requests[0].method, 'GET');
    expect(requests[0].url.path, '/v1/conversations');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/v1/conversations');
    expect(requests[2].method, 'GET');
    expect(requests[2].url.path, '/v1/conversations/backend-conv-1/messages');
    expect(messages, hasLength(1));
    expect(messages.single.role, ChatRole.assistant);
  });

  test(
      'loadMessages resumes the most recently updated existing conversation instead of creating a new one',
      () async {
    var conversationCreateCount = 0;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          return _conversationListResponse([
            _conversationJson('older-conv', updatedAt: '2026-01-01T00:00:00Z'),
            _conversationJson('newest-conv', updatedAt: '2026-01-03T00:00:00Z'),
            _conversationJson('middle-conv', updatedAt: '2026-01-02T00:00:00Z'),
          ]);
        }
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          conversationCreateCount++;
          return _conversationResponse('should-not-be-created');
        }
        return _messagesResponse([
          _messageJson(id: 'm1', role: 'user', content: 'hi'),
          _messageJson(id: 'm2', role: 'assistant', content: 'hello'),
        ]);
      }),
    );

    final messages = await repository.loadMessages('local-session-1');

    expect(conversationCreateCount, 0);
    expect(messages, hasLength(2));
  });

  test(
      'loadMessages reuses the cached backend conversation id on a second call',
      () async {
    var listCallCount = 0;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          listCallCount++;
          return _conversationListResponse(
              [_conversationJson('backend-conv-1')]);
        }
        return _messagesResponse([
          _messageJson(id: 'm1', role: 'user', content: 'hi'),
          _messageJson(id: 'm2', role: 'assistant', content: 'hello'),
        ]);
      }),
    );

    await repository.loadMessages('local-session-1');
    final second = await repository.loadMessages('local-session-1');

    expect(listCallCount, 1);
    expect(second, hasLength(2));
  });

  test('saveUserMessage returns an optimistic message without any network call',
      () async {
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        fail('saveUserMessage must not make a network request');
      }),
    );

    final message = await repository.saveUserMessage(
      conversationId: 'local-session-1',
      content: 'What is the kiln burning-zone temperature?',
    );

    expect(message.role, ChatRole.user);
    expect(message.content, 'What is the kiln burning-zone temperature?');
  });

  test('createAssistantReply posts content and returns the assistant message',
      () async {
    late Map<String, dynamic> postedBody;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          return _conversationListResponse([]);
        }
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          return _conversationResponse('backend-conv-1');
        }
        postedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return _messagesResponse([
          _messageJson(id: 'm1', role: 'user', content: 'What temp?'),
          _messageJson(id: 'm2', role: 'assistant', content: 'About 1450C.'),
        ]);
      }),
    );

    final reply = await repository.createAssistantReply(
      conversationId: 'local-session-1',
      userMessage: 'What temp?',
    );

    expect(postedBody['content'], 'What temp?');
    expect(reply.role, ChatRole.assistant);
    expect(reply.content, 'About 1450C.');
  });

  test('sends dev headers when no session token is configured', () async {
    late Map<String, String> headers;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'tenant-x',
      devUserId: 'user-x',
      client: MockClient((request) async {
        headers = request.headers;
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          return _conversationListResponse(
              [_conversationJson('backend-conv-1')]);
        }
        return _messagesResponse([]);
      }),
    );

    await repository.loadMessages('local-session-1');

    expect(headers['x-dev-tenant-id'], 'tenant-x');
    expect(headers['x-dev-user-id'], 'user-x');
    expect(headers.containsKey('authorization'), isFalse);
  });

  test('sends a bearer session token instead of dev headers when configured',
      () async {
    late Map<String, String> headers;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      sessionToken: 'real-session-token',
      devTenantId: 'tenant-x',
      devUserId: 'user-x',
      client: MockClient((request) async {
        headers = request.headers;
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          return _conversationListResponse(
              [_conversationJson('backend-conv-1')]);
        }
        return _messagesResponse([]);
      }),
    );

    await repository.loadMessages('local-session-1');

    expect(headers['authorization'], 'Bearer real-session-token');
    expect(headers.containsKey('x-dev-tenant-id'), isFalse);
  });

  test('a 401 response throws ApiChatException', () async {
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        return http.Response('{"detail":"unauthorized"}', 401);
      }),
    );

    expect(
      () => repository.loadMessages('local-session-1'),
      throwsA(isA<ApiChatException>()),
    );
  });

  test(
      'clearMessages always creates a genuinely new conversation, even when one already exists',
      () async {
    var createCount = 0;
    var listCount = 0;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/v1/conversations') {
          listCount++;
          return _conversationListResponse([_conversationJson('old-conv')]);
        }
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          createCount++;
          return _conversationResponse('new-conv-$createCount');
        }
        return _messagesResponse([]);
      }),
    );

    // Resumes the existing conversation - no create call yet.
    await repository.loadMessages('local-session-1');
    expect(createCount, 0);
    expect(listCount, 1);

    // "New chat" must not just resume 'old-conv' again.
    await repository.clearMessages('local-session-1');
    expect(createCount, 1);

    // The next load uses the freshly created conversation from cache,
    // without re-listing.
    await repository.loadMessages('local-session-1');
    expect(listCount, 1);
  });

  test('streamAssistantReply yields incremental deltas and stops at done',
      () async {
    final client = MockClient.streaming((request, bodyStream) async {
      if (request.method == 'GET' && request.url.path == '/v1/conversations') {
        return http.StreamedResponse(
          Stream.value(
              utf8.encode(jsonEncode([_conversationJson('backend-conv-1')]))),
          200,
        );
      }
      return _sseStream([
        {
          'type': 'user_message',
          'message': _messageJson(id: 'm1', role: 'user', content: 'hi')
        },
        {'type': 'delta', 'content': 'Kiln '},
        {'type': 'delta', 'content': 'temp '},
        {'type': 'delta', 'content': 'is 1450C.'},
        {
          'type': 'done',
          'message': _messageJson(
              id: 'm2', role: 'assistant', content: 'Kiln temp is 1450C.'),
        },
      ]);
    });

    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: client,
    );

    final deltas = await repository
        .streamAssistantReply(
            conversationId: 'local-session-1', userMessage: 'hi')
        .toList();

    expect(deltas, ['Kiln ', 'temp ', 'is 1450C.']);
  });

  test('streamAssistantReply throws on a mid-stream error event', () async {
    final client = MockClient.streaming((request, bodyStream) async {
      if (request.method == 'GET' && request.url.path == '/v1/conversations') {
        return http.StreamedResponse(
          Stream.value(
              utf8.encode(jsonEncode([_conversationJson('backend-conv-1')]))),
          200,
        );
      }
      return _sseStream([
        {'type': 'delta', 'content': 'partial'},
        {'type': 'error', 'detail': 'provider unavailable'},
      ]);
    });

    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: client,
    );

    final stream = repository.streamAssistantReply(
      conversationId: 'local-session-1',
      userMessage: 'hi',
    );

    final received = <String>[];
    await expectLater(
      stream.listen(received.add).asFuture(),
      throwsA(isA<ApiChatException>()),
    );
    expect(received, ['partial']);
  });

  test('streamAssistantReply throws ApiChatException on a non-200 status',
      () async {
    final client = MockClient.streaming((request, bodyStream) async {
      if (request.method == 'GET' && request.url.path == '/v1/conversations') {
        return http.StreamedResponse(
          Stream.value(
              utf8.encode(jsonEncode([_conversationJson('backend-conv-1')]))),
          200,
        );
      }
      return http.StreamedResponse(
          Stream.value(utf8.encode('server error')), 500);
    });

    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: client,
    );

    expect(
      () => repository
          .streamAssistantReply(
              conversationId: 'local-session-1', userMessage: 'hi')
          .toList(),
      throwsA(isA<ApiChatException>()),
    );
  });
}
