"""Configurable planning-process stages (from PDF Plan-to-Produce logic).

Stages are numbered, redefinable, and may bind to live system data sources.
Decision steps store yes/no next-step numbers explicitly.
"""

from __future__ import annotations

# Binding keys ↔ human labels (connected to ERP data areas)
PLANNING_DATA_BINDINGS: list[tuple[str, str]] = [
    ("none", "بدون اتصال داده"),
    ("orders", "سفارشات هفتگی و معوق"),
    ("inventory_finished", "موجودی محصول نهایی"),
    ("inventory_semi", "موجودی نیمه‌ساخته / UNIT"),
    ("inventory_to_deliver", "فرآیند Inventory to deliver"),
    ("bom", "ساختار BOM"),
    ("bom_alt", "BOM / مواد جایگزین"),
    ("supply", "تأمین / سفارش خرید"),
    ("unit_capacity", "ظرفیت تولید اجزا / UNIT"),
    ("molds", "قالب‌ها و آمادگی قالب"),
    ("mold_alt", "قالب جایگزین"),
    ("machines", "ماشین‌آلات و آمادگی دستگاه"),
    ("machine_alt", "ماشین جایگزین"),
    ("labor", "نیروی انسانی"),
    ("labor_alt", "نیروی انسانی جایگزین"),
    ("depot_ceiling", "ظرفیت انبارش / سقف دپو"),
    ("min_production", "سقف حداقل تولید"),
    ("forecast", "پیش‌بینی فروش"),
    ("capacity", "ظرفیت تولید باقی‌مانده"),
    ("product_new_old", "سیاست محصول جدید / قدیمی"),
    ("marketing", "مارکتینگ / مذاکره مشتری"),
    ("weekly_priority", "لیست اولویت تولید هفتگی"),
    ("produce_plan", "صدور / ثبت برنامه تولید"),
    ("make_to_stock", "ورود به فرآیند Make to Stock"),
]


BINDING_LABELS = dict(PLANNING_DATA_BINDINGS)


def binding_label(key: str) -> str:
    return BINDING_LABELS.get(key or "none", key or "—")


# ---------------------------------------------------------------------------
# Seed definitions from PDF (Make to Order + Make to Stock core paths)
# Each step: (number, title, kind, question, yes_next, no_next, next, binding, desc)
# kind: action | decision | terminal
# ---------------------------------------------------------------------------

