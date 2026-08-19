from django.contrib import admin

from .models import (
    DeviationReason,
    Machine,
    MoldOption,
    Product,
    ProductGroup,
    ProductSubGroup,
    ProductionTypeOption,
    ProductionUnit,
    ProgramChangeReason,
    ProgramUidScheme,
    StoppageReason,
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
        total = 0
        for plan in WeeklyPlan.objects.all().iterator():
            total += refresh_plan_uids(plan, scheme=scheme)
        self.message_user(request, f"شناسه {total} کالا بازسازی شد.")
