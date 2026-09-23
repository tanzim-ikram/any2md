"""Document → Markdown conversion using Microsoft MarkItDown."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Callable, Optional

from .models import (
    ConversionError,
    ConversionOptions,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
    OutputFormat,
)


class ToMarkdownConverter:
    """Converts supported document formats to Markdown using MarkItDown."""

    def __init__(self) -> None:
        self._md: Optional[object] = None

    def _get_engine(self):
        """Lazy-load MarkItDown to avoid startup cost."""
        if self._md is None:
            from markitdown import MarkItDown
            self._md = MarkItDown()
        return self._md

    def convert(
        self,
        request: ConversionRequest,
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> ConversionResult | ConversionError:
        import time

        start = time.monotonic()
        filename = request.input_path.name

        def emit(percent: int, status: ConversionStatus, message: str = "") -> None:
            if progress_callback:
                progress_callback(
                    ConversionProgress(
                        request_id=request.request_id,
                        filename=filename,
                        percent=percent,
                        status=status,
                        message=message,
                    )
                )

        emit(0, ConversionStatus.CONVERTING, "Starting…")

        try:
            # Validate input
            if not request.input_path.exists():
                raise FileNotFoundError(f"File not found: {request.input_path}")

            emit(10, ConversionStatus.CONVERTING, "Reading file…")

            engine = self._get_engine()
            emit(30, ConversionStatus.CONVERTING, "Converting…")

            result = engine.convert(str(request.input_path))
            markdown_content: str = result.text_content or ""

            emit(80, ConversionStatus.CONVERTING, "Writing output…")

            # Ensure output directory exists
            output_path = request.output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_content, encoding="utf-8")

            duration_ms = int((time.monotonic() - start) * 1000)
            emit(100, ConversionStatus.DONE, "Done")

            return ConversionResult(
                request=request,
                output_path=output_path,
                success=True,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            emit(0, ConversionStatus.ERROR, "Failed")
            return ConversionError(
                request=request,
                user_message=self._friendly_message(exc, request.input_path),
                detail=traceback.format_exc(),
            )

    @staticmethod
    def _friendly_message(exc: Exception, path: Path) -> str:
        name = path.name
        ext = path.suffix.upper().lstrip(".")

        if isinstance(exc, FileNotFoundError):
            return f'The file "{name}" could not be found.'
        if isinstance(exc, PermissionError):
            return f'Permission denied when reading "{name}". Is it open in another application?'
        if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
            return f'"{name}" appears to be password-protected.'
        if "corrupted" in str(exc).lower() or "invalid" in str(exc).lower():
            return f'"{name}" appears to be damaged or is not a valid {ext} file.'

        return (
            f'Couldn\'t convert "{name}".\n'
            f"The {ext} file could not be processed. It may be damaged, "
            f"unsupported, or password-protected."
        )

