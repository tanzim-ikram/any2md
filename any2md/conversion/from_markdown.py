"""Markdown → document conversion (PDF via weasyprint, DOCX via python-docx, HTML via markdown)."""

from __future__ import annotations

import base64
import binascii
import re
import traceback
from pathlib import Path
from urllib.parse import unquote, urlparse
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
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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

# Extra rules applied only when paginating to PDF: the page margins come from
# @page, so the screen-oriented body padding/max-width must not stack on top.
_PDF_CSS = """
body { max-width: none; padding: 0; font-size: 11pt; }
pre, code { word-wrap: break-word; }
pre { white-space: pre-wrap; page-break-inside: auto; }
h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
img, table, blockquote { page-break-inside: avoid; }
th, td { word-wrap: break-word; vertical-align: top; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
"""

_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r"""\bsrc\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)


def _load_image_bytes(src: str, base_dir: Optional[Path]) -> Optional[bytes]:
    """Return image bytes for a data URI or local path; None for remote/missing."""
    src = (src or "").strip()
    if not src:
        return None
    if src.lower().startswith("data:"):
        header, _, payload = src.partition(",")
        try:
            if ";base64" in header.lower():
                return base64.b64decode(payload, validate=False)
            return unquote(payload).encode("latin-1")
        except (binascii.Error, ValueError):
            return None
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https", "ftp"):
        return None  # exports stay fully offline
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path.lstrip("/") if re.match(r"^/[A-Za-z]:", parsed.path) else parsed.path))
    else:
        path = Path(unquote(src))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


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
                self._to_pdf(markdown_text, output_path, emit, request.input_path.parent)
            elif request.output_format == OutputFormat.DOCX:
                self._to_docx(markdown_text, output_path, emit, request.input_path.parent)
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

    @staticmethod
    def _normalize_list_indent(markdown_text: str) -> str:
        """Re-indent nested list items to 4 spaces per level (python-markdown needs 4)."""
        item_re = re.compile(r"^( *)(?:[-*+]|\d+[.)])\s")
        out: list[str] = []
        stack: list[int] = []
        in_fence = False
        for line in markdown_text.split("\n"):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
            elif not in_fence:
                m = item_re.match(line)
                if m:
                    indent = len(m.group(1))
                    while stack and stack[-1] > indent:
                        stack.pop()
                    if not stack or stack[-1] < indent:
                        stack.append(indent)
                    line = " " * (4 * (len(stack) - 1)) + line.lstrip(" ")
                elif line.strip() and not line.startswith(" "):
                    stack.clear()
            out.append(line)
        return "\n".join(out)

    def _md_to_html_str(self, markdown_text: str) -> str:
        import markdown as md_lib

        markdown_text = self._normalize_list_indent(markdown_text)

        extensions = [
            "tables",
            "fenced_code",
            "nl2br",
            "sane_lists",
        ]
        return md_lib.markdown(markdown_text, extensions=extensions)

    def _to_pdf(
        self,
        markdown_text: str,
        output_path: Path,
        emit: Callable[[int, ConversionStatus, str], None],
        base_dir: Optional[Path] = None,
    ) -> None:
        emit(50, ConversionStatus.CONVERTING, "Rendering PDF…")
        html_body = self._md_to_html_str(markdown_text)

        # Attempt high-fidelity rendering via WeasyPrint first
        try:
            from weasyprint import HTML, CSS
            full_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Document</title></head>
<body>{html_body}</body>
</html>"""
            HTML(string=full_html, base_url=str(base_dir) if base_dir else None).write_pdf(
                str(output_path),
                stylesheets=[CSS(string=_MARKDOWN_CSS), CSS(string=_PDF_CSS)],
            )
            emit(90, ConversionStatus.CONVERTING, "Saving…")
            return
        except Exception:
            pass

        # Fallback to zero-dependency native Qt PDF engine
        emit(60, ConversionStatus.CONVERTING, "Rendering PDF via native engine…")
        from PyQt6.QtCore import QMarginsF
        from PyQt6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument

        doc = QTextDocument()

        # QTextDocument cannot resolve data: URIs (or relative paths) in <img>,
        # which silently dropped every picture. Load each image ourselves and
        # register it as a document resource, capping width to the text area.
        max_px = 640
        counter = 0

        def register_image(match: "re.Match[str]") -> str:
            nonlocal counter
            tag = match.group(0)
            src_m = _IMG_SRC_RE.search(tag)
            if not src_m:
                return ""
            data = _load_image_bytes(src_m.group(2), base_dir)
            image = QImage.fromData(data) if data else QImage()
            if image.isNull():
                alt = re.search(r"""\balt\s*=\s*(["'])(.*?)\1""", tag, re.IGNORECASE | re.DOTALL)
                return f"<em>[image: {alt.group(2)}]</em>" if alt and alt.group(2) else ""
            counter += 1
            name = f"any2md_img_{counter}"
            doc.addResource(QTextDocument.ResourceType.ImageResource.value, QUrl(name), image)
            width = min(image.width(), max_px)
            return f'<img src="{name}" width="{width}" />'

        from PyQt6.QtCore import QUrl

        body = _IMG_TAG_RE.sub(register_image, html_body)
        # Qt ignores CSS borders/width on tables; use the attributes it honours.
        body = body.replace("<table>", '<table border="1" cellspacing="0" cellpadding="6" width="100%">')
        styled_html = f"""<html>
<head>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1a1a18; }}
h1 {{ font-size: 20pt; font-weight: bold; margin-top: 18pt; margin-bottom: 6pt; color: #111110; }}
h2 {{ font-size: 15pt; font-weight: bold; margin-top: 14pt; margin-bottom: 4pt; color: #111110; }}
h3 {{ font-size: 12pt; font-weight: bold; margin-top: 10pt; margin-bottom: 2pt; color: #111110; }}
p {{ margin-bottom: 8pt; line-height: 1.5; }}
pre {{ background-color: #f7f7f5; padding: 8pt; border: 1px solid #e4e4e0; font-family: Consolas, monospace; font-size: 9pt; }}
code {{ font-family: Consolas, monospace; background-color: #f3f3f1; font-size: 9pt; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 10pt; margin-bottom: 10pt; }}
th, td {{ border: 1px solid #d4d4d0; padding: 6pt 8pt; text-align: left; }}
th {{ background-color: #f3f3f1; font-weight: bold; }}
blockquote {{ border-left: 3px solid #2563eb; padding-left: 10pt; color: #71716c; margin-left: 0; }}
</style>
</head>
<body>{body}</body>
</html>"""
        doc.setHtml(styled_html)

        writer = QPdfWriter(str(output_path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(20, 20, 20, 20), QPageLayout.Unit.Millimeter)
        doc.print(writer)
        emit(90, ConversionStatus.CONVERTING, "Saving…")

    def _to_docx(
        self,
        markdown_text: str,
        output_path: Path,
        emit: Callable[[int, ConversionStatus, str], None],
        base_dir: Optional[Path] = None,
    ) -> None:
        """Convert Markdown → DOCX by walking the rendered HTML with python-docx."""
        from bs4 import BeautifulSoup, NavigableString, Tag
        from docx import Document
        from docx.enum.text import WD_BREAK
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor

        emit(50, ConversionStatus.CONVERTING, "Building document…")

        # Sanitize XML-incompatible control characters (e.g. form feeds \x0c from PDFs)
        markdown_text = re.sub(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]",
            lambda m: "\n" if m.group() in "\x0b\x0c" else "",
            markdown_text,
        )

        soup = BeautifulSoup(self._md_to_html_str(markdown_text), "html.parser")

        doc = Document()
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15

        section = doc.sections[0]
        max_width = section.page_width - section.left_margin - section.right_margin

        mono = "Consolas"

        def shade(element_pr, fill: str) -> None:
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), fill)
            element_pr.append(shd)

        def para_border(paragraph, side: str, color: str, size: int = 6, space: int = 4) -> None:
            ppr = paragraph._p.get_or_add_pPr()
            borders = ppr.find(qn("w:pBdr"))
            if borders is None:
                borders = OxmlElement("w:pBdr")
                ppr.append(borders)
            edge = OxmlElement(f"w:{side}")
            edge.set(qn("w:val"), "single")
            edge.set(qn("w:sz"), str(size))
            edge.set(qn("w:space"), str(space))
            edge.set(qn("w:color"), color)
            borders.append(edge)

        def add_hyperlink(paragraph, url: str, fmt: dict) -> None:
            rel_id = paragraph.part.relate_to(
                url,
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                is_external=True,
            )
            link = OxmlElement("w:hyperlink")
            link.set(qn("r:id"), rel_id)
            return link

        def style_run(run, fmt: dict) -> None:
            if fmt.get("bold"):
                run.bold = True
            if fmt.get("italic"):
                run.italic = True
            if fmt.get("strike"):
                run.font.strike = True
            if fmt.get("code"):
                run.font.name = mono
                run._element.rPr.rFonts.set(qn("w:eastAsia"), mono)
                run.font.size = Pt(9.5)
                shade(run._element.get_or_add_rPr(), "F3F3F1")
            if fmt.get("link"):
                run.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
                run.font.underline = True

        def add_picture(paragraph, node) -> None:
            data = _load_image_bytes(node.get("src", ""), base_dir)
            alt = node.get("alt", "")
            if data:
                import io

                try:
                    shape = paragraph.add_run().add_picture(io.BytesIO(data))
                    if shape.width > max_width:
                        ratio = max_width / shape.width
                        shape.width = int(max_width)
                        shape.height = int(shape.height * ratio)
                    return
                except Exception:
                    pass  # unsupported image type (e.g. SVG) -> alt text below
            if alt:
                run = paragraph.add_run(f"[image: {alt}]")
                run.italic = True

        def add_inline(paragraph, node, fmt: dict) -> None:
            for child in node.children:
                if isinstance(child, NavigableString):
                    # HTML whitespace rules: newlines are just spaces (real line
                    # breaks arrive as <br>), otherwise python-docx emits a
                    # second break for every "\n".
                    text = re.sub(r"\s+", " ", str(child))
                    prev = child.previous_sibling
                    if isinstance(prev, Tag) and prev.name == "br":
                        text = text.lstrip()
                    if text:
                        style_run(paragraph.add_run(text), fmt)
                    continue
                if not isinstance(child, Tag):
                    continue
                name = child.name
                if name == "br":
                    paragraph.add_run().add_break(WD_BREAK.LINE)
                elif name == "img":
                    add_picture(paragraph, child)
                elif name in ("strong", "b"):
                    add_inline(paragraph, child, {**fmt, "bold": True})
                elif name in ("em", "i"):
                    add_inline(paragraph, child, {**fmt, "italic": True})
                elif name in ("del", "s", "strike"):
                    add_inline(paragraph, child, {**fmt, "strike": True})
                elif name == "code":
                    add_inline(paragraph, child, {**fmt, "code": True})
                elif name == "a" and child.get("href"):
                    href = child["href"]
                    if re.match(r"^(https?|mailto):", href, re.IGNORECASE):
                        link = add_hyperlink(paragraph, href, fmt)
                        # Build runs in a scratch paragraph, then move them into the link.
                        holder = doc.add_paragraph()
                        add_inline(holder, child, {**fmt, "link": True})
                        for r in list(holder._p.findall(qn("w:r"))):
                            link.append(r)
                        holder._p.getparent().remove(holder._p)
                        paragraph._p.append(link)
                    else:  # anchors / relative links: keep the text only
                        add_inline(paragraph, child, fmt)
                else:
                    add_inline(paragraph, child, fmt)

        def inline_paragraph(node, style: Optional[str] = None, indent: float = 0.0):
            p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
            if indent:
                p.paragraph_format.left_indent = Inches(indent)
            add_inline(p, node, {})
            return p

        def add_code_block(text: str) -> None:
            text = text.rstrip("\n")
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.left_indent = Inches(0.1)
            shade(p._p.get_or_add_pPr(), "F7F7F5")
            for side in ("top", "left", "bottom", "right"):
                para_border(p, side, "E4E4E0", size=4, space=4)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                run = p.add_run(line)
                run.font.name = mono
                run._element.rPr.rFonts.set(qn("w:eastAsia"), mono)
                run.font.size = Pt(9)
                if i < len(lines) - 1:
                    run.add_break(WD_BREAK.LINE)

        def add_table(node) -> None:
            rows = node.find_all("tr")
            if not rows:
                return
            cols = max(len(r.find_all(["th", "td"])) for r in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            table.style = "Table Grid"
            table.autofit = True
            for ri, row in enumerate(rows):
                for ci, cell_node in enumerate(row.find_all(["th", "td"])[:cols]):
                    cell = table.rows[ri].cells[ci]
                    para = cell.paragraphs[0]
                    para.paragraph_format.space_after = Pt(2)
                    header = cell_node.name == "th"
                    add_inline(para, cell_node, {"bold": header})
                    align = (cell_node.get("style") or "")
                    if "text-align: center" in align:
                        para.alignment = 1
                    elif "text-align: right" in align:
                        para.alignment = 2
                    if header:
                        shade(cell._tc.get_or_add_tcPr(), "F3F3F1")
            doc.add_paragraph().paragraph_format.space_after = Pt(2)

        def add_list(node, level: int = 0) -> None:
            ordered = node.name == "ol"
            number = int(node.get("start", 1)) if ordered and str(node.get("start", "1")).isdigit() else 1
            for li in node.find_all("li", recursive=False):
                # Split the <li> into its own inline content and nested lists/blocks.
                inline_parts = [
                    c for c in li.children
                    if not (isinstance(c, Tag) and c.name in ("ul", "ol", "pre", "blockquote", "table"))
                ]
                if ordered:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Inches(0.35 + 0.3 * level)
                    p.paragraph_format.first_line_indent = Inches(-0.25)
                    p.paragraph_format.space_after = Pt(2)
                    p.add_run(f"{number}.\t")
                    number += 1
                else:
                    style = "List Bullet" if level == 0 else f"List Bullet {min(level + 1, 3)}"
                    p = doc.add_paragraph(style=style)
                    p.paragraph_format.space_after = Pt(2)
                holder = BeautifulSoup("<li></li>", "html.parser").li
                for part in inline_parts:
                    holder.append(part.extract() if hasattr(part, "extract") else part)
                # strip surrounding whitespace in loose-list <p> wrappers
                for para_tag in holder.find_all("p", recursive=False):
                    para_tag.unwrap()
                add_inline(p, holder, {})
                for child in li.find_all(["ul", "ol", "pre", "blockquote", "table"], recursive=False):
                    if child.name in ("ul", "ol"):
                        add_list(child, level + 1)
                    else:
                        add_block(child)

        def add_block(node) -> None:
            if isinstance(node, NavigableString):
                if str(node).strip():
                    p = doc.add_paragraph()
                    p.add_run(str(node).strip())
                return
            if not isinstance(node, Tag):
                return
            name = node.name
            if re.fullmatch(r"h[1-6]", name):
                heading = doc.add_heading(level=int(name[1]))
                add_inline(heading, node, {})
            elif name == "p":
                p = doc.add_paragraph()
                add_inline(p, node, {})
            elif name in ("ul", "ol"):
                add_list(node)
            elif name == "pre":
                add_code_block(node.get_text())
            elif name == "blockquote":
                for child in node.children:
                    if isinstance(child, Tag) and child.name == "p":
                        p = doc.add_paragraph(style="Quote")
                        p.paragraph_format.left_indent = Inches(0.3)
                        para_border(p, "left", "2563EB", size=18, space=8)
                        add_inline(p, child, {})
                    elif isinstance(child, Tag):
                        add_block(child)
            elif name == "table":
                add_table(node)
            elif name == "hr":
                p = doc.add_paragraph()
                para_border(p, "bottom", "BBBBB5", size=6, space=1)
            elif name == "img":
                p = doc.add_paragraph()
                add_picture(p, node)
            else:
                for child in node.children:
                    add_block(child)

        for node in list(soup.children):
            add_block(node)

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

