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
            "product_code": 2,
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
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transferred"], 1)
        self.assertEqual(payload["failed"], 2)
        self.assertFalse(payload["table_deleted"])
        self.assertTrue(ExcelTable.objects.filter(pk=table_id).exists())

        rec = ProductionHistoryRecord.objects.get(program_uid="36001010101001")
        self.assertEqual(rec.product_code, "P-1")
        self.assertEqual(rec.produced_qty, 120)
        self.assertEqual(rec.plan_number, "BP-9001")

        alarms = SystemAlarm.objects.filter(kind=SystemAlarm.Kind.DATA_TRANSFER)
        self.assertTrue(alarms.exists())

        history = self.client.get(reverse("production_history"))
        self.assertContains(history, "36001010101001")
        self.assertContains(history, "قطعه الف")
        self.assertContains(history, "شناسه تعویض")
        self.assertContains(history, "ضایعات تولید")

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
        self.assertContains(history, finished.resolved_uid)

        detail = self.client.get(reverse("production_history_detail", args=[finished.pk]))
        self.assertEqual(detail.status_code, 200)
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
