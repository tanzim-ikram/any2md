"""Markdown → document conversion (PDF via weasyprint, DOCX via python-docx, HTML via markdown)."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Callable, Optional

from .models import (
    ConversionError,
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
    OutputFormat,
)

# CSS used when rendering Markdown → PDF/HTML
_MARKDOWN_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 15px;
    line-height: 1.7;
    color: #1a1a18;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 48px;
}
h1, h2, h3, h4, h5, h6 {
    font-weight: 600;
    line-height: 1.3;
    margin-top: 2em;
    margin-bottom: 0.5em;
    color: #111110;
}
h1 { font-size: 2em; margin-top: 0; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.15em; }
code {
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 0.875em;
    background: #f3f3f1;
    padding: 0.15em 0.35em;
    border-radius: 3px;
    color: #c7254e;
}
pre {
    background: #f7f7f5;
    border: 1px solid #e4e4e0;
    border-radius: 4px;
    padding: 16px 20px;
    overflow-x: auto;
    line-height: 1.5;
}
pre code {
    background: none;
    padding: 0;
    color: #1a1a18;
    font-size: 0.875em;
}
blockquote {
    border-left: 3px solid #d4d4d0;
    margin: 1em 0;
    padding: 0.25em 1em;
    color: #71716c;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}
th, td {
    border: 1px solid #e4e4e0;
    padding: 8px 12px;
    text-align: left;
}
th {
    background: #f7f7f5;
    font-weight: 600;
}
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: none; border-top: 1px solid #e4e4e0; margin: 2em 0; }
img { max-width: 100%; height: auto; border-radius: 4px; }
ul, ol { padding-left: 1.5em; }
li { margin: 0.25em 0; }

@page {
    margin: 2cm 2.5cm;
    @bottom-right {
        content: counter(page);
        font-size: 11px;
        color: #a0a09a;
    }
}
"""


