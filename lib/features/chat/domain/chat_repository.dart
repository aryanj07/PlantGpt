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

  /// Streams the assistant reply incrementally as it's generated (plan
  /// ADR 5). Default implementation just awaits [createAssistantReply] and
  /// emits its content as a single event - real token-by-token streaming
  /// only exists where the backend supports it (`ApiChatRepository`); every
  /// other implementation is indistinguishable from one that "streamed" its
  /// entire reply in one chunk, so none of them need to override this.
  Stream<String> streamAssistantReply({
    required String conversationId,
    required String userMessage,
  }) async* {
    final reply = await createAssistantReply(
      conversationId: conversationId,
      userMessage: userMessage,
    );
    lastCitations = reply.citations;
    yield reply.content;
  }

  /// Citations (Phase 3 RAG) backing whichever [streamAssistantReply] call
  /// most recently completed, or null if that reply used none - the plain
  /// `Stream<String>` return type above has no room to carry structured
  /// data per-event, and citations only ever arrive once (attached to the
  /// whole reply), so a side-channel read after the stream finishes is
  /// simpler than changing the stream's element type for every
  /// implementation. `ApiChatRepository` overrides `streamAssistantReply`
  /// and sets this itself instead of going through this default.
  List<ChatCitation>? lastCitations;
}
