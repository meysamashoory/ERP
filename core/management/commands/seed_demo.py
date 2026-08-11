"""Seed the database with realistic demo data for the production ERP.

Idempotent: safe to run repeatedly. Pass --flush to reset operational data.
"""

from decimal import Decimal

import jdatetime
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (
    CountingUnit,
    DeviationReason,
    Machine,
    MachineType,
    Product,
    ProductGroup,
    ProductKind,
    ProductSubGroup,
    ProductionTypeOption,
    ProductionUnit,
    ProgramChangeReason,
    MoldOption,
    StoppageReason,
)
from planning.models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine, Weekday
from production.models import FittingProduction, PipeProduction, ProductionStoppage

User = get_user_model()

PRODUCTION_TYPES = [
    "پروتکت", "جنرال", "سایلنت", "طوسی", "سرمه‌ای", "مشکی",
    "قرمز", "کرم", "زرد", "(ق ق)", "(ق ج)",
]

STOPPAGE_REASONS = [
    "برق دستگاه", "سیستم خنک کننده", "تست آزمایشگاه", "خرابی مواد",
    "خرابی قالب", "تست قالب", "توقف کنترل کیفیت", "قطعی برق شهر",
    "خطای اپراتور", "گرفتگی سر نازل", "بالا رفتن دمای", "خرابی دستگاه",
    "سایر موارد",
]

DEVIATION_REASONS = [
    "تعویض قالب", "راه‌اندازی قالب", "کمبود مواد", "برنامه‌ریزی مجدد",
    "توقف اضطراری", "افزایش حفره فعال", "کاهش حفره فعال", "سایر موارد",
]

PROGRAM_CHANGE_REASONS = [
    "تغییر دستگاه", "ایراد فنی", "ایراد کیفی", "کمبود مواد",
    "اولویت تولید", "سایر موارد",
]

MOLD_OPTIONS = ["قالب اصلی", "قالب دوم", "قالب کمکی"]

# group name -> (kind, [subgroups])
GROUPS = {
    "اتصالات پیچی (آبرسانی)": (ProductKind.FITTING, ["پیچی استاندارد", "فلنچدار", "کمربند و مغزی", "آبیاری قطره‌ای"]),
    "اتصالات فاضلابی": (ProductKind.FITTING, ["جوشی ۶+", "جوشی فشار قوی", "پوش‌فیت پروتکت", "پوش‌فیت جنرال", "پوش‌فیت سایلنت"]),
    "لوله‌ها": (ProductKind.PIPE, ["پوش‌فیت", "جنرال", "سایلنت", "فاضلابی", "آبرسانی", "خرطومی", "راند دریپردار", "راند بدون دریپر", "فلت دریپردار", "نوار آبیاری (تیپ)"]),
}


