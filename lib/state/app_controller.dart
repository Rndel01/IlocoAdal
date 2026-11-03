import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../api/ilocoadal_client.dart';

enum EngineState { checking, ready, down }

/// Something to show on an error screen.
class AppError {
  const AppError(this.code, this.message, {this.fromProcessing = false});
  final String
  code; // unsupported_file, cannot_read, no_key_terms, engine_down, ...
  final String message; // safe to display
  final bool
  fromProcessing; // true: the whole job failed; false: adding a file failed
}

/// Everything the screens need. Each button calls one method here; the
/// screens only read the fields and rebuild when notifyListeners() fires.
class AppController extends ChangeNotifier {
  AppController({required String baseUrl, String? token, this.startEngine})
    : api = IlocoAdalClient(
        baseUrl,
        token: (token == null || token.isEmpty) ? null : token,
      );

  final IlocoAdalClient api;
  final Future<void> Function()? startEngine;

  // Engine (the Python server)
  EngineState engine = EngineState.checking;
  String engineMessage = '';

  // Upload screen text, read from the server's config
  List<String> allowedExtensions = ['pdf'];
  String supportedText = 'Supports .pdf up to 20MB';

  // Current job
  String? jobId;
  final List<FileInfo> files = []; // "Ready to Process" list
  JobStatus? status; // set once processing starts
  List<KeyTerm> terms = []; // result cards
  AppError? error;
  bool busy = false;

  // How many key terms to find (shown as a slider on the Ready screen)
  static const int minTopN = 10;
  static const int maxTopN = 40;
  int topN = 15;
  final Map<String, String> _paths = {}; // file id -> path, to rebuild the job

  void setTopN(int value) {
    topN = value.clamp(minTopN, maxTopN);
    notifyListeners();
  }

  // ---------------------------------------------------------------------------------
  // Start-up
  // ---------------------------------------------------------------------------------
  Future<void> init() async {
    engine = EngineState.checking;
    notifyListeners();
    try {
      if (startEngine != null) await startEngine!();
      final cfg = await api.config();
      final exts = List<String>.from(cfg['files']['allowed_extensions']);
      final mb = (cfg['files']['max_file_size_mb'] as num).toDouble();
      allowedExtensions = [for (final e in exts) e.replaceFirst('.', '')];
      supportedText =
          'Supports ${exts.join(', ')} up to ${mb == mb.roundToDouble() ? mb.toInt() : mb}MB';
      engine = EngineState.ready;
    } on IlocoAdalException catch (e) {
      engine = EngineState.down;
      engineMessage = e.message;
    } catch (_) {
      engine = EngineState.down;
      engineMessage =
          "Couldn't reach the app's engine. Make sure it is running.";
    }
    notifyListeners();
  }

