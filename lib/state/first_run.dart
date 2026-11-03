import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Remembers whether the first-open walkthrough was already shown.
/// A small marker file in the app's private folder is enough. Clearing the
/// app's data (or reinstalling) shows the walkthrough again.
class FirstRun {
  static Future<File> _file() async {
    final dir = await getApplicationSupportDirectory();
    return File('${dir.path}${Platform.pathSeparator}walkthrough_seen');
  }

  /// true if the walkthrough was seen. If the folder can't be read, answers
  /// true so the user is never stuck on it.
  static Future<bool> hasSeenWalkthrough() async {
    try {
      return (await _file()).existsSync();
    } catch (_) {
      return true;
    }
  }

  static Future<void> markSeen() async {
    try {
      await (await _file()).writeAsString('1');
    } catch (_) {}
  }
}
