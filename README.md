# PlantGPT Flutter Starter

A ChatGPT-style Flutter app with the database linkage isolated behind a repository contract.

## What is included

- Chat screen with assistant/user bubbles
- Message composer with loading state
- OpenAI Responses API repository that can behave like ChatGPT when an API key is supplied
- Plant background image asset for the chat screen
- Material 3 light/dark theme
- `ChatRepository` interface for storage and assistant responses
- `LocalChatRepository` mock implementation for development
- `DatabaseChatRepository` placeholder for your real database/API linkage

## Database linkage

The UI only talks to `ChatRepository`:

```dart
abstract class ChatRepository {
  Future<List<ChatMessage>> loadMessages(String conversationId);
  Future<void> clearMessages(String conversationId);
  Future<ChatMessage> saveUserMessage({required String conversationId, required String content});
  Future<ChatMessage> createAssistantReply({required String conversationId, required String userMessage});
}
```

To connect a real database, add another implementation in `lib/features/chat/data/`, for example:

- `ApiChatRepository` for your own backend
- `FirebaseChatRepository` for Firestore
- `SupabaseChatRepository` for Supabase
- `SqliteChatRepository` for local/offline storage

Then replace this line in `lib/main.dart`:

```dart
home: ChatPage(repository: LocalChatRepository()),
```

with your real repository.

## OpenAI setup

The app reads the API key at build/run time with Dart defines. Do not commit a
real key into source code.

```powershell
flutter run --dart-define=OPENAI_API_KEY=your_api_key_here
```

By default the app uses `gpt-5`, matching OpenAI's current quickstart examples.
You can override it:

```powershell
flutter run --dart-define=OPENAI_API_KEY=your_api_key_here --dart-define=OPENAI_MODEL=gpt-5-mini
```

For production apps, route requests through your own backend so the API key is
not exposed in the mobile or web client.

## Run

```powershell
flutter pub get
flutter run
```
