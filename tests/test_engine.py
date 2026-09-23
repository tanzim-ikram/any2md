"""Unit tests for the conversion engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from any2md.conversion.engine import ConversionEngine
from any2md.conversion.models import (
    ConversionError,
    ConversionOptions,
    ConversionRequest,
    ConversionResult,
    OutputFormat,
)


def make_request(
    filename: str = "test.pdf",
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    output_dir: Path | None = None,
) -> ConversionRequest:
    return ConversionRequest(
        input_path=Path(filename),
        output_format=output_format,
        output_dir=output_dir,
        options=ConversionOptions(),
    )


class TestEngineRouting:
    def setup_method(self) -> None:
        self.engine = ConversionEngine()

    def test_unsupported_format_returns_error(self) -> None:
        req = make_request("test.xyz")
        result = self.engine.convert(req)
        assert isinstance(result, ConversionError)
        assert result.error_code == "UNSUPPORTED_FORMAT"

    def test_same_format_md_to_md_returns_error(self) -> None:
        req = make_request("test.md", OutputFormat.MARKDOWN)
        result = self.engine.convert(req)
        assert isinstance(result, ConversionError)
        assert result.error_code == "SAME_FORMAT"

    def test_unsupported_route_pdf_to_docx_returns_error(self) -> None:
        req = make_request("test.pdf", OutputFormat.DOCX)
        result = self.engine.convert(req)
        assert isinstance(result, ConversionError)
        assert result.error_code == "UNSUPPORTED_ROUTE"

    def test_is_supported_pdf(self) -> None:
        assert ConversionEngine.is_supported(".pdf") is True

    def test_is_supported_md(self) -> None:
        assert ConversionEngine.is_supported(".md") is True

    def test_is_not_supported_xyz(self) -> None:
        assert ConversionEngine.is_supported(".xyz") is False

    @patch("any2md.conversion.to_markdown.ToMarkdownConverter.convert")
    def test_pdf_to_markdown_routes_to_to_markdown(self, mock_convert) -> None:
        mock_convert.return_value = MagicMock(spec=ConversionResult)
        req = make_request("test.pdf", OutputFormat.MARKDOWN)
        self.engine.convert(req)
        mock_convert.assert_called_once()

    @patch("any2md.conversion.from_markdown.FromMarkdownConverter.convert")
    def test_md_to_pdf_routes_to_from_markdown(self, mock_convert) -> None:
        mock_convert.return_value = MagicMock(spec=ConversionResult)
        req = make_request("test.md", OutputFormat.PDF)
        self.engine.convert(req)
        mock_convert.assert_called_once()


class TestBatchConvert:
    def setup_method(self) -> None:
        self.engine = ConversionEngine()

    def test_batch_returns_result_per_request(self) -> None:
        requests = [
            make_request("a.xyz"),
            make_request("b.abc"),
        ]
        results = self.engine.batch_convert(requests)
        assert len(results) == 2
        assert all(isinstance(r, ConversionError) for r in results)

    def test_batch_failure_does_not_abort_others(self) -> None:
        """One failing request should not cancel remaining ones."""
        requests = [
            make_request("bad.xyz"),  # will error: unsupported
            make_request("also_bad.abc"),  # will also error
        ]
        results = self.engine.batch_convert(requests)
        # Both should return ConversionError, not raise an exception
        assert len(results) == 2
