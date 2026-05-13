"""Executable spike scripts for audit-eval."""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
SRC_ROOT_PATH = str(SRC_ROOT)
if SRC_ROOT.is_dir() and SRC_ROOT_PATH not in sys.path:
    sys.path.insert(0, SRC_ROOT_PATH)
