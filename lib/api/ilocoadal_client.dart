// Dart client for the IlocoAdal local server. Needs the `http` package.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// Any error reply. [code] is stable, so the app can pick a screen without
/// reading [message]:
///   unsupported_file, cannot_read, no_key_terms   -> the three error screens
///   engine_down                                    -> the server can't be reached
///   no_files, duplicate_file, wrong_state, unauthorized, ...
/// [message] is safe to show to the user.
class IlocoAdalException implements Exception {
  IlocoAdalException(this.code, this.message);
  final String code;
  final String message;
  @override
  String toString() => message;
}

/// One row of the "Ready to Process" list.
class FileInfo {
  FileInfo(this.json);
  final Map<String, dynamic> json;

  String get id => json['id'];
  String get name => json['name'];
  String get format => json['format']; // "PDF"
  double get sizeMb => (json['size_mb'] as num).toDouble();
  int? get pages => json['pages']; // null for formats without pages
}

/// One row of the Processing checklist.
class StepInfo {
  StepInfo(this.json);
  final Map<String, dynamic> json;

  /// read, clean, rank, contexts, definitions, translate, build
  String get key => json['key'];
  String get label => json['label'];

  /// done, active, pending, skipped, error, cancelled
  String get status => json['status'];
}

class JobStatus {
  JobStatus(this.json);
  final Map<String, dynamic> json;

  String get id => json['id'];

  /// draft, analyzing, review, enriching, building, offline, done, error, cancelled
  String get state => json['state'];
  bool get isFinished => const {'done', 'error', 'cancelled'}.contains(state);

  List<FileInfo> get files => [for (final f in json['files']) FileInfo(f)];
  bool get canStart => json['can_start'];

  int get step => json['step'];
  int get totalSteps => json['total_steps'];
  String get label => json['label'];
  List<StepInfo> get steps => [for (final s in json['steps']) StepInfo(s)];
  double get progress => (json['progress'] as num).toDouble();

  int? get termCount => json['summary']?['term_count'];
  int? get withoutDefinition => json['summary']?['without_definition'];
  int? get documentCount => json['summary']?['document_count'];

  /// [{code, message}] - e.g. no_internet, file_skipped
  List<dynamic> get warnings => json['warnings'];

  /// {code, message} when state == 'error'
  Map<String, dynamic>? get error => json['error'];
  String? get documentPath => json['document_path'];
}

class KeyTerm {
  KeyTerm(this.json);
  final Map<String, dynamic> json;

  String get id => json['id'];
  String get word => json['word'];
  double get score => (json['score'] as num).toDouble();
  double get relativeScore =>
      (json['relative_score'] as num).toDouble(); // 0-1 vs the top term
  bool get selected => json['selected'];
  List<String> get variants => List<String>.from(json['variants']);
  List<String> get contexts => List<String>.from(json['contexts']);
  List<String> get definitions => List<String>.from(json['definitions']);
  List<String> get translatedDefinitions =>
      List<String>.from(json['translated_definitions']);
  List<String> get translatedContexts =>
      List<String>.from(json['translated_contexts']);
}

class IlocoAdalClient {
  IlocoAdalClient(this.baseUrl, {this.token, http.Client? client})
    : _http = client ?? http.Client();

  String? token; // server.auth_token from config.json
  final String baseUrl; // e.g. 'http://127.0.0.1:8765'
  final http.Client _http;
  static const _timeout = Duration(seconds: 60);

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  /// [cause] is the real network error, so the error screen can show why.
  IlocoAdalException _engineDown([Object? cause]) => IlocoAdalException(
    'engine_down',
    "Couldn't reach the app's engine at $baseUrl. Make sure it is running."
        "${cause == null ? '' : ' ($cause)'}",
  );

