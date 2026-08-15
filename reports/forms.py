from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.permissions import get_profile

from .columns import COLUMN_GROUPS, available_keys
from .models import DataSource, PrintForm, SavedReport

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
    columns = forms.MultipleChoiceField(
        label="ستون‌های گزارش (به ترتیب انتخاب)",
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    viewers = forms.ModelMultipleChoiceField(
        label="کاربرانی که می‌توانند گزارش را ببینند",
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    is_standard = forms.BooleanField(
        label="ایجاد گزارش استاندارد (قابل مشاهده برای همه)",
        required=False,
    )

    class Meta:
        model = SavedReport
        fields = ["title", "number", "data_source", "columns", "viewers", "is_standard"]
        labels = {
            "title": "عنوان گزارش",
            "number": "شماره گزارش",
            "data_source": "منبع داده اصلی",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = get_profile(user) if user else None
        source = (
            self.data.get("data_source")
            or self.initial.get("data_source")
            or getattr(self.instance, "data_source", None)
            or DataSource.FITTING
        )
        keys = sorted(available_keys(source))
        choices = []
        for group in COLUMN_GROUPS:
            if group["id"] == source or group["id"] == "file":
                choices.extend(group["columns"])
        seen = set()
        unique = []
        for key, label in choices:
            if key not in seen:
                seen.add(key)
                unique.append((key, label))
        self.fields["columns"].choices = unique or [(k, k) for k in keys]

        qs = User.objects.filter(is_active=True).exclude(pk=user.pk if user else None).order_by("username")
        self.fields["viewers"].queryset = qs

        if not (profile and profile.is_manager):
            self.fields["is_standard"].widget = forms.HiddenInput()
            self.fields["is_standard"].initial = False

        if self.instance and self.instance.pk and self.instance.columns:
            self.fields["columns"].initial = list(self.instance.columns)

        self.column_groups = [
            g for g in COLUMN_GROUPS if g["id"] == source or g["id"] == "file"
        ]
        _style_fields(self)

    def clean_number(self):
        number = self.cleaned_data["number"].strip()
        owner = self.user
        if self.instance and self.instance.pk:
            owner = self.instance.owner
        qs = SavedReport.objects.filter(owner=owner, number=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("شماره گزارش وجود دارد")
        return number

    def clean_columns(self):
        cols = self.cleaned_data.get("columns") or []
        source = self.cleaned_data.get("data_source") or DataSource.FITTING
        allowed = available_keys(source)
        invalid = [c for c in cols if c not in allowed]
        if invalid:
            raise ValidationError("برخی ستون‌های انتخاب‌شده برای این منبع معتبر نیستند.")
        if not cols:
            raise ValidationError("حداقل یک ستون انتخاب کنید.")
        return list(cols)

    def clean_is_standard(self):
        value = self.cleaned_data.get("is_standard")
        profile = get_profile(self.user) if self.user else None
        if value and not (profile and profile.is_manager):
            raise ValidationError("فقط مدیر می‌تواند گزارش استاندارد ایجاد کند.")
        return bool(value)


class SendReportForm(forms.Form):
    recipient = forms.ModelChoiceField(
        label="کاربر مقصد",
        queryset=User.objects.none(),
        required=True,
    )
    title = forms.CharField(label="عنوان گزارش", max_length=200)
    number = forms.CharField(label="شماره گزارش", max_length=60)
    sent_at = forms.CharField(
        label="زمان ارسال (شمسی)",
        required=False,
        widget=forms.TextInput(attrs={"data-jdp": "1", "autocomplete": "off"}),
        help_text="در صورت خالی بودن، زمان فعلی ثبت می‌شود.",
    )

    def __init__(self, *args, sender=None, report=None, **kwargs):
        self.sender = sender
        self.report = report
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(is_active=True)
        if sender:
            qs = qs.exclude(pk=sender.pk)
        self.fields["recipient"].queryset = qs.order_by("username")
        if report:
            self.fields["title"].initial = report.title
            self.fields["number"].initial = report.number
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        recipient = cleaned.get("recipient")
        number = (cleaned.get("number") or "").strip()
        cleaned["number"] = number
        if recipient and number:
            if SavedReport.objects.filter(owner=recipient, number=number).exists():
                self.add_error("number", "شماره گزارش وجود دارد")
        return cleaned


class PrintFormForm(forms.ModelForm):
    viewers = forms.ModelMultipleChoiceField(
        label="کاربرانی که می‌توانند فرم را ببینند",
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    is_standard = forms.BooleanField(
        label="ایجاد فرم استاندارد (قابل مشاهده برای همه)",
        required=False,
    )
    frames_json = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = PrintForm
        fields = [
            "title",
            "number",
            "page_width_mm",
            "page_height_mm",
            "viewers",
            "is_standard",
        ]
        labels = {
            "title": "عنوان فرم",
            "number": "شماره فرم",
            "page_width_mm": "عرض صفحه (میلی‌متر)",
            "page_height_mm": "ارتفاع صفحه (میلی‌متر)",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = get_profile(user) if user else None
        qs = User.objects.filter(is_active=True).exclude(pk=user.pk if user else None).order_by("username")
        self.fields["viewers"].queryset = qs
        if not (profile and profile.is_manager):
            self.fields["is_standard"].widget = forms.HiddenInput()
            self.fields["is_standard"].initial = False
        if self.instance and self.instance.pk:
            import json

            self.fields["frames_json"].initial = json.dumps(
                self.instance.frames or [], ensure_ascii=False
            )
        _style_fields(self)

    def clean_number(self):
        number = self.cleaned_data["number"].strip()
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
        import json

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
                    "x": int(item.get("x") or 10),
                    "y": int(item.get("y") or 10),
                    "width": int(item.get("width") or 80),
                    "height": int(item.get("height") or 24),
                }
            )
        return cleaned


class SendPrintFormForm(forms.Form):
    recipient = forms.ModelChoiceField(
        label="کاربر مقصد",
        queryset=User.objects.none(),
        required=True,
    )
    title = forms.CharField(label="عنوان فرم", max_length=200)
    number = forms.CharField(label="شماره فرم", max_length=60)
    sent_at = forms.CharField(
        label="زمان ارسال (شمسی)",
        required=False,
        widget=forms.TextInput(attrs={"data-jdp": "1", "autocomplete": "off"}),
    )

    def __init__(self, *args, sender=None, form_obj=None, **kwargs):
        self.sender = sender
        self.form_obj = form_obj
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(is_active=True)
        if sender:
            qs = qs.exclude(pk=sender.pk)
        self.fields["recipient"].queryset = qs.order_by("username")
        if form_obj:
            self.fields["title"].initial = form_obj.title
            self.fields["number"].initial = form_obj.number
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        recipient = cleaned.get("recipient")
        number = (cleaned.get("number") or "").strip()
        cleaned["number"] = number
        if recipient and number:
            if PrintForm.objects.filter(owner=recipient, number=number).exists():
                self.add_error("number", "شماره فرم وجود دارد")
        return cleaned
