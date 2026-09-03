"""System data hub must expose real configuration — not app-page shortcuts."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.system_sections import build_system_groups


def _accordion_hrefs(html: str) -> list[str]:
    """Collect hrefs only from the system accordion (exclude sidebar/nav)."""
    match = re.search(
        r'<div class="system-accordion"[^>]*>(.*?)</div>\s*(?:</div>\s*)?(?:{%|\n\s*</main>|</main>)',
        html,
        flags=re.S,
    )
    chunk = match.group(1) if match else ""
    if not chunk:
        # Fallback: between accordion id and end of panel
        start = html.find('id="system-accordion"')
        end = html.find("</main>", start)
        chunk = html[start:end] if start >= 0 and end > start else html
    return re.findall(r'href="([^"]+)"', chunk)


class SystemDataNoShortcutsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.filter(username="admin").first()
        if self.user is None:
            self.user = User.objects.create_superuser("admin", "a@b.c", "erp12345")
        self.client = Client(HTTP_HOST="localhost")
        assert self.client.login(username="admin", password="erp12345")

    def test_hub_avoids_operational_page_urls(self):
        page = self.client.get(reverse("system_data"))
        self.assertEqual(page.status_code, 200)
        hrefs = _accordion_hrefs(page.content.decode())

        forbidden_prefixes = [
            reverse("product_data"),
            reverse("pipe_calc"),
            reverse("excel_list"),
            reverse("excel_import"),
            reverse("systemic_intelligence"),
            reverse("plan_list"),
            reverse("program_list"),
            reverse("production_history"),
            reverse("dashboard"),
        ]
        for href in hrefs:
            for bad in forbidden_prefixes:
                self.assertFalse(
                    href == bad or href.startswith(bad + "?") or href.startswith(bad + "/"),
                    msg=f"accordion shortcut {href} matches operational {bad}",
                )

    def test_hub_uses_admin_for_former_shortcuts(self):
        page = self.client.get(reverse("system_data"))
        hrefs = _accordion_hrefs(page.content.decode())
        joined = "\n".join(hrefs)
        self.assertIn(reverse("admin:catalog_excelupload_changelist"), joined)
        self.assertIn(reverse("admin:catalog_flexibledataset_changelist"), joined)
        self.assertIn(reverse("admin:catalog_flexiblerow_changelist"), joined)
        self.assertIn(reverse("admin:catalog_pipeproductline_changelist"), joined)
        self.assertTrue(
            all("/planning/systemic" not in h for h in hrefs),
            msg="systemic intelligence must not appear as a system-data section link",
        )

    def test_registry_items_prefer_admin_or_system_config_ui(self):
        """Every section either has admin changelist or a dedicated system config URL."""
        system_config_urls = {
            "system_naming_keys",
            "system_table_columns",
            "system_table_layout",
            "planning_process_list",
        }
        for group in build_system_groups():
            for item in group.items:
                if item.admin_changelist:
                    self.assertTrue(
                        item.admin_changelist.startswith("admin:"),
                        msg=f"{item.key} admin_changelist invalid",
                    )
                    continue
                self.assertIn(
                    item.url_name,
                    system_config_urls,
                    msg=f"{item.key} is neither admin nor allowed system-config UI",
                )

    def test_flexible_dataset_admin_loads(self):
        resp = self.client.get(reverse("admin:catalog_flexibledataset_changelist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "بازگشت به داده‌های سیستم")

    def test_section_redirect_uses_admin_not_app(self):
        resp = self.client.get(reverse("system_section", args=["pipe_calc"]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/catalog/pipeproductline/", resp["Location"])

        resp2 = self.client.get(reverse("system_section", args=["product_data_hub"]))
        self.assertEqual(resp2.status_code, 302)
        self.assertIn("/admin/catalog/flexibledataset/", resp2["Location"])


class TableLayoutSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        from django.contrib.auth import get_user_model

        call_command("seed_demo")
        cls.User = get_user_model()
        cls.admin = cls.User.objects.get(username="admin")

    def test_table_layout_page_save(self):
        from django.urls import reverse
        from catalog.models import TableLayoutSettings

        self.client.login(username="admin", password="erp12345")
        url = reverse("system_table_layout")
        get = self.client.get(url)
        self.assertEqual(get.status_code, 200)
        self.assertContains(get, "ارتفاع یکنواخت ردیف")
        self.assertContains(get, "قفل عرض ستون")
        resp = self.client.post(
            url,
            {
                "row_height_px": "44",
                "lock_reports": "1",
                "lock_history": "1",
            },
        )
        self.assertEqual(resp.status_code, 302)
        settings = TableLayoutSettings.load()
        self.assertEqual(settings.clamped_row_height(), 44)
        self.assertTrue(settings.is_width_locked("reports"))
        self.assertTrue(settings.is_width_locked("history"))
        self.assertFalse(settings.is_width_locked("product_data"))
