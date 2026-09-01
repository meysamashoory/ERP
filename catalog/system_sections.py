"""Accordion registry for «داده‌های سیستم» — in-app destinations (not bare admin)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SystemItem:
    key: str
    title: str
    # Prefer named URL when the app already has a page; else use generic section key.
    url_name: str | None = None
    url_kwargs: dict[str, Any] = field(default_factory=dict)
    section_key: str | None = None  # generic /data/system/<key>/
    description: str = ""
    count_fn: Callable[[], int] | None = None
    can_add: bool = True


@dataclass
class SystemGroup:
    key: str
    title: str
    items: list[SystemItem]


def _count(model) -> Callable[[], int]:
    return lambda: model.objects.count()


def build_system_groups() -> list[SystemGroup]:
    from django.contrib.auth.models import Group, User

    from accounts.models import UserProfile
    from planning.models import WeeklyPlan, WeeklyPlanItem
    from production.models import (
        FittingProduction,
        ProductionDayEntry,
        ProductionHistoryRecord,
        ProductionProgram,
    )
    from reports.models import PrintForm, SavedReport

    from .models import (
        DeviationReason,
        ExcelTable,
        ExcelUpload,
        Machine,
        MoldOption,
        PlanningDisplaySettings,
        PlanningInsightField,
        Product,
        ProductBomLine,
        ProductConsumable,
        ProductGroup,
        ProductSubGroup,
        ProductionTypeOption,
        ProductionUnit,
        ProgramChangeReason,
        ProgramUidScheme,
        StoppageReason,
        SystemAlarm,
    )

    return [
        SystemGroup(
            key="reports",
            title="گزارش‌ها",
            items=[
                SystemItem(
                    key="print_forms",
                    title="فرم‌های چاپی",
                    url_name="print_form_list",
                    count_fn=_count(PrintForm),
                ),
                SystemItem(
                    key="saved_reports",
                    title="گزارش‌های ذخیره شده",
                    url_name="report_list",
                    count_fn=_count(SavedReport),
                ),
            ],
        ),
        SystemGroup(
            key="permissions",
            title="بررسی مجوزها",
            items=[
                SystemItem(
                    key="users",
                    title="کاربرها",
                    url_name="user_management",
                    count_fn=_count(User),
                    can_add=True,
                ),
                SystemItem(
                    key="groups",
                    title="گروه‌ها",
                    section_key="groups",
                    count_fn=_count(Group),
                ),
            ],
        ),
        SystemGroup(
            key="weekly",
            title="برنامه‌ریزی هفتگی",
            items=[
                SystemItem(
                    key="weekly_plans",
                    title="برنامه‌ریزی هفتگی",
                    url_name="plan_list",
                    count_fn=_count(WeeklyPlan),
                    can_add=False,
                ),
                SystemItem(
                    key="plan_items",
                    title="کالاهای برنامه",
                    section_key="plan_items",
                    count_fn=_count(WeeklyPlanItem),
                    can_add=False,
                ),
            ],
        ),
        SystemGroup(
            key="daily",
            title="ثبت تولید روزانه",
            items=[
                SystemItem(
                    key="day_entries",
                    title="آمار تولید روزانه",
                    section_key="day_entries",
                    count_fn=_count(ProductionDayEntry),
                    can_add=False,
                ),
                SystemItem(
                    key="programs",
                    title="برنامه‌های تولید",
                    url_name="program_list",
                    count_fn=_count(ProductionProgram),
                    can_add=False,
                ),
                SystemItem(
                    key="fittings",
                    title="تولید روزانه اتصالات",
                    section_key="fittings",
                    count_fn=_count(FittingProduction),
                    can_add=False,
                ),
                SystemItem(
                    key="history",
                    title="سوابق تولید",
                    url_name="production_history",
                    count_fn=_count(ProductionHistoryRecord),
                    can_add=False,
                ),
            ],
        ),
        SystemGroup(
            key="base",
            title="داده‌های پایه",
            items=[
                SystemItem(
                    key="alarms",
                    title="آلارم‌های سیستم",
                    section_key="alarms",
                    description="بررسی و پاک‌سازی",
                    count_fn=lambda: SystemAlarm.objects.filter(
                        status=SystemAlarm.Status.OPEN
                    ).count(),
                ),
                SystemItem(
                    key="molds",
                    title="انواع قالب",
                    section_key="molds",
                    count_fn=_count(MoldOption),
                ),
                SystemItem(
                    key="planning_display",
                    title="تنظیمات کادر آبی قسمت برنامه‌ریزی هفتگی",
                    section_key="planning_display",
                    count_fn=_count(PlanningDisplaySettings),
                    can_add=False,
                ),
                SystemItem(
                    key="excel_tables",
                    title="جداول اکسل",
                    url_name="excel_list",
                    count_fn=_count(ExcelTable),
                ),
                SystemItem(
                    key="machines",
                    title="دستگاه و خطوط",
                    section_key="machines",
                    count_fn=_count(Machine),
                ),
                SystemItem(
                    key="deviation_reasons",
                    title="دلایل انحراف",
                    section_key="deviation_reasons",
                    count_fn=_count(DeviationReason),
                ),
                SystemItem(
                    key="change_reasons",
                    title="دلایل تغییر برنامه",
                    section_key="change_reasons",
                    count_fn=_count(ProgramChangeReason),
                ),
                SystemItem(
                    key="stop_reasons",
                    title="دلایل توقف",
                    section_key="stop_reasons",
                    count_fn=_count(StoppageReason),
                ),
                SystemItem(
                    key="product_groups",
                    title="گروه‌های محصولات",
                    section_key="product_groups",
                    count_fn=_count(ProductGroup),
                ),
                SystemItem(
                    key="product_subgroups",
                    title="زیرگروه محصولات",
                    section_key="product_subgroups",
                    count_fn=_count(ProductSubGroup),
                ),
                SystemItem(
                    key="bom",
                    title="ساختار BOM",
                    url_name="product_data",
                    url_kwargs={"tab": "bom"},
                    count_fn=_count(ProductBomLine),
                    can_add=False,
                ),
                SystemItem(
                    key="insight_fields",
                    title="فیلد اطلاعات نوار شیشه‌ای",
                    section_key="insight_fields",
                    count_fn=_count(PlanningInsightField),
                ),
                SystemItem(
                    key="uid_scheme",
                    title="قانون شناسه برنامه‌ریزی",
                    section_key="uid_scheme",
                    count_fn=_count(ProgramUidScheme),
                    can_add=False,
                ),
                SystemItem(
                    key="products",
                    title="محصولات و قطعات",
                    url_name="product_data",
                    count_fn=_count(Product),
                ),
                SystemItem(
                    key="consumables",
                    title="مواد مصرفی",
                    url_name="product_data",
                    url_kwargs={"tab": "consumables"},
                    count_fn=_count(ProductConsumable),
                    can_add=False,
                ),
                SystemItem(
                    key="units",
                    title="واحد‌های تولید",
                    section_key="units",
                    count_fn=_count(ProductionUnit),
                ),
                SystemItem(
                    key="production_types",
                    title="نوع تولید",
                    section_key="production_types",
                    count_fn=_count(ProductionTypeOption),
                ),
            ],
        ),
    ]


# Generic section configs: model + columns for in-app list/edit
def section_specs() -> dict[str, dict[str, Any]]:
    from django.contrib.auth.models import Group

    from accounts.models import UserProfile
    from planning.models import WeeklyPlanItem
    from production.models import FittingProduction, ProductionDayEntry

    from .models import (
        DeviationReason,
        Machine,
        MoldOption,
        PlanningDisplaySettings,
        PlanningInsightField,
        ProductGroup,
        ProductSubGroup,
        ProductionTypeOption,
        ProductionUnit,
        ProgramChangeReason,
        ProgramUidScheme,
        StoppageReason,
        SystemAlarm,
    )

    return {
        "groups": {
            "title": "گروه‌ها",
            "model": Group,
            "fields": ["name"],
            "labels": {"name": "نام"},
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
        },
        "plan_items": {
            "title": "کالاهای برنامه",
            "model": WeeklyPlanItem,
            "fields": ["id", "plan", "product", "machine", "sequence"],
            "labels": {
                "id": "شناسه",
                "plan": "برنامه",
                "product": "محصول",
                "machine": "دستگاه",
                "sequence": "ردیف",
            },
            "can_add": False,
            "can_edit": False,
            "can_delete": False,
            "select_related": ["plan", "product", "machine"],
        },
        "day_entries": {
            "title": "آمار تولید روزانه",
            "model": ProductionDayEntry,
            "fields": ["id", "program", "date", "produced_quantity", "planned_quantity"],
            "labels": {
                "id": "شناسه",
                "program": "برنامه",
                "date": "تاریخ",
                "produced_quantity": "تولید",
                "planned_quantity": "برنامه",
            },
            "can_add": False,
            "can_edit": False,
            "can_delete": False,
            "select_related": ["program"],
        },
        "fittings": {
            "title": "تولید روزانه اتصالات",
            "model": FittingProduction,
            "fields": ["id", "date", "unit", "product", "produced_quantity"],
            "labels": {
                "id": "شناسه",
                "date": "تاریخ",
                "unit": "واحد",
                "product": "محصول",
                "produced_quantity": "تولید",
            },
            "can_add": False,
            "can_edit": False,
            "can_delete": False,
            "select_related": ["unit", "product"],
        },
        "alarms": {
            "title": "آلارم‌های سیستم",
            "model": SystemAlarm,
            "fields": ["id", "title", "severity", "status", "created_at"],
            "labels": {
                "id": "شناسه",
                "title": "عنوان",
                "severity": "شدت",
                "status": "وضعیت",
                "created_at": "زمان",
            },
            "can_add": False,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["status"],
        },
        "molds": {
            "title": "انواع قالب",
            "model": MoldOption,
            "fields": ["id", "label", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "عنوان",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "order", "is_active"],
        },
        "planning_display": {
            "title": "تنظیمات کادر آبی قسمت برنامه‌ریزی هفتگی",
            "model": PlanningDisplaySettings,
            "fields": [
                "id",
                "height_coefficient",
                "matrix_unit_numbers",
                "show_group_breakdown",
            ],
            "labels": {
                "id": "شناسه",
                "height_coefficient": "ضریب ارتفاع",
                "matrix_unit_numbers": "واحدهای ماتریس",
                "show_group_breakdown": "تفکیک گروه",
            },
            "can_add": False,
            "can_edit": True,
            "can_delete": False,
            "edit_fields": [
                "height_coefficient",
                "matrix_unit_numbers",
                "show_group_breakdown",
            ],
        },
        "machines": {
            "title": "دستگاه و خطوط",
            "model": Machine,
            "fields": ["id", "unit", "machine_type", "number", "is_active"],
            "labels": {
                "id": "شناسه",
                "unit": "واحد",
                "machine_type": "نوع",
                "number": "شماره",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["unit", "machine_type", "number", "is_active"],
            "select_related": ["unit"],
        },
        "deviation_reasons": {
            "title": "دلایل انحراف",
            "model": DeviationReason,
            "fields": ["id", "label", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "عنوان",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "order", "is_active"],
        },
        "change_reasons": {
            "title": "دلایل تغییر برنامه",
            "model": ProgramChangeReason,
            "fields": ["id", "label", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "عنوان",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "order", "is_active"],
        },
        "stop_reasons": {
            "title": "دلایل توقف",
            "model": StoppageReason,
            "fields": ["id", "label", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "عنوان",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "order", "is_active"],
        },
        "product_groups": {
            "title": "گروه‌های محصولات",
            "model": ProductGroup,
            "fields": ["id", "name", "kind", "order"],
            "labels": {
                "id": "شناسه",
                "name": "نام",
                "kind": "نوع",
                "order": "ترتیب",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["name", "kind", "order"],
        },
        "product_subgroups": {
            "title": "زیرگروه محصولات",
            "model": ProductSubGroup,
            "fields": ["id", "group", "name", "order"],
            "labels": {
                "id": "شناسه",
                "group": "گروه",
                "name": "نام",
                "order": "ترتیب",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["group", "name", "order"],
            "select_related": ["group"],
        },
        "insight_fields": {
            "title": "فیلد اطلاعات نوار شیشه‌ای",
            "model": PlanningInsightField,
            "fields": ["id", "label", "source", "source_key", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "برچسب",
                "source": "منبع",
                "source_key": "کلید",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "source", "source_key", "order", "is_active"],
        },
        "uid_scheme": {
            "title": "قانون شناسه برنامه‌ریزی",
            "model": ProgramUidScheme,
            "fields": ["id", "name", "is_active", "base_year"],
            "labels": {
                "id": "شناسه",
                "name": "نام",
                "is_active": "فعال",
                "base_year": "سال پایه",
            },
            "can_add": False,
            "can_edit": True,
            "can_delete": False,
            "edit_fields": ["name", "is_active", "base_year", "notes"],
        },
        "units": {
            "title": "واحد‌های تولید",
            "model": ProductionUnit,
            "fields": ["id", "number", "name", "description"],
            "labels": {
                "id": "شناسه",
                "number": "شماره",
                "name": "نام",
                "description": "توضیح",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["number", "name", "description"],
        },
        "production_types": {
            "title": "نوع تولید",
            "model": ProductionTypeOption,
            "fields": ["id", "label", "order", "is_active"],
            "labels": {
                "id": "شناسه",
                "label": "عنوان",
                "order": "ترتیب",
                "is_active": "فعال",
            },
            "can_add": True,
            "can_edit": True,
            "can_delete": True,
            "edit_fields": ["label", "order", "is_active"],
        },
        "profiles": {
            "title": "پروفایل کاربران",
            "model": UserProfile,
            "fields": ["id", "user", "role", "can_edit_others"],
            "labels": {
                "id": "شناسه",
                "user": "کاربر",
                "role": "نقش",
                "can_edit_others": "ویرایش دیگران",
            },
            "can_add": False,
            "can_edit": True,
            "can_delete": False,
            "edit_fields": ["role", "can_edit_others"],
            "select_related": ["user"],
        },
    }


def get_section_spec(key: str) -> dict[str, Any] | None:
    return section_specs().get(key)
