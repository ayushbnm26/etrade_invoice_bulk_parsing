from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PdfPageData:
    page_number: int
    text: str
    words: list[dict[str, Any]]
    tables: list[list[list[Any]]]


@dataclass(frozen=True)
class PdfDocumentData:
    path: Path
    page_count: int
    pages: list[PdfPageData]

    @property
    def all_text(self) -> str:
        return "\n".join(page.text for page in self.pages if page.text)


@dataclass(frozen=True)
class ParsedInvoice:
    header: dict[str, Any]
    summary: dict[str, Any]
    line_items: list[dict[str, Any]]
    validation: dict[str, Any]


@dataclass
class BatchResult:
    headers: list[dict[str, Any]] = field(default_factory=list)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    line_items: list[dict[str, Any]] = field(default_factory=list)
    validations: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    output_path: Path | None = None
    public_output_paths: list[Path] = field(default_factory=list)
