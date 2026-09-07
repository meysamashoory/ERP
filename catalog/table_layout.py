"""Per-menu table display settings (row height, borders, column-width lock)."""

from __future__ import annotations

from typing import Any

MIN_ROW_HEIGHT = 5
MAX_ROW_HEIGHT = 120
DEFAULT_ROW_HEIGHT = 36

# Order matches the main sidebar menus that have tables.
SECTION_CHOICES: tuple[tuple[str, str], ...] = (
    ("planning", "برنامه‌ریزی هفتگی"),
    ("systemic", "برنامه‌ریزی توسط سیستم"),
    ("production", "ثبت و کنترل تولید"),
    ("history", "سوابق تولید"),
    ("pipe_calc", "محاسبات زمان تولید"),
    ("reports", "گزارش‌ها"),
    ("forms", "فرم‌ها"),
    ("excel", "بارگذاری فایل"),
    ("product_data", "دیتای محصولات"),
    ("system", "مدیریت داده‌های سامانه"),
)

SECTION_KEYS: tuple[str, ...] = tuple(key for key, _label in SECTION_CHOICES)
UNLOCKED_WIDTH_DEFAULTS: frozenset[str] = frozenset({"reports"})


def clamp_row_height(value: Any, default: int = DEFAULT_ROW_HEIGHT) -> int:
    try:
        height = int(value)
    except (TypeError, ValueError):
        height = default
    return max(MIN_ROW_HEIGHT, min(MAX_ROW_HEIGHT, height))


def default_width_locked(section_key: str) -> bool:
    return str(section_key or "") not in UNLOCKED_WIDTH_DEFAULTS


def default_layout(section_key: str) -> dict[str, Any]:
    return {
        "row_height_px": DEFAULT_ROW_HEIGHT,
        "col_border": True,
        "row_border": True,
        "width_locked": default_width_locked(section_key),
    }


def normalize_section_layout(section_key: str, raw: Any) -> dict[str, Any]:
    layout = default_layout(section_key)
    if not isinstance(raw, dict):
        return layout
    if "row_height_px" in raw:
        layout["row_height_px"] = clamp_row_height(raw.get("row_height_px"))
    if "col_border" in raw:
        layout["col_border"] = bool(raw.get("col_border"))
    if "row_border" in raw:
        layout["row_border"] = bool(raw.get("row_border"))
    if "width_locked" in raw:
        layout["width_locked"] = bool(raw.get("width_locked"))
    return layout


def normalize_all_layouts(
    stored: Any,
    *,
    legacy_height: int | None = None,
    legacy_locks: dict[str, bool] | None = None,
) -> dict[str, dict[str, Any]]:
    stored = stored if isinstance(stored, dict) else {}
    legacy_locks = legacy_locks if isinstance(legacy_locks, dict) else {}
    fallback_height = (
        clamp_row_height(legacy_height)
        if legacy_height is not None
        else DEFAULT_ROW_HEIGHT
    )
    out: dict[str, dict[str, Any]] = {}
    for key, _label in SECTION_CHOICES:
        raw = stored.get(key)
        if isinstance(raw, dict):
            out[key] = normalize_section_layout(key, raw)
            continue
        layout = default_layout(key)
        layout["row_height_px"] = fallback_height
        # Old lock maps defaulted to unlocked (False). Only keep explicit True.
        if bool(legacy_locks.get(key)):
            layout["width_locked"] = True
        out[key] = layout
    return out


def locks_from_layouts(layouts: dict[str, dict[str, Any]]) -> dict[str, bool]:
    return {key: bool(cfg.get("width_locked")) for key, cfg in layouts.items()}


def css_for_layouts(layouts: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for key, cfg in layouts.items():
        height = clamp_row_height(cfg.get("row_height_px"))
        parts.append(f'[data-table-section="{key}"]{{--table-row-height:{height}px;}}')
        cells = (
            f'[data-table-section="{key}"] .table th,'
            f'[data-table-section="{key}"] .table td,'
            f'[data-table-section="{key}"] .table thead th,'
            f'[data-table-section="{key}"] .table tbody td,'
            f'[data-table-section="{key}"].table th,'
            f'[data-table-section="{key}"].table td,'
            f'[data-table-section="{key}"] .pcx-table th,'
            f'[data-table-section="{key}"] .pcx-table td'
        )
        if not cfg.get("col_border", True):
            parts.append(
                f"{cells}{{"
                "border-left-color:transparent !important;"
                "border-right-color:transparent !important;"
                "border-inline-start-color:transparent !important;"
                "border-inline-end-color:transparent !important;"
                "}"
            )
        if not cfg.get("row_border", True):
            parts.append(
                f"{cells}{{"
                "border-top-color:transparent !important;"
                "border-bottom-color:transparent !important;"
                "}"
            )
            parts.append(
                f'[data-table-section="{key}"] .table-scroll thead th,'
                f'[data-table-section="{key}"] .table-scroll-wide thead th{{'
                "box-shadow:none !important;"
                "}"
            )
    return "".join(parts)
