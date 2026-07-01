from __future__ import annotations

import re
from typing import Any

from invoice_processing.parsers.common import clean_inline, clean_state_code, clean_text, regex_value


def find_phrase_bbox(
    words: list[dict[str, Any]],
    phrase: str,
    x_min: float = 0,
    x_max: float = 999,
) -> dict[str, float] | None:
    tokens = phrase.split()

    for index in range(len(words) - len(tokens) + 1):
        group = words[index : index + len(tokens)]
        texts = [word["text"] for word in group]
        same_line = max(word["top"] for word in group) - min(word["top"] for word in group) < 5
        in_x_range = all(x_min <= word["x0"] <= x_max for word in group)

        if texts == tokens and same_line and in_x_range:
            return {
                "x0": min(word["x0"] for word in group),
                "x1": max(word["x1"] for word in group),
                "top": min(word["top"] for word in group),
                "bottom": max(word["bottom"] for word in group),
            }

    return None


def words_to_lines(words: list[dict[str, Any]], y_tolerance: float = 3) -> list[str]:
    if not words:
        return []

    sorted_words = sorted(words, key=lambda word: (word["top"], word["x0"]))
    lines: list[str] = []
    current: list[dict[str, Any]] = []
    current_y: float | None = None

    for word in sorted_words:
        if current_y is None or abs(word["top"] - current_y) <= y_tolerance:
            current.append(word)
            if current_y is None:
                current_y = word["top"]
        else:
            current = sorted(current, key=lambda item: item["x0"])
            lines.append(" ".join(item["text"] for item in current))
            current = [word]
            current_y = word["top"]

    if current:
        current = sorted(current, key=lambda item: item["x0"])
        lines.append(" ".join(item["text"] for item in current))

    return [clean_inline(line) for line in lines if clean_inline(line)]


def extract_text_by_words(words: list[dict[str, Any]], bbox: tuple[float, float, float, float]) -> str:
    x0, top, x1, bottom = bbox
    selected = []

    for word in words:
        center_x = (word["x0"] + word["x1"]) / 2
        center_y = (word["top"] + word["bottom"]) / 2
        if x0 <= center_x <= x1 and top <= center_y <= bottom:
            selected.append(word)

    return "\n".join(words_to_lines(selected))


def parse_address_block(raw: str) -> dict[str, str]:
    text = clean_text(raw)
    text = re.sub(
        r"(?i)\b(Billing Address|Receiver Billing Address|Shipping Address|Receiver Shipping Address)\b",
        "",
        text,
    )
    text = re.sub(r"(?i)Place\s+of\s+Supply\s*:.*", "", text)

    lines = [clean_inline(line) for line in text.splitlines() if clean_inline(line)]
    state_code = clean_state_code(regex_value(r"State\s*Code\s*:\s*([A-Z]{2}\s*-\s*\d+|[A-Z]{2})", text))
    gstin = regex_value(r"GSTIN\s*:\s*([0-9A-Z]{15})", text)
    pan = regex_value(r"PAN\s*No\s*:\s*([A-Z0-9]{10})", text)

    clean_lines = []
    for line in lines:
        if re.search(r"State\s*Code|GSTIN|PAN\s*No|Place\s+of\s+Supply", line, flags=re.I):
            continue
        if gstin and line.strip() == gstin:
            continue
        if pan and line.strip() == pan:
            continue
        clean_lines.append(line)

    return {
        "raw": clean_inline(text),
        "name": clean_lines[0] if clean_lines else "",
        "address": ", ".join(clean_lines[1:]) if len(clean_lines) > 1 else "",
        "state_code": state_code,
        "gstin": gstin,
        "pan": pan,
    }


def extract_addresses(words: list[dict[str, Any]]) -> dict[str, str]:
    billing_header = find_phrase_bbox(words, "Billing Address", 0, 280)
    receiver_billing_header = find_phrase_bbox(words, "Receiver Billing Address", 300, 620)
    shipping_header = find_phrase_bbox(words, "Shipping Address", 0, 280)
    receiver_shipping_header = find_phrase_bbox(words, "Receiver Shipping Address", 300, 620)
    invoice_ref_header = find_phrase_bbox(words, "Invoice Reference Number", 0, 350)
    place_supply_header = find_phrase_bbox(words, "Place of Supply", 300, 620)

    billing_y1 = billing_header["bottom"] + 3 if billing_header else 155
    receiver_billing_y1 = receiver_billing_header["bottom"] + 3 if receiver_billing_header else 155
    shipping_y0 = shipping_header["top"] if shipping_header else 245
    shipping_y1 = shipping_header["bottom"] + 3 if shipping_header else 265
    receiver_shipping_y0 = receiver_shipping_header["top"] if receiver_shipping_header else 245
    receiver_shipping_y1 = receiver_shipping_header["bottom"] + 3 if receiver_shipping_header else 265
    meta_y = invoice_ref_header["top"] if invoice_ref_header else 380
    place_y = place_supply_header["top"] if place_supply_header else meta_y

    blocks = {
        "billing": extract_text_by_words(words, (35, billing_y1, 310, shipping_y0 - 2)),
        "receiver_billing": extract_text_by_words(
            words,
            (350, receiver_billing_y1, 590, receiver_shipping_y0 - 2),
        ),
        "shipping": extract_text_by_words(words, (35, shipping_y1, 310, meta_y - 2)),
        "receiver_shipping": extract_text_by_words(
            words,
            (350, receiver_shipping_y1, 590, min(place_y, meta_y) - 2),
        ),
    }

    extracted: dict[str, str] = {}
    for prefix, raw in blocks.items():
        parsed = parse_address_block(raw)
        for key, value in parsed.items():
            extracted[f"{prefix}_{key}"] = value

    return extracted
