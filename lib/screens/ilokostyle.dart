import 'package:flutter/material.dart';

import '../app_config.dart';
import '../state/app_controller.dart';
import '../engine/engine_launcher.dart';
import '../theme/app_theme.dart';
import 'error_screen.dart';
import 'processing_screen.dart';
import 'ready_screen.dart';
import 'results_screen.dart';
import 'upload_screen.dart';
import 'widgets/common.dart';
import 'launch_gate.dart';

/// The app. main.dart runs this, as before.
class IlokoStyleApp extends StatefulWidget {
  const IlokoStyleApp({super.key});

  @override
  State<IlokoStyleApp> createState() => _IlokoStyleAppState();
}

class _IlokoStyleAppState extends State<IlokoStyleApp> {
  late final AppController _controller;

  @override
  void initState() {
    super.initState();
    final embedded = EngineLauncher.isEmbedded;
    _controller = AppController(
      baseUrl: embedded ? EngineLauncher.baseUrl : AppConfig.baseUrl,
      token: embedded ? null : AppConfig.token,
      startEngine: embedded
          ? () async {
              await EngineLauncher.start();
              _controller.api.token = EngineLauncher.token;
            }
          : null,
    )..init();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IlocoAdal',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      builder: (context, child) {
        final mq = MediaQuery.of(context);
        // Keep the phone's own font-size setting, then make everything 20% bigger.
        final system = mq.textScaler.scale(10) / 10;
        return MediaQuery(
          data: mq.copyWith(textScaler: TextScaler.linear(system * 1.2)),
          child: child!,
        );
      },
      home: LaunchGate(
        controller: _controller,
        app: AppRoot(controller: _controller),
      ),
    );
  }
}

/// Chooses the screen from the controller's state, so nothing navigates by hand:
///
///   engine not reachable  -> error (engine)
///   an error to show      -> the matching error screen
///   job is "offline"      -> "No internet connection"
///   job is "done"         -> Document Ready
///   job is running        -> Processing
///   files in the list     -> Ready to Process
///   otherwise             -> Upload Documents
class AppRoot extends StatelessWidget {
  const AppRoot({super.key, required this.controller});
  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final screen = _pick(controller);
        final atUpload =
            controller.jobId == null &&
            controller.error == null &&
            controller.status == null &&
            controller.files.isEmpty;
        return PopScope(
          canPop: atUpload, // only leave the app from the Upload screen
          onPopInvokedWithResult: (didPop, _) {
            if (didPop) return;
            final s = controller.status;
            if (s != null && !s.isFinished) {
              controller.cancel(); // processing: cancel the job, go to Upload
            } else {
              controller.reset(); // results / ready / error: go to Upload
            }
          },
          child: AppShell(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: KeyedSubtree(
                key: ValueKey(screen.name),
                child: screen.widget,
              ),
            ),
          ),
        );
      },
    );
  }

  ({String name, Widget widget}) _pick(AppController c) {
    if (c.engine == EngineState.checking) {
      return (
        name: 'checking',
        widget: const Center(child: CircularProgressIndicator()),
      );
    }
    if (c.engine == EngineState.down) {
      return (
        name: 'engine',
        widget: ErrorScreen(
          c: c,
          kind: ErrorKind.engine,
          detail: c.engineMessage,
        ),
      );
    }
    final error = c.error;
    if (error != null) {
      final kind = errorKindFor(error.code);
      return (
        name: 'error-${kind.name}',
        widget: ErrorScreen(c: c, kind: kind, detail: error.message),
      );
    }
    final s = c.status;
    if (s != null && s.state == 'offline') {
      return (
        name: 'offline',
        widget: ErrorScreen(c: c, kind: ErrorKind.offline),
      );
    }
    if (s != null && s.state == 'done') {
      return (name: 'results', widget: ResultsScreen(c));
    }
    if (s != null && !s.isFinished) {
      return (name: 'processing', widget: ProcessingScreen(c));
    }
    if (c.files.isNotEmpty) return (name: 'ready', widget: ReadyScreen(c));
    return (name: 'upload', widget: UploadScreen(c));
  }
}
