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
from .excel_io import inspect_workbook, read_sheet_data, read_table_data
from .models import ExcelTable, ExcelUpload, SystemAlarm

from .transfer import (
    group_transfer_alarms,
    list_destinations_for_ui,
    transfer_excel_table,
    transfer_result_message,
    transfer_ui_labels_resolved,
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

    from .models import SystemNamingKey
    from .naming_registry import ensure_registry_seeded, resolve_label
    from .system_sections import build_system_groups

    ensure_registry_seeded()

    # Preload section/group naming rows for title resolve + hide
    naming_keys: list[str] = []
    for group in build_system_groups():
        naming_keys.append(f"system.group.{group.key}")
        for item in group.items:
            naming_keys.append(f"system.section.{item.key}")
    naming_rows = {
        r.key: r
        for r in SystemNamingKey.objects.filter(key__in=naming_keys).only(
            "key", "label", "is_active"
        )
    }

    groups_out = []
    for group in build_system_groups():
        group_row = naming_rows.get(f"system.group.{group.key}")
        if group_row is not None and not group_row.is_active:
            continue
        group_title = (
            group_row.label
            if group_row and group_row.label
            else resolve_label(f"system.group.{group.key}", group.title)
        )
        items_out = []
        for item in group.items:
            item_row = naming_rows.get(f"system.section.{item.key}")
            if item_row is not None and not item_row.is_active:
                continue
            url = ""
            add_url = ""
            if getattr(item, "url_name", None):
                try:
                    url = reverse(item.url_name)
                except NoReverseMatch:
                    url = ""
            if not url and item.admin_changelist:
                try:
                    url = reverse(item.admin_changelist)
                except NoReverseMatch:
                    url = ""
            if url and getattr(item, "url_query", ""):
                url = f"{url}?{item.url_query}"
            if item.can_add and getattr(item, "add_url_name", None):
                try:
                    add_url = reverse(item.add_url_name)
                except NoReverseMatch:
                    add_url = ""
            elif item.can_add and item.admin_add:
                try:
                    add_url = reverse(item.admin_add)
                except NoReverseMatch:
                    add_url = ""
            item_title = (
                item_row.label
                if item_row and item_row.label
                else resolve_label(f"system.section.{item.key}", item.title)
            )
            items_out.append(
                {
                    "key": item.key,
                    "title": item_title,
                    "description": item.description,
                    "count": item.count_fn() if item.count_fn else 0,
                    "url": url,
                    "can_add": bool(add_url),
                    "add_url": add_url,
                }
            )
        if not items_out:
            continue
        groups_out.append(
            {"key": group.key, "title": group_title, "items": items_out}
        )
    return render(
        request,
        "catalog/system_data.html",
        {"groups": groups_out},
    )


@login_required
def system_section(request: HttpRequest, key: str) -> HttpResponse:
    """Legacy route: redirect into the matching admin changelist or custom URL."""
    from django.urls import NoReverseMatch, reverse

    from .system_sections import build_system_groups

    for group in build_system_groups():
        for item in group.items:
            if item.key != key:
                continue
            if getattr(item, "url_name", None):
                try:
                    return redirect(reverse(item.url_name))
                except NoReverseMatch:
                    break
            if item.admin_changelist:
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
    return render(
        request,
        "catalog/excel_import.html",
        {"transfer_ui_labels": transfer_ui_labels_resolved()},
    )

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
        inspected = inspect_workbook(uploaded)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to UI
        return JsonResponse(
            {"ok": False, "error": f"خواندن فایل ممکن نشد: {exc}"},
            status=400,
        )
    tables = inspected.get("tables") or []
    sheets = inspected.get("sheets") or []
    if not tables and not sheets:
        return JsonResponse(
            {
                "ok": False,
                "error": "فایل خالی است یا قابل خواندن نیست.",
            },
            status=400,
        )
    display_name = (uploaded.name or "workbook").replace("\\", "/").split("/")[-1]
    return JsonResponse({
        "ok": True,
        "filename": display_name,
        "tables": tables,
        "sheets": sheets,
        "file_kind": inspected.get("file_kind") or "xlsx",
        "csv_delimiter": inspected.get("csv_delimiter"),
        "csv_encoding": inspected.get("csv_encoding"),
        "csv_encoding_label": inspected.get("csv_encoding_label"),
        "table_count": len(tables),
        "sheet_count": len(sheets),
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
        return JsonResponse({"ok": False, "error": "حداقل یک مورد را انتخاب کنید."}, status=400)

    # Prefer [{"sheet":"...","table":"Inventory","name":"...","kind":"table"|"sheet"}, ...]
    selections: list[tuple[str, str, str, str]] = []
    for item in selected:
        if isinstance(item, dict):
            sheet = str(item.get("sheet") or item.get("sheet_name") or "").strip()
            table = str(item.get("table") or item.get("table_name") or "").strip()
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in ("table", "sheet"):
                kind = "sheet" if (not table and sheet) else "table"
            name = str(item.get("name") or table or sheet).strip()
            if kind == "table" and not table:
                table = name or sheet
            if not sheet:
                sheet = "CSV"
            if kind == "sheet" and not name:
                name = sheet
            if kind == "table" and not table:
                continue
            if kind == "sheet" and not sheet:
                continue
        else:
            sheet = "CSV"
            table = str(item).strip()
            name = table
            kind = "table"
            if not table:
                continue
        selections.append((
            sheet[:200],
            table[:200],
            (name or table or sheet)[:200],
            kind,
        ))
    if not selections:
        return JsonResponse({"ok": False, "error": "حداقل یک مورد را انتخاب کنید."}, status=400)

    upload = ExcelUpload(
        title=title,
        original_name=(uploaded.name or "").replace("\\", "/").split("/")[-1][:255],
        uploaded_by=request.user,
    )
    upload.file = uploaded
    upload.save()

    created = 0
    errors: list[str] = []
    for order, (sheet_name, excel_table_name, display_name, kind) in enumerate(selections):
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        try:
            if kind == "sheet":
                headers, rows = read_sheet_data(uploaded, sheet_name)
            else:
                headers, rows = read_table_data(
                    uploaded,
                    sheet_name=sheet_name,
                    table_name=excel_table_name,
                )
        except Exception as exc:  # noqa: BLE001
            label = sheet_name if kind == "sheet" else excel_table_name
            errors.append(f"{label}: {exc}")
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
            "error": "هیچ موردی وارد نشد. " + ("؛ ".join(errors) if errors else ""),
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
            "transfer_destinations": list_destinations_for_ui(),
            "transfer_ui_labels": transfer_ui_labels_resolved(),
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


def _can_edit_naming(user) -> bool:
    profile = get_profile(user)
    return bool(profile and (profile.is_manager or profile.can_enter_data))


@login_required
def system_naming_keys(request: HttpRequest) -> HttpResponse:
    """Searchable registry of all system naming keys with exact addresses."""
    from django.db.models import Q

    from .models import SystemNamingKey
    from .naming_registry import (
        SOURCE_CHOICES,
        ensure_registry_seeded,
        key_source,
        section_choices,
        sync_naming_registry,
    )

    ensure_registry_seeded()
    if request.method == "POST" and request.POST.get("action") == "resync":
        if not _can_edit_naming(request.user):
            return HttpResponseForbidden("مجاز نیستید.")
        stats = sync_naming_registry(refresh_defaults=True)
        messages.success(
            request,
            (
                f"همگام‌سازی انجام شد: {stats['created']} جدید، "
                f"{stats['updated']} به‌روز، {stats.get('deactivated', 0)} پنهان‌شده."
            ),
        )
        return redirect("system_naming_keys")

    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    section = (request.GET.get("section") or "").strip()
    table = (request.GET.get("table") or "").strip()
    source = (request.GET.get("source") or "app").strip()
    if source not in {c[0] for c in SOURCE_CHOICES}:
        source = "app"
    only_renamed = request.GET.get("renamed") == "1"
    show_inactive = request.GET.get("inactive") == "1"

    qs = SystemNamingKey.objects.all()
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(key__icontains=q)
            | Q(label__icontains=q)
            | Q(address__icontains=q)
            | Q(column_key__icontains=q)
            | Q(table_key__icontains=q)
            | Q(default_label__icontains=q)
        )
    if category:
        qs = qs.filter(category=category)
    if section:
        qs = qs.filter(Q(section_key=section) | Q(linked_section_key=section))
    if table:
        qs = qs.filter(table_key=table)
    if only_renamed:
        from django.db.models import F

        qs = qs.exclude(default_label="").exclude(label=F("default_label"))

    # Source filter — default "app" hides admin technical keys users rarely see
    if source == "app":
        qs = qs.exclude(key__startswith="admin.")
    elif source == "ui":
        qs = qs.filter(key__startswith="ui.")
    elif source == "transfer":
        qs = qs.filter(key__startswith="transfer.")
    elif source == "report":
        qs = qs.filter(key__startswith="report.")
    elif source == "section":
        qs = qs.filter(key__startswith="system.")
    elif source == "admin":
        qs = qs.filter(key__startswith="admin.")
    # "all" → no extra filter

    filtered_count = qs.count()
    rows = list(qs.order_by("category", "table_key", "order", "key")[:250])
    for row in rows:
        row.source_bucket = key_source(row.key)  # type: ignore[attr-defined]
    tables = (
        SystemNamingKey.objects.exclude(table_key="")
        .values_list("table_key", flat=True)
        .distinct()
        .order_by("table_key")
    )
    return render(
        request,
        "catalog/system_naming_keys.html",
        {
            "rows": rows,
            "q": q,
            "category": category,
            "section": section,
            "table": table,
            "source": source,
            "source_choices": SOURCE_CHOICES,
            "only_renamed": only_renamed,
            "show_inactive": show_inactive,
            "categories": SystemNamingKey.Category.choices,
            "section_choices": section_choices(),
            "table_choices": list(tables),
            "can_edit": _can_edit_naming(request.user),
            "total_count": SystemNamingKey.objects.filter(is_active=True).count(),
            "filtered_count": filtered_count,
            "shown_count": len(rows),
        },
    )


@login_required
@require_POST
def system_naming_key_save(request: HttpRequest) -> JsonResponse:
    if not _can_edit_naming(request.user):
        return JsonResponse({"ok": False, "error": "مجاز به ویرایش نیستید."}, status=403)
    from .models import SystemNamingKey

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "داده نامعتبر است."}, status=400)

    pk = payload.get("id")
    row = get_object_or_404(SystemNamingKey, pk=pk) if pk else None
    create = row is None
    if create:
        key = str(payload.get("key") or "").strip()
        if not key:
            return JsonResponse({"ok": False, "error": "کلید الزامی است."}, status=400)
        if SystemNamingKey.objects.filter(key=key).exists():
            return JsonResponse({"ok": False, "error": "این کلید از قبل وجود دارد."}, status=400)
        row = SystemNamingKey(key=key[:220], is_custom=True)

    if "label" in payload:
        label = str(payload.get("label") or "").strip()[:200]
        if not label:
            return JsonResponse({"ok": False, "error": "عنوان خالی مجاز نیست."}, status=400)
        row.label = label
        if create:
            row.default_label = label
    if "address" in payload and (create or row.is_custom):
        row.address = str(payload.get("address") or "").strip()[:400]
    if "category" in payload and create:
        cat = str(payload.get("category") or SystemNamingKey.Category.OTHER)
        if cat in SystemNamingKey.Category.values:
            row.category = cat
    if "section_key" in payload:
        row.section_key = str(payload.get("section_key") or "").strip()[:80]
    if "linked_section_key" in payload:
        row.linked_section_key = str(payload.get("linked_section_key") or "").strip()[:80]
    if "table_key" in payload:
        row.table_key = str(payload.get("table_key") or "").strip()[:120]
    if "column_key" in payload:
        row.column_key = str(payload.get("column_key") or "").strip()[:120]
    if "order" in payload:
        try:
            row.order = max(0, int(payload.get("order") or 0))
        except (TypeError, ValueError):
            pass
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "notes" in payload:
        row.notes = str(payload.get("notes") or "")[:2000]
    if create and not row.category:
        row.category = SystemNamingKey.Category.COLUMN
    row.save()
    return JsonResponse({
        "ok": True,
        "id": row.pk,
        "key": row.key,
        "label": row.label,
        "is_active": row.is_active,
        "linked_section_key": row.linked_section_key,
        "is_renamed": row.is_renamed,
    })


