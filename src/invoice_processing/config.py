from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = Path("input_pdfs")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_LOG_DIR = Path("logs")

TABLE_SETTINGS: dict[str, Any] = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 5,
    "edge_min_length": 3,
    "text_x_tolerance": 2,
    "text_y_tolerance": 3,
}

CANONICAL_TABLE_COLUMNS = [
    "si_no",
    "item_description",
    "hsn_sac",
    "asin_code",
    "upc_ean",
    "po_no",
    "vendor_invoice_no",
    "vendor_invoice_date",
    "return_id",
    "shipment_id",
    "qty",
    "price_per_unit",
    "net_amount",
    "tax_rate_raw",
    "tax_type_raw",
    "tax_amount_raw",
    "total_amount",
]

HEADER_COLUMNS = [
    "source_file",
    "document_type",
    "page_count",
    "invoice_reference_number",
    "invoice_number",
    "system_ref_no",
    "invoice_date",
    "credit_note_date",
    "due_date",
    "original_invoice_no",
    "original_invoice_date",
    "place_of_supply",
    "payment_method",
    "payment_term",
    "reason_for_issuing_credit_note",
    "shipment_ids_header",
    "billing_raw",
    "billing_name",
    "billing_address",
    "billing_state_code",
    "billing_gstin",
    "billing_pan",
    "receiver_billing_raw",
    "receiver_billing_name",
    "receiver_billing_address",
    "receiver_billing_state_code",
    "receiver_billing_gstin",
    "receiver_billing_pan",
    "shipping_raw",
    "shipping_name",
    "shipping_address",
    "shipping_state_code",
    "shipping_gstin",
    "shipping_pan",
    "receiver_shipping_raw",
    "receiver_shipping_name",
    "receiver_shipping_address",
    "receiver_shipping_state_code",
    "receiver_shipping_gstin",
    "receiver_shipping_pan",
]

LINE_ITEM_COLUMNS = [
    "source_file",
    "document_type",
    "invoice_number",
    "system_ref_no",
    "invoice_date",
    "page_no",
    *CANONICAL_TABLE_COLUMNS,
    "cgst_rate",
    "cgst_amount",
    "sgst_rate",
    "sgst_amount",
    "igst_rate",
    "igst_amount",
]

SUMMARY_COLUMNS = [
    "source_file",
    "invoice_number",
    "system_ref_no",
    "total_qty_pdf",
    "subtotal_pdf",
    "cgst_subtotal_pdf",
    "sgst_subtotal_pdf",
    "igst_subtotal_pdf",
    "currency",
    "grand_total_pdf",
    "total_tax_amount_words",
    "total_invoice_amount_words",
    "bank_beneficiary_name",
    "bank_account_number",
    "ifsc_code",
    "swift_code",
    "total_qty_from_items",
    "subtotal_from_items",
    "cgst_subtotal_from_items",
    "sgst_subtotal_from_items",
    "igst_subtotal_from_items",
    "grand_total_from_items",
]

VALIDATION_COLUMNS = [
    "source_file",
    "invoice_number",
    "system_ref_no",
    "line_count",
    "qty_sum_extracted",
    "total_sum_extracted",
    "qty_pdf",
    "grand_total_pdf",
    "status",
    "errors",
]

EXCEPTION_COLUMNS = [
    "source_file",
    "error_type",
    "error",
    "traceback",
]


@dataclass(frozen=True)
class AppConfig:
    input_dir: Path = DEFAULT_INPUT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    log_dir: Path = DEFAULT_LOG_DIR
    output_file: Path | None = None
    fail_fast: bool = False
    log_level: str = "INFO"

    def resolved(self) -> "AppConfig":
        input_dir = self.input_dir.resolve()
        output_dir = self.output_dir.resolve()
        log_dir = self.log_dir.resolve()
        output_file = self.output_file

        if output_file is None:
            output_file = output_dir / default_output_name()
        elif not output_file.is_absolute():
            output_file = (output_dir / output_file).resolve()

        return AppConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            log_dir=log_dir,
            output_file=output_file,
            fail_fast=self.fail_fast,
            log_level=self.log_level.upper(),
        )


def default_output_name(prefix: str = "parsed_invoices") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.xlsx"
