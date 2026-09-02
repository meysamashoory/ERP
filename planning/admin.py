from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter

from .models import (
    CustomerOrder,
    PlanningProcessDefinition,
    PlanningProcessStep,
    SalesForecast,
    WeeklyPlan,
    WeeklyPlanItem,
    WeeklyPlanLine,
)


class WeeklyPlanLineInline(admin.TabularInline):
    model = WeeklyPlanLine
    extra = 1


class WeeklyPlanItemInline(admin.StackedInline):
    model = WeeklyPlanItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(WeeklyPlan)
class WeeklyPlanAdmin(admin.ModelAdmin):
    list_display = ("program_number", "date", "weekday_name", "planning_mode", "status", "created_by")
    list_filter = ("status", "planning_mode", ("date", JDateFieldListFilter))
    search_fields = ("program_number",)
    inlines = [WeeklyPlanItemInline]

    @admin.display(description="روز")
    def weekday_name(self, obj):
        return obj.weekday_name


@admin.register(WeeklyPlanItem)
class WeeklyPlanItemAdmin(admin.ModelAdmin):
    list_display = ("plan", "product", "machine", "mold_change_date", "active_cavities")
    list_filter = ("unit", "subgroup")
    search_fields = ("product__code", "product__name", "uid")
    autocomplete_fields = ("product", "machine")
    inlines = [WeeklyPlanLineInline]


@admin.register(CustomerOrder)
class CustomerOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_ref",
        "product_code",
        "quantity",
        "priority",
        "is_backlog",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_backlog", "is_active")
    search_fields = ("order_ref", "product_code", "product_name", "customer_name")


@admin.register(SalesForecast)
class SalesForecastAdmin(admin.ModelAdmin):
    list_display = ("product_code", "period_label", "quantity", "is_active", "updated_at")
    search_fields = ("product_code", "product_name", "period_label")


class PlanningProcessStepInline(admin.TabularInline):
    model = PlanningProcessStep
    extra = 0
    fields = (
        "step_number",
        "kind",
        "title",
        "question",
        "yes_next_number",
        "no_next_number",
        "next_number",
        "data_binding",
        "is_active",
    )


@admin.register(PlanningProcessDefinition)
class PlanningProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "entry_step_number", "is_active", "updated_at")
    search_fields = ("code", "title")
    inlines = [PlanningProcessStepInline]


@admin.register(PlanningProcessStep)
class PlanningProcessStepAdmin(admin.ModelAdmin):
    list_display = (
        "process",
        "step_number",
        "kind",
        "title",
        "yes_next_number",
        "no_next_number",
        "next_number",
        "data_binding",
        "is_active",
    )
    list_filter = ("process", "kind", "data_binding", "is_active")
    search_fields = ("title", "question", "data_binding")
