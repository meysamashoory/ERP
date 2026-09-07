from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.core.exceptions import ValidationError

from reports.columns import get_column_groups

from .models import PrintForm, ReportParameterDef, SavedReport

PARAM_CODE_UNIQUE_MSG = "کد پارامتر باید یکتا باشد و نمونه مشابه در سامانه نباشد."


class HideRelatedWidgetIconsMixin:
    """Keep FK dropdowns, but drop add/change/view shortcut icons."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        widget = getattr(formfield, "widget", None)
        if isinstance(widget, RelatedFieldWidgetWrapper):
            widget.can_add_related = False
            widget.can_change_related = False
            widget.can_delete_related = False
            widget.can_view_related = False
        return formfield


class OwnedRecordAdminMixin(HideRelatedWidgetIconsMixin):
    """Owner stays editable; creator is set once and never changed."""

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and "created_by" not in readonly:
            readonly.append("created_by")
        return readonly

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if obj is None and "created_by" not in exclude:
            exclude.append("created_by")
        return exclude

    def save_model(self, request, obj, form, change):
        if not change or not getattr(obj, "created_by_id", None):
            obj.created_by = request.user
        else:
            original = type(obj).objects.filter(pk=obj.pk).only("created_by").first()
            if original is not None:
                obj.created_by = original.created_by
        super().save_model(request, obj, form, change)


class ReportParameterDefForm(forms.ModelForm):
    source_key = forms.ChoiceField(
        required=False,
        label="فیلد منابع",
        help_text="اگر منبعی انتخاب شود پارامتر فقط در همان منبع معنا دارد؛ خالی یعنی همه منابع.",
    )

    class Meta:
        model = ReportParameterDef
        fields = (
            "code",
            "label",
            "kind",
            "source_key",
            "sample_value",
            "is_active",
            "order",
        )
        error_messages = {
            "code": {"unique": PARAM_CODE_UNIQUE_MSG},
        }
        help_texts = {
            "code": "فقط حروف انگلیسی، عدد، خط تیره و زیرخط. باید در کل سامانه یکتا باشد.",
            "sample_value": (
                "اولین باری که پارامتر ساخته می‌شود این مقدار نمایش داده می‌شود. "
                "پس از اعمال در گزارش، همین مقدار پیش‌فرض به‌روز می‌شود."
            ),
            "kind": (
                "تاریخ روز به‌صورت فشرده شمسی مثل ۱۴۰۵۰۷۱۶ (همان ۱۴۰۵/۰۷/۱۶) است. "
                "سال فقط سال شمسی را در نظر می‌گیرد."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        groups = []
        try:
            groups = get_column_groups()
        except Exception:
            groups = []
        choices = [("", "همه منابع")]
        seen: set[str] = set()
        for group in groups:
            gid = str(group.get("id") or "").strip()
            if not gid or gid in seen:
                continue
            seen.add(gid)
            choices.append((gid, str(group.get("label") or gid)))
        current = ""
        if self.instance and self.instance.pk:
            current = str(self.instance.source_key or "").strip()
        if current and current not in seen:
            choices.append((current, current))
        self.fields["source_key"].choices = choices

    def clean_code(self):
        code = str(self.cleaned_data.get("code") or "").strip()
        qs = ReportParameterDef.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(PARAM_CODE_UNIQUE_MSG)
        return code


@admin.register(SavedReport)
class SavedReportAdmin(OwnedRecordAdminMixin, admin.ModelAdmin):
    list_display = ("number", "title", "owner", "data_source", "is_standard", "updated_at")
    list_filter = ("is_standard", "data_source")
    search_fields = ("number", "title", "owner__username")
    filter_horizontal = ("viewers",)
    exclude = ("source_report", "sent_at")

    def get_fieldsets(self, request, obj=None):
        fields = [
            "owner",
            "title",
            "description",
            "number",
            "data_source",
            "access_mode",
            "columns",
            "source_links",
            "conditions",
            "entry_data",
            "is_standard",
        ]
        if obj:
            fields.append("created_by")
        fields.append("viewers")
        return ((None, {"fields": tuple(fields)}),)


@admin.register(ReportParameterDef)
class ReportParameterDefAdmin(admin.ModelAdmin):
    form = ReportParameterDefForm
    list_display = ("code", "label", "kind", "source_key", "sample_value", "order", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "label")
    ordering = ("order", "code")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "code",
                    "label",
                    "kind",
                    "source_key",
                    "sample_value",
                    "is_active",
                    "order",
                )
            },
        ),
    )


@admin.register(PrintForm)
class PrintFormAdmin(OwnedRecordAdminMixin, admin.ModelAdmin):
    list_display = ("number", "title", "owner", "is_standard", "updated_at")
    list_filter = ("is_standard",)
    search_fields = ("number", "title", "owner__username")
    filter_horizontal = ("viewers",)
    exclude = ("purpose", "linked_report", "source_form", "sent_at")

    def get_fieldsets(self, request, obj=None):
        fields = [
            "owner",
            "title",
            "description",
            "number",
            "frames",
            "page_width_mm",
            "page_height_mm",
            "page_settings",
            "is_standard",
        ]
        if obj:
            fields.append("created_by")
        fields.append("viewers")
        return ((None, {"fields": tuple(fields)}),)
