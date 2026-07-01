from __future__ import annotations

import hashlib
import logging
import secrets as secrets_lib
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from invoice_processing.bulk_emailer import read_smtp_config_from_secrets, send_bulk_admin_email  # noqa: E402
from invoice_processing.bulk_processing import BulkInvoiceProcessor  # noqa: E402
from invoice_processing.error_handling import safe_ui_warning  # noqa: E402
from invoice_processing.logging_config import capture_invoice_logs, flush_invoice_logs  # noqa: E402
from invoice_processing.upload_validation import build_uploaded_file  # noqa: E402


PAGE_TITLE = "Etrade Bulk Invoice Workbook Generator"
AUTH_SESSION_KEY = "etrade_bulk_authenticated"
RESULT_SESSION_KEY = "etrade_bulk_result"
UPLOAD_KEY_SESSION_KEY = "etrade_bulk_upload_key"
WORKBOOK_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LOGGER = logging.getLogger("invoice_processing.dashboard")

USAGE_NOTICE = """
This tool is designed specifically for Etrade invoice PDFs that follow the supported invoice layout pattern. It works best when uploaded PDFs have the same or very similar structure, table format, field placement, and text quality as the sample Etrade invoices used during development. Major changes in invoice design, column order, address placement, tax layout, scanned-image quality, or page structure can significantly reduce extraction accuracy. PDF text/table extraction is not guaranteed to be 100% accurate. Scanned-image PDFs or OCR-dependent documents may fail or be less reliable because this app is built around PDF text/table extraction. The generated Excel workbook must be verified by a human before it is used for finance, accounting, GST, reconciliation, reporting, payment, audit, or any official business process. Upload only supported Etrade invoice PDFs.
"""


@dataclass(frozen=True)
class BulkUiSettings:
    max_files_per_run: int = 30
    max_total_upload_mb: int = 200
    max_upload_size_mb: int = 200

    @property
    def max_total_upload_bytes(self) -> int:
        return self.max_total_upload_mb * 1024 * 1024


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="centered")
    st.title(PAGE_TITLE)

    if not _render_password_gate():
        return

    settings = _read_bulk_settings()
    st.warning(USAGE_NOTICE)

    uploaded_files = _render_bulk_file_uploader(settings)

    upload_payloads = _read_uploaded_files(uploaded_files or [])
    current_upload_key = _upload_key(upload_payloads)
    if st.session_state.get(UPLOAD_KEY_SESSION_KEY) != current_upload_key:
        st.session_state[UPLOAD_KEY_SESSION_KEY] = current_upload_key
        st.session_state.pop(RESULT_SESSION_KEY, None)

    total_size = sum(len(content) for _, content in upload_payloads)
    if upload_payloads:
        st.write(f"Uploaded files: {len(upload_payloads)}")
        st.write(f"Total upload size: {_format_bytes(total_size)}")

    limit_error = _limit_error(upload_payloads, total_size, settings)
    if limit_error:
        st.error(limit_error)
    elif len(upload_payloads) > max(10, int(settings.max_files_per_run * 0.75)):
        st.warning("Large batches can take longer to parse and email. Process in smaller batches if the app becomes slow.")

    process_clicked = st.button(
        "Generate Bulk Workbook",
        disabled=not upload_payloads or limit_error is not None,
        type="primary",
    )

    if process_clicked:
        st.session_state.pop(RESULT_SESSION_KEY, None)
        st.session_state[RESULT_SESSION_KEY] = _process_uploads(upload_payloads)

    result = st.session_state.get(RESULT_SESSION_KEY)
    if result:
        _render_result(result)


def _read_uploaded_files(uploaded_files: list[Any]) -> list[tuple[str, bytes]]:
    payloads: list[tuple[str, bytes]] = []
    for uploaded_file in uploaded_files:
        payloads.append((uploaded_file.name, uploaded_file.getvalue()))
    return payloads


def _render_bulk_file_uploader(settings: BulkUiSettings) -> list[Any]:
    uploader_kwargs: dict[str, Any] = {
        "label": "Upload Etrade invoice PDFs",
        "type": ["pdf"],
        "accept_multiple_files": True,
        "key": "etrade_bulk_invoice_uploads",
        "help": "Upload supported Etrade invoice PDFs only.",
    }

    try:
        uploaded_files = st.file_uploader(
            **uploader_kwargs,
            max_upload_size=settings.max_upload_size_mb,
        )
    except TypeError as exc:
        if "max_upload_size" not in str(exc):
            raise
        uploaded_files = st.file_uploader(**uploader_kwargs)

    return list(uploaded_files or [])


