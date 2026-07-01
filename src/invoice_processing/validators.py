from __future__ import annotations

from typing import Any

from invoice_processing.parsers.common import parse_amount, parse_int


def calculate_item_totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    def sum_numbers(key: str) -> float:
        return round(sum(float(item.get(key) or 0) for item in items), 2)

    return {
        "total_qty_from_items": int(sum(int(item.get("qty") or 0) for item in items)),
        "subtotal_from_items": sum_numbers("net_amount"),
        "cgst_subtotal_from_items": sum_numbers("cgst_amount"),
        "sgst_subtotal_from_items": sum_numbers("sgst_amount"),
        "igst_subtotal_from_items": sum_numbers("igst_amount"),
        "grand_total_from_items": sum_numbers("total_amount"),
    }


def validate_invoice(
    source_file: str,
    invoice_number: str,
    system_ref_no: str,
    items: list[dict[str, Any]],
    summary: dict[str, Any],
    tolerance: float = 0.01,
) -> dict[str, Any]:
    item_totals = calculate_item_totals(items)
    qty_pdf = parse_int(summary.get("total_qty_pdf"))
    grand_total_pdf = parse_amount(summary.get("grand_total_pdf"))
    errors: list[str] = []

    if not items:
        errors.append("No line items extracted")

    if qty_pdf is None:
        errors.append("PDF total quantity missing")
    elif qty_pdf != item_totals["total_qty_from_items"]:
        errors.append(
            f"Quantity mismatch: PDF={qty_pdf}, extracted={item_totals['total_qty_from_items']}"
        )

    if grand_total_pdf is None:
        errors.append("PDF grand total missing")
    elif abs(grand_total_pdf - item_totals["grand_total_from_items"]) > tolerance:
        errors.append(
            "Grand total mismatch: "
            f"PDF={grand_total_pdf}, extracted={item_totals['grand_total_from_items']}"
        )

    return {
        "source_file": source_file,
        "invoice_number": invoice_number,
        "system_ref_no": system_ref_no,
        "line_count": len(items),
        "qty_sum_extracted": item_totals["total_qty_from_items"],
        "total_sum_extracted": item_totals["grand_total_from_items"],
        "qty_pdf": qty_pdf,
        "grand_total_pdf": grand_total_pdf,
        "status": "PASS" if not errors else "FAIL",
        "errors": "; ".join(errors),
    }
