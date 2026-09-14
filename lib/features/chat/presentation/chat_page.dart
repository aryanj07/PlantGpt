import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../documents/data/documents_api_client.dart';
import '../../documents/presentation/documents_sheet.dart';
import '../domain/chat_message.dart';
import '../domain/chat_repository.dart';

/// A per-session local key, not a real conversation identity. It's only
/// ever used as an in-memory cache key by the repositories (see
/// ApiChatRepository's doc comment) - the backend resolves "your"
/// conversation from the authenticated identity, never from this string, so
/// it doesn't need to be stable across app restarts or shared between users.
String _generateLocalConversationId() {
  final random = Random();
  final suffix = List.generate(
    12,
    (_) => random.nextInt(16).toRadixString(16),
  ).join();
  return 'session-${DateTime.now().microsecondsSinceEpoch}-$suffix';
}

class ChatPage extends StatefulWidget {
  const ChatPage({required this.repository, this.documentsClient, super.key});

  final ChatRepository repository;

  /// Only non-null when wired to the real backend (see main.dart) - document
  /// upload has nothing to talk to under LocalChatRepository, so the AppBar
  /// action simply doesn't appear in that case.
  final DocumentsApiClient? documentsClient;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _conversationId = _generateLocalConversationId();

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

    final pendingId = 'pending-${DateTime.now().microsecondsSinceEpoch}';
    if (!mounted) return;
    setState(() {
      _messages.add(userMessage);
      _messages.add(
        ChatMessage(
          id: pendingId,
          conversationId: _conversationId,
          role: ChatRole.assistant,
          content: '',
          createdAt: DateTime.now(),
          isPending: true,
        ),
      );
    });
    _scrollToBottom();

    // streamAssistantReply (plan ADR 5) renders tokens as they arrive for
    // repositories that support it (ApiChatRepository); for every other
    // implementation the default in ChatRepository just emits the full
    // reply as one event, so this same loop covers both cases.
    final buffer = StringBuffer();
    try {
      await for (final delta in widget.repository.streamAssistantReply(
        conversationId: _conversationId,
        userMessage: text,
      )) {
        buffer.write(delta);
        _updatePendingMessage(pendingId, buffer.toString());
      }
    } catch (error) {
      final partial = buffer.toString();
      _updatePendingMessage(
        pendingId,
        partial.isEmpty
            ? 'Sorry, I could not get a response: $error'
            : '$partial\n\n[Response interrupted: $error]',
      );
    }

    if (!mounted) return;
    setState(() {
      final index = _messages.indexWhere((message) => message.id == pendingId);
      if (index != -1) {
        _messages[index] = _messages[index].copyWith(
          isPending: false,
          citations: widget.repository.lastCitations,
        );
      }
      _isSending = false;
    });
    _scrollToBottom();
  }

  void _updatePendingMessage(String pendingId, String content) {
    if (!mounted) return;
    setState(() {
      final index = _messages.indexWhere((message) => message.id == pendingId);
      if (index != -1) {
        _messages[index] = _messages[index].copyWith(content: content);
      }
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
          if (widget.documentsClient != null)
            IconButton(
              tooltip: 'Documents',
              icon: const Icon(Icons.folder_open_outlined),
              onPressed: () => showDocumentsSheet(
                context,
                client: widget.documentsClient!,
              ),
            ),
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
              if (message.isPending && message.content.isEmpty)
                Text(
                  'Thinking…',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: isUser ? colors.onPrimary : colors.onSurface,
                    fontStyle: FontStyle.italic,
                  ),
                )
              else if (message.content.isNotEmpty)
                Text(
                  message.content,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: isUser ? colors.onPrimary : colors.onSurface,
                    height: 1.35,
                  ),
                ),
              if (message.citations != null && message.citations!.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      for (final citation in message.citations!)
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.description_outlined,
                              size: 14,
                              color: colors.onSurfaceVariant,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'Source: ${citation.title}',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: colors.onSurfaceVariant,
                                fontStyle: FontStyle.italic,
                              ),
                            ),
                          ],
                        ),
                    ],
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
