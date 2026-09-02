"""Weekly production planning for fittings, with a manager-approval workflow."""

from django.conf import settings
from django.db import models
from django_jalali.db import models as jmodels

from catalog.models import Machine, MoldOption, Product, ProductionTypeOption, ProductionUnit, ProductSubGroup


def generate_program_uid() -> str:
    """Placeholder default; real UIDs are assigned via planning.uid after save."""
    import secrets
    return secrets.token_hex(4).upper()


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
        DRAFT = "draft", "در انتظار تأیید"
        APPROVED = "approved", "تأییدشده"

    program_number = models.CharField("شماره برنامه", max_length=30, unique=True)
    date = jmodels.jDateField("تاریخ برنامه‌ریزی", unique=True)
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
        from .utils import format_jdate
        return f"برنامه {self.program_number} — {format_jdate(self.date)}"

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
    mold = models.ForeignKey(
        MoldOption, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="نوع قالب",
    )

    mold_change_weekday = models.IntegerField(
        "روز تعویض قالب", choices=Weekday.choices
    )
    mold_change_date = jmodels.jDateField("تاریخ تعویض قالب")
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", default=1)
    production_days = models.JSONField(
        "روزهای تولید", default=list, blank=True,
        help_text="فهرست {date, shift, note}",
    )

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

    def uid_for_type(self, production_type_index: int = 1) -> str:
        from .uid import uid_for_item
        return uid_for_item(self, production_type_index=production_type_index)

    @property
    def has_production_days(self) -> bool:
        days = self.production_days or []
        if not isinstance(days, list):
            return False
        return any(
            isinstance(d, dict) and str(d.get("date") or "").strip()
            for d in days
        )


class WeeklyPlanLine(models.Model):
    """A repeatable (نوع تولید، قالب، مقدار تولید، سیکل تولید) row on a plan item."""

    item = models.ForeignKey(
        WeeklyPlanItem, on_delete=models.CASCADE, related_name="lines"
    )
    production_type = models.ForeignKey(
        ProductionTypeOption, on_delete=models.PROTECT, related_name="+",
        verbose_name="نوع تولید", null=True, blank=True,
    )
    mold = models.ForeignKey(
        MoldOption, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="انتخاب قالب",
    )
    quantity = models.PositiveIntegerField("مقدار تولید", default=0)
    cycle = models.PositiveIntegerField("سیکل تولید (ثانیه)", default=0)
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره", default=1)
    uid = models.CharField(
        "شناسه ردیف تولید",
        max_length=16,
        blank=True,
        default="",
        db_index=True,
        help_text="شناسه ۱۴ رقمی مخصوص این نوع تولید",
    )

    class Meta:
        verbose_name = "ردیف تولید"
        verbose_name_plural = "ردیف‌های تولید"

    def __str__(self) -> str:
        return f"{self.production_type} — {self.quantity}"

    @property
    def production_hours(self) -> float:
        """Estimated production hours: (qty / cavities) × cycle seconds / 3600."""
        cavities = max(int(self.active_cavities or getattr(self.item, "active_cavities", 1) or 1), 1)
        qty = int(self.quantity or 0)
        cycle = int(self.cycle or 0)
        if qty <= 0 or cycle <= 0:
            return 0.0
        return round((qty / cavities) * cycle / 3600.0, 2)
