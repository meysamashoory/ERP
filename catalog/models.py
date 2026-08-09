"""Master data: production units, machines, product hierarchy, option lists."""

from decimal import Decimal

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
        return f"واحد {self.unit.number} - {self.get_machine_type_display()} {self.number}"


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
