import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import 'widgets/common.dart';
import 'widgets/step_checklist.dart';

/// Figma: "Processing". The checklist and the "Step X of Y" line come straight
/// from the engine's status, which the controller polls several times a second.
class ProcessingScreen extends StatelessWidget {
  const ProcessingScreen(this.c, {super.key});
  final AppController c;

  @override
  Widget build(BuildContext context) {
    final s = c.status!;
    final subtitle = s.step == 0
        ? 'Starting...'
        : 'Step ${s.step} of ${s.totalSteps}: ${s.label.toLowerCase()}';
    return ScreenFrame(
      title: 'Processing Document',
      subtitle: subtitle,
      body: SingleChildScrollView(
        child: Column(
          children: [
            WhiteCard(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
              child: StepChecklist(steps: s.steps),
            ),
            const GreenDivider(),
            const NoticeBox([offlineNotice]),
          ],
        ),
      ),
      bottom: SecondaryButton(label: 'Cancel', onPressed: c.cancel),
    );
  }
}
