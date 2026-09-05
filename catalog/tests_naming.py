"""Tests for system naming-key registry and column management UI."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import SystemNamingKey
from catalog.naming_registry import resolve_label, sync_naming_registry
from catalog.transfer import list_destinations_for_ui

User = get_user_model()


class SystemNamingRegistryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")
        cls.expert = User.objects.get(username="expert")

    def test_sync_creates_keys_with_addresses(self):
        stats = sync_naming_registry()
        self.assertGreater(stats["created"], 20)
        self.assertTrue(SystemNamingKey.objects.filter(key="system.section.molds").exists())
        col = SystemNamingKey.objects.get(key="ui.table.planning.plan_list.col.program_number")
        self.assertIn("plan_list.html", col.address)
        self.assertIn("data-col=program_number", col.address)
        self.assertIn("صفحات کاربری", col.address)
        self.assertEqual(col.category, SystemNamingKey.Category.COLUMN)

    def test_admin_harvest_skips_technical_id_fields(self):
        from catalog.naming_registry import harvest_specs

        specs = harvest_specs()
        admin_field_keys = [s["key"] for s in specs if s["key"].startswith("admin.field.")]
        self.assertTrue(admin_field_keys)
        self.assertFalse(any(k.endswith(".id") for k in admin_field_keys))
        created_by = [
            s for s in specs if s["key"].endswith(".created_by") and s["key"].startswith("admin.")
        ]
        if created_by:
            self.assertIn("پنل مدیریت", created_by[0]["address"])

    def test_resync_deactivates_obsolete_admin_fields(self):
        sync_naming_registry()
        obsolete = SystemNamingKey.objects.create(
            key="admin.field.catalog.unit.id",
            label="ID",
            default_label="ID",
            address="old technical field",
            category=SystemNamingKey.Category.COLUMN,
            table_key="admin.catalog.unit",
            column_key="id",
            is_custom=False,
            is_active=True,
        )
        stats = sync_naming_registry(refresh_defaults=True)
        obsolete.refresh_from_db()
        self.assertFalse(obsolete.is_active)
        self.assertGreaterEqual(stats.get("deactivated", 0), 1)

    def test_naming_keys_default_source_hides_admin(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("system_naming_keys"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "صفحات کاربری")
        self.assertContains(page, "اعمال فیلتر")
        self.assertContains(page, "به هیچ بخشی وصل نیست")
        self.assertContains(page, "بخش مرتبط")
        self.assertNotContains(page, "naming-source-legend")
        self.assertNotContains(page, "بدون ربط")
        self.assertNotContains(page, "admin.field.")
        admin_page = self.client.get(reverse("system_naming_keys"), {"source": "admin"})
        self.assertEqual(admin_page.status_code, 200)
        self.assertContains(admin_page, "admin.field.")
        self.assertContains(admin_page, "list_display=")

    def test_transfer_dialog_titles_are_harvested(self):
        sync_naming_registry()
        self.assertTrue(
            SystemNamingKey.objects.filter(
                key="transfer.ui.dialog.title_transfer"
            ).exists()
        )
        self.assertTrue(
            SystemNamingKey.objects.filter(key="transfer.dest.production_history").exists()
        )
        row = SystemNamingKey.objects.get(key="transfer.ui.dialog.title_transfer")
        self.assertIn("دیالوگ انتقال", row.address)
        self.assertEqual(row.section_key, "transfer_dialog_labels")

    def test_hide_transfer_destination_removes_from_dialog(self):
        sync_naming_registry()
        dest = SystemNamingKey.objects.get(key="transfer.dest.production_history")
        dest.is_active = False
        dest.save(update_fields=["is_active"])
        ids = [d["id"] for d in list_destinations_for_ui()]
        self.assertNotIn("production_history", ids)
        self.assertIn("product_data", ids)

    def test_hide_transfer_field_removes_from_dialog(self):
        sync_naming_registry()
        field = SystemNamingKey.objects.get(
            key="transfer.field.production_history.history_list.scrap_qty"
        )
        field.is_active = False
        field.save(update_fields=["is_active"])
        hist = next(
            d for d in list_destinations_for_ui() if d["id"] == "production_history"
        )
        level = next(lv for lv in hist["levels"] if lv["id"] == "history_list")
        keys = [f["key"] for f in level["fields"]]
        self.assertNotIn("scrap_qty", keys)
        self.assertIn("unique_code", keys)

    def test_system_data_lists_transfer_dialog_section(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("system_data"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "عناوین دیالوگ و مقاصد انتقال داده")
        self.assertContains(hub, "source=transfer")

    def test_system_data_hides_inactive_section(self):
        sync_naming_registry()
        row = SystemNamingKey.objects.get(key="system.section.transfer_dialog_labels")
        row.is_active = False
        row.save(update_fields=["is_active"])
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("system_data"))
        self.assertEqual(hub.status_code, 200)
        self.assertNotContains(hub, "عناوین دیالوگ و مقاصد انتقال داده")

    def test_rename_persists_and_resolve_label(self):
        sync_naming_registry()
        self.client.login(username="expert", password="erp12345")
        row = SystemNamingKey.objects.get(
            key="ui.table.production.history_list.col.unique_code"
        )
        resp = self.client.post(
            reverse("system_naming_key_save"),
            data=json.dumps({"id": row.pk, "label": "کد یکتای سفارشی"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        row.refresh_from_db()
        self.assertEqual(row.label, "کد یکتای سفارشی")
        self.assertEqual(
            resolve_label("ui.table.production.history_list.col.unique_code"),
            "کد یکتای سفارشی",
        )

    def test_naming_keys_page_search_by_address(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("system_data"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "کلیدهای نام‌گذاری سیستم")
        self.assertContains(hub, "سرستون‌های جداول و عرض ستون گزارش")

        page = self.client.get(reverse("system_naming_keys"), {"q": "data-col=unique_code"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "unique_code")
        self.assertContains(page, "production/history.html")

    def test_table_columns_add_custom_and_link_section(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        cols = self.client.get(
            reverse("system_table_columns"),
            {"table": "planning.plan_list"},
        )
        self.assertEqual(cols.status_code, 200)
        self.assertContains(cols, "افزودن سرستون سفارشی")

        create = self.client.post(
            reverse("system_naming_key_save"),
            data=json.dumps({
                "key": "ui.table.planning.plan_list.col.custom_note",
                "label": "یادداشت سفارشی",
                "category": "column",
                "table_key": "planning.plan_list",
                "column_key": "custom_note",
                "linked_section_key": "weekly_plans",
                "address": "custom:planning.plan_list#custom_note",
                "is_active": True,
                "order": 50,
            }),
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 200)
        self.assertTrue(create.json()["ok"])
        row = SystemNamingKey.objects.get(key="ui.table.planning.plan_list.col.custom_note")
        self.assertTrue(row.is_custom)
        self.assertEqual(row.linked_section_key, "weekly_plans")

    def test_plan_list_uses_renamed_column_label(self):
        sync_naming_registry()
        row = SystemNamingKey.objects.get(
            key="ui.table.planning.plan_list.col.creator"
        )
        row.label = "نام کاربر ایجادکننده"
        row.save(update_fields=["label"])
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("plan_list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "نام کاربر ایجادکننده")

    def test_transfer_source_filter_shows_dialog_titles(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(
            reverse("system_naming_keys"),
            {"source": "transfer", "q": "انتقال داده جدول"},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "transfer.ui.dialog.title_transfer")
        self.assertContains(page, "دیالوگ انتقال")

    def test_excel_list_uses_renamed_column_label(self):
        from catalog.models import ExcelUpload

        sync_naming_registry()
        ExcelUpload.objects.create(title="نمونه", original_name="sample.xlsx", uploaded_by=self.admin)
        row = SystemNamingKey.objects.get(key="ui.table.catalog.excel_list.col.title")
        row.label = "نام فایل سفارشی"
        row.save(update_fields=["label"])
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("excel_list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "نام فایل سفارشی")
        self.assertContains(page, 'data-col="title"')

    def test_admin_header_save_scoped_to_model(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        # Seed two models that share column_key "label"
        key_a = "admin.field.catalog.moldoption.label"
        key_b = "admin.field.catalog.stoppagereason.label"
        SystemNamingKey.objects.update_or_create(
            key=key_a,
            defaults={
                "label": "عنوان",
                "default_label": "عنوان",
                "category": SystemNamingKey.Category.COLUMN,
                "table_key": "admin.catalog.moldoption",
                "column_key": "label",
                "is_active": True,
            },
        )
        SystemNamingKey.objects.update_or_create(
            key=key_b,
            defaults={
                "label": "عنوان",
                "default_label": "عنوان",
                "category": SystemNamingKey.Category.COLUMN,
                "table_key": "admin.catalog.stoppagereason",
                "column_key": "label",
                "is_active": True,
            },
        )
        resp = self.client.post(
            reverse("system_admin_header_save"),
            data=json.dumps({
                "path": "/admin/catalog/moldoption/",
                "field": "label",
                "label": "عنوان قالب سفارشی",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["key"], key_a)
        self.assertEqual(SystemNamingKey.objects.get(key=key_a).label, "عنوان قالب سفارشی")
        self.assertEqual(SystemNamingKey.objects.get(key=key_b).label, "عنوان")


class ReportColumnDefaultWidthUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")

    def test_report_table_shows_width_column(self):
        sync_naming_registry()
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(
            reverse("system_table_columns"),
            {"table": "report.fitting"},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "عرض ستون")
        self.assertContains(page, "default_width_px")

        row = SystemNamingKey.objects.get(key="report.col.fitting.code")
        save = self.client.post(
            reverse("system_naming_key_save"),
            data=json.dumps({
                "id": row.pk,
                "label": row.label,
                "default_width_px": 180,
                "is_active": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(save.status_code, 200)
        self.assertTrue(save.json()["ok"])
        row.refresh_from_db()
        self.assertEqual(row.default_width_px, 180)
