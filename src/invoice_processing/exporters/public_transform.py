from __future__ import annotations

import re
from typing import Any


KNOWN_PUBLIC_TAX_TYPES = ("cgst", "sgst", "igst")

PUBLIC_ITEM_COLUMNS: list[tuple[str, str]] = [
    ("Invoice Number", "invoice_number"),
    ("System Reference Number", "system_ref_no"),
    ("ASIN", "asin_code"),
    ("Quantity", "qty"),
    ("Price / Unit", "price_per_unit"),
    ("Net Amount", "net_amount"),
    ("CGST Rate", "cgst_rate"),
    ("CGST Amount", "cgst_amount"),
    ("SGST Rate", "sgst_rate"),
    ("SGST Amount", "sgst_amount"),
    ("IGST Rate", "igst_rate"),
    ("IGST Amount", "igst_amount"),
    ("Other Tax Type", "other_tax_type"),
    ("Other Tax Rate", "other_tax_rate"),
    ("Other Tax Amount", "other_tax_amount"),
    ("Total Amount", "total_amount"),
]

PUBLIC_COLUMN_LABELS = [label for label, _ in PUBLIC_ITEM_COLUMNS]
PUBLIC_RATE_FIELDS = {"cgst_rate", "sgst_rate", "igst_rate", "other_tax_rate"}
PUBLIC_AMOUNT_FIELDS = {
    "price_per_unit",
    "net_amount",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "other_tax_amount",
    "total_amount",
}


def public_item_record(item: dict[str, Any], header: dict[str, Any] | None = None) -> dict[str, Any]:
    public_item = dict(item)
    header = header or {}

    public_item["invoice_number"] = public_item.get("invoice_number") or header.get("invoice_number") or ""
    public_item["system_ref_no"] = public_item.get("system_ref_no") or header.get("system_ref_no") or ""

    tax_type_raw = str(item.get("tax_type_raw") or "").upper()

    for tax_type in KNOWN_PUBLIC_TAX_TYPES:
        if public_item.get(f"{tax_type}_rate") is None and tax_type.upper() in tax_type_raw:
            public_item[f"{tax_type}_rate"] = item.get("tax_rate_raw")
        if public_item.get(f"{tax_type}_amount") is None and tax_type.upper() in tax_type_raw:
            public_item[f"{tax_type}_amount"] = item.get("tax_amount_raw")

    tax_tokens = re.findall(r"[A-Z][A-Z0-9]*", tax_type_raw)
    known_tokens = {tax_type.upper() for tax_type in KNOWN_PUBLIC_TAX_TYPES}
    other_tax_tokens = [token for token in tax_tokens if token not in known_tokens]
    has_known_tax_amount = any(public_item.get(f"{tax_type}_amount") is not None for tax_type in KNOWN_PUBLIC_TAX_TYPES)

    public_item["other_tax_type"] = " ".join(other_tax_tokens)
    public_item["other_tax_rate"] = item.get("tax_rate_raw") if other_tax_tokens and not has_known_tax_amount else None
    public_item["other_tax_amount"] = item.get("tax_amount_raw") if other_tax_tokens and not has_known_tax_amount else None

    return {field_name: public_item.get(field_name, "") for _, field_name in PUBLIC_ITEM_COLUMNS}
