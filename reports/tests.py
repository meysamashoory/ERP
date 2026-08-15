from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from reports.models import PrintForm, SavedReport

User = get_user_model()


class ReportFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")
        cls.expert = User.objects.get(username="expert")
        cls.viewer = User.objects.get(username="viewer")

    def test_viewer_cannot_create_report(self):
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("report_create")).status_code, 403)

    def test_expert_can_create_and_list_report(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.post(
            reverse("report_create"),
            {
                "title": "گزارش تست",
                "number": "R-100",
                "data_source": "fitting",
                "columns": ["date", "product", "stock_finished"],
            },
        )
        self.assertEqual(resp.status_code, 302)
        report = SavedReport.objects.get(number="R-100", owner=self.expert)
        self.assertEqual(report.title, "گزارش تست")

        list_resp = self.client.get(reverse("report_list"))
        self.assertContains(list_resp, "گزارش تست")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "گزارش تست")

        excel = self.client.get(reverse("report_detail", args=[report.pk]), {"export": "excel"})
        self.assertEqual(excel.status_code, 200)
        self.assertIn(
            "spreadsheetml",
            excel["Content-Type"],
        )

    def test_send_duplicate_number_alerts(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            title="اصلی",
            number="R-200",
            data_source="product",
            columns=["code", "stock_finished"],
            created_by=self.expert,
        )
        SavedReport.objects.create(
            owner=self.admin,
            title="قبلی",
            number="R-200",
            data_source="product",
            columns=["code"],
            created_by=self.admin,
        )
        resp = self.client.post(
            reverse("report_send", args=[report.pk]),
            {
                "recipient": self.admin.pk,
                "title": "ارسال‌شده",
                "number": "R-200",
                "sent_at": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        # Still only one for admin with that number.
        self.assertEqual(SavedReport.objects.filter(owner=self.admin, number="R-200").count(), 1)

    def test_send_creates_recipient_copy(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            title="اصلی",
            number="R-300",
            data_source="product",
            columns=["code", "product"],
            created_by=self.expert,
        )
        resp = self.client.post(
            reverse("report_send", args=[report.pk]),
            {
                "recipient": self.admin.pk,
                "title": "کپی برای مدیر",
                "number": "R-301",
                "sent_at": "1405/05/20",
            },
        )
        self.assertEqual(resp.status_code, 302)
        copy = SavedReport.objects.get(owner=self.admin, number="R-301")
        self.assertEqual(copy.title, "کپی برای مدیر")
        self.assertEqual(copy.source_report_id, report.pk)
        # Deleting own copy does not delete the other.
        self.client.post(reverse("report_delete", args=[report.pk]))
        self.assertFalse(SavedReport.objects.filter(pk=report.pk).exists())
        self.assertTrue(SavedReport.objects.filter(pk=copy.pk).exists())

    def test_standard_report_visible_to_all_only_manager_deletes(self):
        std = SavedReport.objects.create(
            owner=self.admin,
            title="استاندارد تولید",
            number="STD-1",
            data_source="fitting",
            columns=["date", "produced"],
            is_standard=True,
            created_by=self.admin,
        )
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("report_detail", args=[std.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("report_delete", args=[std.pk])).status_code, 403)

        self.client.login(username="expert", password="erp12345")
        self.assertEqual(self.client.post(reverse("report_delete", args=[std.pk])).status_code, 403)

        self.client.login(username="admin", password="erp12345")
        self.assertEqual(self.client.post(reverse("report_delete", args=[std.pk])).status_code, 302)
        self.assertFalse(SavedReport.objects.filter(pk=std.pk).exists())


class PrintFormFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")
        cls.expert = User.objects.get(username="expert")

    def test_create_form_with_frames(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.post(
            reverse("print_form_create"),
            {
                "title": "فرم کنترل",
                "number": "F-1",
                "page_width_mm": 210,
                "page_height_mm": 297,
                "frames_json": '[{"id":"1","label":"عنوان","kind":"header","x":10,"y":10,"width":190,"height":20}]',
            },
        )
        self.assertEqual(resp.status_code, 302)
        form_obj = PrintForm.objects.get(number="F-1", owner=self.expert)
        self.assertEqual(len(form_obj.frames), 1)
        self.assertContains(self.client.get(reverse("print_form_list")), "فرم کنترل")

    def test_viewer_cannot_create_form(self):
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("print_form_create")).status_code, 403)

    def test_sidebar_labels(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "گزارش‌ها")
        self.assertContains(resp, "مشاهده گزارش‌ها")
        self.assertContains(resp, "ایجاد گزارش")
        self.assertContains(resp, "فرم‌ها")
        self.assertContains(resp, "مشاهده فرم‌ها")
        self.assertContains(resp, "ایجاد فرم")
