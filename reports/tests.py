from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
import json

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
        self.assertContains(list_resp, "عنوان گزارش")
        self.assertContains(list_resp, "مدل گزارش")
        self.assertContains(list_resp, "نوع گزارش")
        self.assertContains(list_resp, "تعداد فرم")
        self.assertContains(list_resp, "+ ایجاد گزارش")
        self.assertNotContains(list_resp, "th-filter-btn")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "100- گزارش تست")
        self.assertContains(detail, "(توضیح نمونه)")
        self.assertContains(detail, ">ویرایش<")
        self.assertContains(detail, "خروجی")
        self.assertContains(detail, "موقعیت:")
        self.assertNotContains(detail, "قابل اصلاح")
        self.assertNotContains(detail, "ارسال گزارش برای کاربر دیگر")

        excel = self.client.get(reverse("report_detail", args=[report.pk]), {"export": "excel"})
        self.assertEqual(excel.status_code, 200)
        self.assertIn("spreadsheetml", excel["Content-Type"])

    def test_editable_data_entry_report_save(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.post(
            reverse("report_create"),
            {
                "title": "ثبت داده تست",
                "description": "",
                "number": 777,
                "access_mode": "editable",
                "columns_json": (
                    '[{"key":"data_titles","source":"data_entry","level":1,"label":"عناوین"},'
                    '{"key":"awaiting_production","source":"data_entry","level":1,"label":"انتظار"},'
                    '{"key":"running_production","source":"data_entry","level":1,"label":"در حال تولید"},'
                    '{"key":"entry_notes","source":"data_entry","level":1,"label":"توضیح"}]'
                ),
            },
        )
        self.assertEqual(resp.status_code, 302)
        report = SavedReport.objects.get(number=777, owner=self.expert)
        self.assertEqual(report.access_mode, "editable")
        self.assertEqual(report.data_source, "data_entry")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "report-edit-toggle")
        self.assertContains(detail, "اصلاح گزارش")
        self.assertNotContains(detail, "قابل اصلاح")
        self.assertContains(detail, "افزودن ردیف")
        self.assertContains(detail, 'id="entry-edit-actions" hidden')
        self.assertContains(detail, "برگه جدید")
        self.assertContains(detail, "موقعیت:")

        # Persist column uids used by the report for entry storage
        report.refresh_from_db()
        save = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {
                "action": "save_entry",
                "entry_payload": (
                    '{"rows":[{"data_titles":"زانو ۱۱۰",'
                    '"awaiting_production":"سرپیچ ۹۰",'
                    '"running_production":"زانو پروتکت ۱۱۰",'
                    '"entry_notes":"تستی"}]}'
                ),
            },
        )
        self.assertEqual(save.status_code, 302)
        report.refresh_from_db()
        self.assertIn("rows", report.entry_data)
        # Values may be under uid or legacy semantic key
        stored = report.entry_data["rows"][0]
        self.assertTrue(
            stored.get("data_titles") == "زانو ۱۱۰"
            or any(v == "زانو ۱۱۰" for v in stored.values())
        )
        after = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertContains(after, "زانو ۱۱۰")
        self.assertContains(after, "سرپیچ ۹۰")

    def test_awaiting_production_field_lists_awaiting_molds(self):
        from catalog.models import MoldOption
        from planning.models import WeeklyPlan, WeeklyPlanItem, Weekday
        from production.models import ProductionProgram
        import jdatetime

        mold = MoldOption.objects.filter(label="قالب اصلی").first()
        self.assertIsNotNone(mold)
        item = (
            WeeklyPlanItem.objects.filter(program__isnull=True)
            .select_related("product", "machine")
            .first()
        )
        if item is None:
            plan = WeeklyPlan.objects.filter(status=WeeklyPlan.Status.APPROVED).first()
            self.assertIsNotNone(plan)
            donor = WeeklyPlanItem.objects.select_related(
                "subgroup", "unit", "machine", "product"
            ).first()
            item = WeeklyPlanItem.objects.create(
                plan=plan,
                subgroup=donor.subgroup,
                unit=donor.unit,
                machine=donor.machine,
                product=donor.product,
                mold=mold,
                mold_change_weekday=Weekday.SHANBE,
                mold_change_date=jdatetime.date.today(),
                active_cavities=1,
                sequence=99,
            )
        else:
            item.mold = mold
            item.save(update_fields=["mold"])
        program = ProductionProgram.objects.create(
            item=item,
            status=ProductionProgram.Status.AWAITING,
        )
        self.assertEqual(program.status, ProductionProgram.Status.AWAITING)
        product_name = item.product.name

        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="قالب‌های در انتظار",
            number=778,
            access_mode="editable",
            data_source="data_entry",
            columns=[
                {"key": "awaiting_production", "source": "data_entry", "level": 1, "label": "انتظار"},
                {"key": "running_production", "source": "data_entry", "level": 1, "label": "در حال تولید"},
            ],
        )
        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "report-edit-toggle")
        meta = detail.context["entry_meta"]
        awaiting = next(m for m in meta if m.get("data_key") == "awaiting_production" or m["key"] == "awaiting_production")
        running = next(m for m in meta if m.get("data_key") == "running_production" or m["key"] == "running_production")
        self.assertEqual(awaiting["type"], "product_select")
        self.assertEqual(running["type"], "product_select")
        self.assertNotEqual(awaiting["key"], running["key"])
        self.assertTrue(any(product_name == (o.get("value") or "") for o in awaiting["options"]))
        # Options are product names only (no machine/mold details)
        for opt in awaiting["options"]:
            self.assertEqual(opt["label"], opt["value"])
            self.assertNotIn("(", opt["label"])

    def test_copied_entry_columns_are_independent(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="کپی ستون",
            number=779,
            access_mode="editable",
            data_source="data_entry",
            columns=[
                {"key": "awaiting_production", "source": "data_entry", "level": 1, "label": "انتظار ۱", "uid": "u1"},
                {"key": "awaiting_production", "source": "data_entry", "level": 1, "label": "انتظار ۲", "uid": "u2"},
            ],
        )
        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        meta = detail.context["entry_meta"]
        self.assertEqual(len(meta), 2)
        self.assertEqual(meta[0]["col_index"], 0)
        self.assertEqual(meta[1]["col_index"], 1)
        self.assertEqual(meta[0]["key"], "u1")
        self.assertEqual(meta[1]["key"], "u2")
        self.assertEqual(meta[0]["data_key"], "awaiting_production")
        save = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {
                "action": "save_entry",
                "entry_payload": '{"rows":[{"u1":"کالای الف","u2":"کالای ب"}]}',
            },
        )
        self.assertEqual(save.status_code, 302)
        after = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertContains(after, "کالای الف")
        self.assertContains(after, "کالای ب")
        rows = after.context["rows"]
        self.assertEqual(rows[0][0], "کالای الف")
        self.assertEqual(rows[0][1], "کالای ب")

    def test_form_print_fill_includes_report_entry_data(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="گزارش فرم",
            number=780,
            access_mode="editable",
            data_source="data_entry",
            columns=[
                {"key": "data_titles", "source": "data_entry", "level": 1, "label": "عنوان", "uid": "t1"},
            ],
            entry_data={"rows": [{"t1": "مقدار ثبت‌شده"}]},
        )
        form_obj = PrintForm.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="فرم گزارش",
            number=81,
            purpose="reports",
            linked_report=report,
            frames=[{
                "id": "f1", "kind": "field", "label": "عنوان",
                "left": 10, "x": 10, "y": 10, "width": 60, "height": 10,
                "source": "level_1", "source_key": "t1",
            }],
        )
        resp = self.client.get(
            reverse("print_form_print_fill", args=[form_obj.pk]),
            {"ctx": "report", "id": report.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "مقدار ثبت‌شده")

    def test_update_report_meta_inline(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="قدیم",
            description="قبل",
            number=781,
            data_source="data_entry",
            columns=[{"key": "data_titles", "source": "data_entry", "level": 1, "label": "عنوان"}],
        )
        resp = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {"action": "update_meta", "title": "تعویض قالب", "number": 10, "description": "به صورت دستی"},
        )
        self.assertEqual(resp.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.title, "تعویض قالب")
        self.assertEqual(report.number, 10)
        self.assertEqual(report.description, "به صورت دستی")
        self.assertEqual(report.heading_label, "10- تعویض قالب (به صورت دستی)")
        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertContains(detail, "10- تعویض قالب (به صورت دستی)")

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
            reverse("print_form_save_ajax_new"),
            {
                "title": "فرم کنترل",
                "description": "نسخه تست",
                "number": 1,
                "page_width_mm": 210,
                "page_height_mm": 297,
                "frames_json": '[{"id":"1","label":"عنوان","kind":"header","left":10,"x":10,"y":10,"width":190,"height":20}]',
                "page_settings_json": '{"margin_top":10,"margin_bottom":10,"margin_left":10,"margin_right":10,"show_grid":true,"show_ruler":true,"guides":[],"snap_mm":2}',
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        form_obj = PrintForm.objects.get(number=1, owner=self.expert)
        self.assertEqual(len(form_obj.frames), 1)
        list_resp = self.client.get(reverse("print_form_list"))
        self.assertContains(list_resp, "فرم کنترل")
        self.assertContains(list_resp, "+ ایجاد فرم")

    def test_viewer_cannot_create_form(self):
        self.client.login(username="viewer", password="erp12345")
        self.assertEqual(self.client.get(reverse("print_form_create")).status_code, 403)

    def test_create_form_opens_designer(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.get(reverse("print_form_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تکرار تا پایین صفحه")
        self.assertContains(resp, "تکرار وابسته به فیلد")
        self.assertContains(resp, "تعداد تکرار")
        self.assertContains(resp, "font-toolbar")
        self.assertContains(resp, "line-style-picker")
        self.assertContains(resp, "ضخیم")
        self.assertNotContains(resp, "امتداد دیتا")
        self.assertContains(resp, "لوگو")
        self.assertContains(resp, "حاشیه بالا")
        self.assertContains(resp, "designer-app")
        self.assertContains(resp, "Gridlines")
        self.assertContains(resp, "ردیف")
        self.assertContains(resp, "کلید منابع")
        self.assertContains(resp, "btn-copy")
        self.assertContains(resp, "btn-paste")
        self.assertContains(resp, "form_sheet_render.js")
        self.assertContains(resp, "کاربرد فرم")
        self.assertContains(resp, "برنامه ریزی هفتگی")
        self.assertNotContains(resp, "اسنپ به لبه‌ها")
        self.assertNotContains(resp, "وارد کردن فرم از اکسل")
        # No main app sidebar in designer window
        self.assertNotContains(resp, "خروج از سامانه")

    def test_form_detail_uses_sheet_renderer(self):
        self.client.login(username="expert", password="erp12345")
        form_obj = PrintForm.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="فرم مشاهده",
            number=77,
            frames=[{
                "id": "1", "kind": "box", "label": "کادر",
                "left": 10, "x": 10, "y": 10, "width": 80, "height": 20,
                "fill_colors": ["#ffffff", "#e8f0fe"],
                "border_styles": {"top": "solid", "right": "solid", "bottom": "dashed", "left": "solid"},
            }],
            page_settings={"margin_top": 10, "margin_bottom": 10, "margin_left": 10, "margin_right": 10},
        )
        resp = self.client.get(reverse("print_form_detail", args=[form_obj.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "form_sheet_render.js")
        self.assertContains(resp, "form-view-canvas")
        self.assertContains(resp, "fill_colors")

    def test_print_fill_repeats_each_plan_item(self):
        import jdatetime
        from catalog.models import Machine, Product, ProductionUnit
        from planning.models import Weekday, WeeklyPlan, WeeklyPlanItem

        self.client.login(username="expert", password="erp12345")
        unit = ProductionUnit.objects.get(number=1)
        machine = Machine.objects.filter(unit=unit).first()
        p1 = Product.objects.get(code="F-0900")
        p2 = Product.objects.get(code="F-1100")
        plan = WeeklyPlan.objects.create(
            program_number="BP-FILL",
            date=jdatetime.date(1405, 5, 24),
            status=WeeklyPlan.Status.DRAFT,
            created_by=self.expert,
        )
        WeeklyPlanItem.objects.create(
            plan=plan, subgroup=p1.subgroup, unit=unit, machine=machine,
            product=p1, mold_change_weekday=Weekday.SHANBE,
            mold_change_date=jdatetime.date(1405, 5, 24), active_cavities=4, sequence=1,
        )
        WeeklyPlanItem.objects.create(
            plan=plan, subgroup=p2.subgroup, unit=unit, machine=machine,
            product=p2, mold_change_weekday=Weekday.YEKSHANBE,
            mold_change_date=jdatetime.date(1405, 5, 25), active_cavities=1, sequence=2,
        )
        form_obj = PrintForm.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="فرم برنامه",
            number=78,
            purpose="weekly_plan",
            frames=[{
                "id": "f1", "kind": "field", "label": "نام محصول",
                "left": 10, "x": 10, "y": 10, "width": 60, "height": 10,
                "source": "weekly_plan", "source_key": "product_name",
            }, {
                "id": "b1", "kind": "box", "label": "کادر",
                "left": 5, "x": 5, "y": 10, "width": 100, "height": 10,
                "extend_mode": "field",
                "fill_colors": ["#ffffff", "#e8f0fe"],
                "border_styles": {"top": "solid", "right": "solid", "bottom": "solid", "left": "solid"},
            }],
        )
        resp = self.client.get(
            reverse("print_form_print_fill", args=[form_obj.pk]),
            {"ctx": "weekly_plan", "id": plan.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "fill-rows")
        self.assertContains(resp, p1.name)
        self.assertContains(resp, p2.name)
        self.assertContains(resp, "fillRows")

    def test_report_edit_shows_existing_columns(self):
        self.client.login(username="admin", password="erp12345")
        report = SavedReport.objects.filter(owner=self.admin).first()
        if report is None:
            report = SavedReport.objects.create(
                owner=self.admin,
                created_by=self.admin,
                title="تست ویرایش",
                number=88,
                columns=[{"key": "date", "source": "fitting", "level": 1, "label": "تاریخ"}],
            )
        resp = self.client.get(reverse("report_edit", args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, report.title)
        self.assertContains(resp, "نحوه نمایش")
        self.assertContains(resp, ">ویرایش<")
        self.assertNotContains(resp, "بالا = راست")

    def test_sidebar_labels(self):
        self.client.login(username="admin", password="erp12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "گزارشات")
        self.assertContains(resp, "گزارش‌ها")
        self.assertContains(resp, "فرم‌ها")
        self.assertContains(resp, "برنامه‌های تولید")
        self.assertContains(resp, "ثبت و کنترل تولید")
        self.assertContains(resp, "سوابق تولید")
        self.assertContains(resp, "بارگذاری")
        self.assertContains(resp, "کاربری سامانه")
        # Create actions moved off the sidebar onto list page tops
        self.assertNotContains(resp, "ایجاد گزارش")
        self.assertNotContains(resp, "ایجاد فرم")
        self.assertNotContains(resp, "مشاهده گزارش‌ها")
        self.assertNotContains(resp, "مشاهده فرم‌ها")

    def test_entry_sheets_save_and_flatten_in_view(self):
        from reports.columns import entry_sheet_count

        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="گزارش چندبرگه",
            number=790,
            access_mode="editable",
            data_source="data_entry",
            columns=[
                {"key": "data_titles", "source": "data_entry", "level": 1, "label": "عنوان", "uid": "s1"},
            ],
        )
        save = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {
                "action": "save_entry",
                "entry_payload": (
                    '{"sheet_count":2,"rows":['
                    '{"sheet":1,"s1":"ردیف برگه۱"},'
                    '{"sheet":2,"s1":"ردیف برگه۲"}'
                    "]}"
                ),
            },
        )
        self.assertEqual(save.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(entry_sheet_count(report.entry_data), 2)
        self.assertEqual(report.entry_data["rows"][0]["sheet"], 1)
        self.assertEqual(report.entry_data["rows"][1]["sheet"], 2)
        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        # View mode stacks all sheets without sheet labels
        self.assertContains(detail, "ردیف برگه۱")
        self.assertContains(detail, "ردیف برگه۲")
        # Separators are only injected in edit mode via JS
        self.assertEqual(detail.context["entry_sheet_count"], 2)
        self.assertEqual(detail.context["entry_row_sheets"], [1, 2])
        self.assertContains(detail, 'id="entry-sheet-toolbar" hidden')

        form_obj = PrintForm.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="فرم چندبرگه",
            number=91,
            purpose="reports",
            linked_report=report,
            frames=[
                {
                    "id": "f1", "kind": "field", "label": "عنوان", "sheet": 1,
                    "left": 10, "x": 10, "y": 10, "width": 60, "height": 10,
                    "source": "level_1", "source_key": "s1",
                },
                {
                    "id": "f2", "kind": "field", "label": "عنوان", "sheet": 2,
                    "left": 10, "x": 10, "y": 10, "width": 60, "height": 10,
                    "source": "level_1", "source_key": "s1",
                },
            ],
        )
        fill = self.client.get(
            reverse("print_form_print_fill", args=[form_obj.pk]),
            {"ctx": "report", "id": report.pk},
        )
        self.assertEqual(fill.status_code, 200)
        self.assertEqual(fill.context["sheet_count"], 2)
        self.assertContains(fill, "ردیف برگه۱")
        self.assertContains(fill, "ردیف برگه۲")
        self.assertContains(fill, "sheets-host")

    def test_form_save_preserves_frame_sheet_and_print_pages(self):
        """Saving via designer must keep sheet on frames so print shows all pages."""
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="گزارش برگه‌دار",
            number=791,
            access_mode="editable",
            data_source="data_entry",
            columns=[
                {"key": "data_titles", "source": "data_entry", "level": 1, "label": "عنوان", "uid": "u791"},
            ],
            entry_data={
                "sheet_count": 2,
                "rows": [
                    {"sheet": 1, "u791": "داده برگه۱"},
                    {"sheet": 2, "u791": "داده برگه۲"},
                ],
            },
        )
        frames_payload = [
            {
                "id": "h1", "kind": "header", "label": "سربرگ برگه۱", "sheet": 1,
                "left": 10, "x": 10, "y": 8, "width": 100, "height": 12,
                "font_family": "Tahoma", "font_size": 14, "font_bold": True,
            },
            {
                "id": "f1", "kind": "field", "label": "کلید۱", "sheet": 1,
                "left": 10, "x": 10, "y": 28, "width": 60, "height": 10,
                "source": "level_1", "source_key": "u791",
                "bindings": [{"source": "level_1", "source_key": "u791"}],
            },
            {
                "id": "h2", "kind": "header", "label": "سربرگ برگه۲", "sheet": 2,
                "left": 10, "x": 10, "y": 8, "width": 100, "height": 12,
            },
            {
                "id": "f2", "kind": "field", "label": "کلید۲", "sheet": 2,
                "left": 10, "x": 10, "y": 28, "width": 60, "height": 10,
                "source": "level_1", "source_key": "u791",
                "bindings": [{"source": "level_1", "source_key": "u791"}],
            },
        ]
        save = self.client.post(
            reverse("print_form_save_ajax_new"),
            {
                "title": "فرم دو برگه",
                "description": "",
                "number": 92,
                "purpose": "reports",
                "linked_report": report.pk,
                "page_width_mm": 210,
                "page_height_mm": 297,
                "frames_json": json.dumps(frames_payload, ensure_ascii=False),
                "page_settings_json": (
                    '{"margin_top":10,"margin_bottom":10,"margin_left":10,'
                    '"margin_right":10,"show_grid":true,"show_ruler":true,"guides":[],"snap_mm":2}'
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(save.status_code, 200)
        self.assertTrue(save.json().get("ok"))
        form_obj = PrintForm.objects.get(number=92, owner=self.expert)
        sheets = sorted({int(f.get("sheet") or 1) for f in form_obj.frames})
        self.assertEqual(sheets, [1, 2])
        header1 = next(f for f in form_obj.frames if f.get("id") == "h1")
        self.assertEqual(header1.get("sheet"), 1)
        self.assertEqual(header1.get("font_size"), 14)
        self.assertTrue(header1.get("font_bold"))
        header2 = next(f for f in form_obj.frames if f.get("id") == "h2")
        self.assertEqual(header2.get("sheet"), 2)

        fill = self.client.get(
            reverse("print_form_print_fill", args=[form_obj.pk]),
            {"ctx": "report", "id": report.pk},
        )
        self.assertEqual(fill.status_code, 200)
        self.assertEqual(fill.context["sheet_count"], 2)
        frames_out = json.loads(fill.context["frames_json"])
        self.assertEqual(
            sorted({int(f.get("sheet") or 1) for f in frames_out}),
            [1, 2],
        )
        fill_rows = json.loads(fill.context["fill_rows_json"])
        sheets_in_rows = sorted({int(r.get("_sheet") or 1) for r in fill_rows})
        self.assertEqual(sheets_in_rows, [1, 2])
        body = fill.content.decode()
        self.assertIn("سربرگ برگه۱", body)
        self.assertIn("سربرگ برگه۲", body)
        self.assertIn("داده برگه۱", body)
        self.assertIn("داده برگه۲", body)
        # Client script builds one canvas per sheet
        self.assertIn("for (var s = 1; s <= sheetCount; s++)", body)
