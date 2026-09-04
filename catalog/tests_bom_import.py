"""Tests for Bom Version CSV import into product-data tabs."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.bom_import import (
    FILE_MATERIALS_BOM,
    FILE_PARTS_BOM,
    FILE_RECIPE_CHANGE,
    FILE_VERSION_LOG,
    classify_bom_csv,
    import_bom_csv,
    import_bom_paths,
)
from catalog.flexible_data import LEVEL_BOM, LEVEL_BOM_MATERIALS, LEVEL_CONSUMABLES
from catalog.models import FlexibleDataset, FlexibleRow, Product, ProductBomLine


SAMPLES = Path(__file__).resolve().parent / "fixtures" / "bom_samples"


class BomImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("bomadmin", "b@x.com", "erp12345")

    def test_classify_sample_files(self):
        from catalog.bom_import import _read_csv

        h, _ = _read_csv(SAMPLES / "parts_bom.csv")
        self.assertEqual(classify_bom_csv(h), FILE_PARTS_BOM)
        h, _ = _read_csv(SAMPLES / "materials_bom.csv")
        self.assertEqual(classify_bom_csv(h), FILE_MATERIALS_BOM)
        h, _ = _read_csv(SAMPLES / "version_registry.csv")
        self.assertEqual(classify_bom_csv(h), FILE_VERSION_LOG)
        h, _ = _read_csv(SAMPLES / "recipe_change_log.csv")
        self.assertEqual(classify_bom_csv(h), FILE_RECIPE_CHANGE)

    def test_import_parts_and_materials(self):
        results = import_bom_paths(
            [
                SAMPLES / "parts_bom.csv",
                SAMPLES / "materials_bom.csv",
                SAMPLES / "version_registry.csv",
                SAMPLES / "recipe_change_log.csv",
            ]
        )
        by_kind = {r.file_kind: r for r in results}
        self.assertEqual(by_kind[FILE_PARTS_BOM].level_id, LEVEL_BOM)
        self.assertGreater(by_kind[FILE_PARTS_BOM].rows_loaded, 10)
        self.assertGreater(by_kind[FILE_PARTS_BOM].products_ensured, 0)
        self.assertGreater(by_kind[FILE_PARTS_BOM].bom_lines_synced, 0)
        self.assertEqual(by_kind[FILE_MATERIALS_BOM].level_id, LEVEL_BOM_MATERIALS)
        self.assertGreater(by_kind[FILE_MATERIALS_BOM].rows_loaded, 10)
        self.assertEqual(by_kind[FILE_VERSION_LOG].rows_loaded, 0)
        self.assertEqual(by_kind[FILE_RECIPE_CHANGE].rows_loaded, 0)

        bom_ds = FlexibleDataset.objects.get(
            destination_id="product_data", level_id=LEVEL_BOM
        )
        self.assertTrue(FlexibleRow.objects.filter(dataset=bom_ds).exists())
        labels = {c["label"] for c in bom_ds.columns}
        self.assertIn("کد محصول", labels)
        self.assertTrue(
            any("مصرفی" in str(x) and "کد" in str(x) for x in labels),
            msg=labels,
        )

        mat_ds = FlexibleDataset.objects.get(
            destination_id="product_data", level_id=LEVEL_BOM_MATERIALS
        )
        self.assertTrue(FlexibleRow.objects.filter(dataset=mat_ds).exists())

        cons_ds = FlexibleDataset.objects.get(
            destination_id="product_data", level_id=LEVEL_CONSUMABLES
        )
        self.assertGreaterEqual(FlexibleRow.objects.filter(dataset=cons_ds).count(), 1)

        self.assertTrue(Product.objects.filter(code="11005045").exists())
        self.assertTrue(
            ProductBomLine.objects.filter(
                parent__code="11005045", component_code="711005045"
            ).exists()
        )

    def test_product_hub_shows_imported_bom(self):
        import_bom_csv(SAMPLES / "parts_bom.csv")
        self.client.login(username="bomadmin", password="erp12345")
        page = self.client.get(reverse("product_data") + "?tab=bom")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "flexible-data-table")
        self.assertContains(page, "11005045")
        self.assertNotContains(page, "در این بخش هنوز دیتایی تعریف نشده است")
