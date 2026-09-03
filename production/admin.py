from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter

from .models import (
    FittingProduction,
    PipeProduction,
    ProductionDayEntry,
    ProductionHistoryRecord,
    ProductionProgram,
    ProductionStoppage,
)


class DayEntryInline(admin.TabularInline):
    model = ProductionDayEntry
    extra = 0
    readonly_fields = ("planned_quantity", "active_seconds")


@admin.register(ProductionProgram)
class ProductionProgramAdmin(admin.ModelAdmin):
    list_display = ("item", "status", "change_type", "production_type",
                    "start_date", "start_time", "stop_date", "stop_time")
    list_filter = ("status", "change_type")
    search_fields = ("item__uid", "item__product__name", "item__product__code")
    inlines = [DayEntryInline]


@admin.register(ProductionDayEntry)
class ProductionDayEntryAdmin(admin.ModelAdmin):
    list_display = ("program", "date", "produced_quantity", "planned_quantity",
                    "deviation", "cycle", "active_cavities")
    list_filter = (("date", JDateFieldListFilter),)
    readonly_fields = ("planned_quantity", "active_seconds")

    @admin.display(description="انحراف")
    def deviation(self, obj):
        return obj.deviation


class FittingStoppageInline(admin.TabularInline):
    model = ProductionStoppage
    fk_name = "fitting"
    extra = 0


class PipeStoppageInline(admin.TabularInline):
    model = ProductionStoppage
    fk_name = "pipe"
    extra = 0


@admin.register(ProductionHistoryRecord)
class ProductionHistoryRecordAdmin(admin.ModelAdmin):
    list_display = (
        "program_uid",
        "product_code",
        "product_name",
        "machine_number",
        "planned_qty",
        "produced_qty",
        "status",
        "created_at",
    )
    search_fields = ("program_uid", "product_code", "product_name", "mold_name")
    list_filter = ("status",)

    def delete_model(self, request, obj):
        from production.sync import delete_history_archive_and_live

        delete_history_archive_and_live(obj)

    def delete_queryset(self, request, queryset):
        from production.sync import delete_history_archives_queryset

        delete_history_archives_queryset(queryset)


@admin.register(FittingProduction)
class FittingProductionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "unit",
        "machine",
        "product",
        "produced_quantity",
        "planned_quantity",
        "scrap_quantity",
        "deviation",
    )
    list_filter = (("date", JDateFieldListFilter), "unit", "machine")
    search_fields = ("product__name", "product__code")
    autocomplete_fields = ("product",)
    inlines = [FittingStoppageInline]

    @admin.display(description="انحراف")
    def deviation(self, obj):
        return obj.deviation


@admin.register(PipeProduction)
class PipeProductionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "unit",
        "line",
        "pipe_type",
        "size",
        "produced_quantity",
        "planned_quantity",
        "deviation",
    )
    list_filter = (("date", JDateFieldListFilter), "unit", "line", "pipe_type")
    search_fields = ("pipe_type", "size")
    inlines = [PipeStoppageInline]

    @admin.display(description="انحراف")
    def deviation(self, obj):
        return obj.deviation