MTO_STEPS: list[dict] = [
    {
        "step_number": 1,
        "title": "تجمیع سفارشات هفتگی و معوق",
        "kind": "action",
        "question": "",
        "next_number": 2,
        "data_binding": "orders",
        "description": "ورودی فرآیند Plan to Produce — تجمیع سفارشات براساس اولویت تحویل.",
    },
    {
        "step_number": 2,
        "title": "بررسی موجودی انبار محصول",
        "kind": "decision",
        "question": "آیا در انبار موجود است؟",
        "yes_next_number": 3,
        "no_next_number": 5,
        "data_binding": "inventory_finished",
        "description": "اگر موجودی کافی باشد مسیر تحویل از انبار؛ در غیر این صورت امکان‌سنجی تولید.",
    },
    {
        "step_number": 3,
        "title": "کسر موجودی از سفارش",
        "kind": "action",
        "question": "",
        "next_number": 4,
        "data_binding": "inventory_finished",
        "description": "کسر موجودی محصول از مقدار سفارش.",
    },
    {
        "step_number": 4,
        "title": "فرآیند Inventory to deliver",
        "kind": "terminal",
        "question": "",
        "data_binding": "inventory_to_deliver",
        "description": "خروج از مسیر تولید؛ تحویل از موجودی انبار.",
    },
    {
        "step_number": 5,
        "title": "بررسی کامل بودن BOM",
        "kind": "decision",
        "question": "آیا مواد و قطعات و BOM به‌طور کامل برای تولید سفارش (براساس اولویت تحویل) وجود دارد؟",
        "yes_next_number": 9,
        "no_next_number": 6,
        "data_binding": "bom",
        "description": "کنترل موجودی اجزای BOM نسبت به مقدار مورد نیاز سفارش.",
    },
    {
        "step_number": 6,
        "title": "مواد و قطعات جایگزین",
        "kind": "decision",
        "question": "آیا می‌خواهیم از مواد و قطعات جایگزین استفاده کنیم؟",
        "yes_next_number": 8,
        "no_next_number": 7,
        "data_binding": "bom_alt",
        "description": "انتخاب نسخه BOM جایگزین در صورت کسری.",
    },
    {
        "step_number": 7,
        "title": "تأمین کسری در زمان مناسب",
        "kind": "decision",
        "question": "آیا تأمین کسری در زمان مناسب انجام می‌شود؟",
        "yes_next_number": 9,
        "no_next_number": 22,
        "data_binding": "supply",
        "description": "در صورت عدم تأمین به‌موقع → مذاکره با مشتری / مارکتینگ.",
    },
    {
        "step_number": 8,
        "title": "استفاده از نسخه BOM جایگزین",
        "kind": "decision",
        "question": "آیا از نسخه BOM جایگزین استفاده می‌کنیم؟",
        "yes_next_number": 9,
        "no_next_number": 22,
        "data_binding": "bom_alt",
        "description": "تأیید نهایی BOM جایگزین؛ اطلاع‌رسانی به مارکتینگ/فروش در صورت نیاز.",
    },
    {
        "step_number": 9,
        "title": "ظرفیت تولید اجزا / UNIT",
        "kind": "decision",
        "question": "آیا ظرفیت تولید اجزا یا UNITهایی که BOM آن موجود است را داریم؟",
        "yes_next_number": 11,
        "no_next_number": 10,
        "data_binding": "unit_capacity",
        "description": "UNIT: مجموعه‌ای از اجزا که باید همزمان تولید شوند.",
    },
    {
        "step_number": 10,
        "title": "سفارش خرید به تأمین و انتظار",
        "kind": "action",
        "question": "",
        "next_number": 5,
        "data_binding": "supply",
        "description": "ارجاع به تأمین و بازگشت به بررسی BOM پس از تأمین.",
    },
    {
        "step_number": 11,
        "title": "موجودی نیمه‌ساخته",
        "kind": "decision",
        "question": "آیا بخشی از اجزا یا UNITها در انبار نیمه‌ساخته موجود است؟",
        "yes_next_number": 12,
        "no_next_number": 12,
        "data_binding": "inventory_semi",
        "description": "در صورت موجودی نیمه‌ساخته می‌توان از آن کسر کرد (هر دو مسیر به امکان‌سنجی ۴عاملی می‌روند).",
    },
    {
        "step_number": 12,
        "title": "آمادگی قالب‌ها",
        "kind": "decision",
        "question": "آیا قالب‌ها آماده تولید هستند؟",
        "yes_next_number": 15,
        "no_next_number": 13,
        "data_binding": "molds",
        "description": "یکی از ۴ فاکتور امکان‌سنجی تولید.",
    },
    {
        "step_number": 13,
        "title": "قالب جایگزین",
        "kind": "decision",
        "question": "آیا قالب جایگزین داریم؟",
        "yes_next_number": 15,
        "no_next_number": 14,
        "data_binding": "mold_alt",
    },
    {
        "step_number": 14,
        "title": "آمادگی قالب در زمان مناسب",
        "kind": "decision",
        "question": "آیا در زمان مناسب آماده می‌شود؟",
        "yes_next_number": 15,
        "no_next_number": 22,
        "data_binding": "molds",
    },
    {
        "step_number": 15,
        "title": "آمادگی ماشین‌آلات",
        "kind": "decision",
        "question": "آیا ماشین‌آلات آماده به تولید هستند؟",
        "yes_next_number": 18,
        "no_next_number": 16,
        "data_binding": "machines",
    },
    {
        "step_number": 16,
        "title": "ماشین جایگزین",
        "kind": "decision",
        "question": "آیا ماشین جایگزین داریم؟",
        "yes_next_number": 18,
        "no_next_number": 17,
        "data_binding": "machine_alt",
    },
    {
        "step_number": 17,
        "title": "آمادگی ماشین در زمان مناسب",
        "kind": "decision",
        "question": "آیا در زمان مناسب آماده می‌شود؟",
        "yes_next_number": 18,
        "no_next_number": 22,
        "data_binding": "machines",
    },
    {
        "step_number": 18,
        "title": "نیروی انسانی لازم",
        "kind": "decision",
        "question": "آیا نیروی انسانی لازم را داریم؟",
        "yes_next_number": 21,
        "no_next_number": 19,
        "data_binding": "labor",
    },
    {
        "step_number": 19,
        "title": "نیروی انسانی جایگزین",
        "kind": "decision",
        "question": "آیا نیروی انسانی جایگزین داریم؟",
        "yes_next_number": 21,
        "no_next_number": 20,
        "data_binding": "labor_alt",
    },
    {
        "step_number": 20,
        "title": "آمادگی نیرو در زمان مناسب",
        "kind": "decision",
        "question": "آیا در زمان مناسب آماده می‌شود؟",
        "yes_next_number": 21,
        "no_next_number": 22,
        "data_binding": "labor",
    },
    {
        "step_number": 21,
        "title": "ظرفیت انبارش",
        "kind": "decision",
        "question": "آیا ظرفیت انبارش داریم؟",
        "yes_next_number": 24,
        "no_next_number": 23,
        "data_binding": "depot_ceiling",
        "description": "محدودیت سقف دپو / فضای انبار.",
    },
    {
        "step_number": 22,
        "title": "اطلاع به مارکتینگ برای مذاکره با مشتری",
        "kind": "decision",
        "question": "آیا مشتری سفارش را کنسل کرد؟",
        "yes_next_number": 35,
        "no_next_number": 1,
        "data_binding": "marketing",
        "description": "مسیر بن‌بست امکان‌سنجی؛ مذاکره یا بازگشت به تجمیع سفارشات.",
    },
    {
        "step_number": 23,
        "title": "تولید به اندازه ظرفیت انبارش",
        "kind": "action",
        "question": "",
        "next_number": 26,
        "data_binding": "depot_ceiling",
    },
    {
        "step_number": 24,
        "title": "سقف حداقل تولید",
        "kind": "decision",
        "question": "آیا تا سقف حداقل تولید می‌توانیم تولید کنیم؟",
        "yes_next_number": 26,
        "no_next_number": 25,
        "data_binding": "min_production",
    },
    {
        "step_number": 25,
        "title": "تولید به اندازه سقف حداقل تولید",
        "kind": "action",
        "question": "",
        "next_number": 26,
        "data_binding": "min_production",
    },
    {
        "step_number": 26,
        "title": "محصول جدید جایگزین قدیمی",
        "kind": "decision",
        "question": "آیا محصولی که می‌خواهیم تولید کنیم محصول جدید است که قرار است جایگزین محصول قدیمی شود؟",
        "yes_next_number": 27,
        "no_next_number": 29,
        "data_binding": "product_new_old",
    },
    {
        "step_number": 27,
        "title": "سیاست اتمام محصول قدیمی",
        "kind": "decision",
        "question": "آیا سیاست شرکت بر اتمام محصول قدیمی و ورود محصول جدید به بازار است؟",
        "yes_next_number": 28,
        "no_next_number": 29,
        "data_binding": "product_new_old",
    },
    {
        "step_number": 28,
        "title": "بررسی موجودی محصول قدیمی و کسر از برنامه",
        "kind": "action",
        "question": "",
        "next_number": 29,
        "data_binding": "inventory_finished",
        "description": "کسر موجودی محصول قدیمی از تعداد برنامه‌ریزی تولید.",
    },
    {
        "step_number": 29,
        "title": "بررسی موجودی محصول جدید / برنامه‌ریزی تولید",
        "kind": "action",
        "question": "",
        "next_number": 30,
        "data_binding": "produce_plan",
        "description": "ثبت پیشنهاد تولید در برنامه هفتگی.",
    },
    {
        "step_number": 30,
        "title": "قابلیت تولید کل سفارش",
        "kind": "decision",
        "question": "آیا کل محصولات یک سفارش قابل تولید است؟",
        "yes_next_number": 31,
        "no_next_number": 32,
        "data_binding": "orders",
    },
    {
        "step_number": 31,
        "title": "محصول دیگر در سفارش",
        "kind": "decision",
        "question": "آیا محصول دیگری در سفارش وجود دارد؟",
        "yes_next_number": 2,
        "no_next_number": 34,
        "data_binding": "orders",
        "description": "حلقه روی اقلام سفارش؛ تعداد اقلام در هر LOOP کم می‌شود.",
    },
    {
        "step_number": 32,
        "title": "مواد تا اندازه حداقل تولید",
        "kind": "decision",
        "question": "آیا تا اندازه حداقل تولید مواد و BOM داریم؟",
        "yes_next_number": 25,
        "no_next_number": 33,
        "data_binding": "bom",
    },
    {
        "step_number": 33,
        "title": "تولید به اندازه موجودی مواد و BOM",
        "kind": "action",
        "question": "",
        "next_number": 31,
        "data_binding": "bom",
    },
    {
        "step_number": 34,
        "title": "ورود به فرآیند Make to Stock",
        "kind": "terminal",
        "question": "",
        "data_binding": "make_to_stock",
        "description": "ادامه در تعریف فرآیند Make to Stock.",
    },
    {
        "step_number": 35,
        "title": "پایان — سفارش کنسل شد",
        "kind": "terminal",
        "question": "",
        "data_binding": "none",
    },
]

