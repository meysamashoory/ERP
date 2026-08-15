import json

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.permissions import get_profile

from .columns import COLUMN_GROUPS, normalize_columns
from .models import PrintForm, SavedReport

User = get_user_model()


def _style_fields(form):
    for field in form.fields.values():
        if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.HiddenInput)):
            continue
        field.widget.attrs.setdefault("class", "input")
        if isinstance(field.widget, forms.Select):
            field.widget.attrs.setdefault("data-combo", "1")
            field.widget.attrs.pop("class", None)


class SavedReportForm(forms.ModelForm):
    columns_json = forms.CharField(widget=forms.HiddenInput, required=False)
    is_standard = forms.BooleanField(
        label="ایجاد گزارش استاندارد (قابل مشاهده برای همه)",
        required=False,
    )

    class Meta:
        model = SavedReport
        fields = ["title", "description", "number", "is_standard"]
        labels = {
            "title": "عنوان گزارش",
            "description": "توضیحات",
            "number": "شماره گزارش",
        }
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "توضیح کوتاه (اختیاری)"}),
            "number": forms.NumberInput(attrs={"min": 1, "max": 999, "step": 1}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = get_profile(user) if user else None
        if not (profile and profile.is_manager):
            self.fields["is_standard"].widget = forms.HiddenInput()
            self.fields["is_standard"].initial = False
        if self.instance and self.instance.pk:
            self.fields["columns_json"].initial = json.dumps(
                normalize_columns(self.instance.columns or []), ensure_ascii=False
            )
        else:
            self.fields["columns_json"].initial = "[]"
        self.column_groups = COLUMN_GROUPS
        self.is_manager = bool(profile and profile.is_manager)
        _style_fields(self)

    def clean_number(self):
        number = self.cleaned_data["number"]
        owner = self.user
        if self.instance and self.instance.pk:
            owner = self.instance.owner
        qs = SavedReport.objects.filter(owner=owner, number=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("شماره گزارش وجود دارد")
        return number

    def clean_columns_json(self):
        raw = self.cleaned_data.get("columns_json") or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("ساختار ستون‌ها نامعتبر است.") from exc
        cols = normalize_columns(data)
        if not cols:
            raise ValidationError("حداقل یک ستون انتخاب کنید.")
        return cols

    def clean_is_standard(self):
        value = self.cleaned_data.get("is_standard")
        profile = get_profile(self.user) if self.user else None
        if value and not (profile and profile.is_manager):
            raise ValidationError("فقط مدیر می‌تواند گزارش استاندارد ایجاد کند.")
        return bool(value)

    def primary_source(self) -> str:
        cols = self.cleaned_data.get("columns_json") or []
        for col in cols:
            src = col.get("source") or ""
            if src and src != "file":
                return src
        return "fitting"


class SendOrCopyReportForm(forms.Form):
    title = forms.CharField(label="نام گزارش", max_length=200)
    number = forms.IntegerField(
        label="شماره گزارش",
        min_value=1,
        max_value=999,
        widget=forms.NumberInput(attrs={"min": 1, "max": 999, "step": 1}),
    )
    description = forms.CharField(
        label="توضیحات",
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "توضیح اختیاری"}),
    )
    recipient = forms.ModelChoiceField(
        label="کاربر مقصد",
        queryset=User.objects.none(),
        required=False,
    )

    def __init__(self, *args, sender=None, report=None, mode="send", **kwargs):
        self.sender = sender
        self.report = report
        self.mode = mode
        super().__init__(*args, **kwargs)
        if mode == "copy":
            self.fields["recipient"].required = False
            self.fields["recipient"].widget = forms.HiddenInput()
            if sender:
                self.fields["recipient"].initial = sender.pk
                self.fields["recipient"].queryset = User.objects.filter(pk=sender.pk)
        else:
            self.fields["recipient"].required = True
            qs = User.objects.filter(is_active=True)
            if sender:
                qs = qs.exclude(pk=sender.pk)
            self.fields["recipient"].queryset = qs.order_by("username")
        if report:
            self.fields["title"].initial = report.title
            self.fields["number"].initial = report.number
            self.fields["description"].initial = report.description
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("number")
        if self.mode == "copy":
            owner = self.sender
        else:
            owner = cleaned.get("recipient")
        if owner and number is not None:
            if SavedReport.objects.filter(owner=owner, number=number).exists():
                self.add_error("number", "شماره گزارش وجود دارد")
        return cleaned


