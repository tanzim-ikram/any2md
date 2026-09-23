"""File queue list — shows pending/active/done files and conversion options."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import (
    ConversionOptions,
    ConversionProgress,
    ConversionRequest,
    OutputFormat,
    SUPPORTED_INPUT_FORMATS,
)
from .file_item import FileItemWidget

_FORMAT_OPTIONS = [
    ("Markdown (.md)", OutputFormat.MARKDOWN),
    ("PDF (.pdf)",     OutputFormat.PDF),
    ("Word (.docx)",   OutputFormat.DOCX),
    ("HTML (.html)",   OutputFormat.HTML),
]

# Extension → valid output formats
_FORMAT_ROUTES: dict[str, list[OutputFormat]] = {
    ".md": [OutputFormat.PDF, OutputFormat.DOCX, OutputFormat.HTML],
}
_DEFAULT_NON_MD = [OutputFormat.MARKDOWN]


class FileListWidget(QWidget):
    """
    Shows the file queue with conversion options and a Convert button.

    Emits:
        convert_requested(list[ConversionRequest])
        clear_requested()
        add_more_requested()
    """

    convert_requested = pyqtSignal(list)   # list[ConversionRequest]
    clear_requested = pyqtSignal()
    add_more_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: Dict[str, FileItemWidget] = {}  # request_id → widget
        self._paths: Dict[str, Path] = {}            # request_id → path
        self._output_dir: Path | None = None
        self._build_ui()

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
        opts.setObjectName("surfacePanel")
        opts.setStyleSheet("#surfacePanel { border-radius: 0; border-left: none; border-right: none; border-top: none; }")
        opts_layout = QHBoxLayout(opts)
        opts_layout.setContentsMargins(18, 12, 18, 12)
        opts_layout.setSpacing(12)

        # Format selector
        fmt_label = QLabel("Convert to:")
        fmt_label.setObjectName("mutedLabel")
        opts_layout.addWidget(fmt_label)

        self._format_combo = QComboBox()
        self._format_combo.setView(QListView())
        for display, fmt in _FORMAT_OPTIONS:
            self._format_combo.addItem(display, fmt)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        opts_layout.addWidget(self._format_combo)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedHeight(20)
        sep1.setStyleSheet("color: #e4e4e0;")
        opts_layout.addWidget(sep1)

        # Output folder
        out_label = QLabel("Output folder:")
        out_label.setObjectName("mutedLabel")
        opts_layout.addWidget(out_label)

        self._out_dir_edit = QLineEdit("Same as source")
        self._out_dir_edit.setReadOnly(True)
        self._out_dir_edit.setFixedWidth(190)
        opts_layout.addWidget(self._out_dir_edit)

        change_btn = QPushButton("Change")
        change_btn.setFixedWidth(82)
        change_btn.clicked.connect(self._pick_output_dir)
        opts_layout.addWidget(change_btn)

        opts_layout.addStretch()

        # Clear all link
        self._clear_btn = QPushButton("Clear all")
        self._clear_btn.setObjectName("linkButton")
        self._clear_btn.clicked.connect(self._on_clear)
        opts_layout.addWidget(self._clear_btn)

        root.addWidget(opts)

        # ── File list (scrollable) ───────────────────
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_container.setObjectName("listContainer")
        self._list_container.setStyleSheet("#listContainer { background: transparent; }")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(16, 12, 16, 12)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()

        self._scroll_area.setWidget(self._list_container)
        root.addWidget(self._scroll_area)

        # ── Action bar ───────────────────────────────
        action_bar = QWidget()
        action_bar.setObjectName("surfacePanel")
        action_bar.setStyleSheet(
            "#surfacePanel { border-radius: 0; border-left: none; border-right: none; border-bottom: none; }"
        )
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(18, 14, 18, 14)
        action_layout.setSpacing(10)

        add_more_btn = QPushButton("Add More Files")
        add_more_btn.clicked.connect(self.add_more_requested.emit)
        action_layout.addWidget(add_more_btn)

        action_layout.addStretch()

        self._file_count_label = QLabel("")
        self._file_count_label.setObjectName("mutedLabel")
        action_layout.addWidget(self._file_count_label)

        self._convert_btn = QPushButton("Convert")
        self._convert_btn.setObjectName("primaryButton")
        self._convert_btn.setFixedWidth(120)
        self._convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._convert_btn.clicked.connect(self._on_convert)
        action_layout.addWidget(self._convert_btn)

        root.addWidget(action_bar)

    # ──────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────

    def add_files(self, paths: list[Path]) -> None:
        """Add files to the queue (deduplicates by resolved path)."""
        existing_paths = {p.resolve() for p in self._paths.values()}
        new_paths = [p for p in paths if p.resolve() not in existing_paths]

        output_format = self._current_format()

        for path in new_paths:
            request_id = str(uuid.uuid4())
            self._paths[request_id] = path

            # Auto-detect format for .md files
            fmt = output_format
            if path.suffix.lower() == ".md":
                fmt = OutputFormat.PDF  # Default for md input
                idx = self._format_combo.findData(fmt)
                # Don't change combo — just use PDF for md files by default

            item = FileItemWidget(request_id, path, output_format)
            item.remove_requested.connect(self._remove_item)

            # Insert before the stretch
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
            self._items[request_id] = item

        self._update_count_label()

    def clear_all(self) -> None:
        for item in list(self._items.values()):
            item.setParent(None)
            item.deleteLater()
        self._items.clear()
        self._paths.clear()
        self._update_count_label()

    def update_item_progress(self, progress: ConversionProgress) -> None:
        if item := self._items.get(progress.request_id):
            item.update_progress(progress)

    def mark_item_done(self, request_id: str) -> None:
        if item := self._items.get(request_id):
            item.mark_done()

    def mark_item_error(self, request_id: str) -> None:
        if item := self._items.get(request_id):
            item.mark_error()

    def set_converting(self, converting: bool) -> None:
        self._convert_btn.setEnabled(not converting)
        self._convert_btn.setText("Converting…" if converting else "Convert")

    def is_empty(self) -> bool:
        return len(self._items) == 0

    # ──────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────

    def _current_format(self) -> OutputFormat:
        return self._format_combo.currentData()

    def _pick_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", str(Path.home())
        )
        if folder:
            self._output_dir = Path(folder)
            self._out_dir_edit.setText(folder)

    def _remove_item(self, request_id: str) -> None:
        if item := self._items.pop(request_id, None):
            item.setParent(None)
            item.deleteLater()
        self._paths.pop(request_id, None)
        self._update_count_label()

    def _on_format_changed(self) -> None:
        fmt = self._current_format()
        for item in self._items.values():
            item.set_output_format(fmt)

    def _on_clear(self) -> None:
        self.clear_all()
        self.clear_requested.emit()

    def _on_convert(self) -> None:
        output_format = self._current_format()
        requests: list[ConversionRequest] = []

        for request_id, path in self._paths.items():
            ext = path.suffix.lower()
            # For .md input, use whatever format is selected (unless it's markdown→markdown)
            fmt = output_format
            if ext == ".md" and fmt == OutputFormat.MARKDOWN:
                fmt = OutputFormat.PDF  # sensible default

            req = ConversionRequest(
                input_path=path,
                output_format=fmt,
                output_dir=self._output_dir,
                options=ConversionOptions(),
                request_id=request_id,
            )
            requests.append(req)

            # Mark each item as waiting
            if item := self._items.get(request_id):
                item.mark_waiting()

        if requests:
            self.convert_requested.emit(requests)

    def _update_count_label(self) -> None:
        n = len(self._items)
        if n == 0:
            self._file_count_label.setText("")
        elif n == 1:
            self._file_count_label.setText("1 file")
        else:
            self._file_count_label.setText(f"{n} files")