MTS_STEPS: list[dict] = [
    {
        "step_number": 1,
        "title": "بررسی لیست اولویت تولید هفتگی",
        "kind": "action",
        "question": "",
        "next_number": 2,
        "data_binding": "weekly_priority",
    },
    {
        "step_number": 2,
        "title": "بررسی موجودی انبار",
        "kind": "action",
        "question": "",
        "next_number": 3,
        "data_binding": "inventory_finished",
    },
    {
        "step_number": 3,
        "title": "وجود در پیش‌بینی فروش آینده",
        "kind": "decision",
        "question": "آیا این محصول در پیش‌بینی فروش آینده وجود دارد؟",
        "yes_next_number": 4,
        "no_next_number": 5,
        "data_binding": "forecast",
        "description": "فعلاً داده پیش‌بینی ذخیره می‌شود؛ اجرای کامل بعداً.",
    },
    {
        "step_number": 4,
        "title": "تعیین میزان تولید (حداکثر − موجودی)",
        "kind": "action",
        "question": "",
        "next_number": 6,
        "data_binding": "capacity",
        "description": "عدد حداکثر تولید منهای عدد موجود محصول.",
    },
    {
        "step_number": 5,
        "title": "حذف از اولویت تولید هفتگی",
        "kind": "action",
        "question": "",
        "next_number": 8,
        "data_binding": "weekly_priority",
    },
    {
        "step_number": 6,
        "title": "بررسی BOM برای Make to Stock",
        "kind": "decision",
        "question": "آیا مواد و قطعات و BOM به‌طور کامل برای تولید وجود دارد؟",
        "yes_next_number": 10,
        "no_next_number": 7,
        "data_binding": "bom",
    },
    {
        "step_number": 7,
        "title": "مواد جایگزین / تأمین",
        "kind": "decision",
        "question": "آیا می‌خواهیم از مواد و قطعات جایگزین استفاده کنیم؟",
        "yes_next_number": 10,
        "no_next_number": 9,
        "data_binding": "bom_alt",
    },
    {
        "step_number": 8,
        "title": "محصول دیگر در لیست اولویت",
        "kind": "decision",
        "question": "آیا محصول دیگری در لیست اولویت تولید هفتگی وجود دارد؟",
        "yes_next_number": 1,
        "no_next_number": 15,
        "data_binding": "weekly_priority",
    },
    {
        "step_number": 9,
        "title": "سفارش خرید به تأمین",
        "kind": "action",
        "question": "",
        "next_number": 8,
        "data_binding": "supply",
    },
    {
        "step_number": 10,
        "title": "آمادگی قالب / ماشین / نیرو (۴ فاکتور)",
        "kind": "decision",
        "question": "آیا قالب‌ها، ماشین‌آلات و نیروی انسانی آماده تولید هستند؟",
        "yes_next_number": 11,
        "no_next_number": 8,
        "data_binding": "molds",
        "description": "خلاصه امکان‌سنجی ۴عاملی؛ جزئیات در MTO به‌صورت جداگانه تعریف شده است.",
    },
    {
        "step_number": 11,
        "title": "کسر از میزان ظرفیت تولید",
        "kind": "action",
        "question": "",
        "next_number": 12,
        "data_binding": "capacity",
    },
    {
        "step_number": 12,
        "title": "به‌روزرسانی ظرفیت براساس تولید برآوردشده",
        "kind": "action",
        "question": "",
        "next_number": 13,
        "data_binding": "capacity",
    },
    {
        "step_number": 13,
        "title": "آیا هنوز ظرفیت خالی داریم؟",
        "kind": "decision",
        "question": "آیا هنوز ظرفیت خالی داریم؟",
        "yes_next_number": 8,
        "no_next_number": 14,
        "data_binding": "capacity",
    },
    {
        "step_number": 14,
        "title": "تولید به اندازه ظرفیت",
        "kind": "action",
        "question": "",
        "next_number": 15,
        "data_binding": "produce_plan",
    },
    {
        "step_number": 15,
        "title": "پایان Make to Stock",
        "kind": "terminal",
        "question": "",
        "data_binding": "produce_plan",
    },
]


