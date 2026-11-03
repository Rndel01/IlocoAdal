import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:serious_python/serious_python.dart';

import '../api/ilocoadal_client.dart';
import '../app_config.dart';

/// Starts the Python engine INSIDE the app, on Android and iOS.
///
/// On a computer (Linux / Windows / macOS) nothing is started here: you run
/// `python server.py` yourself, as before. To use an engine you started
/// yourself on a phone or emulator too, run with
/// `--dart-define=ILOCOADAL_EMBEDDED=false`.
class EngineLauncher {
  static const int port = 8765;
  static const _embeddedFlag = bool.fromEnvironment(
    'ILOCOADAL_EMBEDDED',
    defaultValue: true,
  );

  static bool get isEmbedded =>
      _embeddedFlag && (Platform.isAndroid || Platform.isIOS);
  static String get baseUrl => 'http://127.0.0.1:$port';

  /// Made once, then reused on every launch (saved in the app's private folder).
  static String token = '';

  static bool _started = false;

  /// Starts the engine and returns once it answers. Throws an
  /// [IlocoAdalException] (code engine_down) if it doesn't come up.
  static Future<void> start() async {
    final support = await getApplicationSupportDirectory();
    final sep = Platform.pathSeparator;

    // Same token on every launch, so an engine Android kept alive still matches.
    final tokenFile = File('${support.path}${sep}ilocoadal_token');
    if (token.isEmpty && tokenFile.existsSync()) {
      token = (await tokenFile.readAsString()).trim();
    }
    if (token.isEmpty) {
      token = _randomToken();
      await tokenFile.writeAsString(token);
    }

    if (!_started) {
      // The engine may still be running from the last time the app was open.
      if (!await _isUp()) {
        final docs = await getApplicationDocumentsDirectory();
        final out = Directory('${docs.path}${sep}IlocoAdal')
          ..createSync(recursive: true);
        final configFile = File('${support.path}${sep}ilocoadal_config.json');
        await configFile.writeAsString(
          jsonEncode({
            'files': {'output_dir': out.path},
            'server': {'port': port, 'auth_token': token},
            if (AppConfig.googleKey.isNotEmpty)
              'translation': {'api_key': AppConfig.googleKey},
          }),
        );
        unawaited(
          SeriousPython.run(
            appFileName: 'main.py',
            environmentVariables: {'ILOCOADAL_CONFIG': configFile.path},
          ).catchError((Object e) => null),
        );
      }
      _started = true;
    }
    await _waitUntilUp();
  }

  static Future<bool> _isUp() async {
    try {
      final r = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 2));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static Future<void> _waitUntilUp() async {
    // The first launch unpacks Python, so allow plenty of time.
    for (var i = 0; i < 90; i++) {
      try {
        final r = await http
            .get(Uri.parse('$baseUrl/health'))
            .timeout(const Duration(seconds: 2));
        if (r.statusCode == 200) return;
      } catch (_) {}
      await Future.delayed(const Duration(milliseconds: 500));
    }
    throw IlocoAdalException(
      'engine_down',
      "The engine didn't start. Close the app and open it again. "
          "(For developers: adb logcat | grep -i python)",
    );
  }

  static String _randomToken() {
    final r = Random.secure();
    return List.generate(24, (_) => r.nextInt(36).toRadixString(36)).join();
  }
}
