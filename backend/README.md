# IlocoAdal backend

Finds the key terms in a document, adds definitions and translations, and
writes an annotated `.docx`. The Flutter app talks to it over a small local
HTTP API.

```
pip install -r requirements.txt
python server.py --config config.json     # prints {"event":"listening","host":...,"port":...}
python main.py report.pdf --offline       # command-line test, no server needed
python -m unittest discover -s tests
```

## How the pieces map to the diagrams

| Class diagram | File |
|---|---|
| `User` | `ilocoadal/user.py` (command-line stand-in for the Flutter UI) |
| `ProcessManager` | `ilocoadal/process_manager.py` |
| `Term` | `ilocoadal/models.py` |
| `TextExtractor` / `PDFExtractor` | `ilocoadal/text_extractor.py` |
| `TextProcessor` | `ilocoadal/text_processor.py` |
| `TextAnalyzer` | `ilocoadal/text_analyzer.py` |
| `DefinitionFetcher` | `ilocoadal/definition_fetcher.py` |
| `TextTranslator` | `ilocoadal/text_translator.py` |
| `DocumentBuilder` | `ilocoadal/document_builder.py` |

Added for Flutter: `config.py` (settings), `service.py` (background jobs),
`server.py` (HTTP API), and the whole `flutter_app/lib` folder (the screens).

## Config file (`config.json`)

Write only what you want to change; everything else keeps its default.
Unknown names are rejected so typos are caught. Keys starting with `_` are ignored (use them for comments).
The shipped `config.json` lists every setting with its default.

