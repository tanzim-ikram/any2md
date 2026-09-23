"""Settings panel — slides in from the right side of the main window."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
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

from any2md import __version__
from any2md.storage.settings import AppSettings


class SettingsPanel(QWidget):
    """
    Settings side panel.

    Emits:
        settings_changed(AppSettings)
        closed()
    """

    settings_changed = pyqtSignal(object)  # AppSettings
    closed = pyqtSignal()

    def __init__(
        self, settings: AppSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self._settings = settings
        self._build_ui()
        self._load(settings)

    # ──────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────
        header = QWidget()
        header.setObjectName("settingsPanelHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 14, 16, 14)

        title = QLabel("Settings")
        title.setObjectName("settingsPanelTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "font-size: 14px; color: #a0a09a; border: none; background: transparent;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.closed.emit)
        h_layout.addWidget(close_btn)
        root.addWidget(header)

        # ── Scrollable content ───────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        content = QWidget()
        content.setObjectName("settingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── General section ──────────────────────────
        layout.addWidget(self._section_label("GENERAL"))

        # Theme
        theme_row = self._row_layout("Theme")
        self._theme_combo = QComboBox()
        self._theme_combo.setView(QListView())
        self._theme_combo.addItem("System", "system")
        self._theme_combo.addItem("Light", "light")
        self._theme_combo.addItem("Dark", "dark")
        self._theme_combo.currentIndexChanged.connect(self._on_change)
        theme_row.addWidget(self._theme_combo)
        layout.addLayout(theme_row)

        # Default output dir
        layout.addWidget(self._section_row_label("Default output folder"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setPlaceholderText("Same as source file")
        self._out_dir_edit.setReadOnly(True)
        dir_row.addWidget(self._out_dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(82)
        browse_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Start with Windows
        self._startup_check = QCheckBox("Start with Windows")
        self._startup_check.stateChanged.connect(self._on_change)
        layout.addWidget(self._startup_check)

        # ── Conversion section ───────────────────────
        layout.addWidget(self._divider())
        layout.addWidget(self._section_label("CONVERSION"))

        # Default format
        fmt_row = self._row_layout("Default output format")
        self._format_combo = QComboBox()
        self._format_combo.setView(QListView())
        self._format_combo.addItem("Markdown", "markdown")
        self._format_combo.addItem("PDF", "pdf")
        self._format_combo.addItem("Word (.docx)", "docx")
        self._format_combo.addItem("HTML", "html")
        self._format_combo.currentIndexChanged.connect(self._on_change)
        fmt_row.addWidget(self._format_combo)
        layout.addLayout(fmt_row)

        # Preserve images
        self._images_check = QCheckBox("Preserve images where possible")
        self._images_check.stateChanged.connect(self._on_change)
        layout.addWidget(self._images_check)

        # ── About section ────────────────────────────
        layout.addWidget(self._divider())
        layout.addWidget(self._section_label("ABOUT"))

        about_text = QLabel(
            f"<b>Any2MD</b> v{__version__}<br>"
            f"<span style='color:#a0a09a;'>Your files stay on your computer.<br>"
            f"No data is uploaded to any server.</span>"
        )
        about_text.setWordWrap(True)
        about_text.setTextFormat(Qt.TextFormat.RichText)
        about_text.setStyleSheet("font-size: 12px; line-height: 1.5;")
        layout.addWidget(about_text)

        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ──────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _section_row_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        return label

    def _divider(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        return f

    def _row_layout(self, label_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel(label_text)
        lbl.setObjectName("mutedLabel")
        row.addWidget(lbl)
        row.addStretch()
        return row

    def _pick_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select default output folder", str(Path.home())
        )
        if folder:
            self._out_dir_edit.setText(folder)
            self._on_change()

    def _load(self, s: AppSettings) -> None:
        idx = self._theme_combo.findData(s.theme)
        self._theme_combo.setCurrentIndex(max(0, idx))

        idx2 = self._format_combo.findData(s.default_format)
        self._format_combo.setCurrentIndex(max(0, idx2))

        self._out_dir_edit.setText(s.default_output_dir)
        self._startup_check.setChecked(s.start_with_windows)
        self._images_check.setChecked(s.preserve_images)

    def _on_change(self) -> None:
        s = AppSettings(
            theme=self._theme_combo.currentData(),
            default_output_dir=self._out_dir_edit.text(),
            default_format=self._format_combo.currentData(),
            preserve_images=self._images_check.isChecked(),
            start_with_windows=self._startup_check.isChecked(),
        )
        self._settings = s
        self.settings_changed.emit(s)

    def get_settings(self) -> AppSettings:
        return self._settings

    def update_theme_selection(self, theme: str) -> None:
        """Sync combobox when theme is changed outside of the settings panel."""
        idx = self._theme_combo.findData(theme)
        if idx >= 0 and idx != self._theme_combo.currentIndex():
            self._theme_combo.blockSignals(True)
            self._theme_combo.setCurrentIndex(idx)
            self._theme_combo.blockSignals(False)
            self._settings.theme = theme
