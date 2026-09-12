import 'dart:convert';

import 'package:chatgpt_alt_db/features/chat/data/api_chat_repository.dart';
import 'package:chatgpt_alt_db/features/chat/domain/chat_message.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _conversationResponse(String id) {
  return http.Response(
    jsonEncode({
      'id': id,
      'tenant_id': 'default',
      'user_id': 'dev-user',
      'title': null,
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
    }),
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

void main() {
  test(
      'loadMessages provisions a backend conversation then returns a welcome message when empty',
      () async {
    final requests = <http.Request>[];
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          return _conversationResponse('backend-conv-1');
        }
        return _messagesResponse([]);
      }),
    );

    final messages = await repository.loadMessages('default-conversation');

    expect(requests, hasLength(2));
    expect(requests[0].method, 'POST');
    expect(requests[0].url.path, '/v1/conversations');
    expect(requests[1].method, 'GET');
    expect(requests[1].url.path, '/v1/conversations/backend-conv-1/messages');
    expect(messages, hasLength(1));
    expect(messages.single.role, ChatRole.assistant);
  });

  test(
      'loadMessages reuses the cached backend conversation id on a second call',
      () async {
    var conversationCreateCount = 0;
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          conversationCreateCount++;
          return _conversationResponse('backend-conv-1');
        }
        return _messagesResponse([
          _messageJson(id: 'm1', role: 'user', content: 'hi'),
          _messageJson(id: 'm2', role: 'assistant', content: 'hello'),
        ]);
      }),
    );

    await repository.loadMessages('default-conversation');
    final second = await repository.loadMessages('default-conversation');

    expect(conversationCreateCount, 1);
    expect(second, hasLength(2));
    expect(second[0].role, ChatRole.user);
    expect(second[1].role, ChatRole.assistant);
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
      conversationId: 'default-conversation',
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
      conversationId: 'default-conversation',
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
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          return _conversationResponse('backend-conv-1');
        }
        return _messagesResponse([]);
      }),
    );

    await repository.loadMessages('default-conversation');

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
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          return _conversationResponse('backend-conv-1');
        }
        return _messagesResponse([]);
      }),
    );

    await repository.loadMessages('default-conversation');

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
      () => repository.loadMessages('default-conversation'),
      throwsA(isA<ApiChatException>()),
    );
  });

  test(
      'clearMessages forgets the mapping so the next load provisions a new conversation',
      () async {
    var conversationCreateCount = 0;
    var nextBackendId = 'backend-conv-1';
    final repository = ApiChatRepository(
      baseUrl: 'https://api.plantgpt.test',
      devTenantId: 'default',
      devUserId: 'dev-user',
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path == '/v1/conversations') {
          conversationCreateCount++;
          return _conversationResponse(nextBackendId);
        }
        return _messagesResponse([]);
      }),
    );

    await repository.loadMessages('default-conversation');
    await repository.clearMessages('default-conversation');
    nextBackendId = 'backend-conv-2';
    await repository.loadMessages('default-conversation');

    expect(conversationCreateCount, 2);
  });
}
