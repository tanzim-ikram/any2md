"""Cross-platform helpers for opening converted files and their folders."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def open_path(path: Path) -> bool:
    """Open a file or folder with the user's default application."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal_in_folder(path: Path) -> bool:
    """Show the file selected in the system file manager (falls back to its folder)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return True
    except OSError:
        pass
    return open_path(path.parent)
