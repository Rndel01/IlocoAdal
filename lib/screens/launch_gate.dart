import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../state/first_run.dart';
import 'splash_screen.dart';
import 'walkthrough_screen.dart';

enum _Phase { splash, walkthrough, app }

/// Start-up order: animated splash -> (first launch only) walkthrough -> the app.
///
/// New users go to the walkthrough right after the splash, which also fills the
/// slow first start while Python unpacks. Returning users stay on the splash
/// until the engine answers, so they never see a bare spinner.
class LaunchGate extends StatefulWidget {
  const LaunchGate({super.key, required this.controller, required this.app});
  final AppController controller;
  final Widget app; // the normal app (AppRoot)

  @override
  State<LaunchGate> createState() => _LaunchGateState();
}

class _LaunchGateState extends State<LaunchGate> {
  _Phase _phase = _Phase.splash;
  bool _minTimeDone = false; // the animation has had time to play
  bool _seenLoaded = false;
  bool _seen = true;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_advance);
    FirstRun.hasSeenWalkthrough().then((seen) {
      _seen = seen;
      _seenLoaded = true;
      _advance();
    });
    Future.delayed(const Duration(milliseconds: 2000), () {
      _minTimeDone = true;
      _advance();
    });
  }

  @override
  void dispose() {
    widget.controller.removeListener(_advance);
    super.dispose();
  }

  void _advance() {
    if (!mounted || _phase != _Phase.splash) return;
    if (!_minTimeDone || !_seenLoaded) return;
    if (_seen && widget.controller.engine == EngineState.checking) return;
    setState(() => _phase = _seen ? _Phase.app : _Phase.walkthrough);
  }

  void _finishWalkthrough() {
    FirstRun.markSeen();
    setState(() => _phase = _Phase.app);
  }

  @override
  Widget build(BuildContext context) {
    final Widget page = switch (_phase) {
      _Phase.splash => const SplashScreen(key: ValueKey('splash')),
      _Phase.walkthrough => WalkthroughScreen(
        key: const ValueKey('walkthrough'),
        onDone: _finishWalkthrough,
      ),
      _Phase.app => KeyedSubtree(key: const ValueKey('app'), child: widget.app),
    };
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 400),
      child: page,
    );
  }
}
