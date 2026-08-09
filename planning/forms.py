import jdatetime
from django import forms
from django.forms import inlineformset_factory

from catalog.models import Machine

from .models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .utils import mold_change_date_candidates


class WeeklyPlanForm(forms.ModelForm):
    class Meta:
        model = WeeklyPlan
        fields = ["program_number", "date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")


class WeeklyPlanItemForm(forms.ModelForm):
    mold_change_date = forms.ChoiceField(choices=[], label="تاریخ تعویض قالب")

    class Meta:
        model = WeeklyPlanItem
        fields = [
            "subgroup",
            "unit",
            "machine",
            "product",
            "mold_change_weekday",
            "active_cavities",
        ]

    def __init__(self, *args, plan_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_date = plan_date
        self.fields["machine"].queryset = Machine.objects.filter(
            machine_type="injection", is_active=True
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

        # Populate the candidate dates so the submitted value validates.
        weekday = self.data.get("mold_change_weekday") if self.data else None
        if weekday not in (None, "") and plan_date is not None:
            candidates = mold_change_date_candidates(plan_date, int(weekday))
            self.fields["mold_change_date"].choices = [
                (c.strftime("%Y-%m-%d"), c.strftime("%Y-%m-%d")) for c in candidates
            ]

    def clean_mold_change_date(self):
        raw = self.cleaned_data["mold_change_date"]
        y, m, d = (int(p) for p in raw.split("-"))
        return jdatetime.date(y, m, d)

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
    extra=3,
    can_delete=True,
)
