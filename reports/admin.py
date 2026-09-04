from django.contrib import admin

from .models import PrintForm, ReportParameterDef, SavedReport


@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "owner", "data_source", "is_standard", "updated_at")
    list_filter = ("is_standard", "data_source")
    search_fields = ("number", "title", "owner__username")
    filter_horizontal = ("viewers",)


@admin.register(ReportParameterDef)
class ReportParameterDefAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "kind", "order", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "label")


@admin.register(PrintForm)
class PrintFormAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "owner", "is_standard", "updated_at")
    list_filter = ("is_standard",)
    search_fields = ("number", "title", "owner__username")
    filter_horizontal = ("viewers",)
