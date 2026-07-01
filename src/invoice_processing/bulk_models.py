from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from invoice_processing.models import ParsedInvoice


ProcessingStatus = Literal["SUCCESS", "FAILED"]
EmailStatus = Literal["sent", "skipped", "failed"]


@dataclass(frozen=True)
class UploadedInvoiceFile:
    upload_index: int
    filename: str
    content: bytes = field(repr=False)
    size_bytes: int
    stored_filename: str = ""


@dataclass(frozen=True)
class ProcessingErrorInfo:
    error_type: str
    message: str
    likely_reason: str
    traceback: str = ""
    raw_error: str = ""


@dataclass(frozen=True)
class PerFileOutcome:
    upload: UploadedInvoiceFile
    status: ProcessingStatus
    sheet_name: str
    parsed_invoice: ParsedInvoice | None = None
    error: ProcessingErrorInfo | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCESS" and self.parsed_invoice is not None

    @property
    def item_row_count(self) -> int:
        if not self.parsed_invoice:
            return 0
        return len(self.parsed_invoice.line_items)

    @property
    def invoice_number(self) -> str:
        if not self.parsed_invoice:
            return ""
        return str(self.parsed_invoice.header.get("invoice_number") or "")

    @property
    def system_ref_no(self) -> str:
        if not self.parsed_invoice:
            return ""
        return str(self.parsed_invoice.header.get("system_ref_no") or "")


@dataclass(frozen=True)
class AttachmentStatus:
    label: str
    filename: str
    status: str
    detail: str = ""


@dataclass
class BulkRunResult:
    run_id: str
    processed_at: datetime
    outcomes: list[PerFileOutcome]
    public_workbook_path: Path
    internal_workbook_path: Path
    public_workbook_bytes: bytes = field(repr=False)
    internal_workbook_bytes: bytes = field(repr=False)
    original_uploads_attachment_path: Path | None = None
    attachment_manifest_path: Path | None = None
    log_path: Path | None = None
    attachment_statuses: list[AttachmentStatus] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.outcomes)

    @property
    def successful_invoices(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.succeeded)

    @property
    def failed_invoices(self) -> int:
        return self.total_files - self.successful_invoices

    @property
    def total_item_rows(self) -> int:
        return sum(outcome.item_row_count for outcome in self.outcomes)

    def summary_record(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "processed_at": self.processed_at.isoformat(),
            "total_files_uploaded": self.total_files,
            "successful_invoices": self.successful_invoices,
            "failed_invoices": self.failed_invoices,
            "total_item_rows_extracted": self.total_item_rows,
        }


@dataclass(frozen=True)
class EmailNotificationResult:
    status: EmailStatus
    message: str
