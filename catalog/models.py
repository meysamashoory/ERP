"""Master data: production units, machines, product hierarchy, option lists."""

from decimal import Decimal

from django.conf import settings
from django.db import models


class CountingUnit(models.TextChoices):
    COUNT = "count", "عدد"
    BRANCH = "branch", "شاخه"
    COIL = "coil", "کلاف"
    METER = "meter", "متر"


class ProductionUnit(models.Model):
    """One of the four physical production units of the factory."""

    number = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "واحد تولیدی"
        verbose_name_plural = "واحدهای تولیدی"

    def __str__(self) -> str:
        return f"واحد {self.number}"


class MachineType(models.TextChoices):
    INJECTION = "injection", "تزریق پلاستیک"
    EXTRUDER = "extruder", "اکسترودر لوله"
    BLING = "bling", "بلینگ (سوکت‌زنی)"
    FURNACE = "furnace", "کوره روکش"
    PUNCH_PRINT = "punch_print", "پانچ و پرینت"


class Machine(models.Model):
    """An injection machine, extruder line, bling unit, etc."""

    unit = models.ForeignKey(
        ProductionUnit, on_delete=models.CASCADE, related_name="machines",
        verbose_name="واحد تولیدی",
    )
    machine_type = models.CharField(
        "نوع", max_length=20, choices=MachineType.choices, default=MachineType.INJECTION
    )
    number = models.CharField("شماره", max_length=20, help_text="شماره دستگاه یا خط")
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["unit__number", "machine_type", "number"]
        unique_together = ("unit", "machine_type", "number")
        verbose_name = "دستگاه / خط"
        verbose_name_plural = "دستگاه‌ها و خطوط"

    def __str__(self) -> str:
        return f"{self.get_machine_type_display()} {self.number}"


class ProductKind(models.TextChoices):
    FITTING = "fitting", "اتصالات"
    PIPE = "pipe", "لوله"


class ProductGroup(models.Model):
    """Top-level product group, e.g. اتصالات پیچی، اتصالات فاضلابی، لوله‌ها."""

    name = models.CharField("نام", max_length=120, unique=True)
    kind = models.CharField(
        "دسته", max_length=10, choices=ProductKind.choices, default=ProductKind.FITTING
    )
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "گروه محصول"
        verbose_name_plural = "گروه‌های محصول"

    def __str__(self) -> str:
        return self.name


class ProductSubGroup(models.Model):
    """Sub-group such as پوش‌فیت پروتکت، جوشی فشار قوی، لوله سایلنت."""

    group = models.ForeignKey(
        ProductGroup, on_delete=models.CASCADE, related_name="subgroups",
        verbose_name="گروه",
    )
    name = models.CharField("نام", max_length=120)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["group__order", "order", "name"]
        unique_together = ("group", "name")
        verbose_name = "زیرگروه محصول"
        verbose_name_plural = "زیرگروه‌های محصول"

    def __str__(self) -> str:
        return f"{self.group.name} / {self.name}"


