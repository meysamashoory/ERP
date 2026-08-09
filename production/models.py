"""Daily production logging for fittings (عددی) and pipes (شاخه/کلاف/متر)."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django_jalali.db import models as jmodels

from catalog.models import Machine, Product, ProductionUnit


def _apply_material_usage(record, product) -> None:
    """Auto-fill material_used/material_scrap (kg) from the product weight.

    material = weight(grams) × quantity / 1000. When no product/weight is
    available the values are left at zero.
    """
    weight = getattr(product, "unit_weight_grams", None) or Decimal("0")
    record.material_used = (Decimal(weight) * record.produced_quantity) / Decimal("1000")
    record.material_scrap = (Decimal(weight) * record.scrap_quantity) / Decimal("1000")


class BaseProduction(models.Model):
    """Fields shared by every daily production record."""

    unit = models.ForeignKey(
        ProductionUnit, on_delete=models.PROTECT, related_name="+"
    )
    date = jmodels.jDateField("تاریخ")
    planned_quantity = models.PositiveIntegerField("مقدار برنامه‌ریزی‌شده", default=0)
    produced_quantity = models.PositiveIntegerField("مقدار تولیدشده", default=0)
    scrap_quantity = models.PositiveIntegerField("مقدار ضایعات", default=0)
    # Material usage is auto-computed from the product weight and quantities
    # (see save()); it is shown only in reports, never entered by hand.
    material_used = models.DecimalField(
        "مواد مصرف‌شده (kg)", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    material_scrap = models.DecimalField(
        "مواد ضایعات‌شده (kg)", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deviation_reason = models.ForeignKey(
        "catalog.DeviationReason",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="دلیل انحراف",
    )
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
    shot_cycle = models.PositiveIntegerField("سیکل تولید یک‌ضرب (ثانیه)", default=0)
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", default=1)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "تولید اتصالات"
        verbose_name_plural = "تولید روزانه اتصالات"

    def __str__(self) -> str:
        return f"{self.date} — {self.product.name} ({self.machine})"

    def save(self, *args, **kwargs):
        _apply_material_usage(self, self.product)
        super().save(*args, **kwargs)


class PipeProduction(BaseProduction):
    """Daily production of a pipe/tape on an extruder line.

    Extra fields adapt to the selected pipe type; unused ones stay blank.
    """

    class ThicknessUnit(models.TextChoices):
        MM = "mm", "میلی‌متر"
        MICRON = "micron", "میکرون"

    class MaterialGrade(models.TextChoices):
        PE80 = "PE80", "PE80"
        PE100 = "PE100", "PE100"
        PE32 = "PE32", "PE32"
        PE40 = "PE40", "PE40"

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
        "نوع مواد", max_length=20, choices=MaterialGrade.choices, blank=True
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
        return f"{self.date} — {self.pipe_type} ({self.line})"

    def save(self, *args, **kwargs):
        # Keep pipe_type in sync with the chosen product's subgroup.
        if self.product_id and self.product.subgroup_id:
            self.pipe_type = self.product.subgroup.name
        _apply_material_usage(self, self.product)
        super().save(*args, **kwargs)


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
