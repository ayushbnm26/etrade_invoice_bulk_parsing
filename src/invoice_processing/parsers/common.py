from __future__ import annotations

import re
from typing import Any


FORCE_POSITIVE_NUMBERS = True


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\ufffe", "-")
    text = text.replace("\u00ad", "")
    text = text.replace("âˆ’", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def clean_inline(value: Any) -> str:
    text = clean_text(value)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+-\s+", "-", text)
    return text.strip()


def compact_alnum(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", clean_text(value))


def compact_code(value: Any) -> str:
    text = clean_text(value)
    text = text.replace("\n", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("--", "-")
    text = text.replace("/-", "/")
    return text.strip()


def clean_state_code(value: Any) -> str:
    return re.sub(r"\s*-\s*", "-", clean_inline(value))


def parse_amount(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None

    text = text.replace(",", "")
    text = text.replace("\ufffe", "-")
    text = text.replace("âˆ’", "-")
    text = re.sub(r"(\d+)\.\s*\n\s*(\d{1,2})", r"\1.\2", text)
    compact = re.sub(r"\s+", "", text)

    numbers = re.findall(r"-?\d+(?:\.\d+)?", compact)
    if not numbers:
        return None

    decimal_numbers = [number for number in numbers if "." in number]
    chosen = decimal_numbers[-1] if decimal_numbers else numbers[0]

    try:
        amount = float(chosen)
    except (TypeError, ValueError):
        return None

    return abs(amount) if FORCE_POSITIVE_NUMBERS else amount


def parse_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None

    text = text.replace(",", "")
    text = text.replace("\ufffe", "-")
    text = text.replace("âˆ’", "-")
    match = re.search(r"-?\d+", text)
    if not match:
        return None

    try:
        return abs(int(match.group()))
    except (TypeError, ValueError):
        return None


def regex_value(pattern: str, text: str, flags: int = re.I | re.S) -> str:
    match = re.search(pattern, text or "", flags)
    if not match:
        return ""
    return clean_inline(match.group(1))


def normalise_table_row(row: list[Any], expected_columns: list[str]) -> list[str]:
    cells = [clean_text(cell) for cell in row]
    expected_count = len(expected_columns)

    while len(cells) > expected_count:
        empty_index = next(
            (index for index, cell in enumerate(cells) if index != 0 and not cell.strip()),
            None,
        )
        if empty_index is None:
            empty_index = next((index for index, cell in enumerate(cells) if not cell.strip()), None)
        if empty_index is not None:
            cells.pop(empty_index)
        else:
            cells[expected_count - 1] = "\n".join(cells[expected_count - 1 :])
            cells = cells[:expected_count]

    while len(cells) < expected_count:
        cells.append("")

    return cells


def parse_tax_fields(
    tax_rate_raw: Any,
    tax_type_raw: Any,
    tax_amount_raw: Any,
) -> dict[str, float | None]:
    result = {
        "cgst_rate": None,
        "cgst_amount": None,
        "sgst_rate": None,
        "sgst_amount": None,
        "igst_rate": None,
        "igst_amount": None,
    }

    tax_types = [
        tax_type.upper()
        for tax_type in re.findall(r"\bCGST\b|\bSGST\b|\bIGST\b", clean_text(tax_type_raw), flags=re.I)
    ]
    rates = re.findall(r"-?\d+(?:\.\d+)?", clean_text(tax_rate_raw).replace(",", ""))
    amounts = re.findall(r"-?\d[\d,]*(?:\.\d+)?", clean_text(tax_amount_raw))

    for index, tax_type in enumerate(tax_types):
        rate = parse_amount(rates[index]) if index < len(rates) else None
        amount = parse_amount(amounts[index]) if index < len(amounts) else None
        result[f"{tax_type.lower()}_rate"] = rate
        result[f"{tax_type.lower()}_amount"] = amount

    return result


def first_number_after(cells: list[str], label_index: int, integer: bool = False) -> int | float | None:
    parser = parse_int if integer else parse_amount
    for cell in cells[label_index + 1 :]:
        value = parser(cell)
        if value is not None:
            return value
    return None


def dedupe_repeated_phrase(value: Any) -> str:
    text = clean_inline(value)
    if not text:
        return ""

    words = text.split()
    if len(words) % 2 == 0:
        midpoint = len(words) // 2
        if words[:midpoint] == words[midpoint:]:
            return " ".join(words[:midpoint])

    return text