class FromMarkdownConverter:
    """Converts Markdown to PDF, DOCX, or HTML."""

    def convert(
        self,
        request: ConversionRequest,
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> ConversionResult | ConversionError:
        import time

        start = time.monotonic()

        def emit(percent: int, status: ConversionStatus, message: str = "") -> None:
            if progress_callback:
                progress_callback(
                    ConversionProgress(
                        request_id=request.request_id,
                        filename=request.input_path.name,
                        percent=percent,
                        status=status,
                        message=message,
                    )
                )

        emit(0, ConversionStatus.CONVERTING, "Starting…")

        try:
            if not request.input_path.exists():
                raise FileNotFoundError(f"File not found: {request.input_path}")

            emit(10, ConversionStatus.CONVERTING, "Reading Markdown…")
            markdown_text = request.input_path.read_text(encoding="utf-8")

            emit(30, ConversionStatus.CONVERTING, "Converting…")

            output_path = request.output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if request.output_format == OutputFormat.PDF:
                self._to_pdf(markdown_text, output_path, emit)
            elif request.output_format == OutputFormat.DOCX:
                self._to_docx(markdown_text, output_path, emit)
            elif request.output_format == OutputFormat.HTML:
                self._to_html(markdown_text, output_path, emit)
            else:
                raise ValueError(f"Unsupported output format: {request.output_format}")

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
                user_message=self._friendly_message(exc, request),
                detail=traceback.format_exc(),
            )

    # ──────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────

    def _md_to_html_str(self, markdown_text: str) -> str:
        import markdown as md_lib

        extensions = [
            "tables",
            "fenced_code",
            "codehilite",
            "toc",
            "nl2br",
            "sane_lists",
        ]
        return md_lib.markdown(markdown_text, extensions=extensions)

    def _to_pdf(
        self,
        markdown_text: str,
        output_path: Path,
        emit: Callable[[int, ConversionStatus, str], None],
    ) -> None:
        from weasyprint import HTML, CSS

        emit(50, ConversionStatus.CONVERTING, "Rendering PDF…")
        html_body = self._md_to_html_str(markdown_text)
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Document</title></head>
<body>{html_body}</body>
</html>"""
        css = CSS(string=_MARKDOWN_CSS)
        HTML(string=full_html).write_pdf(str(output_path), stylesheets=[css])
        emit(90, ConversionStatus.CONVERTING, "Saving…")

    def _to_docx(
        self,
        markdown_text: str,
        output_path: Path,
        emit: Callable[[int, ConversionStatus, str], None],
    ) -> None:
        """Convert Markdown → DOCX via HTML intermediate using python-docx."""
        import re
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        emit(50, ConversionStatus.CONVERTING, "Building document…")

        doc = Document()

        # Set default font
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        # Parse markdown line by line (simple structural parser)
        lines = markdown_text.split("\n")
        in_code_block = False
        code_lines: list[str] = []
        in_table = False
        table_rows: list[list[str]] = []

        def flush_code_block():
            nonlocal in_code_block, code_lines
            if code_lines:
                p = doc.add_paragraph()
                run = p.add_run("\n".join(code_lines))
                run.font.name = "Cascadia Code"
                if not run.font.name:
                    run.font.name = "Courier New"
                run.font.size = Pt(9)
                code_lines = []
            in_code_block = False

        def flush_table():
            nonlocal in_table, table_rows
            if not table_rows:
                in_table = False
                return
            # Skip separator rows (only dashes/pipes)
            data_rows = [
                r for r in table_rows
                if not all(c.strip().replace("-", "").replace(":", "") == "" for c in r)
            ]
            if not data_rows:
                in_table = False
                table_rows = []
                return
            cols = max(len(r) for r in data_rows)
            table = doc.add_table(rows=len(data_rows), cols=cols)
            table.style = "Table Grid"
            for ri, row in enumerate(data_rows):
                for ci, cell_text in enumerate(row[:cols]):
                    cell = table.rows[ri].cells[ci]
                    cell.text = cell_text.strip()
                    if ri == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
            in_table = False
            table_rows = []

        def add_inline_text(paragraph, text: str):
            """Handle **bold**, *italic*, `code` inline."""
            pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)")
            pos = 0
            for m in pattern.finditer(text):
                if m.start() > pos:
                    paragraph.add_run(text[pos:m.start()])
                if m.group(2):  # bold
                    run = paragraph.add_run(m.group(2))
                    run.bold = True
                elif m.group(3):  # italic
                    run = paragraph.add_run(m.group(3))
                    run.italic = True
                elif m.group(4):  # code
                    run = paragraph.add_run(m.group(4))
                    run.font.name = "Courier New"
                    run.font.size = Pt(9)
                pos = m.end()
            if pos < len(text):
                paragraph.add_run(text[pos:])

        for line in lines:
            stripped = line.rstrip()

            # Code block toggle
            if stripped.startswith("```"):
                if in_code_block:
                    flush_code_block()
                else:
                    if in_table:
                        flush_table()
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # Table rows
            if "|" in stripped and stripped.strip().startswith("|"):
                if in_table is False:
                    in_table = True
                    table_rows = []
                cells = [c for c in stripped.strip().strip("|").split("|")]
                table_rows.append(cells)
                continue
            elif in_table:
                flush_table()

            # Headings
            heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                heading_map = {1: "Heading 1", 2: "Heading 2", 3: "Heading 3",
                               4: "Heading 4", 5: "Heading 5", 6: "Heading 6"}
                doc.add_heading(text, level=level)
                continue

            # Horizontal rule
            if re.match(r"^[-*_]{3,}$", stripped):
                doc.add_paragraph("─" * 60)
                continue

            # Blank line
            if not stripped:
                doc.add_paragraph()
                continue

            # Bullet list
            if re.match(r"^[-*+]\s+", stripped):
                text = re.sub(r"^[-*+]\s+", "", stripped)
                p = doc.add_paragraph(style="List Bullet")
                add_inline_text(p, text)
                continue

            # Numbered list
            if re.match(r"^\d+\.\s+", stripped):
                text = re.sub(r"^\d+\.\s+", "", stripped)
                p = doc.add_paragraph(style="List Number")
                add_inline_text(p, text)
                continue

            # Blockquote
            if stripped.startswith("> "):
                text = stripped[2:]
                p = doc.add_paragraph(style="Quote" if "Quote" in
                    [s.name for s in doc.styles] else "Normal")
                add_inline_text(p, text)
                continue

            # Normal paragraph
            p = doc.add_paragraph()
            add_inline_text(p, stripped)

        if in_code_block:
            flush_code_block()
        if in_table:
            flush_table()

        emit(90, ConversionStatus.CONVERTING, "Saving…")
        doc.save(str(output_path))

    def _to_html(
        self,
        markdown_text: str,
        output_path: Path,
        emit: Callable[[int, ConversionStatus, str], None],
    ) -> None:
        emit(50, ConversionStatus.CONVERTING, "Rendering HTML…")
        html_body = self._md_to_html_str(markdown_text)
        title = output_path.stem.replace("-", " ").replace("_", " ").title()
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
{_MARKDOWN_CSS}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""
        emit(90, ConversionStatus.CONVERTING, "Saving…")
        output_path.write_text(full_html, encoding="utf-8")

    @staticmethod
    def _friendly_message(exc: Exception, request: ConversionRequest) -> str:
        fmt = request.output_format.display_name
        name = request.input_path.name
        if isinstance(exc, FileNotFoundError):
            return f'The file "{name}" could not be found.'
        if isinstance(exc, PermissionError):
            return f'Permission denied when reading "{name}". Is it open in another application?'
        if isinstance(exc, ImportError):
            missing = str(exc).split("'")[-2] if "'" in str(exc) else "a required library"
            return (
                f"A required library ({missing}) is not installed.\n"
                f"Please run: pip install {missing}"
            )
        return (
            f'Couldn\'t convert "{name}" to {fmt}.\n'
            f"The file could not be processed. It may be damaged or contain unsupported content."
        )

