enum ChatRole { user, assistant }

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.role,
    required this.content,
    required this.createdAt,
    this.isPending = false,
  });

  final String id;
  final String conversationId;
  final ChatRole role;
  final String content;
  final DateTime createdAt;
  final bool isPending;

  ChatMessage copyWith({
    String? id,
    String? conversationId,
    ChatRole? role,
    String? content,
    DateTime? createdAt,
    bool? isPending,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      conversationId: conversationId ?? this.conversationId,
      role: role ?? this.role,
      content: content ?? this.content,
      createdAt: createdAt ?? this.createdAt,
      isPending: isPending ?? this.isPending,
    );
  }
}
