"""Dashboard analytics payload tests."""

import jdatetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.dashboard_analytics import _jalali_parts, build_dashboard_charts


class DashboardAnalyticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("dashadmin", "d@x.com", "erp12345")

    def test_jalali_parts_from_jdate(self):
        self.assertEqual(_jalali_parts(jdatetime.date(1403, 4, 15)), (1403, 4, 15))
        self.assertIsNone(_jalali_parts(None))

    def test_build_charts_shape(self):
        charts = build_dashboard_charts()
        self.assertIn(charts["sales_source"], {"production", "vouchers"})
        self.assertEqual(len(charts["seasons"]["labels"]), 4)
        self.assertIn("labels", charts["years"])
        self.assertIn("values", charts["years"])
        self.assertIn("labels", charts["top_products"])
        self.assertIn("values", charts["top_products"])
        self.assertIn("pct", charts["compare"])
        self.assertIn("compare_points", charts)
        self.assertIsInstance(charts["compare_points"], list)

    def test_dashboard_page_has_chart_controls(self):
        self.client.login(username="dashadmin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تحلیل فروش و روند")
        self.assertContains(resp, "dash-chart-type")
        self.assertContains(resp, "dash-chart-scope")
        self.assertContains(resp, "dash-compare-a")
        self.assertContains(resp, "dash-compare-b")
        self.assertContains(resp, "پرفروش‌ترین")
        self.assertContains(resp, "کم‌فروش‌ترین")
        self.assertContains(resp, "نقطه الف")
        self.assertContains(resp, "نقطه ب")
        self.assertContains(resp, "chart.umd.min.js")
        self.assertContains(resp, "dashboard_charts.js")
        self.assertContains(resp, "برنامه‌ریزی توسط سیستم")
        self.assertContains(resp, "محاسبات زمان تولید")
        # Pipe calc sits under production section, after history in nav order.
        body = resp.content.decode("utf-8")
        hist = body.find("سوابق تولید")
        pipe = body.find("محاسبات زمان تولید")
        self.assertGreater(pipe, hist)
