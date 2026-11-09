"""Installed application entry point."""
import os
import runpy
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    os.environ.setdefault("STUDIO_DATA", str(Path.home() / ".video-studio"))
    os.environ.setdefault("STUDIO_PYTHON", sys.executable)
    runpy.run_path(str(root / "launch.py"), run_name="__main__")
