"""ORM adapters: load profiles and run scenario calculations."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from catalog.models import Product

from .engine import (
    CalcItemInput,
    ScenarioResult,
    aggregate_times,
    calc_bom_needs,
    calc_depot,
    calc_layer_material_kg,
    calc_production_time,
    format_duration,
)
from .models import PipeLengthCut, PipeProductLine, PipeSizeProfile
from .seed import seed_pipe_calc_defaults


def ensure_seeded() -> None:
    if not PipeProductLine.objects.exists():
        seed_pipe_calc_defaults()


def list_lines() -> list[PipeProductLine]:
    ensure_seeded()
    return list(PipeProductLine.objects.filter(is_active=True).order_by("order", "code"))


def get_line(code: str) -> PipeProductLine | None:
    ensure_seeded()
    return PipeProductLine.objects.filter(code=code, is_active=True).first()


def load_size_profiles(line: PipeProductLine) -> list[PipeSizeProfile]:
    return list(
        PipeSizeProfile.objects.filter(line=line, is_active=True)
        .select_related("product")
        .prefetch_related(
            Prefetch(
                "length_cuts",
                queryset=PipeLengthCut.objects.filter(is_active=True).order_by(
                    "nominal_cm", "socket_ends"
                ),
            ),
            "layers",
        )
        .order_by("size_mm")
    )


def _bom_components_for_product(product: Product | None) -> list[dict[str, Any]]:
    if product is None:
        return []
    out: list[dict[str, Any]] = []
    codes: list[str] = []
    for line in product.bom_lines.all():
        codes.append((line.component_code or "").strip())
    for cons in product.consumables.all():
        codes.append((cons.material_code or "").strip())
    stock_map: dict[str, int] = {}
    clean = [c for c in codes if c]
    if clean:
        for p in Product.objects.filter(code__in=clean).only(
            "code", "stock_finished", "stock_unassembled"
        ):
            stock_map[p.code] = int(p.stock_finished or 0) + int(p.stock_unassembled or 0)

    for line in product.bom_lines.all():
        code = (line.component_code or "").strip()
        out.append(
            {
                "code": code,
                "name": line.component_name,
                "unit": line.unit or "عدد",
                "qty_per_unit": float(line.quantity or 0),
                "available": float(stock_map.get(code, 0)),
            }
        )
    for cons in product.consumables.all():
        code = (cons.material_code or "").strip()
        out.append(
            {
                "code": code,
                "name": cons.material_name,
                "unit": cons.unit or "گرم",
                "qty_per_unit": float(cons.quantity_per_unit or 0),
                "available": float(stock_map.get(code, 0)),
            }
        )
    return out


def _layer_components(profile: PipeSizeProfile, meters: float) -> list[dict[str, Any]]:
    """Treat layer materials as BOM-like needs (kg)."""
    layers = [
        {
            "layer": ly.layer,
            "material_code": ly.material_code,
            "material_name": ly.material_name,
            "kg_per_meter": float(ly.kg_per_meter or 0),
            "share_percent": float(ly.share_percent or 0),
        }
        for ly in profile.layers.all()
    ]
    expanded = calc_layer_material_kg(meters, layers)
    out: list[dict[str, Any]] = []
    codes = [e["material_code"] for e in expanded if e["material_code"]]
    stock_map: dict[str, float] = {}
    if codes:
        for p in Product.objects.filter(code__in=codes).only(
            "code", "stock_finished", "stock_unassembled"
        ):
            stock_map[p.code] = float(
                int(p.stock_finished or 0) + int(p.stock_unassembled or 0)
            )
    for e in expanded:
        code = e["material_code"]
        out.append(
            {
                "code": code,
                "name": e["material_name"] or e["layer"],
                "unit": "kg",
                "qty_per_unit": e["kg_per_meter"],  # per meter; we pass meters as produce? 
                # Better: absolute need via qty_per_unit=kg_total/pieces handled outside
                "available": stock_map.get(code, 0.0),
                "kg_total": e["kg_total"],
                "layer": e["layer"],
            }
        )
    return out


def run_scenario(
    *,
    profile: PipeSizeProfile,
    length: PipeLengthCut | None,
    pieces: int,
    voucher_qty: int = 0,
    stock_override: int | None = None,
) -> ScenarioResult:
    line = profile.line
    cut_mm = float(length.cut_length_mm) if length else float(
        profile.extras.get("default_cut_mm") or 1000
    )
    sockets = int(length.socket_ends) if length else 1
    item = CalcItemInput(
        key=f"{line.code}-{profile.size_mm}-{getattr(length, 'length_code', 'm')}",
        pieces=pieces,
        cut_length_mm=cut_mm,
        line_speed_m_per_min=float(profile.line_speed_m_per_min or 0),
        billing_pieces_per_hour=float(profile.billing_pieces_per_hour or 0),
        socket_ends=sockets,
        pack_qty=int(profile.pack_qty or 0),
        needs_billing=bool(line.needs_billing),
        label=f"{line.name} Ø{profile.size_mm}",
    )
    time_res = calc_production_time(item)
    stock = (
        int(stock_override)
        if stock_override is not None
        else int(profile.stock_on_hand or 0)
    )
    if profile.product_id and stock_override is None and profile.stock_on_hand == 0:
        stock = int(profile.product.stock_finished or 0)
    depot = calc_depot(int(profile.depot_ceiling or 0), stock, voucher_qty)

    bom_comps = _bom_components_for_product(profile.product)
    # Layer materials: convert kg_total into needs with qty_per_unit = kg_total/pieces
    layer_rows = _layer_components(profile, time_res.meters)
    layer_bom: list[dict[str, Any]] = []
    for row in layer_rows:
        per = (row["kg_total"] / pieces) if pieces else row.get("qty_per_unit") or 0
        layer_bom.append(
            {
                "code": row["code"],
                "name": f"{row['name']} ({row.get('layer')})",
                "unit": "kg",
                "qty_per_unit": per,
                "available": row["available"],
            }
        )
    bom = calc_bom_needs(pieces, bom_comps + layer_bom)
    layers_out = calc_layer_material_kg(
        time_res.meters,
        [
            {
                "layer": ly.layer,
                "material_code": ly.material_code,
                "material_name": ly.material_name,
                "kg_per_meter": float(ly.kg_per_meter or 0),
                "share_percent": float(ly.share_percent or 0),
            }
            for ly in profile.layers.all()
        ],
    )
    return ScenarioResult(
        time=time_res,
        depot=depot,
        bom=bom,
        layers=layers_out,
        meta={
            "line_code": line.code,
            "line_name": line.name,
            "size_mm": profile.size_mm,
            "length_code": getattr(length, "length_code", ""),
            "length_label": getattr(length, "label", ""),
            "cut_length_mm": cut_mm,
            "pack_qty": profile.pack_qty,
            "is_scaffold": line.is_scaffold,
            "layer_mode": line.layer_mode,
        },
    )


def run_line_aggregate(
    line: PipeProductLine,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """requests: [{size_mm, length_code, pieces}, ...] → detail rows + aggregate."""
    profiles = {p.size_mm: p for p in load_size_profiles(line)}
    details = []
    time_rows = []
    for req in requests:
        size_mm = int(req.get("size_mm") or 0)
        pieces = int(req.get("pieces") or 0)
        profile = profiles.get(size_mm)
        if profile is None or pieces <= 0:
            continue
        length_code = (req.get("length_code") or "").strip()
        length = None
        if length_code:
            length = next(
                (lc for lc in profile.length_cuts.all() if lc.length_code == length_code),
                None,
            )
        scenario = run_scenario(
            profile=profile,
            length=length,
            pieces=pieces,
            voucher_qty=int(req.get("voucher_qty") or 0),
        )
        details.append(scenario.to_dict())
        time_rows.append(scenario.time)
    agg = aggregate_times(time_rows)
    return {
        "aggregate": agg.to_dict(),
        "aggregate_fmt": {
            "line": format_duration(agg.line_seconds),
            "billing": format_duration(agg.billing_seconds),
            "total": format_duration(agg.total_seconds),
        },
        "details": details,
    }


def line_overview(line: PipeProductLine) -> dict[str, Any]:
    """Lightweight overview for hub UI (no heavy joins beyond prefetch)."""
    profiles = load_size_profiles(line)
    size_rows = []
    for p in profiles:
        depot = calc_depot(int(p.depot_ceiling or 0), int(p.stock_on_hand or 0), 0)
        size_rows.append(
            {
                "id": p.id,
                "size_mm": p.size_mm,
                "line_speed_m_per_min": float(p.line_speed_m_per_min or 0),
                "billing_pieces_per_hour": float(p.billing_pieces_per_hour or 0),
                "pack_qty": p.pack_qty,
                "depot_ceiling": p.depot_ceiling,
                "stock_on_hand": p.stock_on_hand,
                "empty_space": depot.empty_space,
                "lengths": [
                    {
                        "code": lc.length_code,
                        "label": lc.label,
                        "nominal_cm": lc.nominal_cm,
                        "cut_length_mm": lc.cut_length_mm,
                        "socket_ends": lc.socket_ends,
                    }
                    for lc in p.length_cuts.all()
                ],
                "layers": [
                    {
                        "layer": ly.layer,
                        "material_code": ly.material_code,
                        "material_name": ly.material_name,
                        "kg_per_meter": float(ly.kg_per_meter or 0),
                        "share_percent": float(ly.share_percent or 0),
                    }
                    for ly in p.layers.all()
                ],
            }
        )
    return {
        "line": {
            "code": line.code,
            "name": line.name,
            "layer_mode": line.layer_mode,
            "needs_billing": line.needs_billing,
            "uses_nominal_lengths": line.uses_nominal_lengths,
            "is_scaffold": line.is_scaffold,
            "notes": line.notes,
            "settings": line.settings or {},
        },
        "sizes": size_rows,
    }
