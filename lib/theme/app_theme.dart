import 'package:flutter/material.dart';

/// Colors sampled from the Figma screens.
class AppColors {
  static const green = Color(0xFF215E3D); // header, primary buttons, links
  static const cream = Color(0xFFF6F4ED); // page background
  static const ink = Color(0xFF29352E); // titles and body text
  static const muted = Color(0xFF6D766F); // secondary text
  static const notice = Color(0xFFE2D7D7); // the pink info boxes
  static const border = Color(0xFFD7D4C9); // card and dashed borders
  static const hairline = Color(0xFFE6E3DA); // lines between rows
  static const gold = Color(0xFFE0A526); // the active step spinner
  static const pdfBadge = Color(0xFFFCEEEC);
  static const pdfRed = Color(0xFFE25349);
  static const errorCircle = Color(0xFFFADCD7);
  static const errorIcon = Color(0xFFC9473C);
  static const warnCircle = Color(0xFFF7F1DE);
  static const warnIcon = Color(0xFFA8701A);
  static const canvas = Color(0xFF464646); // only visible around the phone column on desktop
  static const disabled = Color(0xFFC9CEC9);
}

/// Fonts. The buttons and file details use a monospace face in the design.
/// To use the exact Figma fonts, add them to pubspec.yaml and change the names here.
class AppText {
  static const mono = TextStyle(
    fontFamily: 'monospace',
    fontFamilyFallback: ['Menlo', 'Consolas', 'Courier New', 'Courier'],
  );

  static final title = const TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w700,
    color: AppColors.ink,
    height: 1.2,
  );
  static final body = const TextStyle(fontSize: 11.5, color: AppColors.ink, height: 1.4);
  static final small = const TextStyle(fontSize: 10.5, color: AppColors.muted, height: 1.4);
  static final button = mono.copyWith(fontSize: 12.5, fontWeight: FontWeight.w700);
}

ThemeData buildTheme() {
  return ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.canvas,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.green,
      primary: AppColors.green,
      surface: AppColors.cream,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.gold),
  );
}
