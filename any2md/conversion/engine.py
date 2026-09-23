"""Conversion engine -- routes requests to the correct converter."""

from __future__ import annotations

from typing import Callable, Optional

from .models import (
    ConversionError,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
    OutputFormat,
    SUPPORTED_INPUT_FORMATS,
)
from .to_markdown import ToMarkdownConverter
from .from_markdown import FromMarkdownConverter


class ConversionEngine:
    """
    Central routing point for all conversions.

    Keeps converter instances alive across calls so MarkItDown's lazy
    initialisation cost is paid once per session.
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

        if request.is_from_markdown():
            if request.output_format == OutputFormat.MARKDOWN:
                return ConversionError(
                    request=request,
                    user_message="The input is already a Markdown file.",
                    detail="Source and target format are both Markdown.",
                    error_code="SAME_FORMAT",
                )
            return self._from_md.convert(request, progress_callback)

        if request.output_format != OutputFormat.MARKDOWN:
            return ConversionError(
                request=request,
                user_message=(
                    f"Converting {ext.upper()} directly to "
                    f"{request.output_format.display_name} is not supported. "
                    f"Convert to Markdown first."
                ),
                detail="Two-hop conversion not implemented.",
                error_code="UNSUPPORTED_ROUTE",
            )

        if ext not in SUPPORTED_INPUT_FORMATS:
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

        return self._to_md.convert(request, progress_callback)

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
