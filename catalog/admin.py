from django.contrib import admin

from .models import (
    DeviationReason,
    ExcelTable,
    ExcelUpload,
    Machine,
    MoldOption,
    PlanningDisplaySettings,
    PlanningInsightField,
    Product,
    ProductGroup,
    ProductSubGroup,
    ProductionTypeOption,
    ProductionUnit,
    ProgramChangeReason,
    ProgramUidScheme,
    StoppageReason,
    SystemAlarm,
)


class MachineInline(admin.TabularInline):
    model = Machine
    extra = 0


@admin.register(ProductionUnit)
class ProductionUnitAdmin(admin.ModelAdmin):
    list_display = ("number", "name")
    inlines = [MachineInline]
    search_fields = ("name",)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("unit", "machine_type", "number", "is_active")
    list_filter = ("unit", "machine_type", "is_active")
    search_fields = ("number",)


class ProductSubGroupInline(admin.TabularInline):
    model = ProductSubGroup
    extra = 0


@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "order")
    list_filter = ("kind",)
    list_editable = ("kind", "order")
    inlines = [ProductSubGroupInline]


@admin.register(ProductSubGroup)
class ProductSubGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "order")
    list_filter = ("group",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "subgroup",
        "counting_unit",
        "unit_weight_grams",
        "needs_assembly",
        "needs_machining",
        "needs_facing",
        "stock_finished",
        "needs_reorder",
    )
    list_filter = (
        "subgroup__group",
        "subgroup",
        "counting_unit",
        "needs_assembly",
        "needs_machining",
        "needs_facing",
        "is_active",
    )
    search_fields = ("code", "name")
    list_editable = ("unit_weight_grams", "stock_finished")

    @admin.display(boolean=True, description="سفارش مجدد؟")
    def needs_reorder(self, obj: Product) -> bool:
        return obj.needs_reorder


@admin.register(ProductionTypeOption)
class ProductionTypeOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(StoppageReason)
class StoppageReasonAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(DeviationReason)
class DeviationReasonAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(ProgramChangeReason)
class ProgramChangeReasonAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(MoldOption)
class MoldOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(PlanningInsightField)
class PlanningInsightFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "source", "source_key", "order", "is_active")
    list_editable = ("order", "is_active", "source", "source_key")
    list_filter = ("source", "is_active")
    search_fields = ("label", "source_key")
    ordering = ("order", "id")


