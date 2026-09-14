import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../data/documents_api_client.dart';

/// Upload/status UI for the RAG Module's documents (plan Section H.2,
/// sub-task 6's "fast follow" upload screen). Deliberately a bottom sheet,
/// not a dedicated route - this is a utility action off the chat screen, not
/// a destination someone navigates to and lives in.
Future<void> showDocumentsSheet(
  BuildContext context, {
  required DocumentsApiClient client,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => _DocumentsSheet(client: client),
  );
}

class _DocumentsSheet extends StatefulWidget {
  const _DocumentsSheet({required this.client});

  final DocumentsApiClient client;

  @override
  State<_DocumentsSheet> createState() => _DocumentsSheetState();
}

class _DocumentsSheetState extends State<_DocumentsSheet> {
  List<DocumentStatus>? _documents;
  String? _error;
  bool _isUploading = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final documents = await widget.client.list();
      if (!mounted) return;
      setState(() {
        _documents = documents;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '$error');
    }
  }

  Future<void> _pickAndUpload() async {
    // withData: true so this works identically on web (no filesystem path
    // to read from) and mobile - always get bytes back directly.
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'txt', 'md'],
      withData: true,
    );
    final file = result?.files.single;
    final bytes = file?.bytes;
    if (file == null || bytes == null) return;

    setState(() => _isUploading = true);
    try {
      // Ingestion runs async server-side (BackgroundTasks, no queue in V1) -
      // this call only confirms the upload landed as status=pending; _refresh
      // is a manual snapshot, not a poll, so "processing"/"ready" only shows
      // once the user taps refresh again.
      await widget.client.upload(filename: file.name, bytes: bytes);
      await _refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Upload failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Documents', style: theme.textTheme.titleLarge),
                const Spacer(),
                IconButton(
                  tooltip: 'Refresh',
                  icon: const Icon(Icons.refresh),
                  onPressed: _refresh,
                ),
              ],
            ),
            Text(
              'Upload plant SOPs, manuals, or spec sheets (PDF, TXT, MD). '
              'PlantGPT cites them when it uses one to answer a question.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colors.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _isUploading ? null : _pickAndUpload,
              icon: _isUploading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.upload_file),
              label: Text(_isUploading ? 'Uploading…' : 'Upload document'),
            ),
            const SizedBox(height: 16),
            if (_error != null)
              Text(_error!, style: TextStyle(color: colors.error))
            else if (_documents == null)
              const Center(child: CircularProgressIndicator())
            else if (_documents!.isEmpty)
              Text(
                'No documents uploaded yet.',
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: colors.onSurfaceVariant),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: _documents!.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final doc = _documents![index];
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: _StatusIcon(status: doc.status, colors: colors),
                      title: Text(
                        doc.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        doc.status == 'failed' && doc.errorDetail != null
                            ? doc.errorDetail!
                            : doc.status,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusIcon extends StatelessWidget {
  const _StatusIcon({required this.status, required this.colors});

  final String status;
  final ColorScheme colors;

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case 'ready':
        return Icon(Icons.check_circle, color: Colors.green.shade600);
      case 'failed':
        return Icon(Icons.error, color: colors.error);
      case 'processing':
        return const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      default: // pending
        return Icon(Icons.schedule, color: colors.onSurfaceVariant);
    }
  }
}
