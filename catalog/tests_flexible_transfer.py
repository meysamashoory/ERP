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
    DESTINATION_VOUCHERS,
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

    def test_destinations_include_raw_product_and_vouchers(self):
        dests = {d["id"]: d for d in list_destinations_for_ui()}
        self.assertIn(DESTINATION_PRODUCT_DATA, dests)
        self.assertIn(DESTINATION_VOUCHERS, dests)
        self.assertNotIn("inventory_orders", dests)
        products = dests[DESTINATION_PRODUCT_DATA]
        ids = [l["id"] for l in products["levels"]]
        self.assertEqual(ids, ["products", "bom", "consumables", "specs"])
        for lv in products["levels"]:
            self.assertTrue(lv["is_raw"])
            self.assertEqual(lv["fields"], [])
        vouchers = dests[DESTINATION_VOUCHERS]["levels"][0]
        self.assertTrue(vouchers["is_raw"])

    def test_product_hub_raw_empty(self):
        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("product_data"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "محصولات")
        self.assertContains(page, "BOM")
        self.assertContains(page, "مواد مصرفی")
        self.assertContains(page, "مشخصات فنی")
        self.assertContains(page, "هنوز خام است")
        self.assertNotContains(page, reverse("inventory_orders"))

    def test_vouchers_hub_and_nav(self):
        self.client.login(username="admin", password="erp12345")
        dash = self.client.get(reverse("dashboard"))
        self.assertContains(dash, reverse("vouchers_hub"))
        self.assertContains(dash, "حواله‌ها")
        self.assertNotContains(dash, "بررسی موجودی و سفارشات")
        page = self.client.get(reverse("vouchers_hub"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "هنوز خام است")

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
            destination_id=DESTINATION_VOUCHERS,
            level_id="voucher_list",
            mapping={},
            user=self.admin,
            mode=MODE_TRANSFER,
            bootstrap_columns=[0, 1, 2],
            confirm_replace=True,
        )
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.transferred, 2)
        cols = load_schema_columns(DESTINATION_VOUCHERS, "voucher_list")
        self.assertEqual(len(cols), 3)
        key_labels = {c["label"] for c in cols if c.get("is_key")}
        self.assertIn("شماره حواله", key_labels)
        self.assertIn("کد کالا", key_labels)
        self.assertEqual(FlexibleRow.objects.count(), 2)

        # Second transfer without mapping all columns must fail
        table2 = self._table(
            ["شماره حواله", "کد کالا", "مقدار", "انبار"],
            [["H-9", "900", "1", "A"]],
            name="t2",
        )
        with self.assertRaises(ValueError):
            transfer_excel_table(
                table=table2,
                destination_id=DESTINATION_VOUCHERS,
                level_id="voucher_list",
                mapping={cols[0]["key"]: 0},  # incomplete
                user=self.admin,
                mode=MODE_TRANSFER,
                confirm_replace=True,
            )

        # Full mapping + new column checkbox
        mapping = {c["key"]: i for i, c in enumerate(cols)}
        result2 = transfer_excel_table(
            table=table2,
            destination_id=DESTINATION_VOUCHERS,
            level_id="voucher_list",
            mapping=mapping,
            user=self.admin,
            mode=MODE_TRANSFER,
            confirm_replace=True,
            add_columns=[3],
        )
        self.assertEqual(result2.failed, 0)
        self.assertEqual(result2.transferred, 1)
        self.assertEqual(FlexibleRow.objects.count(), 1)
        cols2 = load_schema_columns(DESTINATION_VOUCHERS, "voucher_list")
        self.assertEqual(len(cols2), 4)

    def test_update_blocked_when_empty_then_keyed_update(self):
        table = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [["H-1", "100", "5"]],
        )
        with self.assertRaises(ValueError):
            transfer_excel_table(
                table=table,
                destination_id=DESTINATION_VOUCHERS,
                level_id="voucher_list",
                mapping={},
                user=self.admin,
                mode=MODE_UPDATE,
            )

        transfer_excel_table(
            table=table,
            destination_id=DESTINATION_VOUCHERS,
            level_id="voucher_list",
            mapping={},
            user=self.admin,
            mode=MODE_TRANSFER,
            bootstrap_columns=[0, 1, 2],
            confirm_replace=True,
        )
        cols = load_schema_columns(DESTINATION_VOUCHERS, "voucher_list")
        key_cols = [c for c in cols if c.get("is_key")]
        self.assertTrue(key_cols)

        # Seed a second row
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
            destination_id=DESTINATION_VOUCHERS,
            level_id="voucher_list",
            mapping=mapping_all,
            user=self.admin,
            mode=MODE_TRANSFER,
            confirm_replace=True,
        )
        self.assertEqual(FlexibleRow.objects.count(), 2)

        # Update: only H-1 remains with new qty; H-2 deleted
        table_u = self._table(
            ["شماره حواله", "کد کالا", "مقدار"],
            [["H-1", "100", "77"]],
            name="upd",
        )
        mapping_keys = {c["key"]: i for i, c in enumerate(cols)}
        result = transfer_excel_table(
            table=table_u,
            destination_id=DESTINATION_VOUCHERS,
            level_id="voucher_list",
            mapping=mapping_keys,
            user=self.admin,
            mode=MODE_UPDATE,
        )
        self.assertEqual(result.failed, 0)
        self.assertEqual(FlexibleRow.objects.count(), 1)
        row = FlexibleRow.objects.get()
        qty_key = next(c["key"] for c in cols if c["label"] == "مقدار")
        self.assertEqual(str(row.values.get(qty_key)), "77")

    def test_naming_is_key_toggle_api(self):
        self.client.login(username="admin", password="erp12345")
        row = SystemNamingKey.objects.create(
            key="transfer.field.vouchers.voucher_list.demo",
            label="دمو",
            default_label="دمو",
            category=SystemNamingKey.Category.COLUMN,
            table_key="transfer.vouchers.voucher_list",
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
