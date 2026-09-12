import 'dart:typed_data';

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

/// Replace the method bodies with calls to your own database/API.
///
/// Keep mapping code in this file so widgets never depend on table names,
/// HTTP routes, Firestore collections, or Supabase schemas.
class DatabaseChatRepository extends ChatRepository {
  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) {
    throw UnimplementedError('Connect this to your message query.');
  }

  @override
  Future<void> clearMessages(String conversationId) {
    throw UnimplementedError('Connect this to your delete/archive operation.');
  }

  @override
  Future<ChatMessage> saveUserMessage({
    required String conversationId,
    required String content,
    Uint8List? imageBytes,
    String? imageMimeType,
  }) {
    throw UnimplementedError('Connect this to your insert operation.');
  }

  @override
  Future<ChatMessage> createAssistantReply({
    required String conversationId,
    required String userMessage,
  }) {
    throw UnimplementedError('Connect this to your model/backend endpoint.');
  }
}
