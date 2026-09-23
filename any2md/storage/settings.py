"""App settings — persisted via QSettings (Windows Registry)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings


APP_ORG = "Any2MD"
APP_NAME = "Any2MD"


@dataclass
class AppSettings:
    theme: str = "system"          # "system" | "light" | "dark"
    default_output_dir: str = ""   # "" = same as source
    default_format: str = "markdown"
    preserve_images: bool = False
    start_with_windows: bool = False
    window_width: int = 900
    window_height: int = 640


class SettingsStore:
    """Reads and writes AppSettings via QSettings (HKCU registry on Windows)."""

    def __init__(self) -> None:
        self._qs = QSettings(APP_ORG, APP_NAME)

    def load(self) -> AppSettings:
        s = AppSettings()
        s.theme = self._qs.value("theme", s.theme, type=str)
        s.default_output_dir = self._qs.value("default_output_dir", s.default_output_dir, type=str)
        s.default_format = self._qs.value("default_format", s.default_format, type=str)
        s.preserve_images = self._qs.value("preserve_images", s.preserve_images, type=bool)
        s.start_with_windows = self._qs.value("start_with_windows", s.start_with_windows, type=bool)
        s.window_width = self._qs.value("window_width", s.window_width, type=int)
        s.window_height = self._qs.value("window_height", s.window_height, type=int)
        return s

    def save(self, settings: AppSettings) -> None:
        self._qs.setValue("theme", settings.theme)
        self._qs.setValue("default_output_dir", settings.default_output_dir)
        self._qs.setValue("default_format", settings.default_format)
        self._qs.setValue("preserve_images", settings.preserve_images)
        self._qs.setValue("start_with_windows", settings.start_with_windows)
        self._qs.setValue("window_width", settings.window_width)
        self._qs.setValue("window_height", settings.window_height)
        self._qs.sync()
