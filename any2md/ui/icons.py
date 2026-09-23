"""SVG icon rendering utility for Any2MD UI."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from any2md.ui.style.theme import _is_system_dark

GEAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
</svg>"""

THEME_CONTRAST_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="9"/>
  <path d="M12 3a9 9 0 0 1 0 18z" fill="{color}"/>
</svg>"""


def render_svg_icon(svg_template: str, color: str, sizes: tuple[int, ...] = (16, 20, 24, 32, 48)) -> QIcon:
    """Render an SVG template string with the specified stroke/fill color into a multi-resolution QIcon."""
    svg_data = svg_template.format(color=color).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg_data))
    icon = QIcon()
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def get_icon_color(theme: str) -> str:
    """Return matching icon hex color for the given theme ('light', 'dark', 'system')."""
    resolved = theme
    if theme == "system":
        resolved = "dark" if _is_system_dark() else "light"
    return "#a0a09a" if resolved == "dark" else "#71716c"


def get_settings_icon(theme: str) -> QIcon:
    """Return Settings gear icon for the current theme."""
    return render_svg_icon(GEAR_SVG, get_icon_color(theme))


def get_theme_icon(theme: str) -> QIcon:
    """Return Theme contrast circle icon for the current theme."""
    return render_svg_icon(THEME_CONTRAST_SVG, get_icon_color(theme))
