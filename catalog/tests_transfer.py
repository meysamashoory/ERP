"""Tests for Excel → system transfer and production history list."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import ExcelTable, ExcelUpload, SystemAlarm
from catalog.transfer import transfer_excel_table
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
        self.assertContains(dash, "کاربری سامانه")
        self.assertNotContains(dash, "ایجاد گزارش")
        self.assertNotContains(dash, "ایجاد فرم")

        history = self.client.get(reverse("production_history"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "سوابق تولید")

    def test_report_and_form_create_on_list_pages(self):
        self.client.login(username="admin", password="erp12345")
        reports = self.client.get(reverse("report_list"))
        self.assertContains(reports, "ایجاد گزارش")
        forms = self.client.get(reverse("print_form_list"))
        self.assertContains(forms, "ایجاد فرم")


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
            "headers": ["شناسه", "کد", "نام", "تولید", "تاریخ"],
            "rows": [
                ["36001010101001", "P-1", "قطعه الف", "120", "1403/01/15"],
                ["36001010101002", "P-2", "قطعه ب", "abc", "1403/02/01"],  # bad int
                ["", "P-3", "بدون شناسه", "10", "1403/03/01"],  # missing required
            ],
            "order": 0,
        }
        data.update(overrides)
        return ExcelTable.objects.create(**data)

    def test_transfer_maps_rows_deletes_table_and_alarms_failures(self):
        self.client.login(username="expert", password="erp12345")
        table = self._make_table()
        table_id = table.pk
        upload_id = table.upload_id

        resp = self.client.post(
            reverse("excel_table_transfer", args=[table_id]),
            data=json.dumps({
                "destination": "production_history",
                "mapping": {
                    "program_uid": 0,
                    "product_code": 1,
                    "product_name": 2,
                    "produced_qty": 3,
                    "plan_date": 4,
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transferred"], 1)
        self.assertEqual(payload["failed"], 2)
        self.assertTrue(payload["table_deleted"])
        self.assertFalse(ExcelTable.objects.filter(pk=table_id).exists())
        # upload had only one table → removed
        self.assertFalse(ExcelUpload.objects.filter(pk=upload_id).exists())

        rec = ProductionHistoryRecord.objects.get(program_uid="36001010101001")
        self.assertEqual(rec.product_code, "P-1")
        self.assertEqual(rec.produced_qty, 120)

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

    def test_transfer_dialog_has_visible_submit(self):
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
        self.assertContains(page, "انتقال و حذف جدول")
        self.assertContains(page, "dialog-transfer")
        self.assertContains(page, "dialog-transfer-footer")

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
            rows=[["36001010101999", "X1", "کهنه", "5", "1402/01/01"]],
        )
        transfer_excel_table(
            table=table,
            destination_id="production_history",
            mapping={
                "program_uid": 0,
                "product_code": 1,
                "product_name": 2,
                "produced_qty": 3,
                "plan_date": 4,
            },
            user=self.expert,
        )
        self.assertEqual(ProductionHistoryRecord.objects.filter(program_uid="36001010101999").count(), 1)

        upload2 = ExcelUpload.objects.create(title="دوباره", uploaded_by=self.expert)
        table2 = ExcelTable.objects.create(
            upload=upload2,
            name="آپدیت",
            headers=["شناسه", "کد", "نام", "تولید", "تاریخ"],
            rows=[["36001010101999", "X1", "تازه‌شده", "50", "1402/01/01"]],
        )
        transfer_excel_table(
            table=table2,
            destination_id="production_history",
            mapping={
                "program_uid": 0,
                "product_code": 1,
                "product_name": 2,
                "produced_qty": 3,
                "plan_date": 4,
            },
            user=self.expert,
        )
        rec = ProductionHistoryRecord.objects.get(program_uid="36001010101999")
        self.assertEqual(rec.product_name, "تازه‌شده")
        self.assertEqual(rec.produced_qty, 50)