def ensure_default_processes(*, force: bool = False) -> dict[str, int]:
    """Create/refresh default MTO and MTS process definitions."""
    from planning.models import PlanningProcessDefinition, PlanningProcessStep

    created = {"processes": 0, "steps": 0}
    specs = [
        (
            "mto",
            "Make to Order — برنامه‌ریزی بر اساس سفارش",
            "منطق PDF برای سفارشات هفتگی و معوق",
            1,
            MTO_STEPS,
        ),
        (
            "mts",
            "Make to Stock — برنامه‌ریزی بر اساس اولویت/پیش‌بینی",
            "منطق PDF برای لیست اولویت تولید هفتگی و ظرفیت",
            1,
            MTS_STEPS,
        ),
    ]
    for code, title, desc, entry, steps in specs:
        proc, was_created = PlanningProcessDefinition.objects.get_or_create(
            code=code,
            defaults={
                "title": title,
                "description": desc,
                "entry_step_number": entry,
                "is_active": True,
            },
        )
        if was_created:
            created["processes"] += 1
        else:
            if not force and proc.steps.exists():
                continue
            proc.title = title
            proc.description = desc
            proc.entry_step_number = entry
            proc.save()
            if force:
                proc.steps.all().delete()

        if force or was_created or not proc.steps.exists():
            for raw in steps:
                PlanningProcessStep.objects.update_or_create(
                    process=proc,
                    step_number=raw["step_number"],
                    defaults={
                        "title": raw["title"],
                        "description": raw.get("description") or "",
                        "kind": raw["kind"],
                        "question": raw.get("question") or "",
                        "yes_next_number": raw.get("yes_next_number"),
                        "no_next_number": raw.get("no_next_number"),
                        "next_number": raw.get("next_number"),
                        "data_binding": raw.get("data_binding") or "none",
                        "is_active": True,
                        "sort_order": raw["step_number"],
                    },
                )
                created["steps"] += 1
    return created
