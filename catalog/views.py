"""Custom Excel workbook import, browse, and grid editing."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import get_profile

from .excel_io import preview_workbook, read_table_data
from .models import ExcelTable, ExcelUpload


def _can_view_excel(user) -> bool:
    return bool(user and user.is_authenticated)


def _can_import_excel(user) -> bool:
    profile = get_profile(user)
    return bool(profile and profile.can_enter_data)


def _can_edit_excel(user) -> bool:
    profile = get_profile(user)
    return bool(profile and profile.can_enter_data)


def _can_delete_excel(user) -> bool:
    profile = get_profile(user)
    return bool(profile and profile.is_manager)


@login_required
def excel_list(request: HttpRequest) -> HttpResponse:
    if not _can_view_excel(request.user):
        return HttpResponseForbidden("مجاز نیستید.")
    uploads = (
        ExcelUpload.objects.prefetch_related("tables")
        .all()
        .order_by("-created_at")
    )
    rows = []
    for up in uploads:
        tables = list(up.tables.all())
        rows.append({
            "upload": up,
            "table_count": len(tables),
            "row_total": sum(t.row_count for t in tables),
            "table_names": "، ".join(t.name for t in tables[:6])
            + ("…" if len(tables) > 6 else ""),
        })
    return render(
        request,
        "catalog/excel_list.html",
        {
            "rows": rows,
            "can_import": _can_import_excel(request.user),
            "can_delete": _can_delete_excel(request.user),
        },
    )


@login_required
def excel_import(request: HttpRequest) -> HttpResponse:
    if not _can_import_excel(request.user):
        return HttpResponseForbidden("مجاز به وارد کردن فایل نیستید.")
    return render(request, "catalog/excel_import.html")


@login_required
@require_POST
def excel_preview(request: HttpRequest) -> JsonResponse:
    if not _can_import_excel(request.user):
        return JsonResponse({"ok": False, "error": "مجاز نیستید."}, status=403)
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"ok": False, "error": "فایلی انتخاب نشده است."}, status=400)
    name = (uploaded.name or "").lower()
    if not (name.endswith(".xlsx") or name.endswith(".xlsm") or name.endswith(".csv")):
        return JsonResponse(
            {"ok": False, "error": "فقط فایل‌های .xlsx ، .xlsm یا .csv پشتیبانی می‌شوند."},
            status=400,
        )
    try:
        tables = preview_workbook(uploaded)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to UI
        return JsonResponse(
            {"ok": False, "error": f"خواندن فایل ممکن نشد: {exc}"},
            status=400,
        )
    if not tables:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "هیچ Table در فایل یافت نشد. "
                    "در اکسل از Insert → Table جدول بسازید و دوباره تلاش کنید."
                ),
            },
            status=400,
        )
    display_name = (uploaded.name or "workbook").replace("\\", "/").split("/")[-1]
    return JsonResponse({
        "ok": True,
        "filename": display_name,
        "tables": tables,
        # keep "sheets" alias for older frontend temporarily
        "sheets": tables,
    })


@login_required
@require_POST
def excel_import_confirm(request: HttpRequest) -> JsonResponse:
    if not _can_import_excel(request.user):
        return JsonResponse({"ok": False, "error": "مجاز نیستید."}, status=403)
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"ok": False, "error": "فایلی انتخاب نشده است."}, status=400)
    title = (request.POST.get("title") or "").strip()[:200]
    if not title:
        title = (uploaded.name or "workbook").replace("\\", "/").split("/")[-1][:200]
    try:
        selected = json.loads(request.POST.get("selected_sheets") or "[]")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "انتخاب جدول نامعتبر است."}, status=400)
    if not isinstance(selected, list) or not selected:
        return JsonResponse({"ok": False, "error": "حداقل یک جدول را انتخاب کنید."}, status=400)

    # Prefer [{"sheet":"...","table":"Inventory","name":"..."}, ...]
    selections: list[tuple[str, str, str]] = []
    for item in selected:
        if isinstance(item, dict):
            sheet = str(item.get("sheet") or item.get("sheet_name") or "").strip()
            table = str(item.get("table") or item.get("table_name") or "").strip()
            name = str(item.get("name") or table or sheet).strip()
            if not table:
                table = name or sheet
            if not sheet:
                sheet = "CSV"
        else:
            sheet = "CSV"
            table = str(item).strip()
            name = table
        if not table:
            continue
        selections.append((sheet[:200], table[:200], (name or table)[:200]))
    if not selections:
        return JsonResponse({"ok": False, "error": "حداقل یک جدول را انتخاب کنید."}, status=400)

    upload = ExcelUpload(
        title=title,
        original_name=(uploaded.name or "").replace("\\", "/").split("/")[-1][:255],
        uploaded_by=request.user,
    )
    upload.file = uploaded
    upload.save()

    created = 0
    errors: list[str] = []
    for order, (sheet_name, excel_table_name, display_name) in enumerate(selections):
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        try:
            headers, rows = read_table_data(
                uploaded,
                sheet_name=sheet_name,
                table_name=excel_table_name,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{excel_table_name}: {exc}")
            continue
        ExcelTable.objects.create(
            upload=upload,
            name=display_name,
            sheet_name=sheet_name,
            headers=headers,
            rows=rows,
            order=order,
        )
        created += 1

    if created == 0:
        if upload.file:
            upload.file.delete(save=False)
        upload.delete()
        return JsonResponse({
            "ok": False,
            "error": "هیچ جدولی وارد نشد. " + ("؛ ".join(errors) if errors else ""),
        }, status=400)

    return JsonResponse({
        "ok": True,
        "upload_id": upload.pk,
        "table_count": created,
        "detail_url": reverse("excel_detail", args=[upload.pk]),
        "list_url": reverse("excel_list"),
    })


@login_required
def excel_detail(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_view_excel(request.user):
        return HttpResponseForbidden("مجاز نیستید.")
    upload = get_object_or_404(ExcelUpload.objects.prefetch_related("tables"), pk=pk)
    tables = list(upload.tables.all())
    tables_payload = [
        {
            "id": t.pk,
            "name": t.name,
            "sheet_name": t.sheet_name,
            "headers": t.headers if isinstance(t.headers, list) else [],
            "rows": t.rows if isinstance(t.rows, list) else [],
            "layout": t.layout if isinstance(t.layout, dict) else {},
            "row_count": t.row_count,
            "column_count": t.column_count,
        }
        for t in tables
    ]
    return render(
        request,
        "catalog/excel_detail.html",
        {
            "upload": upload,
            "tables": tables,
            "tables_json": tables_payload,
            "can_edit": _can_edit_excel(request.user),
            "can_delete": _can_delete_excel(request.user),
        },
    )


@login_required
@require_POST
def excel_table_save(request: HttpRequest, pk: int) -> JsonResponse:
    if not _can_edit_excel(request.user):
        return JsonResponse({"ok": False, "error": "مجاز به ویرایش نیستید."}, status=403)
    table = get_object_or_404(ExcelTable, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "داده نامعتبر است."}, status=400)
    headers = payload.get("headers")
    rows = payload.get("rows")
    name = payload.get("name")
    layout = payload.get("layout")
    if name is not None:
        name = str(name).strip()[:200]
        if name:
            table.name = name
    if isinstance(headers, list):
        clean_headers = [str(h)[:120] for h in headers[:80]]
        table.headers = clean_headers
        width = len(clean_headers)
    else:
        width = table.column_count
    if isinstance(rows, list):
        clean_rows = []
        for row in rows[:5000]:
            if not isinstance(row, list):
                continue
            clean_rows.append([str(c)[:2000] if c is not None else "" for c in row[:width]])
        table.rows = clean_rows
    if isinstance(layout, dict):
        clean_layout: dict = {}

        def _ints(values, lo, hi, default, limit):
            out = []
            if not isinstance(values, list):
                return out
            for raw in values[:limit]:
                try:
                    out.append(max(lo, min(hi, int(float(raw)))))
                except (TypeError, ValueError):
                    out.append(default)
            return out

        clean_layout["colWidths"] = _ints(layout.get("colWidths"), 40, 800, 120, 80)
        clean_layout["rowHeights"] = _ints(layout.get("rowHeights"), 18, 200, 28, 5000)
        table.layout = clean_layout
    table.save()
    return JsonResponse({
        "ok": True,
        "row_count": table.row_count,
        "column_count": table.column_count,
        "name": table.name,
    })


@login_required
@require_POST
def excel_table_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_delete_excel(request.user):
        return HttpResponseForbidden("فقط مدیر می‌تواند جدول را حذف کند.")
    table = get_object_or_404(ExcelTable.objects.select_related("upload"), pk=pk)
    upload_id = table.upload_id
    name = table.name
    table.delete()
    messages.success(request, f"جدول «{name}» حذف شد.")
    upload = ExcelUpload.objects.filter(pk=upload_id).first()
    if upload and not upload.tables.exists():
        upload.delete()
        messages.info(request, "فایل بدون جدول باقی‌مانده حذف شد.")
        return redirect("excel_list")
    return redirect("excel_detail", pk=upload_id)


@login_required
@require_POST
def excel_file_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_delete_excel(request.user):
        return HttpResponseForbidden("فقط مدیر می‌تواند فایل را حذف کند.")
    upload = get_object_or_404(ExcelUpload, pk=pk)
    title = upload.title
    if upload.file:
        upload.file.delete(save=False)
    upload.delete()
    messages.success(request, f"فایل «{title}» و تمام جداول آن حذف شد.")
    return redirect("excel_list")
