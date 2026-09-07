from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from reports.conditions import (
    compact_jalali_day,
    field_param_kinds,
    infer_field_param_kind,
    jalali_year_value,
    list_parameters_for_field,
    row_matches_conditions,
    seed_default_parameters,
    _cmp,
)
from reports.models import PrintForm, ReportParameterDef, SavedReport

User = get_user_model()


class CompactJalaliCompareTests(SimpleTestCase):
    def test_slash_and_compact_are_equal(self):
        self.assertEqual(compact_jalali_day("1405/07/16"), 14050716)
        self.assertEqual(compact_jalali_day("14050716"), 14050716)
        self.assertTrue(_cmp("1405/07/16", "=", "14050716", kind="day_date"))

    def test_greater_or_equal_includes_same_day_and_later(self):
        self.assertTrue(_cmp("1405/07/16", ">=", "14050716", kind="day_date"))
        self.assertTrue(_cmp("1405/07/17", ">=", "14050716", kind="day_date"))
        self.assertFalse(_cmp("1405/07/15", ">=", "14050716", kind="day_date"))

    def test_year_compares_solar_year_only(self):
        self.assertEqual(jalali_year_value("1405/07/16"), 1405)
        self.assertTrue(_cmp("1405/01/01", ">=", "1405", kind="year"))
        self.assertTrue(_cmp("1406/01/01", ">=", "1405", kind="year"))
        self.assertFalse(_cmp("1404/12/29", ">=", "1405", kind="year"))


class ParameterKindMappingTests(SimpleTestCase):
    def test_date_fields_accept_day_and_year(self):
        self.assertEqual(infer_field_param_kind("planning_date"), "day_date")
        self.assertEqual(
            field_param_kinds("date"),
            {"day_date", "year"},
        )

    def test_identity_fields(self):
        self.assertEqual(infer_field_param_kind("code"), "product_code")
        self.assertEqual(infer_field_param_kind("unique_code"), "unique_code")
        self.assertEqual(infer_field_param_kind("mold_number"), "mold_number")
        self.assertEqual(
            infer_field_param_kind("v1", label="شماره حواله", source="flex__product_data__vouchers"),
            "voucher_number",
        )


class ParameterRuntimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")
        cls.expert = User.objects.get(username="expert")

    def test_seed_uses_new_kinds_and_unique_code(self):
        seed_default_parameters()
        today = ReportParameterDef.objects.get(code="date_today")
        self.assertEqual(today.kind, ReportParameterDef.KIND_DAY_DATE)
        self.assertEqual(today.sample_value, "14050101")
        self.assertFalse(ReportParameterDef.objects.filter(kind="number", is_active=True).exists())

    def test_source_scoped_parameter_hidden_on_other_sources(self):
        ReportParameterDef.objects.create(
            code="fit_only_date",
            label="تاریخ تزریق",
            kind=ReportParameterDef.KIND_DAY_DATE,
            source_key="fitting",
            is_active=True,
        )
        fitting = list_parameters_for_field("date", source="fitting")
        weekly = list_parameters_for_field("planning_date", source="weekly_planning")
        self.assertTrue(any(p["code"] == "fit_only_date" for p in fitting))
        self.assertFalse(any(p["code"] == "fit_only_date" for p in weekly))

    def test_date_kind_appears_on_all_date_fields(self):
        codes = {p["code"] for p in list_parameters_for_field("planning_date", source="weekly_planning")}
        self.assertIn("date_today", codes)
        year_codes = {p["code"] for p in list_parameters_for_field("start_date", source="weekly_planning")}
        self.assertIn("date_today", year_codes)

    def test_row_match_compact_date_gte(self):
        rows = [
            {
                "logic": "",
                "source": "fitting",
                "field": "date",
                "op": ">=",
                "value_mode": "parameter",
                "param_code": "date_today",
            }
        ]
        self.assertTrue(
            row_matches_conditions({"date": "1405/07/16"}, rows, {"date_today": "14050716"})
        )
        self.assertFalse(
            row_matches_conditions({"date": "1405/07/15"}, rows, {"date_today": "14050716"})
        )


class SystemAdminFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.admin = User.objects.get(username="admin")

    def setUp(self):
        self.client.login(username="admin", password="erp12345")

    def test_print_form_change_hides_requested_fields_and_related_icons(self):
        form = PrintForm.objects.create(
            owner=self.admin,
            created_by=self.admin,
            title="فرم نمونه",
            number=3,
        )
        url = reverse("admin:reports_printform_change", args=[form.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "مالک")
        self.assertContains(page, "عنوان فرم")
        self.assertContains(page, "کاربران مجاز")
        self.assertNotContains(page, "کاربرد فرم")
        self.assertNotContains(page, "گزارش مرتبط")
        self.assertNotContains(page, "زمان ارسال")
        self.assertNotContains(page, "related-widget-wrapper-link")
        html = page.content.decode()
        self.assertNotIn('name="created_by"', html)
        self.assertContains(page, "ایجادکننده")

    def test_print_form_created_by_not_changed_by_admin_post(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from reports.admin import PrintFormAdmin

        other = User.objects.create_user("other_admin", password="erp12345")
        form = PrintForm.objects.create(
            owner=self.admin,
            created_by=self.admin,
            title="فرم قفل",
            number=4,
        )
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        obj = PrintForm.objects.get(pk=form.pk)
        obj.created_by = other
        PrintFormAdmin(PrintForm, site).save_model(request, obj, form=None, change=True)
        form.refresh_from_db()
        self.assertEqual(form.created_by_id, self.admin.pk)

    def test_saved_report_change_hides_source_and_sent(self):
        report = SavedReport.objects.create(
            owner=self.admin,
            created_by=self.admin,
            title="گزارش نمونه",
            number=9,
        )
        url = reverse("admin:reports_savedreport_change", args=[report.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "مالک")
        self.assertContains(page, "عنوان گزارش")
        self.assertNotContains(page, "گزارش مبدأ")
        self.assertNotContains(page, "زمان ارسال")
        self.assertNotContains(page, "related-widget-wrapper-link")
        self.assertNotIn('name="created_by"', page.content.decode())

    def test_parameter_admin_unique_and_new_kinds(self):
        add = reverse("admin:reports_reportparameterdef_add")
        page = self.client.get(add)
        self.assertContains(page, "کد پارامتر")
        self.assertContains(page, "فیلد منابع")
        self.assertContains(page, "مقدار پیش‌فرض")
        self.assertContains(page, "تاریخ روز")
        self.assertContains(page, "شماره حواله")
        self.assertContains(page, "همه منابع")

        dup = self.client.post(
            add,
            {
                "code": "date_today",
                "label": "تکراری",
                "kind": "day_date",
                "source_key": "",
                "sample_value": "14050716",
                "is_active": "on",
                "order": 10,
            },
        )
        self.assertEqual(dup.status_code, 200)
        self.assertContains(dup, "یکتا")

    def test_apply_params_updates_default_value(self):
        report = SavedReport.objects.create(
            owner=self.admin,
            created_by=self.admin,
            title="پارامتر پیش‌فرض",
            number=88,
            columns=[{"key": "date", "source": "fitting", "level": 1, "label": "تاریخ", "uid": "c1"}],
            conditions={
                "public": [
                    {
                        "logic": "",
                        "source": "fitting",
                        "field": "date",
                        "op": ">=",
                        "value_mode": "parameter",
                        "param_code": "date_today",
                    }
                ],
                "private": {},
            },
        )
        self.client.login(username="expert", password="erp12345")
        # expert may not own this report — use admin
        self.client.login(username="admin", password="erp12345")
        resp = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {"action": "apply_params", "param_date_today": "14050716"},
        )
        self.assertEqual(resp.status_code, 200)
        today = ReportParameterDef.objects.get(code="date_today")
        self.assertEqual(today.sample_value, "14050716")
