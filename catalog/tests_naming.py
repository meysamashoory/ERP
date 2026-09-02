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
        self.assertEqual(col.category, SystemNamingKey.Category.COLUMN)

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
