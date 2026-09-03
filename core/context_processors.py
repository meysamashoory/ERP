from accounts.permissions import get_profile


def user_profile(request):
    """Expose the current user's profile to every template."""
    if request.user.is_authenticated:
        return {"profile": get_profile(request.user)}
    return {"profile": None}


def table_layout(request):
    """Expose global table row height and section width-lock flags."""
    import json

    try:
        from catalog.models import TableLayoutSettings

        settings = TableLayoutSettings.load()
        locks = settings.normalized_locks()
        return {
            "table_row_height_px": settings.clamped_row_height(),
            "table_width_locks": locks,
            "table_width_locks_json": json.dumps(locks, ensure_ascii=False),
        }
    except Exception:  # noqa: BLE001 — migrations / early boot
        return {
            "table_row_height_px": 36,
            "table_width_locks": {},
            "table_width_locks_json": "{}",
        }
