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

    def test_same_format_pdf_to_pdf_returns_error(self) -> None:
        req = make_request("test.pdf", OutputFormat.PDF)
        result = self.engine.convert(req)
        assert isinstance(result, ConversionError)
        assert result.error_code == "SAME_FORMAT"

    @patch("any2md.conversion.from_markdown.FromMarkdownConverter.convert")
    @patch("any2md.conversion.to_markdown.ToMarkdownConverter.convert")
    def test_two_hop_pdf_to_docx_routes_through_pipeline(
        self, mock_to_md, mock_from_md, tmp_path
    ) -> None:
        fake_md = tmp_path / "test.md"
        fake_md.write_text("# Hello", encoding="utf-8")
        mock_to_md.return_value = ConversionResult(
            request=MagicMock(),
            output_path=fake_md,
            success=True,
        )
        fake_docx = tmp_path / "test.docx"
        mock_from_md.return_value = ConversionResult(
            request=MagicMock(),
            output_path=fake_docx,
            success=True,
        )

        req = make_request("test.pdf", OutputFormat.DOCX, output_dir=tmp_path)
        result = self.engine.convert(req)
        assert isinstance(result, ConversionResult)
        assert result.success is True
        mock_to_md.assert_called_once()
        mock_from_md.assert_called_once()

    @patch("any2md.conversion.to_markdown.ToMarkdownConverter.convert")
    def test_two_hop_step1_failure_returns_error(self, mock_to_md, tmp_path) -> None:
        mock_to_md.return_value = ConversionError(
            request=MagicMock(),
            user_message="Failed to read PDF",
            detail="File corrupted",
        )
        req = make_request("test.pdf", OutputFormat.DOCX, output_dir=tmp_path)
        result = self.engine.convert(req)
        assert isinstance(result, ConversionError)
        assert result.user_message == "Failed to read PDF"

    @patch("any2md.conversion.from_markdown.FromMarkdownConverter.convert")
    @patch("any2md.conversion.to_markdown.ToMarkdownConverter.convert")
    def test_two_hop_progress_reporting(self, mock_to_md, mock_from_md, tmp_path) -> None:
        def fake_to_md(req, cb=None):
            if cb:
                from any2md.conversion.models import ConversionProgress, ConversionStatus
                cb(ConversionProgress(request_id="1", filename="test.pdf", percent=50, status=ConversionStatus.CONVERTING))
            fake_md = tmp_path / "test.md"
            fake_md.write_text("# Hello", encoding="utf-8")
            return ConversionResult(request=req, output_path=fake_md, success=True)

        def fake_from_md(req, cb=None):
            if cb:
                from any2md.conversion.models import ConversionProgress, ConversionStatus
                cb(ConversionProgress(request_id="1", filename="test.pdf", percent=50, status=ConversionStatus.CONVERTING))
            fake_docx = tmp_path / "test.docx"
            return ConversionResult(request=req, output_path=fake_docx, success=True)

        mock_to_md.side_effect = fake_to_md
        mock_from_md.side_effect = fake_from_md

        progress_reports = []
        req = make_request("test.pdf", OutputFormat.DOCX, output_dir=tmp_path)
        result = self.engine.convert(req, progress_callback=lambda p: progress_reports.append(p.percent))
        assert isinstance(result, ConversionResult)
        assert 0 in progress_reports
        assert 25 in progress_reports  # step 1 50% -> scaled to 25%
        assert 75 in progress_reports  # step 2 50% -> scaled to 75%
        assert 100 in progress_reports

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
