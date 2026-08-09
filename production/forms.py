from django import forms
from django.forms import inlineformset_factory

from catalog.models import Machine, StoppageReason

from .models import FittingProduction, PipeProduction, ProductionStoppage


TEXT = {"class": "input"}
NUM = {"class": "input", "min": 0}


class FittingProductionForm(forms.ModelForm):
    class Meta:
        model = FittingProduction
        fields = [
            "date",
            "unit",
            "machine",
            "product",
            "shot_cycle",
            "active_cavities",
            "planned_quantity",
            "produced_quantity",
            "scrap_quantity",
            "material_used",
            "material_scrap",
            "deviation_reason",
            "description",
        ]
        widgets = {
            "deviation_reason": forms.Textarea(attrs={"class": "input", "rows": 2}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["machine"].queryset = Machine.objects.filter(
            machine_type="injection", is_active=True
        )
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "input")


class PipeProductionForm(forms.ModelForm):
    class Meta:
        model = PipeProduction
        fields = [
            "date",
            "unit",
            "line",
            "pipe_type",
            "product",
            "size",
            "socket_length",
            "bling_machine",
            "nominal_pressure",
            "thickness",
            "thickness_unit",
            "material_grade",
            "dripper_spec",
            "nominal_flow",
            "dripper_spacing",
            "color",
            "length_meters",
            "planned_quantity",
            "produced_quantity",
            "scrap_quantity",
            "material_used",
            "material_scrap",
            "deviation_reason",
            "description",
        ]
        widgets = {
            "deviation_reason": forms.Textarea(attrs={"class": "input", "rows": 2}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["line"].queryset = Machine.objects.filter(
            machine_type="extruder", is_active=True
        )
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "input")


StoppageFormSetFitting = inlineformset_factory(
    FittingProduction,
    ProductionStoppage,
    fk_name="fitting",
    fields=["reason", "minutes", "note"],
    extra=1,
    can_delete=True,
)

StoppageFormSetPipe = inlineformset_factory(
    PipeProduction,
    ProductionStoppage,
    fk_name="pipe",
    fields=["reason", "minutes", "note"],
    extra=1,
    can_delete=True,
)
