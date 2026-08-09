from django import forms
from django.forms import inlineformset_factory
from django_jalali import forms as jforms

from catalog.models import (
    DeviationReason,
    Machine,
    Product,
    ProductSubGroup,
    ProductKind,
)

from .models import FittingProduction, PipeProduction, ProductionStoppage

# Jalali date input formats accepted from the date picker / manual typing.
JDATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d"]


def jdate_field(label="تاریخ"):
    return jforms.jDateField(
        label=label,
        input_formats=JDATE_FORMATS,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "data-jdp": "",
                "autocomplete": "off",
                "placeholder": "۱۴۰۳/۰۵/۱۸",
            }
        ),
    )


def combo(attrs=None):
    """A <select> widget enhanced into a searchable/typeable combobox."""
    base = {"class": "input", "data-combo": "1"}
    if attrs:
        base.update(attrs)
    return forms.Select(attrs=base)


class _ProductionFormBase(forms.ModelForm):
    """Shared wiring for the fitting/pipe production forms."""

    kind = ProductKind.FITTING  # overridden by subclasses

    subgroup = forms.ModelChoiceField(
        queryset=ProductSubGroup.objects.none(),
        label="زیرگروه",
        widget=combo({"data-role": "subgroup"}),
    )
    code = forms.CharField(
        required=False,
        label="کد کالا",
        widget=forms.Select(attrs={"class": "input", "data-role": "code", "data-combo": "1"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subgroup"].queryset = ProductSubGroup.objects.filter(
            group__kind=self.kind
        )
        self.fields["product"].queryset = Product.objects.filter(
            subgroup__group__kind=self.kind, is_active=True
        )
        self.fields["product"].label = "نام محصول"
        self.fields["product"].widget = combo({"data-role": "product"})
        self.fields["deviation_reason"].queryset = DeviationReason.objects.filter(
            is_active=True
        )
        self.fields["deviation_reason"].required = False
        self.fields["deviation_reason"].empty_label = "—"
        # Pre-select subgroup when editing an existing record.
        if self.instance and self.instance.pk and self.instance.product_id:
            self.fields["subgroup"].initial = self.instance.product.subgroup_id
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        subgroup = cleaned.get("subgroup")
        if product and subgroup and product.subgroup_id != subgroup.id:
            self.add_error("product", "محصول با زیرگروه انتخاب‌شده هم‌خوانی ندارد.")
        return cleaned


class FittingProductionForm(_ProductionFormBase):
    kind = ProductKind.FITTING

    class Meta:
        model = FittingProduction
        fields = [
            "date",
            "unit",
            "machine",
            "subgroup",
            "product",
            "code",
            "shot_cycle",
            "active_cavities",
            "planned_quantity",
            "produced_quantity",
            "scrap_quantity",
            "deviation_reason",
            "description",
        ]
        widgets = {
            "unit": combo({"data-role": "unit"}),
            "machine": combo({"data-role": "machine", "data-machine-type": "injection"}),
            "deviation_reason": combo(),
            "description": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    date = jdate_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["machine"].queryset = Machine.objects.filter(
            machine_type="injection", is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        machine = cleaned.get("machine")
        if unit and machine and machine.unit_id != unit.id:
            self.add_error("machine", "دستگاه انتخاب‌شده متعلق به این واحد نیست.")
        return cleaned


class PipeProductionForm(_ProductionFormBase):
    kind = ProductKind.PIPE

    class Meta:
        model = PipeProduction
        fields = [
            "date",
            "unit",
            "line",
            "subgroup",
            "product",
            "code",
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
            "deviation_reason",
            "description",
        ]
        widgets = {
            "unit": combo({"data-role": "unit"}),
            "line": combo({"data-role": "machine", "data-machine-type": "extruder"}),
            "socket_length": combo(),
            "bling_machine": combo(),
            "thickness_unit": combo(),
            "material_grade": combo(),
            "deviation_reason": combo(),
            "description": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    date = jdate_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["line"].queryset = Machine.objects.filter(
            machine_type="extruder", is_active=True
        )
        self.fields["bling_machine"].queryset = Machine.objects.filter(
            machine_type="bling", is_active=True
        )
        self.fields["product"].required = True

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        line = cleaned.get("line")
        if unit and line and line.unit_id != unit.id:
            self.add_error("line", "خط انتخاب‌شده متعلق به این واحد نیست.")
        return cleaned


def pipe_field_map() -> dict:
    """Map each pipe subgroup id -> list of relevant field names (for the UI).

    Fields not listed for a subgroup are hidden/disabled on the pipe form.
    """
    common = ["thickness", "thickness_unit", "length_meters"]
    result = {}
    for sg in ProductSubGroup.objects.filter(group__kind=ProductKind.PIPE):
        name = sg.name
        fields = list(common)
        if "پوش‌فیت" in name or name in ("جنرال", "سایلنت"):
            fields += ["socket_length", "bling_machine"]
        elif "دریپردار" in name or "تیپ" in name or "دریپر" in name:
            fields += ["dripper_spec", "nominal_flow", "dripper_spacing"]
            if "راند" in name:
                fields += ["material_grade", "nominal_pressure"]
        elif "خرطومی" in name:
            fields += ["color"]
        elif "بدون دریپر" in name:
            fields += ["nominal_pressure", "material_grade"]
        else:  # فاضلابی، آبرسانی و سایر لوله‌ها
            fields += ["nominal_pressure", "material_grade"]
        # de-duplicate, keep order
        seen = set()
        result[str(sg.id)] = [f for f in fields if not (f in seen or seen.add(f))]
    return result


# Stoppages: no delete option (per request); one row, more can be added.
StoppageFormSetFitting = inlineformset_factory(
    FittingProduction,
    ProductionStoppage,
    fk_name="fitting",
    fields=["reason", "minutes", "note"],
    extra=1,
    can_delete=False,
    widgets={"reason": combo()},
)

StoppageFormSetPipe = inlineformset_factory(
    PipeProduction,
    ProductionStoppage,
    fk_name="pipe",
    fields=["reason", "minutes", "note"],
    extra=1,
    can_delete=False,
    widgets={"reason": combo()},
)
