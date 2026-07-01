from __future__ import annotations

import re
from dataclasses import replace

from invoice_processing.bulk_models import PerFileOutcome


EXCEL_SHEET_NAME_LIMIT = 31
INVALID_EXCEL_SHEET_CHARS = r"[]:*?/\\"


def assign_sheet_names(outcomes: list[PerFileOutcome]) -> list[PerFileOutcome]:
    used: set[str] = {"processing summary"}
    assigned: list[PerFileOutcome] = []

    for index, outcome in enumerate(outcomes, start=1):
        base_name = _sheet_name_base(outcome, index)
        sheet_name = unique_sheet_name(base_name, used)
        assigned.append(replace(outcome, sheet_name=sheet_name))

    return assigned


def unique_sheet_name(base_name: str, used_names: set[str]) -> str:
    sanitized = sanitize_sheet_name(base_name) or "Invoice"
    candidate = sanitized[:EXCEL_SHEET_NAME_LIMIT]
    counter = 2

    while candidate.lower() in used_names:
        suffix = f"_{counter}"
        candidate = f"{sanitized[: EXCEL_SHEET_NAME_LIMIT - len(suffix)]}{suffix}"
        counter += 1

    used_names.add(candidate.lower())
    return candidate


def sanitize_sheet_name(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(f"[{re.escape(INVALID_EXCEL_SHEET_CHARS)}]", "_", text)
    text = re.sub(r"[\x00-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("'")
    return text[:EXCEL_SHEET_NAME_LIMIT]


def _sheet_name_base(outcome: PerFileOutcome, index: int) -> str:
    filename = outcome.upload.filename
    if filename:
        return filename

    return f"Invoice_{index:03d}"
