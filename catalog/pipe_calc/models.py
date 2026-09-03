"""Lean master data for pipe line production calculations."""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from .constants import LAYER_LABELS, LAYER_SINGLE, LINE_LABELS, LINE_PROTECT


class PipeProductLine(models.Model):
    """One factory product family (پروتکت، جنرال، تیپ، …)."""

    class LayerMode(models.TextChoices):
        SINGLE = "single", "تک‌لایه"
        TRIPLE = "triple", "سه‌لایه"
        CUSTOM = "custom", "سفارشی / بعداً"

    code = models.SlugField("کد خط", max_length=40, unique=True)
    name = models.CharField("نام", max_length=120)
    layer_mode = models.CharField(
        "حالت لایه",
        max_length=20,
        choices=LayerMode.choices,
        default=LayerMode.SINGLE,
    )
    needs_billing = models.BooleanField("نیاز به بلینگ (سوکت‌زنی)", default=False)
    uses_nominal_lengths = models.BooleanField(
        "طول‌های اسمی مشترک (یک‌سر/دوسر سوکت)", default=False
    )
    is_scaffold = models.BooleanField(
        "داربست (جزئیات بعداً)",
        default=False,
        help_text="خط‌هایی که فقط اسکلت دارند تا تنظیمات کامل شود.",
    )
    is_active = models.BooleanField("فعال", default=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    # Line-specific knobs (PE pressure classes, tip dripper spacing, …) without migrations.
    settings = models.JSONField("تنظیمات ویژه", default=dict, blank=True)
    notes = models.TextField("یادداشت", blank=True)

    class Meta:
        ordering = ["order", "code"]
        verbose_name = "خط محصول لوله"
        verbose_name_plural = "خطوط محصول لوله"

    def __str__(self) -> str:
        return self.name or LINE_LABELS.get(self.code, self.code)


class PipeSizeProfile(models.Model):
    """Per-size rates, pack, depot — the main calc inputs for a line."""

    line = models.ForeignKey(
        PipeProductLine,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name="خط",
    )
    size_mm = models.PositiveIntegerField("سایز (mm)")
    line_speed_m_per_min = models.DecimalField(
        "سرعت خط (m/min)",
        max_digits=10,
        decimal_places=3,
        default=Decimal("0"),
    )
    billing_pieces_per_hour = models.DecimalField(
        "ظرفیت بلینگ (عدد/ساعت برای هر سر سوکت)",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        help_text="برای دوسر سوکت زمان بلینگ تقریباً دوبرابر می‌شود.",
    )
    pack_qty = models.PositiveIntegerField("تعداد در بسته", default=0)
    depot_ceiling = models.PositiveIntegerField("سقف دپو (عدد)", default=0)
    stock_on_hand = models.IntegerField(
        "موجودی فعلی (عدد)",
        default=0,
        help_text="اسنپ‌شات سبک؛ می‌تواند از کاتالوگ/حواله همگام شود.",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipe_size_profiles",
        verbose_name="محصول کاتالوگ (اختیاری)",
    )
    material_note = models.CharField("یادداشت مواد", max_length=255, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    # Extra rates for PE / tip / hose without new columns.
    extras = models.JSONField("پارامترهای اضافی", default=dict, blank=True)

    class Meta:
        ordering = ["line__order", "size_mm"]
        unique_together = ("line", "size_mm")
        verbose_name = "پروفایل سایز لوله"
        verbose_name_plural = "پروفایل‌های سایز لوله"

    def __str__(self) -> str:
        return f"{self.line.code} Ø{self.size_mm}"


class PipeLengthCut(models.Model):
    """Nominal length label shared across sizes; actual cut length differs per size."""

    size_profile = models.ForeignKey(
        PipeSizeProfile,
        on_delete=models.CASCADE,
        related_name="length_cuts",
        verbose_name="سایز",
    )
    length_code = models.CharField("کد طول", max_length=20)
    label = models.CharField("نام طول", max_length=80)
    nominal_cm = models.PositiveIntegerField("طول اسمی (cm)")
    cut_length_mm = models.PositiveIntegerField("طول برش واقعی (mm)")
    socket_ends = models.PositiveSmallIntegerField("تعداد سر سوکت", default=1)
    depot_ceiling = models.PositiveIntegerField(
        "سقف دپو (عدد)",
        default=0,
        help_text="سقف دپوی این طول اسمی؛ برای همه محصولات قابل تعریف است.",
    )
    avg_monthly_sales = models.DecimalField(
        "میانگین فروش ماهانه",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    line_speed_m_per_min = models.DecimalField(
        "سرعت تولید خط (m/min)",
        max_digits=10,
        decimal_places=3,
        default=Decimal("0"),
        help_text="اگر صفر باشد از سرعت پروفایل سایز استفاده می‌شود.",
    )
    stock_on_hand = models.IntegerField(
        "موجودی (عدد)",
        default=0,
        help_text="از داده محصولات همگام می‌شود؛ در صورت نیاز قابل ویرایش است.",
    )
    voucher_qty = models.IntegerField(
        "حواله (عدد)",
        default=0,
        help_text="از تب حواله‌های داده محصولات خوانده می‌شود.",
    )
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["size_profile", "nominal_cm", "socket_ends"]
        unique_together = ("size_profile", "length_code")
        verbose_name = "طول برش لوله"
        verbose_name_plural = "طول‌های برش لوله"

    def __str__(self) -> str:
        return f"{self.size_profile} / {self.label}"


class PipeLayerSpec(models.Model):
    """Material share per layer (تک‌لایه یا درونی/میانی/بیرونی)."""

    size_profile = models.ForeignKey(
        PipeSizeProfile,
        on_delete=models.CASCADE,
        related_name="layers",
        verbose_name="سایز",
    )
    layer = models.CharField("لایه", max_length=20, default=LAYER_SINGLE)
    material_code = models.CharField("کد ماده", max_length=40, blank=True)
    material_name = models.CharField("نام ماده", max_length=120, blank=True)
    kg_per_meter = models.DecimalField(
        "kg در متر",
        max_digits=12,
        decimal_places=5,
        default=Decimal("0"),
    )
    share_percent = models.DecimalField(
        "سهم درصد",
        max_digits=6,
        decimal_places=2,
        default=Decimal("100"),
        help_text="برای سه‌لایه جمع سهم‌ها باید حدود ۱۰۰ باشد.",
    )
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["size_profile", "order", "id"]
        unique_together = ("size_profile", "layer")
        verbose_name = "لایه مواد لوله"
        verbose_name_plural = "لایه‌های مواد لوله"

    def __str__(self) -> str:
        return f"{self.size_profile} / {LAYER_LABELS.get(self.layer, self.layer)}"



class PipeCalcRule(models.Model):
    """Configurable production-matrix factors (system data / per line).

    Mostly reads product + BOM; these knobs scale accessories and material mix.
    """

    line = models.ForeignKey(
        PipeProductLine,
        on_delete=models.CASCADE,
        related_name="calc_rules",
        verbose_name="خط",
        null=True,
        blank=True,
        help_text="خالی = قانون سراسری برای همه خطوط ماتریسی.",
    )
    code = models.SlugField("کد قانون", max_length=40)
    name = models.CharField("نام", max_length=120)
    socket_cap_per_socket = models.DecimalField(
        "درپوش سوکت به ازای هر سر",
        max_digits=10,
        decimal_places=4,
        default=Decimal("1"),
    )
    pipe_cap_per_piece = models.DecimalField(
        "درپوش لوله به ازای هر شاخه",
        max_digits=10,
        decimal_places=4,
        default=Decimal("1"),
    )
    spacer_per_piece = models.DecimalField(
        "اسپیسر به ازای هر شاخه",
        max_digits=10,
        decimal_places=4,
        default=Decimal("0"),
    )
    cover_per_piece = models.DecimalField(
        "کاور به ازای هر شاخه",
        max_digits=10,
        decimal_places=4,
        default=Decimal("0"),
    )
    # Extra material-mix multipliers keyed by layer code, e.g. {"inner": 1.0}.
    material_factors = models.JSONField("ضرایب ترکیب مواد", default=dict, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    notes = models.TextField("یادداشت", blank=True)

    class Meta:
        ordering = ["line__order", "code"]
        unique_together = ("line", "code")
        verbose_name = "قانون محاسبه زمان تولید"
        verbose_name_plural = "قوانین محاسبه زمان تولید"

    def __str__(self) -> str:
        scope = self.line.code if self.line_id else "سراسری"
        return f"{scope} / {self.name or self.code}"



# Default line code used when seeding / demos.
DEFAULT_LINE_CODE = LINE_PROTECT