| Setting | Default | Meaning |
|---|---|---|
| `files.max_file_size_mb` | 20 | Per file; larger files are refused (the Upload screen says 20MB) |
| `files.max_files` | 10 | Documents per job |
| `files.allowed_extensions` | `[".pdf"]` | Must also have an extractor (see `EXTRACTORS`) |
| `files.output_dir` | `""` | Where documents are saved. **Set this on a phone** (e.g. the app's documents folder) |
| `files.output_suffix` | `_key_terms` | `report.pdf` -> `report_key_terms.docx` (never overwrites; adds `_2`, `_3`) |
| `files.combined_name` | `combined` | Base name when several documents are combined: `combined_key_terms.docx` |
| `text.min_word_length` | 3 | Shorter words are dropped |
| `text.extra_filler_words` | `[]` | Added to the built-in English list |
| `text.skip_patterns` | source/citation patterns | Regexes. A sentence matching one is dropped ("Source: ...", "Retrieved from", "(2004)" citations) |
| `text.strip_patterns` | URLs, emails | Regexes. Matching text is removed from a sentence |
| `text.drop_repeated_lines_min` | 3 | A short line repeated this many times (page headers/footers) is ignored; 0 = off |
| `text.extra_abbreviations` | `[]` | Words ending in a period that don't end a sentence, e.g. `"inc."` |
| `text.normalizer` | `lemmatizer` | How word forms are merged: `lemmatizer` (handles mice/mouse; needs `simplemma`) or `stemmer` (simple rules, no dependency) |
| `text.language` | `en` | Document language for the lemmatizer |
| `analysis.top_n` | 10 | Number of key terms |
| `analysis.max_phrase_words` | 3 | Longest phrase to look for ("use case diagram" = 3). 1 = single words only |
| `analysis.min_phrase_count` | 2 | A phrase must appear at least this often |
| `analysis.phrase_cohesion` | 0.15 | 0-1. How often one word of a phrase sits next to the other. Higher = fewer, safer phrases |
| `analysis.phrase_boost` | 1.5 | Ranks phrases above single words (per extra word). 1 = no boost |
| `analysis.max_contexts` | 2 | Context sentences per term |
| `analysis.context_min_length` / `context_max_length` | 40 / 300 | Preferred sentence length |
| `analysis.heading_form` | `most_common` | Or `shortest`, or `lemma` (dictionary form, e.g. "plant"; needs the lemmatizer) |
| `analysis.review_terms` | false | Pause for a Review screen before the online steps (the current design has none) |
| `analysis.ask_when_offline` | true | If the dictionary/translator can't be reached, pause so the app can show "No internet connection" (Try again / Continue without definitions). `false` continues automatically with a warning |
| `dictionary.enabled` | true | Turn the Free Dictionary step on/off |
| `dictionary.api_url`, `language` | dictionaryapi.dev, `en` | Final URL is `{api_url}/{language}/{word}` |
| `dictionary.max_retries`, `max_definitions` | 3, 3 | |
| `dictionary.timeout_seconds`, `retry_backoff_seconds` | 10, 1 | Backoff doubles each retry |
| `translation.enabled` | true | Turn the Google Translate step on/off |
| `translation.api_key` / `api_key_env` | `""` / `GOOGLE_TRANSLATE_API_KEY` | Key in the file wins; otherwise the environment variable is read |
| `translation.source_language` / `target_language` | `en` / `ilo` | Ilocano |
| `translation.max_retries`, `timeout_seconds`, `retry_backoff_seconds` | 3, 10, 1 | |
| `document.title` | `Key terms` | Title at the top of the .docx |
| `document.include_definitions` / `include_context` / `include_translations` | true | Sections to include |
| `document.bold_matches` | true | Bold every form of the term in its context |
| `server.host`, `port` | `127.0.0.1`, 8765 | `port: 0` picks a free one (printed on start) |
| `server.auth_token` | `""` | If set, every request needs `Authorization: Bearer <token>` |
| `server.allow_origin` | `""` | CORS origin; only for Flutter web during development |
| `server.job_ttl_minutes` | 60 | How long finished jobs are remembered (documents are kept) |

A single job can override `top_n`, `review`, `target_language`, and `online`
(`false` skips both API steps): `POST /jobs {"path": "...", "options": {"top_n": 15}}`.

## How key terms are found

1. **Sentences from the layout.** Slides and notes have bullets and short lines with few full stops, so a
   bullet, a heading line, or a line that ends early starts a new sentence. Lines wrapped by the page width
   are joined again.
2. **Noise removed.** Source lines, citations, URLs and repeated page headers/footers are dropped.
3. **Phrases.** Words that keep appearing side by side ("use case", "activity diagram") become one term, and
   their words are not counted again on their own.
4. **TF-IDF ranking** over words and phrases, with each sentence treated as a small document.
5. **Context sentences:** the same sentence is never listed twice; readable lengths come first; a very long
   sentence is cut to a window around the term (shown with "...").

## The four screens and the API

| Screen | What the app calls |
|---|---|
| **Upload Documents** | `POST /jobs` creates a job in the `draft` state. `GET /config` gives "Supports .pdf up to 20MB". |
| **Ready to Process** | `POST /jobs/{id}/files {"path"}` for each file. It returns `name`, `format`, `size_mb`, `pages`, or the error to show. `DELETE /jobs/{id}/files/{file_id}` is the X. Adding another file is the same call again. |
| **Processing** | `POST /jobs/{id}/start`, then poll `GET /jobs/{id}`: `steps` (the checklist), `step` / `total_steps` / `label`, `progress`. `POST /jobs/{id}/cancel` is the Cancel button. |
| **The document is ready** | `GET /jobs/{id}` gives `summary` (`term_count`, `without_definition`) and `warnings`. `GET /jobs/{id}/terms` gives the cards. `GET /jobs/{id}/document` is Download. |

Several documents become **one combined list of key terms and one downloaded document**.
A document with no readable text (e.g. a scan) is skipped with a `file_skipped` warning
as long as another one works.

## HTTP API

All bodies are JSON. Errors look like `{"error": {"code": "...", "message": "..."}}`;
`message` is safe to show, `code` is for choosing a screen.

| Request | Purpose |
|---|---|
| `GET /health` | Is the server up? (no token needed) |
| `GET /config` | Settings, with secrets replaced by flags |
| `POST /jobs` `{"paths"?, "options"?, "start"?}` | New job in `draft`. `paths` adds files at once; `start: true` begins processing immediately |
| `GET /jobs/{id}` | Status: `state`, `files`, `can_start`, `steps`, `step`, `total_steps`, `label`, `progress`, `summary`, `warnings`, `error`, `document_path` |
| `GET /jobs/{id}/files` | The "Ready to Process" list |
| `POST /jobs/{id}/files` `{"path"}` | Add a document (only while `draft`) |
| `DELETE /jobs/{id}/files/{file_id}` | Remove a document |
| `POST /jobs/{id}/start` | Start Processing (`no_files` if the list is empty) |
| `POST /jobs/{id}/retry` | After state `offline`: **Try again**. Resumes where it stopped |
| `POST /jobs/{id}/skip_online` | After state `offline`: **Continue without definitions** |
| `GET /jobs/{id}/terms` | All terms with `score`, `relative_score` (0-1), definitions, contexts, translations |
| `POST /jobs/{id}/cancel` | Stop |
| `GET /jobs/{id}/document` | Download the `.docx` |
| `DELETE /jobs/{id}` | Forget a job |
| *Only when `analysis.review_terms` is true:* `PATCH /jobs/{id}/terms/{term_id}` `{"selected"}`, `POST /jobs/{id}/terms` `{"word"}`, `POST /jobs/{id}/continue` | The Review screen |

States: `draft` -> `analyzing` -> `enriching` -> `building` -> `done`, or `error` / `cancelled`.
`enriching` can become `offline` (no internet) and wait for `retry` or `skip_online`.
Steps the user skipped show as `skipped` in `steps`.
(With the Review option there is a `review` state after `analyzing`.)

Step keys, in order: `read` ("Reading document"), `clean` ("Extract and clean text"), `rank`, `contexts`,
`definitions` ("Fetching definitions"), `translate` ("Translating content"), `build`. Steps switched off in the
config (or by `online: false`) are left out, so `total_steps` becomes 5.

Error codes: `unsupported_file`, `cannot_read`, `no_key_terms` match the three error screens; others are
`no_files`, `duplicate_file`, `wrong_state`, `not_found`, `bad_request`, `unauthorized`, `cancelled`.
Warning codes (the job finishes anyway): `no_internet`, `translation_not_configured`,
`translation_unavailable`, `file_skipped`.

## The Flutter app (`flutter_app/lib`)

```
lib/
├── main.dart                     runApp(const IlokoStyleApp())  (unchanged)
├── app_config.dart               engine URL + token (set with --dart-define)
├── api/ilocoadal_client.dart     talks to the server
├── state/app_controller.dart     every button calls one method here
├── theme/app_theme.dart          colors sampled from the Figma, fonts
└── screens/
    ├── ilokostyle.dart           IlokoStyleApp + AppRoot (picks the screen from the state)
    ├── upload_screen.dart        Figma: Upload document
    ├── ready_screen.dart         Figma: Ready to Process
    ├── processing_screen.dart    Figma: Processing
    ├── results_screen.dart       Figma: Document Ready (scrollable terms box)
    ├── error_screen.dart         Figma: Error - File / No Text / No Usable Term / No internet
    └── widgets/                  header, buttons, cards, checklist, term card
```

Add to `pubspec.yaml` (needs Flutter 3.10+ / Dart 3):

```
dependencies:
  http: ^1.2.0
  file_picker: ^8.0.0
  path_provider: ^2.1.0
  open_filex: ^4.4.0
```

Remove from the old draft: `db_helper.dart` (an expenses database from another app) and the
`convert_button`, `file_button`, `menu_button`, `more_button` widgets (not in the design), and drop
`sqflite` / `path` from `pubspec.yaml` if nothing else uses them.

Run (server first, from this folder; then the app as a **desktop** target):

```
python server.py --config config.json
flutter run -d windows --dart-define=ILOCOADAL_TOKEN=my-secret      # or macos / linux
```

* The token must equal `server.auth_token` in `config.json` (leave both empty to switch it off).
* **macOS:** add `com.apple.security.network.client` and `com.apple.security.files.user-selected.read-only`
  (set to true) to `macos/Runner/DebugProfile.entitlements` and `Release.entitlements`, or the app can't
  reach the server or read the picked file.
* **Why desktop:** the server reads each file by its path, and a path from a phone's file picker only
  exists on that phone. An emulator or real phone can't be used with a PC server yet.
* **On the phone itself:** the Python server has to ship inside the app and run on the device. A package
  such as `serious_python` is built for this, but **I haven't tried it**: check that it supports your
  target platforms and that `pypdf`, `python-docx` (needs `lxml`, compiled code) and `simplemma` install there.
* Set `server.auth_token` so other apps on the phone can't use the local server, and put the Google
  key in the config file the app writes at startup rather than in the source.