@login_required
@require_POST
def system_naming_key_delete(request: HttpRequest) -> JsonResponse:
    if not _can_edit_naming(request.user):
        return JsonResponse({"ok": False, "error": "مجاز نیستید."}, status=403)
    from .models import SystemNamingKey

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "داده نامعتبر است."}, status=400)
    row = get_object_or_404(SystemNamingKey, pk=payload.get("id"))
    if not row.is_custom:
        return JsonResponse(
            {"ok": False, "error": "فقط کلیدهای افزوده‌شده توسط کاربر قابل حذف‌اند. برای بقیه نمایش را خاموش کنید."},
            status=400,
        )
    row.delete()
    return JsonResponse({"ok": True})


@login_required
def system_table_columns(request: HttpRequest) -> HttpResponse:
    """Manage column headers per table: rename, show/hide, link to sections, add."""
    from .models import SystemNamingKey
    from .naming_registry import ensure_registry_seeded, section_choices

    ensure_registry_seeded()
    table_key = (request.GET.get("table") or "").strip()
    tables = list(
        SystemNamingKey.objects.filter(category=SystemNamingKey.Category.TABLE)
        .order_by("label")
    )
    if not table_key and tables:
        table_key = tables[0].table_key or tables[0].key.replace("ui.table.", "").replace("admin.table.", "")
        # Prefer table_key field
        table_key = tables[0].table_key or ""
    columns = []
    table_meta = None
    if table_key:
        table_meta = (
            SystemNamingKey.objects.filter(
                category=SystemNamingKey.Category.TABLE, table_key=table_key
            ).first()
            or SystemNamingKey.objects.filter(key=f"ui.table.{table_key}").first()
            or SystemNamingKey.objects.filter(key=f"admin.table.{table_key}").first()
        )
        columns = list(
            SystemNamingKey.objects.filter(
                category=SystemNamingKey.Category.COLUMN,
                table_key=table_key,
            ).order_by("order", "id")
        )
    return render(
        request,
        "catalog/system_table_columns.html",
        {
            "tables": tables,
            "table_key": table_key,
            "table_meta": table_meta,
            "columns": columns,
            "section_choices": section_choices(),
            "can_edit": _can_edit_naming(request.user),
        },
    )


