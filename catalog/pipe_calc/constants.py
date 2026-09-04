"""Shared constants for pipe production-time calculation lines."""

from __future__ import annotations

from typing import Final

# Product line codes (stable keys; UI labels below / seed).
LINE_PROTECT = "protect"
LINE_GENERAL = "general"
LINE_SILENT = "silent"
LINE_PE_HD = "pe_hd"
LINE_SEWER = "sewer"
LINE_TIP = "tip"
LINE_HOSE = "hose"
LINE_ROUND_DRIP = "round_drip"
LINE_PE_LD = "pe_ld"
LINE_PC = "pc"

# Legacy aliases kept so old seeds/tests keep resolving.
LINE_PE = LINE_PE_HD
LINE_ROUND_PLAIN = "round_plain"  # retired from tabs; kept for migration cleanup

LINE_CODES: Final[tuple[str, ...]] = (
    LINE_PROTECT,
    LINE_GENERAL,
    LINE_SILENT,
    LINE_PE_HD,
    LINE_SEWER,
    LINE_TIP,
    LINE_HOSE,
    LINE_ROUND_DRIP,
    LINE_PE_LD,
    LINE_PC,
)

LINE_LABELS: Final[dict[str, str]] = {
    LINE_PROTECT: "لوله‌های پروتکت",
    LINE_GENERAL: "لوله‌های جنرال سایلنت",
    LINE_SILENT: "لوله‌های سایلنت ۱۰",
    LINE_PE_HD: "لوله‌های پلی‌اتیلن HD",
    LINE_SEWER: "لوله‌های فاضلابی",
    LINE_TIP: "نوار آبیاری (تیپ)",
    LINE_HOSE: "لوله‌های خرطومی",
    LINE_ROUND_DRIP: "لوله‌های راند دریپردار",
    LINE_PE_LD: "لوله‌های پلی‌اتیلن LD",
    LINE_PC: "لوله فلت (PC)",
}

# Lines that share the protect/general/silent depot + production matrix UI.
MATRIX_LINE_CODES: Final[frozenset[str]] = frozenset(
    {LINE_PROTECT, LINE_GENERAL, LINE_SILENT}
)

# Push-fit style sizes (mm).
PROTECT_SIZES: Final[tuple[int, ...]] = (40, 50, 75, 110, 125, 160, 200)
GENERAL_SIZES: Final[tuple[int, ...]] = (50, 75, 110, 125, 160)  # no 40 / 200
SILENT_SIZES: Final[tuple[int, ...]] = GENERAL_SIZES

LAYER_SINGLE = "single"
LAYER_INNER = "inner"
LAYER_MIDDLE = "middle"
LAYER_OUTER = "outer"

LAYER_LABELS: Final[dict[str, str]] = {
    LAYER_SINGLE: "تک‌لایه",
    LAYER_INNER: "لایه درونی",
    LAYER_MIDDLE: "لایه میانی",
    LAYER_OUTER: "لایه بیرونی",
}

# Shared nominal length catalog (naming identical across protect/general/silent).
# code, label, nominal_cm, socket_ends
# After ۳ متری دوسر سوکت, a coupler (رابط) row is appended.
NOMINAL_LENGTHS: Final[tuple[tuple[str, str, int, int], ...]] = (
    ("30cm_1s", "۳۰ سانتی یک‌سر سوکت", 30, 1),
    ("50cm_1s", "۵۰ سانتی یک‌سر سوکت", 50, 1),
    ("100cm_1s", "۱ متری یک‌سر سوکت", 100, 1),
    ("200cm_1s", "۲ متری یک‌سر سوکت", 200, 1),
    ("300cm_1s", "۳ متری یک‌سر سوکت", 300, 1),
    ("50cm_2s", "۵۰ سانتی دوسر سوکت", 50, 2),
    ("100cm_2s", "۱ متری دوسر سوکت", 100, 2),
    ("200cm_2s", "۲ متری دوسر سوکت", 200, 2),
    ("300cm_2s", "۳ متری دوسر سوکت", 300, 2),
    ("coupler", "رابط", 0, 0),
)

LENGTH_COUPLER = "coupler"

# Qty source keys for the post-calc selector (default = first).
QTY_SOURCE_DEDUCT_STOCK = "deduct_stock"  # کسر از دپو (موجودی)
QTY_SOURCE_DEDUCT_REMAINING = "deduct_remaining"  # کسر از دپو (مانده)
QTY_SOURCE_REQUIRED = "required"  # مقدار مورد نیاز
QTY_SOURCE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    (QTY_SOURCE_DEDUCT_STOCK, "کسر از دپو (موجودی)"),
    (QTY_SOURCE_DEDUCT_REMAINING, "کسر از دپو (مانده)"),
    (QTY_SOURCE_REQUIRED, "مقدار مورد نیاز"),
)

# Default socket cut allowance (mm) by outer diameter — editable per size later.
DEFAULT_SOCKET_EXTRA_MM: Final[dict[int, int]] = {
    40: 15,
    50: 18,
    75: 22,
    110: 28,
    125: 30,
    160: 35,
    200: 40,
}

# Placeholder line speeds (m/min) — replace with factory rates via UI/admin.
DEFAULT_LINE_SPEED_M_PER_MIN: Final[dict[int, float]] = {
    40: 12.0,
    50: 11.0,
    75: 9.5,
    110: 7.5,
    125: 6.5,
    160: 5.0,
    200: 4.0,
}

# Placeholder billing throughput (pieces/hour per socket end) — editable later.
DEFAULT_BILLING_PIECES_PER_HOUR: Final[dict[int, float]] = {
    40: 480.0,
    50: 420.0,
    75: 360.0,
    110: 280.0,
    125: 240.0,
    160: 180.0,
    200: 140.0,
}

DEFAULT_PACK_QTY: Final[dict[int, int]] = {
    40: 50,
    50: 40,
    75: 25,
    110: 12,
    125: 10,
    160: 6,
    200: 4,
}

# Placeholder depot ceilings (pieces) until factory file is provided.
DEFAULT_DEPOT_CEILING: Final[dict[int, int]] = {
    40: 5000,
    50: 4000,
    75: 3000,
    110: 2000,
    125: 1500,
    160: 1000,
    200: 800,
}

# Default accessory factors (per piece) until system-data rules override.
DEFAULT_SOCKET_CAP_PER_SOCKET = 1.0
DEFAULT_PIPE_CAP_PER_PIECE = 1.0
DEFAULT_SPACER_PER_PIECE = 0.0
DEFAULT_COVER_PER_PIECE = 0.0
