"""Individual file row widget in the conversion queue."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import (
    ConversionError,
    ConversionProgress,
    ConversionResult,
    ConversionStatus,
    OutputFormat,
)
from any2md.ui.file_actions import open_path, reveal_in_folder

# File-type color accents (subtle, not noisy)
_EXT_COLORS: dict[str, str] = {
    ".pdf":  "#ef4444",
    ".docx": "#2563eb",
    ".xlsx": "#16a34a",
    ".xls":  "#16a34a",
    ".pptx": "#ea580c",
    ".ppt":  "#ea580c",
    ".txt":  "#71716c",
    ".html": "#7c3aed",
    ".htm":  "#7c3aed",
    ".csv":  "#0891b2",
    ".md":   "#64748b",
}

_EXT_LABELS: dict[str, str] = {
    ".pdf":  "PDF",
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".xls":  "XLS",
    ".pptx": "PPTX",
    ".ppt":  "PPT",
    ".txt":  "TXT",
    ".html": "HTML",
    ".htm":  "HTML",
    ".csv":  "CSV",
    ".md":   "MD",
}

_SHORT_FORMAT: dict[OutputFormat, str] = {
    OutputFormat.MARKDOWN: "MD",
    OutputFormat.PDF: "PDF",
    OutputFormat.DOCX: "DOCX",
    OutputFormat.HTML: "HTML",
}


class ItemState(str, Enum):
    READY = "ready"
    QUEUED = "queued"
    CONVERTING = "converting"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


# state → (badge text, badge object name)
_BADGES: dict[ItemState, tuple[str, str]] = {
    ItemState.READY:      ("Ready",      "badgeReady"),
    ItemState.QUEUED:     ("Queued",     "badgeReady"),
    ItemState.CONVERTING: ("Converting", "badgeConverting"),
    ItemState.DONE:       ("Done",       "badgeDone"),
    ItemState.ERROR:      ("Failed",     "badgeError"),
    ItemState.CANCELLED:  ("Cancelled",  "badgeReady"),
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_duration(ms: int) -> str:
    return "<0.1 s" if ms < 100 else f"{ms / 1000:.1f} s"


def _rgba(hex_color: str, alpha: float) -> str:
    # Qt reads 8-digit hex as #AARRGGBB, so build translucent colours explicitly.
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {int(alpha * 255)})"


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FileItemWidget(QWidget):
    """
    A single row in the file queue. Shows live progress while converting and,
    once finished, inline actions (Open / Show in folder, or error Details).

    Emits:
        remove_requested(request_id: str)
    """

    remove_requested = pyqtSignal(str)

    def __init__(
        self,
        request_id: str,
        path: Path,
        output_format: OutputFormat,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("fileItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._request_id = request_id
        self._path = path
        self._output_format = output_format
        self._state = ItemState.READY
        self._result: Optional[ConversionResult] = None
        self._error: Optional[ConversionError] = None
        try:
            self._size_str = _format_size(path.stat().st_size)
        except OSError:
            self._size_str = "—"
        self._build_ui()
        self._apply_state()

    # ──────────────────────────────────────────────────
    # Properties
    # ──────────────────────────────────────────────────

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def path(self) -> Path:
        return self._path

    @property
    def state(self) -> ItemState:
        return self._state

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @property
    def result(self) -> Optional[ConversionResult]:
        return self._result

    @property
    def error(self) -> Optional[ConversionError]:
        return self._error

    # ──────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 10)
        outer.setSpacing(12)

        # File type badge
        ext = self._path.suffix.lower()
        label = _EXT_LABELS.get(ext, ext.upper().lstrip("."))
        color = _EXT_COLORS.get(ext, "#71716c")

        type_badge = QLabel(label)
        type_badge.setFixedSize(40, 40)
        type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_badge.setStyleSheet(
            f"background-color: {_rgba(color, 0.12)}; color: {color}; "
            f"border: 1px solid {_rgba(color, 0.28)}; border-radius: 6px; "
            f"font-size: 9px; font-weight: 700; letter-spacing: 0.3px;"
        )
        outer.addWidget(type_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # File info (name + meta + progress)
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        self._name_label = QLabel(self._path.name)
        self._name_label.setObjectName("fileItemName")
        self._name_label.setToolTip(str(self._path))
        self._name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._name_label.setMinimumWidth(80)
        info_col.addWidget(self._name_label)

        self._meta_label = QLabel()
        self._meta_label.setObjectName("fileItemMeta")
        self._meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info_col.addWidget(self._meta_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        info_col.addWidget(self._progress)

        outer.addLayout(info_col, 1)

        # Inline actions (shown per state)
        self._open_btn = self._action_button("Open", "Open the converted file", self._open_output)
        self._folder_btn = self._action_button("Show in folder", "Reveal in file manager", self._reveal_output)
        self._details_btn = self._action_button("Details", "Why did this fail?", self._show_details)
        for btn in (self._open_btn, self._folder_btn, self._details_btn):
            outer.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # Status badge
        self._status_badge = QLabel()
        self._status_badge.setFixedHeight(22)
        self._status_badge.setMinimumWidth(76)
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # Remove button
        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("removeButton")
        self._remove_btn.setFixedSize(28, 28)
        self._remove_btn.setToolTip("Remove from list")
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._request_id))
        outer.addWidget(self._remove_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _action_button(self, text: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("rowActionButton")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # ──────────────────────────────────────────────────
    # State rendering
    # ──────────────────────────────────────────────────

    def _route_text(self) -> str:
        src = _EXT_LABELS.get(self._path.suffix.lower(), self._path.suffix.upper().lstrip("."))
        return f"{src} → {_SHORT_FORMAT.get(self._output_format, self._output_format.display_name)}"

    def _set_meta(self, text: str, tone: str = "") -> None:
        self._meta_label.setText(text)
        self._meta_label.setProperty("tone", tone)
        _repolish(self._meta_label)

    def _apply_state(self, message: str = "") -> None:
        state = self._state
        text, badge_id = _BADGES[state]
        self._status_badge.setText(text)
        self._status_badge.setObjectName(badge_id)
        _repolish(self._status_badge)

        self._progress.setVisible(state == ItemState.CONVERTING)
        self._open_btn.setVisible(state == ItemState.DONE)
        self._folder_btn.setVisible(state == ItemState.DONE)
        self._details_btn.setVisible(state == ItemState.ERROR)
        self._remove_btn.setVisible(state not in (ItemState.QUEUED, ItemState.CONVERTING))

        if state == ItemState.CONVERTING:
            self._set_meta(message or f"{self._route_text()}  ·  Starting…")
        elif state == ItemState.DONE and self._result is not None:
            out = self._result.output_path
            self._set_meta(f"Saved as {out.name}  ·  {_format_duration(self._result.duration_ms)}", "success")
            self.setToolTip(str(out))
        elif state == ItemState.ERROR and self._error is not None:
            self._set_meta(self._error.user_message.split("\n")[0], "error")
            self._meta_label.setToolTip(self._error.user_message)
        elif state == ItemState.CANCELLED:
            self._set_meta(f"{self._size_str}  ·  {self._route_text()}  ·  Skipped")
        else:
            self._set_meta(f"{self._size_str}  ·  {self._route_text()}")

    # ──────────────────────────────────────────────────
    # Status updates
    # ──────────────────────────────────────────────────

    def mark_ready(self) -> None:
        self._state = ItemState.READY
        self._result = None
        self._error = None
        self.setToolTip("")
        self._meta_label.setToolTip("")
        self._progress.setValue(0)
        self._apply_state()

    def mark_waiting(self) -> None:
        self._state = ItemState.QUEUED
        self._progress.setValue(0)
        self._apply_state()

    def mark_started(self) -> None:
        self._state = ItemState.CONVERTING
        self._progress.setValue(0)
        self._apply_state()

    def update_progress(self, progress: ConversionProgress) -> None:
        if self._state in (ItemState.DONE, ItemState.ERROR):
            return
        if progress.status in (ConversionStatus.DONE, ConversionStatus.ERROR):
            return  # final state arrives via mark_done / mark_error
        self._state = ItemState.CONVERTING
        self._progress.setValue(max(self._progress.value(), progress.percent))
        detail = progress.message.rstrip("…") if progress.message else "Converting"
        self._apply_state(f"{self._route_text()}  ·  {detail}…  {self._progress.value()}%")

    def mark_done(self, result: Optional[ConversionResult] = None) -> None:
        self._state = ItemState.DONE
        self._result = result
        self._apply_state()

    def mark_error(self, error: Optional[ConversionError] = None) -> None:
        self._state = ItemState.ERROR
        self._error = error
        self._apply_state()

    def mark_cancelled(self) -> None:
        self._state = ItemState.CANCELLED
        self._apply_state()

    def set_output_format(self, output_format: OutputFormat) -> None:
        """Update the target format (only meaningful before conversion)."""
        self._output_format = output_format
        self._apply_state()

    # ──────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────

    def _open_output(self) -> None:
        if self._result is not None:
            open_path(self._result.output_path)

    def _reveal_output(self) -> None:
        if self._result is not None:
            reveal_in_folder(self._result.output_path)

    def _show_details(self) -> None:
        if self._error is None:
            return
        from any2md.ui.dialogs.error_dialog import ErrorDialog

        ErrorDialog(self._error, self.window()).exec()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._state == ItemState.DONE:
            self._open_output()
        elif self._state == ItemState.ERROR:
            self._show_details()
        super().mouseDoubleClickEvent(event)
