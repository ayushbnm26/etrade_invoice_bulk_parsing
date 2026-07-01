from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

from invoice_processing.config import CANONICAL_TABLE_COLUMNS, HEADER_COLUMNS, SUMMARY_COLUMNS
from invoice_processing.exceptions import NoInvoiceRowsError, UnsupportedLayoutError
from invoice_processing.models import ParsedInvoice, PdfDocumentData
from invoice_processing.parsers.address import extract_addresses
from invoice_processing.parsers.common import (
    clean_inline,
    compact_alnum,
    compact_code,
    dedupe_repeated_phrase,
    first_number_after,
    normalise_table_row,
    parse_amount,
    parse_int,
    parse_tax_fields,
    regex_value,
)
from invoice_processing.pdf.extractor import PdfExtractor
from invoice_processing.validators import calculate_item_totals, validate_invoice


DATE_PATTERN = r"\d{1,2}-[A-Za-z]{3}-\d{4}"
AMOUNT_PATTERN = r"\d[\d,]*(?:\.\d{1,2})?"


@dataclass
class RawLineItem:
    page_no: int
    cells: list[str]


class InvoiceParser:
    def __init__(self, extractor: PdfExtractor | None = None) -> None:
        self.extractor = extractor or PdfExtractor()

    def parse(self, pdf_path: Path) -> ParsedInvoice:
        document = self.extractor.extract(pdf_path)
        if not document.all_text.strip():
            raise UnsupportedLayoutError(f"No readable text found in '{pdf_path.name}'")

        header = self._parse_header(document)
        raw_items, summary_from_tables = self._extract_raw_items_and_summary(document)
        if not raw_items:
            raise NoInvoiceRowsError(f"No invoice table rows found in '{pdf_path.name}'")

        line_items = [self._build_line_item(raw_item, header) for raw_item in raw_items]
        summary = self._parse_summary(document, header, line_items, summary_from_tables)
        validation = validate_invoice(
            source_file=header["source_file"],
            invoice_number=header["invoice_number"],
            system_ref_no=header["system_ref_no"],
            items=line_items,
            summary=summary,
        )

        return ParsedInvoice(
            header=self._ordered_record(header, HEADER_COLUMNS),
            summary=self._ordered_record(summary, SUMMARY_COLUMNS),
            line_items=line_items,
            validation=validation,
        )

    def _parse_header(self, document: PdfDocumentData) -> dict[str, Any]:
        text = document.all_text
        first_page = document.pages[0]
        document_type = regex_value(r"\b(GST Invoice|Tax Invoice|Credit Note|Debit Note)\b", text) or "Invoice"
        shipment_id = regex_value(r"Shipment ID\s*:\s*([A-Za-z0-9,\s-]+?)(?:\s+Payment Term|\n|$)", text)

        header: dict[str, Any] = {
            "source_file": document.path.name,
            "document_type": document_type,
            "page_count": document.page_count,
            "invoice_reference_number": regex_value(r"Invoice Reference Number\s*:\s*([A-Za-z0-9]+)", text),
            "invoice_number": regex_value(r"Invoice Number\s*:\s*([A-Za-z0-9\-/]+)", text),
            "system_ref_no": regex_value(r"System Ref No\s*:\s*([A-Za-z0-9\-/]+)", text, flags=re.I),
            "invoice_date": regex_value(rf"Invoice Date\s*:\s*({DATE_PATTERN})", text),
            "credit_note_date": regex_value(rf"Credit Note Date\s*:\s*({DATE_PATTERN})", text),
            "due_date": regex_value(rf"Due Date\s*:\s*({DATE_PATTERN})", text),
            "original_invoice_no": regex_value(r"Original Invoice No\s*:\s*([A-Za-z0-9\-/]+)", text),
            "original_invoice_date": regex_value(rf"Original Invoice Date\s*:\s*({DATE_PATTERN})", text),
            "place_of_supply": regex_value(r"Place of Supply\s*:\s*([^\n]+)", text),
            "payment_method": regex_value(r"Payment Method\s*:\s*(.*?)(?:\n|Shipment ID|Payment Term|$)", text),
            "payment_term": regex_value(r"Payment Term\s*:\s*([^\n]+)", text),
            "reason_for_issuing_credit_note": regex_value(
                r"Reason for issuing credit note\s*:\s*([^\n]+)",
                text,
            ),
            "shipment_ids_header": compact_alnum(shipment_id),
        }
        header.update(extract_addresses(first_page.words))
        return header

    def _extract_raw_items_and_summary(
        self,
        document: PdfDocumentData,
    ) -> tuple[list[RawLineItem], dict[str, Any]]:
        raw_items: list[RawLineItem] = []
        current_item: RawLineItem | None = None
        summary_values: dict[str, Any] = {}

        for page in document.pages:
            for table in page.tables:
                for row in table:
                    cells = normalise_table_row(row, CANONICAL_TABLE_COLUMNS)
                    if self._is_header_row(cells):
                        continue

                    self._capture_summary_from_row(cells, summary_values)
                    if self._is_summary_row(cells):
                        continue

                    si_no = self._parse_si_no(cells[0])
                    if si_no is not None:
                        current_item = RawLineItem(page_no=page.page_number, cells=cells)
                        raw_items.append(current_item)
                    elif current_item and self._is_continuation_row(cells):
                        current_item.cells = self._merge_continuation(current_item.cells, cells)

        return raw_items, summary_values

    def _is_header_row(self, cells: list[str]) -> bool:
        joined = clean_inline(" ".join(cells)).lower()
        return "item description" in joined and "tax" in joined and "total" in joined

    def _is_summary_row(self, cells: list[str]) -> bool:
        joined = clean_inline(" ".join(cells)).lower()
        return any(label in joined for label in ("total qty", "subtotal", "currency:", "total:"))

    def _is_continuation_row(self, cells: list[str]) -> bool:
        joined = clean_inline(" ".join(cells))
        return bool(joined) and self._parse_si_no(cells[0]) is None and not self._is_summary_row(cells)

    def _merge_continuation(self, base: list[str], continuation: list[str]) -> list[str]:
        merged = base[:]
        for index, value in enumerate(continuation):
            value = clean_inline(value)
            if not value or index == 0:
                continue
            merged[index] = f"{merged[index]}\n{value}".strip() if merged[index] else value
        return merged

    def _parse_si_no(self, value: Any) -> int | None:
        text = clean_inline(value)
        if not re.fullmatch(r"\d+", text):
            return None
        return parse_int(text)

    def _capture_summary_from_row(self, cells: list[str], summary_values: dict[str, Any]) -> None:
        for index, cell in enumerate(cells):
            label = clean_inline(cell).lower()
            if not label:
                continue

            if "total qty" in label:
                summary_values["total_qty_pdf"] = first_number_after(cells, index, integer=True)
            elif label == "subtotal:":
                summary_values["subtotal_pdf"] = first_number_after(cells, index)
            elif "subtotal for" in label:
                amount = first_number_after(cells, index)
                for tax_type in ("cgst", "sgst", "igst"):
                    if tax_type in label:
                        summary_values[f"{tax_type}_subtotal_pdf"] = amount

    def _build_line_item(self, raw_item: RawLineItem, header: dict[str, Any]) -> dict[str, Any]:
        cells = raw_item.cells
        tax_fields = parse_tax_fields(cells[13], cells[14], cells[15])

        return {
            "source_file": header.get("source_file", ""),
            "document_type": header.get("document_type", ""),
            "invoice_number": header.get("invoice_number", ""),
            "system_ref_no": header.get("system_ref_no", ""),
            "invoice_date": header.get("invoice_date", ""),
            "page_no": raw_item.page_no,
            "si_no": self._parse_si_no(cells[0]),
            "item_description": clean_inline(cells[1]),
            "hsn_sac": compact_alnum(cells[2]),
            "asin_code": compact_alnum(cells[3]),
            "upc_ean": compact_alnum(cells[4]),
            "po_no": compact_alnum(cells[5]),
            "vendor_invoice_no": compact_code(cells[6]),
            "vendor_invoice_date": compact_code(cells[7]),
            "return_id": compact_alnum(cells[8]),
            "shipment_id": compact_alnum(cells[9]),
            "qty": parse_int(cells[10]),
            "price_per_unit": parse_amount(cells[11]),
            "net_amount": parse_amount(cells[12]),
            "tax_rate_raw": parse_amount(cells[13]),
            "tax_type_raw": clean_inline(cells[14]).upper(),
            "tax_amount_raw": parse_amount(cells[15]),
            "total_amount": parse_amount(cells[16]),
            **tax_fields,
        }

    def _parse_summary(
        self,
        document: PdfDocumentData,
        header: dict[str, Any],
        line_items: list[dict[str, Any]],
        summary_from_tables: dict[str, Any],
    ) -> dict[str, Any]:
        text = document.all_text
        item_totals = calculate_item_totals(line_items)
        total_tax_words = regex_value(
            r"Total Tax amount in words\s*:\s*(.*?)\s+Total Invoice amount in words\s*:",
            text,
        )
        total_invoice_words = regex_value(
            r"Total Invoice amount in words\s*:\s*(.*?)(?:\s+E\s*&\s*OE|\s+Authorized|\s+Please send)",
            text,
        )

        summary: dict[str, Any] = {
            "source_file": header.get("source_file", ""),
            "invoice_number": header.get("invoice_number", ""),
            "system_ref_no": header.get("system_ref_no", ""),
            "total_qty_pdf": summary_from_tables.get("total_qty_pdf")
            or parse_int(regex_value(r"Total Qty\s*:\s*([0-9,]+)", text)),
            "subtotal_pdf": summary_from_tables.get("subtotal_pdf")
            or parse_amount(regex_value(rf"(?m)^Subtotal\s*:\s*({AMOUNT_PATTERN})", text)),
            "cgst_subtotal_pdf": summary_from_tables.get("cgst_subtotal_pdf")
            or self._extract_tax_subtotal(text, "CGST"),
            "sgst_subtotal_pdf": summary_from_tables.get("sgst_subtotal_pdf")
            or self._extract_tax_subtotal(text, "SGST"),
            "igst_subtotal_pdf": summary_from_tables.get("igst_subtotal_pdf")
            or self._extract_tax_subtotal(text, "IGST"),
            "currency": regex_value(r"Currency\s*:\s*([A-Z]{3})", text),
            "grand_total_pdf": parse_amount(
                regex_value(rf"Currency\s*:\s*[A-Z]{{3}}\s+Total\s*:\s*({AMOUNT_PATTERN})", text)
            )
            or parse_amount(regex_value(rf"\bTotal\s*:\s*({AMOUNT_PATTERN})", text)),
            "total_tax_amount_words": total_tax_words,
            "total_invoice_amount_words": total_invoice_words,
            "bank_beneficiary_name": dedupe_repeated_phrase(
                regex_value(r"Beneficiary Name\s*:\s*(.*?)\s+Account Number\s*:", text)
            ),
            "bank_account_number": regex_value(r"Account Number\s*:\s*([0-9]+)", text),
            "ifsc_code": regex_value(r"IFSC Code\s*:\s*([A-Z0-9]+)", text),
            "swift_code": regex_value(r"Swift code\s*-\s*([A-Z0-9]+)", text),
            **item_totals,
        }
        return summary

    def _extract_tax_subtotal(self, text: str, tax_type: str) -> float | None:
        after_label = regex_value(rf"Subtotal for\s+{tax_type}\s*:\s*({AMOUNT_PATTERN})", text)
        if after_label:
            return parse_amount(after_label)

        before_label = regex_value(rf"Subtotal for\s+({AMOUNT_PATTERN})\s+{tax_type}\s*:", text)
        if before_label:
            return parse_amount(before_label)

        return None

    def _ordered_record(self, record: dict[str, Any], columns: list[str]) -> dict[str, Any]:
        ordered = {column: record.get(column, "") for column in columns}
        for key, value in record.items():
            if key not in ordered:
                ordered[key] = value
        return ordered
