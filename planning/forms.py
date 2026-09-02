import json

from django import forms
from django.forms import inlineformset_factory
from django_jalali import forms as jforms

from catalog.models import Machine, MoldOption, Product, ProductKind, ProductSubGroup

from .models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .utils import format_jdate, mold_change_date_candidates, parse_jdate_string

JDATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d"]

PRODUCTION_SHIFT_CHOICES = [
    ("", "——"),
    ("day", "فقط شیفت روز"),
    ("night", "فقط شیفت شب"),
    ("both", "هر دو شیفت"),
]


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
        required=False,
        widget=combo({"data-role": "subgroup"}),
    )
    code = forms.CharField(
        required=False, label="کد کالا",
        widget=forms.Select(attrs={"data-role": "code", "data-combo": "1"}),
    )
    mold_change_date = forms.ChoiceField(
        choices=[], label="تاریخ تعویض قالب", widget=combo(),
    )
    production_days = forms.CharField(
        required=False, widget=forms.HiddenInput(attrs={"id": "id_production_days"}),
    )

    class Meta:
        model = WeeklyPlanItem
        fields = [
            "subgroup", "product", "code", "mold",
            "unit", "machine", "mold_change_weekday",
        ]
        widgets = {
            "unit": combo({"data-role": "unit"}),
            "machine": combo({"data-role": "machine", "data-machine-type": "injection"}),
            "product": combo({"data-role": "product"}),
            "mold": combo(),
            "mold_change_weekday": combo({"data-role": "weekday"}),
        }

    def __init__(self, *args, plan_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_date = plan_date
        self.fields["machine"].queryset = Machine.objects.filter(
            machine_type="injection", is_active=True
        )
        self.fields["machine"].label = "شماره دستگاه تزریق"
        products = Product.objects.filter(
            subgroup__group__kind=ProductKind.FITTING, is_active=True
        )
        self.fields["product"].queryset = products
        self.fields["product"].label = "نام کالا"
        # Keep نام کالا = name only (Product.__str__ mixes code + name).
        self.fields["product"].label_from_instance = lambda obj: obj.name
        self.fields["code"].widget.choices = (
            [("", "——")] + [(str(p.pk), p.code) for p in products]
        )
        self.fields["mold"].queryset = MoldOption.objects.filter(is_active=True)
        self.fields["mold"].required = False
        self.fields["mold"].empty_label = "——"
        self.fields["mold"].label = "نوع قالب"
        self.fields["subgroup"].empty_label = "——"
        style_fields(self)

        weekday = None
        if self.data:
            weekday = self.data.get("mold_change_weekday")
        elif self.instance and self.instance.pk:
            weekday = self.instance.mold_change_weekday
        choices = []
        if weekday not in (None, "") and plan_date is not None:
            candidates = mold_change_date_candidates(plan_date, int(weekday))
            choices = [(format_jdate(c), format_jdate(c)) for c in candidates]
        # Keep the currently saved date selectable even if outside the horizon.
        current_date = None
        if self.instance and self.instance.pk and self.instance.mold_change_date:
            current_date = format_jdate(self.instance.mold_change_date)
        if self.data and self.data.get("mold_change_date"):
            current_date = self.data.get("mold_change_date")
        if current_date and (current_date, current_date) not in choices:
            choices.insert(0, (current_date, current_date))
        self.fields["mold_change_date"].choices = choices
        if self.instance and self.instance.pk:
            self.fields["subgroup"].initial = self.instance.product.subgroup_id
            self.fields["code"].initial = str(self.instance.product_id)
            self.fields["mold_change_date"].initial = format_jdate(
                self.instance.mold_change_date
            )
            days = self.instance.production_days or []
            self.fields["production_days"].initial = json.dumps(
                days, ensure_ascii=False
            )

    def clean_mold_change_date(self):
        return parse_jdate_string(self.cleaned_data["mold_change_date"])

    def clean_production_days(self):
        raw = self.cleaned_data.get("production_days") or "[]"
        if isinstance(raw, list):
            return raw
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        cleaned = []
        for row in data:
            if not isinstance(row, dict):
                continue
            date = str(row.get("date") or "").strip()
            if not date:
                continue
            shift = str(row.get("shift") or "").strip()
            if shift not in ("", "day", "night", "both"):
                shift = ""
            cleaned.append({
                "date": format_jdate(date),
                "shift": shift,
                "note": str(row.get("note") or "").strip()[:200],
            })
        return cleaned

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        machine = cleaned.get("machine")
        product = cleaned.get("product")
        subgroup = cleaned.get("subgroup")
        if unit and machine and machine.unit_id != unit.id:
            self.add_error("machine", "دستگاه انتخاب‌شده متعلق به این واحد نیست.")
        if product and subgroup and product.subgroup_id != subgroup.id:
            # Auto-align when product drives subgroup; only error if both set and conflict
            # after user intentionally filtered — still auto-fix from product.
            cleaned["subgroup"] = product.subgroup
        elif product and not subgroup:
            cleaned["subgroup"] = product.subgroup
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.mold_change_date = self.cleaned_data["mold_change_date"]
        obj.production_days = self.cleaned_data.get("production_days") or []
        subgroup = self.cleaned_data.get("subgroup")
        if subgroup is None and obj.product_id:
            obj.subgroup = obj.product.subgroup
        elif subgroup is not None:
            obj.subgroup = subgroup
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
        fields = ["production_type", "active_cavities", "quantity", "cycle"]
        widgets = {
            "production_type": combo(),
            "active_cavities": EmptyZeroNumberInput(attrs={"class": "input", "min": "1"}),
            "quantity": EmptyZeroNumberInput(attrs={"class": "input", "min": "0"}),
            "cycle": EmptyZeroNumberInput(attrs={"class": "input", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["production_type"].required = False
        self.fields["production_type"].empty_label = "——"
        for name in ("quantity", "cycle", "active_cavities"):
            field = self.fields[name]
            field.required = False
            if not self.is_bound:
                current = getattr(self.instance, name, None) if self.instance else None
                if name == "active_cavities":
                    if not self.instance.pk or current in (0, None):
                        field.initial = None
                elif not self.instance.pk or current in (0, None):
                    field.initial = None
        self.fields["active_cavities"].label = "تعداد حفره"
        style_fields(self)

    def clean_quantity(self):
        return self.cleaned_data.get("quantity") or 0

    def clean_cycle(self):
        return self.cleaned_data.get("cycle") or 0

    def clean_active_cavities(self):
        return self.cleaned_data.get("active_cavities") or 0

    def is_empty_row(self) -> bool:
        cd = getattr(self, "cleaned_data", None) or {}
        return not (
            cd.get("production_type")
            or (cd.get("quantity") or 0)
            or (cd.get("cycle") or 0)
            or (cd.get("active_cavities") or 0)
        )

    def clean(self):
        cleaned = super().clean()
        ptype = cleaned.get("production_type")
        qty = cleaned.get("quantity") or 0
        cycle = cleaned.get("cycle") or 0
        cavities = cleaned.get("active_cavities") or 0
        # Completely empty spare row is fine.
        if not ptype and not qty and not cycle and not cavities:
            return cleaned
        # Partial/started row: cavities, quantity, cycle are always required.
        # نوع تولید is enforced at formset level only when 2+ rows are filled.
        if cavities < 1:
            self.add_error("active_cavities", "تعداد حفره الزامی است.")
        if qty < 1:
            self.add_error("quantity", "مقدار تولید الزامی است.")
        if cycle < 1:
            self.add_error("cycle", "سیکل تولید الزامی است.")
        return cleaned


class WeeklyPlanLineFormSetBase(forms.BaseInlineFormSet):
    """Validate production rows: one row may omit نوع تولید; 2+ rows all need it."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        filled = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data is None:
                continue
            if form.is_empty_row():
                continue
            filled.append(form)
        if not filled:
            # Prefer field errors so the UI paints red borders (not only a toast).
            target = self.forms[0] if self.forms else None
            if target is not None:
                target.add_error("active_cavities", "تعداد حفره الزامی است.")
                target.add_error("quantity", "مقدار تولید الزامی است.")
                target.add_error("cycle", "سیکل تولید الزامی است.")
            else:
                raise forms.ValidationError(
                    "ردیف تولید را کامل کنید: تعداد حفره، مقدار تولید و سیکل تولید الزامی است."
                )
            return
        if len(filled) >= 2:
            for form in filled:
                if not form.cleaned_data.get("production_type"):
                    form.add_error(
                        "production_type",
                        "وقتی بیش از یک ردیف تولید دارید، نوع تولید همه ردیف‌ها الزامی است.",
                    )


WeeklyPlanLineFormSet = inlineformset_factory(
    WeeklyPlanItem,
    WeeklyPlanLine,
    form=WeeklyPlanLineForm,
    formset=WeeklyPlanLineFormSetBase,
    fields=["production_type", "active_cavities", "quantity", "cycle"],
    extra=1,
    can_delete=False,
)
