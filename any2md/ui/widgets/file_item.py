"""Individual file row widget in the conversion queue."""

from __future__ import annotations

from pathlib import Path

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

from any2md.conversion.models import ConversionProgress, ConversionStatus, OutputFormat, SUPPORTED_INPUT_FORMATS

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
    ".md":   "#1a1a18",
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


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class FileItemWidget(QWidget):
    """
    A single row in the file queue.

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
        self._request_id = request_id
        self._path = path
        self._output_format = output_format
        self._build_ui()

    @property
    def request_id(self) -> str:
        return self._request_id

    # ──────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 12, 10)
        outer.setSpacing(12)

        # File type badge
        ext = self._path.suffix.lower()
        label = _EXT_LABELS.get(ext, ext.upper().lstrip("."))
        color = _EXT_COLORS.get(ext, "#71716c")

        type_badge = QLabel(label)
        type_badge.setFixedSize(40, 40)
        type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_badge.setStyleSheet(
            f"background-color: {color}18; color: {color}; "
            f"border: 1px solid {color}30; border-radius: 4px; "
            f"font-size: 9px; font-weight: 700; letter-spacing: 0.3px;"
        )
        outer.addWidget(type_badge)

        # File info (name + meta)
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        self._name_label = QLabel(self._path.name)
        self._name_label.setObjectName("fileItemName")
        self._name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        info_col.addWidget(self._name_label)

        size_str = _format_size(self._path.stat().st_size) if self._path.exists() else "—"
        meta_text = f"{size_str}  ·  {ext.upper().lstrip('.')} → {self._output_format.display_name}"
        self._meta_label = QLabel(meta_text)
        self._meta_label.setObjectName("fileItemMeta")
        info_col.addWidget(self._meta_label)

        # Progress bar (hidden until converting)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(3)
        self._progress.setVisible(False)
        info_col.addWidget(self._progress)

        outer.addLayout(info_col)

        # Status badge
        self._status_badge = QLabel("Ready")
        self._status_badge.setObjectName("badgeReady")
        self._status_badge.setFixedHeight(22)
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_badge)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setObjectName("linkButton")
        remove_btn.setToolTip("Remove from list")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._request_id))
        remove_btn.setStyleSheet("font-size: 16px; color: #a0a09a; border: none; background: transparent;")
        outer.addWidget(remove_btn)

    # ──────────────────────────────────────────────────
    # Status updates
    # ──────────────────────────────────────────────────

    def update_progress(self, progress: ConversionProgress) -> None:
        self._progress.setVisible(True)
        self._progress.setValue(progress.percent)

        status_map = {
            ConversionStatus.WAITING:    ("Waiting",     "badgeReady"),
            ConversionStatus.CONVERTING: ("Converting",  "badgeConverting"),
            ConversionStatus.DONE:       ("Done",        "badgeDone"),
            ConversionStatus.ERROR:      ("Failed",      "badgeError"),
            ConversionStatus.CANCELLED:  ("Cancelled",   "badgeReady"),
        }
        text, badge_id = status_map.get(progress.status, ("Ready", "badgeReady"))
        self._status_badge.setText(text)
        self._status_badge.setObjectName(badge_id)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        if progress.status in (ConversionStatus.DONE, ConversionStatus.ERROR):
            self._progress.setVisible(False)

    def mark_done(self) -> None:
        self._status_badge.setText("Done")
        self._status_badge.setObjectName("badgeDone")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._progress.setVisible(False)

    def mark_error(self) -> None:
        self._status_badge.setText("Failed")
        self._status_badge.setObjectName("badgeError")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._progress.setVisible(False)

    def mark_waiting(self) -> None:
        self._status_badge.setText("Waiting")
        self._status_badge.setObjectName("badgeReady")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    def set_output_format(self, output_format: OutputFormat) -> None:
        """Update displayed target format."""
        self._output_format = output_format
        ext = self._path.suffix.lower()
        size_str = _format_size(self._path.stat().st_size) if self._path.exists() else "—"
        self._meta_label.setText(f"{size_str}  ·  {ext.upper().lstrip('.')} → {self._output_format.display_name}")
