import 'package:flutter/material.dart';

import '../../api/ilocoadal_client.dart';
import '../../theme/app_theme.dart';

const _notAvailable = 'Definition not available';

/// One found term: word and score, then Definition, Context and Translation.
class TermCard extends StatelessWidget {
  const TermCard({super.key, required this.term});
  final KeyTerm term;

  @override
  Widget build(BuildContext context) {
    final forms = [term.word, ...term.variants];
    final translation = [
      ...term.translatedDefinitions,
      ...term.translatedContexts,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Expanded(
              child: Text(
                term.word,
                style: const TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.w700,
                  color: AppColors.ink,
                ),
              ),
            ),
            // relativeScore: 1.00 = the top term. Use term.score for the raw TF-IDF value.
            Text(
              'score ${term.relativeScore.toStringAsFixed(2)}',
              style: const TextStyle(fontSize: 9.5, color: AppColors.green),
            ),
          ],
        ),
        if (term.definitions.isNotEmpty) ...[
          const _Label('Definition'),
          for (final d in term.definitions)
            d == _notAvailable
                ? Text(
                    d,
                    style: AppText.body.copyWith(
                      color: AppColors.muted,
                      fontStyle: FontStyle.italic,
                    ),
                  )
                : Text(d, style: AppText.body),
        ],
        if (term.contexts.isNotEmpty) ...[
          const _Label('Context'),
          for (final c in term.contexts)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Text.rich(
                TextSpan(style: AppText.body, children: _highlight(c, forms)),
              ),
            ),
        ],
        if (translation.isNotEmpty) ...[
          const _Label('Translation'),
          for (final t in translation) Text(t, style: AppText.body),
        ],
      ],
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8, bottom: 2),
    child: Text(
      text,
      style: const TextStyle(
        fontSize: 9.5,
        fontWeight: FontWeight.w700,
        color: AppColors.green,
      ),
    ),
  );
}

/// Bolds every form of the term inside its context sentence (like the document does).
List<TextSpan> _highlight(String sentence, List<String> forms) {
  final sorted = [...forms]..sort((a, b) => b.length.compareTo(a.length));
  // The words of a phrase may be joined by spaces or hyphens ("object-oriented").
  final parts = sorted.map(
    (f) => f.split(' ').map(RegExp.escape).join(r'[\s\-]+'),
  );
  final pattern = RegExp(
    r'\b(' + parts.join('|') + r')\b',
    caseSensitive: false,
  );
  final spans = <TextSpan>[];
  var pos = 0;
  for (final m in pattern.allMatches(sentence)) {
    if (m.start > pos) {
      spans.add(TextSpan(text: sentence.substring(pos, m.start)));
    }
    spans.add(
      TextSpan(
        text: m.group(0),
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
    );
    pos = m.end;
  }
  if (pos < sentence.length) spans.add(TextSpan(text: sentence.substring(pos)));
  return spans;
}
