"""Conversion engine -- routes requests to the correct converter."""

from __future__ import annotations

import tempfile
import time
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
    SUPPORTED_INPUT_FORMATS,
)
from .to_markdown import ToMarkdownConverter
from .from_markdown import FromMarkdownConverter


class ConversionEngine:
    """
    Central routing point for all conversions.

    Supports:
    - Any supported document format -> Markdown (via MarkItDown)
    - Markdown -> PDF / DOCX / HTML (via WeasyPrint / python-docx / markdown)
    - Two-hop pipeline (e.g. PDF -> DOCX, PDF -> HTML, DOCX -> PDF):
      Converts source document to Markdown first, then from Markdown to target format.
    """

    def __init__(self) -> None:
        self._to_md = ToMarkdownConverter()
        self._from_md = FromMarkdownConverter()

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def convert(
        self,
        request: ConversionRequest,
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> ConversionResult | ConversionError:
        """Convert a single file. Safe to call from any thread."""
        ext = request.input_extension

        if ext not in SUPPORTED_INPUT_FORMATS and ext != ".md":
            supported = ", ".join(SUPPORTED_INPUT_FORMATS.keys())
            return ConversionError(
                request=request,
                user_message=(
                    f'"{request.input_path.name}" is not a supported format.\n'
                    f"Supported: {supported}"
                ),
                detail=f"Extension {ext!r} not in SUPPORTED_INPUT_FORMATS.",
                error_code="UNSUPPORTED_FORMAT",
            )

        if (request.is_from_markdown() and request.output_format == OutputFormat.MARKDOWN) or (
            ext == request.output_format.extension
        ):
            return ConversionError(
                request=request,
                user_message=f"The file is already in {request.output_format.display_name} format.",
                detail=f"Source and target format are both {request.output_format.display_name}.",
                error_code="SAME_FORMAT",
            )

        if request.is_from_markdown():
            return self._from_md.convert(request, progress_callback)

        if request.is_to_markdown():
            return self._to_md.convert(request, progress_callback)

        return self._convert_two_hop(request, progress_callback)

    def _convert_two_hop(
        self,
        request: ConversionRequest,
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> ConversionResult | ConversionError:
        """Two-hop conversion pipeline: Source -> Intermediate Markdown -> Target format."""
        start_time = time.monotonic()
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

        emit(0, ConversionStatus.CONVERTING, "Starting conversion…")

        def step1_progress(prog: ConversionProgress) -> None:
            scaled = int(prog.percent * 0.5)
            emit(scaled, prog.status, f"Extracting to Markdown… ({prog.percent}%)")

        def step2_progress(prog: ConversionProgress) -> None:
            scaled = int(50 + prog.percent * 0.5)
            emit(scaled, prog.status, f"Generating {request.output_format.display_name}… ({prog.percent}%)")

        with tempfile.TemporaryDirectory(prefix="any2md_intermediate_") as temp_dir:
            temp_dir_path = Path(temp_dir)

            # Step 1: Source Document -> Intermediate Markdown
            step1_req = ConversionRequest(
                input_path=request.input_path,
                output_format=OutputFormat.MARKDOWN,
                output_dir=temp_dir_path,
                options=request.options,
                request_id=request.request_id,
            )
            step1_res = self._to_md.convert(step1_req, step1_progress)
            if isinstance(step1_res, ConversionError):
                return step1_res

            intermediate_md_path = step1_res.output_path
            if not intermediate_md_path.exists():
                return ConversionError(
                    request=request,
                    user_message="Intermediate conversion to Markdown failed.",
                    detail="Temporary Markdown file was not found.",
                    error_code="INTERMEDIATE_CONVERSION_FAILED",
                )

            # Step 2: Intermediate Markdown -> Final requested output format
            target_out_dir = request.output_dir or request.input_path.parent
            step2_req = ConversionRequest(
                input_path=intermediate_md_path,
                output_format=request.output_format,
                output_dir=target_out_dir,
                options=ConversionOptions(
                    preserve_images=request.options.preserve_images,
                    combine_files=request.options.combine_files,
                    custom_output_name=request.options.custom_output_name or request.input_path.stem,
                ),
                request_id=request.request_id,
            )
            step2_res = self._from_md.convert(step2_req, step2_progress)
            if isinstance(step2_res, ConversionError):
                step2_res.request = request
                return step2_res

            duration_ms = int((time.monotonic() - start_time) * 1000)
            emit(100, ConversionStatus.DONE, "Done")

            return ConversionResult(
                request=request,
                output_path=step2_res.output_path,
                success=True,
                duration_ms=duration_ms,
                warnings=step2_res.warnings,
            )

    def batch_convert(
        self,
        requests: list[ConversionRequest],
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> list[ConversionResult | ConversionError]:
        """Convert multiple files. Each file is independent -- failures don't abort others."""
        results: list[ConversionResult | ConversionError] = []
        for req in requests:
            result = self.convert(req, progress_callback)
            results.append(result)
        return results

    @staticmethod
    def is_supported(path_or_ext: str) -> bool:
        ext = path_or_ext if path_or_ext.startswith(".") else f".{path_or_ext.split('.')[-1]}"
        return ext.lower() in SUPPORTED_INPUT_FORMATS or ext.lower() == ".md"
