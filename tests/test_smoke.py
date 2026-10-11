"""Comprehensive smoke test suite for Any2MD.

Verifies:
1. Real end-to-end conversions across all supported routes (Single-hop & Two-hop).
2. UI construction, navigation, and page stacking.
3. Every button, combobox, input field, and interactive component.
4. Settings persistence and theme switching.
5. Recent files history recording and clearing.
6. Keyboard shortcuts.
7. Stylesheet parsing and application.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QRadioButton, QToolButton

from any2md.conversion.engine import ConversionEngine
from any2md.conversion.models import (
    ConversionError,
    ConversionOptions,
    ConversionRequest,
    ConversionResult,
    OutputFormat,
)
from any2md.conversion.worker import BatchConversionWorker
from any2md.storage.history import HistoryEntry, HistoryStore
from any2md.storage.settings import AppSettings, SettingsStore
from any2md.ui.icons import get_app_icon, get_app_logo_path, get_settings_icon, get_theme_icon
from any2md.ui.main_window import MainWindow, PAGE_DROP, PAGE_FILES
from any2md.ui.style.theme import apply_theme, load_stylesheet
from any2md.ui.widgets.file_item import FileItemWidget, ItemState


def wait_for_batch(win: MainWindow, timeout_ms: int = 60000) -> None:
    """Block until the window's conversion worker(s) finish and their signals are delivered."""
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while win._worker is not None and time.monotonic() < deadline:
        win._worker.wait(50)
        QApplication.instance().processEvents()
    assert win._worker is None, "conversion did not finish in time"


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ════════════════════════════════════════════════════════════════════
# 1. Real Engine End-to-End Conversion Smoke Tests
# ════════════════════════════════════════════════════════════════════

