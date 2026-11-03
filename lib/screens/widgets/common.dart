import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/app_theme.dart';

/// The screen frame: green header on top, cream page below.
///
/// On a phone it fills the whole screen, and the green header extends up
/// behind the status bar. On a desktop window it is a phone-width column
/// centered on a dark canvas, like the Figma boards.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.child});
  final Widget child;

  static bool get _isPhone =>
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS;

  @override
  Widget build(BuildContext context) {
    final insets = MediaQuery.of(context).padding; // status bar and gesture bar
    final page = ColoredBox(
      color: AppColors.cream,
      child: Column(
        children: [
          AppHeader(topInset: insets.top),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: insets.bottom),
              child: child,
            ),
          ),
        ],
      ),
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness:
            Brightness.light, // white icons on the green header
        statusBarBrightness: Brightness.dark, // same, for iOS
        systemNavigationBarColor: AppColors.cream,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: _isPhone ? AppColors.cream : AppColors.canvas,
        body: _isPhone
            ? page
            : Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 430),
                  child: page,
                ),
              ),
      ),
    );
  }
}

class AppHeader extends StatelessWidget {
  const AppHeader({super.key, this.topInset = 0});

  /// Height of the status bar, so the green reaches the top of the screen.
  final double topInset;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 64 + topInset,
      color: AppColors.green,
      padding: EdgeInsets.only(top: topInset, left: 20, right: 8),
      child: Row(
        children: [
          const Text(
            'IlocoAdal',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          IconButton(
            tooltip: 'Help',
            icon: const Icon(Icons.help_outline, color: Colors.white, size: 24),
            onPressed: () => _showHelp(context),
          ),
        ],
      ),
    );
  }

  void _showHelp(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('How it works'),
        content: const Text(
          '1. Upload one or more PDF files.\n'
          '2. IlocoAdal finds the key terms and a sentence for each.\n'
          '3. With an internet connection it adds definitions and translations.\n'
          '4. Download the finished document.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }
}

/// Page padding + the title block used on the first four screens.
class ScreenFrame extends StatelessWidget {
  const ScreenFrame({
    super.key,
    required this.title,
    this.subtitle,
    required this.body,
    this.bottom,
  });

  final String title;
  final String? subtitle;
  final Widget body; // fills the middle; scrolls if it is long
  final Widget? bottom; // pinned buttons

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppText.title),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle!, style: AppText.body.copyWith(fontSize: 11)),
          ],
          const SizedBox(height: 14),
          Expanded(child: body),
          if (bottom != null) ...[const SizedBox(height: 12), bottom!],
        ],
      ),
    );
  }
}

const pickSubtitle =
    'Pick a PDF. IlocoAdal finds its key terms, adds a definition and a sentence from the text, '
    'then translates both.';

/// Thin green line between sections.
class GreenDivider extends StatelessWidget {
  const GreenDivider({super.key});
  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 14),
    child: Divider(height: 1, thickness: 1, color: AppColors.green),
  );
}

/// The pink information box.
class NoticeBox extends StatelessWidget {
  const NoticeBox(this.lines, {super.key});
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.notice,
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        lines.join('\n'),
        textAlign: TextAlign.center,
        style: AppText.body.copyWith(fontSize: 10.5),
      ),
    );
  }
}

const offlineNotice =
    'An internet connection is needed for definitions and translation';

class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.loading = false,
  });
  final String label;
  final VoidCallback? onPressed;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: FilledButton(
        onPressed: loading ? null : onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.green,
          foregroundColor: Colors.white,
          disabledBackgroundColor: onPressed == null && !loading
              ? AppColors.disabled
              : AppColors.green,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        ),
        child: loading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : Text(label, style: AppText.button),
      ),
    );
  }
}

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({
    super.key,
    required this.label,
    required this.onPressed,
  });
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          backgroundColor: const Color(0xFFF9F9F9),
          foregroundColor: AppColors.ink,
          side: const BorderSide(color: AppColors.ink, width: 1),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        ),
        child: Text(label, style: AppText.button),
      ),
    );
  }
}

/// White card with a thin border (file list, step list, term list).
class WhiteCard extends StatelessWidget {
  const WhiteCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(12),
  });
  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

/// Dashed rounded border for the upload box.
class DashedRRectPainter extends CustomPainter {
  DashedRRectPainter({
    this.color = AppColors.border,
    this.radius = 12,
    this.dash = 5,
    this.gap = 4,
  });
  final Color color;
  final double radius, dash, gap;

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..addRRect(
        RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(radius)),
      );
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    for (final PathMetric metric in path.computeMetrics()) {
      double d = 0;
      while (d < metric.length) {
        canvas.drawPath(metric.extractPath(d, d + dash), paint);
        d += dash + gap;
      }
    }
  }

  @override
  bool shouldRepaint(covariant DashedRRectPainter old) => old.color != color;
}
