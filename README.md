# IlocoAdal

IlocoAdal finds the key terms in your PDF documents, adds a definition and example sentences for each term, translates both into Ilocano, and gives you a downloadable Word document (`.docx`).

## How it works

1. Upload one or more PDFs.
2. The app extracts and cleans the text.
3. TF-IDF ranks the terms (words and short phrases of up to 3 words).
4. It finds the sentences where each term appears.
5. It gets definitions from the [Free Dictionary API](https://dictionaryapi.dev/).
6. It translates the sentences and definitions with the Google Cloud Translation API.
7. You choose where to save the finished document.

You can choose how many key terms to find (10 to 40, default 15). With several files, the terms are ranked together and saved in one combined document.

## What's inside

| Part                       | What it does                                                                                                      |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Flutter app (`lib/`)       | The screens: upload, ready to process, processing, results and error screens                                      |
| Python engine (`backend/`) | Does all the processing: reading PDFs, ranking terms, fetching definitions, translating and building the document |

The engine runs as a small local server on the device, and the app talks to it. On Android it runs inside the app itself.

## Notes

- Definitions and translations need an internet connection. If the connection is lost, you can try again or continue without them.
- Translation needs a Google Cloud Translation API key. Without one, the app still works and leaves the translations out.

## Known limitations

- PDF only. Scanned pages (images) are not supported.
- English text only.
- The Free Dictionary API has no entry for most phrases, so those show "Definition not available".
