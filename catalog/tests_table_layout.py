"""Unit tests for per-menu table display helpers."""

from __future__ import annotations

from django.test import SimpleTestCase

from catalog.table_layout import (
    clamp_row_height,
    css_for_layouts,
    default_width_locked,
    normalize_all_layouts,
)


class TableLayoutHelpersTests(SimpleTestCase):
    def test_clamp_row_height_range(self):
        self.assertEqual(clamp_row_height(5), 5)
        self.assertEqual(clamp_row_height(120), 120)
        self.assertEqual(clamp_row_height(4), 5)
        self.assertEqual(clamp_row_height(200), 120)
        self.assertEqual(clamp_row_height("x"), 36)

    def test_default_lock_only_reports_unlocked(self):
        self.assertFalse(default_width_locked("reports"))
        self.assertTrue(default_width_locked("planning"))
        self.assertTrue(default_width_locked("product_data"))

    def test_normalize_empty_uses_defaults(self):
        layouts = normalize_all_layouts({})
        self.assertFalse(layouts["reports"]["width_locked"])
        self.assertTrue(layouts["history"]["width_locked"])
        self.assertTrue(layouts["reports"]["col_border"])
        self.assertEqual(layouts["planning"]["row_height_px"], 36)

    def test_normalize_uses_legacy_locks_when_layouts_empty(self):
        layouts = normalize_all_layouts(
            {},
            legacy_height=40,
            legacy_locks={"reports": True},
        )
        self.assertEqual(layouts["planning"]["row_height_px"], 40)
        self.assertTrue(layouts["reports"]["width_locked"])

    def test_css_includes_height_and_hidden_borders(self):
        css = css_for_layouts(
            {
                "planning": {
                    "row_height_px": 8,
                    "col_border": False,
                    "row_border": True,
                    "width_locked": True,
                }
            }
        )
        self.assertIn('[data-table-section="planning"]{--table-row-height:8px;}', css)
        self.assertIn("border-left-color:transparent", css)
        self.assertNotIn("border-bottom-color:transparent", css)
