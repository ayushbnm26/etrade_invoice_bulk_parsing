from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from invoice_processing.bulk_models import UploadedInvoiceFile
from invoice_processing.exceptions import EmptyFileError, PdfSignatureError, UploadValidationError


PDF_SIGNATURE = b"%PDF"


def build_uploaded_file(upload_index: int, filename: str, content: bytes) -> UploadedInvoiceFile:
    safe_name = safe_upload_filename(filename)
    return UploadedInvoiceFile(
        upload_index=upload_index,
        filename=safe_name,
        content=content,
        size_bytes=len(content),
    )


def validate_uploaded_file(upload: UploadedInvoiceFile) -> None:
    if Path(upload.filename).suffix.lower() != ".pdf":
        raise UploadValidationError("Uploaded file is not a PDF.")
    if upload.size_bytes <= 0 or not upload.content:
        raise EmptyFileError("Uploaded PDF is empty.")
    if not upload.content.startswith(PDF_SIGNATURE):
        raise PdfSignatureError("Uploaded file has an invalid PDF signature.")


def safe_upload_filename(filename: str) -> str:
    cleaned = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "uploaded_invoice.pdf"


def with_stored_filename(upload: UploadedInvoiceFile, stored_filename: str) -> UploadedInvoiceFile:
    return replace(upload, stored_filename=stored_filename)


def unique_stored_filename(upload: UploadedInvoiceFile, used_names: set[str]) -> str:
    name = safe_upload_filename(upload.filename)
    stem = Path(name).stem or f"invoice_{upload.upload_index:03d}"
    suffix = Path(name).suffix or ".pdf"
    candidate = f"{upload.upload_index:03d}_{stem}{suffix}"
    counter = 2

    while candidate.lower() in used_names:
        candidate = f"{upload.upload_index:03d}_{stem}_{counter}{suffix}"
        counter += 1

    used_names.add(candidate.lower())
    return candidate
