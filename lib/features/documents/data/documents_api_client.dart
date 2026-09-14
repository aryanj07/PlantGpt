import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

class DocumentsApiException implements Exception {
  const DocumentsApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class DocumentStatus {
  const DocumentStatus({
    required this.id,
    required this.title,
    required this.status,
    required this.createdAt,
    this.errorDetail,
    this.ingestedAt,
  });

  final String id;
  final String title;

  /// pending | processing | ready | failed (backend/app/modules/rag/models.py)
  final String status;
  final String? errorDetail;
  final DateTime createdAt;
  final DateTime? ingestedAt;

  factory DocumentStatus.fromJson(Map<String, dynamic> json) {
    return DocumentStatus(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Untitled',
      status: json['status'] as String? ?? 'pending',
      errorDetail: json['error_detail'] as String?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.now(),
      ingestedAt: (json['ingested_at'] as String?) == null
          ? null
          : DateTime.tryParse(json['ingested_at'] as String),
    );
  }
}

/// Talks to the RAG Module's document endpoints (plan Section H.2, sub-tasks
/// 4 & 6): POST/GET /v1/documents. Mirrors ApiChatRepository's auth header
/// pattern (session token if present, else dev headers) rather than sharing
/// code with it - the two clients are small and unrelated enough that an
/// early shared base class would be more ceremony than it saves.
class DocumentsApiClient {
  DocumentsApiClient({
    required String baseUrl,
    this.sessionToken,
    this.devTenantId,
    this.devUserId,
    this.timeout = const Duration(seconds: 60),
    http.Client? client,
  })  : baseUrl = baseUrl.endsWith('/')
            ? baseUrl.substring(0, baseUrl.length - 1)
            : baseUrl,
        _client = client ?? http.Client();

  final String baseUrl;
  final String? sessionToken;
  final String? devTenantId;
  final String? devUserId;
  final Duration timeout;
  final http.Client _client;

  Map<String, String> get _headers {
    final headers = <String, String>{};
    final token = sessionToken;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
      return headers;
    }
    final tenant = devTenantId;
    final user = devUserId;
    if (tenant != null && tenant.isNotEmpty) {
      headers['X-Dev-Tenant-Id'] = tenant;
    }
    if (user != null && user.isNotEmpty) headers['X-Dev-User-Id'] = user;
    return headers;
  }

  Future<DocumentStatus> upload({
    required String filename,
    required Uint8List bytes,
  }) async {
    final request =
        http.MultipartRequest('POST', Uri.parse('$baseUrl/v1/documents'))
          ..headers.addAll(_headers)
          ..files.add(http.MultipartFile.fromBytes(
            'file',
            bytes,
            filename: filename,
          ));

    final http.StreamedResponse streamed;
    try {
      streamed = await _client.send(request).timeout(timeout);
    } catch (error) {
      throw DocumentsApiException('Could not reach the backend: $error');
    }
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode == 401) {
      throw const DocumentsApiException(
          'Not authenticated. Please sign in again.');
    }
    if (response.statusCode != 200) {
      throw DocumentsApiException(
          'Upload failed (status ${response.statusCode}): ${response.body}');
    }
    return DocumentStatus.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<DocumentStatus>> list() async {
    final http.Response response;
    try {
      response = await _client
          .get(Uri.parse('$baseUrl/v1/documents'), headers: _headers)
          .timeout(timeout);
    } catch (error) {
      throw DocumentsApiException('Could not reach the backend: $error');
    }

    if (response.statusCode == 401) {
      throw const DocumentsApiException(
          'Not authenticated. Please sign in again.');
    }
    if (response.statusCode != 200) {
      throw DocumentsApiException(
          'Failed to list documents (status ${response.statusCode}).');
    }
    final decoded = jsonDecode(response.body) as List<dynamic>;
    return decoded
        .map((raw) => DocumentStatus.fromJson(raw as Map<String, dynamic>))
        .toList();
  }
}
