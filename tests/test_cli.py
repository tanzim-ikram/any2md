"""Unit tests for CLI argument handling and quick-convert mode."""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from any2md.conversion.models import OutputFormat
from any2md.ui.main_window import MainWindow, PAGE_FILES, PAGE_RESULT


class TestCLIHandling:
    def setup_method(self) -> None:
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)
        self.win = MainWindow()
        self.win.show()

    def teardown_method(self) -> None:
        self.win.close()

    def test_open_files_via_cli(self, tmp_path: Path) -> None:
        f1 = tmp_path / "doc1.txt"
        f1.write_text("File 1", encoding="utf-8")

        self.win.handle_cli_args([str(f1)])
        assert self.win._stack.currentIndex() == PAGE_FILES
        assert self.win._file_list.file_count == 1

    def test_quick_convert_via_cli(self, tmp_path: Path) -> None:
        f1 = tmp_path / "notes.txt"
        f1.write_text("Important meeting notes", encoding="utf-8")

        self.win.handle_cli_args([str(f1)], convert_to="md")

        # Worker should have been launched immediately
        assert self.win._worker is not None
        assert self.win._worker.wait(5000)

        # Process Qt events
        QApplication.instance().processEvents()

        # Should land on PAGE_RESULT
        assert self.win._stack.currentIndex() == PAGE_RESULT
        assert len(self.win._result_view._items) == 1