def _process_uploads(upload_payloads: list[tuple[str, bytes]]) -> dict[str, Any]:
    uploads = [
        build_uploaded_file(index, filename, content)
        for index, (filename, content) in enumerate(upload_payloads, start=1)
    ]

    with tempfile.TemporaryDirectory(prefix="etrade_bulk_invoice_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        log_dir = temp_dir / "logs"
        work_dir = temp_dir / "work"

        with capture_invoice_logs(log_dir) as log_path:
            with st.status("Processing uploaded invoices...", expanded=True) as status:
                progress_bar = st.progress(0.0)

                def progress(index: int, total: int, filename: str, message: str) -> None:
                    progress_bar.progress(index / total)
                    status.write(f"{index}/{total} - {filename}: {message}")

                try:
                    run_result = BulkInvoiceProcessor().process(
                        uploads,
                        work_dir=work_dir,
                        progress_callback=progress,
                    )
                    run_result.log_path = log_path
                    flush_invoice_logs()

                    smtp_config, admin_email, smtp_error = read_smtp_config_from_secrets(st.secrets)
                    email_result = send_bulk_admin_email(
                        run_result=run_result,
                        smtp_config=smtp_config,
                        admin_email=admin_email,
                        config_error=smtp_error,
                    )
                    if email_result.status == "sent":
                        status.update(label="Bulk workbook ready.", state="complete")
                    else:
                        status.update(label="Bulk workbook ready; admin email was not sent.", state="complete")
                except Exception as exc:
                    LOGGER.exception("Bulk dashboard processing failed")
                    status.update(label="Processing failed.", state="error")
                    return {
                        "ok": False,
                        "message": safe_ui_warning(exc),
                    }

                return {
                    "ok": True,
                    "download_name": run_result.public_workbook_path.name,
                    "workbook_bytes": run_result.public_workbook_bytes,
                    "total_files": run_result.total_files,
                    "successful_invoices": run_result.successful_invoices,
                    "failed_invoices": run_result.failed_invoices,
                    "total_item_rows": run_result.total_item_rows,
                    "email_status": email_result.status,
                    "email_message": email_result.message,
                }


def _render_result(result: dict[str, Any]) -> None:
    if not result.get("ok"):
        st.error(result.get("message") or "Processing failed.")
        return

    st.success("Team workbook generated successfully.")

    columns = st.columns(5)
    columns[0].metric("Total files uploaded", result["total_files"])
    columns[1].metric("Successful invoices", result["successful_invoices"])
    columns[2].metric("Failed invoices", result["failed_invoices"])
    columns[3].metric("Total item rows", result["total_item_rows"])
    columns[4].metric("Admin email", result["email_status"].upper())

    if result["email_status"] == "skipped":
        st.warning(f"Admin email skipped: {result['email_message']}")
    elif result["email_status"] == "failed":
        st.warning(f"Admin email failed: {result['email_message']}")

    st.info(
        "Verify the generated workbook manually before using it for finance, accounting, GST, "
        "reconciliation, reporting, payment, audit, or any official business process."
    )
    st.download_button(
        "Download Team Workbook",
        data=result["workbook_bytes"],
        file_name=result["download_name"],
        mime=WORKBOOK_MIME,
    )


def _render_password_gate() -> bool:
    app_password = _get_streamlit_secret("APP_PASSWORD")
    if not app_password:
        st.error("Application password is not configured. Ask the app owner to set APP_PASSWORD in Streamlit secrets.")
        return False

    if st.session_state.get(AUTH_SESSION_KEY):
        return True

    with st.form("app_password_gate", clear_on_submit=True):
        entered_password = st.text_input("App password", type="password")
        submitted = st.form_submit_button("Continue")

    if submitted:
        if secrets_lib.compare_digest(str(entered_password), app_password):
            st.session_state[AUTH_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect app password.")

    return False


def _get_streamlit_secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        return None

    text = str(value or "").strip()
    return text or None


def _read_bulk_settings() -> BulkUiSettings:
    try:
        bulk_secrets = st.secrets.get("BULK", {})
    except Exception:
        bulk_secrets = {}

    return BulkUiSettings(
        max_files_per_run=_positive_int(bulk_secrets.get("MAX_FILES_PER_RUN"), 30),
        max_total_upload_mb=_positive_int(bulk_secrets.get("MAX_TOTAL_UPLOAD_MB"), 200),
        max_upload_size_mb=_positive_int(bulk_secrets.get("MAX_UPLOAD_SIZE_MB"), 200),
    )


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _limit_error(upload_payloads: list[tuple[str, bytes]], total_size: int, settings: BulkUiSettings) -> str | None:
    if len(upload_payloads) > settings.max_files_per_run:
        return f"Too many files uploaded. Maximum files per run: {settings.max_files_per_run}."
    if total_size > settings.max_total_upload_bytes:
        return f"Total upload size exceeds {_format_bytes(settings.max_total_upload_bytes)}."
    return None


def _upload_key(upload_payloads: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for filename, content in upload_payloads:
        digest.update(filename.encode("utf-8", errors="replace"))
        digest.update(str(len(content)).encode("ascii"))
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    main()
