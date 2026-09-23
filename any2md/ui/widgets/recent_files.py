"""Recent conversions widget — compact history table."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from any2md.storage.history import HistoryEntry, HistoryStore


class RecentFilesWidget(QWidget):
    """
    Collapsible recent conversions panel.

    Emits:
        history_cleared()
    """

    history_cleared = pyqtSignal()

    def __init__(
        self, history: HistoryStore, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._history = history
        self._expanded = True
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header row
        header = QWidget()
        header.setObjectName("recentHeader")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(8)

        self._toggle_btn = QPushButton("Recent ∨" if self._expanded else "Recent ›")
        self._toggle_btn.setObjectName("linkButton")
        self._toggle_btn.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #71716c; border: none; background: transparent; padding: 0;"
        )
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_expand)
        header_layout.addWidget(self._toggle_btn)
        header_layout.addStretch()

        self._clear_btn = QPushButton("Clear history")
        self._clear_btn.setObjectName("linkButton")
        self._clear_btn.setStyleSheet("font-size: 11px; color: #a0a09a; border: none; background: transparent; padding: 0;")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_history)
        header_layout.addWidget(self._clear_btn)

        root.addWidget(header)

        # Table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["File", "Direction", "Date", "Status"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setMaximumHeight(180)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self._table)

    def _update_table_height(self) -> None:
        """Size table and widget snugly to contents, eliminating any empty gap."""
        header_h = 36
        if not self._expanded:
            self._table.setFixedHeight(0)
            self.setFixedHeight(header_h)
            return
        rows = self._table.rowCount()
        if rows == 0:
            self._table.setFixedHeight(0)
            self.setFixedHeight(header_h)
            self._clear_btn.setEnabled(False)
            return
        self._clear_btn.setEnabled(True)
        h = self._table.horizontalHeader().height() + 4
        for i in range(rows):
            h += self._table.rowHeight(i)
        table_h = min(180, max(56, h))
        self._table.setFixedHeight(table_h)
        self.setFixedHeight(header_h + table_h)

    def refresh(self) -> None:
        """Reload history from store and repopulate table."""
        entries = self._history.get_all()
        self._table.setRowCount(0)
        for entry in entries[:20]:  # Show max 20 in the widget
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(entry.input_filename)
            name_item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            name_item.setToolTip(entry.input_path)
            self._table.setItem(row, 0, name_item)

            dir_item = QTableWidgetItem(entry.direction)
            self._table.setItem(row, 1, dir_item)

            date_item = QTableWidgetItem(entry.timestamp_display)
            self._table.setItem(row, 2, date_item)

            status_text = "Done" if entry.status == "done" else "Failed"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    "#16a34a" if entry.status == "done" else "#dc2626"
                )
            )
            self._table.setItem(row, 3, status_item)

        self._update_table_height()

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self._table.setVisible(self._expanded)
        self._toggle_btn.setText("Recent ∨" if self._expanded else "Recent ›")
        self._update_table_height()

    def _clear_history(self) -> None:
        self._history.clear()
        self._table.setRowCount(0)
        self._update_table_height()
        self.history_cleared.emit()

    def _show_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return

        entry_id_item = self._table.item(row, 0)
        if not entry_id_item:
            return
        entry_id = entry_id_item.data(Qt.ItemDataRole.UserRole)
        entries = {e.entry_id: e for e in self._history.get_all()}
        entry = entries.get(entry_id)
        if not entry:
            return

        menu = QMenu(self)
        if entry.output_path and Path(entry.output_path).exists():
            open_act = menu.addAction("Open Output File")
            open_act.triggered.connect(lambda: subprocess.Popen(["explorer", entry.output_path]))
            folder_act = menu.addAction("Show in Folder")
            folder_act.triggered.connect(
                lambda: subprocess.Popen(["explorer", "/select,", entry.output_path])
            )
            menu.addSeparator()

        remove_act = menu.addAction("Remove from History")
        remove_act.triggered.connect(lambda: self._remove_entry(entry_id, row))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_entry(self, entry_id: str, row: int) -> None:
        self._history.remove(entry_id)
        self._table.removeRow(row)
        self._update_table_height()
