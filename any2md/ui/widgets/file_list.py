"""File queue — every file is a row that shows its own progress and result."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import (
    ConversionError,
    ConversionOptions,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
    OutputFormat,
)
from any2md.storage.settings import AppSettings
from any2md.ui.file_actions import open_path
from .file_item import FileItemWidget, ItemState

_FORMAT_OPTIONS = [
    ("Markdown (.md)", OutputFormat.MARKDOWN),
    ("PDF (.pdf)",     OutputFormat.PDF),
    ("Word (.docx)",   OutputFormat.DOCX),
    ("HTML (.html)",   OutputFormat.HTML),
]

# States a row can be (re)submitted from.
_SUBMITTABLE = (ItemState.READY, ItemState.CANCELLED)
_BUSY = (ItemState.QUEUED, ItemState.CONVERTING)


def effective_format(path: Path, fmt: OutputFormat) -> OutputFormat:
    """Markdown can't be converted to Markdown — fall back to PDF for .md files."""
    if path.suffix.lower() == ".md" and fmt == OutputFormat.MARKDOWN:
        return OutputFormat.PDF
    return fmt


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FileListWidget(QWidget):
    """
    The conversion queue: options, a row per file, and a batch status strip.

    Emits:
        convert_requested(list[ConversionRequest])
        cancel_requested()
        clear_requested()     — the list became empty
        add_more_requested()
    """

    convert_requested = pyqtSignal(list)   # list[ConversionRequest]
    cancel_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    add_more_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: Dict[str, FileItemWidget] = {}  # request_id → widget
        self._output_dir: Path | None = None
        self._preserve_images = True
        self._running = False
        self._cancelling = False
        self._build_ui()
        self.set_output_dir(None)
        self._refresh()

    @property
    def file_count(self) -> int:
        """Return the current number of files in the queue."""
        return len(self._items)

    # ──────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Options bar ──────────────────────────────
        opts = QWidget()
        opts.setObjectName("toolbarPanel")
        opts.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        opts_layout = QHBoxLayout(opts)
        opts_layout.setContentsMargins(18, 10, 18, 10)
        opts_layout.setSpacing(10)

        fmt_label = QLabel("Convert to")
        fmt_label.setObjectName("mutedLabel")
        opts_layout.addWidget(fmt_label)

        self._format_combo = QComboBox()
        self._format_combo.setView(QListView())
        self._format_combo.setToolTip("Target format for files that haven't been converted yet")
        for display, fmt in _FORMAT_OPTIONS:
            self._format_combo.addItem(display, fmt)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        opts_layout.addWidget(self._format_combo)

        opts_layout.addSpacing(10)

        out_label = QLabel("Save to")
        out_label.setObjectName("mutedLabel")
        opts_layout.addWidget(out_label)

        self._out_dir_btn = QPushButton("Same folder as source")
        self._out_dir_btn.setObjectName("folderPickerButton")
        self._out_dir_btn.setToolTip("Choose where converted files are saved")
        self._out_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._out_dir_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._out_dir_btn.setMaximumWidth(260)
        self._out_dir_btn.clicked.connect(self._pick_output_dir)
        opts_layout.addWidget(self._out_dir_btn)

        self._reset_dir_btn = QPushButton("Reset")
        self._reset_dir_btn.setObjectName("linkButton")
        self._reset_dir_btn.setToolTip("Save next to each source file")
        self._reset_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_dir_btn.clicked.connect(lambda: self.set_output_dir(None))
        opts_layout.addWidget(self._reset_dir_btn)

        opts_layout.addStretch()

        self._clear_btn = QPushButton("Clear all")
        self._clear_btn.setObjectName("linkButton")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._on_clear)
        opts_layout.addWidget(self._clear_btn)

        root.addWidget(opts)

        # ── Batch status strip ───────────────────────
        self._status_strip = QWidget()
        self._status_strip.setObjectName("statusStrip")
        self._status_strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip = QVBoxLayout(self._status_strip)
        strip.setContentsMargins(18, 10, 18, 10)
        strip.setSpacing(8)

        strip_row = QHBoxLayout()
        strip_row.setSpacing(10)
        self._status_label = QLabel()
        self._status_label.setObjectName("statusLabel")
        self._status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        strip_row.addWidget(self._status_label, 1)

        self._retry_btn = QPushButton("Retry failed")
        self._retry_btn.setObjectName("linkButton")
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.clicked.connect(self._retry_failed)
        strip_row.addWidget(self._retry_btn)

        self._clear_done_btn = QPushButton("Clear finished")
        self._clear_done_btn.setObjectName("linkButton")
        self._clear_done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_done_btn.clicked.connect(self._clear_finished)
        strip_row.addWidget(self._clear_done_btn)

        self._open_folder_btn = QPushButton("Open folder")
        self._open_folder_btn.setObjectName("linkButton")
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        strip_row.addWidget(self._open_folder_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setToolTip("Stop after the current file  (Esc)")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        strip_row.addWidget(self._cancel_btn)
        strip.addLayout(strip_row)

        self._overall_progress = QProgressBar()
        self._overall_progress.setObjectName("overallProgress")
        self._overall_progress.setTextVisible(False)
        self._overall_progress.setFixedHeight(4)
        strip.addWidget(self._overall_progress)

        root.addWidget(self._status_strip)

        # ── File list (scrollable) ───────────────────
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_container.setObjectName("listContainer")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(16, 12, 16, 12)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()

        self._scroll_area.setWidget(self._list_container)
        root.addWidget(self._scroll_area, 1)

        # ── Action bar ───────────────────────────────
        action_bar = QWidget()
        action_bar.setObjectName("actionBar")
        action_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(18, 12, 18, 12)
        action_layout.setSpacing(10)

        add_more_btn = QPushButton("+  Add files")
        add_more_btn.setToolTip("Add more files  (Ctrl+O) — or drop them anywhere on this window")
        add_more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_more_btn.clicked.connect(self.add_more_requested.emit)
        action_layout.addWidget(add_more_btn)

        action_layout.addStretch()

        self._file_count_label = QLabel("")
        self._file_count_label.setObjectName("mutedLabel")
        action_layout.addWidget(self._file_count_label)

        self._convert_btn = QPushButton("Convert")
        self._convert_btn.setObjectName("primaryButton")
        self._convert_btn.setMinimumWidth(140)
        self._convert_btn.setToolTip("Convert  (Ctrl+Enter)")
        self._convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._convert_btn.clicked.connect(self._on_convert)
        action_layout.addWidget(self._convert_btn)

        root.addWidget(action_bar)

    # ──────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────

    def apply_settings(self, settings: AppSettings) -> None:
        """Pick up defaults (format, output folder, image handling) from settings."""
        self._preserve_images = settings.preserve_images
        if settings.default_output_dir:
            self.set_output_dir(Path(settings.default_output_dir))
        try:
            fmt = OutputFormat(settings.default_format)
        except ValueError:
            fmt = OutputFormat.MARKDOWN
        if self.is_empty():
            self.set_format(fmt)

    def set_format(self, fmt: OutputFormat) -> None:
        idx = self._format_combo.findData(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

    def current_format(self) -> OutputFormat:
        return self._format_combo.currentData()

    def set_output_dir(self, folder: Optional[Path]) -> None:
        self._output_dir = folder
        if folder is None:
            self._out_dir_btn.setText("Same folder as source")
            self._out_dir_btn.setToolTip("Converted files are saved next to each source file")
        else:
            text = str(folder)
            metrics = self._out_dir_btn.fontMetrics()
            self._out_dir_btn.setText(metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, 200))
            self._out_dir_btn.setToolTip(text)
        self._reset_dir_btn.setVisible(folder is not None)

    def add_files(
        self, paths: Iterable[Path], output_format: Optional[OutputFormat] = None
    ) -> list[str]:
        """
        Add files to the queue, deduplicating by resolved path.

        Returns the request ids of the rows for these paths that are ready to
        convert. A path already in the list is reused: if it is not busy it is
        reset to Ready (with `output_format`, when given) so it can run again.
        """
        by_path = {self._key(item.path): item for item in self._items.values()}
        ids: list[str] = []
        for path in paths:
            fmt = effective_format(path, output_format or self.current_format())
            existing = by_path.get(self._key(path))
            if existing is not None:
                if existing.state in _BUSY:
                    continue
                if output_format is not None or existing.state not in _SUBMITTABLE:
                    existing.set_output_format(fmt)
                    existing.mark_ready()
                ids.append(existing.request_id)
                continue

            request_id = str(uuid.uuid4())
            item = FileItemWidget(request_id, path, fmt)
            item.remove_requested.connect(self._remove_item)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
            self._items[request_id] = item
            by_path[self._key(path)] = item
            ids.append(request_id)

        self._refresh()
        if ids:
            last = self._items[ids[-1]]
            self._scroll_area.ensureWidgetVisible(last)
        return ids

    def build_requests(self, request_ids: Optional[Iterable[str]] = None) -> list[ConversionRequest]:
        """Create requests for the given (or all ready) rows and mark them queued."""
        if request_ids is None:
            request_ids = [rid for rid, it in self._items.items() if it.state in _SUBMITTABLE]
        requests: list[ConversionRequest] = []
        for rid in request_ids:
            item = self._items.get(rid)
            if item is None or item.state not in _SUBMITTABLE:
                continue
            requests.append(
                ConversionRequest(
                    input_path=item.path,
                    output_format=item.output_format,
                    output_dir=self._output_dir,
                    options=ConversionOptions(preserve_images=self._preserve_images),
                    request_id=rid,
                )
            )
            item.mark_waiting()
        self._refresh()
        return requests

    def clear_all(self) -> None:
        for rid in [rid for rid, it in self._items.items() if it.state not in _BUSY]:
            self._drop_item(rid)
        self._refresh()

    def item(self, request_id: str) -> Optional[FileItemWidget]:
        return self._items.get(request_id)

    def items(self) -> list[FileItemWidget]:
        return list(self._items.values())

    def mark_item_started(self, request_id: str) -> None:
        if item := self._items.get(request_id):
            item.mark_started()
            self._scroll_area.ensureWidgetVisible(item)

    def update_item_progress(self, progress: ConversionProgress) -> None:
        if item := self._items.get(progress.request_id):
            item.update_progress(progress)

    def mark_item_done(self, request_id: str, result: Optional[ConversionResult] = None) -> None:
        if item := self._items.get(request_id):
            item.mark_done(result)
        self._refresh()

    def mark_item_error(self, request_id: str, error: Optional[ConversionError] = None) -> None:
        if item := self._items.get(request_id):
            item.mark_error(error)
        self._refresh()

    def mark_unfinished_cancelled(self) -> None:
        for item in self._items.values():
            if item.state in _BUSY:
                item.mark_cancelled()
        self._refresh()

    def set_converting(self, converting: bool) -> None:
        self._running = converting
        self._cancelling = False
        self._cancel_btn.setEnabled(True)
        if converting:
            self._overall_progress.setValue(0)
        self._refresh()

    def show_cancelling(self) -> None:
        if not self._running:
            return
        self._cancelling = True
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("Stopping after the current file…")

    def set_batch_progress(self, completed: int, total: int, current: str = "") -> None:
        self._overall_progress.setRange(0, max(total, 1))
        self._overall_progress.setValue(completed)
        if self._running and not self._cancelling:
            step = min(completed + 1, total)
            text = f"Converting {step} of {total}"
            if current:
                text += f"  ·  {current}"
            self._status_label.setText(text)

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def has_pending(self) -> bool:
        return any(it.state in _SUBMITTABLE for it in self._items.values())

    # ──────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────

    @staticmethod
    def _key(path: Path) -> str:
        try:
            return str(path.resolve()).lower()
        except OSError:
            return str(path).lower()

    def _pick_output_dir(self) -> None:
        start = str(self._output_dir or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if folder:
            self.set_output_dir(Path(folder))

    def _drop_item(self, request_id: str) -> None:
        if item := self._items.pop(request_id, None):
            item.setParent(None)
            item.deleteLater()

    def _remove_item(self, request_id: str) -> None:
        item = self._items.get(request_id)
        if item is None or item.state in _BUSY:
            return
        self._drop_item(request_id)
        self._refresh()
        if self.is_empty():
            self.clear_requested.emit()

    def _on_format_changed(self) -> None:
        fmt = self.current_format()
        for item in self._items.values():
            if item.state in _BUSY:
                continue
            item.set_output_format(effective_format(item.path, fmt))
            if item.state not in _SUBMITTABLE:
                item.mark_ready()  # picking a new target means "convert again"
        self._refresh()

    def _on_clear(self) -> None:
        self.clear_all()
        if self.is_empty():
            self.clear_requested.emit()

    def _clear_finished(self) -> None:
        for rid in [rid for rid, it in self._items.items() if it.state == ItemState.DONE]:
            self._drop_item(rid)
        self._refresh()
        if self.is_empty():
            self.clear_requested.emit()

    def _retry_failed(self) -> None:
        ids = [rid for rid, it in self._items.items() if it.state == ItemState.ERROR]
        for rid in ids:
            self._items[rid].mark_ready()
        requests = self.build_requests(ids)
        if requests:
            self.convert_requested.emit(requests)

    def _output_folders(self) -> set[Path]:
        return {
            it.result.output_path.parent
            for it in self._items.values()
            if it.state == ItemState.DONE and it.result is not None
        }

    def _open_output_folder(self) -> None:
        folders = self._output_folders()
        if len(folders) == 1:
            open_path(next(iter(folders)))

    def _on_convert(self) -> None:
        requests = self.build_requests()
        if requests:
            self.convert_requested.emit(requests)

    def _refresh(self) -> None:
        """Sync counts, buttons and the status strip with the rows' states."""
        states = [it.state for it in self._items.values()]
        n = len(states)
        ready = sum(s in _SUBMITTABLE for s in states)
        done = states.count(ItemState.DONE)
        failed = states.count(ItemState.ERROR)
        busy = sum(s in _BUSY for s in states)

        self._file_count_label.setText(_plural(n, "file") if n else "")
        if ready:
            label = "Convert" if ready == n and n == 1 else f"Convert {_plural(ready, 'file')}"
            if self._running:
                label = f"Add {ready} to queue"
            self._convert_btn.setText(label)
            self._convert_btn.setEnabled(True)
        else:
            self._convert_btn.setText("Converting…" if self._running else "Convert")
            self._convert_btn.setEnabled(False)
        self._clear_btn.setEnabled(n > busy)

        # Status strip: live progress while running, summary afterwards.
        self._cancel_btn.setVisible(self._running)
        self._overall_progress.setVisible(self._running)
        finished_any = (done or failed) and not self._running
        self._retry_btn.setVisible(bool(finished_any and failed))
        self._clear_done_btn.setVisible(bool(finished_any and done))
        self._open_folder_btn.setVisible(bool(finished_any and len(self._output_folders()) == 1))

        if self._running:
            self._status_strip.setVisible(True)
            self._status_strip.setProperty("tone", "")
            if not self._cancelling and not self._status_label.text().startswith("Converting"):
                self._status_label.setText("Converting…")
        elif finished_any:
            self._status_strip.setVisible(True)
            parts = []
            if done:
                parts.append(f"✓  {_plural(done, 'file')} converted")
            if failed:
                parts.append(f"{failed} failed")
            if ready:
                parts.append(f"{ready} ready")
            self._status_label.setText("   ·   ".join(parts))
            self._status_strip.setProperty("tone", "error" if failed and not done else ("warning" if failed else "success"))
        else:
            self._status_strip.setVisible(False)
        _repolish(self._status_strip)
        _repolish(self._status_label)
