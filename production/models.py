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
        ProductionUnit, on_delete=models.PROTECT, related_name="+", verbose_name="واحد تولیدی"
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
        Machine, on_delete=models.PROTECT, related_name="fitting_records", verbose_name="دستگاه"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="fitting_records", verbose_name="نام محصول"
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
        L200_2S = "200cm_2s", "۲ متری دوسر سوکت"
        L300_2S = "300cm_2s", "۳ متری دوسر سوکت"

    line = models.ForeignKey(
        Machine, on_delete=models.PROTECT, related_name="pipe_records", verbose_name="خط"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="pipe_records",
        null=True,
        blank=True,
        verbose_name="نام محصول",
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
        verbose_name="دستگاه بلینگ",
    )

    # Sewage / water pipe specifics
    nominal_pressure = models.CharField("فشار اسمی", max_length=20, blank=True)
    thickness = models.DecimalField(
        "ضخامت", max_digits=8, decimal_places=2, null=True, blank=True
    )
    thickness_unit = models.CharField(
        "واحد ضخامت", max_length=10, choices=ThicknessUnit.choices, default=ThicknessUnit.MM
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


class ProductionProgram(models.Model):
    """Execution state of one approved weekly-plan item (a mold-change program).

    Created when its plan is approved; driven through its lifecycle by the
    «تعیین وضعیت» control.
    """

    class Status(models.TextChoices):
        AWAITING = "awaiting", "در انتظار تولید"
        RUNNING = "running", "در حال تولید"
        TEMP_STOP = "temp_stop", "توقف موقت"
        FINISHED = "finished", "اتمام تولید"

    class ChangeType(models.TextChoices):
        SETUP = "setup", "راه‌اندازی"
        CHANGE = "change", "تغییر برنامه"

    item = models.OneToOneField(
        "planning.WeeklyPlanItem", on_delete=models.CASCADE, related_name="program"
    )
    status = models.CharField(
        "وضعیت", max_length=12, choices=Status.choices, default=Status.AWAITING
    )
    change_type = models.CharField(
        "نوع شروع", max_length=8, choices=ChangeType.choices, blank=True
    )
    change_reason = models.ForeignKey(
        "catalog.ProgramChangeReason", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="دلیل تغییر برنامه",
    )
    # Which production line (نوع تولید) is being run: 1 = نوع اول, 2 = نوع دوم.
    production_type = models.PositiveSmallIntegerField("نوع تولید", default=1)
    mold = models.ForeignKey(
        "catalog.MoldOption", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="انتخاب قالب",
    )

    start_date = jmodels.jDateField("تاریخ شروع", null=True, blank=True)
    start_time = models.TimeField("ساعت شروع", null=True, blank=True)
    stop_date = jmodels.jDateField("تاریخ پایان/توقف", null=True, blank=True)
    stop_time = models.TimeField("ساعت پایان/توقف", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "برنامه تولید"
        verbose_name_plural = "برنامه‌های تولید"

    def __str__(self) -> str:
        return f"{self.resolved_uid} — {self.item.product.name}"

    # --- helpers -------------------------------------------------------
    @property
    def resolved_uid(self) -> str:
        """UID for the currently selected production type (14-digit scheme)."""
        line = self.line
        if line is not None and getattr(line, "uid", ""):
            return line.uid
        return self.item.uid_for_type(self.production_type or 1)

    @property
    def line(self):
        """The WeeklyPlanLine for the selected production_type (1-based)."""
        lines = list(self.item.lines.all())
        idx = (self.production_type or 1) - 1
        return lines[idx] if 0 <= idx < len(lines) else (lines[0] if lines else None)

    @property
    def default_cycle(self) -> int:
        line = self.line
        return int(line.cycle) if line and line.cycle else int(self.item.product.last_cycle or 0)

    @property
    def machine_label(self) -> str:
        m = self.item.machine
        return f"دستگاه {m.number} واحد {m.unit.number}"

    def start_datetime(self):
        if self.start_date and self.start_time:
            from .timeutils import to_gregorian
            return to_gregorian(self.start_date, self.start_time)
        return None

    def stop_datetime(self):
        if self.stop_date and self.stop_time:
            from .timeutils import to_gregorian
            return to_gregorian(self.stop_date, self.stop_time)
        return None


class ProductionDayEntry(models.Model):
    """Recorded production statistics for one full work-day of a program."""

    program = models.ForeignKey(
        ProductionProgram, on_delete=models.CASCADE, related_name="entries",
        verbose_name="برنامه تولید",
    )
    date = jmodels.jDateField("تاریخ")
    produced_quantity = models.PositiveIntegerField("مقدار تولیدشده (ضرب)", default=0)
    scrap_quantity = models.PositiveIntegerField("مقدار ضایعات", default=0)
    cycle = models.PositiveIntegerField("سیکل یک‌ضرب (ثانیه)", default=0)
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", default=1)

    # Denormalised, computed on save from the shift/time model.
    planned_quantity = models.PositiveIntegerField("مقدار برنامه‌ریزی‌شده (ضرب)", default=0)
    active_seconds = models.PositiveIntegerField("زمان فعال (ثانیه)", default=0)

    deviation_reason = models.ForeignKey(
        "catalog.DeviationReason", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="دلیل انحراف",
    )
    description = models.TextField("توضیحات", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        unique_together = ("program", "date")
        verbose_name = "آمار تولید روزانه"
        verbose_name_plural = "آمار تولید روزانه"

    def __str__(self) -> str:
        return f"{self.program.resolved_uid} — {self.date}"

    @property
    def deviation(self) -> int:
        """Planned minus produced (positive means production is behind plan)."""
        return self.planned_quantity - self.produced_quantity

    def recompute(self):
        from .timeutils import day_active_seconds, expected_shots
        start = self.program.start_datetime()
        stop = self.program.stop_datetime()
        self.active_seconds = day_active_seconds(start, stop, self.date)
        self.planned_quantity = expected_shots(self.active_seconds, self.cycle)

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)


class ProductionHistoryRecord(models.Model):
    """Archived / Excel-imported production history row, sorted by program UID.

    Live planning programs also appear in «سوابق تولید»; this model holds rows
    transferred from Excel (or other imports) that are not yet linked to a
    WeeklyPlanItem / ProductionProgram.
    """

    program_uid = models.CharField("شناسه تعویض", max_length=32, db_index=True)
    plan_number = models.CharField("شماره برنامه", max_length=40, blank=True)
    plan_date = models.DateField("تاریخ برنامه‌ریزی", null=True, blank=True)
    mold_change_date = models.DateField("تاریخ تعویض قالب", null=True, blank=True)
    unit_number = models.PositiveSmallIntegerField("شماره واحد", null=True, blank=True)
    machine_number = models.CharField("شماره دستگاه", max_length=40, blank=True)
    product_code = models.CharField("کد کالا", max_length=80, blank=True)
    product_name = models.CharField("نام جنس", max_length=200, blank=True)
    mold_name = models.CharField("نام قالب", max_length=200, blank=True)
    mold_number = models.CharField("شماره قالب", max_length=80, blank=True)
    unique_code = models.CharField("کد یکتا", max_length=80, blank=True)
    material = models.CharField("مواد", max_length=120, blank=True)
    color = models.CharField("رنگ", max_length=80, blank=True)
    sequence = models.PositiveSmallIntegerField("ترتیب", null=True, blank=True)
    plan_start_date = models.DateField("تاریخ شروع برنامه", null=True, blank=True)
    actual_start_date = models.DateField("تاریخ شروع واقعی", null=True, blank=True)
    actual_end_date = models.DateField("تاریخ پایان تولید", null=True, blank=True)
    planned_qty = models.IntegerField("مقدار تولید برنامه", null=True, blank=True)
    produced_qty = models.IntegerField("مقدار تولید واقعی", null=True, blank=True)
    planned_cycle = models.IntegerField("سیکل تولید برنامه", null=True, blank=True)
    last_cycle = models.IntegerField("آخرین سیکل تولید", null=True, blank=True)
    planned_hours = models.DecimalField(
        "ساعت تولید برنامه", max_digits=10, decimal_places=2, null=True, blank=True
    )
    active_cavities = models.PositiveSmallIntegerField("تعداد حفره فعال", null=True, blank=True)
    last_cavities = models.PositiveSmallIntegerField("آخرین وضعیت حفره", null=True, blank=True)
    scrap_qty = models.IntegerField("ضایعات تولید", null=True, blank=True)
    status = models.CharField("وضعیت", max_length=80, blank=True)
    notes = models.TextField("توضیحات", blank=True)
    source_table_name = models.CharField("نام جدول مبدأ", max_length=200, blank=True)
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="انتقال‌دهنده",
    )
    extra = models.JSONField("اطلاعات تکمیلی", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["program_uid", "id"]
        verbose_name = "سابقه تولید"
        verbose_name_plural = "سوابق تولید (آرشیو)"

    def __str__(self) -> str:
        return f"{self.program_uid} — {self.product_name or self.product_code or '—'}"


class ProductionStoppage(models.Model):
    """A stoppage attached to a fitting or pipe production record."""

    reason = models.ForeignKey(
        "catalog.StoppageReason", on_delete=models.PROTECT, related_name="stoppages",
        verbose_name="دلیل توقف",
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
