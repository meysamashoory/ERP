from decimal import Decimal

import jdatetime
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from catalog.models import Machine, Product, ProductionUnit
from production.models import FittingProduction

User = get_user_model()


class SeedAndDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_seed_is_idempotent(self):
        units_before = Machine.objects.count()
        products_before = Product.objects.count()
        call_command("seed_demo")
        self.assertEqual(Machine.objects.count(), units_before)
        self.assertEqual(Product.objects.count(), products_before)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_dashboard_loads_for_authenticated_user(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "داشبورد عملیات")

    def test_reports_excel_export(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("reports"), {"type": "fitting", "export": "excel"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(resp.content), 0)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_viewer_cannot_open_fitting_form(self):
        self.client.login(username="viewer", password="erp12345")
        resp = self.client.get(reverse("fitting_create"))
        self.assertEqual(resp.status_code, 403)

    def test_clerk_cannot_create_plan(self):
        self.client.login(username="clerk", password="erp12345")
        resp = self.client.get(reverse("plan_create"))
        self.assertEqual(resp.status_code, 403)

    def test_expert_can_open_fitting_form(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.get(reverse("fitting_create"))
        self.assertEqual(resp.status_code, 200)

    def test_role_defaults_for_superuser(self):
        admin = User.objects.get(username="admin")
        self.assertEqual(admin.profile.role, Role.PLANNING_MANAGER)


class ModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_fitting_deviation(self):
        rec = FittingProduction.objects.create(
            unit=ProductionUnit.objects.get(number=1),
            date=jdatetime.date.today(),
            machine=Machine.objects.filter(machine_type="injection").first(),
            product=Product.objects.first(),
            planned_quantity=1000,
            produced_quantity=930,
        )
        self.assertEqual(rec.deviation, -70)

    def test_product_needs_reorder(self):
        low = Product.objects.get(code="F-1100")  # stock 300, reorder 400
        self.assertTrue(low.needs_reorder)
        ok = Product.objects.get(code="F-0900")  # stock 1800, reorder 500
        self.assertFalse(ok.needs_reorder)
