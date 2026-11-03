import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/app_theme.dart';
import 'widgets/common.dart';
import 'widgets/file_card.dart';

/// Figma: "Ready to Process" (one file, or several - the card just grows).
class ReadyScreen extends StatelessWidget {
  const ReadyScreen(this.c, {super.key});
  final AppController c;

  @override
  Widget build(BuildContext context) {
    return ScreenFrame(
      title: 'Ready to Process',
      subtitle: pickSubtitle,
      body: SingleChildScrollView(
        child: Column(
          children: [
            WhiteCard(
              padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
              child: Column(
                children: [
                  for (var i = 0; i < c.files.length; i++) ...[
                    // The X: removes the file from the list.
                    FileRow(
                      file: c.files[i],
                      onRemove: c.busy ? null : () => c.removeFile(c.files[i]),
                    ),
                    if (i < c.files.length - 1)
                      const Divider(
                        height: 14,
                        thickness: 1,
                        color: AppColors.hairline,
                      ),
                  ],
                ],
              ),
            ),
            const GreenDivider(),
            WhiteCard(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Expanded(child: Text('Number of key terms')),
                      Text(
                        '${c.topN}',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  Slider(
                    value: c.topN.toDouble(),
                    min: AppController.minTopN.toDouble(),
                    max: AppController.maxTopN.toDouble(),
                    label: '${c.topN}',
                    onChanged: c.busy ? null : (v) => c.setTopN(v.round()),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const NoticeBox([offlineNotice]),
          ],
        ),
      ),
      bottom: Column(
        children: [
          SecondaryButton(
            label: 'Upload another document',
            onPressed: c.busy
                ? null
                : c.addDocument, // opens the file browser again
          ),
          const SizedBox(height: 8),
          PrimaryButton(
            label: 'Start Processing',
            loading: c.busy,
            onPressed: c.files.isEmpty ? null : c.startProcessing,
          ),
        ],
      ),
    );
  }
}
