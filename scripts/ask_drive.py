#!/usr/bin/env python3
"""Backward-compatible launcher for the ``brain-drive`` command."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from api.drive_cli import main  # noqa: E402


if __name__ == "__main__":
    main()
