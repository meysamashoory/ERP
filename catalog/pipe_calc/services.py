"""ORM adapters: load profiles and run scenario calculations."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from catalog.models import FlexibleDataset, FlexibleRow, Product

from .engine import (
    calc_depot_matrix_row,
    calc_production_matrix_row,
    resolve_qty_from_depot_row,

    CalcItemInput,
    ScenarioResult,
    aggregate_times,
    calc_bom_needs,
    calc_depot,
    calc_layer_material_kg,
    calc_production_time,
    format_duration,
)
from .models import PipeCalcRule, PipeLengthCut, PipeProductLine, PipeSizeProfile
from .constants import (
    MATRIX_LINE_CODES,
    NOMINAL_LENGTHS,
    QTY_SOURCE_CHOICES,
    QTY_SOURCE_DEDUCT_STOCK,
)
from .seed import seed_pipe_calc_defaults


def ensure_seeded() -> None:
    if not PipeProductLine.objects.exists():
        seed_pipe_calc_defaults()


def list_lines() -> list[PipeProductLine]:
    ensure_seeded()
    from .constants import LINE_CODES

    lines = list(PipeProductLine.objects.filter(is_active=True).order_by("order", "code"))
    rank = {code: idx for idx, code in enumerate(LINE_CODES)}
    lines = [ln for ln in lines if ln.code in rank]
    lines.sort(key=lambda ln: (rank.get(ln.code, 999), ln.order, ln.code))
    return lines


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
    order_map = {code: idx for idx, (code, *_rest) in enumerate(NOMINAL_LENGTHS)}
    size_rows = []
    for p in profiles:
        depot = calc_depot(int(p.depot_ceiling or 0), int(p.stock_on_hand or 0), 0)
        lengths = list(p.length_cuts.all())
        lengths.sort(
            key=lambda lc: (
                order_map.get(lc.length_code, 999),
                lc.nominal_cm,
                lc.socket_ends,
                lc.id,
            )
        )
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
                        "id": lc.id,
                        "code": lc.length_code,
                        "label": lc.label,
                        "nominal_cm": lc.nominal_cm,
                        "cut_length_mm": lc.cut_length_mm,
                        "socket_ends": lc.socket_ends,
                        "depot_ceiling": int(lc.depot_ceiling or 0),
                        "avg_monthly_sales": float(lc.avg_monthly_sales or 0),
                        "stock_on_hand": int(lc.stock_on_hand or 0),
                        "voucher_qty": int(lc.voucher_qty or 0),
                    }
                    for lc in lengths
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
            "is_matrix_line": line.code in MATRIX_LINE_CODES,
            "notes": line.notes,
            "settings": line.settings or {},
        },
        "sizes": size_rows,
    }



def _voucher_qty_by_product_code() -> dict[str, int]:
    """Sum voucher quantities from flexible product-data vouchers tab."""
    ds = (
        FlexibleDataset.objects.filter(destination_id="product_data", level_id="vouchers")
        .order_by("-updated_at")
        .first()
    )
    if ds is None:
        return {}
    totals: dict[str, int] = {}
    for row in FlexibleRow.objects.filter(dataset=ds).iterator():
        values = row.values or {}
        code = str(
            values.get("کد_کالا")
            or values.get("کد کالا")
            or values.get("product_code")
            or values.get("code")
            or ""
        ).strip()
        if not code:
            continue
        raw = values.get("مقدار") or values.get("qty") or values.get("quantity") or 0
        try:
            qty = int(float(str(raw).replace(",", "").strip() or 0))
        except (TypeError, ValueError):
            qty = 0
        totals[code] = totals.get(code, 0) + qty
    return totals


def _sync_length_stock_from_products(profile: PipeSizeProfile) -> None:
    """Refresh length stock/voucher snapshots from linked product + vouchers when empty."""
    vouchers = _voucher_qty_by_product_code()
    product = profile.product
    product_stock = int(product.stock_finished or 0) if product else int(profile.stock_on_hand or 0)
    product_code = (product.code if product else "") or ""
    product_voucher = vouchers.get(product_code, 0)
    lengths = list(profile.length_cuts.filter(is_active=True))
    if not lengths:
        return
    # If length rows still at zero, distribute/copy product snapshot as a starting point.
    for lc in lengths:
        changed = False
        if lc.stock_on_hand == 0 and product_stock:
            lc.stock_on_hand = product_stock
            changed = True
        if lc.voucher_qty == 0 and product_voucher:
            lc.voucher_qty = product_voucher
            changed = True
        if lc.depot_ceiling == 0 and profile.depot_ceiling:
            lc.depot_ceiling = int(profile.depot_ceiling)
            changed = True
        if changed:
            lc.save(
                update_fields=["stock_on_hand", "voucher_qty", "depot_ceiling"]
            )


def _resolve_calc_rule(line: PipeProductLine) -> PipeCalcRule | None:
    rule = (
        PipeCalcRule.objects.filter(line=line, code="default", is_active=True).first()
        or PipeCalcRule.objects.filter(line__isnull=True, code="default", is_active=True).first()
    )
    return rule


def build_depot_matrix(profile: PipeSizeProfile) -> list[dict[str, Any]]:
    """Upper planning table rows for one size."""
    _sync_length_stock_from_products(profile)
    rows: list[dict[str, Any]] = []
    order_map = {code: idx for idx, (code, *_rest) in enumerate(NOMINAL_LENGTHS)}
    lengths = list(profile.length_cuts.filter(is_active=True))
    lengths.sort(key=lambda lc: (order_map.get(lc.length_code, 999), lc.nominal_cm, lc.socket_ends, lc.id))
    for lc in lengths:
        row = calc_depot_matrix_row(
            length_code=lc.length_code,
            label=lc.label,
            depot_ceiling=int(lc.depot_ceiling or 0),
            stock=int(lc.stock_on_hand or 0),
            voucher=int(lc.voucher_qty or 0),
            avg_monthly_sales=float(lc.avg_monthly_sales or 0),
            required_qty=None,
        )
        data = row.to_dict()
        data["id"] = lc.id
        data["nominal_cm"] = lc.nominal_cm
        data["cut_length_mm"] = lc.cut_length_mm
        data["socket_ends"] = lc.socket_ends
        cut_speed = float(lc.line_speed_m_per_min or 0)
        profile_speed = float(profile.line_speed_m_per_min or 0)
        data["line_speed_m_per_min"] = cut_speed if cut_speed > 0 else profile_speed
        rows.append(data)
    return rows


def build_production_matrix(
    profile: PipeSizeProfile,
    depot_rows: list[dict[str, Any]],
    *,
    qty_source: str = QTY_SOURCE_DEDUCT_STOCK,
) -> dict[str, Any]:
    """Lower computational table + material column headers."""
    line = profile.line
    rule = _resolve_calc_rule(line)
    socket_cap = float(rule.socket_cap_per_socket) if rule else 1.0
    pipe_cap = float(rule.pipe_cap_per_piece) if rule else 1.0
    spacer = float(rule.spacer_per_piece) if rule else 0.0
    cover = float(rule.cover_per_piece) if rule else 0.0
    material_factors = (rule.material_factors if rule else {}) or {}

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
    # Also fold BOM component names into material columns when present.
    bom_comps = _bom_components_for_product(profile.product)

    material_headers: list[dict[str, str]] = []
    seen: set[str] = set()
    for ly in layers:
        key = ly["layer"]
        if key in seen:
            continue
        seen.add(key)
        material_headers.append(
            {
                "key": f"layer:{key}",
                "label": ly["material_name"] or ly["material_code"] or key,
            }
        )
    for comp in bom_comps:
        key = f"bom:{(comp.get('code') or comp.get('name') or '').strip()}"
        if not key or key in seen:
            continue
        seen.add(key)
        material_headers.append({"key": key, "label": comp.get("name") or comp.get("code") or key})

    length_by_code = {
        lc.length_code: lc for lc in profile.length_cuts.filter(is_active=True)
    }
    out_rows: list[dict[str, Any]] = []
    for depot in depot_rows:
        code = depot.get("length_code") or ""
        lc = length_by_code.get(code)
        if lc is None:
            continue
        qty = resolve_qty_from_depot_row(depot, qty_source)
        cut_speed = float(lc.line_speed_m_per_min or 0)
        profile_speed = float(profile.line_speed_m_per_min or 0)
        # Prefer explicit depot-row override from definitions dialog when present.
        try:
            row_speed = float(depot.get("line_speed_m_per_min") or 0)
        except (TypeError, ValueError):
            row_speed = 0.0
        speed = row_speed if row_speed > 0 else (cut_speed if cut_speed > 0 else profile_speed)
        prod = calc_production_matrix_row(
            length_code=code,
            label=str(depot.get("label") or lc.label),
            qty=qty,
            cut_length_mm=float(lc.cut_length_mm or 0),
            line_speed_m_per_min=speed,
            billing_pieces_per_hour=float(profile.billing_pieces_per_hour or 0),
            socket_ends=int(lc.socket_ends or 0),
            needs_billing=bool(line.needs_billing),
            layers=layers,
            socket_cap_per_socket=socket_cap,
            pipe_cap_per_piece=pipe_cap,
            spacer_per_piece=spacer,
            cover_per_piece=cover,
            material_factors={str(k): float(v) for k, v in material_factors.items()},
        )
        data = prod.to_dict()
        # Flatten materials for table cells.
        material_values: dict[str, float] = {}
        for mat in data.get("materials") or []:
            material_values[f"layer:{mat.get('layer')}"] = float(mat.get("kg_total") or 0)
        for comp in bom_comps:
            key = f"bom:{(comp.get('code') or comp.get('name') or '').strip()}"
            per = float(comp.get("qty_per_unit") or 0)
            material_values[key] = round(qty * per, 4)
        data["material_values"] = material_values
        data["qty_source"] = qty_source
        out_rows.append(data)

    return {
        "qty_source": qty_source,
        "qty_source_choices": [{"value": v, "label": lbl} for v, lbl in QTY_SOURCE_CHOICES],
        "material_headers": material_headers,
        "rows": out_rows,
        "rule": {
            "code": rule.code if rule else "default",
            "name": rule.name if rule else "پیش‌فرض",
            "socket_cap_per_socket": socket_cap,
            "pipe_cap_per_piece": pipe_cap,
            "spacer_per_piece": spacer,
            "cover_per_piece": cover,
        },
    }


def size_matrix_payload(
    profile: PipeSizeProfile,
    *,
    qty_source: str = QTY_SOURCE_DEDUCT_STOCK,
    include_production: bool = False,
) -> dict[str, Any]:
    depot_rows = build_depot_matrix(profile)
    payload: dict[str, Any] = {
        "size_mm": profile.size_mm,
        "size_id": profile.id,
        "line_code": profile.line.code,
        "is_matrix_line": profile.line.code in MATRIX_LINE_CODES,
        "depot_rows": depot_rows,
        "qty_source_choices": [{"value": v, "label": lbl} for v, lbl in QTY_SOURCE_CHOICES],
        "default_qty_source": QTY_SOURCE_DEDUCT_STOCK,
    }
    if include_production:
        payload["production"] = build_production_matrix(
            profile, depot_rows, qty_source=qty_source or QTY_SOURCE_DEDUCT_STOCK
        )
    return payload

