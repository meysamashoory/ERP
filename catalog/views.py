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

from .alarms import register_alarm
from .excel_io import preview_workbook, read_table_data
from .models import ExcelTable, ExcelUpload, SystemAlarm
from .transfer import (
    group_transfer_alarms,
    list_destinations,
    transfer_excel_table,
    transfer_result_message,
)


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
def system_data_hub(request: HttpRequest) -> HttpResponse:
    """Accordion hub — each item opens full Django-admin capabilities in app chrome."""
    from django.urls import NoReverseMatch, reverse

    from .system_sections import build_system_groups

    groups_out = []
    for group in build_system_groups():
        items_out = []
        for item in group.items:
            try:
                url = reverse(item.admin_changelist)
            except NoReverseMatch:
                url = ""
            add_url = ""
            if item.can_add and item.admin_add:
                try:
                    add_url = reverse(item.admin_add)
                except NoReverseMatch:
                    add_url = ""
            items_out.append(
                {
                    "key": item.key,
                    "title": item.title,
                    "description": item.description,
                    "count": item.count_fn() if item.count_fn else 0,
                    "url": url,
                    "can_add": bool(add_url),
                    "add_url": add_url,
                }
            )
        groups_out.append(
            {"key": group.key, "title": group.title, "items": items_out}
        )
    return render(
        request,
        "catalog/system_data.html",
        {"groups": groups_out},
    )


@login_required
def system_section(request: HttpRequest, key: str) -> HttpResponse:
    """Legacy route: redirect into the matching admin changelist."""
    from django.urls import NoReverseMatch, reverse

    from .system_sections import build_system_groups

    for group in build_system_groups():
        for item in group.items:
            if item.key == key:
                try:
                    return redirect(reverse(item.admin_changelist))
                except NoReverseMatch:
                    break
    messages.error(request, "بخش یافت نشد.")
    return redirect("system_data")


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
            "can_transfer": _can_edit_excel(request.user),
            "transfer_destinations": list_destinations(),
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
        "redirect_url": reverse("excel_list"),
    })


