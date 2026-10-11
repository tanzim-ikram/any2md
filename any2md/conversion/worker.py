"""QThread-based workers for non-blocking background conversion."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from .engine import ConversionEngine
from .models import (
    ConversionError,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
)


class ConversionWorker(QThread):
    """
    Runs a single file conversion in a background thread.

    Signals:
        progress  — emitted with each progress update
        finished  — emitted on success
        error     — emitted on failure
    """

    progress = pyqtSignal(ConversionProgress)
    finished = pyqtSignal(ConversionResult)
    error = pyqtSignal(ConversionError)

    def __init__(
        self,
        engine: ConversionEngine,
        request: ConversionRequest,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._request = request
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._cancelled:
            return

        result = self._engine.convert(
            self._request,
            progress_callback=lambda p: self.progress.emit(p),
        )

        if self._cancelled:
            return

        if isinstance(result, ConversionError):
            self.error.emit(result)
        else:
            self.finished.emit(result)


class BatchConversionWorker(QThread):
    """
    Runs a queue of conversions in a background thread.

    Each file emits its own progress/finished/error signals. More requests can
    be appended with `enqueue()` while the batch is running (e.g. files that
    arrive from further Explorer launches), so they join the same run.
    """

    file_started = pyqtSignal(str)  # request_id
    file_progress = pyqtSignal(ConversionProgress)
    file_finished = pyqtSignal(ConversionResult)
    file_error = pyqtSignal(ConversionError)
    batch_progress = pyqtSignal(int, int)  # (completed, total)
    batch_finished = pyqtSignal(list)  # list[ConversionResult | ConversionError]

    def __init__(
        self,
        engine: ConversionEngine,
        requests: list[ConversionRequest],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._requests = list(requests)
        self._total = len(self._requests)
        self._lock = threading.Lock()
        self._closed = False
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        """Stop after the file currently converting; queued files are skipped."""
        self._cancelled = True

    def enqueue(self, requests: list[ConversionRequest]) -> bool:
        """Append requests to the running batch. False once the batch has wrapped up."""
        with self._lock:
            if self._closed or self._cancelled:
                return False
            self._requests.extend(requests)
            self._total += len(requests)
            return True

    def pending_request_ids(self) -> list[str]:
        with self._lock:
            return [r.request_id for r in self._requests]

    def _next_request(self) -> ConversionRequest | None:
        with self._lock:
            if self._cancelled or not self._requests:
                self._closed = True
                return None
            return self._requests.pop(0)

    def run(self) -> None:
        results: list[ConversionResult | ConversionError] = []

        while (req := self._next_request()) is not None:
            self.file_started.emit(req.request_id)
            result = self._engine.convert(
                req,
                progress_callback=lambda p: self.file_progress.emit(p),
            )

            # The file in flight is allowed to finish even when cancelled, so
            # its output is reported rather than left half-known.
            if isinstance(result, ConversionError):
                self.file_error.emit(result)
            else:
                self.file_finished.emit(result)

            results.append(result)
            with self._lock:
                total = self._total
            self.batch_progress.emit(len(results), total)

        self.batch_finished.emit(results)
