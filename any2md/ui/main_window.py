"""Main application window."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import Qt, QSize, pyqtSlot
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
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
    OutputFormat,
)
from any2md.conversion.worker import BatchConversionWorker
from any2md.storage.history import HistoryEntry, HistoryStore
from any2md.storage.settings import AppSettings, SettingsStore
from any2md.ui.icons import (
    get_app_icon,
    get_app_logo_path,
    get_settings_icon,
    get_theme_icon,
)
from any2md.ui.style.theme import apply_theme
from any2md.ui.widgets.drop_zone import DropZoneWidget, collect_supported_files
from any2md.ui.widgets.file_list import FileListWidget
from any2md.ui.widgets.recent_files import RecentFilesWidget
from any2md.ui.widgets.settings_panel import SettingsPanel

# Page indices in the stacked widget
PAGE_DROP = 0
PAGE_FILES = 1

# --convert-to values accepted from the CLI / Explorer context menu
_CLI_FORMATS: dict[str, OutputFormat] = {
    "md": OutputFormat.MARKDOWN,
    "markdown": OutputFormat.MARKDOWN,
    "pdf": OutputFormat.PDF,
    "docx": OutputFormat.DOCX,
    "word": OutputFormat.DOCX,
    "html": OutputFormat.HTML,
}


class MainWindow(QMainWindow):
    """
    Application shell.

    Layout:
        ┌─────────────────────────────────────┐
        │  Header bar (title + controls)      │
        ├─────────────────────────────────────┤
        │  Central stacked widget             │
        │   Page 0: Drop zone                 │
        │   Page 1: Queue — one row per file, │
        │           live progress + results   │
        ├─────────────────────────────────────┤
        │  Recent files (collapsible)         │
        ├─────────────────────────────────────┤
        │  Footer — privacy note              │
        └─────────────────────────────────────┘
        [Settings panel overlaid on right side]

    Files can arrive at any time — dropped on the window, picked in a dialog,
    or forwarded from further Explorer launches — and all of them land in the
    same queue. Requests made while a batch is running join that batch.
    """

    def __init__(self) -> None:
        super().__init__()
        self._engine = ConversionEngine()
        self._settings_store = SettingsStore()
        self._settings = self._settings_store.load()
        self._history = HistoryStore()
        self._worker: Optional[BatchConversionWorker] = None
        self._backlog: list[ConversionRequest] = []  # submitted while a worker was wrapping up
        self._current_name = ""
        self._counts = (0, 0)  # (completed, total) of the running batch

        self.setWindowTitle("Any2MD")
        self.resize(self._settings.window_width, self._settings.window_height)
        self.setMinimumSize(760, 520)
        self.setAcceptDrops(True)

        self._build_ui()
        self._setup_shortcuts()
        self._file_list.apply_settings(self._settings)

        # Set window icon / favicon
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

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
        main_layout.addWidget(self._build_header())

        # Central stacked widget
        self._stack = QStackedWidget()

        # Page 0: Drop zone
        self._stack.addWidget(self._build_drop_page())

        # Page 1: Queue
        self._file_list = FileListWidget()
        self._file_list.convert_requested.connect(self._submit)
        self._file_list.cancel_requested.connect(self._cancel)
        self._file_list.clear_requested.connect(lambda: self._show_page(PAGE_DROP))
        self._file_list.add_more_requested.connect(self._open_add_more)
        self._stack.addWidget(self._file_list)

        self._stack.setCurrentIndex(PAGE_DROP)
        main_layout.addWidget(self._stack, 1)

        # Recent files
        self._recent_files = RecentFilesWidget(self._history)
        main_layout.addWidget(self._recent_files, 0)

        # Footer
        main_layout.addWidget(self._build_footer())

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

        # App logo + title
        logo_path = get_app_logo_path()
        if logo_path.exists():
            logo_label = QLabel()
            logo_label.setObjectName("appLogo")
            pm = QPixmap(str(logo_path)).scaled(
                24, 24,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_label.setPixmap(pm)
            logo_label.setFixedSize(24, 24)
            layout.addWidget(logo_label)

        # App title
        title = QLabel("Any2MD")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        layout.addStretch()

        # Theme toggle button
        self._theme_btn = QToolButton()
        self._theme_btn.setObjectName("headerThemeBtn")
        self._theme_btn.setToolTip("Toggle theme")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setIconSize(QSize(20, 20))
        self._theme_btn.setIcon(get_theme_icon(self._settings.theme))
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._cycle_theme)
        layout.addWidget(self._theme_btn)

        # Settings button
        self._settings_btn = QToolButton()
        self._settings_btn.setObjectName("headerSettingsBtn")
        self._settings_btn.setToolTip("Settings  (Ctrl+,)")
        self._settings_btn.setFixedSize(36, 36)
        self._settings_btn.setIconSize(QSize(20, 20))
        self._settings_btn.setIcon(get_settings_icon(self._settings.theme))
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self._toggle_settings)
        layout.addWidget(self._settings_btn)

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

        hint = QLabel("Ctrl+O  add files   ·   Ctrl+Enter  convert   ·   Esc  cancel")
        hint.setObjectName("footerPrivacyNote")
        layout.addWidget(hint)

        return footer

    # ──────────────────────────────────────────────────
    # Keyboard shortcuts
    # ──────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        def add(name: str, keys: list[str], slot) -> None:
            action = QAction(name, self)
            action.setShortcuts([QKeySequence(k) for k in keys])
            action.triggered.connect(slot)
            self.addAction(action)

        add("Open files", ["Ctrl+O"], self._open_add_more)
        add("Settings", ["Ctrl+,"], self._toggle_settings)
        add("Convert", ["Ctrl+Return", "Ctrl+Enter"], self._convert_shortcut)
        add("Escape", ["Escape"], self._on_escape)

    # ──────────────────────────────────────────────────
    # Adding files
    # ──────────────────────────────────────────────────

    @pyqtSlot(list)
    def _on_files_dropped(self, paths: list[Path]) -> None:
        self.add_files(paths)

    def _open_add_more(self) -> None:
        """Open file dialog to add more files to the queue."""
        self._drop_zone._open_file_dialog()

    def add_files(
        self,
        paths: Iterable[Path | str],
        convert_to: Optional[OutputFormat] = None,
    ) -> list[str]:
        """Add files (folders are expanded) to the queue; optionally convert them right away."""
        files = collect_supported_files(Path(p) for p in paths)
        if not files:
            return []
        ids = self._file_list.add_files(files, convert_to)
        self._show_page(PAGE_FILES)
        if convert_to is not None:
            self._submit(self._file_list.build_requests(ids))
        return ids

    # ──────────────────────────────────────────────────
    # Window-wide drag and drop
    # ──────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if collect_supported_files(Path(u.toLocalFile()) for u in urls if u.isLocalFile()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if self.add_files(paths):
            event.acceptProposedAction()

    # ──────────────────────────────────────────────────
    # Conversion
    # ──────────────────────────────────────────────────

    @pyqtSlot(list)
    def _submit(self, requests: list[ConversionRequest]) -> None:
        """Run requests — joining the active batch when there is one."""
        if not requests:
            return
        if self._worker is not None:
            if not self._worker.enqueue(requests):
                # The worker is wrapping up; start these once it has finished.
                self._backlog.extend(requests)
            return
        self._start_worker(requests)

    def _start_worker(self, requests: list[ConversionRequest]) -> None:
        self._file_list.set_converting(True)
        self._current_name = ""

        self._worker = BatchConversionWorker(self._engine, requests)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.file_error.connect(self._on_file_error)
        self._worker.batch_progress.connect(self._on_batch_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._counts = (0, len(requests))
        self._file_list.set_batch_progress(0, len(requests))
        self._update_title(0, len(requests))
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._file_list.show_cancelling()
        for req in self._backlog:
            if item := self._file_list.item(req.request_id):
                item.mark_cancelled()
        self._backlog.clear()

    def _convert_shortcut(self) -> None:
        if self._stack.currentIndex() == PAGE_FILES and self._file_list.has_pending():
            self._submit(self._file_list.build_requests())

    @pyqtSlot(str)
    def _on_file_started(self, request_id: str) -> None:
        self._file_list.mark_item_started(request_id)
        item = self._file_list.item(request_id)
        self._current_name = item.path.name if item else ""
        completed, _ = self._counts
        total = len(self._worker.pending_request_ids()) + completed + 1 if self._worker else 0
        total = max(total, self._counts[1])
        self._counts = (completed, total)
        self._file_list.set_batch_progress(completed, total, self._current_name)
        self._update_title(completed, total)

    @pyqtSlot(ConversionProgress)
    def _on_file_progress(self, progress: ConversionProgress) -> None:
        self._file_list.update_item_progress(progress)

    @pyqtSlot(int, int)
    def _on_batch_progress(self, completed: int, total: int) -> None:
        self._counts = (completed, total)
        self._file_list.set_batch_progress(completed, total, self._current_name)
        self._update_title(completed, total)

    @pyqtSlot(ConversionResult)
    def _on_file_finished(self, result: ConversionResult) -> None:
        self._file_list.mark_item_done(result.request.request_id, result)

        req = result.request
        self._history.add(
            HistoryEntry(
                entry_id=str(uuid.uuid4()),
                input_filename=req.input_path.name,
                input_path=str(req.input_path),
                output_path=str(result.output_path),
                direction=f"{req.input_extension.upper().lstrip('.')} → {req.output_format.display_name}",
                status="done",
                timestamp=datetime.datetime.now().isoformat(),
            )
        )
        self._recent_files.refresh()

    @pyqtSlot(ConversionError)
    def _on_file_error(self, error: ConversionError) -> None:
        self._file_list.mark_item_error(error.request.request_id, error)

        req = error.request
        self._history.add(
            HistoryEntry(
                entry_id=str(uuid.uuid4()),
                input_filename=req.input_path.name,
                input_path=str(req.input_path),
                output_path="",
                direction=f"{req.input_extension.upper().lstrip('.')} → {req.output_format.display_name}",
                status="error",
                timestamp=datetime.datetime.now().isoformat(),
                error_message=error.user_message,
            )
        )
        self._recent_files.refresh()

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            if worker.is_cancelled:
                self._file_list.mark_unfinished_cancelled()
            worker.deleteLater()

        if self._backlog:
            backlog, self._backlog = self._backlog, []
            self._start_worker(backlog)
            return

        self._file_list.set_converting(False)
        self.setWindowTitle("Any2MD")
        if not self.isActiveWindow():
            QApplication.alert(self)  # flash the taskbar entry

    def _update_title(self, completed: int, total: int) -> None:
        self.setWindowTitle(f"Any2MD — converting {min(completed + 1, total)} of {total}")

    # ──────────────────────────────────────────────────
    # Slot: Navigation
    # ──────────────────────────────────────────────────

    def _show_page(self, index: int) -> None:
        if index != self._stack.currentIndex():
            # The queue needs the room; history is one click away when wanted.
            self._recent_files.set_expanded(index == PAGE_DROP)
        self._stack.setCurrentIndex(index)

    def _on_escape(self) -> None:
        """Escape: close settings, else cancel a running batch, else clear the queue."""
        if self._settings_panel.isVisible():
            self._toggle_settings()
        elif self._worker is not None:
            self._cancel()
        elif self._stack.currentIndex() == PAGE_FILES:
            self._file_list.clear_all()
            self._show_page(PAGE_DROP)

    # ──────────────────────────────────────────────────
    # Slot: Settings
    # ──────────────────────────────────────────────────

    def _toggle_settings(self) -> None:
        visible = self._settings_panel.isVisible()
        self._settings_panel.setVisible(not visible)

    def _update_header_icons(self) -> None:
        """Update header buttons with theme-matching icons."""
        theme = self._settings.theme
        self._theme_btn.setIcon(get_theme_icon(theme))
        self._settings_btn.setIcon(get_settings_icon(theme))

    @pyqtSlot(object)
    def _on_settings_changed(self, settings: AppSettings) -> None:
        settings.window_width = self._settings.window_width
        settings.window_height = self._settings.window_height
        output_dir_changed = settings.default_output_dir != self._settings.default_output_dir
        self._settings = settings
        self._settings_store.save(settings)
        # Re-apply theme
        apply_theme(QApplication.instance(), settings.theme)
        self._update_header_icons()
        self._file_list.apply_settings(settings)
        if output_dir_changed and not settings.default_output_dir:
            self._file_list.set_output_dir(None)

    def _cycle_theme(self) -> None:
        themes = ["light", "dark", "system"]
        current = self._settings.theme
        next_theme = themes[(themes.index(current) + 1) % len(themes)]
        self._settings.theme = next_theme
        self._settings_store.save(self._settings)
        apply_theme(QApplication.instance(), next_theme)
        self._update_header_icons()
        self._settings_panel.update_theme_selection(next_theme)

    # ──────────────────────────────────────────────────
    # CLI / Explorer Context Menu handling
    # ──────────────────────────────────────────────────

    def handle_cli_args(self, files: list[str], convert_to: Optional[str] = None) -> None:
        """Handle files and conversion format passed via CLI / Explorer context menu."""
        target = _CLI_FORMATS.get(convert_to.lower()) if convert_to else None
        self.add_files(files, target)

    def handle_external_request(self, files: list[str], convert_to: Optional[str] = None) -> None:
        """Files forwarded by another Any2MD launch (e.g. multi-select in Explorer)."""
        self.handle_cli_args(files, convert_to)
        self.bring_to_front()

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

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
            self._worker.wait(5000)

        super().closeEvent(event)