class TestConversionEngineSmoke:
    """Smoke test real conversion execution across supported formats."""

    def setup_method(self) -> None:
        self.engine = ConversionEngine()

    def test_txt_to_markdown_real(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "sample.txt"
        txt_file.write_text("Hello Any2MD smoke test!\nSecond line of plain text.", encoding="utf-8")

        req = ConversionRequest(
            input_path=txt_file,
            output_format=OutputFormat.MARKDOWN,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        assert res.output_path.suffix.lower() == ".md"
        assert "Hello Any2MD" in res.output_path.read_text(encoding="utf-8")

    def test_csv_to_markdown_real(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("Name,Age,Role\nAlice,30,Developer\nBob,25,Designer\n", encoding="utf-8")

        req = ConversionRequest(
            input_path=csv_file,
            output_format=OutputFormat.MARKDOWN,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        content = res.output_path.read_text(encoding="utf-8")
        assert "Alice" in content
        assert "Developer" in content

    def test_markdown_to_html_real(self, tmp_path: Path) -> None:
        md_file = tmp_path / "document.md"
        md_file.write_text("# Heading 1\n\nThis is **bold** text and a [link](https://example.com).", encoding="utf-8")

        req = ConversionRequest(
            input_path=md_file,
            output_format=OutputFormat.HTML,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        content = res.output_path.read_text(encoding="utf-8")
        assert "<h1" in content
        assert "Heading 1" in content
        assert "<strong>bold</strong>" in content

    def test_markdown_to_docx_real(self, tmp_path: Path) -> None:
        md_file = tmp_path / "document.md"
        md_file.write_text("# Title\n\nSome paragraph text.\n\n- Item 1\n- Item 2\n", encoding="utf-8")

        req = ConversionRequest(
            input_path=md_file,
            output_format=OutputFormat.DOCX,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        assert res.output_path.stat().st_size > 0

    def test_docx_to_markdown_real(self, tmp_path: Path) -> None:
        import docx

        doc_file = tmp_path / "sample.docx"
        doc = docx.Document()
        doc.add_heading("Docx Heading", level=1)
        doc.add_paragraph("This is a paragraph inside docx.")
        doc.save(str(doc_file))

        req = ConversionRequest(
            input_path=doc_file,
            output_format=OutputFormat.MARKDOWN,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        content = res.output_path.read_text(encoding="utf-8")
        assert "Docx Heading" in content
        assert "paragraph inside docx" in content

    def test_pdf_to_markdown_real(self, tmp_path: Path, qapp) -> None:
        from PyQt6.QtGui import QPageSize, QPdfWriter, QTextDocument

        pdf_file = tmp_path / "sample.pdf"
        writer = QPdfWriter(str(pdf_file))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        doc = QTextDocument()
        doc.setPlainText("Hello PDF to Markdown Conversion!")
        doc.print(writer)

        req = ConversionRequest(
            input_path=pdf_file,
            output_format=OutputFormat.MARKDOWN,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        content = res.output_path.read_text(encoding="utf-8")
        assert "Hello PDF to Markdown" in content


    def test_two_hop_txt_to_docx_real(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Meeting Notes\nDiscuss project deliverables.", encoding="utf-8")

        req = ConversionRequest(
            input_path=txt_file,
            output_format=OutputFormat.DOCX,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        assert res.output_path.suffix.lower() == ".docx"
        assert res.output_path.stat().st_size > 0

    def test_two_hop_txt_to_html_real(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "log.txt"
        txt_file.write_text("Server initialized.\nListening on port 8080.", encoding="utf-8")

        req = ConversionRequest(
            input_path=txt_file,
            output_format=OutputFormat.HTML,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionResult)
        assert res.output_path.exists()
        assert res.output_path.suffix.lower() == ".html"
        assert "Server initialized" in res.output_path.read_text(encoding="utf-8")

    def test_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.txt"
        req = ConversionRequest(
            input_path=missing,
            output_format=OutputFormat.MARKDOWN,
            output_dir=tmp_path,
            options=ConversionOptions(),
        )
        res = self.engine.convert(req)
        assert isinstance(res, ConversionError)
        assert "could not be found" in res.user_message


# ════════════════════════════════════════════════════════════════════
# 2. UI Components, Buttons, Inputs & Workflow Smoke Tests
# ════════════════════════════════════════════════════════════════════

class TestMainWindowSmoke:
    """Smoke test all MainWindow UI components, buttons, navigation, and settings."""

    def setup_method(self) -> None:
        self.win = MainWindow()
        self.win.show()

    def teardown_method(self) -> None:
        self.win.close()

    def test_app_and_window_icons(self, qapp) -> None:
        """Verify favicon / window icons are properly loaded and configured."""
        app_icon = get_app_icon()
        assert not app_icon.isNull()
        assert len(app_icon.availableSizes()) >= 5

        # MainWindow window icon
        assert not self.win.windowIcon().isNull()

        # Logo path exists
        assert get_app_logo_path().exists()

    def test_header_components_and_theme_cycling(self, qapp) -> None:
        """Verify header logo, title, and theme/settings button behavior."""
        # Logo widget
        logo_label = self.win.findChild(QLabel, "appLogo")
        assert logo_label is not None
        assert not logo_label.pixmap().isNull()
        assert logo_label.size() == QSize(24, 24)

        # Title widget
        title_label = self.win.findChild(QLabel, "appTitle")
        assert title_label is not None
        assert title_label.text() == "Any2MD"

        # Theme toggle button
        theme_btn = self.win._theme_btn
        assert theme_btn.size() == QSize(36, 36)
        assert theme_btn.iconSize() == QSize(20, 20)
        assert not theme_btn.icon().isNull()
        assert theme_btn.text() == ""

        # Settings button
        settings_btn = self.win._settings_btn
        assert settings_btn.size() == QSize(36, 36)
        assert settings_btn.iconSize() == QSize(20, 20)
        assert not settings_btn.icon().isNull()
        assert settings_btn.text() == ""

        # Test cycling theme
        initial_theme = self.win._settings.theme
        theme_btn.click()
        assert self.win._settings.theme != initial_theme
        assert not theme_btn.icon().isNull()
        assert not settings_btn.icon().isNull()

        # Cycle again
        theme_btn.click()
        theme_btn.click()
        assert self.win._settings.theme == initial_theme

    def test_settings_panel_toggle_and_inputs(self) -> None:
        """Verify settings panel visibility toggle, dropdowns, and radios."""
        panel = self.win._settings_panel
        assert not panel.isVisible()

        # Toggle open via header button
        self.win._settings_btn.click()
        assert panel.isVisible()

        # Test theme dropdown change
        panel._theme_combo.setCurrentIndex(1)  # dark
        assert self.win._settings.theme in ("light", "dark", "system")

        # Test format dropdown change
        panel._format_combo.setCurrentIndex(1)  # pdf
        assert self.win._settings.default_format == "pdf"

        # Test startup and images checkboxes
        panel._startup_check.setChecked(True)
        assert self.win._settings.start_with_windows is True

        # Test output directory setting
        panel._out_dir_edit.setText("C:/custom_out")
        panel._on_change()
        assert self.win._settings.default_output_dir == "C:/custom_out"

        # Toggle close via header button
        self.win._settings_btn.click()
        assert not panel.isVisible()

    def test_drag_drop_and_file_list_workflow(self, tmp_path: Path) -> None:
        """Verify file addition, format selection, output options, removal, and conversion."""
        f1 = tmp_path / "test1.txt"
        f1.write_text("Hello file 1", encoding="utf-8")
        f2 = tmp_path / "test2.csv"
        f2.write_text("a,b\n1,2", encoding="utf-8")

        # Initial state: Drop page
        assert self.win._stack.currentIndex() == PAGE_DROP

        # Simulate files dropped
        self.win._on_files_dropped([f1, f2])

        # Page should switch to PAGE_FILES
        assert self.win._stack.currentIndex() == PAGE_FILES
        file_list = self.win._file_list
        assert file_list.file_count == 2

        # Format combobox: changing target format updates all badges
        file_list._format_combo.setCurrentIndex(1)  # pdf
        for item in file_list._items.values():
            assert item._output_format == OutputFormat.PDF
            assert item._route_text() in item._meta_label.text()

        file_list._format_combo.setCurrentIndex(2)  # docx
        for item in file_list._items.values():
            assert item._output_format == OutputFormat.DOCX
            assert item._route_text() in item._meta_label.text()

        file_list._format_combo.setCurrentIndex(0)  # md
        for item in file_list._items.values():
            assert item._output_format == OutputFormat.MARKDOWN
            assert item._route_text() in item._meta_label.text()

        # Output folder controls
        assert file_list._out_dir_btn.text() == "Same folder as source"
        assert file_list._output_dir is None
        assert not file_list._reset_dir_btn.isVisibleTo(file_list)

        file_list.set_output_dir(tmp_path)
        assert file_list._output_dir == tmp_path
        assert file_list._out_dir_btn.toolTip() == str(tmp_path)
        assert file_list._reset_dir_btn.isVisibleTo(file_list)
        file_list._reset_dir_btn.click()
        assert file_list._output_dir is None

        # Dropping the same file again doesn't duplicate it
        self.win._on_files_dropped([f1])
        assert file_list.file_count == 2

        # Convert button reflects how many files are ready
        assert file_list._convert_btn.text() == "Convert 2 files"

        # Remove single item via item's remove button
        req_ids = list(file_list._items.keys())
        first_item = file_list._items[req_ids[0]]
        first_item._remove_btn.click()
        assert file_list.file_count == 1

        # Clear all files button returns to drop page
        file_list._clear_btn.click()
        assert self.win._stack.currentIndex() == PAGE_DROP
        assert file_list.file_count == 0

    def test_end_to_end_ui_conversion_and_results(self, tmp_path: Path) -> None:
        """Run a UI-driven batch; every row shows its own result in place."""
        good = tmp_path / "readme.txt"
        good.write_text("Integration smoke test content.", encoding="utf-8")
        bad = tmp_path / "blocked.txt"
        bad.write_text("Output path is taken by a folder.", encoding="utf-8")
        (tmp_path / "blocked.md").mkdir()  # writing the result must fail

        self.win._on_files_dropped([good, bad])
        assert self.win._stack.currentIndex() == PAGE_FILES

        self.win._file_list._convert_btn.click()
        assert self.win._worker is not None
        assert self.win._file_list._cancel_btn.isVisibleTo(self.win._file_list)
        wait_for_batch(self.win)

        # Results stay on the same page, one row per file
        assert self.win._stack.currentIndex() == PAGE_FILES
        file_list = self.win._file_list
        rows = {item.path.name: item for item in file_list.items()}
        ok, failed = rows["readme.txt"], rows["blocked.txt"]

        assert ok.state == ItemState.DONE
        assert ok.result is not None and ok.result.output_path.exists()
        assert ok._open_btn.isVisibleTo(ok) and ok._folder_btn.isVisibleTo(ok)
        assert "readme.md" in ok._meta_label.text()

        assert failed.state == ItemState.ERROR
        assert failed.error is not None
        assert failed._details_btn.isVisibleTo(failed)

        # Batch summary + follow-up actions
        assert not file_list._cancel_btn.isVisibleTo(file_list)
        assert "1 file converted" in file_list._status_label.text()
        assert "1 failed" in file_list._status_label.text()
        assert file_list._retry_btn.isVisibleTo(file_list)

        file_list._clear_done_btn.click()
        assert [i.path.name for i in file_list.items()] == ["blocked.txt"]

        file_list._clear_btn.click()
        assert self.win._stack.currentIndex() == PAGE_DROP
        assert file_list.file_count == 0

    def test_files_added_mid_batch_join_running_queue(self, tmp_path: Path) -> None:
        """Files arriving while converting (e.g. more Explorer launches) join the batch."""
        files = []
        for i in range(3):
            f = tmp_path / f"part{i}.txt"
            f.write_text(f"Part {i}", encoding="utf-8")
            files.append(f)

        self.win.handle_external_request([str(files[0])], "md")
        worker = self.win._worker
        assert worker is not None
        self.win.handle_external_request([str(files[1]), str(files[2])], "md")
        assert self.win._worker is worker  # same run, not a new window/worker
        wait_for_batch(self.win)

        file_list = self.win._file_list
        assert file_list.file_count == 3
        assert all(item.state == ItemState.DONE for item in file_list.items())
        assert all((tmp_path / f"part{i}.md").exists() for i in range(3))
        assert "3 files converted" in file_list._status_label.text()

    def test_recent_files_widget(self, tmp_path: Path) -> None:
        """Verify recent files table displays entries and can be cleared."""
        recent_widget = self.win._recent_files
        entry = HistoryEntry(
            entry_id="test-entry-1",
            input_filename="document.pdf",
            input_path=str(tmp_path / "document.pdf"),
            output_path=str(tmp_path / "document.md"),
            direction="PDF → Markdown",
            status="done",
            timestamp="2026-09-24T01:00:00",
        )
        self.win._history.add(entry)
        recent_widget.refresh()

        assert recent_widget._table.rowCount() >= 1

        # Clear recent files
        recent_widget._clear_history()
        assert recent_widget._table.rowCount() == 0

    def test_keyboard_shortcuts(self) -> None:
        """Verify Ctrl+, and Escape shortcut actions."""
        # Toggle settings via shortcut action
        settings_action = None
        esc_action = None
        for action in self.win.actions():
            if action.text() == "Settings":
                settings_action = action
            elif action.text() == "Escape":
                esc_action = action

        assert settings_action is not None
        assert esc_action is not None

        # Open settings
        settings_action.trigger()
        assert self.win._settings_panel.isVisible()

        # Esc closes settings
        esc_action.trigger()
        assert not self.win._settings_panel.isVisible()

        names = {a.text() for a in self.win.actions()}
        assert {"Open files", "Convert"} <= names


# ════════════════════════════════════════════════════════════════════
# 3. Stylesheet Parsing & Application Smoke Tests
# ════════════════════════════════════════════════════════════════════

class TestStylesheetsSmoke:
    """Verify both light and dark stylesheets load and apply without errors."""

    def test_light_stylesheet_loads(self, qapp) -> None:
        qss = load_stylesheet("light")
        assert len(qss) > 500
        assert "#headerBar" in qss
        assert "#appTitle" in qss
        assert "#appLogo" in qss
        resolved = apply_theme(qapp, "light")
        assert resolved == "light"

    def test_dark_stylesheet_loads(self, qapp) -> None:
        qss = load_stylesheet("dark")
        assert len(qss) > 500
        assert "#headerBar" in qss
        assert "#appTitle" in qss
        assert "#appLogo" in qss
        resolved = apply_theme(qapp, "dark")
        assert resolved == "dark"
