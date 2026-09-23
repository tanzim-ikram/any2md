"""QThread-based workers for non-blocking background conversion."""

from __future__ import annotations

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
    Runs batch conversion in a background thread.

    Each file emits its own progress/finished/error signals.
    Overall progress is tracked via `batch_progress`.
    """

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
        self._requests = requests
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        results: list[ConversionResult | ConversionError] = []
        total = len(self._requests)

        for i, req in enumerate(self._requests):
            if self._cancelled:
                break

            result = self._engine.convert(
                req,
                progress_callback=lambda p: self.file_progress.emit(p),
            )

            if self._cancelled:
                break

            if isinstance(result, ConversionError):
                self.file_error.emit(result)
            else:
                self.file_finished.emit(result)

            results.append(result)
            self.batch_progress.emit(i + 1, total)

        self.batch_finished.emit(results)
