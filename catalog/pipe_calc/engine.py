"""Pure calculation engine — no ORM, no I/O.

All times in seconds unless noted. Aggregation is a thin sum so callers
can batch many SKUs without nested queries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Sequence


def _f(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _hours(seconds: float) -> float:
    return round(seconds / 3600.0, 4) if seconds else 0.0


@dataclass(frozen=True)
class StageTime:
    """Detail time for one stage (خط تولید یا بلینگ)."""

    seconds: float
    hours: float
    label: str = ""

    @staticmethod
    def from_seconds(seconds: float, label: str = "") -> "StageTime":
        sec = max(0.0, float(seconds))
        return StageTime(seconds=round(sec, 2), hours=_hours(sec), label=label)


@dataclass(frozen=True)
class ProductionTimeResult:
    pieces: int
    meters: float
    packs: float
    line: StageTime
    billing: StageTime
    total: StageTime
    socket_ends: int = 1
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DepotResult:
    """سقف دپو و کسری‌ها."""

    ceiling: int
    stock: int
    empty_space: int  # کسری از سقف دپو = فضای خالی
    voucher_qty: int
    stock_after_voucher: int
    empty_after_voucher: int  # کسری بعد از حواله از سقف دپو
    fill_to_ceiling: int  # مقدار قابل تولید تا پر شدن سقف

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BomNeedLine:
    code: str
    name: str
    unit: str
    qty_needed: float
    qty_available: float
    qty_short: float
    order_suggested: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BomResult:
    lines: tuple[BomNeedLine, ...]
    has_shortage: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_shortage": self.has_shortage,
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass(frozen=True)
class AggregateTime:
    line_seconds: float
    billing_seconds: float
    total_seconds: float
    line_hours: float
    billing_hours: float
    total_hours: float
    pieces: int
    meters: float
    item_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalcItemInput:
    """One SKU request for detail calc."""

    key: str
    pieces: int
    cut_length_mm: float
    line_speed_m_per_min: float
    billing_pieces_per_hour: float
    socket_ends: int = 1
    pack_qty: int = 0
    needs_billing: bool = True
    label: str = ""


def calc_line_time_seconds(
    pieces: int,
    cut_length_mm: float,
    line_speed_m_per_min: float,
) -> tuple[float, float]:
    """Return (seconds, meters). Speed 0 → infinite-safe 0 with meters still computed."""
    pieces = max(0, int(pieces))
    meters = pieces * max(0.0, _f(cut_length_mm)) / 1000.0
    speed = _f(line_speed_m_per_min)
    if pieces <= 0 or meters <= 0 or speed <= 0:
        return 0.0, round(meters, 4)
    minutes = meters / speed
    return minutes * 60.0, round(meters, 4)


def calc_billing_time_seconds(
    pieces: int,
    billing_pieces_per_hour: float,
    socket_ends: int = 1,
) -> float:
    """Billing time scales with socket ends (دوسر ≈ ۲× یک‌سر)."""
    pieces = max(0, int(pieces))
    rate = _f(billing_pieces_per_hour)
    ends = max(1, int(socket_ends or 1))
    if pieces <= 0 or rate <= 0:
        return 0.0
    # Effective rate drops when both ends need socketing on same machine.
    effective_rate = rate / ends
    return (pieces / effective_rate) * 3600.0


def calc_production_time(item: CalcItemInput) -> ProductionTimeResult:
    line_sec, meters = calc_line_time_seconds(
        item.pieces, item.cut_length_mm, item.line_speed_m_per_min
    )
    billing_sec = 0.0
    notes: list[str] = []
    if item.needs_billing:
        billing_sec = calc_billing_time_seconds(
            item.pieces, item.billing_pieces_per_hour, item.socket_ends
        )
    else:
        notes.append("بلینگ برای این خط فعال نیست.")

    pack_qty = max(0, int(item.pack_qty or 0))
    packs = (item.pieces / pack_qty) if pack_qty else 0.0
    total_sec = line_sec + billing_sec
    return ProductionTimeResult(
        pieces=max(0, int(item.pieces)),
        meters=meters,
        packs=round(packs, 3),
        line=StageTime.from_seconds(line_sec, "خط تولید"),
        billing=StageTime.from_seconds(billing_sec, "بلینگ"),
        total=StageTime.from_seconds(total_sec, "جمع"),
        socket_ends=max(1, int(item.socket_ends or 1)),
        notes=tuple(notes),
    )


def calc_depot(
    ceiling: int,
    stock: int,
    voucher_qty: int = 0,
) -> DepotResult:
    """کسری از سقف دپو = فضای خالی؛ بعد از حواله خروجی موجودی کم و فضای خالی زیاد می‌شود."""
    ceiling = max(0, int(ceiling or 0))
    stock = int(stock or 0)
    voucher = max(0, int(voucher_qty or 0))
    empty = max(0, ceiling - stock) if ceiling else 0
    stock_after = stock - voucher
    empty_after = max(0, ceiling - stock_after) if ceiling else 0
    fill = max(0, ceiling - stock) if ceiling else 0
    return DepotResult(
        ceiling=ceiling,
        stock=stock,
        empty_space=empty,
        voucher_qty=voucher,
        stock_after_voucher=stock_after,
        empty_after_voucher=empty_after,
        fill_to_ceiling=fill,
    )


def calc_bom_needs(
    produce_qty: int,
    components: Sequence[dict[str, Any]],
) -> BomResult:
    """components: code, name, unit, qty_per_unit, available."""
    produce_qty = max(0, int(produce_qty))
    lines: list[BomNeedLine] = []
    shortage = False
    for raw in components:
        per = _f(raw.get("qty_per_unit") or 0)
        needed = round(produce_qty * per, 4)
        available = _f(raw.get("available") or 0)
        short = max(0.0, round(needed - available, 4))
        if short > 0:
            shortage = True
        lines.append(
            BomNeedLine(
                code=str(raw.get("code") or ""),
                name=str(raw.get("name") or ""),
                unit=str(raw.get("unit") or ""),
                qty_needed=needed,
                qty_available=available,
                qty_short=short,
                order_suggested=short > 0,
            )
        )
    return BomResult(lines=tuple(lines), has_shortage=shortage)


def calc_layer_material_kg(
    meters: float,
    layers: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand layer kg/m × meters for material planning."""
    meters = max(0.0, _f(meters))
    out: list[dict[str, Any]] = []
    for layer in layers:
        kg_m = _f(layer.get("kg_per_meter") or 0)
        total = round(meters * kg_m, 4)
        out.append(
            {
                "layer": layer.get("layer") or "single",
                "material_code": layer.get("material_code") or "",
                "material_name": layer.get("material_name") or "",
                "kg_per_meter": kg_m,
                "kg_total": total,
                "share_percent": _f(layer.get("share_percent") or 0),
            }
        )
    return out


