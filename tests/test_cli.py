"""Unit tests for CLI argument handling, quick-convert mode and single-instance routing."""

import sys
import uuid
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QElapsedTimer
from PyQt6.QtWidgets import QApplication

from any2md.conversion.models import OutputFormat
from any2md.platform.single_instance import SingleInstance
from any2md.ui.main_window import MainWindow, PAGE_FILES
from any2md.ui.widgets.file_item import ItemState


def _wait_for_batch(win: MainWindow, timeout_ms: int = 60000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while win._worker is not None and timer.elapsed() < timeout_ms:
        win._worker.wait(50)
        QApplication.instance().processEvents()
    assert win._worker is None


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
        assert self.win._worker is None  # no --convert-to: wait for the user

    def test_quick_convert_via_cli(self, tmp_path: Path) -> None:
        f1 = tmp_path / "notes.txt"
        f1.write_text("Important meeting notes", encoding="utf-8")

        self.win.handle_cli_args([str(f1)], convert_to="md")

        # Worker should have been launched immediately
        assert self.win._worker is not None
        _wait_for_batch(self.win)

        assert self.win._stack.currentIndex() == PAGE_FILES
        (item,) = self.win._file_list.items()
        assert item.state == ItemState.DONE
        assert (tmp_path / "notes.md").exists()

    def test_explorer_multi_select_converts_in_one_window(self, tmp_path: Path) -> None:
        """Explorer sends one launch per file; all of them must end up in one queue."""
        paths = []
        for i in range(3):
            p = tmp_path / f"report{i}.txt"
            p.write_text(f"Report {i}", encoding="utf-8")
            paths.append(p)

        # First launch is the window itself; the others are forwarded requests.
        self.win.handle_cli_args([str(paths[0])], convert_to="md")
        for p in paths[1:]:
            self.win.handle_external_request([str(p)], "md")
        _wait_for_batch(self.win)

        items = self.win._file_list.items()
        assert [i.path.name for i in items] == [p.name for p in paths]
        assert all(i.state == ItemState.DONE for i in items)
        assert all(i.output_format == OutputFormat.MARKDOWN for i in items)

    def test_reconvert_same_file_to_another_format(self, tmp_path: Path) -> None:
        src = tmp_path / "notes.md"
        src.write_text("# Notes\n\nHello", encoding="utf-8")

        self.win.handle_cli_args([str(src)], convert_to="html")
        _wait_for_batch(self.win)
        self.win.handle_external_request([str(src)], "docx")
        _wait_for_batch(self.win)

        (item,) = self.win._file_list.items()
        assert item.state == ItemState.DONE
        assert item.output_format == OutputFormat.DOCX
        assert (tmp_path / "notes.html").exists() and (tmp_path / "notes.docx").exists()

    def test_unsupported_and_missing_files_are_ignored(self, tmp_path: Path) -> None:
        junk = tmp_path / "image.bmp"
        junk.write_bytes(b"BM")
        self.win.handle_cli_args([str(junk), str(tmp_path / "missing.pdf")], convert_to="md")
        assert self.win._file_list.file_count == 0
        assert self.win._worker is None


class TestSingleInstance:
    def setup_method(self) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)

    def test_second_instance_forwards_to_primary(self) -> None:
        key = f"any2md-test-{uuid.uuid4().hex[:8]}"
        primary = SingleInstance(key)
        assert primary.try_become_primary()

        received: list[dict] = []
        primary.message_received.connect(received.append)

        secondary = SingleInstance(key)
        assert not secondary.try_become_primary()

        # Blocking send from the "other process"; pump events so the server reads it.
        import threading

        ok: list[bool] = []
        payloads = [{"files": [f"C:/docs/{i}.pdf"], "convert_to": "md"} for i in range(3)]
        t = threading.Thread(
            target=lambda: ok.extend(SingleInstance(key).send_to_primary(p, 5) for p in payloads)
        )
        t.start()
        timer = QElapsedTimer()
        timer.start()
        while (t.is_alive() or len(received) < 3) and timer.elapsed() < 10000:
            QCoreApplication.processEvents()
        t.join()

        assert ok == [True, True, True]
        assert received == payloads
        primary.close()

        # Once the primary is gone, the next launch takes over.
        assert secondary.try_become_primary()
        secondary.close()

    def test_send_without_primary_fails_fast(self) -> None:
        lonely = SingleInstance(f"any2md-test-{uuid.uuid4().hex[:8]}")
        assert lonely.send_to_primary({"files": []}, timeout_s=0.3) is False
