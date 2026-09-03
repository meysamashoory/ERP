"""Views for pipe production-time calculation hub."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import get_profile

from .models import PipeLengthCut, PipeProductLine, PipeSizeProfile
from .seed import seed_pipe_calc_defaults
from .services import (
    ensure_seeded,
    get_line,
    line_overview,
    list_lines,
    run_line_aggregate,
    run_scenario,
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

    # Optional GET calc for deep-link / bookmark
    result = None
    if line and request.GET.get("calc") == "1":
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
            "result": result,
            "can_edit": bool(profile and profile.can_enter_data),
        },
    )


@login_required
@require_POST
def pipe_calc_run(request: HttpRequest) -> HttpResponse:
    """JSON or form POST: run one scenario or aggregate batch."""
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
        }

    line_code = (payload.get("line") or "").strip()
    line = get_line(line_code)
    if line is None:
        return JsonResponse({"ok": False, "error": "خط نامعتبر"}, status=404)

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
        length = (
            PipeLengthCut.objects.filter(
                size_profile=profile, length_code=length_code, is_active=True
            ).first()
        )

    scenario = run_scenario(
        profile=profile,
        length=length,
        pieces=pieces,
        voucher_qty=voucher_qty,
    )
    return JsonResponse({"ok": True, "result": scenario.to_dict()})


@login_required
@require_POST
def pipe_calc_save_stock(request: HttpRequest) -> HttpResponse:
    """Update stock / depot snapshot on a size profile (lightweight)."""
    profile_user = get_profile(request.user)
    if not profile_user or not profile_user.can_enter_data:
        return JsonResponse({"ok": False, "error": "مجوز ویرایش ندارید"}, status=403)

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
        f"خطوط لوله همگام شد — {counts['lines']} خط، {counts['sizes']} سایز.",
    )
    return redirect("pipe_calc")
