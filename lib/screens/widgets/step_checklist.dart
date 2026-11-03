import 'package:flutter/material.dart';

import '../../api/ilocoadal_client.dart';
import '../../theme/app_theme.dart';

/// Row wording from the Figma Processing screen, by the server's step key.
const _designLabels = {
  'read': 'Reading Document',
  'clean': 'Extract and Clean text',
  'rank': 'Rank key terms',
  'contexts': 'Find Context Sentences',
  'definitions': 'Fetching Definitions',
  'translate': 'Translating Content',
  'build': 'Build Document',
};

/// The Processing screen's checklist. Rebuilds on every status poll, so a row
/// goes pending -> active (gold spinner) -> done (green check) as the engine
/// moves through the steps.
class StepChecklist extends StatelessWidget {
  const StepChecklist({super.key, required this.steps});
  final List<StepInfo> steps;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var i = 0; i < steps.length; i++) ...[
          _StepRow(step: steps[i]),
          if (i < steps.length - 1)
            const Divider(height: 1, thickness: 1, color: AppColors.hairline),
        ],
      ],
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.step});
  final StepInfo step;

  @override
  Widget build(BuildContext context) {
    final label = _designLabels[step.key] ?? step.label;
    final active = step.status == 'active';
    final muted = step.status == 'pending' || step.status == 'skipped';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        children: [
          SizedBox(
            width: 20,
            height: 20,
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 250),
              child: KeyedSubtree(
                key: ValueKey(step.status),
                child: _icon(step.status),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              step.status == 'skipped' ? '$label (skipped)' : label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                color: muted ? AppColors.muted : AppColors.ink,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _icon(String status) {
    switch (status) {
      case 'done':
        return const Icon(
          Icons.check_circle_outline,
          size: 19,
          color: AppColors.green,
        );
      case 'active':
        return const Padding(
          padding: EdgeInsets.all(2),
          child: CircularProgressIndicator(
            strokeWidth: 2.2,
            color: AppColors.gold,
          ),
        );
      case 'skipped':
        return const Icon(
          Icons.remove_circle_outline,
          size: 19,
          color: AppColors.muted,
        );
      case 'error':
        return const Icon(
          Icons.error_outline,
          size: 19,
          color: AppColors.errorIcon,
        );
      default: // pending, cancelled
        return const Icon(
          Icons.radio_button_unchecked,
          size: 19,
          color: AppColors.disabled,
        );
    }
  }
}
