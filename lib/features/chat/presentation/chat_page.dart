import 'package:flutter/material.dart';

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
  final List<ChatMessage> _messages = [];
  bool _isSending = false;

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

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isSending) return;

    _controller.clear();
    setState(() => _isSending = true);

    final userMessage = await widget.repository.saveUserMessage(
      conversationId: _conversationId,
      content: text,
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
          Image.asset(
            'assets/images/plant_background.png',
            fit: BoxFit.cover,
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              color: colors.surface.withOpacity(
                Theme.of(context).brightness == Brightness.dark ? 0.72 : 0.58,
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
          child: Text(
            message.content,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: isUser ? colors.onPrimary : colors.onSurface,
              height: 1.35,
            ),
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
  });

  final TextEditingController controller;
  final bool isSending;
  final VoidCallback onSend;

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
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 5,
                textInputAction: TextInputAction.newline,
                decoration: const InputDecoration(
                  hintText: 'Enter the context here',
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
      ),
    );
  }
}
