"""Tests for pipe production-time calculation engine and hub."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts.models import Role, UserProfile
from catalog.pipe_calc.constants import LINE_GENERAL, LINE_PROTECT, LINE_TIP, PROTECT_SIZES
from catalog.pipe_calc.engine import (
    CalcItemInput,
    aggregate_times,
    calc_bom_needs,
    calc_depot,
    calc_production_time,
)
from catalog.pipe_calc.models import PipeLengthCut, PipeProductLine, PipeSizeProfile
from catalog.pipe_calc.seed import seed_pipe_calc_defaults
from catalog.pipe_calc.services import run_line_aggregate, run_scenario


class PipeCalcEngineTests(TestCase):
    def test_line_and_billing_time(self):
        item = CalcItemInput(
            key="p",
            pieces=100,
            cut_length_mm=318,  # ~0.318 m
            line_speed_m_per_min=10.0,
            billing_pieces_per_hour=300.0,
            socket_ends=1,
            pack_qty=50,
            needs_billing=True,
        )
        res = calc_production_time(item)
        self.assertAlmostEqual(res.meters, 31.8, places=2)
        # 31.8 m / 10 m/min = 3.18 min = 190.8 s
        self.assertAlmostEqual(res.line.seconds, 190.8, places=1)
        # 100 pcs / 300 per hour = 1200 s
        self.assertAlmostEqual(res.billing.seconds, 1200.0, places=1)
        self.assertEqual(res.packs, 2.0)

    def test_two_socket_doubles_billing(self):
        one = calc_production_time(
            CalcItemInput(
                key="a",
                pieces=60,
                cut_length_mm=1000,
                line_speed_m_per_min=10,
                billing_pieces_per_hour=120,
                socket_ends=1,
            )
        )
        two = calc_production_time(
            CalcItemInput(
                key="b",
                pieces=60,
                cut_length_mm=1000,
                line_speed_m_per_min=10,
                billing_pieces_per_hour=120,
                socket_ends=2,
            )
        )
        self.assertAlmostEqual(two.billing.seconds, one.billing.seconds * 2, places=1)

    def test_depot_shortage_and_voucher(self):
        d = calc_depot(ceiling=1000, stock=700, voucher_qty=100)
        self.assertEqual(d.empty_space, 300)
        self.assertEqual(d.stock_after_voucher, 600)
        self.assertEqual(d.empty_after_voucher, 400)
        self.assertEqual(d.fill_to_ceiling, 300)

    def test_bom_order_signal(self):
        bom = calc_bom_needs(
            10,
            [
                {
                    "code": "M1",
                    "name": "ماده",
                    "unit": "kg",
                    "qty_per_unit": 2,
                    "available": 5,
                }
            ],
        )
        self.assertTrue(bom.has_shortage)
        self.assertEqual(bom.lines[0].qty_needed, 20)
        self.assertEqual(bom.lines[0].qty_short, 15)
        self.assertTrue(bom.lines[0].order_suggested)

    def test_aggregate(self):
        a = calc_production_time(
            CalcItemInput(
                key="1",
                pieces=10,
                cut_length_mm=1000,
                line_speed_m_per_min=10,
                billing_pieces_per_hour=100,
            )
        )
        b = calc_production_time(
            CalcItemInput(
                key="2",
                pieces=20,
                cut_length_mm=1000,
                line_speed_m_per_min=10,
                billing_pieces_per_hour=100,
            )
        )
        agg = aggregate_times([a, b])
        self.assertEqual(agg.pieces, 30)
        self.assertEqual(agg.item_count, 2)
        self.assertAlmostEqual(agg.line_seconds, a.line.seconds + b.line.seconds, places=1)


class PipeCalcSeedAndServiceTests(TestCase):
    def setUp(self):
        seed_pipe_calc_defaults()

    def test_protect_sizes_and_lengths(self):
        line = PipeProductLine.objects.get(code=LINE_PROTECT)
        self.assertFalse(line.is_scaffold)
        self.assertTrue(line.needs_billing)
        sizes = list(
            PipeSizeProfile.objects.filter(line=line).values_list("size_mm", flat=True)
        )
        self.assertEqual(sorted(sizes), list(PROTECT_SIZES))
        profile = PipeSizeProfile.objects.get(line=line, size_mm=110)
        self.assertEqual(profile.length_cuts.count(), 10)
        self.assertEqual(profile.layers.count(), 1)
        cut_30 = PipeLengthCut.objects.get(size_profile=profile, length_code="30cm_1s")
        cut_50 = PipeLengthCut.objects.get(size_profile=profile, length_code="50cm_1s")
        coupler = PipeLengthCut.objects.get(size_profile=profile, length_code="coupler")
        self.assertLess(cut_30.cut_length_mm, cut_50.cut_length_mm)
        self.assertEqual(coupler.label, "رابط")

    def test_general_no_40_200_triple_layer(self):
        line = PipeProductLine.objects.get(code=LINE_GENERAL)
        sizes = set(
            PipeSizeProfile.objects.filter(line=line).values_list("size_mm", flat=True)
        )
        self.assertNotIn(40, sizes)
        self.assertNotIn(200, sizes)
        profile = PipeSizeProfile.objects.get(line=line, size_mm=110)
        self.assertEqual(profile.layers.count(), 3)

    def test_tip_is_scaffold(self):
        tip = PipeProductLine.objects.get(code=LINE_TIP)
        self.assertTrue(tip.is_scaffold)
        self.assertEqual(PipeSizeProfile.objects.filter(line=tip).count(), 0)

    def test_scenario_runs(self):
        line = PipeProductLine.objects.get(code=LINE_PROTECT)
        profile = (
            PipeSizeProfile.objects.filter(line=line, size_mm=50)
            .prefetch_related("length_cuts", "layers")
            .first()
        )
        profile.stock_on_hand = 100
        profile.depot_ceiling = 500
        profile.save(update_fields=["stock_on_hand", "depot_ceiling"])
        length = profile.length_cuts.get(length_code="100cm_1s")
        scenario = run_scenario(
            profile=profile, length=length, pieces=50, voucher_qty=20
        )
        self.assertGreater(scenario.time.line.seconds, 0)
        self.assertGreater(scenario.time.billing.seconds, 0)
        self.assertEqual(scenario.depot.empty_space, 400)
        self.assertEqual(scenario.depot.empty_after_voucher, 420)
        self.assertTrue(scenario.layers)

    def test_aggregate_batch(self):
        line = PipeProductLine.objects.get(code=LINE_PROTECT)
        data = run_line_aggregate(
            line,
            [
                {"size_mm": 40, "length_code": "50cm_1s", "pieces": 10},
                {"size_mm": 110, "length_code": "200cm_1s", "pieces": 10},
            ],
        )
        self.assertEqual(data["aggregate"]["item_count"], 2)
        self.assertEqual(data["aggregate"]["pieces"], 20)
        self.assertEqual(len(data["details"]), 2)


class PipeCalcViewTests(TestCase):
    def setUp(self):
        seed_pipe_calc_defaults()
        self.user = User.objects.create_user("pipeuser", password="pass12345")
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"role": Role.PLANNING_MANAGER},
        )
        self.client = Client()
        self.client.login(username="pipeuser", password="pass12345")

    def test_hub_loads_protect(self):
        resp = self.client.get("/data/pipe-calc/?line=protect")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "لوله‌های پروتکت")
        self.assertContains(resp, "سایز لوله")
        self.assertContains(resp, "سقف دپو")
        self.assertContains(resp, "Ø110")
        self.assertNotContains(resp, "اسکلت")
        self.assertNotContains(resp, "بعداً تکمیل می‌شود")

    def test_matrix_run_endpoint(self):
        resp = self.client.post(
            "/data/pipe-calc/run/",
            data='{"line":"protect","size_mm":75,"mode":"matrix","qty_source":"deduct_stock"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        matrix = payload["matrix"]
        self.assertTrue(matrix["depot_rows"])
        self.assertEqual(matrix["depot_rows"][-1]["length_code"], "coupler")
        self.assertEqual(matrix["depot_rows"][-1]["label"], "رابط")
        self.assertIn("production", matrix)
        self.assertTrue(matrix["production"]["rows"])

    def test_run_endpoint_legacy_scenario(self):
        resp = self.client.post(
            "/data/pipe-calc/run/",
            {
                "line": "protect",
                "size_mm": "75",
                "length_code": "100cm_1s",
                "pieces": "25",
                "voucher_qty": "5",
            },
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertIn("time", payload["result"])
        self.assertIn("depot", payload["result"])
        self.assertGreater(payload["result"]["time"]["total"]["seconds"], 0)

    def test_tabs_and_title(self):
        resp = self.client.get("/data/pipe-calc/")
        self.assertContains(resp, "محاسبات زمان تولید")
        self.assertContains(resp, "لوله‌های جنرال سایلنت")
        self.assertContains(resp, "لوله‌های سایلنت ۱۰")
        self.assertContains(resp, "نوار آبیاری (تیپ)")
        self.assertContains(resp, "لوله فلت (PC)")
        self.assertNotContains(resp, "اسکلت")


class PipeCalcMatrixEngineTests(TestCase):
    def test_depot_matrix_row_math(self):
        from catalog.pipe_calc.engine import calc_depot_matrix_row

        row = calc_depot_matrix_row(
            length_code="100cm_1s",
            label="۱ متری",
            depot_ceiling=1000,
            stock=700,
            voucher=100,
            avg_monthly_sales=200,
        )
        self.assertEqual(row.remaining_after_voucher, 600)
        self.assertEqual(row.months_remaining, 3.0)
        self.assertEqual(row.depot_remaining_pct, 60.0)
        self.assertEqual(row.deduct_from_depot_stock, 300)
        self.assertEqual(row.deduct_from_depot_remaining, 400)
        self.assertEqual(row.required_qty, 300)
