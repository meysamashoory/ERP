"""Form purpose catalogs: sources/columns for designer binding and print fill."""

from __future__ import annotations

PURPOSE_WEEKLY = "weekly_planning"
PURPOSE_PRODUCTION = "production"
PURPOSE_REPORTS = "reports"

PURPOSE_CHOICES = [
    (PURPOSE_WEEKLY, "برنامه ریزی هفتگی"),
    (PURPOSE_PRODUCTION, "برنامه های تولید"),
    (PURPOSE_REPORTS, "گزارش ها"),
]

PURPOSE_LABELS = dict(PURPOSE_CHOICES)

# Sources + columns for weekly planning
WEEKLY_SOURCES = [
    {
        "id": "weekly_injection",
        "label": "برنامه ریزی دستگاه تزریق",
        "enabled": True,
        "columns": [
            ("program_number", "شماره برنامه"),
            ("date", "تاریخ"),
            ("weekday", "روز"),
            ("status", "وضعیت"),
            ("created_by", "ایجادکننده"),
            ("uid", "شناسه"),
            ("product_code", "کد کالا"),
            ("product_name", "نام محصول"),
            ("unit", "واحد"),
            ("machine", "دستگاه"),
            ("mold_change_day", "روز تعویض قالب"),
            ("mold_change_date", "تاریخ تعویض"),
            ("cavities", "حفره فعال"),
            ("production_rows", "ردیف‌های تولید"),
        ],
    },
    {
        "id": "weekly_pipe",
        "label": "برنامه ریزی خط لوله",
        "enabled": False,
        "columns": [
            ("program_number", "شماره برنامه"),
            ("date", "تاریخ"),
            ("weekday", "روز"),
            ("status", "وضعیت"),
            ("unit", "واحد"),
            ("line", "خط"),
            ("pipe_type", "نوع"),
            ("product_code", "کد کالا"),
            ("product_name", "نام محصول"),
        ],
    },
]

PRODUCTION_SOURCES = [
    {
        "id": "prod_fitting",
        "label": "برنامه تولید اتصالات",
        "enabled": True,
        "columns": [
            ("uid", "شناسه"),
            ("program_number", "شماره برنامه"),
            ("machine", "دستگاه/واحد"),
            ("product_code", "کد کالا"),
            ("product_name", "نام محصول"),
            ("status", "وضعیت"),
            ("produced", "تولید"),
            ("planned", "برنامه"),
            ("scrap", "ضایعات"),
            ("cycle", "سیکل"),
            ("cavities", "حفره فعال"),
            ("deviation", "انحراف"),
            ("deviation_reason", "دلیل انحراف"),
            ("date", "تاریخ"),
        ],
    },
    {
        "id": "prod_pipe",
        "label": "برنامه تولید لوله",
        "enabled": True,
        "columns": [
            ("date", "تاریخ"),
            ("unit", "واحد"),
            ("line", "خط"),
            ("pipe_type", "نوع"),
            ("product_code", "کد کالا"),
            ("product_name", "نام محصول"),
            ("produced", "تولید"),
            ("planned", "برنامه"),
            ("deviation", "انحراف"),
        ],
    },
]


def purpose_source_groups(purpose: str) -> list[dict]:
    if purpose == PURPOSE_WEEKLY:
        return [
            {
                "id": s["id"],
                "label": s["label"],
                "enabled": s.get("enabled", True),
                "columns": list(s["columns"]),
            }
            for s in WEEKLY_SOURCES
        ]
    if purpose == PURPOSE_PRODUCTION:
        return [
            {
                "id": s["id"],
                "label": s["label"],
                "enabled": s.get("enabled", True),
                "columns": list(s["columns"]),
            }
            for s in PRODUCTION_SOURCES
        ]
    return []


def report_level_groups(report) -> list[dict]:
    """Build source groups as report levels; columns are headers at that level.

    Column ids prefer per-instance ``uid`` so form bindings stay independent
    when the same data key is copied.
    """
    from reports.columns import normalize_columns, storage_key

    cols = normalize_columns(report.columns or [])
    levels = sorted({int(c.get("level") or 1) for c in cols})
    if not levels:
        levels = [1]
    groups = []
    for lv in levels:
        level_cols = [
            (storage_key(c), str(c.get("label") or c.get("key") or ""))
            for c in cols
            if int(c.get("level") or 1) == lv
        ]
        groups.append({
            "id": f"level_{lv}",
            "label": f"سطح {lv}",
            "enabled": True,
            "level": lv,
            "columns": level_cols,
        })
    return groups


def forms_for_purpose(user, purpose: str, report_id=None):
    from reports.access import visible_forms
    from reports.models import PrintForm

    qs = visible_forms(user).filter(purpose=purpose)
    if purpose == PURPOSE_REPORTS and report_id:
        qs = qs.filter(linked_report_id=report_id)
    return qs.order_by("number", "id")
