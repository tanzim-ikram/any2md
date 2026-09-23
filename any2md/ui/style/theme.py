"""Theme manager — detects system theme and applies QSS stylesheets."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

_STYLE_DIR = Path(__file__).parent


def _is_system_dark() -> bool:
    """Check Windows 10/11 registry for dark mode preference."""
    try:
        qs = QSettings(
            r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            QSettings.Format.NativeFormat,
        )
        # AppsUseLightTheme: 0 = dark, 1 = light
        value = qs.value("AppsUseLightTheme", 1, type=int)
        return value == 0
    except Exception:
        return False


def load_stylesheet(theme: str) -> str:
    """Return QSS content for the given theme ('light', 'dark', 'system')."""
    if theme == "system":
        theme = "dark" if _is_system_dark() else "light"
    path = _STYLE_DIR / f"{theme}.qss"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def apply_theme(app: QApplication, theme: str) -> str:
    """Apply the QSS theme to the QApplication. Returns the resolved theme name."""
    resolved = theme
    if theme == "system":
        resolved = "dark" if _is_system_dark() else "light"
    qss = load_stylesheet(resolved)
    app.setStyleSheet(qss)
    return resolved
