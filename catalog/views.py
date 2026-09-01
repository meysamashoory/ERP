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
    """App-styled hub mirroring previous Django-admin «داده‌های پایه» options."""
    from django.urls import reverse

    from accounts.models import UserProfile

    from .models import (
        DeviationReason,
        ExcelTable,
        ExcelUpload,
        Machine,
        MoldOption,
        PlanningDisplaySettings,
        PlanningInsightField,
        Product,
        ProductBomLine,
        ProductConsumable,
        ProductGroup,
        ProductSubGroup,
        ProductionTypeOption,
        ProductionUnit,
        ProgramChangeReason,
        ProgramUidScheme,
        StoppageReason,
        SystemAlarm,
    )

    # Same options as former admin sidebar under «داده‌های پایه» (+ users)
    sections = [
        {
            "group": "داده‌های پایه",
            "title": "آلارم‌های سیستم (بررسی و پاک‌سازی)",
            "description": "تداخل تولید، انتقال اکسل، شناسه تکراری",
            "count": SystemAlarm.objects.filter(status=SystemAlarm.Status.OPEN).count(),
            "url": reverse("admin:catalog_systemalarm_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_systemalarm_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "انواع قالب",
            "description": "فهرست قالب‌های قابل انتخاب در برنامه",
            "count": MoldOption.objects.count(),
            "url": reverse("admin:catalog_moldoption_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_moldoption_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "تنظیمات نمایش برنامه‌ریزی (کادر آبی و ماتریس)",
            "description": "ضریب ارتفاع، واحدهای ماتریس، تفکیک گروه",
            "count": PlanningDisplaySettings.objects.count(),
            "url": reverse("admin:catalog_planningdisplaysettings_changelist"),
            "can_add": False,
            "add_url": "",
        },
        {
            "group": "داده‌های پایه",
            "title": "جداول اکسل",
            "description": "برگه‌های واردشده از فایل‌های اکسل",
            "count": ExcelTable.objects.count(),
            "url": reverse("admin:catalog_exceltable_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_exceltable_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "دستگاه‌ها و خطوط",
            "description": "دستگاه تزریق و خطوط تولید (متصل به واحد)",
            "count": Machine.objects.count(),
            "url": reverse("admin:catalog_machine_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_machine_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "دلایل انحراف",
            "description": "علل انحراف آمار تولید",
            "count": DeviationReason.objects.count(),
            "url": reverse("admin:catalog_deviationreason_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_deviationreason_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "دلایل تغییر برنامه",
            "description": "علل تغییر / راه‌اندازی برنامه",
            "count": ProgramChangeReason.objects.count(),
            "url": reverse("admin:catalog_programchangereason_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_programchangereason_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "دلایل توقف",
            "description": "علل توقف تولید",
            "count": StoppageReason.objects.count(),
            "url": reverse("admin:catalog_stoppagereason_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_stoppagereason_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "زیرگروه‌های محصول",
            "description": "زیرگروه وابسته به گروه اصلی",
            "count": ProductSubGroup.objects.count(),
            "url": reverse("admin:catalog_productsubgroup_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productsubgroup_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "ساختار BOM",
            "description": "اجزای تشکیل‌دهنده محصول",
            "count": ProductBomLine.objects.count(),
            "url": reverse("admin:catalog_productbomline_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productbomline_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "فایل‌های اکسل",
            "description": "فایل‌های بارگذاری‌شده برای انتقال داده",
            "count": ExcelUpload.objects.count(),
            "url": reverse("admin:catalog_excelupload_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_excelupload_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "فیلدهای اطلاعات برنامه‌ریزی (نوار شیشه‌ای)",
            "description": "ستون‌های قابل نمایش در کادر بینش برنامه",
            "count": PlanningInsightField.objects.count(),
            "url": reverse("admin:catalog_planninginsightfield_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_planninginsightfield_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "قانون شناسه برنامه (بازتعریف)",
            "description": "الگوی ساخت شناسه ۱۴ رقمی تعویض",
            "count": ProgramUidScheme.objects.count(),
            "url": reverse("admin:catalog_programuidscheme_changelist"),
            "can_add": False,
            "add_url": "",
        },
        {
            "group": "داده‌های پایه",
            "title": "محصولات و قطعات",
            "description": "ویرایش سریع در «دیتای محصولات»؛ فهرست کامل در ادمین",
            "count": Product.objects.count(),
            "url": reverse("product_data"),
            "can_add": True,
            "add_url": reverse("admin:catalog_product_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "مواد مصرفی",
            "description": "مواد مصرفی به ازای هر محصول",
            "count": ProductConsumable.objects.count(),
            "url": reverse("admin:catalog_productconsumable_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productconsumable_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "واحدهای تولیدی",
            "description": "شماره و نام واحدهای تزریق / تولید",
            "count": ProductionUnit.objects.count(),
            "url": reverse("admin:catalog_productionunit_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productionunit_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "گروه‌های محصول",
            "description": "گروه اصلی محصولات",
            "count": ProductGroup.objects.count(),
            "url": reverse("admin:catalog_productgroup_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productgroup_add"),
        },
        {
            "group": "داده‌های پایه",
            "title": "گزینه‌های نوع تولید",
            "description": "گزینه‌های نوع تولید در برنامه و سوابق",
            "count": ProductionTypeOption.objects.count(),
            "url": reverse("admin:catalog_productiontypeoption_changelist"),
            "can_add": True,
            "add_url": reverse("admin:catalog_productiontypeoption_add"),
        },
        {
            "group": "کاربران و دسترسی‌ها",
            "title": "پروفایل کاربران",
            "description": "نقش و دسترسی کاربران سامانه",
            "count": UserProfile.objects.count(),
            "url": reverse("admin:accounts_userprofile_changelist"),
            "can_add": True,
            "add_url": reverse("admin:accounts_userprofile_add"),
        },
    ]
    return render(request, "catalog/system_data.html", {"sections": sections})


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
    """Tabbed product master data — editable and Excel-transfer targets."""
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
    can_edit = bool(profile and profile.can_enter_data)
    tab = resolve_tab(request.GET.get("tab"))
    context = {
        "tabs": PRODUCT_DATA_TABS,
        "active_tab": tab,
        "can_edit": can_edit,
        "counting_units": [
            {"value": "count", "label": "عدد"},
            {"value": "branch", "label": "شاخه"},
            {"value": "coil", "label": "کلاف"},
            {"value": "meter", "label": "متر"},
        ],
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
