"""Saved reports and printable forms owned per-user (with optional standard copies)."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
import django_jalali.db.models as jmodels


class DataSource(models.TextChoices):
    FITTING = "fitting", "تولید اتصالات"
    PIPE = "pipe", "تولید لوله"
    PRODUCT = "product", "اطلاعات کالا و موجودی"
    DATA_ENTRY = "data_entry", "ثبت داده"


class ReportAccessMode(models.TextChoices):
    READONLY = "readonly", "گزارش فقط خواندنی"
    EDITABLE = "editable", "گزارش قابل ویرایش"


class SavedReport(models.Model):
    """A report definition owned by one user (or a manager-owned standard report).

    ``columns`` is an ordered JSON list of
    ``{"key", "source", "level", "label"}`` entries (level 1–10).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_reports",
        verbose_name="مالک",
    )
    title = models.CharField("عنوان گزارش", max_length=200)
    description = models.CharField("توضیحات", max_length=300, blank=True, default="")
    number = models.PositiveSmallIntegerField(
        "شماره گزارش",
        validators=[MinValueValidator(1), MaxValueValidator(999)],
    )
    data_source = models.CharField(
        "منبع داده", max_length=20, choices=DataSource.choices, default=DataSource.FITTING
    )
    access_mode = models.CharField(
        "نوع دسترسی",
        max_length=20,
        choices=ReportAccessMode.choices,
        default=ReportAccessMode.READONLY,
    )
    # Ordered: [{"key", "source", "level", "label"}, ...]
    columns = models.JSONField("ستون‌ها", default=list)
    # Join keys across sources: [{"keys": {"fitting": "code", "file": "file_col_1"}}]
    source_links = models.JSONField("ربط منابع", default=list, blank=True)
    # Manual values for «ثبت داده» columns:
    # {"cells": {"sig": {"data_titles": "...", ...}}, "values": {...}}
    entry_data = models.JSONField("داده ثبت‌شده", default=dict, blank=True)
    is_standard = models.BooleanField("گزارش استاندارد", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reports",
        verbose_name="ایجادکننده",
    )
    source_report = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_copies",
        verbose_name="گزارش مبدأ",
    )
    sent_at = jmodels.jDateTimeField("زمان ارسال", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    viewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="viewable_reports",
        verbose_name="کاربران مجاز به مشاهده",
    )

    class Meta:
        ordering = ["number", "id"]
        verbose_name = "گزارش ذخیره‌شده"
        verbose_name_plural = "گزارش‌های ذخیره‌شده"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "number"],
                name="uniq_report_number_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.title}"


class PrintForm(models.Model):
    """Printable form definition with framing/layout for hard-copy use."""

    PURPOSE_WEEKLY = "weekly_planning"
    PURPOSE_PRODUCTION = "production"
    PURPOSE_REPORTS = "reports"
    PURPOSE_CHOICES = [
        (PURPOSE_WEEKLY, "برنامه ریزی هفتگی"),
        (PURPOSE_PRODUCTION, "برنامه های تولید"),
        (PURPOSE_REPORTS, "گزارش ها"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_print_forms",
        verbose_name="مالک",
    )
    title = models.CharField("عنوان فرم", max_length=200)
    description = models.CharField("توضیحات", max_length=300, blank=True, default="")
    number = models.PositiveSmallIntegerField(
        "شماره فرم",
        validators=[MinValueValidator(1), MaxValueValidator(999)],
    )
    purpose = models.CharField(
        "کاربرد فرم",
        max_length=40,
        choices=PURPOSE_CHOICES,
        blank=True,
        default="",
        db_index=True,
    )
    linked_report = models.ForeignKey(
        "SavedReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_print_forms",
        verbose_name="گزارش مرتبط",
    )
    frames = models.JSONField("کادرها و چیدمان", default=list)
    page_width_mm = models.PositiveIntegerField("عرض صفحه (مم)", default=210)
    page_height_mm = models.PositiveIntegerField("ارتفاع صفحه (مم)", default=297)
    page_settings = models.JSONField(
        "تنظیمات صفحه",
        default=dict,
        blank=True,
        help_text="حاشیه چاپ، حساسیت اسنپ لبه و …",
    )
    is_standard = models.BooleanField("فرم استاندارد", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_print_forms",
        verbose_name="ایجادکننده",
    )
    source_form = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_copies",
        verbose_name="فرم مبدأ",
    )
    sent_at = jmodels.jDateTimeField("زمان ارسال", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    viewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="viewable_print_forms",
        verbose_name="کاربران مجاز به مشاهده",
    )

    class Meta:
        ordering = ["number", "id"]
        verbose_name = "فرم چاپی"
        verbose_name_plural = "فرم‌های چاپی"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "number"],
                name="uniq_form_number_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.title}"

    @property
    def purpose_label(self) -> str:
        return dict(self.PURPOSE_CHOICES).get(self.purpose, "")
