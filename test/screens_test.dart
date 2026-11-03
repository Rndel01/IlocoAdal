// Widget tests for every screen in the Figma design.
// Replaces the old test that used `DocumentError` (that enum no longer exists;
// the equivalent is `ErrorKind` in screens/error_screen.dart).
//
// Run with:  flutter test
//
// Nothing here talks to the Python server: each test puts the controller into
// the state a screen needs and checks what is drawn.

// ignore_for_file: avoid_relative_lib_imports
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../lib/api/ilocoadal_client.dart';
import '../lib/screens/error_screen.dart';
import '../lib/screens/ilokostyle.dart';
import '../lib/state/app_controller.dart';
import '../lib/theme/app_theme.dart';

// ---- helpers ---------------------------------------------------------------------

AppController newController() =>
    AppController(baseUrl: 'http://127.0.0.1:1')..engine = EngineState.ready;

Future<void> show(WidgetTester tester, AppController c) async {
  tester.view.physicalSize = const Size(390 * 3, 844 * 3); // a phone-sized screen
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: AppRoot(controller: c)));
  // pump, not pumpAndSettle: the Processing spinner animates forever.
  await tester.pump(const Duration(milliseconds: 400));
}

FileInfo file(String name, {double mb = 5.05, int pages = 23}) =>
    FileInfo({'id': name, 'name': name, 'format': 'PDF', 'size_mb': mb, 'pages': pages});

JobStatus status(String state, {int step = 0, String label = '', List<String>? stepStates,
    Map<String, dynamic>? summary, List<Map<String, String>>? warnings}) {
  const keys = ['read', 'clean', 'rank', 'contexts', 'definitions', 'translate', 'build'];
  final states = stepStates ?? List.filled(7, 'pending');
  return JobStatus({
    'id': 'job1',
    'state': state,
    'files': [],
    'can_start': false,
    'step': step,
    'total_steps': 7,
    'label': label,
    'steps': [
      for (var i = 0; i < 7; i++) {'key': keys[i], 'label': keys[i], 'status': states[i]},
    ],
    'progress': 0.0,
    'summary': summary,
    'warnings': warnings ?? [],
    'error': null,
    'document_path': null,
  });
}

KeyTerm term(String word, {double score = 0.5, List<String> definitions = const ['A definition.']}) =>
    KeyTerm({
      'id': word,
      'word': word,
      'score': 0.1,
      'relative_score': score,
      'selected': true,
      'variants': <String>[],
      'contexts': ['The $word appears in a sentence.'],
      'definitions': definitions,
      'translated_definitions': ['Naipatarus a kayat a sawen.'],
      'translated_contexts': ['Naipatarus a pangudal.'],
    });

// ---- tests ----------------------------------------------------------------------------

