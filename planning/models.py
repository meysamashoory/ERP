"""Weekly production planning for fittings, with a manager-approval workflow."""

import secrets

from django.conf import settings
from django.db import models
from django_jalali.db import models as jmodels

from catalog.models import Machine, Product, ProductionTypeOption, ProductionUnit, ProductSubGroup


def generate_program_uid() -> str:
    """A short, unique, human-referable id for a production program."""
    return secrets.token_hex(4).upper()  # e.g. "9F3A2B10"


PERSIAN_WEEKDAYS = [
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
]


def persian_weekday(jdate) -> str:
    """Return the Persian weekday name for a jdatetime.date (Saturday=0)."""
    try:
        return PERSIAN_WEEKDAYS[jdate.weekday()]
    except (AttributeError, IndexError):
        return ""


class Weekday(models.IntegerChoices):
    SHANBE = 0, "شنبه"
    YEKSHANBE = 1, "یکشنبه"
    DOSHANBE = 2, "دوشنبه"
    SESHANBE = 3, "سه‌شنبه"
    CHAHARSHANBE = 4, "چهارشنبه"
    PANJSHANBE = 5, "پنج‌شنبه"
    JOME = 6, "جمعه"


class WeeklyPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "موقت"
        APPROVED = "approved", "تأییدشده"

    program_number = models.CharField("شماره برنامه", max_length=30, unique=True)
    date = jmodels.jDateField("تاریخ برنامه‌ریزی")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    alarms = models.TextField("هشدارها", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_plans",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_plans",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "برنامه هفتگی"
        verbose_name_plural = "برنامه‌ریزی هفتگی"

    def __str__(self) -> str:
        return f"برنامه {self.program_number} — {self.date}"

    @property
    def weekday_name(self) -> str:
        return persian_weekday(self.date)


class WeeklyPlanItem(models.Model):
    plan = models.ForeignKey(
        WeeklyPlan, on_delete=models.CASCADE, related_name="items"
    )
    subgroup = models.ForeignKey(
        ProductSubGroup, on_delete=models.PROTECT, related_name="+", verbose_name="زیرگروه"
    )
    unit = models.ForeignKey(
        ProductionUnit, on_delete=models.PROTECT, related_name="+", verbose_name="واحد تولیدی"
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.PROTECT, related_name="+", verbose_name="دستگاه"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="+", verbose_name="نام محصول"
    )

    mold_change_weekday = models.IntegerField(
        "روز تعویض قالب", choices=Weekday.choices
    )
    mold_change_date = jmodels.jDateField("تاریخ تعویض قالب")
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", default=1)

    uid = models.CharField(
        "شناسه برنامه", max_length=16, unique=True, default=generate_program_uid,
        editable=False, db_index=True,
    )
    # Sequence position on the same machine within a plan (1 = تولید اول, ...).
    sequence = models.PositiveSmallIntegerField("ترتیب روی دستگاه", default=1)

    history_alarm = models.BooleanField(default=False)

    class Meta:
        verbose_name = "کالای برنامه"
        verbose_name_plural = "کالاهای برنامه"

    def __str__(self) -> str:
        return f"{self.product.name} @ {self.machine}"


class WeeklyPlanLine(models.Model):
    """A repeatable (نوع تولید، مقدار تولید، سیکل تولید) row on a plan item."""

    item = models.ForeignKey(
        WeeklyPlanItem, on_delete=models.CASCADE, related_name="lines"
    )
    production_type = models.ForeignKey(
        ProductionTypeOption, on_delete=models.PROTECT, related_name="+", verbose_name="نوع تولید"
    )
    quantity = models.PositiveIntegerField("مقدار تولید", default=0)
    cycle = models.PositiveIntegerField("سیکل تولید (ثانیه)", default=0)

    class Meta:
        verbose_name = "ردیف تولید"
        verbose_name_plural = "ردیف‌های تولید"

    def __str__(self) -> str:
        return f"{self.production_type} — {self.quantity}"