  // ---------------------------------------------------------------------------------
  // Upload Documents / Upload another document
  // ---------------------------------------------------------------------------------
  Future<void> addDocument() async {
    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: allowedExtensions,
    );
    if (picked.isEmpty) return; // the user closed the file browser
    for (final f in picked) {
      final path = f.path;
      if (path == null) continue;
      await _run(() async {
        jobId ??= (await api.createJob()).id;
        final info = await api.addFile(jobId!, path);
        files.add(info);
        _paths[info.id] = path;
      });
      if (error != null) break;
    }
  }

  /// The X on a file row.
  Future<void> removeFile(FileInfo file) => _run(() async {
    await api.removeFile(jobId!, file.id);
    files.removeWhere((f) => f.id == file.id);
    _paths.remove(file.id);
  });

  // ---------------------------------------------------------------------------------
  // Start Processing / Try again / Continue without definitions
  // ---------------------------------------------------------------------------------
  Future<void> startProcessing() => _run(() async {
    final oldId = jobId!;
    // The job already exists, so make a fresh one that carries top_n.
    final fresh = await api.createJob(
      paths: _paths.values.toList(),
      options: {'top_n': topN},
    );
    jobId = fresh.id;
    files
      ..clear()
      ..addAll(fresh.files);
    try {
      await api.cancel(oldId); // discard the empty draft
    } catch (_) {}
    status = await api.start(fresh.id);
    notifyListeners();
    await _poll(fresh.id);
  }, processing: true);

  Future<void> retryOnline() => _run(() async {
    final id = jobId!;
    status = await api.retry(id);
    notifyListeners();
    await _poll(id);
  }, processing: true);

  Future<void> continueWithoutOnline() => _run(() async {
    final id = jobId!;
    status = await api.skipOnline(id);
    notifyListeners();
    await _poll(id);
  }, processing: true);

  /// Follows the job until it is done, failed, or needs the user (offline).
  /// Every update redraws the Processing screen's checklist.
  Future<void> _poll(String id) async {
    final last = await api.waitFor(
      id,
      {'done', 'offline'},
      onUpdate: (s) {
        if (jobId != id || s.state == 'done') {
          return; // cancelled meanwhile / hold "done" back
        }
        status = s;
        notifyListeners();
      },
    );
    if (jobId != id) return; // the user cancelled and went back to Upload
    if (last.state == 'done') {
      terms = await api.terms(id); // load the cards before showing Results
    } else if (last.state == 'error') {
      error = AppError(
        last.error?['code'] ?? 'unknown',
        last.error?['message'] ?? 'Something went wrong.',
        fromProcessing: true,
      );
    }
    status = last;
  }

  /// Cancel button on the Processing screen.
  Future<void> cancel() async {
    final id = jobId;
    if (id != null) {
      try {
        await api.cancel(id);
      } catch (_) {}
    }
    reset();
  }

  // ---------------------------------------------------------------------------------
  // Download Document
  // ---------------------------------------------------------------------------------
  /// Downloads the .docx, then lets the user choose where to save it.
  /// Returns path == null and error == null when the user cancels the dialog.
  Future<({String? path, String? error})> download() async {
    final id = jobId;
    if (id == null) {
      return (path: null, error: 'There is no document to download yet.');
    }
    busy = true;
    notifyListeners();
    File? temp;
    try {
      // "<original name>_ilocoadal_2026-11-03.docx"
      final now = DateTime.now();
      final date =
          '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
      final String name;
      if (files.length == 1) {
        final base = files.first.name.replaceFirst(RegExp(r'\.[^./\\]+$'), '');
        name = '${base}_ilocoadal_$date.docx';
      } else {
        name = 'combined_ilocoadal_$date.docx';
      }
      // 1. Download into a temporary file.
      final tmpDir = await getTemporaryDirectory();
      temp = await api.downloadDocument(
        id,
        '${tmpDir.path}${Platform.pathSeparator}$name',
      );
      final bytes = await temp.readAsBytes();

      // 2. Let the user choose the folder and file name.
      final chosen = await FilePicker.saveFile(
        dialogTitle: 'Save document',
        fileName: name,
        bytes: bytes,
      );
      if (chosen == null) return (path: null, error: null); // cancelled

      // Desktop: the picker only returns the path, so write the file here.
      if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
        await File.fromUri(chosen).writeAsBytes(bytes);
      }
      return (path: chosen.toString(), error: null);
    } on IlocoAdalException catch (e) {
      return (path: null, error: e.message);
    } catch (_) {
      return (path: null, error: "Couldn't save the document.");
    } finally {
      try {
        await temp?.delete();
      } catch (_) {}
      busy = false;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------------
  // Error screens
  // ---------------------------------------------------------------------------------
  /// "Choose another file".
  Future<void> chooseAnotherFile() async {
    if (error?.fromProcessing ?? false) {
      reset(); // the whole job failed: start a fresh list
    } else {
      error = null; // adding one file failed: keep the rest of the list
      notifyListeners();
    }
    await addDocument();
  }

  /// "Try again" on the generic / engine error screens.
  Future<void> tryAgainAfterError() async {
    final wasEngine =
        error?.code == 'engine_down' || engine == EngineState.down;
    reset();
    if (wasEngine) await init();
  }

  /// Back to the Upload screen.
  void reset() {
    jobId = null;
    status = null;
    files.clear();
    _paths.clear();
    terms = [];
    error = null;
    busy = false;
    notifyListeners();
  }

  Future<void> _run(
    Future<void> Function() action, {
    bool processing = false,
  }) async {
    error = null;
    busy = true;
    notifyListeners();
    try {
      await action();
    } on IlocoAdalException catch (e) {
      error = AppError(e.code, e.message, fromProcessing: processing);
    } catch (_) {
      error = AppError(
        'unknown',
        'Something went wrong. Please try again.',
        fromProcessing: processing,
      );
    } finally {
      busy = false;
      notifyListeners();
    }
  }
}