  Future<dynamic> _send(String method, String path, [Object? body]) async {
    final request = http.Request(method, Uri.parse('$baseUrl$path'))
      ..headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
    http.Response response;
    try {
      response = await http.Response.fromStream(
        await _http.send(request).timeout(_timeout),
      );
    } on TimeoutException catch (e) {
      throw _engineDown(e);
    } on SocketException catch (e) {
      throw _engineDown(e);
    } on http.ClientException catch (e) {
      throw _engineDown(e);
    }
    dynamic decoded;
    try {
      decoded = response.body.isEmpty ? null : jsonDecode(response.body);
    } on FormatException {
      throw IlocoAdalException(
        'unknown',
        'Unexpected reply from the app\'s engine.',
      );
    }
    if (response.statusCode >= 400) {
      final e = (decoded is Map ? decoded['error'] : null) ?? {};
      throw IlocoAdalException(
        e['code'] ?? 'unknown',
        e['message'] ?? 'Something went wrong.',
      );
    }
    return decoded;
  }

  /// Settings the UI may show: files.max_file_size_mb, files.allowed_extensions, ...
  Future<Map<String, dynamic>> config() async => await _send('GET', '/config');

  // --- Upload / Ready to Process -------------------------------------------------
  Future<JobStatus> createJob({
    List<String>? paths,
    Map<String, dynamic>? options,
  }) async => JobStatus(
    await _send('POST', '/jobs', {
      'paths': paths ?? [],
      'options': options ?? {},
    }),
  );

  /// Throws for unusable files (unsupported_file, cannot_read) and duplicate_file.
  Future<FileInfo> addFile(String id, String filePath) async =>
      FileInfo(await _send('POST', '/jobs/$id/files', {'path': filePath}));

  Future<void> removeFile(String id, String fileId) =>
      _send('DELETE', '/jobs/$id/files/$fileId');

  Future<JobStatus> start(String id) async =>
      JobStatus(await _send('POST', '/jobs/$id/start'));

  // --- Processing ------------------------------------------------------------------
  Future<JobStatus> job(String id) async =>
      JobStatus(await _send('GET', '/jobs/$id'));

  /// Polls until the job's state is one of [states] (or it finishes).
  Future<JobStatus> waitFor(
    String id,
    Set<String> states, {
    void Function(JobStatus)? onUpdate,
    Duration every = const Duration(milliseconds: 300),
  }) async {
    while (true) {
      final status = await job(id);
      onUpdate?.call(status);
      if (states.contains(status.state) || status.isFinished) return status;
      await Future.delayed(every);
    }
  }

  Future<JobStatus> cancel(String id) async =>
      JobStatus(await _send('POST', '/jobs/$id/cancel'));

  /// After state == 'offline': "Try again".
  Future<JobStatus> retry(String id) async =>
      JobStatus(await _send('POST', '/jobs/$id/retry'));

  /// After state == 'offline': "Continue without definitions".
  Future<JobStatus> skipOnline(String id) async =>
      JobStatus(await _send('POST', '/jobs/$id/skip_online'));

  // --- Results -----------------------------------------------------------------------
  Future<List<KeyTerm>> terms(String id) async => [
    for (final t in (await _send('GET', '/jobs/$id/terms'))['terms'])
      KeyTerm(t),
  ];

  /// Saves the finished .docx to [savePath].
  Future<File> downloadDocument(String id, String savePath) async {
    http.Response response;
    try {
      response = await _http
          .get(Uri.parse('$baseUrl/jobs/$id/document'), headers: _headers)
          .timeout(_timeout);
    } on TimeoutException catch (e) {
      throw _engineDown(e);
    } on SocketException catch (e) {
      throw _engineDown(e);
    } on http.ClientException catch (e) {
      throw _engineDown(e);
    }
    if (response.statusCode >= 400) {
      final e = jsonDecode(response.body)['error'];
      throw IlocoAdalException(e['code'], e['message']);
    }
    return File(savePath).writeAsBytes(response.bodyBytes);
  }

  // --- Review key terms (only when the server has analysis.review_terms on) --------------
  Future<KeyTerm> setSelected(String id, String termId, bool selected) async =>
      KeyTerm(
        await _send('PATCH', '/jobs/$id/terms/${Uri.encodeComponent(termId)}', {
          'selected': selected,
        }),
      );

  Future<KeyTerm> addTerm(String id, String word) async =>
      KeyTerm(await _send('POST', '/jobs/$id/terms', {'word': word}));

  Future<JobStatus> continueJob(String id) async =>
      JobStatus(await _send('POST', '/jobs/$id/continue'));
}
