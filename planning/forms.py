from django import forms
from django.forms import inlineformset_factory
from django_jalali import forms as jforms

from catalog.models import Machine, MoldOption, Product, ProductKind, ProductSubGroup

from .models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .utils import format_jdate, mold_change_date_candidates, parse_jdate_string

JDATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d"]


def style_fields(form):
    """Apply ``input`` class to non-combo widgets only (avoid double borders)."""
    for field in form.fields.values():
        if field.widget.attrs.get("data-combo"):
            field.widget.attrs.pop("class", None)
            continue
        field.widget.attrs.setdefault("class", "input")


def combo(attrs=None):
    # Avoid class="input" — Tom Select copies it onto .ts-wrapper and that
    # creates a second outer border around the control.
    base = {"data-combo": "1"}
    if attrs:
        base.update(attrs)
    return forms.Select(attrs=base)


class WeeklyPlanForm(forms.ModelForm):
    date = jforms.jDateField(
        label="تاریخ برنامه‌ریزی",
        input_formats=JDATE_FORMATS,
        widget=forms.TextInput(attrs={
            "class": "input", "data-jdp": "", "autocomplete": "off",
            "placeholder": "۱۴۰۳/۰۵/۱۸",
        }),
    )

    class Meta:
        model = WeeklyPlan
        fields = ["program_number", "date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program_number"].widget.attrs.setdefault("class", "input")

    def clean_date(self):
        value = self.cleaned_data.get("date")
        if value is None:
            return value
        qs = WeeklyPlan.objects.filter(date=value)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            other = qs.first()
            raise forms.ValidationError(
                f"تاریخ برنامه‌ریزی تکراری است؛ برنامه «{other.program_number}» "
                f"همین تاریخ را دارد. دو برنامه با یک تاریخ مجاز نیست."
            )
        return value


class WeeklyPlanItemForm(forms.ModelForm):
    subgroup = forms.ModelChoiceField(
        queryset=ProductSubGroup.objects.filter(group__kind=ProductKind.FITTING),
        label="زیرگروه",
        widget=combo({"data-role": "subgroup"}),
    )
    code = forms.CharField(
        required=False, label="کد کالا",
        widget=forms.Select(attrs={"data-role": "code", "data-combo": "1"}),
    )
    mold_change_date = forms.ChoiceField(choices=[], label="تاریخ تعویض قالب",
                                         widget=combo())

    class Meta:
        model = WeeklyPlanItem
        fields = ["subgroup", "unit", "machine", "product", "code",
                  "mold_change_weekday", "active_cavities"]
        widgets = {
            "unit": combo({"data-role": "unit"}),
            "machine": combo({"data-role": "machine", "data-machine-type": "injection"}),
            "product": combo({"data-role": "product"}),
            "mold_change_weekday": combo({"data-role": "weekday"}),
        }

    def __init__(self, *args, plan_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_date = plan_date
        self.fields["machine"].queryset = Machine.objects.filter(
            machine_type="injection", is_active=True
        )
        self.fields["product"].queryset = Product.objects.filter(
            subgroup__group__kind=ProductKind.FITTING, is_active=True
        )
        self.fields["product"].label = "نام محصول"
        style_fields(self)

        # Candidate mold-change dates (for validation and initial display).
        weekday = None
        if self.data:
            weekday = self.data.get("mold_change_weekday")
        elif self.instance and self.instance.pk:
            weekday = self.instance.mold_change_weekday
        if weekday not in (None, "") and plan_date is not None:
            candidates = mold_change_date_candidates(plan_date, int(weekday))
            self.fields["mold_change_date"].choices = [
                (format_jdate(c), format_jdate(c)) for c in candidates
            ]
        if self.instance and self.instance.pk:
            self.fields["subgroup"].initial = self.instance.product.subgroup_id
            self.fields["mold_change_date"].initial = format_jdate(
                self.instance.mold_change_date
            )

    def clean_mold_change_date(self):
        return parse_jdate_string(self.cleaned_data["mold_change_date"])

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        machine = cleaned.get("machine")
        product = cleaned.get("product")
        subgroup = cleaned.get("subgroup")
        if unit and machine and machine.unit_id != unit.id:
            self.add_error("machine", "دستگاه انتخاب‌شده متعلق به این واحد نیست.")
        if product and subgroup and product.subgroup_id != subgroup.id:
            self.add_error("product", "محصول با زیرگروه انتخاب‌شده هم‌خوانی ندارد.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.mold_change_date = self.cleaned_data["mold_change_date"]
        if commit:
            obj.save()
        return obj


class EmptyZeroNumberInput(forms.NumberInput):
    """Render 0 as blank so typing a new number is not blocked by a leading zero."""

    def format_value(self, value):
        if value in (0, "0", None, ""):
            return ""
        return super().format_value(value)


class WeeklyPlanLineForm(forms.ModelForm):
    class Meta:
        model = WeeklyPlanLine
        fields = ["production_type", "mold", "quantity", "cycle"]
        widgets = {
            "production_type": combo(),
            "mold": combo(),
            "quantity": EmptyZeroNumberInput(attrs={"class": "input", "min": "0"}),
            "cycle": EmptyZeroNumberInput(attrs={"class": "input", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mold"].queryset = MoldOption.objects.filter(is_active=True)
        self.fields["mold"].required = False
        self.fields["mold"].empty_label = "—"
        # Blank out zeros on new/empty rows (and when stored value is 0).
        for name in ("quantity", "cycle"):
            field = self.fields[name]
            field.required = False
            if not self.is_bound:
                current = getattr(self.instance, name, None) if self.instance else None
                if not self.instance.pk or current in (0, None):
                    field.initial = None
        style_fields(self)

    def clean_quantity(self):
        return self.cleaned_data.get("quantity") or 0

    def clean_cycle(self):
        return self.cleaned_data.get("cycle") or 0


WeeklyPlanLineFormSet = inlineformset_factory(
    WeeklyPlanItem,
    WeeklyPlanLine,
    form=WeeklyPlanLineForm,
    fields=["production_type", "mold", "quantity", "cycle"],
    extra=1,
    can_delete=False,
)
