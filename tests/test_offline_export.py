"""Regression tests: exported documents must not reference remote resources."""

from __future__ import annotations

from pathlib import Path

from any2md.conversion.engine import ConversionEngine
from any2md.conversion.from_markdown import _MARKDOWN_CSS
from any2md.conversion.models import ConversionRequest, ConversionResult, OutputFormat


def test_export_css_has_no_remote_urls() -> None:
    assert "http://" not in _MARKDOWN_CSS
    assert "https://" not in _MARKDOWN_CSS
    assert "@import" not in _MARKDOWN_CSS


def test_html_export_has_no_remote_urls(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nSome text.", encoding="utf-8")

    res = ConversionEngine().convert(
        ConversionRequest(input_path=md, output_format=OutputFormat.HTML, output_dir=tmp_path)
    )
    assert isinstance(res, ConversionResult)

    html = res.output_path.read_text(encoding="utf-8")
    assert "googleapis" not in html
    assert "@import" not in html
