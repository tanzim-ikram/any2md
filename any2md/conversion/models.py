"""Conversion data models — UI-independent, reusable in web context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"

    @property
    def extension(self) -> str:
        return {
            OutputFormat.MARKDOWN: ".md",
            OutputFormat.PDF: ".pdf",
            OutputFormat.DOCX: ".docx",
            OutputFormat.HTML: ".html",
        }[self]

    @property
    def display_name(self) -> str:
        return {
            OutputFormat.MARKDOWN: "Markdown",
            OutputFormat.PDF: "PDF",
            OutputFormat.DOCX: "Word Document",
            OutputFormat.HTML: "HTML",
        }[self]


class ConversionStatus(str, Enum):
    WAITING = "waiting"
    CONVERTING = "converting"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


# Supported input extensions → display name
SUPPORTED_INPUT_FORMATS: dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".pptx": "PowerPoint",
    ".ppt": "PowerPoint",
    ".txt": "Text",
    ".html": "HTML",
    ".htm": "HTML",
    ".csv": "CSV",
    ".md": "Markdown",
}


@dataclass
class ConversionOptions:
    preserve_images: bool = False
    combine_files: bool = False
    custom_output_name: Optional[str] = None


@dataclass
class ConversionRequest:
    input_path: Path
    output_format: OutputFormat
    output_dir: Optional[Path] = None
    options: ConversionOptions = field(default_factory=ConversionOptions)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def input_extension(self) -> str:
        return self.input_path.suffix.lower()

    @property
    def output_path(self) -> Path:
        out_dir = self.output_dir or self.input_path.parent
        stem = self.options.custom_output_name or self.input_path.stem
        return out_dir / (stem + self.output_format.extension)

    def is_to_markdown(self) -> bool:
        return self.output_format == OutputFormat.MARKDOWN

    def is_from_markdown(self) -> bool:
        return self.input_extension == ".md"


@dataclass
class ConversionResult:
    request: ConversionRequest
    output_path: Path
    success: bool = True
    duration_ms: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConversionProgress:
    request_id: str
    filename: str
    percent: int  # 0–100
    status: ConversionStatus
    message: str = ""


@dataclass
class ConversionError:
    request: ConversionRequest
    user_message: str
    detail: str  # Full traceback — only shown in "View Details"
    error_code: str = "CONVERSION_FAILED"

    @property
    def request_id(self) -> str:
        return self.request.request_id

    @property
    def filename(self) -> str:
        return self.request.input_path.name
