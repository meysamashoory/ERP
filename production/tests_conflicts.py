"""Unit tests for قالب تکراری / تقدم‌تاخر conflict rules."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from production.conflicts import (
    ConflictParty,
    _pair_duplicate_conflict,
    _pair_precedence_conflict,
    evaluate_duplicate_for_new_item,
)


User = get_user_model()


class ConflictRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")

    def test_duplicate_both_awaiting(self):
        a = ConflictParty(
            ref="a", kind="history", pk=1, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="P1", order_date=date(2026, 1, 1),
        )
        b = ConflictParty(
            ref="b", kind="history", pk=2, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="P2", order_date=date(2026, 1, 2),
        )
        self.assertTrue(_pair_duplicate_conflict(a, b))

    def test_duplicate_older_awaiting_newer_running(self):
        a = ConflictParty(
            ref="a", kind="history", pk=1, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="P1", order_date=date(2026, 1, 1),
        )
        b = ConflictParty(
            ref="b", kind="history", pk=2, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="running", plan_number="P2", order_date=date(2026, 1, 2),
        )
        self.assertTrue(_pair_duplicate_conflict(a, b))

    def test_duplicate_older_running_newer_awaiting_ok(self):
        older = ConflictParty(
            ref="r", kind="history", pk=1, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="running", plan_number="P1", order_date=date(2026, 1, 1),
        )
        newer = ConflictParty(
            ref="d", kind="history", pk=2, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="P2", order_date=date(2026, 1, 2),
        )
        self.assertFalse(_pair_duplicate_conflict(older, newer))

    def test_duplicate_different_mold_ok(self):
        a = ConflictParty(
            ref="a", kind="history", pk=1, unique_code="U1", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="P1", order_date=date(2026, 1, 1),
        )
        b = ConflictParty(
            ref="b", kind="history", pk=2, unique_code="U1", mold_key="id:9", mold_label="A",
            mold_id=9, status="awaiting", plan_number="P2", order_date=date(2026, 1, 2),
        )
        self.assertFalse(_pair_duplicate_conflict(a, b))

    def test_precedence_second_awaiting_ok(self):
        a = ConflictParty(
            ref="a", kind="live", pk=1, unique_code="A", mold_key="", mold_label="",
            mold_id=None, status="running", plan_number="1", machine_id=10,
            order_date=date(2026, 1, 1), product_code="A",
        )
        b = ConflictParty(
            ref="b", kind="live", pk=2, unique_code="B", mold_key="", mold_label="",
            mold_id=None, status="awaiting", plan_number="2", machine_id=10,
            order_date=date(2026, 1, 2), product_code="B",
        )
        self.assertFalse(_pair_precedence_conflict(a, b))

    def test_precedence_second_running_conflict(self):
        a = ConflictParty(
            ref="a", kind="live", pk=1, unique_code="A", mold_key="", mold_label="",
            mold_id=None, status="running", plan_number="1", machine_id=10,
            order_date=date(2026, 1, 1), product_code="A",
        )
        b = ConflictParty(
            ref="b", kind="live", pk=2, unique_code="B", mold_key="", mold_label="",
            mold_id=None, status="running", plan_number="2", machine_id=10,
            order_date=date(2026, 1, 2), product_code="B",
        )
        self.assertTrue(_pair_precedence_conflict(a, b))

    def test_evaluate_duplicate_occupying_blocks_awaiting_warns(self):
        from production.models import ProductionHistoryRecord

        ProductionHistoryRecord.objects.create(
            program_uid="dup-live-block-1",
            plan_number="PLAN-OCC",
            unique_code="CODE-LIVE-1",
            product_code="CODE-LIVE-1",
            product_name="تست",
            status="در حال تولید",
            actual_start_date=date(2026, 1, 1),
        )
        blocked = evaluate_duplicate_for_new_item(
            unique_code="CODE-LIVE-1",
            mold_id=None,
            plan_number="PLAN-NEW",
            plan_start=date(2026, 2, 1),
        )
        self.assertTrue(blocked["blocked"])

        ProductionHistoryRecord.objects.filter(program_uid="dup-live-block-1").delete()
        ProductionHistoryRecord.objects.create(
            program_uid="dup-live-warn-1",
            plan_number="PLAN-AWAIT",
            unique_code="CODE-LIVE-2",
            product_code="CODE-LIVE-2",
            product_name="تست۲",
            status="در انتظار تولید",
        )
        warned = evaluate_duplicate_for_new_item(
            unique_code="CODE-LIVE-2",
            mold_id=None,
            plan_number="PLAN-NEW2",
            plan_start=date(2026, 2, 1),
        )
        self.assertFalse(warned["blocked"])
        self.assertTrue(warned["warn"])

    def test_conflict_pages_manager_ok_viewer_denied(self):
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("production_conflicts"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "قالب تکراری")
        dup = self.client.get(reverse("production_conflicts_kind", args=["duplicate"]))
        self.assertEqual(dup.status_code, 200)
        prec = self.client.get(reverse("production_conflicts_kind", args=["precedence"]))
        self.assertEqual(prec.status_code, 200)

        viewer = User.objects.filter(profile__role="viewer").first()
        if viewer is None:
            return
        self.client.logout()
        self.client.force_login(viewer)
        denied = self.client.get(reverse("production_conflicts"))
        self.assertEqual(denied.status_code, 403)

    def test_delete_button_label_on_resolve_page(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("production_conflicts_kind", args=["duplicate"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "حذف از سوابق")