class Command(BaseCommand):
    help = "Seed demo master data, users, and sample production records."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Reset operational data first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            ProductionStoppage.objects.all().delete()
            FittingProduction.objects.all().delete()
            PipeProduction.objects.all().delete()
            WeeklyPlanLine.objects.all().delete()
            WeeklyPlanItem.objects.all().delete()
            WeeklyPlan.objects.all().delete()
            self.stdout.write("Operational data flushed.")

        self._seed_options()
        units = self._seed_units_and_machines()
        subgroups = self._seed_groups()
        products = self._seed_products(subgroups)
        self._seed_users()
        self._seed_production(units, products)
        self._seed_plan(units, subgroups, products)

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {ProductionUnit.objects.count()} units, "
            f"{Machine.objects.count()} machines, {Product.objects.count()} products, "
            f"{User.objects.count()} users, {FittingProduction.objects.count()} fitting records, "
            f"{PipeProduction.objects.count()} pipe records, {WeeklyPlan.objects.count()} plans."
        ))

    def _seed_options(self):
        for i, label in enumerate(PRODUCTION_TYPES):
            ProductionTypeOption.objects.get_or_create(label=label, defaults={"order": i})
        for i, label in enumerate(STOPPAGE_REASONS):
            StoppageReason.objects.get_or_create(label=label, defaults={"order": i})
        for i, label in enumerate(DEVIATION_REASONS):
            DeviationReason.objects.get_or_create(label=label, defaults={"order": i})
        for i, label in enumerate(PROGRAM_CHANGE_REASONS):
            ProgramChangeReason.objects.get_or_create(label=label, defaults={"order": i})
        for i, label in enumerate(MOLD_OPTIONS):
            MoldOption.objects.get_or_create(label=label, defaults={"order": i})

    def _seed_units_and_machines(self):
        specs = {
            1: ("واحد ۱", "۳۴ تزریق + کفتراش، تراشکاری، جوش، مونتاژ و بسته‌بندی", {MachineType.INJECTION: 34}),
            2: ("واحد ۲", "۱۶ تزریق + ۳ اکسترودر + ۲ بلینگ + جوش و بسته‌بندی",
                {MachineType.INJECTION: 16, MachineType.EXTRUDER: 3, MachineType.BLING: 2}),
            3: ("واحد ۳", "کوره روکش بست فلزی، پانچ و پرینت، مونتاژ و بسته‌بندی",
                {MachineType.FURNACE: 1, MachineType.PUNCH_PRINT: 2}),
            4: ("واحد ۴", "۷ تزریق + ۷ اکسترودر + جوش، مونتاژ و بسته‌بندی",
                {MachineType.INJECTION: 7, MachineType.EXTRUDER: 7}),
        }
        units = {}
        for number, (name, desc, machines) in specs.items():
            unit, _ = ProductionUnit.objects.get_or_create(
                number=number, defaults={"name": name, "description": desc}
            )
            units[number] = unit
            for mtype, count in machines.items():
                for n in range(1, count + 1):
                    Machine.objects.get_or_create(
                        unit=unit, machine_type=mtype, number=str(n)
                    )
        return units

    def _seed_groups(self):
        subgroups = {}
        for gi, (gname, (kind, subs)) in enumerate(GROUPS.items()):
            group, _ = ProductGroup.objects.get_or_create(
                name=gname, defaults={"order": gi, "kind": kind}
            )
            if group.kind != kind:
                group.kind = kind
                group.save(update_fields=["kind"])
            for si, sname in enumerate(subs):
                sg, _ = ProductSubGroup.objects.get_or_create(
                    group=group, name=sname, defaults={"order": si}
                )
                subgroups[(gname, sname)] = sg
        return subgroups

    def _seed_products(self, subgroups):
        specs = [
            ("F-0900", "سرپیچ ۹۰", ("اتصالات پیچی (آبرسانی)", "پیچی استاندارد"),
             CountingUnit.COUNT, dict(needs_assembly=True, needs_machining=True, per_carton=200, stock_finished=1800, reorder_level=500, unit_weight_grams=Decimal("165.00"))),
            ("F-1100", "سرپیچ ۱۱۰", ("اتصالات پیچی (آبرسانی)", "پیچی استاندارد"),
             CountingUnit.COUNT, dict(needs_assembly=True, needs_machining=True, per_carton=150, stock_finished=300, reorder_level=400, unit_weight_grams=Decimal("240.00"))),
            ("F-FLN6", "فلنچ ۶ بار", ("اتصالات فاضلابی", "جوشی فشار قوی"),
             CountingUnit.COUNT, dict(needs_machining=True, per_carton=80, stock_finished=640, reorder_level=200, unit_weight_grams=Decimal("310.00"))),
            ("F-PRT110", "زانو پروتکت ۱۱۰", ("اتصالات فاضلابی", "پوش‌فیت پروتکت"),
             CountingUnit.COUNT, dict(needs_assembly=False, per_carton=120, stock_finished=2600, reorder_level=600, unit_weight_grams=Decimal("190.00"))),
            ("F-SLNT75", "بوشن سایلنت ۷۵", ("اتصالات فاضلابی", "پوش‌فیت سایلنت"),
             CountingUnit.COUNT, dict(per_carton=140, stock_finished=180, reorder_level=300, unit_weight_grams=Decimal("95.00"))),
            ("P-PRT110", "لوله پروتکت ۱۱۰", ("لوله‌ها", "پوش‌فیت"),
             CountingUnit.BRANCH, dict(stock_finished=900, reorder_level=250, unit_weight_grams=Decimal("2500.00"))),
            ("P-WAT63", "لوله آبرسانی ۶۳", ("لوله‌ها", "آبرسانی"),
             CountingUnit.BRANCH, dict(stock_finished=430, reorder_level=150, unit_weight_grams=Decimal("1800.00"))),
            ("P-TAPE16", "نوار آبیاری تیپ ۱۶", ("لوله‌ها", "نوار آبیاری (تیپ)"),
             CountingUnit.COIL, dict(stock_finished=75, reorder_level=120, unit_weight_grams=Decimal("5200.00"))),
        ]
        products = {}
        for code, name, key, unit, extra in specs:
            product, _ = Product.objects.get_or_create(
                code=code,
                defaults=dict(name=name, subgroup=subgroups[key], counting_unit=unit, **extra),
            )
            products[code] = product
        return products

    def _seed_users(self):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": True, "first_name": "مدیر", "last_name": "سامانه"},
        )
        if created:
            admin.set_password("erp12345")
            admin.save()
        roles = [
            ("expert", "کارشناس", "planning_expert", False),
            ("clerk", "کارمند", "planning_clerk", False),
            ("viewer", "ناظر", "viewer", False),
        ]
        for username, first, role, can_edit in roles:
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "is_staff": True}
            )
            if created:
                user.set_password("erp12345")
                user.save()
            profile = user.profile
            profile.role = role
            profile.can_edit_others = can_edit
            profile.save()

    def _seed_production(self, units, products):
        if FittingProduction.objects.exists():
            return
        admin = User.objects.filter(username="admin").first()
        reason = StoppageReason.objects.first()
        dev_reason = DeviationReason.objects.filter(label="تعویض قالب").first()
        today = jdatetime.date.today()

        injection_u1 = Machine.objects.filter(unit=units[1], machine_type="injection").order_by("id")
        m1, m2 = injection_u1[0], injection_u1[1]

        f1 = FittingProduction.objects.create(
            unit=units[1], date=today - jdatetime.timedelta(days=2), machine=m1,
            product=products["F-0900"], shot_cycle=29, active_cavities=4,
            planned_quantity=4000, produced_quantity=3720, scrap_quantity=110,
            deviation_reason=dev_reason, created_by=admin,
        )
        ProductionStoppage.objects.create(fitting=f1, reason=reason, minutes=45, note="راه‌اندازی قالب")

        f2 = FittingProduction.objects.create(
            unit=units[1], date=today - jdatetime.timedelta(days=1), machine=m2,
            product=products["F-1100"], shot_cycle=34, active_cavities=2,
            planned_quantity=2000, produced_quantity=2050, scrap_quantity=40,
            created_by=admin,
        )
        ProductionStoppage.objects.create(
            fitting=f2, reason=StoppageReason.objects.all()[3], minutes=20, note="خرابی مواد اولیه"
        )

        extruder_u4 = Machine.objects.filter(unit=units[4], machine_type="extruder").order_by("id").first()
        PipeProduction.objects.create(
            unit=units[4], date=today - jdatetime.timedelta(days=1), line=extruder_u4,
            product=products["P-WAT63"], nominal_pressure="۱۰ بار",
            thickness=Decimal("5.80"), material_grade="PE100",
            planned_quantity=300, produced_quantity=280, scrap_quantity=6,
            created_by=admin,
        )

    def _seed_plan(self, units, subgroups, products):
        if WeeklyPlan.objects.exists():
            return
        admin = User.objects.filter(username="admin").first()
        today = jdatetime.date.today()
        plan = WeeklyPlan.objects.create(
            program_number="BP-1001", date=today, status=WeeklyPlan.Status.DRAFT, created_by=admin,
        )
        machine = Machine.objects.filter(unit=units[1], machine_type="injection").first()
        item = WeeklyPlanItem.objects.create(
            plan=plan, subgroup=subgroups[("اتصالات فاضلابی", "پوش‌فیت پروتکت")],
            unit=units[1], machine=machine, product=products["F-PRT110"],
            mold_change_weekday=Weekday.CHAHARSHANBE,
            mold_change_date=today + jdatetime.timedelta(days=3), active_cavities=4,
        )
        ptype = ProductionTypeOption.objects.filter(label="پروتکت").first()
        mold = MoldOption.objects.filter(label="قالب اصلی").first()
        WeeklyPlanLine.objects.create(
            item=item, production_type=ptype, mold=mold, quantity=5000, cycle=30
        )

        # An approved, running demo program with a day of stats (mirrors the
        # spec example: دستگاه 2 واحد 2، زانو ۱۱۰ پروتکت، سیکل ۴۲).
        from datetime import time as _time

        from production.models import ProductionDayEntry, ProductionProgram

        unit2 = units[2]
        m2 = Machine.objects.filter(unit=unit2, machine_type="injection").order_by("id")[1]
        approved = WeeklyPlan.objects.create(
            program_number="BP-1000", date=today, status=WeeklyPlan.Status.APPROVED,
            created_by=admin, approved_by=admin,
        )
        item2 = WeeklyPlanItem.objects.create(
            plan=approved, subgroup=subgroups[("اتصالات فاضلابی", "پوش‌فیت پروتکت")],
            unit=unit2, machine=m2, product=products["F-PRT110"],
            mold_change_weekday=Weekday.SHANBE, mold_change_date=today,
            active_cavities=4, sequence=1,
        )
        WeeklyPlanLine.objects.create(
            item=item2, production_type=ptype, mold=mold, quantity=6000, cycle=42
        )
        program = ProductionProgram.objects.create(
            item=item2, status=ProductionProgram.Status.RUNNING, change_type="setup",
            production_type=1, mold=mold, start_date=today, start_time=_time(9, 0),
        )
        ProductionDayEntry.objects.create(
            program=program, date=today, produced_quantity=1800, scrap_quantity=40,
            cycle=42, active_cavities=4,
            deviation_reason=DeviationReason.objects.filter(label="تعویض قالب").first(),
        )
