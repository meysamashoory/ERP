"""Parse Excel quantity phrases like «1000 ضرب جنرال» and merge type into product name."""

from __future__ import annotations

import re

_DIGIT_TABLE = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
_SIZE_TAIL = re.compile(r"^(.*?)(\s+\d+(?:\s*[./\-]\s*\d+)*)\s*$")
_LEADING_NOISE = re.compile(
    r"^(?:یا\s*)?(?:حدود\s*)?(?:\d+(?:[./]\d+)?\s*)+",
    re.UNICODE,
)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_TABLE)


def parse_unit_machine_label(raw: str) -> tuple[int | None, str | None]:
    """Extract ``(unit_number, machine_number)`` from Excel labels.

    Supports combined labels used in exports, e.g.:
    - ``دستگاه 6 واحد1`` / ``دستگاه 6 واحد 1`` → ``(1, "6")``
    - ``واحد 2 دستگاه 03`` → ``(2, "3")``
    - plain ``6`` / ``۰۶`` → ``(None, "6")`` (caller decides which field)
    """
    text = normalize_digits(str(raw or "")).strip()
    if not text:
        return None, None

    # دستگاه N واحد M  (machine first — common export format)
    match = re.search(r"دستگاه\s*(\d+)\s*واحد\s*(\d+)", text)
    if match:
        return int(match.group(2)), str(int(match.group(1)))

    # واحد N دستگاه M
    match = re.search(r"واحد\s*(\d+)\s*دستگاه\s*(\d+)", text)
    if match:
        return int(match.group(1)), str(int(match.group(2)))

    # Only "واحد N"
    match = re.search(r"واحد\s*(\d+)", text)
    if match and "دستگاه" not in text:
        return int(match.group(1)), None

    # Only "دستگاه N"
    match = re.search(r"دستگاه\s*(\d+)", text)
    if match and "واحد" not in text:
        return None, str(int(match.group(1)))

    nums = re.findall(r"\d+", text)
    if len(nums) == 1:
        return None, str(int(nums[0]))
    return None, None


def extract_qty_and_production_type(raw: str) -> tuple[int | None, str, str | None]:
    """Return (quantity, production_type, error).

    Examples:
    - ``1000`` → (1000, "", None)
    - ``1000 ضرب`` → (1000, "", None)
    - ``1000 ضرب جنرال`` → (1000, "جنرال", None)
    - ``1000 ضرب یا حدود 10000 ضرب پروتکت`` → (1000, "پروتکت", None)
    """
    text = normalize_digits(str(raw or "").strip())
    if not text:
        return None, "", None

    nums = re.findall(r"\d+", text)
    if not nums:
        return None, "", f"در مقدار «{raw}» عدد تولید یافت نشد."

    qty = int(nums[0])
    prod_type = ""
    if "ضرب" in text:
        after = text.rsplit("ضرب", 1)[-1].strip()
        after = _LEADING_NOISE.sub("", after).strip()
        after = re.sub(r"^[\s|/\\\-_,.،؛:]+", "", after).strip()
        after = re.sub(r"[\s|/\\\-_,.،؛:]+$", "", after).strip()
        prod_type = after

    return qty, prod_type, None


def apply_production_type_to_name(name: str, prod_type: str) -> str:
    """Insert production type before trailing size code.

    ``زانو 45-110`` + ``جنرال`` → ``زانو جنرال 45-110``
    """
    name = (name or "").strip()
    prod_type = (prod_type or "").strip()
    if not name or not prod_type:
        return name

    parts = name.split()
    if prod_type in parts:
        return name

    match = _SIZE_TAIL.match(name)
    if match and match.group(1).strip():
        head = match.group(1).strip()
        size = match.group(2).strip()
        return f"{head} {prod_type} {size}"
    return f"{name} {prod_type}"
