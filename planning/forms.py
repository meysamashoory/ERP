import jdatetime
from django import forms
from django.forms import inlineformset_factory
from django_jalali import forms as jforms

from catalog.models import DeviationReason, Machine, Product, ProductKind, ProductSubGroup

from .models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .utils import mold_change_date_candidates

JDATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d"]


def combo(attrs=None):
    base = {"class": "input", "data-combo": "1"}
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


class WeeklyPlanItemForm(forms.ModelForm):
    subgroup = forms.ModelChoiceField(
        queryset=ProductSubGroup.objects.filter(group__kind=ProductKind.FITTING),
        label="زیرگروه",
        widget=combo({"data-role": "subgroup"}),
    )
    code = forms.CharField(
        required=False, label="کد کالا",
        widget=forms.Select(attrs={"class": "input", "data-role": "code", "data-combo": "1"}),
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
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

        # Candidate mold-change dates (for validation and initial display).
        weekday = None
        if self.data:
            weekday = self.data.get("mold_change_weekday")
        elif self.instance and self.instance.pk:
            weekday = self.instance.mold_change_weekday
        if weekday not in (None, "") and plan_date is not None:
            candidates = mold_change_date_candidates(plan_date, int(weekday))
            self.fields["mold_change_date"].choices = [
                (c.strftime("%Y-%m-%d"), c.strftime("%Y-%m-%d")) for c in candidates
            ]
        if self.instance and self.instance.pk:
            self.fields["subgroup"].initial = self.instance.product.subgroup_id
            self.fields["mold_change_date"].initial = self.instance.mold_change_date.strftime("%Y-%m-%d")

    def clean_mold_change_date(self):
        raw = self.cleaned_data["mold_change_date"]
        y, m, d = (int(p) for p in raw.split("-"))
        return jdatetime.date(y, m, d)

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


WeeklyPlanLineFormSet = inlineformset_factory(
    WeeklyPlanItem,
    WeeklyPlanLine,
    fields=["production_type", "quantity", "cycle"],
    extra=1,
    can_delete=False,
    widgets={"production_type": combo()},
)
