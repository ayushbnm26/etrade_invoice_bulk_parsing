from __future__ import annotations

from pathlib import Path
from typing import Any

from invoice_processing.bulk_models import BulkRunResult, EmailNotificationResult
from invoice_processing.emailer import SMTPConfig, send_email
from invoice_processing.exceptions import EmailDeliveryError
from invoice_processing.error_handling import safe_ui_warning


SMTP_SECRET_KEYS = ("HOST", "PORT", "USERNAME", "APP_PASSWORD", "FROM_EMAIL", "ADMIN_EMAIL")


def read_smtp_config_from_secrets(secrets: Any) -> tuple[SMTPConfig | None, str | None, str | None]:
    try:
        smtp_secrets = secrets.get("SMTP")
    except Exception:
        return None, None, "SMTP secrets are not configured."

    if not smtp_secrets:
        return None, None, "SMTP secrets are not configured."

    missing_keys = [key for key in SMTP_SECRET_KEYS if not str(smtp_secrets.get(key, "")).strip()]
    if missing_keys:
        return None, None, f"SMTP secrets are missing: {', '.join(missing_keys)}."

    try:
        port = int(smtp_secrets["PORT"])
    except (TypeError, ValueError):
        return None, None, "SMTP.PORT must be an integer."

    return (
        SMTPConfig(
            host=str(smtp_secrets["HOST"]).strip(),
            port=port,
            username=str(smtp_secrets["USERNAME"]).strip(),
            app_password=str(smtp_secrets["APP_PASSWORD"]).strip(),
            from_email=str(smtp_secrets["FROM_EMAIL"]).strip(),
        ),
        str(smtp_secrets["ADMIN_EMAIL"]).strip(),
        None,
    )


def send_bulk_admin_email(
    *,
    run_result: BulkRunResult,
    smtp_config: SMTPConfig | None,
    admin_email: str | None,
    config_error: str | None = None,
) -> EmailNotificationResult:
    if smtp_config is None or admin_email is None:
        message = config_error or "SMTP configuration is incomplete."
        return EmailNotificationResult(status="skipped", message=safe_ui_warning(message))

    attachment_paths = _available_attachment_paths(run_result)
    subject = (
        "Etrade bulk invoice run - "
        f"{run_result.successful_invoices} succeeded, {run_result.failed_invoices} failed - "
        f"{run_result.processed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    try:
        send_email(
            smtp_config,
            admin_email,
            subject,
            _email_body(run_result, attachment_paths),
            attachment_paths=attachment_paths,
        )
    except EmailDeliveryError as exc:
        return EmailNotificationResult(status="failed", message=safe_ui_warning(exc))
    except Exception as exc:
        return EmailNotificationResult(status="failed", message=safe_ui_warning(exc))

    return EmailNotificationResult(status="sent", message="Admin email sent.")


def _available_attachment_paths(run_result: BulkRunResult) -> list[Path]:
    candidates = [
        run_result.public_workbook_path,
        run_result.internal_workbook_path,
        run_result.log_path,
        run_result.original_uploads_attachment_path,
        run_result.attachment_manifest_path,
    ]
    return [path for path in candidates if path is not None and path.exists() and path.is_file()]


def _email_body(run_result: BulkRunResult, attachment_paths: list[Path]) -> str:
    failures = [
        f"- {outcome.upload.filename}: {outcome.error.error_type if outcome.error else 'ProcessingError'}"
        for outcome in run_result.outcomes
        if not outcome.succeeded
    ] or ["- None captured."]
    attachments = [f"- {path.name}" for path in attachment_paths] or ["- No attachments available."]

    return "\n".join(
        [
            "Etrade bulk invoice processing run completed.",
            "",
            f"Run ID: {run_result.run_id}",
            f"Processing timestamp: {run_result.processed_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"Total files uploaded: {run_result.total_files}",
            f"Successful invoices: {run_result.successful_invoices}",
            f"Failed invoices: {run_result.failed_invoices}",
            f"Total item rows extracted: {run_result.total_item_rows}",
            "",
            "Failure summary:",
            *failures,
            "",
            "Attachments:",
            *attachments,
            "",
            "Human verification required before finance, accounting, GST, reconciliation, reporting, "
            "payment, audit, or official business use.",
        ]
    )
