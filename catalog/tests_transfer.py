"""Tests for Excel → system transfer and production history list."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import ExcelTable, ExcelUpload, SystemAlarm
from catalog.transfer import transfer_excel_table
from core.natsort import natural_sorted
from production.models import ProductionHistoryRecord

User = get_user_model()


class MenuAndHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")

    def test_sidebar_labels_and_history_route(self):
        self.client.login(username="admin", password="erp12345")
        dash = self.client.get(reverse("dashboard"))
        self.assertEqual(dash.status_code, 200)
        self.assertContains(dash, "برنامه‌های تولید")
        self.assertContains(dash, "ثبت و کنترل تولید")
        self.assertContains(dash, "سوابق تولید")
        self.assertContains(dash, "گزارشات")
        self.assertContains(dash, "بارگذاری")
        self.assertContains(dash, "دیتای محصولات")
        self.assertContains(dash, reverse("product_data"))
        self.assertContains(dash, "داده‌های سیستم")
        self.assertContains(dash, reverse("system_data"))
        self.assertContains(dash, "کاربری سامانه")
        self.assertNotContains(dash, "ایجاد گزارش")
        self.assertNotContains(dash, "ایجاد فرم")

        history = self.client.get(reverse("production_history"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "سوابق تولید")

        system = self.client.get(reverse("system_data"))
        self.assertEqual(system.status_code, 200)
        self.assertContains(system, "واحدهای تولیدی")
        self.assertContains(system, "آلارم‌های سیستم")

        products = self.client.get(reverse("product_data"))
        self.assertEqual(products.status_code, 200)
        self.assertContains(products, "اطلاعات محصول")
        self.assertContains(products, "ساختار BOM")
        self.assertContains(products, "مواد مصرفی")
        self.assertContains(products, "بسته‌بندی")
        self.assertContains(products, "مشخصات فنی")

        history = self.client.get(reverse("production_history"))
        self.assertContains(history, "history-filter-col")
        self.assertContains(history, "history-filter-q")

    def test_report_and_form_create_on_list_pages(self):
        self.client.login(username="admin", password="erp12345")
        reports = self.client.get(reverse("report_list"))
        self.assertContains(reports, "ایجاد گزارش")
        forms = self.client.get(reverse("print_form_list"))
        self.assertContains(forms, "ایجاد فرم")

    def test_natural_sort_helper(self):
        self.assertEqual(
            natural_sorted(["1", "10", "2", "20", "9"]),
            ["1", "2", "9", "10", "20"],
        )


class ExcelTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.expert = User.objects.get(username="expert")
        cls.admin = User.objects.get(username="admin")

    def _make_table(self, **overrides):
        upload = ExcelUpload.objects.create(title="آرشیو تست", uploaded_by=self.expert)
        data = {
            "upload": upload,
            "name": "سوابق قدیمی",
            "sheet_name": "Sheet1",
            "headers": ["شناسه", "شماره برنامه", "کد", "نام", "تولید", "تاریخ"],
            "rows": [
                ["36001010101001", "BP-9001", "P-1", "قطعه الف", "120", "1403/01/15"],
                ["36001010101002", "BP-9002", "P-2", "قطعه ب", "abc", "1403/02/01"],  # bad int
                ["", "BP-9003", "P-3", "بدون شناسه", "10", "1403/03/01"],  # missing required
            ],
            "order": 0,
        }
        data.update(overrides)
        return ExcelTable.objects.create(**data)

    def _mapping(self):
        return {
            "program_uid": 0,
            "plan_number": 1,
            "product_name": 3,
            "produced_qty": 4,
            "plan_date": 5,
        }

    def test_transfer_keeps_table_and_alarms_failures(self):
        self.client.login(username="expert", password="erp12345")
        table = self._make_table()
        table_id = table.pk

        resp = self.client.post(
            reverse("excel_table_transfer", args=[table_id]),
            data=json.dumps({
                "destination": "production_history",
                "level": "history_list",
                "mapping": self._mapping(),
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        # 1 ok row, 1 invalid integer (failed), 1 empty uid (skipped — not failed)
        self.assertEqual(payload["transferred"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(payload["skipped"], 1)
        self.assertFalse(payload["table_deleted"])
        self.assertIn("ناقص", payload["message"])
        self.assertNotIn("با موفقیت انجام شد", payload["message"])
        self.assertTrue(ExcelTable.objects.filter(pk=table_id).exists())

        rec = ProductionHistoryRecord.objects.get(program_uid="36001010101001")
        self.assertEqual(rec.product_name, "قطعه الف")
        self.assertEqual(rec.produced_qty, 120)
        self.assertEqual(rec.plan_number, "BP-9001")

        alarms = SystemAlarm.objects.filter(kind=SystemAlarm.Kind.DATA_TRANSFER)
        self.assertTrue(alarms.exists())
        alarm_text = " ".join(alarms.values_list("message", flat=True))
        self.assertIn("مقدار تولید واقعی", alarm_text)
        self.assertIn("abc", alarm_text)
        self.assertIn("عدد تولید یافت نشد", alarm_text)

        history = self.client.get(reverse("production_history"))
        self.assertContains(history, "قطعه الف")
        self.assertContains(history, "ضایعات تولید")
        self.assertContains(history, "BP-9001")
        # شناسه تعویض فقط در سطح دوم (جزئیات روزانه)
        self.assertNotContains(history, 'data-col="change_uid"')
        detail = self.client.get(
            reverse("production_history_archive_detail", args=[rec.pk])
        )
        self.assertContains(detail, "شناسه تعویض")
        self.assertContains(detail, "36001010101001")

    def test_hub_hides_finished_programs(self):
        from production.models import ProductionProgram

        self.client.login(username="admin", password="erp12345")
        finished = ProductionProgram.objects.filter(
            status=ProductionProgram.Status.FINISHED
        ).first()
        if finished is None:
            prog = ProductionProgram.objects.first()
            self.assertIsNotNone(prog)
            prog.status = ProductionProgram.Status.FINISHED
            prog.save(update_fields=["status"])
            finished = prog

        hub = self.client.get(reverse("program_list"))
        self.assertEqual(hub.status_code, 200)
        self.assertNotContains(hub, finished.resolved_uid)

        history = self.client.get(reverse("production_history"))
        # سطح اول شناسه را نشان نمی‌دهد؛ در جزئیات هست
        self.assertNotContains(history, 'data-col="change_uid"')
        detail = self.client.get(reverse("production_history_detail", args=[finished.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, finished.resolved_uid)
        self.assertContains(detail, "شناسه تعویض")
        self.assertContains(detail, "اسناد ثبت‌شده روزانه")
        self.assertContains(detail, "انحراف آمار تولید")

    def test_transfer_dialog_has_level_and_submit(self):
        self.client.login(username="expert", password="erp12345")
        upload = ExcelUpload.objects.create(title="دیالوگ", uploaded_by=self.expert)
        ExcelTable.objects.create(
            upload=upload,
            name="t1",
            headers=["a", "b"],
            rows=[["1", "2"]],
        )
        page = self.client.get(reverse("excel_detail", args=[upload.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="transfer-submit"')
        self.assertContains(page, ">انتقال<")
        self.assertContains(page, "transfer-level")
        self.assertContains(page, "انتخاب سطح")
        self.assertContains(page, "dialog-transfer-footer")
        self.assertNotContains(page, "انتقال و حذف جدول")

    def test_transfer_requires_destination_mapping(self):
        self.client.login(username="expert", password="erp12345")
        table = self._make_table()
        bad = self.client.post(
            reverse("excel_table_transfer", args=[table.pk]),
            data=json.dumps({"destination": "", "mapping": {}}),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertTrue(ExcelTable.objects.filter(pk=table.pk).exists())

    def test_direct_transfer_helper_updates_existing_archive(self):
        table = self._make_table(
            rows=[["36001010101999", "BP-991", "X1", "کهنه", "5", "1402/01/01"]],
        )
        transfer_excel_table(
            table=table,
            destination_id="production_history",
            level_id="history_list",
            mapping=self._mapping(),
            user=self.expert,
        )
        self.assertEqual(ProductionHistoryRecord.objects.filter(program_uid="36001010101999").count(), 1)
        self.assertTrue(ExcelTable.objects.filter(pk=table.pk).exists())

        upload2 = ExcelUpload.objects.create(title="دوباره", uploaded_by=self.expert)
        table2 = ExcelTable.objects.create(
            upload=upload2,
            name="آپدیت",
            headers=["شناسه", "شماره برنامه", "کد", "نام", "تولید", "تاریخ"],
            rows=[["36001010101999", "BP-991", "X1", "تازه‌شده", "50", "1402/01/01"]],
        )
        transfer_excel_table(
            table=table2,
            destination_id="production_history",
            level_id="history_list",
            mapping=self._mapping(),
            user=self.expert,
        )
        rec = ProductionHistoryRecord.objects.get(program_uid="36001010101999")
        self.assertEqual(rec.product_name, "تازه‌شده")
        self.assertEqual(rec.produced_qty, 50)

    def test_save_returns_redirect_to_list(self):
        self.client.login(username="expert", password="erp12345")
        table = self._make_table()
        resp = self.client.post(
            reverse("excel_table_save", args=[table.pk]),
            data=json.dumps({"name": "نام جدید", "headers": ["a"], "rows": [["1"]]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["redirect_url"], reverse("excel_list"))

    def test_history_status_inference_and_conflict_alarm(self):
        from datetime import date, timedelta

        from catalog.models import Machine, Product
        from planning.models import WeeklyPlan
        from production.models import ProductionProgram
        from production.sync import (
            check_history_machine_conflicts,
            infer_history_status,
            sync_history_record_to_planning,
        )

        self.assertEqual(infer_history_status(actual_start=None, actual_end=None), "awaiting")
        self.assertEqual(
            infer_history_status(actual_start=date(2024, 1, 1), actual_end=None),
            "running",
        )
        self.assertEqual(
            infer_history_status(actual_start=date(2024, 1, 1), actual_end=date(2024, 2, 1)),
            "finished",
        )

        product = Product.objects.first()
        machine = Machine.objects.select_related("unit").first()
        self.assertIsNotNone(product)
        self.assertIsNotNone(machine)

        # Running history + live RUNNING on same machine → conflict alarm
        live = (
            ProductionProgram.objects.filter(status=ProductionProgram.Status.RUNNING)
            .select_related("item__machine")
            .first()
        )
        if live is None:
            live = ProductionProgram.objects.select_related("item__machine").first()
            live.status = ProductionProgram.Status.RUNNING
            live.start_date = date.today() - timedelta(days=1)
            live.save()
        mid = live.item.machine
        rec = ProductionHistoryRecord.objects.create(
            program_uid="SYNC-CONFLICT-001",
            plan_number="BP-SYNC-1",
            product_code=product.code,
            product_name=product.name,
            unit_number=mid.unit.number,
            machine_number=mid.number,
            actual_start_date=date.today(),
            planned_qty=10,
        )
        out = sync_history_record_to_planning(rec, user=self.admin)
        self.assertTrue(out["ok"] or out.get("error") == "live")
        created = check_history_machine_conflicts()
        self.assertGreaterEqual(created, 0)
        self.assertTrue(
            SystemAlarm.objects.filter(kind=SystemAlarm.Kind.PRODUCTION_CONFLICT).exists()
            or WeeklyPlan.objects.filter(program_number="BP-SYNC-1").exists()
        )


    def test_history_chunk_sync_creates_plan_even_when_uid_already_known(self):
        """Excel reverse-aggregation: known UID + new plan_number must still create a plan."""
        from datetime import date

        from catalog.models import Machine, Product
        from planning.models import WeeklyPlan
        from production.sync import (
            sync_history_chunk_to_planning,
            sync_history_record_to_planning,
        )

        product = Product.objects.first()
        machine = Machine.objects.select_related("unit").first()
        self.assertIsNotNone(product)
        self.assertIsNotNone(machine)

        # First history row creates plan BP-KNOWN-UID and registers the UID in planning
        seed = ProductionHistoryRecord.objects.create(
            program_uid="UID-CHUNK-REUSE-1",
            plan_number="BP-KNOWN-UID",
            product_code=product.code,
            product_name=product.name,
            unit_number=machine.unit.number,
            machine_number=machine.number,
            plan_date=date(1403, 1, 10),
            planned_qty=5,
        )
        seed_out = sync_history_record_to_planning(seed, user=self.admin)
        self.assertTrue(seed_out["ok"], seed_out)
        self.assertTrue(WeeklyPlan.objects.filter(program_number="BP-KNOWN-UID").exists())

        # Second Excel row reuses the same UID under a *new* plan number
        ProductionHistoryRecord.objects.create(
            program_uid="UID-CHUNK-REUSE-1",
            plan_number="BP-NEW-FROM-EXCEL",
            product_code=product.code,
            product_name=product.name,
            unit_number=machine.unit.number,
            machine_number=machine.number,
            plan_date=date(1403, 2, 1),
            planned_qty=8,
        )
        self.assertFalse(
            WeeklyPlan.objects.filter(program_number="BP-NEW-FROM-EXCEL").exists()
        )

        # Without the plan_number-aware skip fix, chunk sync would skip this UID
        stats = sync_history_chunk_to_planning(user=self.admin, offset=0, limit=500)
        self.assertTrue(
            WeeklyPlan.objects.filter(program_number="BP-NEW-FROM-EXCEL").exists(),
            msg=f"chunk stats={stats}",
        )

    def test_history_to_planning_by_plan_number_uses_jalali_dates(self):
        """Archive row → WeeklyPlan grouped by plan_number with شمسی dates."""
        import jdatetime
        from datetime import date

        from catalog.models import Machine, Product
        from planning.models import WeeklyPlan
        from production.sync import sync_history_record_to_planning

        product = Product.objects.first()
        machine = Machine.objects.select_related("unit").first()
        rec = ProductionHistoryRecord.objects.create(
            program_uid="36006666001001",
            plan_number="BP-JALALI-1",
            plan_date=date(1405, 6, 1),
            plan_start_date=date(1405, 6, 2),
            actual_start_date=date(1405, 6, 3),
            product_code=product.code,
            product_name=product.name,
            unit_number=machine.unit.number,
            machine_number=machine.number,
            planned_qty=50,
            planned_cycle=28,
            active_cavities=4,
        )
        # Also accept accidental Gregorian storage and repair it
        rec2 = ProductionHistoryRecord.objects.create(
            program_uid="36006666001002",
            plan_number="BP-JALALI-1",
            plan_date=date(2026, 8, 23),  # میلادی equivalent of 1405/06/01
            plan_start_date=date(2026, 8, 24),
            product_code=product.code,
            product_name=product.name,
            unit_number=machine.unit.number,
            machine_number=machine.number,
            planned_qty=60,
            planned_cycle=30,
            active_cavities=2,
        )
        out1 = sync_history_record_to_planning(rec, user=self.admin)
        out2 = sync_history_record_to_planning(rec2, user=self.admin)
        self.assertTrue(out1["ok"], out1)
        self.assertTrue(out2["ok"], out2)
        self.assertEqual(out1["plan_id"], out2["plan_id"])

        plan = WeeklyPlan.objects.get(program_number="BP-JALALI-1")
        self.assertEqual(plan.items.count(), 2)
        self.assertIsInstance(plan.date, jdatetime.date)
        self.assertEqual((plan.date.year, plan.date.month, plan.date.day), (1405, 6, 1))

        rec2.refresh_from_db()
        self.assertEqual(rec2.plan_date, date(1405, 6, 1))

        # Transfer of Gregorian ISO string stores شمسی
        from catalog.transfer import transfer_excel_table

        upload = ExcelUpload.objects.create(title="dates", uploaded_by=self.expert)
        table = ExcelTable.objects.create(
            upload=upload,
            name="سوابق",
            headers=["شناسه", "برنامه", "تاریخ", "کد", "نام", "واحد", "دستگاه"],
            rows=[
                [
                    "36006666001003",
                    "BP-JALALI-2",
                    "2026-08-23",
                    product.code,
                    product.name,
                    str(machine.unit.number),
                    machine.number,
                ]
            ],
        )
        result = transfer_excel_table(
            table=table,
            destination_id="production_history",
            level_id="history_list",
            mapping={
                "program_uid": 0,
                "plan_number": 1,
                "plan_date": 2,
                "product_name": 4,
                "unit_number": 5,
                "machine_number": 6,
            },
            user=self.expert,
        )
        self.assertEqual(result.failed, 0)
        stored = ProductionHistoryRecord.objects.get(program_uid="36006666001003")
        self.assertEqual(stored.plan_date, date(1405, 6, 1))
        # کد کالا از سطح روزانه می‌آید
        from catalog.transfer import transfer_excel_table as _xfer

        daily = ExcelTable.objects.create(
            upload=upload,
            name="روزانه",
            headers=["شناسه", "کد", "وضعیت", "تاریخ", "تولید"],
            rows=[["36006666001003", product.code, "در حال تولید", "1405/06/03", "40"]],
        )
        daily_result = _xfer(
            table=daily,
            destination_id="production_history",
            level_id="history_daily",
            mapping={
                "program_uid": 0,
                "product_code": 1,
                "status": 2,
                "work_date": 3,
                "produced_qty": 4,
            },
            user=self.expert,
        )
        self.assertEqual(daily_result.failed, 0)
        stored.refresh_from_db()
        self.assertEqual(stored.product_code, product.code)
        self.assertIn("در حال تولید", stored.status)
        plan2 = WeeklyPlan.objects.filter(program_number="BP-JALALI-2").first()
        self.assertIsNotNone(plan2)
        # Plan.date is unique — may bump one day if 1405/06/01 already taken by BP-JALALI-1
        self.assertEqual(plan2.date.year, 1405)
        self.assertEqual(plan2.date.month, 6)
        self.assertGreaterEqual(plan2.date.day, 1)
        # History archive itself keeps the exact شمسی value from Excel
        self.assertEqual(stored.plan_date, date(1405, 6, 1))
        item = plan2.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.product_id, product.pk)

class ProductDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.expert = User.objects.get(username="expert")
        cls.admin = User.objects.get(username="admin")

    def test_product_info_transfer_and_bom(self):
        from catalog.models import Product, ProductBomLine, ProductConsumable
        from catalog.transfer import transfer_excel_table

        upload = ExcelUpload.objects.create(title="محصولات", uploaded_by=self.expert)
        info_table = ExcelTable.objects.create(
            upload=upload,
            name="اطلاعات",
            headers=["کد", "نام", "گروه", "زیرگروه", "وزن"],
            rows=[["PD-100", "قطعه تست", "اتصالات", "تست", "12.5"]],
        )
        result = transfer_excel_table(
            table=info_table,
            destination_id="product_data",
            level_id="product_info",
            mapping={
                "code": 0,
                "name": 1,
                "group_name": 2,
                "subgroup_name": 3,
                "unit_weight_grams": 4,
            },
            user=self.expert,
        )
        self.assertEqual(result.transferred, 1)
        self.assertEqual(result.failed, 0)
        product = Product.objects.get(code="PD-100")
        self.assertEqual(product.name, "قطعه تست")
        self.assertEqual(float(product.unit_weight_grams), 12.5)

        bom_table = ExcelTable.objects.create(
            upload=upload,
            name="BOM",
            headers=["والد", "کد جزء", "نام جزء", "مقدار"],
            rows=[["PD-100", "C-1", "پیچ", "4"]],
        )
        bom_result = transfer_excel_table(
            table=bom_table,
            destination_id="product_data",
            level_id="product_bom",
            mapping={
                "parent_code": 0,
                "component_code": 1,
                "component_name": 2,
                "quantity": 3,
            },
            user=self.expert,
        )
        self.assertEqual(bom_result.transferred, 1)
        self.assertEqual(ProductBomLine.objects.filter(parent=product).count(), 1)

        cons_table = ExcelTable.objects.create(
            upload=upload,
            name="مواد",
            headers=["کد محصول", "کد ماده", "نام ماده", "مقدار"],
            rows=[["PD-100", "M-PVC", "گرانول PVC", "85.2"]],
        )
        cons_result = transfer_excel_table(
            table=cons_table,
            destination_id="product_data",
            level_id="product_consumables",
            mapping={
                "product_code": 0,
                "material_code": 1,
                "material_name": 2,
                "quantity_per_unit": 3,
            },
            user=self.expert,
        )
        self.assertEqual(cons_result.transferred, 1)
        self.assertEqual(ProductConsumable.objects.filter(product=product).count(), 1)

        self.client.login(username="expert", password="erp12345")
        page = self.client.get(reverse("product_data") + "?tab=bom")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "PD-100")
        self.assertContains(page, "پیچ")

        save = self.client.post(
            reverse("product_data_save"),
            data=json.dumps({
                "tab": "info",
                "rows": [{
                    "id": product.pk,
                    "code": "PD-100",
                    "name": "قطعه تست ویرایش",
                    "group_name": "اتصالات",
                    "subgroup_name": "تست",
                    "counting_unit": "count",
                    "unit_weight_grams": "13",
                    "stock_finished": 10,
                    "needs_assembly": False,
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(save.status_code, 200)
        self.assertTrue(save.json()["ok"])
        product.refresh_from_db()
        self.assertEqual(product.name, "قطعه تست ویرایش")

    def test_empty_optional_fields_do_not_fail_transfer(self):
        from catalog.transfer import transfer_excel_table, transfer_result_message
        from catalog.models import Product

        upload = ExcelUpload.objects.create(title="خالی‌ها", uploaded_by=self.expert)
        table = ExcelTable.objects.create(
            upload=upload,
            name="اطلاعات",
            headers=["کد", "نام", "وزن", "موجودی"],
            rows=[
                ["PD-EMPTY-1", "فقط کد و نام", "", ""],  # empty weight/stock OK
                ["PD-EMPTY-2", "", "not-a-number", ""],  # invalid weight → fail
            ],
        )
        result = transfer_excel_table(
            table=table,
            destination_id="product_data",
            level_id="product_info",
            mapping={"code": 0, "name": 1, "unit_weight_grams": 2, "stock_finished": 3},
            user=self.expert,
        )
        self.assertEqual(result.transferred, 1)
        self.assertEqual(result.failed, 1)
        self.assertTrue(Product.objects.filter(code="PD-EMPTY-1").exists())
        msg = transfer_result_message(result)
        self.assertIn("ناقص", msg)
        self.assertTrue(any("وزن هر واحد" in a for a in result.alarms))

    def test_jalali_and_excel_serial_dates(self):
        """Excel serial / میلادی / شمسی all store as Jalali-encoded date(1405,6,1)."""
        from catalog.transfer import _parse_date
        from datetime import date

        expected = date(1405, 6, 1)  # شمسی encoded for history DateField

        for raw in ("46257", "46257.0", "1405/06/01", "1405-06-01", "۱۴۰۵/۰۶/۰۱"):
            parsed, err = _parse_date(raw, "تاریخ آزمایشی")
            self.assertIsNone(err, msg=f"raw={raw!r} err={err}")
            self.assertEqual(parsed, expected, msg=f"raw={raw!r}")

        # Must NOT treat 1405 as Gregorian year 1405, and must NOT store میلادی year
        parsed, err = _parse_date("1405/06/01", "تاریخ")
        self.assertEqual(parsed.year, 1405)

        # Datetime / ISO Gregorian from openpyxl → شمسی storage
        parsed, err = _parse_date("2026-08-23 00:00:00", "تاریخ")
        self.assertIsNone(err)
        self.assertEqual(parsed, expected)

        from catalog.excel_io import _cell_str

        self.assertEqual(
            _cell_str(46257, number_format="[$-fa-IR,96]yyyy/mm/dd"),
            "1405/06/01",
        )
        self.assertEqual(_cell_str(date(2026, 8, 23)), "1405/06/01")

    def test_qty_phrase_extracts_number_and_merges_type_into_name(self):
        from catalog.qty_parse import (
            apply_production_type_to_name,
            extract_qty_and_production_type,
        )
        from catalog.transfer import transfer_excel_table
        from production.models import ProductionHistoryRecord

        cases = [
            ("1000", 1000, ""),
            ("1000 ضرب", 1000, ""),
            ("1000 ضرب جنرال", 1000, "جنرال"),
            ("1000 ضرب یا حدود 10000 ضرب پروتکت", 1000, "پروتکت"),
            ("۱۰۰۰ ضرب سرمه ای", 1000, "سرمه ای"),
        ]
        for raw, qty, ptype in cases:
            got_qty, got_type, err = extract_qty_and_production_type(raw)
            self.assertIsNone(err, msg=raw)
            self.assertEqual(got_qty, qty, msg=raw)
            self.assertEqual(got_type, ptype, msg=raw)

        self.assertEqual(
            apply_production_type_to_name("زانو 45-110", "جنرال"),
            "زانو جنرال 45-110",
        )

        upload = ExcelUpload.objects.create(title="qty", uploaded_by=self.expert)
        table = ExcelTable.objects.create(
            upload=upload,
            name="سوابق",
            headers=["شناسه", "برنامه", "نام", "مقدار"],
            rows=[["36001999001001", "BP-Q1", "زانو 45-110", "1000 ضرب جنرال"]],
        )
        result = transfer_excel_table(
            table=table,
            destination_id="production_history",
            level_id="history_list",
            mapping={
                "program_uid": 0,
                "plan_number": 1,
                "product_name": 2,
                "produced_qty": 3,
            },
            user=self.expert,
        )
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.transferred, 1)
        rec = ProductionHistoryRecord.objects.get(program_uid="36001999001001")
        self.assertEqual(rec.produced_qty, 1000)
        self.assertEqual(rec.product_name, "زانو جنرال 45-110")

    def test_update_mode_does_not_create_new_history_rows(self):
        from catalog.transfer import MODE_UPDATE, transfer_excel_table
        from production.models import ProductionHistoryRecord

        ProductionHistoryRecord.objects.create(
            program_uid="36001888001001",
            plan_number="BP-U1",
            product_name="قدیمی",
            produced_qty=10,
        )
        before = ProductionHistoryRecord.objects.count()
        upload = ExcelUpload.objects.create(title="upd", uploaded_by=self.expert)
        table = ExcelTable.objects.create(
            upload=upload,
            name="سوابق",
            headers=["شناسه", "برنامه", "نام", "مقدار"],
            rows=[
                ["36001888001001", "BP-U1", "جدید", "55"],
                ["36001888001999", "BP-NEW", "ایجاد نشود", "1"],
            ],
        )
        result = transfer_excel_table(
            table=table,
            destination_id="production_history",
            level_id="history_list",
            mapping={
                "program_uid": 0,
                "plan_number": 1,
                "product_name": 2,
                "produced_qty": 3,
            },
            user=self.expert,
            mode=MODE_UPDATE,
        )
        self.assertEqual(result.mode, MODE_UPDATE)
        self.assertEqual(result.transferred, 1)
        self.assertGreaterEqual(result.skipped, 1)
        self.assertEqual(ProductionHistoryRecord.objects.count(), before)
        rec = ProductionHistoryRecord.objects.get(program_uid="36001888001001")
        self.assertEqual(rec.product_name, "جدید")
        self.assertEqual(rec.produced_qty, 55)
        self.assertFalse(
            ProductionHistoryRecord.objects.filter(program_uid="36001888001999").exists()
        )

    def test_update_mode_product_skips_missing_codes(self):
        from catalog.models import Product
        from catalog.transfer import MODE_UPDATE, transfer_excel_table

        product = Product.objects.filter(is_active=True).first()
        self.assertIsNotNone(product)
        old_name = product.name
        upload = ExcelUpload.objects.create(title="pupd", uploaded_by=self.expert)
        table = ExcelTable.objects.create(
            upload=upload,
            name="محصولات",
            headers=["کد", "نام"],
            rows=[
                [product.code, "نام اصلاح‌شده تست"],
                ["NO-SUCH-CODE-XYZ", "نباید ساخته شود"],
            ],
        )
        before = Product.objects.count()
        result = transfer_excel_table(
            table=table,
            destination_id="product_data",
            level_id="product_info",
            mapping={"code": 0, "name": 1},
            user=self.expert,
            mode=MODE_UPDATE,
        )
        self.assertEqual(result.transferred, 1)
        self.assertGreaterEqual(result.skipped, 1)
        self.assertEqual(Product.objects.count(), before)
        product.refresh_from_db()
        self.assertEqual(product.name, "نام اصلاح‌شده تست")
        self.assertNotEqual(product.name, old_name)
        self.assertFalse(Product.objects.filter(code="NO-SUCH-CODE-XYZ").exists())

    def test_history_page_stays_fast_with_many_archives(self):
        import time
        from unittest.mock import patch

        from production.models import ProductionHistoryRecord

        ProductionHistoryRecord.objects.bulk_create(
            [
                ProductionHistoryRecord(
                    program_uid=f"36001777{i:06d}",
                    plan_number=f"BP-{i}",
                    product_code=f"C-{i}",
                    product_name=f"قطعه {i}",
                    produced_qty=i,
                )
                for i in range(400)
            ]
        )
        self.client.login(username="admin", password="erp12345")
        with patch("production.sync.sync_all_history_to_planning") as sync_mock:
            with patch("production.sync.check_history_machine_conflicts") as conflict_mock:
                t0 = time.perf_counter()
                resp = self.client.get(reverse("production_history"))
                elapsed = time.perf_counter() - t0
        self.assertEqual(resp.status_code, 200)
        sync_mock.assert_not_called()
        conflict_mock.assert_not_called()
        self.assertLess(elapsed, 5.0, msg=f"history page took {elapsed:.2f}s")
        plans = self.client.get(reverse("plan_list"))
        self.assertEqual(plans.status_code, 200)

    def test_excel_detail_shows_update_button(self):
        self.client.login(username="admin", password="erp12345")
        upload = ExcelUpload.objects.create(title="ui", uploaded_by=self.admin)
        ExcelTable.objects.create(
            upload=upload, name="t1", headers=["a"], rows=[["1"]]
        )
        resp = self.client.get(reverse("excel_detail", args=[upload.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "بروزرسانی")
        self.assertContains(resp, 'data-transfer-mode="update"')
        self.assertContains(resp, 'data-transfer-mode="transfer"')

    def test_running_history_appears_in_production_hub_with_quantities(self):
        from datetime import date

        from catalog.models import Machine, Product
        from production.models import ProductionDayEntry, ProductionProgram
        from production.sync import ensure_running_history_in_production

        product = Product.objects.first()
        machine = Machine.objects.select_related("unit").first()
        rec = ProductionHistoryRecord.objects.create(
            program_uid="36008888001001",
            plan_number="BP-RUN-HUB",
            plan_date=date(1405, 6, 10),
            actual_start_date=date(1405, 6, 11),
            product_code=product.code,
            product_name=product.name,
            unit_number=machine.unit.number,
            machine_number=machine.number,
            planned_qty=200,
            produced_qty=55,
            status="در حال تولید",
            extra={
                "day_entries": [
                    {
                        "date": "1405-06-11",
                        "produced": 55,
                        "scrap": 2,
                        "program_uid": "36008888001001",
                        "product_code": product.code,
                        "status": "در حال تولید",
                    }
                ]
            },
        )
        stats = ensure_running_history_in_production(user=self.admin)
        self.assertGreaterEqual(stats["ok"] + stats["refreshed"], 1)
        prog = ProductionProgram.objects.filter(item__lines__uid=rec.program_uid).first()
        self.assertIsNotNone(prog)
        self.assertEqual(prog.status, ProductionProgram.Status.RUNNING)
        self.assertTrue(
            ProductionDayEntry.objects.filter(program=prog, produced_quantity=55).exists()
        )

        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("program_list"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "36008888001001")
        self.assertContains(hub, product.code)

        detail = self.client.get(reverse("production_history_archive_detail", args=[rec.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "شناسه تعویض")
        self.assertContains(detail, "کد کالا")
        self.assertContains(detail, "وضعیت")
        self.assertContains(detail, product.code)
        self.assertContains(detail, "36008888001001")

        listing = self.client.get(reverse("production_history"))
        self.assertEqual(listing.status_code, 200)
        # سطح اول دیگر ستون شناسه تعویض / کد کالا / وضعیت ندارد (همه در سطح روزانه)
        self.assertNotContains(listing, 'data-col="change_uid"')
        self.assertNotContains(listing, 'data-col="product_code"')
        self.assertNotContains(listing, 'data-col="status"')
        self.assertContains(listing, 'data-col="plan_number"')
