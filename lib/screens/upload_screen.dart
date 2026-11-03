import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/app_theme.dart';
import 'widgets/common.dart';

/// Figma: "Upload document".
class UploadScreen extends StatelessWidget {
  const UploadScreen(this.c, {super.key});
  final AppController c;

  @override
  Widget build(BuildContext context) {
    return ScreenFrame(
      title: 'Upload Documents',
      subtitle: pickSubtitle,
      body: SingleChildScrollView(
        child: Column(
          children: [
            CustomPaint(
              foregroundPainter: DashedRRectPainter(),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.fromLTRB(22, 26, 22, 14),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  children: [
                    const Icon(
                      Icons.file_upload_outlined,
                      size: 30,
                      color: AppColors.ink,
                    ),
                    const SizedBox(height: 14),
                    // Opens the phone's / computer's file browser (PDF files only).
                    PrimaryButton(
                      label: 'Upload Documents',
                      loading: c.busy,
                      onPressed: c.addDocument,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      c.supportedText,
                      style: AppText.mono.copyWith(
                        fontSize: 9.5,
                        color: AppColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const GreenDivider(),
            const NoticeBox([offlineNotice]),
          ],
        ),
      ),
    );
  }
}
