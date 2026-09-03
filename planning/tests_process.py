"""Tests for configurable planning process stages."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from planning.models import PlanningProcessDefinition, PlanningProcessStep
from planning.process_data import ensure_default_processes


User = get_user_model()


class PlanningProcessStagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        ensure_default_processes(force=True)
        cls.admin = User.objects.get(username="admin")

    def test_seed_mto_has_numbered_decisions_with_yes_no(self):
        mto = PlanningProcessDefinition.objects.get(code="mto")
        self.assertGreaterEqual(mto.steps.count(), 20)
        inv = mto.steps.get(step_number=2)
        self.assertEqual(inv.kind, "decision")
        self.assertIn("انبار", inv.question)
        self.assertEqual(inv.yes_next_number, 3)
        self.assertEqual(inv.no_next_number, 5)
        self.assertEqual(inv.data_binding, "inventory_finished")
        yes_step = mto.steps.get(step_number=inv.yes_next_number)
        no_step = mto.steps.get(step_number=inv.no_next_number)
        self.assertTrue(yes_step.title)
        self.assertTrue(no_step.title)

    def test_system_data_links_to_process_list(self):
        self.client.login(username="admin", password="erp12345")
        hub = self.client.get(reverse("system_data"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "منطق فرآیند برنامه‌ریزی")
        self.assertContains(hub, reverse("planning_process_list"))

    def test_process_pages_and_redefine(self):
        self.client.login(username="admin", password="erp12345")
        listing = self.client.get(reverse("planning_process_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Make to Order")
        mto = PlanningProcessDefinition.objects.get(code="mto")
        detail = self.client.get(reverse("planning_process_detail", args=[mto.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "بله → مرحله")
        self.assertContains(detail, "اتصال به داده سیستم")
        # redefine: change yes target of step 2
        step = mto.steps.get(step_number=2)
        edit = self.client.post(
            reverse("planning_process_edit", args=[mto.pk]),
            {
                "action": "save",
                "process_title": mto.title,
                "process_description": mto.description,
                "entry_step_number": "1",
                f"step_{step.pk}_active": "1",
                f"step_{step.pk}_number": "2",
                f"step_{step.pk}_kind": "decision",
                f"step_{step.pk}_title": step.title,
                f"step_{step.pk}_question": step.question,
                f"step_{step.pk}_yes": "5",
                f"step_{step.pk}_no": "3",
                f"step_{step.pk}_next": "",
                f"step_{step.pk}_binding": "inventory_finished",
                f"step_{step.pk}_description": "",
            },
        )
        self.assertEqual(edit.status_code, 302)
        step.refresh_from_db()
        self.assertEqual(step.yes_next_number, 5)
        self.assertEqual(step.no_next_number, 3)

    def test_add_and_delete_step(self):
        self.client.login(username="admin", password="erp12345")
        mto = PlanningProcessDefinition.objects.get(code="mto")
        add = self.client.post(
            reverse("planning_process_edit", args=[mto.pk]),
            {
                "action": "add",
                "new_step_number": "900",
                "new_title": "مرحله آزمایشی",
                "new_kind": "action",
                "new_question": "",
                "new_binding": "orders",
            },
        )
        self.assertEqual(add.status_code, 302)
        step = PlanningProcessStep.objects.get(process=mto, step_number=900)
        delete = self.client.post(
            reverse("planning_process_edit", args=[mto.pk]),
            {"action": "delete", "step_id": str(step.pk)},
        )
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(
            PlanningProcessStep.objects.filter(process=mto, step_number=900).exists()
        )