@admin.register(PlanningDisplaySettings)
class PlanningDisplaySettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "height_coefficient", "matrix_unit_numbers", "show_group_breakdown")
    list_display_links = ("id",)
    list_editable = ("height_coefficient", "matrix_unit_numbers", "show_group_breakdown")
    fieldsets = (
        (
            "کادر آبی و ماتریس تعویض قالب",
            {
                "fields": (
                    "height_coefficient",
                    "matrix_unit_numbers",
                    "show_group_breakdown",
                ),
                "description": (
                    "ضریب ارتفاع ۱٫۰ = پایه؛ ۱٫۲ یعنی ۲۰٪ بلندتر. "
                    "واحدهای ماتریس را با ویرگول مشخص کنید (مثلاً ۱,۲,۴)."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        # Keep a single settings row when possible.
        if PlanningDisplaySettings.objects.exists():
            return False
        return super().has_add_permission(request)

@admin.register(ProgramUidScheme)
class ProgramUidSchemeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
        "base_year",
        "total_digits_display",
        "updated_at",
    )
    list_display_links = ("name",)
    list_editable = ("is_active", "base_year")
    readonly_fields = ("updated_at", "example_preview")
    fieldsets = (
        (
            "قانون فعال",
            {
                "fields": ("name", "is_active", "notes", "example_preview"),
                "description": (
                    "این قانون شناسه ۱۴ رقمی برنامه‌ریزی را تعریف می‌کند. "
                    "با تغییر ارقام یا سال مبدأ، شناسه‌های جدید بر اساس تنظیمات ساخته می‌شوند. "
                    "برای اعمال روی برنامه‌های موجود از اکشن «بازسازی شناسه‌ها» استفاده کنید."
                ),
            },
        ),
        (
            "سال و ارقام",
            {
                "fields": (
                    "base_year",
                    "year_digits",
                    "program_digits",
                    "unit_digits",
                    "machine_digits",
                    "date_sum_digits",
                    "production_type_digits",
                    "mold_row_digits",
                ),
            },
        ),
        (
            "تعریف قطعات (بازتعریف آینده)",
            {
                "fields": ("segments_json",),
                "classes": ("collapse",),
            },
        ),
        (None, {"fields": ("updated_at",)}),
    )
    actions = ("rebuild_all_uids",)

    def total_digits_display(self, obj):
        return obj.total_digits

    total_digits_display.short_description = "مجموع ارقام"

    def example_preview(self, obj):
        import jdatetime
        from planning.uid import build_program_uid

        sample = build_program_uid(
            plan_date=jdatetime.date(1405, 5, 26),
            program_number=159,
            unit_number=4,
            machine_number=2,
            mold_change_date=jdatetime.date(1405, 5, 27),
            production_type_index=2,
            mold_row=23,
            scheme=obj,
        )
        return f"نمونه (برنامه ۱۵۹ / واحد۴ / دستگاه۲ / نوع۲ / ردیف۲۳): {sample}"

    example_preview.short_description = "پیش‌نمایش نمونه"

    def has_add_permission(self, request):
        if ProgramUidScheme.objects.exists():
            return False
        return super().has_add_permission(request)

    @admin.action(description="بازسازی شناسه همه کالاهای برنامه‌ها با قانون فعال")
    def rebuild_all_uids(self, request, queryset):
        from planning.models import WeeklyPlan
        from planning.uid import refresh_plan_uids

        scheme = ProgramUidScheme.load()
        items = 0
        collisions = 0
        for plan in WeeklyPlan.objects.all().iterator():
            n_before = plan.items.count()
            cols = refresh_plan_uids(plan, scheme=scheme)
            items += n_before
            collisions += len(cols)
        msg = f"شناسه {items} کالا بازسازی شد."
        if collisions:
            msg += f" {collisions} مورد تکرار شناسه در آلارم‌های سیستم ثبت شد."
        self.message_user(request, msg)


@admin.register(SystemAlarm)
class SystemAlarmAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "severity",
        "kind",
        "status",
        "title",
        "short_suggestion",
    )
    list_filter = ("severity", "kind", "status", "created_at")
    search_fields = ("title", "message", "suggestion")
    readonly_fields = ("created_at", "reviewed_at", "reviewed_by", "details")
    list_display_links = ("title",)
    actions = ("mark_reviewed", "mark_cleared", "hard_delete")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "severity",
                    "kind",
                    "status",
                    "title",
                    "message",
                    "suggestion",
                    "details",
                    "created_at",
                    "reviewed_at",
                    "reviewed_by",
                ),
                "description": (
                    "آلارم‌های جدی (مثل تکرار شناسه) اینجا ثبت می‌شوند. "
                    "پس از بررسی می‌توانید وضعیت را به بررسی‌شده یا پاک‌شده تغییر دهید."
                ),
            },
        ),
    )

    def short_suggestion(self, obj):
        text = (obj.suggestion or "")[:80]
        return text + ("…" if obj.suggestion and len(obj.suggestion) > 80 else "")

    short_suggestion.short_description = "پیشنهاد اصلاح"

    @admin.action(description="علامت‌گذاری به‌عنوان بررسی‌شده")
    def mark_reviewed(self, request, queryset):
        for alarm in queryset:
            alarm.mark_reviewed(user=request.user)
        self.message_user(request, f"{queryset.count()} آلارم بررسی‌شده شد.")

    @admin.action(description="علامت‌گذاری به‌عنوان پاک‌شده")
    def mark_cleared(self, request, queryset):
        for alarm in queryset:
            alarm.mark_cleared(user=request.user)
        self.message_user(request, f"{queryset.count()} آلارم پاک‌شده شد.")

    @admin.action(description="حذف دائمی از فهرست")
    def hard_delete(self, request, queryset):
        n = queryset.count()
        queryset.delete()
        self.message_user(request, f"{n} آلارم برای همیشه حذف شد.")


class ExcelTableInline(admin.TabularInline):
    model = ExcelTable
    extra = 0
    fields = ("name", "sheet_name", "order", "row_count_display", "updated_at")
    readonly_fields = ("row_count_display", "updated_at")
    show_change_link = True

    def row_count_display(self, obj):
        if not obj.pk:
            return "—"
        return f"{obj.row_count} × {obj.column_count}"

    row_count_display.short_description = "ردیف × ستون"


@admin.register(ExcelUpload)
class ExcelUploadAdmin(admin.ModelAdmin):
    list_display = ("title", "original_name", "table_count", "uploaded_by", "created_at", "download_link")
    list_display_links = ("title",)
    search_fields = ("title", "original_name", "notes")
    list_filter = ("created_at",)
    readonly_fields = ("original_name", "uploaded_by", "created_at", "updated_at", "download_link")
    fields = (
        "title", "file", "notes", "original_name",
        "uploaded_by", "created_at", "updated_at", "download_link",
    )
    inlines = [ExcelTableInline]

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def download_link(self, obj):
        if not obj.pk or not obj.file:
            return "—"
        from django.utils.html import format_html
        return format_html('<a href="{}" download>دانلود فایل</a>', obj.file.url)

    download_link.short_description = "سوابق / دانلود"


@admin.register(ExcelTable)
class ExcelTableAdmin(admin.ModelAdmin):
    list_display = ("name", "upload", "sheet_name", "order", "row_count", "column_count", "updated_at")
    list_filter = ("upload",)
    search_fields = ("name", "sheet_name", "upload__title")
    readonly_fields = ("created_at", "updated_at", "source_id_display")
    fields = (
        "upload", "name", "sheet_name", "order",
        "headers", "rows", "source_id_display", "created_at", "updated_at",
    )

    def source_id_display(self, obj):
        return obj.source_id if obj.pk else "—"

    source_id_display.short_description = "شناسه منبع گزارش"
