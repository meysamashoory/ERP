"""Natural (human) sorting helpers — 1,2,9,10 instead of 1,10,2,9."""

from __future__ import annotations

import re
from typing import Any


_SPLIT = re.compile(r"(\d+)")


def natural_key(value: Any) -> list:
    """Key for sorted(..., key=natural_key) / list.sort."""
    text = "" if value is None else str(value).strip()
    parts: list = []
    for part in _SPLIT.split(text):
        if part == "":
            continue
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part.casefold()))
    return parts


def natural_sorted(items, *, key=None, reverse: bool = False):
    """Return a new list sorted with natural order."""

    def _key(item):
        raw = key(item) if key is not None else item
        if isinstance(raw, tuple):
            return tuple(natural_key(p) if not isinstance(p, (int, float)) else (0, p) for p in raw)
        return natural_key(raw)

    return sorted(items, key=_key, reverse=reverse)
