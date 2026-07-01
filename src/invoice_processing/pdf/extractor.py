from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber

from invoice_processing.config import TABLE_SETTINGS
from invoice_processing.exceptions import PdfReadError
from invoice_processing.models import PdfDocumentData, PdfPageData


class PdfExtractor:
    def __init__(self, table_settings: dict[str, Any] | None = None) -> None:
        self.table_settings = table_settings or TABLE_SETTINGS

    def extract(self, pdf_path: Path) -> PdfDocumentData:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = [
                    PdfPageData(
                        page_number=index + 1,
                        text=page.extract_text(x_tolerance=2, y_tolerance=3) or "",
                        words=page.extract_words(x_tolerance=2, y_tolerance=3) or [],
                        tables=page.extract_tables(table_settings=self.table_settings) or [],
                    )
                    for index, page in enumerate(pdf.pages)
                ]
        except Exception as exc:
            raise PdfReadError(f"Unable to read PDF '{pdf_path.name}': {exc}") from exc

        if not pages:
            raise PdfReadError(f"PDF '{pdf_path.name}' does not contain readable pages")

        return PdfDocumentData(path=pdf_path, page_count=len(pages), pages=pages)
