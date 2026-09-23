"""Result view — clean completion state after conversion."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import ConversionError, ConversionResult


class ResultItemWidget(QWidget):
    """Single row for a completed or failed file in the result view."""

    def __init__(
        self,
        result: ConversionResult | ConversionError,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(10)

        is_success = isinstance(self._result, ConversionResult)

        # Status icon
        icon = QLabel("✓" if is_success else "✕")
        icon.setStyleSheet(
            f"color: {'#16a34a' if is_success else '#dc2626'}; "
            f"font-size: 14px; font-weight: 600; min-width: 16px;"
        )
        layout.addWidget(icon)

        # Filename
        if is_success:
            name = self._result.output_path.name
        else:
            name = self._result.request.input_path.name

        name_label = QLabel(name)
        name_label.setObjectName("fileItemName")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name_label)

        if is_success:
            # Open button
            open_btn = QPushButton("Open")
            open_btn.setObjectName("linkButton")
            open_btn.setFixedWidth(50)
            open_btn.clicked.connect(self._open_file)
            layout.addWidget(open_btn)

            # Show in folder button
            folder_btn = QPushButton("Show in Folder")
            folder_btn.setObjectName("linkButton")
            folder_btn.clicked.connect(self._show_in_folder)
            layout.addWidget(folder_btn)
        else:
            err_label = QLabel(self._result.user_message.split("\n")[0])
            err_label.setObjectName("mutedLabel")
            err_label.setStyleSheet("color: #dc2626;")
            layout.addWidget(err_label)

    def _open_file(self) -> None:
        if isinstance(self._result, ConversionResult):
            try:
                subprocess.Popen(["explorer", str(self._result.output_path)])
            except Exception:
                pass

    def _show_in_folder(self) -> None:
        if isinstance(self._result, ConversionResult):
            try:
                subprocess.Popen(
                    ["explorer", "/select,", str(self._result.output_path)]
                )
            except Exception:
                pass


class ResultView(QWidget):
    """
    Completion screen shown after conversion finishes.

    Emits:
        convert_more_requested()
    """

    convert_more_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header
        self._header = QLabel("3 files converted")
        self._header.setObjectName("headingLabel")
        root.addWidget(self._header)

        # Sub-stats
        self._sub_label = QLabel("")
        self._sub_label.setObjectName("mutedLabel")
        root.addWidget(self._sub_label)

        # Divider
        from PyQt6.QtWidgets import QFrame
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        # Scrollable results list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll)

        # Actions
        btn_row = QHBoxLayout()
        convert_more_btn = QPushButton("Convert More Files")
        convert_more_btn.setObjectName("primaryButton")
        convert_more_btn.clicked.connect(self.convert_more_requested.emit)
        btn_row.addWidget(convert_more_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    def set_results(self, results: list[ConversionResult | ConversionError]) -> None:
        """Populate the result view with conversion results."""
        # Clear existing items
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        successes = [r for r in results if isinstance(r, ConversionResult)]
        errors = [r for r in results if isinstance(r, ConversionError)]
        total = len(results)

        if errors:
            if successes:
                self._header.setText(
                    f"✓ {len(successes)} of {total} files converted"
                )
                self._sub_label.setText(
                    f"{len(errors)} file{'s' if len(errors) > 1 else ''} failed."
                )
            else:
                self._header.setText("Conversion failed")
                self._sub_label.setText(
                    f"None of the {total} files could be converted."
                )
        else:
            self._header.setText(
                f"✓ {len(successes)} file{'s' if len(successes) > 1 else ''} converted"
            )
            self._sub_label.setText("")

        # Add result items
        for result in results:
            item = ResultItemWidget(result)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
