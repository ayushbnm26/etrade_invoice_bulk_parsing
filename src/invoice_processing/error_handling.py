from __future__ import annotations

import re
import traceback
from typing import Any

from invoice_processing.bulk_models import ProcessingErrorInfo
from invoice_processing.exceptions import (
    EmptyFileError,
    ExportError,
    InvoiceParseError,
    NoInvoiceRowsError,
    PdfReadError,
    PdfSignatureError,
    UnsupportedLayoutError,
    UploadValidationError,
)


PUBLIC_ACTION_NOTE = "Please verify the PDF manually and retry with a supported Etrade invoice layout."


def classify_exception(exc: Exception, *, include_traceback: bool = True) -> ProcessingErrorInfo:
    error_type = _safe_error_type(exc)
    raw_error = str(exc).strip()
    safe_message = sanitize_public_message(raw_error or "No additional details were provided.")
    likely_reason = _likely_reason(exc, raw_error)
    trace = traceback.format_exc() if include_traceback else ""

    return ProcessingErrorInfo(
        error_type=error_type,
        message=safe_message,
        likely_reason=likely_reason,
        traceback=trace if trace and trace != "NoneType: None\n" else "",
        raw_error=raw_error,
    )


def sanitize_public_message(message: Any, *, max_length: int = 360) -> str:
    text = " ".join(str(message or "").split())
    text = re.sub(r"Traceback \(most recent call last\):.*", "Internal processing details were captured for admin review.", text)
    text = re.sub(r"[A-Za-z]:\\[^\s,;]+", "[local path redacted]", text)
    text = re.sub(r"/(?:tmp|var|home|users|Users)/[^\s,;]+", "[local path redacted]", text)
    text = re.sub(r"(?i)(app_password|password|smtp_password|token|secret)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    text = text.strip()

    if not text:
        return "No additional details were provided."
    if len(text) > max_length:
        return f"{text[: max_length - 3].rstrip()}..."
    return text


def safe_ui_warning(message: Any) -> str:
    return sanitize_public_message(message, max_length=220)


def _safe_error_type(exc: Exception) -> str:
    if isinstance(exc, PdfSignatureError):
        return "PdfSignatureError"
    if isinstance(exc, EmptyFileError):
        return "EmptyFileError"
    if isinstance(exc, UploadValidationError):
        return "UploadValidationError"
    if isinstance(exc, PdfReadError):
        return "PdfReadError"
    if isinstance(exc, NoInvoiceRowsError):
        return "NoInvoiceRowsError"
    if isinstance(exc, UnsupportedLayoutError):
        return "UnsupportedLayoutError"
    if isinstance(exc, InvoiceParseError):
        return "UnsupportedLayoutError"
    if isinstance(exc, ExportError):
        return "ExportError"
    return "UnexpectedProcessingError"


def _likely_reason(exc: Exception, raw_error: str) -> str:
    lower = raw_error.lower()

    if isinstance(exc, EmptyFileError):
        return "empty PDF"
    if isinstance(exc, PdfSignatureError):
        return "invalid PDF signature"
    if isinstance(exc, UploadValidationError):
        return "not a PDF"
    if isinstance(exc, NoInvoiceRowsError) or "no invoice table rows" in lower:
        return "no invoice item rows extracted"
    if isinstance(exc, UnsupportedLayoutError) and "no readable text" in lower:
        return "scanned/OCR-dependent PDF unsupported"
    if isinstance(exc, UnsupportedLayoutError) or isinstance(exc, InvoiceParseError):
        return "unsupported/wrong invoice layout"
    if isinstance(exc, PdfReadError):
        if "does not contain readable pages" in lower:
            return "empty PDF"
        return "unreadable PDF"
    if isinstance(exc, ExportError):
        return "workbook/export failure"
    return "unexpected processing failure"
