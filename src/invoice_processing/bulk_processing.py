from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import logging
from pathlib import Path
import uuid
import zipfile

from invoice_processing.bulk_models import AttachmentStatus, BulkRunResult, PerFileOutcome, UploadedInvoiceFile
from invoice_processing.error_handling import classify_exception
from invoice_processing.exceptions import ExportError, NoInvoiceRowsError
from invoice_processing.exporters.bulk_public_excel import BulkPublicWorkbookExporter
from invoice_processing.exporters.internal_excel import InternalWorkbookExporter
from invoice_processing.parsers.invoice_parser import InvoiceParser
from invoice_processing.sheet_names import assign_sheet_names
from invoice_processing.upload_validation import unique_stored_filename, validate_uploaded_file, with_stored_filename


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int, str, str], None]


class BulkInvoiceProcessor:
    def __init__(
        self,
        parser: InvoiceParser | None = None,
        public_exporter: BulkPublicWorkbookExporter | None = None,
        internal_exporter: InternalWorkbookExporter | None = None,
    ) -> None:
        self.parser = parser or InvoiceParser()
        self.public_exporter = public_exporter or BulkPublicWorkbookExporter()
        self.internal_exporter = internal_exporter or InternalWorkbookExporter()

    def process(
        self,
        uploads: list[UploadedInvoiceFile],
        *,
        work_dir: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> BulkRunResult:
        if not uploads:
            raise ValueError("At least one uploaded file is required.")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:8]}"
        processed_at = datetime.now(timezone.utc)
        input_dir = work_dir / "uploads"
        artifact_dir = work_dir / "artifacts"
        input_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        outcomes: list[PerFileOutcome] = []
        input_paths: list[Path] = []
        used_stored_names: set[str] = set()
        total = len(uploads)

        for index, upload in enumerate(uploads, start=1):
            stored_filename = unique_stored_filename(upload, used_stored_names)
            upload = with_stored_filename(upload, stored_filename)
            input_path = input_dir / stored_filename
            input_path.write_bytes(upload.content)
            input_paths.append(input_path)

            self._progress(progress_callback, index, total, upload.filename, "Validating upload.")
            try:
                validate_uploaded_file(upload)

                self._progress(progress_callback, index, total, upload.filename, "Parsing invoice.")
                parsed_invoice = self.parser.parse(input_path)
                if not parsed_invoice.line_items:
                    raise NoInvoiceRowsError(f"No invoice item rows extracted from '{upload.filename}'.")

                outcomes.append(
                    PerFileOutcome(
                        upload=upload,
                        status="SUCCESS",
                        sheet_name="",
                        parsed_invoice=parsed_invoice,
                    )
                )
                LOGGER.info(
                    "Parsed %s with %s line item row(s)",
                    upload.filename,
                    len(parsed_invoice.line_items),
                )
                self._progress(progress_callback, index, total, upload.filename, "Parsed successfully.")
            except Exception as exc:
                LOGGER.exception("Failed to process uploaded file %s", upload.filename)
                outcomes.append(
                    PerFileOutcome(
                        upload=upload,
                        status="FAILED",
                        sheet_name="",
                        error=classify_exception(exc),
                    )
                )
                self._progress(progress_callback, index, total, upload.filename, "Captured failure.")

        outcomes = assign_sheet_names(outcomes)

        original_uploads_attachment_path, manifest_path, base_attachment_statuses = self._prepare_admin_artifacts(
            outcomes=outcomes,
            input_paths=input_paths,
            artifact_dir=artifact_dir,
        )

        outcomes = self._strip_uploaded_bytes(outcomes)
        public_path = artifact_dir / "etrade_team_invoice_workbook.xlsx"
        internal_path = artifact_dir / "etrade_internal_invoice_workbook.xlsx"

        try:
            self.public_exporter.export(outcomes, public_path)
        except Exception as exc:
            LOGGER.exception("Team workbook export failed; generating export-failure workbook")
            export_error = classify_exception(ExportError(str(exc)))
            outcomes = [
                replace(outcome, status="FAILED", parsed_invoice=None, error=export_error)
                for outcome in outcomes
            ]
            self.public_exporter.export(outcomes, public_path)

        public_bytes = public_path.read_bytes()
        attachment_statuses = [
            AttachmentStatus("Public/team workbook", public_path.name, "generated"),
            AttachmentStatus("Detailed/internal workbook", internal_path.name, "generated"),
            *base_attachment_statuses,
        ]

        run_result = BulkRunResult(
            run_id=run_id,
            processed_at=processed_at,
            outcomes=outcomes,
            public_workbook_path=public_path,
            internal_workbook_path=internal_path,
            public_workbook_bytes=public_bytes,
            internal_workbook_bytes=b"",
            original_uploads_attachment_path=original_uploads_attachment_path,
            attachment_manifest_path=manifest_path,
            attachment_statuses=attachment_statuses,
        )

        self.internal_exporter.export(run_result=run_result, output_path=internal_path)
        run_result.internal_workbook_bytes = internal_path.read_bytes()

        return run_result

    def _prepare_admin_artifacts(
        self,
        *,
        outcomes: list[PerFileOutcome],
        input_paths: list[Path],
        artifact_dir: Path,
    ) -> tuple[Path | None, Path, list[AttachmentStatus]]:
        manifest_path = artifact_dir / "attachment_manifest.txt"
        self._write_attachment_manifest(outcomes, manifest_path)

        statuses = [AttachmentStatus("Attachment manifest", manifest_path.name, "generated")]

        if len(input_paths) == 1:
            original_path = input_paths[0]
            statuses.append(AttachmentStatus("Original uploaded file", original_path.name, "available"))
            return original_path, manifest_path, statuses

        zip_path = artifact_dir / "original_uploads.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for input_path in input_paths:
                archive.write(input_path, arcname=input_path.name)

        statuses.append(AttachmentStatus("Original uploaded files", zip_path.name, "generated"))
        return zip_path, manifest_path, statuses

    def _write_attachment_manifest(self, outcomes: list[PerFileOutcome], manifest_path: Path) -> None:
        lines = [
            "Etrade bulk invoice processing attachment manifest",
            "",
            "Source File | Stored Filename | Sheet Name | Status | Size Bytes | Item Rows",
        ]
        for outcome in outcomes:
            lines.append(
                " | ".join(
                    [
                        outcome.upload.filename,
                        outcome.upload.stored_filename,
                        outcome.sheet_name,
                        outcome.status,
                        str(outcome.upload.size_bytes),
                        str(outcome.item_row_count),
                    ]
                )
            )
        manifest_path.write_text("\n".join(lines), encoding="utf-8")

    def _strip_uploaded_bytes(self, outcomes: list[PerFileOutcome]) -> list[PerFileOutcome]:
        stripped: list[PerFileOutcome] = []
        for outcome in outcomes:
            upload = replace(outcome.upload, content=b"")
            stripped.append(replace(outcome, upload=upload))
        return stripped

    def _progress(
        self,
        callback: ProgressCallback | None,
        index: int,
        total: int,
        filename: str,
        message: str,
    ) -> None:
        if callback:
            callback(index, total, filename, message)
