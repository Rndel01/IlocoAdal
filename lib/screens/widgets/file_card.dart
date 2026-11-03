import 'package:flutter/material.dart';

import '../../api/ilocoadal_client.dart';
import '../../theme/app_theme.dart';

/// One row of the "Ready to Process" list: PDF icon, name, format, size and pages, and the X.
class FileRow extends StatelessWidget {
  const FileRow({super.key, required this.file, required this.onRemove});
  final FileInfo file;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final details =
        '${file.sizeMb.toStringAsFixed(2)} MB'
        '${file.pages == null ? '' : ' - ${file.pages} pages'}';
    return Row(
      children: [
        const _PdfIcon(),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                file.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppText.mono.copyWith(
                  fontSize: 10.5,
                  color: AppColors.ink,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                '${file.format} file format',
                style: AppText.mono.copyWith(
                  fontSize: 9.5,
                  color: AppColors.muted,
                ),
              ),
              Text(
                details,
                style: AppText.mono.copyWith(
                  fontSize: 9.5,
                  color: AppColors.muted,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Remove ${file.name}',
          visualDensity: VisualDensity.compact,
          onPressed: onRemove,
          icon: const Icon(Icons.close, size: 18, color: AppColors.ink),
        ),
      ],
    );
  }
}

class _PdfIcon extends StatelessWidget {
  const _PdfIcon();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 30,
      height: 36,
      child: Stack(
        children: [
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFFF1F1EE),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
          Positioned(
            left: 0,
            bottom: 5,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1.5),
              decoration: BoxDecoration(
                color: AppColors.pdfRed,
                borderRadius: BorderRadius.circular(2),
              ),
              child: const Text(
                'PDF',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 7.5,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
