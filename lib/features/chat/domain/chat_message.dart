import 'dart:typed_data';

enum ChatRole { user, assistant }

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

  ChatMessage copyWith({
    String? id,
    String? conversationId,
    ChatRole? role,
    String? content,
    DateTime? createdAt,
    bool? isPending,
    Uint8List? imageBytes,
    String? imageMimeType,
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
    );
  }
}