class Product(models.Model):
    """A part or finished good."""

    code = models.CharField("کد", max_length=40, unique=True)
    name = models.CharField("نام قطعه", max_length=200)
    subgroup = models.ForeignKey(
        ProductSubGroup, on_delete=models.PROTECT, related_name="products",
        verbose_name="زیرگروه",
    )
    counting_unit = models.CharField(
        "واحد شمارش", max_length=10, choices=CountingUnit.choices, default=CountingUnit.COUNT
    )

    # Process routing flags described in the specification.
    needs_assembly = models.BooleanField("نیاز به مونتاژ", default=False)
    needs_machining = models.BooleanField("نیاز به تراشکاری", default=False)
    needs_facing = models.BooleanField("نیاز به کفتراشی", default=False)

    # Reference data shown on the planning screen.
    per_carton = models.PositiveIntegerField("تعداد در کارتن", null=True, blank=True)
    per_bag = models.PositiveIntegerField("تعداد در کیسه", null=True, blank=True)
    depot_ceiling = models.PositiveIntegerField("سقف دپو", null=True, blank=True)
    main_cavities = models.PositiveIntegerField("حفره اصلی", null=True, blank=True)
    last_cycle = models.PositiveIntegerField("آخرین سیکل", null=True, blank=True)

    # Weight of one produced unit (grams); used to auto-compute material usage.
    unit_weight_grams = models.DecimalField(
        "وزن هر واحد (گرم)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Inventory snapshots (may also be sourced from uploaded Excel data).
    stock_finished = models.IntegerField("موجودی محصول", default=0)
    stock_unassembled = models.IntegerField("موجودی مونتاژ‌نشده", default=0)
    reorder_level = models.PositiveIntegerField("سطح سفارش مجدد", default=0)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["subgroup", "name"]
        verbose_name = "محصول / قطعه"
        verbose_name_plural = "محصولات و قطعات"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def needs_reorder(self) -> bool:
        return self.reorder_level > 0 and self.stock_finished <= self.reorder_level


class ProductBomLine(models.Model):
    """One BOM component line for a finished/parent product (ساختار BOM)."""

    parent = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="bom_lines",
        verbose_name="محصول والد",
    )
    component_code = models.CharField("کد جزء", max_length=40, blank=True)
    component_name = models.CharField("نام جزء", max_length=200)
    quantity = models.DecimalField("مقدار", max_digits=14, decimal_places=4, default=Decimal("1"))
    unit = models.CharField("واحد", max_length=40, blank=True, default="عدد")
    notes = models.CharField("توضیحات", max_length=255, blank=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["parent__code", "order", "id"]
        verbose_name = "سطر BOM"
        verbose_name_plural = "ساختار BOM"

    def __str__(self) -> str:
        return f"{self.parent.code} ← {self.component_code or self.component_name}"


class ProductConsumable(models.Model):
    """Consumable / raw material usage per product unit (مواد مصرفی)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="consumables",
        verbose_name="محصول",
    )
    material_code = models.CharField("کد ماده", max_length=40, blank=True)
    material_name = models.CharField("نام ماده", max_length=200)
    quantity_per_unit = models.DecimalField(
        "مقدار به ازای واحد محصول", max_digits=14, decimal_places=4, default=Decimal("0")
    )
    unit = models.CharField("واحد", max_length=40, blank=True, default="گرم")
    notes = models.CharField("توضیحات", max_length=255, blank=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["product__code", "order", "id"]
        verbose_name = "ماده مصرفی"
        verbose_name_plural = "مواد مصرفی"

    def __str__(self) -> str:
        return f"{self.product.code} / {self.material_name}"


class ProductionTypeOption(models.Model):
    """Editable list backing the «نوع تولید» dropdowns."""

    label = models.CharField("عنوان", max_length=60, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "گزینه نوع تولید"
        verbose_name_plural = "گزینه‌های نوع تولید"

    def __str__(self) -> str:
        return self.label


class StoppageReason(models.Model):
    """Editable list backing the «دلیل توقف» dropdowns."""

    label = models.CharField("عنوان", max_length=120, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "دلیل توقف"
        verbose_name_plural = "دلایل توقف"

    def __str__(self) -> str:
        return self.label


class DeviationReason(models.Model):
    """Editable list backing the «دلیل انحراف» dropdowns."""

    label = models.CharField("عنوان", max_length=120, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "دلیل انحراف"
        verbose_name_plural = "دلایل انحراف"

    def __str__(self) -> str:
        return self.label


class ProgramChangeReason(models.Model):
    """Editable list backing the «دلیل تغییر برنامه» dropdowns."""

    label = models.CharField("عنوان", max_length=120, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "دلیل تغییر برنامه"
        verbose_name_plural = "دلایل تغییر برنامه"

    def __str__(self) -> str:
        return self.label


class MoldOption(models.Model):
    """Editable list of mold identifiers («نوع قالب»).

    Lets the same product run on two machines at once with *different* molds.
    """

    label = models.CharField("عنوان", max_length=120, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "نوع قالب"
        verbose_name_plural = "انواع قالب"

    def __str__(self) -> str:
        return self.label


class PlanningInsightField(models.Model):
    """Configurable metric shown in the glass insight strip on planning.

    Values are resolved at runtime from either the product catalog, the latest
    saved production record, or (later) a mapped file/Excel column.
    """

    class Source(models.TextChoices):
        PRODUCT = "product", "اطلاعات کالا (کاتالوگ)"
        LAST_PRODUCTION = "last_production", "آخرین تولید ذخیره‌شده"
        FILE_COLUMN = "file_column", "ستون فایل / داده خارجی"

    # Keys the insight resolver understands for each source.
    PRODUCT_KEYS = (
        ("last_cycle", "آخرین سیکل (کاتالوگ)"),
        ("main_cavities", "حفره اصلی"),
        ("per_carton", "تعداد در کارتن"),
        ("per_bag", "تعداد در کیسه"),
        ("depot_ceiling", "سقف دپو"),
        ("stock_finished", "موجودی محصول"),
        ("unit_weight_grams", "وزن واحد (گرم)"),
    )
    LAST_PRODUCTION_KEYS = (
        ("shot_cycle", "آخرین سیکل تولیدشده"),
        ("machine_unit", "آخرین دستگاه و واحد"),
        ("active_cavities", "تعداد حفره فعال"),
        ("produced_quantity", "آخرین مقدار تولید"),
        ("date", "آخرین تاریخ تولید"),
    )

    label = models.CharField("عنوان نمایشی", max_length=120)
    source = models.CharField("منبع داده", max_length=20, choices=Source.choices)
    source_key = models.CharField(
        "کلید / ستون",
        max_length=80,
        help_text="برای کاتالوگ/تولید یکی از کلیدهای شناخته‌شده؛ برای فایل نام ستون.",
    )
    order = models.PositiveSmallIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("نمایش در صفحه", default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "فیلد اطلاعات برنامه‌ریزی"
        verbose_name_plural = "فیلدهای اطلاعات برنامه‌ریزی (نوار شیشه‌ای)"

    def __str__(self) -> str:
        return self.label


class PlanningDisplaySettings(models.Model):
    """Singleton-style settings for the planning detail glass strip and matrix.

    Manage via «مدیریت داده‌ها». Prefer a single row; ``load()`` returns the first
    row or sensible defaults.
    """

    height_coefficient = models.DecimalField(
        "ضریب ارتفاع کادر آبی",
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text="مثلاً ۱٫۲ یعنی ارتفاع کادر آبی ۲۰٪ بیشتر از حالت پایه.",
    )
    matrix_unit_numbers = models.CharField(
        "واحدهای جدول ماتریس",
        max_length=40,
        default="1,2,4",
        help_text="شماره واحدها با ویرگول؛ مثلاً ۱,۲,۴",
    )
    show_group_breakdown = models.BooleanField(
        "نمایش تفکیک گروه در کادر آبی",
        default=True,
        help_text="زیر هر واحد، تعداد قالب هر گروه محصول نمایش داده شود.",
    )

    class Meta:
        verbose_name = "تنظیمات نمایش برنامه‌ریزی"
        verbose_name_plural = "تنظیمات نمایش برنامه‌ریزی (کادر آبی و ماتریس)"

    def __str__(self) -> str:
        return f"ضریب ارتفاع {self.height_coefficient} · واحدها {self.matrix_unit_numbers}"

    @classmethod
    def load(cls) -> "PlanningDisplaySettings":
        obj = cls.objects.first()
        if obj is None:
            obj = cls(height_coefficient=1, matrix_unit_numbers="1,2,4", show_group_breakdown=True)
        return obj

    def unit_numbers(self) -> list[int]:
        nums: list[int] = []
        for part in (self.matrix_unit_numbers or "").replace("،", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                nums.append(int(part))
            except ValueError:
                continue
        return nums or [1, 2, 4]

class ProgramUidScheme(models.Model):
    """Active law for building the planning program UID (شناسه برنامه).

    Managed via «مدیریت داده‌ها». Digits and base year can be redefined here;
    ``segments_json`` documents each segment for future custom schemes.
    """

    name = models.CharField("نام قانون", max_length=120, default="قانون اصلی ۱۴ رقمی")
    is_active = models.BooleanField("فعال", default=True)
    base_year = models.PositiveIntegerField(
        "سال مبدأ شمسی",
        default=1370,
        help_text="کد سال = سال برنامه‌ریزی − مبدأ + ۱ (مثلاً ۱۴۰۵ با مبدأ ۱۳۷۰ → ۳۶).",
    )
    year_digits = models.PositiveSmallIntegerField("ارقام کد سال", default=2)
    program_digits = models.PositiveSmallIntegerField("ارقام شماره برنامه", default=3)
    unit_digits = models.PositiveSmallIntegerField("ارقام واحد", default=1)
    machine_digits = models.PositiveSmallIntegerField("ارقام دستگاه", default=2)
    date_sum_digits = models.PositiveSmallIntegerField("ارقام جمع روزها", default=3)
    production_type_digits = models.PositiveSmallIntegerField("ارقام نوع تولید", default=1)
    mold_row_digits = models.PositiveSmallIntegerField("ارقام ردیف قالب", default=2)
    segments_json = models.JSONField(
        "تعریف قطعات شناسه",
        default=list,
        blank=True,
        help_text="ساختار قطعات برای مستندسازی و بازتعریف آینده.",
    )
    notes = models.TextField(
        "توضیحات",
        blank=True,
        help_text="شرح قانون برای اپراتور / برنامه‌نویس.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قانون شناسه برنامه"
        verbose_name_plural = "قانون شناسه برنامه (بازتعریف)"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.segments_json:
            from planning.uid import DEFAULT_SEGMENTS
            self.segments_json = list(DEFAULT_SEGMENTS)
        super().save(*args, **kwargs)
        if self.is_active:
            type(self).objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)

    @classmethod
    def load(cls) -> "ProgramUidScheme":
        obj = cls.objects.filter(is_active=True).first() or cls.objects.first()
        if obj is None:
            from planning.uid import DEFAULT_SEGMENTS
            obj = cls(
                name="قانون اصلی ۱۴ رقمی",
                is_active=True,
                base_year=1370,
                segments_json=list(DEFAULT_SEGMENTS),
                notes=(
                    "YY=سال−۱۳۷۰+۱ | PPP=شماره برنامه | U=واحد | MM=دستگاه | "
                    "DDD=جمع آفست اکسل تاریخ برنامه و تعویض قالب | T=نوع تولید | RR=ردیف قالب"
                ),
            )
        return obj

    @property
    def total_digits(self) -> int:
        return (
            self.year_digits
            + self.program_digits
            + self.unit_digits
            + self.machine_digits
            + self.date_sum_digits
            + self.production_type_digits
            + self.mold_row_digits
        )


class SystemAlarm(models.Model):
    """Serious (and optionally advisory) alarms for «مدیریت داده‌ها»."""

    class Severity(models.TextChoices):
        SERIOUS = "serious", "جدی"
        ADVISORY = "advisory", "پیشنهادی"

    class Status(models.TextChoices):
        OPEN = "open", "باز"
        REVIEWED = "reviewed", "بررسی‌شده"
        CLEARED = "cleared", "پاک‌شده"

    class Kind(models.TextChoices):
        UID_DUPLICATE = "uid_duplicate", "تکرار شناسه برنامه"
        DATA_TRANSFER = "data_transfer", "انتقال داده اکسل"
        PRODUCTION_CONFLICT = "production_conflict", "تداخل تولید / سوابق"
        OTHER = "other", "سایر"

    severity = models.CharField(
        "سطح", max_length=12, choices=Severity.choices, default=Severity.SERIOUS, db_index=True
    )
    kind = models.CharField(
        "نوع", max_length=40, choices=Kind.choices, default=Kind.OTHER, db_index=True
    )
    status = models.CharField(
        "وضعیت", max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    title = models.CharField("عنوان", max_length=200)
    message = models.TextField("شرح")
    suggestion = models.TextField(
        "پیشنهاد اصلاح",
        blank=True,
        help_text="برای آلارم‌های جدی (مثل شناسه) راه‌حل پیشنهادی اینجا ثبت می‌شود.",
    )
    details = models.JSONField("جزئیات", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="بررسی‌کننده",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "آلارم سیستم"
        verbose_name_plural = "آلارم‌های سیستم (بررسی و پاک‌سازی)"

    def __str__(self) -> str:
        return f"[{self.get_severity_display()}] {self.title}"

    def mark_reviewed(self, user=None) -> None:
        from django.utils import timezone
        self.status = self.Status.REVIEWED
        self.reviewed_at = timezone.now()
        if user is not None:
            self.reviewed_by = user
        self.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    def mark_cleared(self, user=None) -> None:
        from django.utils import timezone
        self.status = self.Status.CLEARED
        self.reviewed_at = timezone.now()
        if user is not None:
            self.reviewed_by = user
        self.save(update_fields=["status", "reviewed_at", "reviewed_by"])


class ExcelUpload(models.Model):
    """Imported workbook container shown under «فایل‌های اکسل»."""

    title = models.CharField("نام فایل", max_length=200)
    file = models.FileField(
        "فایل اکسل",
        upload_to="excel_uploads/%Y/%m/",
        blank=True,
        null=True,
        help_text="فرمت‌های رایج: .xlsx ، .xlsm ، .csv",
    )
    original_name = models.CharField("نام اصلی فایل", max_length=255, blank=True)
    notes = models.TextField("توضیحات", blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="بارگذارنده",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "فایل اکسل"
        verbose_name_plural = "فایل‌های اکسل"

    def __str__(self) -> str:
        return self.title or self.original_name or f"اکسل #{self.pk}"

    @property
    def table_count(self) -> int:
        return self.tables.count()

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = getattr(self.file, "name", "") or ""
            self.original_name = self.original_name.replace("\\", "/").split("/")[-1]
        super().save(*args, **kwargs)


class ExcelTable(models.Model):
    """One imported sheet/table from an Excel workbook (editable grid)."""

    upload = models.ForeignKey(
        ExcelUpload,
        on_delete=models.CASCADE,
        related_name="tables",
        verbose_name="فایل",
    )
    name = models.CharField("نام جدول", max_length=200)
    sheet_name = models.CharField("نام شیت اصلی", max_length=200, blank=True)
    headers = models.JSONField("ستون‌ها", default=list, blank=True)
    rows = models.JSONField("ردیف‌ها", default=list, blank=True)
    layout = models.JSONField(
        "چیدمان گرید",
        default=dict,
        blank=True,
        help_text="عرض ستون‌ها و ارتفاع ردیف‌ها برای نمایش شبیه اکسل",
    )
    order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "جدول اکسل"
        verbose_name_plural = "جداول اکسل"

    def __str__(self) -> str:
        return self.name

    @property
    def source_id(self) -> str:
        return f"excel_table_{self.pk}"

    @property
    def row_count(self) -> int:
        return len(self.rows) if isinstance(self.rows, list) else 0

    @property
    def column_count(self) -> int:
        return len(self.headers) if isinstance(self.headers, list) else 0

    def column_defs(self) -> list[tuple[str, str]]:
        """(key, label) pairs for report source picker."""
        headers = self.headers if isinstance(self.headers, list) else []
        out = []
        for i, h in enumerate(headers):
            label = str(h or f"ستون {i + 1}")[:120]
            out.append((f"col_{i}", label))
        return out

