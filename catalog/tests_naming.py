"""Tests for system naming-key registry and column management UI."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import SystemNamingKey
from catalog.naming_registry import resolve_label, sync_naming_registry

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
        # list_display columns like created_by remain (visible in /admin/), but
        # addresses must clearly say they are from the admin panel.
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
        self.assertNotContains(page, "admin.field.")
        admin_page = self.client.get(reverse("system_naming_keys"), {"source": "admin"})
        self.assertEqual(admin_page.status_code, 200)
        self.assertContains(admin_page, "admin.field.")
        self.assertContains(admin_page, "list_display=")

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
        self.assertContains(hub, "سرستون‌های جداول سامانه")

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
