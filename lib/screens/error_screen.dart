import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/app_theme.dart';
import 'widgets/common.dart';

enum ErrorKind { file, noText, noTerms, offline, engine, generic }

/// Which screen an engine error code belongs to.
ErrorKind errorKindFor(String code) {
  switch (code) {
    case 'unsupported_file':
    case 'duplicate_file':
      return ErrorKind.file; // "This file can't be used"
    case 'cannot_read':
      return ErrorKind.noText; // "Can't read this document"
    case 'no_key_terms':
      return ErrorKind.noTerms; // "No key terms found"
    case 'engine_down':
      return ErrorKind.engine;
    default:
      return ErrorKind.generic;
  }
}

/// Figma: "Error - File", "Error - No Text", "Error - No Usable Term" and
/// "No internet Connection". [detail] is the engine's own message (for example
/// "This file is too large (limit is 20 MB)."), shown under the standard text.
class ErrorScreen extends StatelessWidget {
  const ErrorScreen({
    super.key,
    required this.c,
    required this.kind,
    this.detail,
  });
  final AppController c;
  final ErrorKind kind;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final content = _contentFor(kind);
    // Don't repeat the standard text if the engine said the same thing.
    final extra =
        (detail != null &&
            detail!.isNotEmpty &&
            !content.body.contains(detail!))
        ? detail
        : null;
    final isWarning = kind == ErrorKind.offline;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Column(
        children: [
          const Spacer(flex: 3),
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isWarning ? AppColors.warnCircle : AppColors.errorCircle,
            ),
            child: Icon(
              isWarning ? Icons.wifi_off : Icons.error_outline,
              size: 30,
              color: isWarning ? AppColors.warnIcon : AppColors.errorIcon,
            ),
          ),
          const SizedBox(height: 18),
          Text(
            content.title,
            textAlign: TextAlign.center,
            style: AppText.title.copyWith(fontSize: 18),
          ),
          const SizedBox(height: 10),
          Text(
            content.body,
            textAlign: TextAlign.center,
            style: AppText.small.copyWith(fontSize: 11),
          ),
          if (extra != null) ...[
            const SizedBox(height: 8),
            Text(
              extra,
              textAlign: TextAlign.center,
              style: AppText.small.copyWith(
                fontSize: 10.5,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
          const SizedBox(height: 18),
          ..._buttons(),
          const Spacer(flex: 5),
        ],
      ),
    );
  }

  List<Widget> _buttons() {
    switch (kind) {
      case ErrorKind.file:
      case ErrorKind.noText:
      case ErrorKind.noTerms:
        return [
          PrimaryButton(
            label: 'Choose another file',
            onPressed: c.chooseAnotherFile,
          ),
        ];
      case ErrorKind.offline:
        return [
          PrimaryButton(label: 'Try again', onPressed: c.retryOnline),
          const SizedBox(height: 10),
          SecondaryButton(
            label: 'Continue without definitions',
            onPressed: c.continueWithoutOnline,
          ),
        ];
      case ErrorKind.engine:
      case ErrorKind.generic:
        return [
          PrimaryButton(label: 'Try again', onPressed: c.tryAgainAfterError),
        ];
    }
  }

  static ({String title, String body}) _contentFor(ErrorKind kind) {
    switch (kind) {
      case ErrorKind.file:
        return (
          title: "This file can't be used",
          body:
              "Only PDF files are supported for now. Password-protected or very large files "
              "can't be opened.",
        );
      case ErrorKind.noText:
        return (
          title: "Can't read this document",
          body: "No readable text was found. Scanned pages and images aren't supported yet.",
        );
      case ErrorKind.noTerms:
        return (
          title: 'No key terms found',
          body: "This document doesn't have enough text to find key terms. Try a longer document.",
        );
      case ErrorKind.offline:
        return (
          title: 'No internet connection',
          body:
              'Definitions and translations need the internet. You can try again, or continue '
              'without them.',
        );
      case ErrorKind.engine:
        return (
          title: "Can't reach the app's engine",
          body: "The part of IlocoAdal that reads documents isn't running. Start it, then try again.",
        );
      case ErrorKind.generic:
        return (title: 'Something went wrong', body: 'Please try again.');
    }
  }
}
