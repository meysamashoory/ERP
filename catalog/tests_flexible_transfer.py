"""Tests for raw destinations, bootstrap transfer, replace, and keyed update."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.flexible_data import load_schema_columns
from catalog.models import ExcelTable, ExcelUpload, FlexibleRow, SystemNamingKey
from catalog.transfer import (
    DESTINATION_PRODUCT_DATA,
    MODE_TRANSFER,
    MODE_UPDATE,
    list_destinations_for_ui,
    transfer_excel_table,
)

User = get_user_model()


class FlexibleTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")

    def _table(self, headers, rows, name="t1"):
        upload = ExcelUpload.objects.create(title="test", uploaded_by=self.admin)
        return ExcelTable.objects.create(
            upload=upload,
            name=name,
            headers=headers,
            rows=rows,
            sheet_name="Sheet1",
        )

    def test_destinations_include_raw_product_tabs(self):
        dests = {d["id"]: d for d in list_destinations_for_ui()}
        self.assertIn(DESTINATION_PRODUCT_DATA, dests)
        self.assertNotIn("inventory_orders", dests)
        self.assertNotIn("vouchers", dests)
        products = dests[DESTINATION_PRODUCT_DATA]
        ids = [lv["id"] for lv in products["levels"]]
        self.assertIn("products", ids)
        self.assertIn("bom", ids)
        self.assertIn("consumables", ids)
        self.assertIn("specs", ids)
        self.assertIn("vouchers", ids)
        for lv in products["levels"]:
            if lv["id"] == "vouchers" and lv.get("has_rows"):
                continue
            self.assertTrue(lv.get("is_raw") or lv.get("has_schema"))

    def test_product_hub_raw_empty(self):
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("product_data"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "محصولات")
        self.assertContains(page, "BOM")
        self.assertContains(page, "مواد مصرفی")
        self.assertContains(page, "مشخصات فنی")
        self.assertContains(page, "حواله‌ها")

    def test_vouchers_tab_shows_data_after_transfer(self):
        self.client.login(username="admin", password="erp12345")
        table = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [["H-1", "100", "5"]],
        )
        transfer_excel_table(
            table=table,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping={},
            user=self.admin,
            mode=MODE_TRANSFER,
            bootstrap_columns=[0, 1, 2],
            confirm_replace=True,
        )
        page = self.client.get(reverse("product_data") + "?tab=vouchers")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "flexible-data-table")
        self.assertContains(page, "H-1")

    def test_bootstrap_transfer_then_replace(self):
        table = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [
                ["H-1", "100", "5"],
                ["H-2", "200", "9"],
            ],
        )
        result = transfer_excel_table(
            table=table,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping={},
            user=self.admin,
            mode=MODE_TRANSFER,
            bootstrap_columns=[0, 1, 2],
            confirm_replace=True,
        )
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.transferred, 2)
        cols = load_schema_columns(DESTINATION_PRODUCT_DATA, "vouchers")
        self.assertEqual(len(cols), 3)
        key_labels = {c["label"] for c in cols if c.get("is_key")}
        self.assertIn("شماره حواله", key_labels)
        self.assertIn("کد کالا", key_labels)
        self.assertEqual(FlexibleRow.objects.filter(dataset__level_id="vouchers").count(), 2)

        table2 = self._table(
            ["شماره حواله", "کد کالا", "مقدار", "انبار"],
            [["H-9", "900", "1", "A"]],
            name="t2",
        )
        with self.assertRaises(ValueError):
            transfer_excel_table(
                table=table2,
                destination_id=DESTINATION_PRODUCT_DATA,
                level_id="vouchers",
                mapping={cols[0]["key"]: 0},
                user=self.admin,
                mode=MODE_TRANSFER,
                confirm_replace=True,
            )

        mapping = {c["key"]: i for i, c in enumerate(cols)}
        result2 = transfer_excel_table(
            table=table2,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping=mapping,
            user=self.admin,
            mode=MODE_TRANSFER,
            confirm_replace=True,
            add_columns=[3],
        )
        self.assertEqual(result2.failed, 0)
        self.assertEqual(result2.transferred, 1)
        self.assertEqual(FlexibleRow.objects.filter(dataset__level_id="vouchers").count(), 1)
        cols2 = load_schema_columns(DESTINATION_PRODUCT_DATA, "vouchers")
        self.assertEqual(len(cols2), 4)

    def test_update_blocked_when_empty_then_keyed_update(self):
        table = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [["H-1", "100", "5"]],
        )
        with self.assertRaises(ValueError):
            transfer_excel_table(
                table=table,
                destination_id=DESTINATION_PRODUCT_DATA,
                level_id="vouchers",
                mapping={},
                user=self.admin,
                mode=MODE_UPDATE,
            )

        transfer_excel_table(
            table=table,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping={},
            user=self.admin,
            mode=MODE_TRANSFER,
            bootstrap_columns=[0, 1, 2],
            confirm_replace=True,
        )
        cols = load_schema_columns(DESTINATION_PRODUCT_DATA, "vouchers")

        table_b = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [
                ["H-1", "100", "5"],
                ["H-2", "200", "9"],
            ],
            name="seed2",
        )
        mapping_all = {c["key"]: i for i, c in enumerate(cols)}
        transfer_excel_table(
            table=table_b,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping=mapping_all,
            user=self.admin,
            mode=MODE_TRANSFER,
            confirm_replace=True,
        )
        self.assertEqual(FlexibleRow.objects.filter(dataset__level_id="vouchers").count(), 2)

        table_u = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [["H-1", "100", "77"]],
            name="upd",
        )
        result = transfer_excel_table(
            table=table_u,
            destination_id=DESTINATION_PRODUCT_DATA,
            level_id="vouchers",
            mapping=mapping_all,
            user=self.admin,
            mode=MODE_UPDATE,
        )
        self.assertEqual(result.failed, 0)
        self.assertEqual(FlexibleRow.objects.filter(dataset__level_id="vouchers").count(), 1)
        row = FlexibleRow.objects.get(dataset__level_id="vouchers")
        qty_key = next(c["key"] for c in cols if c["label"] == "مقدار")
        self.assertEqual(str(row.values.get(qty_key)), "77")

    def test_naming_is_key_toggle_api(self):
        self.client.login(username="admin", password="erp12345")
        row = SystemNamingKey.objects.create(
            key="transfer.field.product_data.vouchers.demo",
            label="دمو",
            default_label="دمو",
            category=SystemNamingKey.Category.COLUMN,
            table_key="transfer.product_data.vouchers",
            column_key="demo",
            is_custom=True,
            is_key=False,
        )
        resp = self.client.post(
            reverse("system_naming_key_save"),
            data=json.dumps({"id": row.pk, "is_key": True, "label": "دمو"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.is_key)