void main() {
  group('Upload and Ready to Process', () {
    testWidgets('Upload screen shows the button, the limits and the internet notice', (tester) async {
      await show(tester, newController());
      expect(find.text('Upload Documents'), findsNWidgets(2)); // title + button
      expect(find.text('Supports .pdf up to 20MB'), findsOneWidget);
      expect(find.textContaining('An internet connection is needed'), findsOneWidget);
    });

    testWidgets('Ready screen lists each file with format, size and pages', (tester) async {
      final c = newController()
        ..files.addAll([file('Chapter 1 - Lesson 4.pdf'), file('Chapter 2.pdf', mb: 1.2, pages: 4)]);
      await show(tester, c);
      expect(find.text('Ready to Process'), findsOneWidget);
      expect(find.text('Chapter 1 - Lesson 4.pdf'), findsOneWidget);
      expect(find.text('5.05 MB - 23 pages'), findsOneWidget);
      expect(find.text('1.20 MB - 4 pages'), findsOneWidget);
      expect(find.text('PDF file format'), findsNWidgets(2));
      expect(find.byIcon(Icons.close), findsNWidgets(2)); // one X per file
      expect(find.text('Upload another document'), findsOneWidget);
      expect(find.text('Start Processing'), findsOneWidget);
    });
  });

  group('Processing', () {
    testWidgets('shows "Step X of Y" and the checklist', (tester) async {
      final c = newController()
        ..status = status('enriching', step: 5, label: 'Fetching definitions',
            stepStates: ['done', 'done', 'done', 'done', 'active', 'pending', 'pending']);
      await show(tester, c);
      expect(find.text('Step 5 of 7: fetching definitions'), findsOneWidget);
      expect(find.text('Reading Document'), findsOneWidget);
      expect(find.text('Fetching Definitions'), findsOneWidget);
      expect(find.text('Build Document'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle_outline), findsNWidgets(4)); // 4 finished steps
      expect(find.byType(CircularProgressIndicator), findsOneWidget); // the active step
      expect(find.text('Cancel'), findsOneWidget);
    });

    testWidgets('updates when the controller reports the next step', (tester) async {
      final c = newController()
        ..status = status('enriching', step: 5, label: 'Fetching definitions',
            stepStates: ['done', 'done', 'done', 'done', 'active', 'pending', 'pending']);
      await show(tester, c);
      expect(find.text('Step 5 of 7: fetching definitions'), findsOneWidget);

      c.status = status('enriching', step: 6, label: 'Translating content',
          stepStates: ['done', 'done', 'done', 'done', 'done', 'active', 'pending']);
      c.notifyListeners(); // what the poll loop does after every update
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Step 6 of 7: translating content'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle_outline), findsNWidgets(5));
    });

    testWidgets('skipped steps are marked', (tester) async {
      final c = newController()
        ..status = status('building', step: 7, label: 'Build document',
            stepStates: ['done', 'done', 'done', 'done', 'skipped', 'skipped', 'active']);
      await show(tester, c);
      expect(find.text('Fetching Definitions (skipped)'), findsOneWidget);
    });
  });

  group('Document Ready', () {
    testWidgets('summary, terms and download button', (tester) async {
      final c = newController()
        ..status = status('done', summary: {'term_count': 2, 'without_definition': 1, 'document_count': 1})
        ..terms = [term('algorithm', score: 1.0), term('model', score: 0.9, definitions: ['Definition not available'])];
      await show(tester, c);
      expect(find.text('The document is ready.'), findsOneWidget);
      expect(find.text('2 key terms found.\n1 term had no definition available.'), findsOneWidget);
      expect(find.text('algorithm'), findsOneWidget);
      expect(find.text('score 1.00'), findsOneWidget);
      expect(find.text('Definition not available'), findsOneWidget);
      expect(find.text('Translation'), findsNWidgets(2));
      expect(find.text('Download Document'), findsOneWidget);
    });

    testWidgets('the terms box scrolls on its own', (tester) async {
      final c = newController()
        ..status = status('done', summary: {'term_count': 25, 'without_definition': 0, 'document_count': 1})
        ..terms = [for (var i = 0; i < 25; i++) term('word$i')];
      await show(tester, c);
      expect(find.text('word0'), findsOneWidget);
      expect(find.text('word24'), findsNothing); // off screen until scrolled
      await tester.scrollUntilVisible(find.text('word24'), 300,
          scrollable: find.byType(Scrollable).first);
      expect(find.text('word24'), findsOneWidget);
      expect(find.text('Download Document'), findsOneWidget); // button stays in place
    });

    testWidgets('warnings (e.g. no internet) appear in the summary box', (tester) async {
      final c = newController()
        ..status = status('done',
            summary: {'term_count': 1, 'without_definition': 0, 'document_count': 1},
            warnings: [{'code': 'no_internet', 'message': 'No internet connection. Definitions and translations were left out.'}])
        ..terms = [term('algorithm')];
      await show(tester, c);
      expect(find.textContaining('1 key term found.'), findsOneWidget);
      expect(find.textContaining('were left out'), findsOneWidget);
    });
  });

  group('Error screens', () {
    final cases = {
      'unsupported_file': "This file can't be used",
      'cannot_read': "Can't read this document",
      'no_key_terms': 'No key terms found',
    };
    cases.forEach((code, title) {
      testWidgets('$code -> "$title"', (tester) async {
        final c = newController()..error = AppError(code, 'engine message');
        await show(tester, c);
        expect(find.text(title), findsOneWidget);
        expect(find.text('Choose another file'), findsOneWidget);
        expect(find.byIcon(Icons.error_outline), findsOneWidget);
      });
    });

    testWidgets('the engine\'s own message is shown under the standard text', (tester) async {
      final c = newController()
        ..error = const AppError('unsupported_file', 'This file is too large (limit is 20 MB).');
      await show(tester, c);
      expect(find.text('This file is too large (limit is 20 MB).'), findsOneWidget);
    });

    testWidgets('No internet connection has both buttons', (tester) async {
      final c = newController()..status = status('offline', step: 5, label: 'Fetching definitions');
      await show(tester, c);
      expect(find.text('No internet connection'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
      expect(find.text('Continue without definitions'), findsOneWidget);
      expect(find.byIcon(Icons.wifi_off), findsOneWidget);
    });

    testWidgets('engine not running', (tester) async {
      final c = AppController(baseUrl: 'http://127.0.0.1:1')
        ..engine = EngineState.down
        ..engineMessage = "Couldn't reach the app's engine. Make sure it is running.";
      await show(tester, c);
      expect(find.text("Can't reach the app's engine"), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });

    test('error codes map to the right screen', () {
      expect(errorKindFor('unsupported_file'), ErrorKind.file);
      expect(errorKindFor('duplicate_file'), ErrorKind.file);
      expect(errorKindFor('cannot_read'), ErrorKind.noText);
      expect(errorKindFor('no_key_terms'), ErrorKind.noTerms);
      expect(errorKindFor('engine_down'), ErrorKind.engine);
      expect(errorKindFor('something_else'), ErrorKind.generic);
    });
  });
}
