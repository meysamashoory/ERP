"""Daily production logging for fittings (عددی) and pipes (شاخه/کلاف/متر)."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django_jalali.db import models as jmodels

from catalog.models import Machine, Product, ProductionUnit


class BaseProduction(models.Model):
    """Fields shared by every daily production record."""

    unit = models.ForeignKey(
        ProductionUnit, on_delete=models.PROTECT, related_name="+"
    )
    date = jmodels.jDateField("تاریخ")
    planned_quantity = models.PositiveIntegerField("مقدار برنامه‌ریزی‌شده", default=0)
    produced_quantity = models.PositiveIntegerField("مقدار تولیدشده", default=0)
    scrap_quantity = models.PositiveIntegerField("مقدار ضایعات", default=0)
    material_used = models.DecimalField(
        "مواد مصرف‌شده (kg)", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    material_scrap = models.DecimalField(
        "مواد ضایعات‌شده (kg)", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deviation_reason = models.TextField("دلیل انحراف", blank=True)
    description = models.TextField("توضیحات", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def deviation(self) -> int:
        """Produced minus planned (negative means under plan)."""
        return self.produced_quantity - self.planned_quantity


class FittingProduction(BaseProduction):
    """Daily production of a fitting on an injection machine."""

    machine = models.ForeignKey(
        Machine, on_delete=models.PROTECT, related_name="fitting_records"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="fitting_records"
    )
    shot_cycle = models.DecimalField(
        "سیکل تولید یک‌ضرب (ثانیه)", max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", default=1)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "تولید اتصالات"
        verbose_name_plural = "تولید روزانه اتصالات"

    def __str__(self) -> str:
        return f"{self.date} — {self.product.name} ({self.machine})"


class PipeProduction(BaseProduction):
    """Daily production of a pipe/tape on an extruder line.

    Extra fields adapt to the selected pipe type; unused ones stay blank.
    """

    class ThicknessUnit(models.TextChoices):
        MM = "mm", "میلی‌متر"
        MICRON = "micron", "میکرون"

    class SocketLength(models.TextChoices):
        L30_1S = "30cm_1s", "۳۰ سانتی یک‌سر سوکت"
        L50_1S = "50cm_1s", "نیم‌متری یک‌سر سوکت"
        L100_1S = "100cm_1s", "۱ متری یک‌سر سوکت"
        L200_1S = "200cm_1s", "۲ متری یک‌سر سوکت"
        L300_1S = "300cm_1s", "۳ متری یک‌سر سوکت"
        L50_2S = "50cm_2s", "نیم‌متری دوسر سوکت"
        L100_2S = "100cm_2s", "۱ متری دوسر سوکت"
        L300_2S = "300cm_2s", "۳ متری دوسر سوکت"

    line = models.ForeignKey(
        Machine, on_delete=models.PROTECT, related_name="pipe_records"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="pipe_records",
        null=True,
        blank=True,
    )
    pipe_type = models.CharField("نوع محصول", max_length=60)
    size = models.CharField("سایز", max_length=40, blank=True)

    # Push-fit specifics
    socket_length = models.CharField(
        "اندازه لوله (سوکت)", max_length=20, choices=SocketLength.choices, blank=True
    )
    bling_machine = models.ForeignKey(
        Machine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bling_records",
        limit_choices_to={"machine_type": "bling"},
    )

    # Sewage / water pipe specifics
    nominal_pressure = models.CharField("فشار اسمی", max_length=20, blank=True)
    thickness = models.DecimalField(
        "ضخامت", max_digits=8, decimal_places=2, null=True, blank=True
    )
    thickness_unit = models.CharField(
        max_length=10, choices=ThicknessUnit.choices, default=ThicknessUnit.MM
    )
    material_grade = models.CharField(
        "نوع مواد", max_length=20, blank=True, help_text="PE80 / PE100 / PE32 / PE40"
    )

    # Drip pipe / tape specifics
    dripper_spec = models.CharField("مشخصات دریپر", max_length=120, blank=True)
    nominal_flow = models.CharField("دبی اسمی", max_length=40, blank=True)
    dripper_spacing = models.PositiveIntegerField(
        "فاصله دریپر (cm)", null=True, blank=True
    )
    length_meters = models.PositiveIntegerField("متراژ تولید (m)", null=True, blank=True)

    # Corrugated specifics
    color = models.CharField("رنگ", max_length=40, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "تولید لوله"
        verbose_name_plural = "تولید روزانه لوله‌ها"

    def __str__(self) -> str:
        return f"{self.date} — {self.pipe_type} {self.size} ({self.line})"


class ProductionStoppage(models.Model):
    """A stoppage attached to a fitting or pipe production record."""

    reason = models.ForeignKey(
        "catalog.StoppageReason", on_delete=models.PROTECT, related_name="stoppages"
    )
    minutes = models.PositiveIntegerField("مدت توقف (دقیقه)", default=0)
    note = models.CharField("توضیح تکمیلی", max_length=255, blank=True)

    fitting = models.ForeignKey(
        FittingProduction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stoppages",
    )
    pipe = models.ForeignKey(
        PipeProduction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stoppages",
    )

    class Meta:
        verbose_name = "توقف"
        verbose_name_plural = "توقفات"

    def __str__(self) -> str:
        return f"{self.reason} ({self.minutes} دقیقه)"
