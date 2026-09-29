"""Structure-aware PDF -> Markdown conversion using pdfplumber.

MarkItDown's default PDF handling (pdfminer text dump) loses headings, bold/
italic emphasis, and table structure. This module rebuilds that structure by
looking at each line's font size/weight and at pdfplumber's table detection.
"""

from __future__ import annotations

import base64
import io
import re
from collections import Counter
from pathlib import Path
from typing import Optional

_BULLET_RE = re.compile(r"^[•◦▪–⁃·]\s+")
_NUMBERED_RE = re.compile(r"^(\d+)[.)]\s+")
# Reportlab (and some other generators) render bullet glyphs from a symbol
# font with no Unicode mapping, so pdfplumber decodes each one as a literal
# "(cid:N)" placeholder instead of a character. A run of these at the start
# of a line is a bullet marker, not text.
_LEADING_CID_RUN_RE = re.compile(r"^(?:\(cid:\d+\)\s*)+")
_CID_TOKEN_RE = re.compile(r"\(cid:\d+\)")
_BOLD_RE = re.compile(r"bold|black|heavy|semibold", re.IGNORECASE)
_ITALIC_RE = re.compile(r"italic|oblique", re.IGNORECASE)


def pdf_to_markdown(path: Path, preserve_images: bool = True) -> str:
    """Convert a PDF to Markdown, preserving headings, emphasis, and tables.

    Returns an empty string if the PDF has no extractable text layer (e.g. a
    scanned document); callers should fall back to another engine in that case.
    """
    import pdfplumber

    blocks: list[str] = []
    body_size = None

    with pdfplumber.open(str(path)) as pdf:
        body_size = _detect_body_size(pdf.pages)
        heading_sizes = _detect_heading_sizes(pdf.pages, body_size)

        for page in pdf.pages:
            blocks.extend(
                _page_to_blocks(page, body_size, heading_sizes, preserve_images)
            )

    text = "\n\n".join(b for b in blocks if b.strip())
    return _collapse_blank_lines(text)


# --------------------------------------------------------------------------
# Body / heading size detection
# --------------------------------------------------------------------------


def _detect_body_size(pages) -> float:
    counts: Counter[float] = Counter()
    for page in pages:
        for ch in page.chars:
            counts[round(ch["size"], 1)] += 1
    if not counts:
        return 10.0
    return counts.most_common(1)[0][0]


def _detect_heading_sizes(pages, body_size: float) -> dict[float, int]:
    """Map distinct larger-than-body font sizes to heading levels 1-4."""
    sizes: set[float] = set()
    for page in pages:
        for ch in page.chars:
            size = round(ch["size"], 1)
            if size >= body_size * 1.15:
                sizes.add(size)
    ranked = sorted(sizes, reverse=True)[:4]
    return {size: level + 1 for level, size in enumerate(ranked)}


# --------------------------------------------------------------------------
# Per-page rendering
# --------------------------------------------------------------------------


def _page_to_blocks(page, body_size: float, heading_sizes: dict[float, int], preserve_images: bool) -> list[str]:
    items: list[tuple[float, str]] = []  # (top, markdown)

    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]
    for table in tables:
        rows = table.extract()
        md = _md_table(rows)
        if md:
            items.append((table.bbox[1], md))

    excluded_chars = _chars_in_bboxes(page, table_bboxes)
    text_page = page.filter(lambda obj: obj.get("object_type") != "char" or id(obj) not in excluded_chars)

    for line in text_page.extract_text_lines(layout=False):
        if not line["text"].strip():
            continue
        if _looks_like_page_number(line, page):
            continue
        md = _render_line(line, body_size, heading_sizes)
        if md.strip():
            items.append((line["top"], md))

    if preserve_images:
        for img in page.images:
            try:
                items.append((img["top"], _render_image(page, img)))
            except Exception:
                continue

    items.sort(key=lambda pair: pair[0])
    return _merge_paragraphs([md for _, md in items])


def _chars_in_bboxes(page, bboxes) -> set[int]:
    if not bboxes:
        return set()
    ids: set[int] = set()
    for ch in page.chars:
        cx0, cx1 = ch["x0"], ch["x1"]
        ctop, cbottom = ch["top"], ch["bottom"]
        for x0, top, x1, bottom in bboxes:
            if cx0 >= x0 - 1 and cx1 <= x1 + 1 and ctop >= top - 1 and cbottom <= bottom + 1:
                ids.add(id(ch))
                break
    return ids


def _looks_like_page_number(line: dict, page) -> bool:
    text = line["text"].strip()
    if not re.fullmatch(r"[-–—]?\s*\d{1,4}\s*[-–—]?", text):
        return False
    page_height = page.height
    band = page_height * 0.05
    return line["top"] <= band or line["bottom"] >= page_height - band


# --------------------------------------------------------------------------
# Line rendering: headings, lists, inline emphasis
# --------------------------------------------------------------------------