@login_required
@require_POST
def system_admin_header_save(request: HttpRequest) -> JsonResponse:
    """Persist admin changelist header renames into the naming registry."""
    if not _can_edit_naming(request.user):
        return JsonResponse({"ok": False, "error": "مجاز نیستید."}, status=403)
    from .models import SystemNamingKey

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "داده نامعتبر است."}, status=400)
    path = str(payload.get("path") or "").strip()[:300]
    field = str(payload.get("field") or payload.get("column_key") or "").strip()[:120]
    label = str(payload.get("label") or "").strip()[:200]
    col_index = payload.get("col_index")
    if not label:
        return JsonResponse({"ok": False, "error": "عنوان خالی است."}, status=400)

    # Prefer field name when known; else path+index
    if field:
        key = f"admin.header.{field}"
        # Try to match existing admin.field.* keys by column_key suffix
        existing = SystemNamingKey.objects.filter(
            category=SystemNamingKey.Category.COLUMN, column_key=field
        ).first()
        if existing:
            existing.label = label
            existing.save(update_fields=["label", "updated_at"])
            return JsonResponse({"ok": True, "id": existing.pk, "key": existing.key})
    else:
        key = f"admin.header.path:{path}:col:{col_index}"

    row, _created = SystemNamingKey.objects.update_or_create(
        key=key[:220],
        defaults={
            "label": label,
            "default_label": label,
            "address": f"admin-changelist:{path}#col={field or col_index}",
            "category": SystemNamingKey.Category.COLUMN,
            "column_key": field,
            "table_key": f"admin.path:{path}"[:120],
            "is_custom": True,
            "is_active": True,
        },
    )
    return JsonResponse({"ok": True, "id": row.pk, "key": row.key})
