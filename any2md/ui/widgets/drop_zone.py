"""Drop zone widget — drag-and-drop + file picker."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import SUPPORTED_INPUT_FORMATS


_ACCEPT_EXTENSIONS = set(SUPPORTED_INPUT_FORMATS.keys()) | {".md"}

_FORMAT_CHIPS = "PDF · DOCX · XLSX · PPTX · TXT · HTML · CSV · MD"

_ICON_SVG = """<svg width="36" height="36" viewBox="0 0 24 24" fill="none"
    xmlns="http://www.w3.org/2000/svg">
  <path d="M12 16L12 8M12 8L9 11M12 8L15 11" stroke="#a0a09a"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M3 15C3 17.8284 3 19.2426 3.87868 20.1213C4.75736 21 6.17157 21
    9 21H15C17.8284 21 19.2426 21 20.1213 20.1213C21 19.2426 21 17.8284 21
    15" stroke="#a0a09a" stroke-width="1.5" stroke-linecap="round"/>
</svg>"""


class DropZoneWidget(QWidget):
    """
    Primary file input area.

    Emits:
        files_dropped(list[Path]) — when valid files are dragged in or selected
    """

    files_dropped = pyqtSignal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()

    # ──────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(40, 40, 40, 40)

        # Upload icon (rendered as Unicode/emoji-free SVG label)
        icon_label = QLabel("↑")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            "font-size: 28px; color: #a0a09a; background: transparent; border: none;"
        )
        layout.addWidget(icon_label)

        # Title
        title = QLabel("Drop files here")
        title.setObjectName("dropZoneTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("or choose from your computer")
        subtitle.setObjectName("dropZoneSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Select Files button
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._select_btn = QPushButton("Select Files")
        self._select_btn.setFixedWidth(150)
        self._select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_btn.clicked.connect(self._open_file_dialog)
        btn_row.addWidget(self._select_btn)
        layout.addLayout(btn_row)

        # Format chips
        chips = QLabel(_FORMAT_CHIPS)
        chips.setObjectName("formatChips")
        chips.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(chips)

    # ──────────────────────────────────────────────────
    # Drag-and-drop
    # ──────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
            if any(p.suffix.lower() in _ACCEPT_EXTENSIONS for p in paths):
                event.acceptProposedAction()
                self.setProperty("dragActive", "true")
                self.style().unpolish(self)
                self.style().polish(self)
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragActive", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragActive", "false")
        self.style().unpolish(self)
        self.style().polish(self)

        paths = [
            Path(u.toLocalFile())
            for u in event.mimeData().urls()
            if Path(u.toLocalFile()).suffix.lower() in _ACCEPT_EXTENSIONS
        ]
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)

    # ──────────────────────────────────────────────────
    # File dialog
    # ──────────────────────────────────────────────────

    def _open_file_dialog(self) -> None:
        ext_filter = (
            "Supported files ("
            + " ".join(f"*{e}" for e in sorted(_ACCEPT_EXTENSIONS))
            + ");;All files (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files to convert",
            str(Path.home()),
            ext_filter,
        )
        if paths:
            self.files_dropped.emit([Path(p) for p in paths])
