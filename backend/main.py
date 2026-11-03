"""Command-line runner for testing the pipeline without the app.

    python main.py report.pdf
    python main.py report.pdf --config config.json -o notes.docx -n 15
    python main.py report.pdf --offline        # skip dictionary + translation
    python main.py a.pdf b.pdf c.pdf           # several documents -> one combined result

Settings come from the config file (see config.json); flags override it.
"""
import argparse
import sys

from ilocoadal.config import Config
from ilocoadal.errors import IlocoAdalError
from ilocoadal.process_manager import ProcessManager
from ilocoadal.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description="IlocoAdal key term extractor")
    parser.add_argument("input", nargs="+", help="path(s) to document(s)")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("-o", "--output", help="output .docx path")
    parser.add_argument("-n", "--terms", type=int, help="key terms to find")
    parser.add_argument("--offline", action="store_true", help="skip the API steps")
    args = parser.parse_args()

    try:
        config = Config.load(args.config)
        if args.terms:
            config.analysis.top_n = args.terms
        config.validate()
    except IlocoAdalError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    user = User(ProcessManager(config, online=not args.offline))
    for path in args.input:
        if not user.upload_document(path):
            return 1
    ok = user.process_document(
        args.output, on_progress=lambda s, t, label: print(f"[{s}/{t}] {label}")
    )
    if not ok:
        return 1
    print(f"Saved: {user.download_document()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
