"""Any2MD application entry point."""

from __future__ import annotations

import argparse
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from any2md.platform.single_instance import SingleInstance


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

    # Explorer launches one process per selected file. Only the first becomes
    # the window; the rest hand their files over and exit immediately.
    files = [os.path.abspath(f) for f in args.files]
    instance = SingleInstance()
    if not instance.try_become_primary():
        if instance.send_to_primary({"files": files, "convert_to": args.convert_to}):
            sys.exit(0)
        # Primary is unresponsive: fall back to a standalone window.

    # Heavy UI imports happen only in the process that actually shows a window.
    from any2md.storage.settings import SettingsStore
    from any2md.ui.icons import get_app_icon
    from any2md.ui.main_window import MainWindow
    from any2md.ui.style.theme import apply_theme

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

    instance.message_received.connect(
        lambda msg: window.handle_external_request(msg.get("files") or [], msg.get("convert_to"))
    )

    # Handle files passed via CLI or Windows Explorer context menu
    if files:
        window.handle_cli_args(files, args.convert_to)

    code = app.exec()
    instance.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
