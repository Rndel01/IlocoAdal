import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/app_theme.dart';
import 'widgets/common.dart';
import 'widgets/term_card.dart';

/// Figma: "Document Ready". The terms sit in a white box that scrolls on its own;
/// the summary above it and the Download button below it stay in place.
class ResultsScreen extends StatelessWidget {
  const ResultsScreen(this.c, {super.key});
  final AppController c;

  @override
  Widget build(BuildContext context) {
    final s = c.status!;
    final count = s.termCount ?? c.terms.length;
    final noDef = s.withoutDefinition ?? 0;
    final summary = <String>[
      '$count key ${count == 1 ? 'term' : 'terms'} found.',
      if (noDef > 0)
        '$noDef ${noDef == 1 ? 'term' : 'terms'} had no definition available.',
      for (final w in s.warnings)
        w['message'] as String, // e.g. "No internet connection. ..."
    ];

    return ScreenFrame(
      title: 'The document is ready.',
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          NoticeBox(summary),
          const SizedBox(height: 12),
          Expanded(child: _TermsBox(c: c)),
        ],
      ),
      bottom: Builder(
        builder: (context) => PrimaryButton(
          label: 'Download Document',
          loading: c.busy,
          onPressed: () async {
            final result = await c.download();
            if (!context.mounted) return;
            if (result.error == null && result.path == null) {
              return; // the user cancelled the Save dialog
            }
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(result.error ?? 'Document saved.')),
            );
          },
        ),
      ),
    );
  }
}

/// The scrollable box with every found term.
class _TermsBox extends StatefulWidget {
  const _TermsBox({required this.c});
  final AppController c;

  @override
  State<_TermsBox> createState() => _TermsBoxState();
}

class _TermsBoxState extends State<_TermsBox> {
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final terms = widget.c.terms;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Scrollbar(
        controller: _scroll,
        thumbVisibility: true,
        child: ListView.separated(
          controller: _scroll,
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
          itemCount: terms.length,
          separatorBuilder: (_, _) => const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Divider(height: 1, thickness: 1, color: AppColors.green),
          ),
          itemBuilder: (_, i) => TermCard(term: terms[i]),
        ),
      ),
    );
  }
}
