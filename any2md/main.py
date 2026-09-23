"""Any2MD application entry point."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from any2md.ui.main_window import MainWindow
from any2md.ui.style.theme import apply_theme
from any2md.storage.settings import SettingsStore


def main() -> None:
    # High-DPI support (works at 100% and 125% Windows scaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Any2MD")
    app.setOrganizationName("Any2MD")
    app.setApplicationVersion("0.1.0")

    # Load and apply saved theme
    store = SettingsStore()
    settings = store.load()
    apply_theme(app, settings.theme)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
