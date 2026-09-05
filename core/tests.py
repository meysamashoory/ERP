import datetime

import jdatetime
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from catalog.models import Machine, Product, ProductionUnit, ProductionTypeOption
from planning.models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine, Weekday
from production.models import ProductionDayEntry, ProductionProgram
from production.timeutils import day_active_seconds, expected_shots, to_gregorian

User = get_user_model()


class SeedAndDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_seed_is_idempotent(self):
        machines = Machine.objects.count()
        products = Product.objects.count()
        call_command("seed_demo")
        self.assertEqual(Machine.objects.count(), machines)
        self.assertEqual(Product.objects.count(), products)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_dashboard_loads(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "داشبورد عملیات")

    def test_reports_excel_export(self):
        self.client.login(username="admin", password="erp12345")
        from reports.models import SavedReport

        report = SavedReport.objects.create(
            owner=User.objects.get(username="admin"),
            title="گزارش تولید",
            number=11,
            data_source="fitting",
            columns=[
                {"key": "date", "source": "fitting", "level": 1},
                {"key": "product", "source": "fitting", "level": 1},
                {"key": "produced", "source": "fitting", "level": 1},
            ],
        )
        resp = self.client.get(reverse("report_detail", args=[report.pk]), {"export": "excel"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_viewer_cannot_enter_data(self):
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("pipe_create")).status_code, 403)

    def test_expert_can_enter_data(self):
        self.client.login(username="expert", password="erp12345")
        self.assertEqual(self.client.get(reverse("pipe_create")).status_code, 200)

    def test_clerk_cannot_create_plan(self):
        self.client.login(username="clerk", password="erp12345")
        self.assertEqual(self.client.get(reverse("plan_create")).status_code, 403)

    def test_superuser_is_manager(self):
        self.assertEqual(User.objects.get(username="admin").profile.role, Role.PLANNING_MANAGER)


class ShiftMathTests(TestCase):
    def test_expected_shots_example(self):
        # Start Sat 1405-05-24 at 09:00; the work-day runs to Sun 07:00 -> 22h.
        start = to_gregorian(jdatetime.date(1405, 5, 24), datetime.time(9, 0))
        secs = day_active_seconds(start, None, jdatetime.date(1405, 5, 24))
        self.assertEqual(secs, 22 * 3600)  # 79200
        self.assertEqual(expected_shots(secs, 42), 1886)


class ProgramFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def _make_program(self):
        unit = ProductionUnit.objects.get(number=1)
        machine = Machine.objects.filter(unit=unit, machine_type="injection").first()
        product = Product.objects.get(code="F-0900")
        plan = WeeklyPlan.objects.create(
            program_number="BP-TEST", date=jdatetime.date(1405, 5, 24),
            status=WeeklyPlan.Status.APPROVED,
        )
        item = WeeklyPlanItem.objects.create(
            plan=plan, subgroup=product.subgroup, unit=unit, machine=machine,
            product=product, mold_change_weekday=Weekday.SHANBE,
            mold_change_date=jdatetime.date(1405, 5, 24), active_cavities=4, sequence=1,
        )
        WeeklyPlanLine.objects.create(
            item=item, production_type=ProductionTypeOption.objects.first(),
            quantity=6000, cycle=42,
        )
        program = ProductionProgram.objects.create(
            item=item, status=ProductionProgram.Status.RUNNING,
            change_type="setup", production_type=1,
            start_date=jdatetime.date(1405, 5, 24), start_time=datetime.time(9, 0),
        )
        return program

    def test_day_entry_planned_and_deviation(self):
        program = self._make_program()
        entry = ProductionDayEntry.objects.create(
            program=program, date=jdatetime.date(1405, 5, 24),
            produced_quantity=1800, cycle=42, active_cavities=4,
        )
        self.assertEqual(entry.planned_quantity, 1886)
        self.assertEqual(entry.deviation, 86)  # behind plan

    def test_product_needs_reorder(self):
        self.assertTrue(Product.objects.get(code="F-1100").needs_reorder)
        self.assertFalse(Product.objects.get(code="F-0900").needs_reorder)

    def test_start_form_has_no_mold_field(self):
        from production.forms import ProgramStartForm
        program = self._make_program()
        program.status = ProductionProgram.Status.AWAITING
        program.save()
        form = ProgramStartForm(program=program)
        self.assertNotIn("mold", form.fields)
        self.assertIn("production_type", form.fields)


class PlanningUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_view_mode_hides_header_edit(self):
        self.client.login(username="admin", password="erp12345")
        plan = WeeklyPlan.objects.get(program_number="BP-1000")  # approved
        resp = self.client.get(reverse("plan_detail", args=[plan.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "ویرایش شماره و تاریخ")
        self.assertNotContains(resp, "صفحه اصلی")
        self.assertNotContains(resp, "تأیید برنامه")

    def test_edit_mode_shows_finalize(self):
        self.client.login(username="admin", password="erp12345")
        plan = WeeklyPlan.objects.get(program_number="BP-1001")  # draft
        resp = self.client.get(reverse("plan_detail", args=[plan.pk]) + "?mode=edit")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ویرایش شماره و تاریخ")
        self.assertContains(resp, "در حال ویرایش")
        self.assertContains(resp, "plan-matrix")
        self.assertNotContains(resp, "صفحه اصلی")

    def test_sidebar_branding_and_logout(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "سامانه برنامه ریزی")
        self.assertContains(resp, "و کنترل تولید")
        self.assertContains(resp, "خروج از سامانه")
        self.assertNotContains(resp, "مدیر سامانه")
        self.assertContains(resp, "(admin)")

    def test_plan_list_status_labels(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("plan_list"))
        self.assertContains(resp, "تعداد قالب برنامه")
        self.assertContains(resp, "تعداد قالب فعال")
        self.assertContains(resp, "تقویم برنامه")
        self.assertContains(resp, "عملیات")
        self.assertContains(resp, "plan-filter-col")
        self.assertContains(resp, "topbar-filter")
        self.assertNotContains(resp, "تغییر وضعیت")
        self.assertNotContains(resp, "تأیید (تأییدشده)")

    def test_plan_detail_edit_has_matrix_and_blue_insights(self):
        self.client.login(username="admin", password="erp12345")
        plan = WeeklyPlan.objects.get(program_number="BP-1001")
        resp = self.client.get(reverse("plan_detail", args=[plan.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "روز تعویض")
        self.assertContains(resp, "plan-matrix")
        self.assertContains(resp, "data-insights")
        self.assertNotContains(resp, "کالاهای برنامه")
        self.assertContains(resp, "items-scroll")

    def test_plan_detail_view_has_green_glass_no_matrix(self):
        self.client.login(username="admin", password="erp12345")
        plan = WeeklyPlan.objects.get(program_number="BP-1000")
        resp = self.client.get(reverse("plan_detail", args=[plan.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mold-glass-green")
        self.assertNotContains(resp, "plan-matrix-panel")
        self.assertContains(resp, "قالب")


class BackupRestoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_expert_cannot_open_backup_center(self):
        self.client.login(username="expert", password="erp12345")
        self.assertEqual(self.client.get(reverse("backup_center")).status_code, 403)

    def test_viewer_cannot_open_backup_center(self):
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("backup_center")).status_code, 403)

    def test_manager_page_shows_path_fields(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("backup_center"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "dest_path")
        self.assertContains(resp, "source_path")
        self.assertContains(resp, "داده‌های پایه سامانه")
        self.assertContains(resp, "ثبت و سوابق تولید")
        self.assertContains(resp, "گزارش‌ها و فرم‌های چاپی")
        self.assertContains(resp, "آدرس ذخیره روی سرور")

    def test_dashboard_nav_has_backup_link(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "پشتیبان‌گیری")
        self.assertContains(resp, "/backup/")

    def test_empty_path_is_rejected(self):
        from core.backup import create_backup, resolve_user_path

        with self.assertRaises(ValueError):
            resolve_user_path("")
        with self.assertRaises(ValueError):
            create_backup(sections=["catalog"], dest="")

    def test_sectional_backup_and_restore_from_path(self):
        import tempfile
        from pathlib import Path

        from core.backup import create_backup, read_manifest, restore_backup
        from production.models import FittingProduction

        dest = tempfile.mkdtemp(prefix="erp-backup-test-")
        result = create_backup(sections=["production"], dest=dest, created_by="admin")
        zip_path = Path(result.path)
        self.assertTrue(zip_path.is_file())
        self.assertEqual(result.sections, ["production"])

        info = read_manifest(str(zip_path))
        self.assertEqual(info["format"], "erp-backup-v1")

        record = FittingProduction.objects.first()
        self.assertIsNotNone(record)
        pk = record.pk
        record.delete()
        restore_backup(source=str(zip_path), sections=["production"])
        self.assertTrue(FittingProduction.objects.filter(pk=pk).exists())

    def test_manager_can_backup_to_specified_folder(self):
        import tempfile
        from pathlib import Path

        dest = tempfile.mkdtemp(prefix="erp-backup-post-")
        self.client.login(username="admin", password="erp12345")
        resp = self.client.post(
            reverse("backup_center"),
            {"action": "backup", "full": "1", "dest_path": dest},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(list(Path(dest).glob("erp-backup-*.zip"))), 1)

    def test_restore_requires_confirmation(self):
        import tempfile

        from core.backup import create_backup

        dest = tempfile.mkdtemp(prefix="erp-backup-confirm-")
        archive = create_backup(sections=["production"], dest=dest).path
        self.client.login(username="admin", password="erp12345")
        resp = self.client.post(
            reverse("backup_center"),
            {"action": "restore", "source_path": archive, "sections": ["production"]},
            follow=True,
        )
        self.assertContains(resp, "برای بازیابی باید جایگزینی بخش‌ها را تأیید کنید.")

    def test_manager_can_restore_from_specified_path(self):
        import tempfile

        from core.backup import create_backup
        from production.models import FittingProduction

        dest = tempfile.mkdtemp(prefix="erp-backup-restore-")
        archive = create_backup(sections=["production"], dest=dest).path
        record = FittingProduction.objects.first()
        pk = record.pk
        record.delete()
        self.client.login(username="admin", password="erp12345")
        resp = self.client.post(
            reverse("backup_center"),
            {
                "action": "restore",
                "source_path": archive,
                "sections": ["production"],
                "confirm_restore": "1",
            },
            follow=True,
        )
        self.assertContains(resp, "بازیابی از")
        self.assertTrue(FittingProduction.objects.filter(pk=pk).exists())

    def test_full_backup_restore_roundtrip(self):
        import tempfile

        from catalog.models import Machine
        from core.backup import create_backup, restore_backup
        from planning.models import WeeklyPlan
        from production.models import FittingProduction

        dest = tempfile.mkdtemp(prefix="erp-backup-full-")
        archive = create_backup(sections=["full"], dest=dest).path
        counts = {
            "fitting": FittingProduction.objects.count(),
            "plans": WeeklyPlan.objects.count(),
            "machines": Machine.objects.count(),
        }
        restored = restore_backup(source=archive, sections=["full"])
        self.assertIn("users", restored.sections)
        self.assertIn("catalog", restored.sections)
        self.assertIn("planning", restored.sections)
        self.assertIn("production", restored.sections)
        self.assertIn("reports", restored.sections)
        self.assertEqual(FittingProduction.objects.count(), counts["fitting"])
        self.assertEqual(WeeklyPlan.objects.count(), counts["plans"])
        self.assertEqual(Machine.objects.count(), counts["machines"])

    def test_catalog_only_restore_blocked_when_production_exists(self):
        import tempfile

        from core.backup import create_backup, restore_backup

        dest = tempfile.mkdtemp(prefix="erp-backup-catalog-")
        archive = create_backup(sections=["catalog"], dest=dest).path
        with self.assertRaises(ValueError) as ctx:
            restore_backup(source=archive, sections=["catalog"])
        self.assertIn("وابسته", str(ctx.exception))
