"""Views for pipe production-time calculation hub."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import get_profile

from .constants import MATRIX_LINE_CODES, QTY_SOURCE_DEDUCT_STOCK
from .models import PipeLengthCut, PipeProductLine, PipeSizeProfile
from .seed import seed_pipe_calc_defaults
from .services import (
    build_production_matrix,
    ensure_seeded,
    get_line,
    line_overview,
    list_lines,
    run_line_aggregate,
    run_scenario,
    size_matrix_payload,
)


@login_required
def pipe_calc_hub(request: HttpRequest) -> HttpResponse:
    ensure_seeded()
    lines = list_lines()
    line_code = (request.GET.get("line") or "").strip()
    if not line_code and lines:
        line_code = lines[0].code
    line = get_line(line_code) if line_code else None
    overview = line_overview(line) if line else None

    matrix = None
    selected_size_mm = None
    if line and line.code in MATRIX_LINE_CODES and overview and overview.get("sizes"):
        try:
            selected_size_mm = int(request.GET.get("size") or overview["sizes"][0]["size_mm"])
        except (TypeError, ValueError):
            selected_size_mm = overview["sizes"][0]["size_mm"]
        profile = (
            PipeSizeProfile.objects.filter(
                line=line, size_mm=selected_size_mm, is_active=True
            )
            .select_related("product", "line")
            .prefetch_related("length_cuts", "layers", "product__bom_lines", "product__consumables")
            .first()
        )
        if profile:
            matrix = size_matrix_payload(profile, include_production=False)

    # Optional GET calc for deep-link / bookmark (legacy scenario)
    result = None
    if line and request.GET.get("calc") == "1" and line.code not in MATRIX_LINE_CODES:
        try:
            size_mm = int(request.GET.get("size") or 0)
            pieces = int(request.GET.get("pieces") or 0)
            voucher = int(request.GET.get("voucher") or 0)
            length_code = (request.GET.get("length") or "").strip()
        except (TypeError, ValueError):
            size_mm = pieces = voucher = 0
            length_code = ""
        profile = (
            PipeSizeProfile.objects.filter(line=line, size_mm=size_mm, is_active=True)
            .prefetch_related("length_cuts", "layers", "product__bom_lines", "product__consumables")
            .first()
        )
        if profile and pieces > 0:
            length = None
            if length_code:
                length = next(
                    (lc for lc in profile.length_cuts.all() if lc.length_code == length_code),
                    None,
                )
            result = run_scenario(
                profile=profile,
                length=length,
                pieces=pieces,
                voucher_qty=voucher,
            ).to_dict()

    profile = get_profile(request.user)
    return render(
        request,
        "catalog/pipe_calc.html",
        {
            "profile": profile,
            "lines": lines,
            "active_line": line_code,
            "overview": overview,
            "matrix": matrix,
            "matrix_json": json.dumps(matrix, ensure_ascii=False) if matrix else "null",
            "selected_size_mm": selected_size_mm,
            "result": result,
            "can_edit": bool(profile and profile.can_enter_data),
        },
    )


@login_required
@require_POST
def pipe_calc_run(request: HttpRequest) -> HttpResponse:
    """JSON or form POST: matrix calc, one scenario, or aggregate batch."""
    ensure_seeded()
    ctype = request.content_type or ""
    if "application/json" in ctype:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "JSON نامعتبر"}, status=400)
    else:
        payload = {
            "line": request.POST.get("line"),
            "size_mm": request.POST.get("size_mm"),
            "length_code": request.POST.get("length_code"),
            "pieces": request.POST.get("pieces"),
            "voucher_qty": request.POST.get("voucher_qty"),
            "batch": request.POST.get("batch"),
            "mode": request.POST.get("mode"),
            "qty_source": request.POST.get("qty_source"),
            "depot_rows": request.POST.get("depot_rows"),
        }

    line_code = (payload.get("line") or "").strip()
    line = get_line(line_code)
    if line is None:
        return JsonResponse({"ok": False, "error": "خط نامعتبر"}, status=404)

    mode = (payload.get("mode") or "").strip()
    if mode == "matrix" or (line.code in MATRIX_LINE_CODES and not payload.get("batch") and not payload.get("pieces")):
        try:
            size_mm = int(payload.get("size_mm") or 0)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "سایز نامعتبر"}, status=400)
        profile = (
            PipeSizeProfile.objects.filter(line=line, size_mm=size_mm, is_active=True)
            .select_related("product", "line")
            .prefetch_related("length_cuts", "layers", "product__bom_lines", "product__consumables")
            .first()
        )
        if profile is None:
            return JsonResponse({"ok": False, "error": "سایز یافت نشد"}, status=404)

        # Optional inline edits to depot rows before calc (ceiling / required / avg sales).
        raw_rows = payload.get("depot_rows")
        if isinstance(raw_rows, str):
            try:
                raw_rows = json.loads(raw_rows or "[]")
            except json.JSONDecodeError:
                return JsonResponse({"ok": False, "error": "ردیف‌های دپو نامعتبر"}, status=400)
        if isinstance(raw_rows, list):
            by_id = {int(r.get("id")): r for r in raw_rows if r.get("id")}
            for lc in profile.length_cuts.filter(is_active=True):
                patch = by_id.get(lc.id)
                if not patch:
                    continue
                fields: list[str] = []
                if "depot_ceiling" in patch:
                    try:
                        lc.depot_ceiling = max(0, int(patch.get("depot_ceiling") or 0))
                        fields.append("depot_ceiling")
                    except (TypeError, ValueError):
                        return JsonResponse({"ok": False, "error": "سقف دپو نامعتبر"}, status=400)
                if "avg_monthly_sales" in patch:
                    try:
                        lc.avg_monthly_sales = max(0, float(patch.get("avg_monthly_sales") or 0))
                        fields.append("avg_monthly_sales")
                    except (TypeError, ValueError):
                        return JsonResponse({"ok": False, "error": "میانگین فروش نامعتبر"}, status=400)
                if "required_qty" in patch:
                    # required_qty is computed client-side; persist via stock extras not needed
                    pass
                if "stock_on_hand" in patch and profile_can_edit(request):
                    try:
                        lc.stock_on_hand = int(patch.get("stock_on_hand") or 0)
                        fields.append("stock_on_hand")
                    except (TypeError, ValueError):
                        return JsonResponse({"ok": False, "error": "موجودی نامعتبر"}, status=400)
                if "voucher_qty" in patch and profile_can_edit(request):
                    try:
                        lc.voucher_qty = max(0, int(patch.get("voucher_qty") or 0))
                        fields.append("voucher_qty")
                    except (TypeError, ValueError):
                        return JsonResponse({"ok": False, "error": "حواله نامعتبر"}, status=400)
                if fields:
                    lc.save(update_fields=fields)

        qty_source = (payload.get("qty_source") or QTY_SOURCE_DEDUCT_STOCK).strip()
        data = size_matrix_payload(
            profile, qty_source=qty_source, include_production=False
        )
        # Overlay client-edited required_qty (not persisted) before production calc.
        if isinstance(raw_rows, list) and data.get("depot_rows"):
            by_id = {int(r.get("id")): r for r in raw_rows if r.get("id")}
            for row in data["depot_rows"]:
                patch = by_id.get(int(row.get("id") or 0))
                if not patch or "required_qty" not in patch:
                    continue
                try:
                    row["required_qty"] = max(0, int(patch.get("required_qty") or 0))
                except (TypeError, ValueError):
                    return JsonResponse({"ok": False, "error": "مقدار مورد نیاز نامعتبر"}, status=400)
        data["production"] = build_production_matrix(
            profile, data["depot_rows"], qty_source=qty_source or QTY_SOURCE_DEDUCT_STOCK
        )
        return JsonResponse({"ok": True, "matrix": data})

    batch = payload.get("batch")
    if batch:
        if isinstance(batch, str):
            try:
                batch = json.loads(batch)
            except json.JSONDecodeError:
                return JsonResponse({"ok": False, "error": "batch نامعتبر"}, status=400)
        data = run_line_aggregate(line, list(batch or []))
        return JsonResponse({"ok": True, **data})

    try:
        size_mm = int(payload.get("size_mm") or 0)
        pieces = int(payload.get("pieces") or 0)
        voucher_qty = int(payload.get("voucher_qty") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "ورودی عددی نامعتبر"}, status=400)

    profile = (
        PipeSizeProfile.objects.filter(line=line, size_mm=size_mm, is_active=True)
        .select_related("product")
        .prefetch_related("length_cuts", "layers", "product__bom_lines", "product__consumables")
        .first()
    )
    if profile is None:
        return JsonResponse({"ok": False, "error": "سایز یافت نشد"}, status=404)

    length_code = (payload.get("length_code") or "").strip()
    length = None
    if length_code:
        length = PipeLengthCut.objects.filter(
            size_profile=profile, length_code=length_code, is_active=True
        ).first()

    scenario = run_scenario(
        profile=profile,
        length=length,
        pieces=pieces,
        voucher_qty=voucher_qty,
    )
    return JsonResponse({"ok": True, "result": scenario.to_dict()})


def profile_can_edit(request: HttpRequest) -> bool:
    profile_user = get_profile(request.user)
    return bool(profile_user and profile_user.can_enter_data)


@login_required
@require_POST
def pipe_calc_save_stock(request: HttpRequest) -> HttpResponse:
    """Update stock / depot snapshot on a size profile or length cut."""
    if not profile_can_edit(request):
        return JsonResponse({"ok": False, "error": "مجوز ویرایش ندارید"}, status=403)

    length_id = request.POST.get("length_id")
    if length_id:
        try:
            length = get_object_or_404(PipeLengthCut, pk=int(length_id))
            fields: list[str] = []
            if "depot_ceiling" in request.POST:
                length.depot_ceiling = max(0, int(request.POST.get("depot_ceiling") or 0))
                fields.append("depot_ceiling")
            if "avg_monthly_sales" in request.POST:
                length.avg_monthly_sales = max(0, float(request.POST.get("avg_monthly_sales") or 0))
                fields.append("avg_monthly_sales")
            if "stock_on_hand" in request.POST:
                length.stock_on_hand = int(request.POST.get("stock_on_hand") or 0)
                fields.append("stock_on_hand")
            if "voucher_qty" in request.POST:
                length.voucher_qty = max(0, int(request.POST.get("voucher_qty") or 0))
                fields.append("voucher_qty")
            if fields:
                length.save(update_fields=fields)
            return JsonResponse(
                {
                    "ok": True,
                    "length_id": length.id,
                    "depot_ceiling": length.depot_ceiling,
                    "avg_monthly_sales": float(length.avg_monthly_sales or 0),
                    "stock_on_hand": length.stock_on_hand,
                    "voucher_qty": length.voucher_qty,
                }
            )
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "ورودی نامعتبر"}, status=400)

    try:
        size_id = int(request.POST.get("size_id") or 0)
        stock = int(request.POST.get("stock_on_hand") or 0)
        ceiling = request.POST.get("depot_ceiling")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "ورودی نامعتبر"}, status=400)

    size = get_object_or_404(PipeSizeProfile, pk=size_id)
    size.stock_on_hand = stock
    if ceiling not in (None, ""):
        try:
            size.depot_ceiling = max(0, int(ceiling))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "سقف دپو نامعتبر"}, status=400)
    size.save(update_fields=["stock_on_hand", "depot_ceiling"])
    return JsonResponse(
        {
            "ok": True,
            "stock_on_hand": size.stock_on_hand,
            "depot_ceiling": size.depot_ceiling,
        }
    )


@login_required
@require_POST
def pipe_calc_reseed(request: HttpRequest) -> HttpResponse:
    profile_user = get_profile(request.user)
    if not profile_user or not profile_user.is_manager:
        messages.error(request, "فقط مدیر می‌تواند سید پیش‌فرض را اجرا کند.")
        return redirect("pipe_calc")
    counts = seed_pipe_calc_defaults(force_rates=False)
    messages.success(
        request,
        f"خطوط لوله همگام شد — {counts.get('lines', 0)} خط، {counts.get('sizes', 0)} سایز.",
    )
    return redirect("pipe_calc")
