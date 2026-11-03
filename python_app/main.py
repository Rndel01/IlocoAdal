"""Starts the IlocoAdal engine inside the app (run by serious_python on the phone).

The Flutter app writes a config file and passes its path in ILOCOADAL_CONFIG.
This program must keep running (the server blocks), so the engine stays up
for as long as the app is open.
"""
import os
import sys

from ilocoadal.server import main

if __name__ == "__main__":
    config = os.environ.get("ILOCOADAL_CONFIG")
    sys.exit(main(["--config", config] if config else []))
