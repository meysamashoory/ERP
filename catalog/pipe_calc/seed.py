"""Seed pipe lines: Protect fully; others as editable scaffolds."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from .constants import (
    DEFAULT_BILLING_PIECES_PER_HOUR,
    DEFAULT_DEPOT_CEILING,
    DEFAULT_LINE_SPEED_M_PER_MIN,
    DEFAULT_PACK_QTY,
    DEFAULT_SOCKET_EXTRA_MM,
    GENERAL_SIZES,
    LAYER_INNER,
    LAYER_MIDDLE,
    LAYER_OUTER,
    LAYER_SINGLE,
    LINE_GENERAL,
    LINE_HOSE,
    LINE_LABELS,
    LINE_PC,
    LINE_PE,
    LINE_PROTECT,
    LINE_ROUND_DRIP,
    LINE_ROUND_PLAIN,
    LINE_SILENT,
    LINE_TIP,
    NOMINAL_LENGTHS,
    PROTECT_SIZES,
    SILENT_SIZES,
)
from .models import PipeLayerSpec, PipeLengthCut, PipeProductLine, PipeSizeProfile


def _dec(value: float | int) -> Decimal:
    return Decimal(str(value))


def _cut_mm(nominal_cm: int, socket_ends: int, size_mm: int) -> int:
    extra = DEFAULT_SOCKET_EXTRA_MM.get(size_mm, 25)
    return int(nominal_cm * 10 + extra * max(1, socket_ends))


def _ensure_lengths(profile: PipeSizeProfile) -> None:
    for code, label, nominal_cm, sockets in NOMINAL_LENGTHS:
        PipeLengthCut.objects.update_or_create(
            size_profile=profile,
            length_code=code,
            defaults={
                "label": label,
                "nominal_cm": nominal_cm,
                "cut_length_mm": _cut_mm(nominal_cm, sockets, profile.size_mm),
                "socket_ends": sockets,
                "is_active": True,
            },
        )


def _ensure_size(
    line: PipeProductLine,
    size_mm: int,
    *,
    with_lengths: bool,
    layer_mode: str,
) -> PipeSizeProfile:
    profile, _ = PipeSizeProfile.objects.update_or_create(
        line=line,
        size_mm=size_mm,
        defaults={
            "line_speed_m_per_min": _dec(DEFAULT_LINE_SPEED_M_PER_MIN.get(size_mm, 5)),
            "billing_pieces_per_hour": _dec(
                DEFAULT_BILLING_PIECES_PER_HOUR.get(size_mm, 200)
            ),
            "pack_qty": DEFAULT_PACK_QTY.get(size_mm, 10),
            "depot_ceiling": DEFAULT_DEPOT_CEILING.get(size_mm, 1000),
            "is_active": True,
        },
    )
    if with_lengths:
        _ensure_lengths(profile)

    if layer_mode == PipeProductLine.LayerMode.SINGLE:
        approx_kg = round(0.00012 * (size_mm**1.15), 5)
        PipeLayerSpec.objects.update_or_create(
            size_profile=profile,
            layer=LAYER_SINGLE,
            defaults={
                "material_code": f"PVC-{size_mm}",
                "material_name": f"مواد تک‌لایه Ø{size_mm}",
                "kg_per_meter": _dec(approx_kg),
                "share_percent": _dec(100),
                "order": 0,
            },
        )
    elif layer_mode == PipeProductLine.LayerMode.TRIPLE:
        total_kg = round(0.00014 * (size_mm**1.15), 5)
        shares = (
            (LAYER_INNER, "درونی", Decimal("20"), 0),
            (LAYER_MIDDLE, "میانی", Decimal("60"), 1),
            (LAYER_OUTER, "بیرونی", Decimal("20"), 2),
        )
        for layer, fa_name, share, order in shares:
            kg = (total_kg * float(share) / 100.0)
            PipeLayerSpec.objects.update_or_create(
                size_profile=profile,
                layer=layer,
                defaults={
                    "material_code": f"{line.code.upper()}-{layer[:3].upper()}-{size_mm}",
                    "material_name": f"مواد لایه {fa_name} Ø{size_mm}",
                    "kg_per_meter": _dec(round(kg, 5)),
                    "share_percent": share,
                    "order": order,
                },
            )
    return profile


def _line(
    code: str,
    *,
    order: int,
    layer_mode: str,
    needs_billing: bool,
    uses_nominal: bool,
    scaffold: bool,
    settings: dict | None = None,
    notes: str = "",
) -> PipeProductLine:
    obj, _ = PipeProductLine.objects.update_or_create(
        code=code,
        defaults={
            "name": LINE_LABELS.get(code, code),
            "layer_mode": layer_mode,
            "needs_billing": needs_billing,
            "uses_nominal_lengths": uses_nominal,
            "is_scaffold": scaffold,
            "is_active": True,
            "order": order,
            "settings": settings or {},
            "notes": notes,
        },
    )
    return obj


@transaction.atomic
def seed_pipe_calc_defaults(*, force_rates: bool = False) -> dict[str, int]:
    """Idempotent seed. Returns counts of lines/sizes touched.

    force_rates=False keeps user-edited speeds/depot if profiles already exist
    (update_or_create still refreshes defaults on first create; for existing
    profiles we only fill missing length/layer rows).
    """
    counts = {"lines": 0, "sizes": 0, "lengths": 0, "layers": 0}

    protect = _line(
        LINE_PROTECT,
        order=10,
        layer_mode=PipeProductLine.LayerMode.SINGLE,
        needs_billing=True,
        uses_nominal=True,
        scaffold=False,
        notes="محاسبات کامل: خط تولید + بلینگ + سقف دپو + BOM لایه‌ای.",
    )
    counts["lines"] += 1
    for size in PROTECT_SIZES:
        if force_rates or not PipeSizeProfile.objects.filter(line=protect, size_mm=size).exists():
            _ensure_size(protect, size, with_lengths=True, layer_mode=protect.layer_mode)
        else:
            profile = PipeSizeProfile.objects.get(line=protect, size_mm=size)
            _ensure_lengths(profile)
            if not profile.layers.exists():
                _ensure_size(protect, size, with_lengths=True, layer_mode=protect.layer_mode)
        counts["sizes"] += 1

    for code, sizes, order in (
        (LINE_GENERAL, GENERAL_SIZES, 20),
        (LINE_SILENT, SILENT_SIZES, 30),
    ):
        line = _line(
            code,
            order=order,
            layer_mode=PipeProductLine.LayerMode.TRIPLE,
            needs_billing=True,
            uses_nominal=True,
            scaffold=False,
            notes="سه‌لایه (درونی/میانی/بیرونی)؛ سایز ۴۰ و ۲۰۰ ندارد.",
        )
        counts["lines"] += 1
        for size in sizes:
            if force_rates or not PipeSizeProfile.objects.filter(line=line, size_mm=size).exists():
                _ensure_size(line, size, with_lengths=True, layer_mode=line.layer_mode)
            else:
                profile = PipeSizeProfile.objects.get(line=line, size_mm=size)
                _ensure_lengths(profile)
                if profile.layers.count() < 3:
                    _ensure_size(line, size, with_lengths=True, layer_mode=line.layer_mode)
            counts["sizes"] += 1

    scaffolds = (
        (
            LINE_PE,
            40,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {"pressure_classes": ["PN6", "PN10", "PN16"], "grades": ["PE80", "PE100"]},
            "تنظیمات فشار اسمی و گرید مواد بعداً تکمیل می‌شود.",
        ),
        (
            LINE_TIP,
            50,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {"needs_detail": True, "metrics": ["flow", "spacing_cm", "thickness_micron"]},
            "نوار آبیاری — نیاز به توضیحات مفصل‌تر برای فرمول زمان.",
        ),
        (
            LINE_HOSE,
            60,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {"color_variants": True},
            "خط خرطومی — اسکلت آماده.",
        ),
        (
            LINE_PC,
            70,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {},
            "خط PC — اسکلت آماده.",
        ),
        (
            LINE_ROUND_DRIP,
            80,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {"has_dripper": True},
            "راند دریپردار — اسکلت آماده.",
        ),
        (
            LINE_ROUND_PLAIN,
            90,
            PipeProductLine.LayerMode.CUSTOM,
            False,
            False,
            {"has_dripper": False},
            "راند بدون دریپر — اسکلت آماده.",
        ),
    )
    for code, order, layer_mode, billing, nominal, settings, notes in scaffolds:
        _line(
            code,
            order=order,
            layer_mode=layer_mode,
            needs_billing=billing,
            uses_nominal=nominal,
            scaffold=True,
            settings=settings,
            notes=notes,
        )
        counts["lines"] += 1

    counts["lengths"] = PipeLengthCut.objects.count()
    counts["layers"] = PipeLayerSpec.objects.count()
    return counts