def _render_line(line: dict, body_size: float, heading_sizes: dict[float, int]) -> str:
    chars = line.get("chars", [])
    sizes = [round(c["size"], 1) for c in chars if c.get("size")]
    dominant_size = Counter(sizes).most_common(1)[0][0] if sizes else body_size

    inline = _render_inline(chars) if chars else line["text"]
    stripped = inline.strip()

    # A run of undecodable glyph placeholders at the line start is a bullet
    # marker drawn from a symbol font, not literal text (see regex comment).
    cid_prefix = _LEADING_CID_RUN_RE.match(stripped)
    if cid_prefix:
        return f"- {_CID_TOKEN_RE.sub('', stripped[cid_prefix.end():]).strip()}"
    stripped = _CID_TOKEN_RE.sub("", stripped).strip()

    bullet_match = _BULLET_RE.match(stripped)
    numbered_match = _NUMBERED_RE.match(stripped)

    if dominant_size in heading_sizes and not bullet_match and not numbered_match:
        level = heading_sizes[dominant_size]
        return f"{'#' * level} {_strip_emphasis_edges(stripped)}"

    if bullet_match:
        return f"- {stripped[bullet_match.end():].strip()}"

    if numbered_match:
        return f"{numbered_match.group(1)}. {stripped[numbered_match.end():].strip()}"

    return stripped


def _strip_emphasis_edges(text: str) -> str:
    # Headings read better without inline bold/italic markers (the heading
    # markup already conveys emphasis).
    return re.sub(r"\*\*?|__?", "", text).strip()


def _render_inline(chars: list[dict]) -> str:
    """Wrap runs of bold/italic characters in Markdown emphasis markers.

    Some PDF generators (reportlab included) don't draw an actual space
    glyph between words -- they just position the next glyph further along
    the line. pdfplumber's line/word extraction reconstructs those gaps as
    spaces for its `text` field, but the raw `chars` list has no such
    character, so a large enough x-gap between consecutive characters is
    treated as a word boundary here too.
    """
    out: list[str] = []
    run_text = ""
    run_bold = False
    run_italic = False
    prev_x1: Optional[float] = None

    def flush():
        nonlocal run_text
        if not run_text:
            return
        segment = run_text
        if run_bold and run_italic:
            segment = f"***{segment}***"
        elif run_bold:
            segment = f"**{segment}**"
        elif run_italic:
            segment = f"*{segment}*"
        out.append(segment)
        run_text = ""

    for ch in chars:
        font = ch.get("fontname", "") or ""
        is_bold = bool(_BOLD_RE.search(font))
        is_italic = bool(_ITALIC_RE.search(font))
        text = ch.get("text", "")
        size = ch.get("size") or 10

        gap = None if prev_x1 is None else ch["x0"] - prev_x1
        prev_x1 = ch.get("x1", prev_x1)

        if text.strip() == "":
            run_text += text
            continue

        # Word gaps end the current run (so a space never lands inside
        # emphasis markers) and are emitted as unformatted text between runs.
        if gap is not None and gap > size * 0.2:
            flush()
            out.append(" ")

        if (is_bold, is_italic) != (run_bold, run_italic) and run_text.strip():
            flush()
        run_bold, run_italic = is_bold, is_italic
        run_text += text

    flush()
    return "".join(out).strip()


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def _md_table(rows: list[list[Optional[str]]]) -> str:
    rows = [[cell if cell is not None else "" for cell in row] for row in rows]
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    def fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(c.replace("\n", " ").strip() for c in row) + " |"

    header, *body = rows
    lines = [fmt_row(header), "| " + " | ".join(["---"] * col_count) + " |"]
    lines.extend(fmt_row(r) for r in body)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------


def _render_image(page, img: dict) -> str:
    bbox = (
        max(img["x0"], 0),
        max(img["top"], 0),
        min(img["x1"], page.width),
        min(img["bottom"], page.height),
    )
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return ""
    cropped = page.crop(bbox)
    pil_image = cropped.to_image(resolution=150).original
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"![](data:image/png;base64,{encoded})"


# --------------------------------------------------------------------------
# Paragraph merging & cleanup
# --------------------------------------------------------------------------


def _merge_paragraphs(blocks: list[str]) -> list[str]:
    """Join consecutive plain-text lines into paragraphs; leave structural
    blocks (headings, list items, tables, images) as their own blocks."""
    merged: list[str] = []
    buffer: list[str] = []

    def flush():
        if buffer:
            merged.append(" ".join(buffer))
            buffer.clear()

    for block in blocks:
        is_structural = (
            block.startswith("#")
            or block.startswith("- ")
            or block.startswith("![")
            or block.startswith("|")
            or re.match(r"^\d+\.\s", block)
        )
        if is_structural:
            flush()
            merged.append(block)
        else:
            text = block.rstrip("-") if block.endswith("-") else block
            buffer.append(text)
    flush()
    return merged


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n" if text.strip() else ""
