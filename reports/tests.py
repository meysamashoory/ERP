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
        self.assertEqual(self.client.post(reverse("report_create"), {"title": "x", "number": 1}).status_code, 403)

    def test_expert_can_create_and_list_report(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.post(
            reverse("report_create"),
            {
                "title": "گزارش تست",
                "description": "توضیح نمونه",
                "number": 100,
                "columns_json": (
                    '[{"key":"date","source":"fitting","level":1,"label":"تاریخ","is_key":true},'
                    '{"key":"product","source":"fitting","level":1,"label":"نام محصول"},'
                    '{"key":"code","source":"fitting","level":2,"label":"کد","is_key":true},'
                    '{"key":"produced","source":"fitting","level":2,"label":"تولید"}]'
                ),
            },
        )
        self.assertEqual(resp.status_code, 200)
        report = SavedReport.objects.get(number=100, owner=self.expert)
        self.assertEqual(report.title, "گزارش تست")
        self.assertEqual(report.description, "توضیح نمونه")
        self.assertEqual(len(report.columns), 4)
        self.assertContains(resp, "گزارش ذخیره شد")
        self.assertContains(resp, "در حال بستن پنجره")

        list_resp = self.client.get(reverse("report_list"))
        self.assertContains(list_resp, "گزارش تست")
        self.assertContains(list_resp, "عنوان گزارش")
        self.assertContains(list_resp, "مدل گزارش")
        self.assertContains(list_resp, "نوع گزارش")
        self.assertContains(list_resp, "تعداد فرم")
        self.assertContains(list_resp, "+ ایجاد گزارش")
        self.assertContains(list_resp, "لیست گزارش‌ها")
        self.assertContains(list_resp, 'data-lock-widths="1"')
        self.assertContains(list_resp, "btn-create-report")
        self.assertContains(list_resp, "tpl-create")
        self.assertNotContains(list_resp, "th-filter-btn")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "100- گزارش تست")
        self.assertContains(detail, "(توضیح نمونه)")
        self.assertNotContains(detail, 'id="rp-edit-link"')
        self.assertContains(detail, "خروجی")
        self.assertContains(detail, "موقعیت:")
        self.assertNotContains(detail, "قابل اصلاح")
        self.assertNotContains(detail, "ارسال گزارش برای کاربر دیگر")

        excel = self.client.get(reverse("report_detail", args=[report.pk]), {"export": "excel"})
        self.assertEqual(excel.status_code, 200)
        self.assertIn("spreadsheetml", excel["Content-Type"])

    def test_create_report_rejects_empty_columns_and_prefills_meta_from_query(self):
        self.client.login(username="expert", password="erp12345")
        resp = self.client.post(
            reverse("report_create"),
            {
                "title": "گزارش دیالوگ",
                "description": "",
                "number": "05",
                "access_mode": "readonly",
                "columns_json": "[]",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            SavedReport.objects.filter(title="گزارش دیالوگ", owner=self.expert).exists()
        )
        self.assertContains(resp, "حداقل یک ستون انتخاب کنید.")

        get_create = self.client.get(
            reverse("report_create"),
            {"title": "گزارش دیالوگ", "number": "05", "access_mode": "readonly"},
        )
        self.assertEqual(get_create.status_code, 200)
        self.assertContains(get_create, "گزارش جدید")
        self.assertContains(get_create, "report-builder-form")
        self.assertContains(get_create, 'value="گزارش دیالوگ"')
        self.assertContains(get_create, 'value="5"')
        self.assertContains(get_create, "metaConfirmed: true")

    def test_report_sources_include_history_not_excel(self):
        from reports.columns import get_column_groups, run_report

        ids = [g["id"] for g in get_column_groups()]
        self.assertIn("history", ids)
        self.assertIn("data_entry", ids)
        self.assertTrue(all(not str(i).startswith("excel_table_") for i in ids))

        headers, rows, _p, _d = run_report(
            "history",
            [{"key": "plan_number", "source": "history", "level": 1, "label": "شماره برنامه"}],
        )
        self.assertEqual(headers, ["شماره برنامه"])
        self.assertIsInstance(rows, list)

    def test_builder_filters_sources_by_access_mode_in_script(self):
        """Readonly hides data_entry; editable keeps only data_entry (client filter)."""
        self.client.login(username="expert", password="erp12345")
        readonly = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="فقط خواندنی",
            number=801,
            access_mode="readonly",
            data_source="fitting",
            columns=[{"key": "date", "source": "fitting", "level": 1, "label": "تاریخ"}],
        )
        editable = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="قابل اصلاح",
            number=802,
            access_mode="editable",
            data_source="data_entry",
            columns=[{"key": "data_titles", "source": "data_entry", "level": 1, "label": "عناوین"}],
        )
        ro = self.client.get(reverse("report_edit", args=[readonly.pk]))
        ed = self.client.get(reverse("report_edit", args=[editable.pk]))
        self.assertEqual(ro.status_code, 200)
        self.assertEqual(ed.status_code, 200)
        self.assertContains(ro, "report_builder_display.js")
        self.assertContains(ro, "ERPReportBuilderDisplay")
        self.assertContains(ed, 'id="id_access_mode"')
        # Logic lives in static JS; verify file still enforces access-mode source filter.
        from pathlib import Path

        js = Path("static/js/report_builder_display.js").read_text(encoding="utf-8")
        self.assertIn("sourceAllowedForAccess", js)
        self.assertIn('m === "editable"', js)
        self.assertIn('return sourceId === "data_entry"', js)
        self.assertIn('return sourceId !== "data_entry"', js)
        # access mode values present in both forms
        self.assertContains(ro, 'value="readonly"')
        self.assertContains(ed, 'value="editable"')

    def test_flex_product_data_source_from_transferred_rows(self):
        from catalog.models import FlexibleDataset, FlexibleRow
        from reports.columns import flex_source_id, get_column_groups, run_report

        ds = FlexibleDataset.objects.create(
            destination_id="product_data",
            level_id="products",
            title="محصولات",
            columns=[
                {"key": "code", "label": "کد کالا"},
                {"key": "name", "label": "نام"},
            ],
        )
        FlexibleRow.objects.create(
            dataset=ds, order=0, identity_key="A1", values={"code": "A1", "name": "کالا ۱"}
        )
        FlexibleRow.objects.create(
            dataset=ds, order=1, identity_key="B2", values={"code": "B2", "name": "کالا ۲"}
        )
        source = flex_source_id("product_data", "products")
        ids = [g["id"] for g in get_column_groups()]
        self.assertIn(source, ids)
        headers, rows, _p, _d = run_report(
            source,
            [
                {"key": "code", "source": source, "level": 1, "label": "کد کالا"},
                {"key": "name", "source": source, "level": 1, "label": "نام"},
            ],
        )
        self.assertEqual(headers, ["کد کالا", "نام"])
        self.assertEqual(rows, [["A1", "کالا ۱"], ["B2", "کالا ۲"]])

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
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "گزارش ذخیره شد")
        report = SavedReport.objects.get(number=777, owner=self.expert)
        self.assertEqual(report.access_mode, "editable")
        self.assertEqual(report.data_source, "data_entry")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "report-edit-toggle")
        self.assertContains(detail, "اصلاح گزارش")
        self.assertNotContains(detail, "قابل اصلاح")
        self.assertContains(detail, "افزودن ردیف")
        self.assertContains(detail, 'id="entry-edit-actions"')
        self.assertNotContains(detail, 'id="entry-edit-actions" hidden')
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
        self.assertContains(resp, "ثبت گزارش")
        self.assertNotContains(resp, 'id="edit-meta-btn"')
        self.assertContains(resp, "برای ویرایش اطلاعات گزارش کلیک کنید")
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
        self.assertContains(resp, "بارگذاری فایل")
        self.assertContains(resp, "مدیریت داده‌های سامانه")
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
        self.assertContains(detail, 'id="add-entry-sheet"')

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


class ReportColumnKeyAndWidthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.expert = User.objects.get(username="expert")

    def test_numeric_cannot_be_key_and_multilevel_requires_keys(self):
        from reports.columns import column_can_be_key, normalize_columns, validate_report_level_keys

        self.assertFalse(column_can_be_key("fitting", "produced"))
        self.assertTrue(column_can_be_key("fitting", "code"))
        cols = normalize_columns(
            [
                {"key": "produced", "source": "fitting", "level": 1, "is_key": True},
                {"key": "code", "source": "fitting", "level": 2, "is_key": True},
            ]
        )
        self.assertFalse(cols[0]["is_key"])
        self.assertTrue(cols[1]["is_key"])
        errs = validate_report_level_keys(
            [
                {"key": "code", "source": "fitting", "level": 1, "is_key": True},
                {"key": "product", "source": "fitting", "level": 2, "is_key": False},
            ]
        )
        self.assertTrue(any("سطح 2" in e for e in errs))

    def test_edit_rejects_multilevel_without_keys(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="چندسطحی",
            number=311,
            data_source="fitting",
            columns=[
                {"key": "code", "source": "fitting", "level": 1, "label": "کد"},
                {"key": "product", "source": "fitting", "level": 2, "label": "نام"},
            ],
        )
        resp = self.client.post(
            reverse("report_edit", args=[report.pk]),
            {
                "title": "چندسطحی",
                "number": 311,
                "description": "",
                "access_mode": "readonly",
                "columns_json": json.dumps(
                    [
                        {"key": "code", "source": "fitting", "level": 1, "label": "کد"},
                        {"key": "product", "source": "fitting", "level": 2, "label": "نام"},
                    ],
                    ensure_ascii=False,
                ),
                "source_links_json": "[]",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "حداقل یک ستون کلید")

    def test_width_and_key_persist_on_save(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="عرض",
            number=312,
            data_source="fitting",
            columns=[],
        )
        resp = self.client.post(
            reverse("report_edit", args=[report.pk]),
            {
                "title": "عرض",
                "number": 312,
                "description": "",
                "access_mode": "readonly",
                "columns_json": json.dumps(
                    [
                        {
                            "key": "code",
                            "source": "fitting",
                            "level": 1,
                            "label": "کد",
                            "is_key": True,
                            "width": 140,
                        },
                        {
                            "key": "product",
                            "source": "fitting",
                            "level": 1,
                            "label": "نام",
                            "width": 200,
                        },
                    ],
                    ensure_ascii=False,
                ),
                "source_links_json": "[]",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "گزارش ذخیره شد")
        report.refresh_from_db()
        by_key = {c["key"]: c for c in report.columns}
        self.assertTrue(by_key["code"]["is_key"])
        self.assertEqual(by_key["code"]["width"], 140)
        self.assertEqual(by_key["product"]["width"], 200)

    def test_drill_uses_key_columns_only(self):
        from reports.columns import run_report

        columns = [
            {"key": "code", "source": "product", "level": 1, "label": "کد", "is_key": True, "uid": "c1"},
            {"key": "product", "source": "product", "level": 1, "label": "نام", "uid": "c2"},
            {"key": "stock_finished", "source": "product", "level": 2, "label": "موجودی", "is_key": True, "uid": "c3"},
        ]
        # stock_finished is numeric — normalize would strip is_key; use code at level2 for key
        columns[2] = {
            "key": "code",
            "source": "product",
            "level": 2,
            "label": "کد2",
            "is_key": True,
            "uid": "c3",
        }
        headers, rows, payloads, deeper = run_report("product", columns, level=1)
        self.assertTrue(deeper)
        self.assertTrue(payloads)
        self.assertIn("_drill_keys", payloads[0])
        self.assertIn("c1", payloads[0]["_drill_keys"])
        self.assertNotIn("c2", payloads[0]["_drill_keys"])



class ColumnDisplayPropsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_demo")

    def test_level_labels_use_ordinals(self):
        from reports.columns import LEVEL_MODE_CHOICES
        labels = dict(LEVEL_MODE_CHOICES)
        self.assertEqual(labels["1"], "اول")
        self.assertEqual(labels["9"], "نهم")
        self.assertEqual(labels["upto_2"], "تا دوم")
        self.assertEqual(labels["upto_8"], "تا هشتم")
        self.assertEqual(labels["all"], "همه سطوح")

    def test_hidden_column_excluded_from_display_but_sortable(self):
        from reports.columns import normalize_columns, run_report, level_display_meta
        from reports.formula import to_number

        cols = normalize_columns([
            {
                "key": "code", "source": "product", "label": "کد",
                "level_mode": "all", "is_key": True, "sort_priority": 2,
            },
            {
                "key": "stock_finished", "source": "product", "label": "موجودی",
                "level_mode": "all", "sort_priority": 1, "sort_asc": False,
                "number_format": "#,##0", "cell_align": "center",
            },
            {
                "key": "file_stock", "source": "product", "label": "فایل",
                "level_mode": "all", "sort_priority": 9, "is_hidden": True,
                "props_level_mode": "all",
            },
        ])
        meta = level_display_meta(cols, 1)
        self.assertEqual([m["label"] for m in meta], ["کد", "موجودی"])
        self.assertEqual(meta[1]["cell_align"], "center")
        headers, rows, _payloads, _deeper = run_report("product", cols, level=1)
        self.assertEqual(headers, ["کد", "موجودی"])
        self.assertTrue(rows)
        self.assertEqual(len(rows[0]), 2)
        first = to_number(str(rows[0][1]).replace(",", ""))
        last = to_number(str(rows[-1][1]).replace(",", ""))
        self.assertGreaterEqual(first, last)

    def test_same_priority_prefers_rightmost_column(self):
        from reports.columns import _sort_report_rows

        level_cols = [
            {"sort_priority": 1, "sort_asc": True, "label": "R"},
            {"sort_priority": 1, "sort_asc": True, "label": "L"},
        ]
        rows = [["b", "a"], ["a", "b"]]
        payloads = [{}, {}]
        sorted_rows, _ = _sort_report_rows(level_cols, rows, payloads)
        self.assertEqual(sorted_rows[0], ["a", "b"])
        self.assertEqual(sorted_rows[1], ["b", "a"])

    def test_clamp_sort_priority_allows_zero(self):
        from reports.columns import clamp_sort_priority

        self.assertEqual(clamp_sort_priority(None), 0)
        self.assertEqual(clamp_sort_priority(""), 0)
        self.assertEqual(clamp_sort_priority(0), 0)
        self.assertEqual(clamp_sort_priority("0"), 0)
        self.assertEqual(clamp_sort_priority(3), 3)
        self.assertEqual(clamp_sort_priority(10), 9)

    def test_all_zero_priority_sorts_from_right(self):
        from reports.columns import _sort_report_rows

        level_cols = [
            {"sort_priority": 0, "sort_asc": True, "label": "R"},
            {"sort_priority": 0, "sort_asc": True, "label": "L"},
        ]
        rows = [["b", "a"], ["a", "b"]]
        sorted_rows, _ = _sort_report_rows(level_cols, rows, [{}, {}])
        self.assertEqual(sorted_rows[0], ["a", "b"])
        self.assertEqual(sorted_rows[1], ["b", "a"])

    def test_mixed_zero_uses_only_prioritized_columns(self):
        from reports.columns import _sort_report_rows

        level_cols = [
            {"sort_priority": 0, "sort_asc": True, "label": "R"},
            {"sort_priority": 1, "sort_asc": True, "label": "L"},
        ]
        rows = [["z", "a"], ["a", "b"]]
        sorted_rows, _ = _sort_report_rows(level_cols, rows, [{}, {}])
        self.assertEqual(sorted_rows[0], ["z", "a"])
        self.assertEqual(sorted_rows[1], ["a", "b"])


class ReportDefaultColumnWidthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_demo")

    def test_type_defaults_and_naming_override(self):
        from catalog.models import SystemNamingKey
        from catalog.naming_registry import sync_naming_registry
        from reports.columns import (
            DEFAULT_WIDTH_BY_KIND,
            get_column_groups,
            resolve_default_column_width,
        )

        sync_naming_registry()
        self.assertEqual(
            resolve_default_column_width("fitting", "produced"),
            DEFAULT_WIDTH_BY_KIND["number"],
        )
        self.assertEqual(
            resolve_default_column_width("fitting", "product"),
            DEFAULT_WIDTH_BY_KIND["text"],
        )
        row = SystemNamingKey.objects.get(key="report.col.fitting.product")
        row.default_width_px = 240
        row.save(update_fields=["default_width_px"])
        self.assertEqual(resolve_default_column_width("fitting", "product"), 240)
        groups = get_column_groups()
        fitting = next(g for g in groups if g["id"] == "fitting")
        self.assertEqual(fitting["default_widths"]["product"], 240)
        self.assertEqual(fitting["default_widths"]["produced"], DEFAULT_WIDTH_BY_KIND["number"])

    def test_report_form_has_no_header_preview(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from reports.models import SavedReport

        User = get_user_model()
        expert = User.objects.get(username="expert")
        report = SavedReport.objects.create(
            owner=expert,
            created_by=expert,
            title="بدون پیش‌نمایش",
            number=401,
            data_source="fitting",
            columns=[],
        )
        self.client.login(username="expert", password="erp12345")
        resp = self.client.get(reverse("report_edit", args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "col-header-preview")
        self.assertContains(resp, "نحوه نمایش")


class ReportCalcFormulaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_demo")

    def test_formula_round_and_sum(self):
        from reports.formula import evaluate_formula, format_excel_number

        self.assertEqual(evaluate_formula("=ROUND(10/3, 2)", {}), 3.33)
        self.assertEqual(evaluate_formula("=SUM(A1,B1)", {"a1": 4, "b1": 6}), 10)
        self.assertEqual(format_excel_number(1234.56, "#,##0.00"), "1,234.56")

    def test_calc_column_in_run_report(self):
        from reports.columns import normalize_columns, run_report

        cols = normalize_columns([
            {
                "key": "code", "source": "product", "level_mode": "1",
                "label": "کد", "is_key": True, "uid": "k1",
            },
            {
                "key": "stock_finished", "source": "product", "level_mode": "1",
                "label": "موجودی", "uid": "k2",
            },
            {
                "key": "calc", "source": "_calc", "kind": "calc", "level_mode": "1",
                "label": "دوبرابر", "uid": "k3", "formula": "=B1*2",
                "number_format": "#,##0",
            },
        ])
        self.assertEqual(cols[0]["col_code"], "a1")
        self.assertEqual(cols[2]["kind"], "calc")
        headers, rows, _payloads, deeper = run_report("product", cols, level=1)
        self.assertIn("دوبرابر", headers)
        self.assertFalse(deeper)
        # seed_demo sets F-1100.stock_finished = 300 on a fresh DB
        hit = next((r for r in rows if r[0] == "F-1100"), None)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], 300)
        self.assertEqual(str(hit[2]), "600")

    def test_upto_level_aggregates_numeric(self):
        from reports.columns import normalize_columns, run_report

        cols = normalize_columns([
            {
                "key": "code", "source": "product", "level_mode": "1",
                "label": "کد", "is_key": True, "uid": "k1",
            },
            {
                "key": "stock_finished", "source": "product", "level_mode": "upto_2",
                "label": "موجودی", "uid": "k2",
            },
            {
                "key": "product", "source": "product", "level_mode": "2",
                "label": "نام", "uid": "k3",
            },
        ])
        headers1, rows1, _, deeper1 = run_report("product", cols, level=1)
        self.assertTrue(deeper1)
        self.assertIn("موجودی", headers1)
        self.assertNotIn("نام", headers1)
        hit = next((r for r in rows1 if r[0] == "F-1100"), None)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], 300)

        headers2, rows2, _, deeper2 = run_report("product", cols, level=2)
        self.assertFalse(deeper2)
        self.assertIn("نام", headers2)

    def test_builder_page_has_calc_controls(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from reports.models import SavedReport

        User = get_user_model()
        expert = User.objects.get(username="expert")
        report = SavedReport.objects.create(
            owner=expert, created_by=expert, title="محاسبات", number=601,
            data_source="product", columns=[],
        )
        self.client.login(username="expert", password="erp12345")
        resp = self.client.get(reverse("report_edit", args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "add-calc-col")
        self.assertContains(resp, "formula-dialog")
        self.assertContains(resp, "کد ستون")
        self.assertContains(resp, "نوع نمایش")
        self.assertContains(resp, "report-conditions-panel")


class ReportUiPolishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_login_title_is_single_line_phrase(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("سامانه برنامه ریزی و کنترل تولید", body)
        self.assertNotIn("سامانه برنامه ریزی<br>", body)
        self.assertNotIn("سامانه برنامه ریزی<br/>", body)

    def test_app_css_drops_zebra_and_keeps_sticky_headers(self):
        from pathlib import Path

        css = Path("/workspace/static/css/app.css").read_text(encoding="utf-8")
        js = Path("/workspace/static/js/table_layout.js").read_text(encoding="utf-8")
        self.assertNotIn("tbody tr:nth-child(even)", css)
        self.assertIn(".table-scroll thead th", css)
        self.assertIn("position: sticky", css)
        self.assertIn(".content:has(.panel-list)", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn('th.style.position = "sticky"', js)
        self.assertIn("REVEAL_SPEED_PX_PER_SEC", js)
        self.assertIn("cell-reveal-inner", js)
        self.assertIn("scrollTableToRtlStart", js)
        self.assertIn("overflow: hidden", css)
        self.assertNotIn("distance * 28", js)

    def test_builder_priority_zero_and_rtl_parens(self):
        from pathlib import Path

        js = Path("/workspace/static/js/report_builder_display.js").read_text(encoding="utf-8")
        html = Path("/workspace/templates/reports/builder_standalone.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("function clampPriority", js)
        self.assertIn("for (var i = 0; i <= 9; i++)", js)
        self.assertIn("sort_priority: 0", js)
        self.assertIn("function rtlParenGlyph", js)
        self.assertIn("novalidate", html)
        self.assertIn('option value="(">)', html)
        self.assertIn('option value=")">(', html)
        self.assertIn("rb-paren-select", html)
        css = Path("/workspace/static/css/report_app.css").read_text(encoding="utf-8")
        self.assertIn(".rb-paren-select", css)
        self.assertIn("direction: ltr", css)
        hub = Path("/workspace/static/js/flexible_hub.js").read_text(encoding="utf-8")
        self.assertIn("scrollTableToRtlStart", hub)


class ReportConditionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.expert = User.objects.get(username="expert")

    def test_condition_validation_and_or_parens(self):
        from reports.conditions import validate_conditions_blob, row_matches_conditions

        good = {
            "public": [
                {
                    "logic": "",
                    "paren": "(",
                    "source": "fitting",
                    "field": "date",
                    "op": "=",
                    "value_mode": "parameter",
                    "param_code": "date_today",
                    "value": "",
                },
                {
                    "logic": "or",
                    "paren": "",
                    "source": "fitting",
                    "field": "date",
                    "op": "=",
                    "value_mode": "value",
                    "value": "14051102",
                    "param_code": "",
                },
                {
                    "logic": "or",
                    "paren": ")",
                    "source": "fitting",
                    "field": "code",
                    "op": "=",
                    "value_mode": "value",
                    "value": "ABC",
                    "param_code": "",
                },
            ],
            "private": {},
        }
        self.assertEqual(validate_conditions_blob(good), [])
        rows = good["public"]
        self.assertTrue(
            row_matches_conditions(
                {"date": "14051102", "code": "Z"}, rows, {"date_today": "14050101"}
            )
        )
        self.assertTrue(
            row_matches_conditions(
                {"date": "14050101", "code": "Z"}, rows, {"date_today": "14050101"}
            )
        )
        self.assertTrue(
            row_matches_conditions(
                {"date": "x", "code": "ABC"}, rows, {"date_today": "y"}
            )
        )
        self.assertFalse(
            row_matches_conditions(
                {"date": "x", "code": "Z"}, rows, {"date_today": "y"}
            )
        )

    def test_condition_split_parens_open_close(self):
        from reports.conditions import validate_conditions_blob, row_matches_conditions

        blob = {
            "public": [
                {
                    "logic": "",
                    "paren_open": "(",
                    "paren_close": "",
                    "source": "fitting",
                    "field": "date",
                    "op": "=",
                    "value_mode": "value",
                    "value": "14051102",
                    "param_code": "",
                },
                {
                    "logic": "or",
                    "paren_open": "",
                    "paren_close": ")",
                    "source": "fitting",
                    "field": "code",
                    "op": "=",
                    "value_mode": "value",
                    "value": "ABC",
                    "param_code": "",
                },
            ],
            "private": {},
        }
        self.assertEqual(validate_conditions_blob(blob), [])
        self.assertTrue(
            row_matches_conditions(
                {"date": "14051102", "code": "Z"}, blob["public"], {}
            )
        )
        self.assertTrue(
            row_matches_conditions(
                {"date": "x", "code": "ABC"}, blob["public"], {}
            )
        )

    def test_condition_exclusive_and_nested_parens(self):
        from reports.conditions import (
            paren_close_of,
            paren_open_of,
            row_matches_conditions,
            validate_conditions_blob,
        )

        both = {
            "public": [
                {
                    "logic": "",
                    "paren_open": "(",
                    "paren_close": ")",
                    "source": "fitting",
                    "field": "date",
                    "op": "=",
                    "value_mode": "value",
                    "value": "14051102",
                    "param_code": "",
                }
            ],
            "private": {},
        }
        errs = validate_conditions_blob(both)
        self.assertTrue(any("فقط پرانتز" in err for err in errs))

        nested = {
            "public": [
                {
                    "logic": "",
                    "paren_open": "((",
                    "paren_close": "",
                    "source": "fitting",
                    "field": "a",
                    "op": "=",
                    "value_mode": "value",
                    "value": "1",
                    "param_code": "",
                },
                {
                    "logic": "or",
                    "paren_open": "(",
                    "paren_close": "",
                    "source": "fitting",
                    "field": "b",
                    "op": "=",
                    "value_mode": "value",
                    "value": "2",
                    "param_code": "",
                },
                {
                    "logic": "and",
                    "paren_open": "",
                    "paren_close": ")",
                    "source": "fitting",
                    "field": "c",
                    "op": "=",
                    "value_mode": "value",
                    "value": "3",
                    "param_code": "",
                },
                {
                    "logic": "or",
                    "paren_open": "",
                    "paren_close": "))",
                    "source": "fitting",
                    "field": "d",
                    "op": "=",
                    "value_mode": "value",
                    "value": "4",
                    "param_code": "",
                },
            ],
            "private": {},
        }
        self.assertEqual(validate_conditions_blob(nested), [])
        self.assertEqual(paren_open_of(nested["public"][0]), "((")
        self.assertEqual(paren_close_of(nested["public"][3]), "))")
        rows = nested["public"]
        self.assertTrue(row_matches_conditions({"a": "1", "b": "x", "c": "x", "d": "x"}, rows))
        self.assertTrue(row_matches_conditions({"a": "x", "b": "2", "c": "3", "d": "x"}, rows))
        self.assertTrue(row_matches_conditions({"a": "x", "b": "x", "c": "x", "d": "4"}, rows))
        self.assertFalse(row_matches_conditions({"a": "x", "b": "2", "c": "x", "d": "x"}, rows))

    def test_run_report_empty_columns_returns_no_system_rows(self):
        from reports.columns import run_report

        headers, rows, payloads, deeper = run_report("fitting", [])
        self.assertEqual(headers, [])
        self.assertEqual(rows, [])
        self.assertEqual(payloads, [])
        self.assertFalse(deeper)

    def test_builder_and_viewer_use_standalone_templates(self):
        self.client.login(username="expert", password="erp12345")
        report = SavedReport.objects.create(
            owner=self.expert,
            created_by=self.expert,
            title="Standalone",
            number=777,
            data_source="fitting",
            columns=[{"key": "date", "source": "fitting", "level": 1, "label": "تاریخ", "uid": "c1"}],
            conditions={
                "public": [
                    {
                        "logic": "",
                        "paren": "",
                        "source": "fitting",
                        "field": "date",
                        "op": "=",
                        "value_mode": "parameter",
                        "param_code": "date_today",
                        "value": "",
                    }
                ],
                "private": {},
            },
        )
        edit = self.client.get(reverse("report_edit", args=[report.pk]))
        self.assertEqual(edit.status_code, 200)
        self.assertContains(edit, "rp-shell")
        self.assertContains(edit, "cond-tab-public")
        self.assertContains(edit, "condition-dialog")
        self.assertContains(edit, 'value="(("')
        self.assertContains(edit, 'value="))"')
        self.assertContains(edit, "delete-col")
        self.assertContains(edit, "خصوصی")

        detail = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "report-param-dialog")
        self.assertContains(detail, "date_today")
        self.assertTrue(detail.context["need_params"])

        applied = self.client.post(
            reverse("report_detail", args=[report.pk]),
            {"action": "apply_params", "param_date_today": "14051102"},
        )
        self.assertEqual(applied.status_code, 200)
        self.assertFalse(applied.context["need_params"])
