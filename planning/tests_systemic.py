"""Tests for inventory/orders hub and systemic weekly planning."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import ExcelTable, ExcelUpload, Machine, Product, ProductBomLine
from catalog.transfer import transfer_excel_table
from planning.inventory_orders import upsert_order_from_values, upsert_stock_from_values
from planning.models import CustomerOrder, WeeklyPlan
from planning.systemic import build_systemic_proposals, create_systemic_plan


User = get_user_model()


class InventoryOrdersSystemicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")
        cls.product = Product.objects.filter(is_active=True).first()
        cls.machine = Machine.objects.filter(machine_type="injection").first()
        assert cls.product is not None
        assert cls.machine is not None

    def test_upsert_order_and_stock(self):
        order = upsert_order_from_values(
            {
                "order_ref": "SO-1",
                "product_code": self.product.code,
                "product_name": self.product.name,
                "quantity": 100,
                "priority": 10,
                "is_backlog": "بله",
            }
        )
        self.assertEqual(order.quantity, 100)
        self.assertTrue(order.is_backlog)
        self.assertEqual(order.product_id, self.product.pk)

        upsert_stock_from_values(
            {
                "product_code": self.product.code,
                "stock_finished": 40,
                "depot_ceiling": 200,
            }
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_finished, 40)
        self.assertEqual(self.product.depot_ceiling, 200)

    def test_excel_transfer_orders_destination(self):
        upload = ExcelUpload.objects.create(title="orders", uploaded_by=self.admin)
        table = ExcelTable.objects.create(
            upload=upload,
            name="سفارشات",
            headers=["سفارش", "کد", "نام", "مقدار", "اولویت"],
            rows=[[ "SO-X", self.product.code, self.product.name, "55", "5"]],
        )
        result = transfer_excel_table(
            table=table,
            destination_id="inventory_orders",
            level_id="orders",
            mapping={
                "order_ref": 0,
                "product_code": 1,
                "product_name": 2,
                "quantity": 3,
                "priority": 4,
            },
            user=self.admin,
        )
        self.assertEqual(result.transferred, 1)
        self.assertTrue(
            CustomerOrder.objects.filter(order_ref="SO-X", product_code=self.product.code).exists()
        )
        self.assertIn("/planning/inventory-orders/", result.redirect_url)

    def test_systemic_plan_respects_stock_and_depot(self):
        CustomerOrder.objects.all().delete()
        from planning.models import WeeklyPlanItem

        WeeklyPlanItem.objects.filter(product=self.product).delete()
        self.product.stock_finished = 30
        self.product.depot_ceiling = 80
        self.product.last_cycle = 40
        self.product.main_cavities = 2
        self.product.save()
        CustomerOrder.objects.create(
            order_ref="SO-SYS",
            product_code=self.product.code,
            product_name=self.product.name,
            product=self.product,
            quantity=100,
            priority=1,
        )
        from planning.intelligence import open_planned_qty_for_product

        proposals = build_systemic_proposals()
        hit = [p for p in proposals if p.product.pk == self.product.pk]
        self.assertEqual(len(hit), 1)
        # Isolated product: need 70, depot room 50 → produce 50
        self.assertEqual(open_planned_qty_for_product(self.product), 0)
        self.assertEqual(hit[0].net_need, 70)
        self.assertEqual(hit[0].produce_qty, 50)

        import jdatetime

        plan, alarms = create_systemic_plan(
            program_number="SYS-TEST-1",
            plan_date=jdatetime.date(1405, 7, 20),
            user=self.admin,
        )
        self.assertEqual(plan.planning_mode, WeeklyPlan.PlanningMode.SYSTEMIC)
        self.assertGreaterEqual(plan.items.count(), 1)
        line = plan.items.first().lines.first()
        self.assertEqual(line.quantity, 50)

    def test_hub_and_create_choose_pages(self):
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("inventory_orders"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "بررسی موجودی و سفارشات")
        self.assertContains(hub, "plan-create-dialog")
        self.assertContains(hub, "data-plan-mode=\"systemic\"")

        # Legacy choose/form URLs now open the list dialog
        choose = self.client.get(reverse("plan_create"))
        self.assertEqual(choose.status_code, 302)
        self.assertIn("create=1", choose["Location"])
        systemic = self.client.get(reverse("plan_create") + "?mode=systemic")
        self.assertEqual(systemic.status_code, 302)
        self.assertIn("create=systemic", systemic["Location"])

        listing = self.client.get(reverse("plan_list") + "?create=systemic")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "plan-create-dialog")
        self.assertContains(listing, "ساخت برنامه سیستمی")

    def test_intelligence_cockpit_and_forecast_netting(self):
        from planning.intelligence import demand_balance, material_shortages
        from planning.models import SalesForecast, WeeklyPlanItem
        from catalog.models import ProductBomLine

        WeeklyPlanItem.objects.filter(product=self.product).delete()
        CustomerOrder.objects.filter(product_code=self.product.code).delete()
        self.product.stock_finished = 10
        self.product.depot_ceiling = 500
        self.product.save()
        CustomerOrder.objects.create(
            product_code=self.product.code,
            product_name=self.product.name,
            product=self.product,
            quantity=40,
            priority=1,
        )
        SalesForecast.objects.create(
            product_code=self.product.code,
            product_name=self.product.name,
            product=self.product,
            quantity=20,
            period_label="هفته جاری",
        )
        rows = {r.product_code: r for r in demand_balance()}
        row = rows[self.product.code]
        self.assertEqual(row.order_qty, 40)
        self.assertEqual(row.forecast_qty, 20)
        self.assertEqual(row.net_gap, 50)  # 60 demand - 10 stock

        other = Product.objects.exclude(pk=self.product.pk).filter(is_active=True).first()
        if other:
            other.stock_finished = 1
            other.save(update_fields=["stock_finished"])
            ProductBomLine.objects.create(
                parent=self.product,
                component_code=other.code,
                component_name=other.name,
                quantity=2,
            )
            mats = {m.component_code: m for m in material_shortages({self.product.code: 10})}
            self.assertIn(other.code, mats)
            self.assertGreater(mats[other.code].gap, 0)

        self.client.login(username="admin", password="erp12345")
        page = self.client.get(reverse("systemic_intelligence"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "هوش برنامه‌ریزی سیستمی")
        self.assertContains(page, "تراز تقاضا و تأمین")
        page2 = self.client.get(reverse("systemic_intelligence"), {"tab": "exceptions"})
        self.assertEqual(page2.status_code, 200)
        self.assertContains(page2, "NET_SHORT")


    def test_systemic_create_json_returns_redirect(self):
        self.client.login(username="admin", password="erp12345")
        from datetime import timedelta

        from catalog.jalali_dates import format_jalali_slash
        from django.utils import timezone

        plan_date = timezone.localdate() + timedelta(days=17)
        while WeeklyPlan.objects.filter(date=plan_date).exists():
            plan_date += timedelta(days=1)
        resp = self.client.post(
            reverse("plan_create"),
            {
                "planning_mode": "systemic",
                "program_number": "SYS-DIALOG-1",
                "date": format_jalali_slash(plan_date),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("/planning/", data["redirect_url"])
        plan = WeeklyPlan.objects.get(program_number="SYS-DIALOG-1")
        self.assertEqual(plan.planning_mode, WeeklyPlan.PlanningMode.SYSTEMIC)

    def test_systemic_create_validation_errors_json(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.post(
            reverse("plan_create"),
            {"planning_mode": "systemic", "program_number": "", "date": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("program_number", data["errors"])
