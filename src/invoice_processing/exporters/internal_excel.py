from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from invoice_processing.bulk_models import AttachmentStatus, BulkRunResult, PerFileOutcome
from invoice_processing.config import HEADER_COLUMNS, LINE_ITEM_COLUMNS, SUMMARY_COLUMNS, VALIDATION_COLUMNS
from invoice_processing.exceptions import ExportError


EXCEPTION_COLUMNS = [
    "source_file",
    "sheet_name",
    "status",
    "error_type",
    "safe_error_message",
    "likely_reason",
    "raw_error",
    "traceback",
]

INPUT_FILE_COLUMNS = [
    "upload_index",
    "source_file",
    "stored_filename",
    "size_bytes",
    "status",
    "sheet_name",
    "invoice_number",
    "system_ref_no",
    "item_rows",
]

ATTACHMENT_COLUMNS = ["label", "filename", "status", "detail"]


class InternalWorkbookExporter:
    def export(
        self,
        *,
        run_result: BulkRunResult,
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        outcomes = run_result.outcomes

        frames = {
            "Run_Summary": self._run_summary_frame(run_result),
            "Input_Files": self._input_files_frame(outcomes),
            "Invoice_Header": self._frame(self._headers(outcomes), HEADER_COLUMNS),
            "Invoice_Line_Items": self._frame(self._line_items(outcomes), LINE_ITEM_COLUMNS),
            "Invoice_Summary": self._frame(self._summaries(outcomes), SUMMARY_COLUMNS),
            "Validation": self._frame(self._validations(outcomes), VALIDATION_COLUMNS),
            "Exceptions": self._frame(self._exceptions(outcomes), EXCEPTION_COLUMNS),
            "Attachment_Status": self._frame(self._attachments(run_result.attachment_statuses), ATTACHMENT_COLUMNS),
        }

        try:
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                for sheet_name, frame in frames.items():
                    frame.to_excel(writer, sheet_name=sheet_name, index=False)

                for worksheet in writer.sheets.values():
                    worksheet.freeze_panes = "A2"
                    worksheet.sheet_view.showGridLines = False
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            value = cell.value
                            if value is None:
                                continue
                            parts = str(value).splitlines() or [""]
                            max_length = max(max_length, *(len(part) for part in parts))
                        worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 10), 80)
        except Exception as exc:
            raise ExportError(f"Unable to write internal workbook '{output_path.name}': {exc}") from exc

        return output_path

    def _run_summary_frame(self, run_result: BulkRunResult) -> pd.DataFrame:
        rows = [
            {"Metric": "Run ID", "Value": run_result.run_id},
            {"Metric": "Processed At", "Value": run_result.processed_at.isoformat()},
            {"Metric": "Total Files Uploaded", "Value": run_result.total_files},
            {"Metric": "Successful Invoices", "Value": run_result.successful_invoices},
            {"Metric": "Failed Invoices", "Value": run_result.failed_invoices},
            {"Metric": "Total Item Rows Extracted", "Value": run_result.total_item_rows},
            {"Metric": "Public Workbook", "Value": run_result.public_workbook_path.name},
            {"Metric": "Internal Workbook", "Value": run_result.internal_workbook_path.name},
        ]
        return pd.DataFrame(rows)

    def _input_files_frame(self, outcomes: list[PerFileOutcome]) -> pd.DataFrame:
        rows = [
            {
                "upload_index": outcome.upload.upload_index,
                "source_file": outcome.upload.filename,
                "stored_filename": outcome.upload.stored_filename,
                "size_bytes": outcome.upload.size_bytes,
                "status": outcome.status,
                "sheet_name": outcome.sheet_name,
                "invoice_number": outcome.invoice_number,
                "system_ref_no": outcome.system_ref_no,
                "item_rows": outcome.item_row_count,
            }
            for outcome in outcomes
        ]
        return self._frame(rows, INPUT_FILE_COLUMNS)

    def _headers(self, outcomes: list[PerFileOutcome]) -> list[dict[str, Any]]:
        return [outcome.parsed_invoice.header for outcome in outcomes if outcome.parsed_invoice]

    def _line_items(self, outcomes: list[PerFileOutcome]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for outcome in outcomes:
            if outcome.parsed_invoice:
                rows.extend(outcome.parsed_invoice.line_items)
        return rows

    def _summaries(self, outcomes: list[PerFileOutcome]) -> list[dict[str, Any]]:
        return [outcome.parsed_invoice.summary for outcome in outcomes if outcome.parsed_invoice]

    def _validations(self, outcomes: list[PerFileOutcome]) -> list[dict[str, Any]]:
        return [outcome.parsed_invoice.validation for outcome in outcomes if outcome.parsed_invoice]

    def _exceptions(self, outcomes: list[PerFileOutcome]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for outcome in outcomes:
            if not outcome.error:
                continue
            rows.append(
                {
                    "source_file": outcome.upload.filename,
                    "sheet_name": outcome.sheet_name,
                    "status": outcome.status,
                    "error_type": outcome.error.error_type,
                    "safe_error_message": outcome.error.message,
                    "likely_reason": outcome.error.likely_reason,
                    "raw_error": outcome.error.raw_error,
                    "traceback": outcome.error.traceback,
                }
            )
        return rows

    def _attachments(self, attachment_statuses: list[AttachmentStatus]) -> list[dict[str, Any]]:
        return [
            {
                "label": attachment.label,
                "filename": attachment.filename,
                "status": attachment.status,
                "detail": attachment.detail,
            }
            for attachment in attachment_statuses
        ]

    def _frame(self, rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        for column in columns:
            if column not in frame.columns:
                frame[column] = pd.NA
        extra_columns = [column for column in frame.columns if column not in columns]
        return frame[columns + extra_columns]
