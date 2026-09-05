from accounts.permissions import get_profile


def user_profile(request):
    """Expose the current user's profile to every template."""
    if request.user.is_authenticated:
        return {"profile": get_profile(request.user)}
    return {"profile": None}


def table_layout(request):
    """Expose per-menu table height, borders, and width-lock flags."""
    import json

    try:
        from catalog.models import TableLayoutSettings
        from catalog.table_layout import css_for_layouts, locks_from_layouts

        settings = TableLayoutSettings.load()
        layouts = settings.layouts_map()
        locks = locks_from_layouts(layouts)
        return {
            "table_row_height_px": settings.clamped_row_height(),
            "table_width_locks": locks,
            "table_width_locks_json": json.dumps(locks, ensure_ascii=False),
            "table_section_layouts": layouts,
            "table_section_layouts_json": json.dumps(layouts, ensure_ascii=False),
            "table_layout_css": css_for_layouts(layouts),
        }
    except Exception:  # noqa: BLE001 — migrations / early boot
        return {
            "table_row_height_px": 36,
            "table_width_locks": {},
            "table_width_locks_json": "{}",
            "table_section_layouts": {},
            "table_section_layouts_json": "{}",
            "table_layout_css": "",
        }
