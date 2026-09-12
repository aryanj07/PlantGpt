import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({required this.repository, super.key});

  final ChatRepository repository;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  static const _conversationId = 'default-conversation';

  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _imagePicker = ImagePicker();
  final List<ChatMessage> _messages = [];
  bool _isSending = false;
  Uint8List? _pendingImageBytes;
  String? _pendingImageMimeType;

  @override
  void initState() {
    super.initState();
    _loadMessages();
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadMessages() async {
    final messages = await widget.repository.loadMessages(_conversationId);
    if (!mounted) return;
    setState(() => _messages.addAll(messages));
  }

  Future<void> _pickImage() async {
    final picked = await _imagePicker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1600,
      imageQuality: 85,
    );
    if (picked == null) return;

    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _pendingImageBytes = bytes;
      _pendingImageMimeType = picked.mimeType ?? _guessMimeType(picked.name);
    });
  }

  String _guessMimeType(String fileName) {
    final lower = fileName.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    if (lower.endsWith('.gif')) return 'image/gif';
    return 'image/jpeg';
  }

  void _clearPendingImage() {
    setState(() {
      _pendingImageBytes = null;
      _pendingImageMimeType = null;
    });
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    final imageBytes = _pendingImageBytes;
    final imageMimeType = _pendingImageMimeType;
    if ((text.isEmpty && imageBytes == null) || _isSending) return;

    _controller.clear();
    setState(() {
      _isSending = true;
      _pendingImageBytes = null;
      _pendingImageMimeType = null;
    });

    final userMessage = await widget.repository.saveUserMessage(
      conversationId: _conversationId,
      content: text,
      imageBytes: imageBytes,
      imageMimeType: imageMimeType,
    );

    if (!mounted) return;
    setState(() {
      _messages.add(userMessage);
      _messages.add(
        ChatMessage(
          id: 'pending-${DateTime.now().microsecondsSinceEpoch}',
          conversationId: _conversationId,
          role: ChatRole.assistant,
          content: 'Thinking...',
          createdAt: DateTime.now(),
          isPending: true,
        ),
      );
    });
    _scrollToBottom();

    ChatMessage assistantMessage;
    try {
      assistantMessage = await widget.repository.createAssistantReply(
        conversationId: _conversationId,
        userMessage: text,
      );
    } catch (error) {
      assistantMessage = ChatMessage(
        id: 'error-${DateTime.now().microsecondsSinceEpoch}',
        conversationId: _conversationId,
        role: ChatRole.assistant,
        content: 'Sorry, I could not get a response: $error',
        createdAt: DateTime.now(),
      );
    }

    if (!mounted) return;
    setState(() {
      _messages
        ..removeWhere((message) => message.isPending)
        ..add(assistantMessage);
      _isSending = false;
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('PlantGPT'),
        backgroundColor: colors.surface.withOpacity(0.82),
        actions: [
          IconButton(
            tooltip: 'New chat',
            icon: const Icon(Icons.add_comment_outlined),
            onPressed: () async {
              await widget.repository.clearMessages(_conversationId);
              if (!mounted) return;
              setState(() {
                _messages
                  ..clear()
                  ..add(
                    ChatMessage(
                      id: 'welcome-${DateTime.now().microsecondsSinceEpoch}',
                      conversationId: _conversationId,
                      role: ChatRole.assistant,
                      content: 'New chat started.',
                      createdAt: DateTime.now(),
                    ),
                  );
              });
            },
          ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [colors.surfaceContainerHighest, colors.surface],
              ),
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                Expanded(
                  child: ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      return _MessageBubble(message: _messages[index]);
                    },
                  ),
                ),
                _Composer(
                  controller: _controller,
                  isSending: _isSending,
                  onSend: _sendMessage,
                  onAttach: _pickImage,
                  pendingImageBytes: _pendingImageBytes,
                  onClearAttachment: _clearPendingImage,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUser = message.role == ChatRole.user;
    final colors = theme.colorScheme;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 6),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: isUser
                ? colors.primary.withOpacity(0.94)
                : colors.surface.withOpacity(0.9),
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(18),
              topRight: const Radius.circular(18),
              bottomLeft: Radius.circular(isUser ? 18 : 4),
              bottomRight: Radius.circular(isUser ? 4 : 18),
            ),
            border: isUser
                ? null
                : Border.all(color: colors.outlineVariant.withOpacity(0.7)),
            boxShadow: [
              BoxShadow(
                color: colors.shadow.withOpacity(0.08),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (message.imageBytes != null)
                Padding(
                  padding: EdgeInsets.only(
                    bottom: message.content.isEmpty ? 0 : 8,
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.memory(
                      message.imageBytes!,
                      fit: BoxFit.cover,
                      height: 180,
                    ),
                  ),
                ),
              if (message.content.isNotEmpty)
                Text(
                  message.content,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: isUser ? colors.onPrimary : colors.onSurface,
                    height: 1.35,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.isSending,
    required this.onSend,
    required this.onAttach,
    required this.pendingImageBytes,
    required this.onClearAttachment,
  });

  final TextEditingController controller;
  final bool isSending;
  final VoidCallback onSend;
  final VoidCallback onAttach;
  final Uint8List? pendingImageBytes;
  final VoidCallback onClearAttachment;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface.withOpacity(0.9),
        border: Border(top: BorderSide(color: colors.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (pendingImageBytes != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.memory(
                        pendingImageBytes!,
                        width: 64,
                        height: 64,
                        fit: BoxFit.cover,
                      ),
                    ),
                    Positioned(
                      top: -6,
                      right: -6,
                      child: GestureDetector(
                        onTap: onClearAttachment,
                        child: CircleAvatar(
                          radius: 10,
                          backgroundColor: colors.error,
                          child: Icon(
                            Icons.close,
                            size: 14,
                            color: colors.onError,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                IconButton(
                  tooltip: 'Attach photo',
                  onPressed: isSending ? null : onAttach,
                  icon: const Icon(Icons.add_photo_alternate_outlined),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: TextField(
                    controller: controller,
                    minLines: 1,
                    maxLines: 5,
                    textInputAction: TextInputAction.newline,
                    decoration: const InputDecoration(
                      hintText: 'Ask about plant operations…',
                      contentPadding: EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                SizedBox.square(
                  dimension: 48,
                  child: FilledButton(
                    onPressed: isSending ? null : onSend,
                    style: FilledButton.styleFrom(
                      padding: EdgeInsets.zero,
                      shape: const CircleBorder(),
                    ),
                    child: isSending
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.arrow_upward),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
