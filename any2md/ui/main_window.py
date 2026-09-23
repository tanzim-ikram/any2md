"""Main application window."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, pyqtSlot
from PyQt6.QtGui import QAction, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.engine import ConversionEngine
from any2md.conversion.models import (
    ConversionError,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
)
from any2md.conversion.worker import BatchConversionWorker
from any2md.storage.history import HistoryEntry, HistoryStore
from any2md.storage.settings import AppSettings, SettingsStore
from any2md.ui.style.theme import apply_theme
from any2md.ui.widgets.drop_zone import DropZoneWidget
from any2md.ui.widgets.file_list import FileListWidget
from any2md.ui.widgets.recent_files import RecentFilesWidget
from any2md.ui.widgets.result_view import ResultView
from any2md.ui.widgets.settings_panel import SettingsPanel
from any2md.ui.dialogs.error_dialog import ErrorDialog

# Page indices in the stacked widget
PAGE_DROP = 0
PAGE_FILES = 1
PAGE_RESULT = 2


class MainWindow(QMainWindow):
    """
    Application shell.

    Layout:
        ┌─────────────────────────────────────┐
        │  Header bar (title + controls)      │
        ├─────────────────────────────────────┤
        │  Central stacked widget             │
        │   Page 0: Drop zone                 │
        │   Page 1: File list + options       │
        │   Page 2: Result view               │
        ├─────────────────────────────────────┤
        │  Recent files (collapsible)         │
        ├─────────────────────────────────────┤
        │  Footer — privacy note              │
        └─────────────────────────────────────┘
        [Settings panel overlaid on right side]
    """

    def __init__(self) -> None:
        super().__init__()
        self._engine = ConversionEngine()
        self._settings_store = SettingsStore()
        self._settings = self._settings_store.load()
        self._history = HistoryStore()
        self._worker: Optional[BatchConversionWorker] = None
        self._pending_results: list[ConversionResult | ConversionError] = []

        self.setWindowTitle("Any2MD")
        self.resize(self._settings.window_width, self._settings.window_height)
        self.setMinimumSize(720, 500)

        self._build_ui()
        self._setup_shortcuts()

    # ──────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Root widget
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Left/main area ──────────────────────────
        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = self._build_header()
        main_layout.addWidget(header)

        # Central stacked widget
        self._stack = QStackedWidget()

        # Page 0: Drop zone
        drop_page = self._build_drop_page()
        self._stack.addWidget(drop_page)

        # Page 1: File list
        self._file_list = FileListWidget()
        self._file_list.convert_requested.connect(self._start_conversion)
        self._file_list.clear_requested.connect(lambda: self._show_page(PAGE_DROP))
        self._file_list.add_more_requested.connect(self._open_add_more)
        self._stack.addWidget(self._file_list)

        # Page 2: Result view
        self._result_view = ResultView()
        self._result_view.convert_more_requested.connect(self._on_convert_more)
        self._stack.addWidget(self._result_view)

        self._stack.setCurrentIndex(PAGE_DROP)
        main_layout.addWidget(self._stack, 1)

        # Recent files
        self._recent_files = RecentFilesWidget(self._history)
        main_layout.addWidget(self._recent_files, 0)

        # Footer
        footer = self._build_footer()
        main_layout.addWidget(footer)

        root_layout.addWidget(main_area)

        # ── Settings panel (hidden by default) ──────
        self._settings_panel = SettingsPanel(self._settings)
        self._settings_panel.settings_changed.connect(self._on_settings_changed)
        self._settings_panel.closed.connect(self._toggle_settings)
        self._settings_panel.setVisible(False)
        root_layout.addWidget(self._settings_panel)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("headerBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(8)

        # App title
        title = QLabel("Any2MD")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        layout.addStretch()

        # Theme toggle button
        self._theme_btn = QToolButton()
        self._theme_btn.setText("◐")
        self._theme_btn.setToolTip("Toggle theme")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setStyleSheet("font-size: 20px; font-weight: bold;")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._cycle_theme)
        layout.addWidget(self._theme_btn)

        # Settings button
        settings_btn = QToolButton()
        settings_btn.setText("⚙")
        settings_btn.setToolTip("Settings  (Ctrl+,)")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setStyleSheet("font-size: 18px;")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._toggle_settings)
        layout.addWidget(settings_btn)

        return header

    def _build_drop_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(0)

        self._drop_zone = DropZoneWidget()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self._drop_zone)

        return page

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 20, 0)

        privacy = QLabel("Your files stay on your computer.")
        privacy.setObjectName("footerPrivacyNote")
        layout.addWidget(privacy)
        layout.addStretch()

        return footer

    # ──────────────────────────────────────────────────
    # Keyboard shortcuts
    # ──────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        open_action = QAction("Open files", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._drop_zone._open_file_dialog)
        self.addAction(open_action)

        settings_action = QAction("Settings", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._toggle_settings)
        self.addAction(settings_action)

        esc_action = QAction("Escape", self)
        esc_action.setShortcut(QKeySequence("Escape"))
        esc_action.triggered.connect(self._on_escape)
        self.addAction(esc_action)

    # ──────────────────────────────────────────────────
    # Slot: Files dropped / selected
    # ──────────────────────────────────────────────────

    @pyqtSlot(list)
    def _on_files_dropped(self, paths: list[Path]) -> None:
        if not paths:
            return
        self._file_list.add_files(paths)
        self._show_page(PAGE_FILES)

    def _open_add_more(self) -> None:
        """Open file dialog to add more files to existing queue."""
        self._drop_zone._open_file_dialog()

    # ──────────────────────────────────────────────────
    # Slot: Conversion
    # ──────────────────────────────────────────────────

    @pyqtSlot(list)
    def _start_conversion(self, requests: list[ConversionRequest]) -> None:
        if not requests or self._worker is not None:
            return

        self._pending_results = []
        self._file_list.set_converting(True)

        self._worker = BatchConversionWorker(self._engine, requests)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.file_error.connect(self._on_file_error)
        self._worker.batch_finished.connect(self._on_batch_finished)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    @pyqtSlot(ConversionProgress)
    def _on_file_progress(self, progress: ConversionProgress) -> None:
        self._file_list.update_item_progress(progress)

    @pyqtSlot(ConversionResult)
    def _on_file_finished(self, result: ConversionResult) -> None:
        self._file_list.mark_item_done(result.request.request_id)
        self._pending_results.append(result)

        # Record in history
        req = result.request
        entry = HistoryEntry(
            entry_id=str(uuid.uuid4()),
            input_filename=req.input_path.name,
            input_path=str(req.input_path),
            output_path=str(result.output_path),
            direction=f"{req.input_extension.upper().lstrip('.')} → {req.output_format.display_name}",
            status="done",
            timestamp=datetime.datetime.now().isoformat(),
        )
        self._history.add(entry)

    @pyqtSlot(ConversionError)
    def _on_file_error(self, error: ConversionError) -> None:
        self._file_list.mark_item_error(error.request.request_id)
        self._pending_results.append(error)

        # Record error in history
        req = error.request
        entry = HistoryEntry(
            entry_id=str(uuid.uuid4()),
            input_filename=req.input_path.name,
            input_path=str(req.input_path),
            output_path="",
            direction=f"{req.input_extension.upper().lstrip('.')} → {req.output_format.display_name}",
            status="error",
            timestamp=datetime.datetime.now().isoformat(),
            error_message=error.user_message,
        )
        self._history.add(entry)

    @pyqtSlot(list)
    def _on_batch_finished(self, results: list) -> None:
        self._file_list.set_converting(False)
        self._recent_files.refresh()
        self._result_view.set_results(self._pending_results)
        self._show_page(PAGE_RESULT)

    def _cleanup_worker(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # ──────────────────────────────────────────────────
    # Slot: Navigation
    # ──────────────────────────────────────────────────

    def _show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _on_convert_more(self) -> None:
        self._file_list.clear_all()
        self._show_page(PAGE_DROP)

    def _on_escape(self) -> None:
        """Escape: close settings if open, else go back a page."""
        if self._settings_panel.isVisible():
            self._toggle_settings()
        elif self._stack.currentIndex() == PAGE_RESULT:
            self._on_convert_more()
        elif self._stack.currentIndex() == PAGE_FILES:
            if self._worker:
                self._worker.cancel()
            else:
                self._file_list.clear_all()
                self._show_page(PAGE_DROP)

    # ──────────────────────────────────────────────────
    # Slot: Settings
    # ──────────────────────────────────────────────────

    def _toggle_settings(self) -> None:
        visible = self._settings_panel.isVisible()
        self._settings_panel.setVisible(not visible)

    @pyqtSlot(object)
    def _on_settings_changed(self, settings: AppSettings) -> None:
        self._settings = settings
        self._settings_store.save(settings)
        # Re-apply theme
        apply_theme(QApplication.instance(), settings.theme)

    def _cycle_theme(self) -> None:
        themes = ["light", "dark", "system"]
        current = self._settings.theme
        next_theme = themes[(themes.index(current) + 1) % len(themes)]
        self._settings.theme = next_theme
        self._settings_store.save(self._settings)
        apply_theme(QApplication.instance(), next_theme)
        self._settings_panel.update_theme_selection(next_theme)

    # ──────────────────────────────────────────────────
    # Window events
    # ──────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        # Save window size
        self._settings.window_width = self.width()
        self._settings.window_height = self.height()
        self._settings_store.save(self._settings)

        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)

        super().closeEvent(event)