def aggregate_times(results: Iterable[ProductionTimeResult]) -> AggregateTime:
    line_s = billing_s = 0.0
    pieces = 0
    meters = 0.0
    count = 0
    for row in results:
        count += 1
        line_s += row.line.seconds
        billing_s += row.billing.seconds
        pieces += row.pieces
        meters += row.meters
    total_s = line_s + billing_s
    return AggregateTime(
        line_seconds=round(line_s, 2),
        billing_seconds=round(billing_s, 2),
        total_seconds=round(total_s, 2),
        line_hours=_hours(line_s),
        billing_hours=_hours(billing_s),
        total_hours=_hours(total_s),
        pieces=pieces,
        meters=round(meters, 4),
        item_count=count,
    )


def format_duration(seconds: float) -> str:
    """Human-readable HH:MM:SS for UI."""
    sec = int(max(0, round(_f(seconds))))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class ScenarioResult:
    """Full scenario: time (detail+agg) + depot + BOM + layers."""

    time: ProductionTimeResult
    depot: DepotResult
    bom: BomResult
    layers: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time.to_dict(),
            "depot": self.depot.to_dict(),
            "bom": self.bom.to_dict(),
            "layers": self.layers,
            "meta": self.meta,
            "time_fmt": {
                "line": format_duration(self.time.line.seconds),
                "billing": format_duration(self.time.billing.seconds),
                "total": format_duration(self.time.total.seconds),
            },
        }
