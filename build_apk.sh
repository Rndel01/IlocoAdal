#!/usr/bin/env bash
# Builds (or runs) the app with the Python engine packed inside it.
#
# Put this file in the ROOT of the Flutter project (next to pubspec.yaml) and run:
#     bash build_apk.sh              -> builds the release APK
#     bash build_apk.sh run          -> runs on the connected phone (debug)
#
# Needs: the `python_app` folder (main.py, requirements.txt) and the engine code
# in `backend/ilocoadal` (this script copies it into python_app for you).
set -euo pipefail

# Which Python to bundle. 3.12 has the most ready-made Android packages.
export SERIOUS_PYTHON_VERSION=3.12
export SERIOUS_PYTHON_SITE_PACKAGES="$(pwd)/build/py_site_packages"
export SERIOUS_PYTHON_APP="$(pwd)/build/py_app"
# python-docx and simplemma open their data files by path, which can't work
# from inside a zip, so they are unpacked to disk when the app first starts.
export SERIOUS_PYTHON_ANDROID_EXTRACT_PACKAGES="docx,simplemma,certifi"

echo "==> Copying the engine into python_app/"
rm -rf python_app/ilocoadal
cp -r backend/ilocoadal python_app/ilocoadal
find python_app -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Packaging Python for Android (downloads packages; needs internet)"
flutter pub get
rm -rf build/py_site_packages build/py_app
dart run serious_python:main package python_app -p Android -r -r -r python_app/requirements.txt

echo "==> flutter ${*:-build apk --release}"
flutter ${*:-build apk --release}
