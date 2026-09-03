"""Accordion registry for «داده‌های سیستم» — full Django-admin capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class SystemItem:
    key: str
    title: str
    # Django admin reverse names, e.g. "admin:catalog_moldoption_changelist"
    admin_changelist: str = ""
    admin_add: str | None = None
    description: str = ""
    count_fn: Callable[[], int] | None = None
    can_add: bool = True
    # Optional named URL (non-admin) — preferred when set
    url_name: str | None = None
    add_url_name: str | None = None
    # Optional query string without leading «?», e.g. "source=transfer"
    url_query: str = ""


@dataclass
class SystemGroup:
    key: str
    title: str
    items: list[SystemItem]


def _count(model) -> Callable[[], int]:
    return lambda: model.objects.count()


def build_system_groups() -> list[SystemGroup]:
    from django.contrib.auth.models import Group, User

    from planning.models import (
        PlanningProcessStep,
        WeeklyPlan,
        WeeklyPlanItem,
    )
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
        FlexibleDataset,
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
        SystemNamingKey,
    )

    return [
        SystemGroup(
            key="meta",
            title="نام‌گذاری و ساختار نمایش",
            items=[
                SystemItem(
                    key="naming_keys",
                    title="کلیدهای نام‌گذاری سیستم",
                    admin_changelist="",
                    url_name="system_naming_keys",
                    description=(
                        "همه کلیدهای عنوان (بخش‌ها، سرستون‌ها، انتقال داده، گزارش‌ها) "
                        "با آدرس دقیق — قابل جستجو و تغییر نام."
                    ),
                    count_fn=_count(SystemNamingKey),
                    can_add=False,
                ),
                SystemItem(
                    key="table_columns",
                    title="سرستون‌های جداول سامانه",
                    admin_changelist="",
                    url_name="system_table_columns",
                    description=(
                        "تغییر نام، نمایش/پنهان، افزودن ستون سفارشی و ربط به بخش‌های مختلف."
                    ),
                    count_fn=lambda: SystemNamingKey.objects.filter(
                        category=SystemNamingKey.Category.COLUMN
                    ).count(),
                    can_add=False,
                ),
            ],
        ),
        SystemGroup(
            key="reports",
            title="گزارش‌ها",
            items=[
                SystemItem(
                    key="print_forms",
                    title="فرم‌های چاپی",
                    admin_changelist="admin:reports_printform_changelist",
                    admin_add="admin:reports_printform_add",
                    count_fn=_count(PrintForm),
                ),
                SystemItem(
                    key="saved_reports",
                    title="گزارش‌های ذخیره شده",
                    admin_changelist="admin:reports_savedreport_changelist",
                    admin_add="admin:reports_savedreport_add",
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
                    admin_changelist="admin:auth_user_changelist",
                    admin_add="admin:auth_user_add",
                    description="کاربران، گروه‌ها و مجوزهای سطح کاربر",
                    count_fn=_count(User),
                ),
                SystemItem(
                    key="groups",
                    title="گروه‌ها",
                    admin_changelist="admin:auth_group_changelist",
                    admin_add="admin:auth_group_add",
                    description="گروه‌ها و صدور مجوزهای گروهی",
                    count_fn=_count(Group),
                ),
            ],
        ),
        SystemGroup(
            key="weekly",
            title="برنامه‌ریزی هفتگی",
            items=[
                SystemItem(
                    key="planning_process",
                    title="منطق فرآیند برنامه‌ریزی (مراحل)",
                    admin_changelist="",
                    url_name="planning_process_list",
                    description=(
                        "مراحل شماره‌دار Make to Order / Make to Stock از روی PDF؛ "
                        "سوال‌های بله/خیر با اتصال به مرحله بعدی و داده سیستم — قابل بازتعریف."
                    ),
                    count_fn=_count(PlanningProcessStep),
                    can_add=False,
                ),
                SystemItem(
                    key="systemic_intelligence",
                    title="هوش برنامه‌ریزی سیستمی",
                    admin_changelist="",
                    url_name="systemic_intelligence",
                    description=(
                        "تراز تقاضا و تأمین، کسری BOM، بار دستگاه، انحراف برنامه–واقعی "
                        "و پیام‌های برنامه‌ریزی متناسب با برنامه هفتگی قالب."
                    ),
                    count_fn=lambda: WeeklyPlan.objects.filter(planning_mode="systemic").count(),
                    can_add=False,
                ),
                SystemItem(
                    key="weekly_plans",
                    title="برنامه‌ریزی هفتگی",
                    admin_changelist="admin:planning_weeklyplan_changelist",
                    admin_add="admin:planning_weeklyplan_add",
                    count_fn=_count(WeeklyPlan),
                ),
                SystemItem(
                    key="plan_items",
                    title="کالاهای برنامه",
                    admin_changelist="admin:planning_weeklyplanitem_changelist",
                    admin_add="admin:planning_weeklyplanitem_add",
                    count_fn=_count(WeeklyPlanItem),
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
                    admin_changelist="admin:production_productiondayentry_changelist",
                    admin_add="admin:production_productiondayentry_add",
                    count_fn=_count(ProductionDayEntry),
                ),
                SystemItem(
                    key="programs",
                    title="برنامه‌های تولید",
                    admin_changelist="admin:production_productionprogram_changelist",
                    admin_add="admin:production_productionprogram_add",
                    count_fn=_count(ProductionProgram),
                ),
                SystemItem(
                    key="fittings",
                    title="تولید روزانه اتصالات",
                    admin_changelist="admin:production_fittingproduction_changelist",
                    admin_add="admin:production_fittingproduction_add",
                    count_fn=_count(FittingProduction),
                ),
                SystemItem(
                    key="history",
                    title="سوابق تولید",
                    admin_changelist="admin:production_productionhistoryrecord_changelist",
                    admin_add="admin:production_productionhistoryrecord_add",
                    count_fn=_count(ProductionHistoryRecord),
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
                    admin_changelist="admin:catalog_systemalarm_changelist",
                    admin_add="admin:catalog_systemalarm_add",
                    description="بررسی و پاک‌سازی",
                    count_fn=lambda: SystemAlarm.objects.filter(
                        status=SystemAlarm.Status.OPEN
                    ).count(),
                ),
                SystemItem(
                    key="molds",
                    title="انواع قالب",
                    admin_changelist="admin:catalog_moldoption_changelist",
                    admin_add="admin:catalog_moldoption_add",
                    count_fn=_count(MoldOption),
                ),
                SystemItem(
                    key="planning_display",
                    title="تنظیمات کادر آبی قسمت برنامه‌ریزی هفتگی",
                    admin_changelist="admin:catalog_planningdisplaysettings_changelist",
                    admin_add=None,
                    can_add=False,
                    count_fn=_count(PlanningDisplaySettings),
                ),
                SystemItem(
                    key="excel_tables",
                    title="جداول اکسل",
                    admin_changelist="admin:catalog_exceltable_changelist",
                    admin_add="admin:catalog_exceltable_add",
                    count_fn=_count(ExcelTable),
                ),
                SystemItem(
                    key="excel_uploads",
                    title="فایل‌های اکسل / CSV",
                    admin_changelist="",
                    url_name="excel_list",
                    description="ورود، مشاهده TABLE/SHEETS و انتقال داده",
                    count_fn=_count(ExcelUpload),
                    can_add=True,
                    add_url_name="excel_import",
                ),
                SystemItem(
                    key="transfer_dialog_labels",
                    title="عناوین دیالوگ و مقاصد انتقال داده",
                    admin_changelist="",
                    url_name="system_naming_keys",
                    url_query="source=transfer",
                    description=(
                        "عنوان دیالوگ انتقال/بروزرسانی، بخش مقصد، سطح‌ها و فیلدهای نگاشت. "
                        "پنهان کردن مقصد یا فیلد، آن را از دیالوگ انتقال حذف می‌کند."
                    ),
                    count_fn=lambda: SystemNamingKey.objects.filter(
                        key__startswith="transfer.", is_active=True
                    ).count(),
                    can_add=False,
                ),
                SystemItem(
                    key="product_data_hub",
                    title="دیتای محصولات (هاب)",
                    admin_changelist="",
                    url_name="product_data",
                    description=(
                        "تب‌های خام محصولات/BOM/مواد مصرفی/مشخصات فنی؛ "
                        "جدول پس از انتقال اکسل ساخته می‌شود. تب‌ها و سرستون‌ها و ستون‌های کلیدی از نام‌گذاری سیستم."
                    ),
                    count_fn=lambda: FlexibleDataset.objects.filter(
                        destination_id="product_data"
                    ).count(),
                    can_add=False,
                ),
                SystemItem(
                    key="vouchers_hub",
                    title="حواله‌ها (تب در دیتای محصولات)",
                    admin_changelist="",
                    url_name="product_data",
                    url_query="tab=vouchers",
                    description="حواله‌ها به‌عنوان تب دیتای محصولات — خام تا انتقال اکسل",
                    count_fn=lambda: FlexibleDataset.objects.filter(
                        destination_id="product_data", level_id="vouchers"
                    ).count(),
                    can_add=False,
                ),
                SystemItem(
                    key="machines",
                    title="دستگاه و خطوط",
                    admin_changelist="admin:catalog_machine_changelist",
                    admin_add="admin:catalog_machine_add",
                    count_fn=_count(Machine),
                ),
                SystemItem(
                    key="deviation_reasons",
                    title="دلایل انحراف",
                    admin_changelist="admin:catalog_deviationreason_changelist",
                    admin_add="admin:catalog_deviationreason_add",
                    count_fn=_count(DeviationReason),
                ),
                SystemItem(
                    key="change_reasons",
                    title="دلایل تغییر برنامه",
                    admin_changelist="admin:catalog_programchangereason_changelist",
                    admin_add="admin:catalog_programchangereason_add",
                    count_fn=_count(ProgramChangeReason),
                ),
                SystemItem(
                    key="stop_reasons",
                    title="دلایل توقف",
                    admin_changelist="admin:catalog_stoppagereason_changelist",
                    admin_add="admin:catalog_stoppagereason_add",
                    count_fn=_count(StoppageReason),
                ),
                SystemItem(
                    key="product_groups",
                    title="گروه‌های محصولات",
                    admin_changelist="admin:catalog_productgroup_changelist",
                    admin_add="admin:catalog_productgroup_add",
                    count_fn=_count(ProductGroup),
                ),
                SystemItem(
                    key="product_subgroups",
                    title="زیرگروه محصولات",
                    admin_changelist="admin:catalog_productsubgroup_changelist",
                    admin_add="admin:catalog_productsubgroup_add",
                    count_fn=_count(ProductSubGroup),
                ),
                SystemItem(
                    key="bom",
                    title="ساختار BOM",
                    admin_changelist="admin:catalog_productbomline_changelist",
                    admin_add="admin:catalog_productbomline_add",
                    count_fn=_count(ProductBomLine),
                ),
                SystemItem(
                    key="insight_fields",
                    title="فیلد اطلاعات نوار شیشه‌ای",
                    admin_changelist="admin:catalog_planninginsightfield_changelist",
                    admin_add="admin:catalog_planninginsightfield_add",
                    count_fn=_count(PlanningInsightField),
                ),
                SystemItem(
                    key="uid_scheme",
                    title="قانون شناسه برنامه‌ریزی",
                    admin_changelist="admin:catalog_programuidscheme_changelist",
                    admin_add=None,
                    can_add=False,
                    count_fn=_count(ProgramUidScheme),
                ),
                SystemItem(
                    key="products",
                    title="محصولات و قطعات",
                    admin_changelist="admin:catalog_product_changelist",
                    admin_add="admin:catalog_product_add",
                    count_fn=_count(Product),
                ),
                SystemItem(
                    key="consumables",
                    title="مواد مصرفی",
                    admin_changelist="admin:catalog_productconsumable_changelist",
                    admin_add="admin:catalog_productconsumable_add",
                    count_fn=_count(ProductConsumable),
                ),
                SystemItem(
                    key="units",
                    title="واحد‌های تولید",
                    admin_changelist="admin:catalog_productionunit_changelist",
                    admin_add="admin:catalog_productionunit_add",
                    count_fn=_count(ProductionUnit),
                ),
                SystemItem(
                    key="production_types",
                    title="نوع تولید",
                    admin_changelist="admin:catalog_productiontypeoption_changelist",
                    admin_add="admin:catalog_productiontypeoption_add",
                    count_fn=_count(ProductionTypeOption),
                ),
            ],
        ),
    ]

