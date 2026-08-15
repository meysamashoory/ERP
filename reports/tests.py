from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

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
                "description": "توضیح نمونه",
                "number": 100,
                "columns_json": (
                    '[{"key":"date","source":"fitting","level":1,"label":"تاریخ"},'
                    '{"key":"product","source":"fitting","level":1,"label":"نام محصول"},'
                    '{"key":"produced","source":"fitting","level":2,"label":"تولید"}]'
                ),
            },
        )
        self.assertEqual(resp.status_code, 302)
        report = SavedReport.objects.get(number=100, owner=self.expert)
        self.assertEqual(report.title, "گزارش تست")
        self.assertEqual(report.description, "توضیح نمونه")
        self.assertEqual(len(report.columns), 3)

        list_resp = self.client.get(reverse("report_list"))
        self.assertContains(list_resp, "گزارش تست")
        self.assertContains(list_resp, "(توضیح نمونه)")
        self.assertNotContains(list_resp, "+ ایجاد گزارش")
        self.assertContains(list_resp, "list-desc")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "گزارش تست")
        self.assertContains(detail, "خروجی")
        self.assertNotContains(detail, "ارسال گزارش برای کاربر دیگر")

        excel = self.client.get(reverse("report_detail", args=[report.pk]), {"export": "excel"})
        self.assertEqual(excel.status_code, 200)
        self.assertIn("spreadsheetml", excel["Content-Type"])

    def test_send_duplicate_number_alerts(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            title="اصلی",
            number=200,
            data_source="product",
            columns=[{"key": "code", "source": "product", "level": 1}],
            created_by=self.expert,
        )
        SavedReport.objects.create(
            owner=self.admin,
            title="قبلی",
            number=200,
            data_source="product",
            columns=[{"key": "code", "source": "product", "level": 1}],
            created_by=self.admin,
        )
        resp = self.client.post(
            reverse("report_send", args=[report.pk]),
            {
                "recipient": self.admin.pk,
                "title": "ارسال‌شده",
                "number": 200,
                "description": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SavedReport.objects.filter(owner=self.admin, number=200).count(), 1)

    def test_send_and_copy(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            title="اصلی",
            number=300,
            data_source="product",
            columns=[{"key": "code", "source": "product", "level": 1}],
            created_by=self.expert,
        )
        resp = self.client.post(
            reverse("report_send", args=[report.pk]),
            {
                "recipient": self.admin.pk,
                "title": "کپی برای مدیر",
                "number": 301,
                "description": "ارسالی",
            },
        )
        self.assertEqual(resp.status_code, 302)
        copy = SavedReport.objects.get(owner=self.admin, number=301)
        self.assertEqual(copy.description, "ارسالی")

        resp2 = self.client.post(
            reverse("report_copy", args=[report.pk]),
            {"title": "کپی خودم", "number": 302, "description": ""},
        )
        self.assertEqual(resp2.status_code, 302)
        self.assertTrue(SavedReport.objects.filter(owner=self.expert, number=302).exists())

        self.client.post(reverse("report_delete", args=[report.pk]))
        self.assertFalse(SavedReport.objects.filter(pk=report.pk).exists())
        self.assertTrue(SavedReport.objects.filter(pk=copy.pk).exists())

    def test_standard_report_visible_to_all_only_manager_deletes(self):
        std = SavedReport.objects.create(
            owner=self.admin,
            title="استاندارد تولید",
            number=1,
            data_source="fitting",
            columns=[{"key": "date", "source": "fitting", "level": 1}],
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

    def test_list_sorted_by_number(self):
        self.client.login(username="expert", password="erp12345")
        SavedReport.objects.create(
            owner=self.expert, title="دوم", number=20, data_source="product",
            columns=[{"key": "code", "source": "product", "level": 1}], created_by=self.expert,
        )
        SavedReport.objects.create(
            owner=self.expert, title="اول", number=5, data_source="product",
            columns=[{"key": "code", "source": "product", "level": 1}], created_by=self.expert,
        )
        resp = self.client.get(reverse("report_list"))
        body = resp.content.decode()
        self.assertLess(body.index(">5<"), body.index(">20<"))


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
                "description": "نسخه تست",
                "number": 1,
                "page_width_mm": 210,
                "page_height_mm": 297,
                "frames_json": '[{"id":"1","label":"عنوان","kind":"header","x":10,"y":10,"width":190,"height":20}]',
            },
        )
        self.assertEqual(resp.status_code, 302)
        form_obj = PrintForm.objects.get(number=1, owner=self.expert)
        self.assertEqual(len(form_obj.frames), 1)
        list_resp = self.client.get(reverse("print_form_list"))
        self.assertContains(list_resp, "فرم کنترل")
        self.assertNotContains(list_resp, "+ ایجاد فرم")

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