@login_required
@require_POST
def excel_table_transfer(request: HttpRequest, pk: int) -> JsonResponse:
    if not _can_edit_excel(request.user):
        return JsonResponse({"ok": False, "error": "مجاز به انتقال داده نیستید."}, status=403)
    table = get_object_or_404(ExcelTable.objects.select_related("upload"), pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "داده نامعتبر است."}, status=400)
    destination_id = str(payload.get("destination") or "").strip()
    level_id = str(payload.get("level") or "").strip()
    mode = str(payload.get("mode") or "transfer").strip().lower()
    if mode not in ("transfer", "update"):
        mode = "transfer"
    mapping = payload.get("mapping")
    if not isinstance(mapping, dict):
        return JsonResponse({"ok": False, "error": "نگاشت ستون‌ها الزامی است."}, status=400)
    if not destination_id:
        return JsonResponse({"ok": False, "error": "مقصد انتقال را انتخاب کنید."}, status=400)
    try:
        offset = int(payload.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    limit = payload.get("limit", None)
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 80
    # Chunk history list transfers so the UI can show progress percent
    if destination_id in ("production_history", "history") and level_id in (
        "history_list",
        "list",
        "",
    ):
        if limit is None:
            limit = 80
    try:
        result = transfer_excel_table(
            table=table,
            destination_id=destination_id,
            level_id=level_id,
            mapping=mapping,
            user=request.user,
            mode=mode,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        register_alarm(
            title="شکست انتقال داده اکسل",
            message=str(exc),
            suggestion="نگاشت و سطح انتقال را بررسی کنید.",
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.DATA_TRANSFER,
            details={"table_id": table.pk},
            dedupe=False,
        )
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001
        register_alarm(
            title="شکست انتقال داده اکسل",
            message=f"انتقال ناموفق بود: {exc}",
            suggestion="جزئیات خطا را بررسی و دوباره تلاش کنید.",
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.DATA_TRANSFER,
            details={"table_id": table.pk},
            dedupe=False,
        )
        return JsonResponse(
            {"ok": False, "error": f"انتقال ناموفق بود: {exc}"},
            status=500,
        )
    return JsonResponse({
        "ok": result.failed == 0 or result.transferred > 0,
        "partial": bool(result.failed and result.transferred),
        "transferred": result.transferred,
        "failed": result.failed,
        "skipped": result.skipped,
        "mode": result.mode,
        "alarms": result.alarms[:40],
        "alarm_groups": group_transfer_alarms(result.alarms),
        "conflicts": getattr(result, "conflicts", []) or [],
        "error_cells": getattr(result, "error_cells", []) or [],
        "table_deleted": False,
        "redirect_url": result.redirect_url,
        "message": transfer_result_message(result),
        "progress": {
            "offset": getattr(result, "offset", 0),
            "next_offset": getattr(result, "next_offset", 0),
            "total_rows": getattr(result, "total_rows", 0),
            "done": getattr(result, "done", True),
            "percent": getattr(result, "percent", 100),
        },
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


@login_required
def product_data_hub(request: HttpRequest) -> HttpResponse:
    """Tabbed product master data — view-first; edit after topbar toggle."""
    from .models import ProductGroup, ProductSubGroup
    from .product_data import (
        PRODUCT_DATA_TABS,
        TAB_BOM,
        TAB_CONSUMABLES,
        TAB_INFO,
        bom_rows,
        consumable_rows,
        product_info_rows,
        resolve_tab,
    )

    profile = get_profile(request.user)
    can_edit_permission = bool(profile and profile.can_enter_data)
    tab = resolve_tab(request.GET.get("tab"))
    groups = list(
        ProductGroup.objects.order_by("order", "name").values("id", "name")
    )
    subgroups = list(
        ProductSubGroup.objects.select_related("group")
        .order_by("group__order", "order", "name")
        .values("id", "name", "group_id", "group__name")
    )
    context = {
        "tabs": PRODUCT_DATA_TABS,
        "active_tab": tab,
        "can_edit_permission": can_edit_permission,
        # Page opens in view mode; JS enables edit when user clicks «ویرایش».
        "can_edit": False,
        "counting_units": [
            {"value": "count", "label": "عدد"},
            {"value": "branch", "label": "شاخه"},
            {"value": "coil", "label": "کلاف"},
            {"value": "meter", "label": "متر"},
        ],
        "product_groups": groups,
        "product_subgroups": subgroups,
        "product_groups_json": json.dumps(groups, ensure_ascii=False),
        "product_subgroups_json": json.dumps(
            [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "group_id": s["group_id"],
                    "group_name": s["group__name"],
                }
                for s in subgroups
            ],
            ensure_ascii=False,
        ),
        "info_rows": product_info_rows() if tab == TAB_INFO else [],
        "bom_rows": bom_rows() if tab == TAB_BOM else [],
        "consumable_rows": consumable_rows() if tab == TAB_CONSUMABLES else [],
        "save_url": reverse("product_data_save"),
        "delete_url": reverse("product_data_delete"),
    }
    return render(request, "catalog/product_data.html", context)


@login_required
@require_POST
def product_data_save(request: HttpRequest) -> JsonResponse:
    profile = get_profile(request.user)
    if not (profile and profile.can_enter_data):
        return JsonResponse({"ok": False, "error": "مجاز به ویرایش نیستید."}, status=403)
    from .product_data import save_tab_rows

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON نامعتبر است."}, status=400)
    tab = str(payload.get("tab") or "info")
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return JsonResponse({"ok": False, "error": "ردیف‌ها نامعتبر است."}, status=400)
    stats = save_tab_rows(tab, rows)
    if stats["failed"] and not stats["saved"]:
        return JsonResponse(
            {
                "ok": False,
                "error": "ذخیره ناموفق بود. کدها و فیلدهای الزامی را بررسی کنید.",
                **stats,
            },
            status=400,
        )
    return JsonResponse(
        {
            "ok": True,
            "message": f"{stats['saved']} ردیف ذخیره شد"
            + (f"؛ {stats['failed']} ناموفق" if stats["failed"] else "")
            + ".",
            **stats,
        }
    )


@login_required
@require_POST
def product_data_delete(request: HttpRequest) -> JsonResponse:
    profile = get_profile(request.user)
    if not (profile and profile.can_enter_data):
        return JsonResponse({"ok": False, "error": "مجاز به حذف نیستید."}, status=403)
    from .product_data import delete_tab_row

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON نامعتبر است."}, status=400)
    tab = str(payload.get("tab") or "")
    try:
        row_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "شناسه ردیف نامعتبر است."}, status=400)
    try:
        delete_tab_row(tab, row_id)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True})
