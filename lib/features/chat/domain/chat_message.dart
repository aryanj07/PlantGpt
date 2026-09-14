import 'dart:typed_data';

enum ChatRole { user, assistant }

/// A RAG source document backing an assistant reply (Phase 3). Only ever
/// populated on assistant messages, and only when the backend's RAGService
/// actually retrieved and used a document to answer.
class ChatCitation {
  const ChatCitation({
    required this.documentId,
    required this.title,
    this.sourceUri,
  });

  final String documentId;
  final String title;
  final String? sourceUri;
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.role,
    required this.content,
    required this.createdAt,
    this.isPending = false,
    this.imageBytes,
    this.imageMimeType,
    this.citations,
  });

  final String id;
  final String conversationId;
  final ChatRole role;
  final String content;
  final DateTime createdAt;
  final bool isPending;

  /// Optional attached image (e.g. a plant photo). Only populated on user
  /// messages; only sent to the model by repositories that support it.
  final Uint8List? imageBytes;
  final String? imageMimeType;

  final List<ChatCitation>? citations;

  ChatMessage copyWith({
    String? id,
    String? conversationId,
    ChatRole? role,
    String? content,
    DateTime? createdAt,
    bool? isPending,
    Uint8List? imageBytes,
    String? imageMimeType,
    List<ChatCitation>? citations,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      conversationId: conversationId ?? this.conversationId,
      role: role ?? this.role,
      content: content ?? this.content,
      createdAt: createdAt ?? this.createdAt,
      isPending: isPending ?? this.isPending,
      imageBytes: imageBytes ?? this.imageBytes,
      imageMimeType: imageMimeType ?? this.imageMimeType,
      citations: citations ?? this.citations,
    );
  }
}
