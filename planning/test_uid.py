import jdatetime
from django.test import TestCase

from planning.uid import (
    build_program_uid,
    excel_serial,
    excel_year_day_offset,
    year_code,
)


class ProgramUidSchemeTests(TestCase):
    def test_year_codes(self):
        self.assertEqual(year_code(1405), 36)
        self.assertEqual(year_code(1409), 40)

    def test_excel_serials_match_reference(self):
        self.assertEqual(excel_serial(jdatetime.date(1405, 1, 1)), 46102)
        self.assertEqual(excel_serial(jdatetime.date(1406, 1, 1)), 46467)
        self.assertEqual(excel_serial(jdatetime.date(1405, 5, 26)), 46251)
        self.assertEqual(excel_serial(jdatetime.date(1405, 5, 28)), 46253)

    def test_day_offsets(self):
        self.assertEqual(excel_year_day_offset(jdatetime.date(1405, 5, 26)), 149)
        self.assertEqual(excel_year_day_offset(jdatetime.date(1405, 5, 27)), 150)
        self.assertEqual(excel_year_day_offset(jdatetime.date(1405, 5, 28)), 151)

    def test_full_example_36159402299223(self):
        """User reference: plan 159 on 1405-05-26, unit 4, machine 2,
        mold change 1405-05-27, production type 2, mold row 23.
        """
        uid = build_program_uid(
            plan_date=jdatetime.date(1405, 5, 26),
            program_number=159,
            unit_number=4,
            machine_number=2,
            mold_change_date=jdatetime.date(1405, 5, 27),
            production_type_index=2,
            mold_row=23,
        )
        self.assertEqual(uid, "36159402299223")
        self.assertEqual(len(uid), 14)

    def test_date_sum_300_case(self):
        uid = build_program_uid(
            plan_date=jdatetime.date(1405, 5, 26),
            program_number=159,
            unit_number=1,
            machine_number=3,
            mold_change_date=jdatetime.date(1405, 5, 28),
            production_type_index=1,
            mold_row=5,
        )
        # 36 159 1 03 300 1 05
        self.assertEqual(uid, "36159103300105")

    def test_program_number_from_prefixed_string(self):
        uid = build_program_uid(
            plan_date=jdatetime.date(1405, 5, 26),
            program_number="BP-159",
            unit_number=4,
            machine_number="02",
            mold_change_date=jdatetime.date(1405, 5, 27),
            production_type_index=2,
            mold_row=23,
        )
        self.assertEqual(uid, "36159402299223")


class ProgramUidAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_demo")

    def test_assign_uids_on_plan_items(self):
        from catalog.models import Machine, Product, ProductionTypeOption, ProductionUnit
        from planning.models import Weekday, WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
        from planning.uid import refresh_plan_uids

        unit = ProductionUnit.objects.get(number=1)
        machine = Machine.objects.filter(unit=unit, number="2").first() or Machine.objects.filter(unit=unit).first()
        product = Product.objects.first()
        plan = WeeklyPlan.objects.create(
            program_number="159",
            date=jdatetime.date(1405, 5, 26),
            status=WeeklyPlan.Status.DRAFT,
        )
        # Create 23 placeholder rows so the real item becomes mold row 23
        for i in range(22):
            WeeklyPlanItem.objects.create(
                plan=plan,
                subgroup=product.subgroup,
                unit=unit,
                machine=machine,
                product=product,
                mold_change_weekday=Weekday.SHANBE,
                mold_change_date=jdatetime.date(1405, 5, 20),
                active_cavities=1,
                sequence=1,
            )
        unit4 = ProductionUnit.objects.filter(number=4).first() or unit
        machine2 = Machine.objects.filter(unit=unit4, number="2").first()
        if machine2 is None:
            machine2 = Machine.objects.create(unit=unit4, machine_type="injection", number="2")
        item = WeeklyPlanItem.objects.create(
            plan=plan,
            subgroup=product.subgroup,
            unit=unit4,
            machine=machine2,
            product=product,
            mold_change_weekday=Weekday.YEKSHANBE,
            mold_change_date=jdatetime.date(1405, 5, 27),
            active_cavities=4,
            sequence=1,
        )
        pt = ProductionTypeOption.objects.first()
        WeeklyPlanLine.objects.create(item=item, production_type=pt, quantity=100, cycle=30)
        WeeklyPlanLine.objects.create(item=item, production_type=pt, quantity=200, cycle=40)
        refresh_plan_uids(plan)
        item.refresh_from_db()
        lines = list(item.lines.order_by("id"))
        self.assertEqual(lines[0].uid, item.uid)
        self.assertEqual(lines[1].uid, "36159402299223")
        self.assertEqual(len(item.uid), 14)
