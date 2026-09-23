"""Theme manager — detects system theme and applies QSS stylesheets."""

import sys
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def _get_style_dir() -> Path:
    """Return the directory containing QSS stylesheet files."""
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "any2md" / "ui" / "style"
        if candidate.exists():
            return candidate
    return Path(__file__).parent


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


def _build_light_palette() -> QPalette:
    """Build a complete light QPalette to prevent dark system theme leaking into popups."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#f7f7f5"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a18"))
    p.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#f3f3f1"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1a1a18"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Text, QColor("#1a1a18"))
    p.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#1a1a18"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#dbeafe"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#1d4ed8"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#a0a09a"))
    return p


def _build_dark_palette() -> QPalette:
    """Build a complete dark QPalette."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#111110"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#efefec"))
    p.setColor(QPalette.ColorRole.Base, QColor("#1c1c1a"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#222220"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2a2a28"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#efefec"))
    p.setColor(QPalette.ColorRole.Text, QColor("#efefec"))
    p.setColor(QPalette.ColorRole.Button, QColor("#1c1c1a"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#efefec"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#1e3a5f"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#93c5fd"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#63635e"))
    return p


def load_stylesheet(theme: str) -> str:
    """Return QSS content for the given theme ('light', 'dark', 'system')."""
    if theme == "system":
        theme = "dark" if _is_system_dark() else "light"
    path = _get_style_dir() / f"{theme}.qss"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def apply_theme(app: QApplication, theme: str) -> str:
    """Apply the QSS theme and matching QPalette to the QApplication. Returns the resolved theme name."""
    resolved = theme
    if theme == "system":
        resolved = "dark" if _is_system_dark() else "light"

    # Set matching palette to prevent native popups/menus from using mismatched OS palette
    palette = _build_dark_palette() if resolved == "dark" else _build_light_palette()
    app.setPalette(palette)

    qss = load_stylesheet(resolved)
    app.setStyleSheet(qss)
    return resolved
