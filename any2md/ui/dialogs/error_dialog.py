"""User-friendly error dialog with optional technical details."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from any2md.conversion.models import ConversionError


class ErrorDialog(QDialog):
    """
    Shows a friendly error message with an optional "View Details" expansion.

    Never exposes raw Python tracebacks by default.
    """

    def __init__(
        self,
        error: ConversionError,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conversion Failed")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._error = error
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("Couldn't convert this file")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        # User message
        msg = QLabel(self._error.user_message)
        msg.setWordWrap(True)
        msg.setObjectName("mutedLabel")
        msg.setStyleSheet("font-size: 13px; color: #71716c; line-height: 1.5;")
        layout.addWidget(msg)

        # Details toggle
        self._details_edit = QTextEdit()
        self._details_edit.setReadOnly(True)
        self._details_edit.setPlainText(self._error.detail)
        self._details_edit.setMinimumHeight(140)
        self._details_edit.setStyleSheet(
            "font-family: 'Cascadia Code', 'Consolas', monospace; "
            "font-size: 11px; "
            "background: #f7f7f5; "
            "border: 1px solid #e4e4e0; "
            "border-radius: 4px;"
        )
        self._details_edit.setVisible(False)
        layout.addWidget(self._details_edit)

        details_btn = QPushButton("View Details")
        details_btn.setObjectName("linkButton")
        details_btn.setStyleSheet("font-size: 12px; color: #a0a09a; border: none; background: transparent; padding: 0; text-align: left;")
        details_btn.clicked.connect(self._toggle_details)
        layout.addWidget(details_btn)
        self._details_btn = details_btn

        # Buttons
        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Dismiss", QDialogButtonBox.ButtonRole.AcceptRole)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(btns)

    def _toggle_details(self) -> None:
        visible = not self._details_edit.isVisible()
        self._details_edit.setVisible(visible)
        self._details_btn.setText("Hide Details" if visible else "View Details")
        self.adjustSize()
