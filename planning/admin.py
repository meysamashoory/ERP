from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter

from .models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine


class WeeklyPlanLineInline(admin.TabularInline):
    model = WeeklyPlanLine
    extra = 1


class WeeklyPlanItemInline(admin.StackedInline):
    model = WeeklyPlanItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(WeeklyPlan)
class WeeklyPlanAdmin(admin.ModelAdmin):
    list_display = ("program_number", "date", "weekday_name", "status", "created_by")
    list_filter = ("status", ("date", JDateFieldListFilter))
    search_fields = ("program_number",)
    inlines = [WeeklyPlanItemInline]

    @admin.display(description="روز")
    def weekday_name(self, obj):
        return obj.weekday_name


@admin.register(WeeklyPlanItem)
class WeeklyPlanItemAdmin(admin.ModelAdmin):
    list_display = ("plan", "product", "machine", "mold_change_date", "active_cavities")
    list_filter = ("unit", "subgroup")
    autocomplete_fields = ("product",)
    inlines = [WeeklyPlanLineInline]
