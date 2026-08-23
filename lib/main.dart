import 'package:flutter/material.dart';

import 'core/app_theme.dart';
import 'features/chat/data/local_chat_repository.dart';
import 'features/chat/data/openai_chat_repository.dart';
import 'features/chat/domain/chat_repository.dart';
import 'features/chat/presentation/chat_page.dart';

void main() {
  runApp(const ChatApp());
}

class ChatApp extends StatelessWidget {
  const ChatApp({super.key});

  static const _openAiApiKey = String.fromEnvironment('OPENAI_API_KEY');
  static const _openAiModel = String.fromEnvironment(
    'OPENAI_MODEL',
    defaultValue: 'gpt-5',
  );

  @override
  Widget build(BuildContext context) {
    final ChatRepository repository = _openAiApiKey.isEmpty
        ? LocalChatRepository()
        : OpenAiChatRepository(apiKey: _openAiApiKey, model: _openAiModel);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PlantGPT',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: ChatPage(repository: repository),
    );
  }
}
