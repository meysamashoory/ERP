from django.contrib import admin

from .models import (
    DeviationReason,
    Machine,
    Product,
    ProductGroup,
    ProductSubGroup,
    ProductionTypeOption,
    ProductionUnit,
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