class PrintFormForm(forms.ModelForm):
    is_standard = forms.BooleanField(
        label="ایجاد فرم استاندارد (قابل مشاهده برای همه)",
        required=False,
    )
    frames_json = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = PrintForm
        fields = ["title", "description", "number", "page_width_mm", "page_height_mm", "is_standard"]
        labels = {
            "title": "عنوان فرم",
            "description": "توضیحات",
            "number": "شماره فرم",
            "page_width_mm": "عرض صفحه (میلی‌متر)",
            "page_height_mm": "ارتفاع صفحه (میلی‌متر)",
        }
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "توضیح کوتاه (اختیاری)"}),
            "number": forms.NumberInput(attrs={"min": 1, "max": 999, "step": 1}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = get_profile(user) if user else None
        if not (profile and profile.is_manager):
            self.fields["is_standard"].widget = forms.HiddenInput()
            self.fields["is_standard"].initial = False
        if self.instance and self.instance.pk:
            self.fields["frames_json"].initial = json.dumps(
                self.instance.frames or [], ensure_ascii=False
            )
        self.is_manager = bool(profile and profile.is_manager)
        _style_fields(self)

    def clean_number(self):
        number = self.cleaned_data["number"]
        owner = self.user
        if self.instance and self.instance.pk:
            owner = self.instance.owner
        qs = PrintForm.objects.filter(owner=owner, number=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("شماره فرم وجود دارد")
        return number

    def clean_is_standard(self):
        value = self.cleaned_data.get("is_standard")
        profile = get_profile(self.user) if self.user else None
        if value and not (profile and profile.is_manager):
            raise ValidationError("فقط مدیر می‌تواند فرم استاندارد ایجاد کند.")
        return bool(value)

    def clean_frames_json(self):
        raw = self.cleaned_data.get("frames_json") or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("ساختار کادرها نامعتبر است.") from exc
        if not isinstance(data, list):
            raise ValidationError("ساختار کادرها باید لیست باشد.")
        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "id": str(item.get("id") or ""),
                    "label": str(item.get("label") or "")[:120],
                    "kind": str(item.get("kind") or "box")[:40],
                    "x": float(item.get("x") or 10),
                    "y": float(item.get("y") or 10),
                    "width": float(item.get("width") or 80),
                    "height": float(item.get("height") or 24),
                }
            )
        return cleaned


class SendOrCopyPrintFormForm(forms.Form):
    title = forms.CharField(label="نام فرم", max_length=200)
    number = forms.IntegerField(
        label="شماره فرم",
        min_value=1,
        max_value=999,
        widget=forms.NumberInput(attrs={"min": 1, "max": 999, "step": 1}),
    )
    description = forms.CharField(
        label="توضیحات",
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "توضیح اختیاری"}),
    )
    recipient = forms.ModelChoiceField(
        label="کاربر مقصد",
        queryset=User.objects.none(),
        required=False,
    )

    def __init__(self, *args, sender=None, form_obj=None, mode="send", **kwargs):
        self.sender = sender
        self.form_obj = form_obj
        self.mode = mode
        super().__init__(*args, **kwargs)
        if mode == "copy":
            self.fields["recipient"].required = False
            self.fields["recipient"].widget = forms.HiddenInput()
            if sender:
                self.fields["recipient"].initial = sender.pk
                self.fields["recipient"].queryset = User.objects.filter(pk=sender.pk)
        else:
            self.fields["recipient"].required = True
            qs = User.objects.filter(is_active=True)
            if sender:
                qs = qs.exclude(pk=sender.pk)
            self.fields["recipient"].queryset = qs.order_by("username")
        if form_obj:
            self.fields["title"].initial = form_obj.title
            self.fields["number"].initial = form_obj.number
            self.fields["description"].initial = form_obj.description
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("number")
        owner = self.sender if self.mode == "copy" else cleaned.get("recipient")
        if owner and number is not None:
            if PrintForm.objects.filter(owner=owner, number=number).exists():
                self.add_error("number", "شماره فرم وجود دارد")
        return cleaned
