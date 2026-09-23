"""Any2MD application entry point."""

from __future__ import annotations

import argparse
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from any2md.ui.icons import get_app_icon
from any2md.ui.main_window import MainWindow
from any2md.ui.style.theme import apply_theme
from any2md.storage.settings import SettingsStore


def main() -> None:
    # Set Windows AppUserModelID so taskbar groups properly and displays the icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("any2md.desktop.app")
        except Exception:
            pass

    # Parse CLI arguments (e.g. from Explorer right-click context menu or file associations)
    parser = argparse.ArgumentParser(description="Any2MD document conversion.")
    parser.add_argument(
        "--convert-to",
        choices=["md", "markdown", "pdf", "docx", "word", "html"],
        help="Directly convert input file(s) to this target format and show result",
    )
    parser.add_argument("files", nargs="*", help="Files to open or convert")
    args, unknown = parser.parse_known_args()

    # High-DPI support (works at 100% and 125% Windows scaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Any2MD")
    app.setOrganizationName("Any2MD")
    app.setApplicationVersion("0.1.0")

    # Set favicon / window icon for taskbar and titlebar
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Load and apply saved theme
    store = SettingsStore()
    settings = store.load()
    apply_theme(app, settings.theme)

    window = MainWindow()
    window.show()

    # Handle files passed via CLI or Windows Explorer context menu
    if args.files:
        window.handle_cli_args(args.files, args.convert_to)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
