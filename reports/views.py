from __future__ import annotations

import json
from urllib.parse import urlencode

import jdatetime
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.exports import export_excel, export_pdf

from planning.utils import format_jdate

from .access import (
    can_create_form,
    can_create_report,
    can_delete_form,
    can_delete_report,
    can_edit_form,
    can_edit_report,
    can_view_form,
    can_view_report,
    visible_forms,
    visible_reports,
)
from .columns import (
    get_column_groups,
    column_keyability_map,
    entry_sheet_count,
    level_display_meta,
    level_entry_meta,
    normalize_columns,
    persist_column_uids,
    row_sheet_number,
    run_report,
)
from .form_purposes import (
    PURPOSE_PRODUCTION,
    PURPOSE_REPORTS,
    PURPOSE_WEEKLY,
    forms_for_purpose,
    purpose_source_groups,
    report_level_groups,
)
from .forms import (
    PrintFormForm,
    SavedReportForm,
    SendOrCopyPrintFormForm,
    SendOrCopyReportForm,
)
from .models import PrintForm, ReportAccessMode, SavedReport

User = get_user_model()


def _now_jdt():
    return jdatetime.datetime.now()


def _designer_extra(user) -> dict:
    """Purpose catalogs + saved reports (with levels) for the form designer."""
    catalogs = {
        PURPOSE_WEEKLY: purpose_source_groups(PURPOSE_WEEKLY),
        PURPOSE_PRODUCTION: purpose_source_groups(PURPOSE_PRODUCTION),
    }
    reports_payload = []
    for rep in visible_reports(user).order_by("number", "id"):
        reports_payload.append({
            "id": rep.pk,
            "number": rep.number,
            "title": rep.title,
            "access_mode": rep.access_mode,
            "sheet_count": entry_sheet_count(rep.entry_data),
            "levels": report_level_groups(rep),
        })
    return {
        "purpose_catalogs": catalogs,
        "saved_reports": reports_payload,
    }


def _forms_list_payload(user, purpose: str, report_id=None) -> list[dict]:
    items = []
    for f in forms_for_purpose(user, purpose, report_id=report_id):
        items.append({"id": f.pk, "number": f.number, "title": f.title})
    return items


def _forms_context_for_lists(user) -> dict:
    return {
        "forms_weekly": _forms_list_payload(user, PURPOSE_WEEKLY),
        "forms_production": _forms_list_payload(user, PURPOSE_PRODUCTION),
        "forms_reports_by_report": {
            str(r.pk): _forms_list_payload(user, PURPOSE_REPORTS, report_id=r.pk)
            for r in visible_reports(user)
        },
        "forms_reports_all": _forms_list_payload(user, PURPOSE_REPORTS),
    }


def _parse_filters(request: HttpRequest) -> dict:
    filters = {}
    for key, value in request.GET.items():
        if key.startswith("f_") and value != "":
            filters[key[2:]] = value
    return filters


def _breadcrumb(filters: dict, level: int) -> list[dict]:
    crumbs = [{"level": 1, "label": "سطح ۱", "query": ""}]
    # Rebuild cumulative path from filters in stable key order for display
    if not filters:
        return crumbs[:1] if level <= 1 else crumbs
    parts = []
    for i, (k, v) in enumerate(filters.items(), start=1):
        parts.append((k, v))
        q = urlencode({f"f_{a}": b for a, b in parts})
        crumbs.append(
            {
                "level": i + 1,
                "label": f"سطح {i + 1} — {v}",
                "query": q,
            }
        )
    return crumbs


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@login_required
def report_list(request: HttpRequest) -> HttpResponse:
    from core.natsort import natural_key

    reports = list(visible_reports(request.user))
    sort = request.GET.get("sort", "number")
    direction = request.GET.get("dir", "asc")
    reverse = direction == "desc"
    if sort == "title":
        reports.sort(key=lambda r: (r.title or "").casefold(), reverse=reverse)
    else:
        reports.sort(key=lambda r: (natural_key(r.number), r.id), reverse=reverse)

    rows = []
    for report in reports:
        forms_for_report = _forms_list_payload(request.user, PURPOSE_REPORTS, report_id=report.pk)
        rows.append(
            {
                "report": report,
                "can_edit": can_edit_report(request.user, report),
                "can_delete": can_delete_report(request.user, report),
                "can_send": can_create_report(request.user)
                and (report.owner_id == request.user.id or can_edit_report(request.user, report)),
                "can_copy": can_create_report(request.user)
                and (report.owner_id == request.user.id or can_view_report(request.user, report)),
                "forms": forms_for_report,
                "forms_json": json.dumps(forms_for_report, ensure_ascii=False),
                "forms_count": len(forms_for_report),
            }
        )
    return render(
        request,
        "reports/list.html",
        {
            "rows": rows,
            "sort": sort,
            "dir": direction,
            "users": User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("username"),
            "can_create": can_create_report(request.user),
        },
    )


@login_required
def report_create(request: HttpRequest) -> HttpResponse:
    if not can_create_report(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد گزارش نیست.")
    if request.method != "POST":
        return redirect("report_list")
    form = SavedReportForm(request.POST, user=request.user, allow_empty_columns=True)
    if form.is_valid():
        report = form.save(commit=False)
        report.owner = request.user
        report.created_by = request.user
        report.columns = form.cleaned_data["columns_json"] or []
        report.data_source = form.primary_source()
        report.access_mode = form.cleaned_data.get("access_mode") or ReportAccessMode.READONLY
        try:
            report.source_links = json.loads(request.POST.get("source_links_json") or "[]")
        except json.JSONDecodeError:
            report.source_links = []
        report.save()
        messages.success(request, "گزارش ایجاد شد. ستون‌ها را انتخاب کنید.")
        return redirect("report_edit", pk=report.pk)
    for field, errors in form.errors.items():
        for err in errors:
            label = form.fields[field].label if field in form.fields else field
            messages.error(request, f"{label}: {err}" if label else str(err))
    return redirect("report_list")


@login_required
def report_edit(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_edit_report(request.user, report):
        return HttpResponseForbidden("مجاز به ویرایش این گزارش نیستید.")
    if request.method == "POST":
        form = SavedReportForm(request.POST, instance=report, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.columns = form.cleaned_data["columns_json"]
            obj.data_source = form.primary_source()
            obj.access_mode = form.cleaned_data.get("access_mode") or ReportAccessMode.READONLY
            try:
                obj.source_links = json.loads(request.POST.get("source_links_json") or "[]")
            except json.JSONDecodeError:
                obj.source_links = []
            obj.save()
            messages.success(request, "گزارش به‌روزرسانی شد.")
            return redirect("report_detail", pk=report.pk)
    else:
        form = SavedReportForm(instance=report, user=request.user)
    from reports.formula import FORMULA_FUNCTION_CATALOG, NUMBER_FORMAT_PRESETS

    columns_data = persist_column_uids(report)
    return render(
        request,
        "reports/form.html",
        {
            "form": form,
            "column_groups": get_column_groups(),
            "column_keyability": column_keyability_map(),
            "columns_data": columns_data,
            "source_links_data": list(report.source_links or []),
            "formula_catalog": FORMULA_FUNCTION_CATALOG,
            "number_format_presets": NUMBER_FORMAT_PRESETS,
            "mode": "edit",
            "page_title": report.heading_label,
            "report": report,
        },
    )


@login_required
def report_detail(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_view_report(request.user, report):
        return HttpResponseForbidden("مجاز به مشاهده این گزارش نیستید.")

    if request.method == "POST" and request.POST.get("action") == "update_meta":
        if not can_edit_report(request.user, report):
            return HttpResponseForbidden("مجاز به ویرایش این گزارش نیستید.")
        title = (request.POST.get("title") or "").strip()[:200]
        description = (request.POST.get("description") or "").strip()[:300]
        try:
            number = int(request.POST.get("number") or 0)
        except (TypeError, ValueError):
            number = 0
        if not title:
            messages.error(request, "عنوان گزارش را وارد کنید.")
            return redirect("report_detail", pk=report.pk)
        if number < 1 or number > 999:
            messages.error(request, "شماره گزارش باید بین ۱ تا ۹۹۹ باشد.")
            return redirect("report_detail", pk=report.pk)
        conflict = (
            SavedReport.objects.filter(owner=report.owner, number=number)
            .exclude(pk=report.pk)
            .exists()
        )
        if conflict:
            messages.error(request, "شماره گزارش وجود دارد")
            return redirect("report_detail", pk=report.pk)
        report.title = title
        report.description = description
        report.number = number
        report.save(update_fields=["title", "description", "number", "updated_at"])
        messages.success(request, "عنوان گزارش به‌روزرسانی شد.")
        return redirect("report_detail", pk=report.pk)

    if request.method == "POST" and request.POST.get("action") == "save_entry":
        if report.access_mode != ReportAccessMode.EDITABLE:
            return HttpResponseForbidden("این گزارش قابل ویرایش نیست.")
        if not can_edit_report(request.user, report):
            return HttpResponseForbidden("مجاز به ویرایش داده این گزارش نیستید.")
        try:
            payload = json.loads(request.POST.get("entry_payload") or "{}")
        except json.JSONDecodeError:
            messages.error(request, "داده ورودی نامعتبر است.")
            return redirect(request.get_full_path())
        entry = dict(report.entry_data or {}) if isinstance(report.entry_data, dict) else {}

        rows_in = payload.get("rows") if isinstance(payload, dict) else None
        if isinstance(rows_in, list):
            try:
                sheet_count = int(payload.get("sheet_count") or 1)
            except (TypeError, ValueError):
                sheet_count = 1
            sheet_count = max(1, min(200, sheet_count))
            clean_rows = []
            for row in rows_in[:200]:
                if not isinstance(row, dict):
                    continue
                clean = {}
                sheet_n = row_sheet_number(row)
                sheet_count = max(sheet_count, sheet_n)
                clean["sheet"] = sheet_n
                for k, v in row.items():
                    key = str(k)[:80]
                    if not key or key.startswith("_") or key == "sheet":
                        continue
                    clean[key] = str(v)[:2000]
                clean_rows.append(clean)
            entry["rows"] = clean_rows or [{"sheet": 1}]
            entry["sheet_count"] = sheet_count
            if clean_rows:
                first_vals = {k: v for k, v in clean_rows[0].items() if k != "sheet"}
                entry["values"] = dict(first_vals)
                entry["cells"] = {"": dict(first_vals)}
            report.entry_data = entry
            report.save(update_fields=["entry_data", "updated_at"])
            messages.success(request, "تغییرات ذخیره شد.")
            q = request.GET.urlencode()
            return redirect(request.path + (("?" + q) if q else ""))

        cells_in = payload.get("cells") if isinstance(payload, dict) else {}
        if not isinstance(cells_in, dict):
            cells_in = {}
        cells = dict(entry.get("cells") or {}) if isinstance(entry.get("cells"), dict) else {}
        ordered_rows = []
        for sig, values in cells_in.items():
            if not isinstance(values, dict):
                continue
            clean = {}
            for k, v in values.items():
                key = str(k)[:80]
                if not key:
                    continue
                clean[key] = str(v)[:2000]
            cells[str(sig)] = clean
            ordered_rows.append(clean)
            if str(sig) in ("", "__empty__"):
                entry["values"] = clean
        entry["cells"] = cells
        if ordered_rows:
            entry["rows"] = ordered_rows
        report.entry_data = entry
        report.save(update_fields=["entry_data", "updated_at"])
        messages.success(request, "تغییرات ذخیره شد.")
        q = request.GET.urlencode()
        return redirect(request.path + (("?" + q) if q else ""))

    try:
        level = int(request.GET.get("level") or 1)
    except ValueError:
        level = 1
    filters = _parse_filters(request)

    persist_column_uids(report)

    headers, rows, payloads, deeper = run_report(
        report.data_source,
        report.columns or [],
        level=level,
        filters=filters,
        entry_data=report.entry_data or {},
    )

    export = request.GET.get("export")
    if export in {"excel", "pdf"}:
        # Export current level view
        if export == "excel":
            return export_excel(f"report_{report.number}", headers, rows, report.title)
        return export_pdf(f"report_{report.number}", headers, rows, report.title)

    crumbs = _breadcrumb(filters, level)
    parent_query = ""
    if level > 1 and crumbs:
        # Better: strip last filter
        items = list(filters.items())
        if items:
            parent_filters = dict(items[:-1])
            parent_query = urlencode({f"f_{k}": v for k, v in parent_filters.items()})
            parent_level = level - 1
        else:
            parent_level = 1
            parent_query = ""
    else:
        parent_level = 1

    # Context path label
    path_label = "سطح ۱"
    if filters:
        parts = [f"{v}" for v in filters.values()]
        path_label = f"سطح {level} — " + " ← ".join(parts)

    entry_meta = level_entry_meta(report.columns or [], level=level)
    display_meta = level_display_meta(report.columns or [], level=level)
    header_cells = []
    for i, h in enumerate(headers):
        meta = display_meta[i] if i < len(display_meta) else {}
        header_cells.append({
            "label": h,
            "width": int(meta.get("width") or 0) if isinstance(meta, dict) else 0,
            "is_key": bool(meta.get("is_key")) if isinstance(meta, dict) else False,
        })
    is_editable_report = report.access_mode == ReportAccessMode.EDITABLE
    can_edit_entry = is_editable_report and can_edit_report(request.user, report) and bool(entry_meta)
    can_edit_meta = can_edit_report(request.user, report)
    sheet_count = entry_sheet_count(report.entry_data)
    row_sheets = [int(p.get("_sheet") or 1) for p in payloads] if payloads else [1]

    return render(
        request,
        "reports/detail.html",
        {
            "report": report,
            "headers": headers,
            "header_cells": header_cells,
            "rows": rows,
            "payloads": payloads,
            "deeper": deeper,
            "level": level,
            "filters": filters,
            "path_label": path_label,
            "parent_level": max(1, level - 1),
            "parent_query": parent_query,
            "can_go_back": level > 1 or bool(filters),
            "is_editable_report": is_editable_report,
            "can_edit_entry": can_edit_entry,
            "can_edit_meta": can_edit_meta,
            "entry_meta": entry_meta,
            "entry_meta_json": entry_meta,
            "display_meta": display_meta,
            "display_meta_json": display_meta,
            "entry_sheet_count": sheet_count,
            "entry_row_sheets": row_sheets,
        },
    )


@login_required
@require_POST
def report_delete(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_delete_report(request.user, report):
        return HttpResponseForbidden("مجاز به حذف این گزارش نیستید.")
    report.delete()
    messages.success(request, "گزارش حذف شد.")
    return redirect("report_list")


@login_required
@require_POST
def report_send(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_view_report(request.user, report):
        return HttpResponseForbidden("مجاز به ارسال این گزارش نیستید.")
    if not can_create_report(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ارسال گزارش نیست.")
    if not (report.owner_id == request.user.id or can_edit_report(request.user, report)):
        return HttpResponseForbidden("فقط مالک گزارش می‌تواند آن را ارسال کند.")

    form = SendOrCopyReportForm(request.POST, sender=request.user, report=report, mode="send")
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("report_list")

    recipient = form.cleaned_data["recipient"]
    SavedReport.objects.create(
        owner=recipient,
        title=form.cleaned_data["title"],
        description=form.cleaned_data.get("description") or "",
        number=form.cleaned_data["number"],
        data_source=report.data_source,
        access_mode=getattr(report, "access_mode", ReportAccessMode.READONLY) or ReportAccessMode.READONLY,
        columns=list(report.columns or []),
        source_links=list(report.source_links or []),
        entry_data=dict(report.entry_data or {}) if isinstance(report.entry_data, dict) else {},
        is_standard=False,
        created_by=request.user,
        source_report=report,
        sent_at=_now_jdt(),
    )
    messages.success(request, f"گزارش برای «{recipient.username}» ارسال شد.")
    return redirect("report_list")


@login_required
@require_POST
def report_copy(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_view_report(request.user, report):
        return HttpResponseForbidden("مجاز به کپی این گزارش نیستید.")
    if not can_create_report(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد کپی نیست.")

    form = SendOrCopyReportForm(request.POST, sender=request.user, report=report, mode="copy")
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("report_list")

    SavedReport.objects.create(
        owner=request.user,
        title=form.cleaned_data["title"],
        description=form.cleaned_data.get("description") or "",
        number=form.cleaned_data["number"],
        data_source=report.data_source,
        access_mode=getattr(report, "access_mode", ReportAccessMode.READONLY) or ReportAccessMode.READONLY,
        columns=list(report.columns or []),
        source_links=list(report.source_links or []),
        entry_data=dict(report.entry_data or {}) if isinstance(report.entry_data, dict) else {},
        is_standard=False,
        created_by=request.user,
        source_report=report,
        sent_at=_now_jdt(),
    )
    messages.success(request, "کپی گزارش ایجاد شد.")
    return redirect("report_list")


# ---------------------------------------------------------------------------
# Print forms
# ---------------------------------------------------------------------------


@login_required
def form_list(request: HttpRequest) -> HttpResponse:
    from core.natsort import natural_key

    forms_qs = visible_forms(request.user)
    sort = request.GET.get("sort", "number")
    direction = request.GET.get("dir", "asc")
    title_q = request.GET.get("title", "").strip()
    if title_q:
        forms_qs = forms_qs.filter(title__icontains=title_q)
    forms_list = list(forms_qs)
    reverse = direction == "desc"
    if sort == "title":
        forms_list.sort(key=lambda f: (f.title or "").casefold(), reverse=reverse)
    elif sort == "type":
        forms_list.sort(key=lambda f: (0 if f.is_standard else 1, natural_key(f.number), f.id), reverse=reverse)
    else:
        forms_list.sort(key=lambda f: (natural_key(f.number), f.id), reverse=reverse)

    rows = []
    for form_obj in forms_list:
        rows.append(
            {
                "form": form_obj,
                "can_edit": can_edit_form(request.user, form_obj),
                "can_delete": can_delete_form(request.user, form_obj),
                "can_send": can_create_form(request.user)
                and (form_obj.owner_id == request.user.id or can_edit_form(request.user, form_obj)),
                "can_copy": can_create_form(request.user) and can_view_form(request.user, form_obj),
            }
        )
    return render(
        request,
        "print_forms/list.html",
        {
            "rows": rows,
            "sort": sort,
            "dir": direction,
            "title_q": title_q,
            "users": User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("username"),
            "can_create": can_create_form(request.user),
        },
    )


@login_required
def form_create(request: HttpRequest) -> HttpResponse:
    if not can_create_form(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد فرم نیست.")
    if request.method == "POST" and request.headers.get("X-Requested-With") != "XMLHttpRequest":
        # Non-AJAX fallback
        form = PrintFormForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.created_by = request.user
            obj.frames = form.cleaned_data.get("frames_json") or []
            obj.page_settings = form.cleaned_data.get("page_settings_json") or {}
            obj.save()
            messages.success(request, "فرم ایجاد شد.")
            return redirect("print_form_list")
    else:
        form = PrintFormForm(user=request.user)
        used = set(PrintForm.objects.filter(owner=request.user).values_list("number", flat=True))
        n = next((i for i in range(1, 1000) if i not in used), 1)
        form.fields["title"].initial = form.fields["title"].initial or "فرم جدید"
        form.fields["number"].initial = form.fields["number"].initial or n
    return render(
        request,
        "print_forms/designer.html",
        {
            "form": form,
            "mode": "create",
            "page_title": "ایجاد فرم",
            "frames_json": "[]",
            "page_settings_json": form.fields["page_settings_json"].initial or "{}",
            "column_groups": get_column_groups(),
            **_designer_extra(request.user),
        },
    )


@login_required
def form_edit(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_edit_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به ویرایش این فرم نیستید.")
    if request.method == "POST" and request.headers.get("X-Requested-With") != "XMLHttpRequest":
        form = PrintFormForm(request.POST, instance=form_obj, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.frames = form.cleaned_data.get("frames_json") or []
            obj.page_settings = form.cleaned_data.get("page_settings_json") or {}
            obj.save()
            messages.success(request, "فرم به‌روزرسانی شد.")
            return redirect("print_form_list")
    else:
        form = PrintFormForm(instance=form_obj, user=request.user)
    return render(
        request,
        "print_forms/designer.html",
        {
            "form": form,
            "mode": "edit",
            "page_title": f"ویرایش فرم — {form_obj.title}",
            "print_form": form_obj,
            "frames_json": json.dumps(form_obj.frames or [], ensure_ascii=False),
            "page_settings_json": json.dumps(form_obj.page_settings or {}, ensure_ascii=False),
            "column_groups": get_column_groups(),
            **_designer_extra(request.user),
        },
    )


@login_required
@require_POST
def form_save_ajax(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """AJAX save for the fullscreen designer (stay on page or close after register)."""
    from django.http import JsonResponse

    if not can_create_form(request.user):
        return JsonResponse({"ok": False, "error": "مجاز نیستید."}, status=403)

    form_obj = None
    if pk is not None:
        form_obj = get_object_or_404(PrintForm, pk=pk)
        if not can_edit_form(request.user, form_obj):
            return JsonResponse({"ok": False, "error": "مجاز به ویرایش نیستید."}, status=403)
        form = PrintFormForm(request.POST, instance=form_obj, user=request.user)
    else:
        form = PrintFormForm(request.POST, user=request.user)

    if not form.is_valid():
        errs = []
        for field, messages_list in form.errors.items():
            for msg in messages_list:
                errs.append(f"{field}: {msg}")
        return JsonResponse({"ok": False, "error": " | ".join(errs) or "مقادیر نامعتبر"}, status=400)

    obj = form.save(commit=False)
    if form_obj is None:
        obj.owner = request.user
        obj.created_by = request.user
    obj.frames = form.cleaned_data.get("frames_json") or []
    obj.page_settings = form.cleaned_data.get("page_settings_json") or {}
    obj.save()
    from django.urls import reverse
    return JsonResponse({
        "ok": True,
        "pk": obj.pk,
        "title": obj.title,
        "save_url": reverse("print_form_save_ajax", args=[obj.pk]),
        "edit_url": reverse("print_form_edit", args=[obj.pk]),
    })


@login_required
def form_detail(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_view_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به مشاهده این فرم نیستید.")
    return render(
        request,
        "print_forms/detail.html",
        {
            "print_form": form_obj,
            "frames_json": json.dumps(form_obj.frames or [], ensure_ascii=False),
            "page_settings_json": json.dumps(form_obj.page_settings or {}, ensure_ascii=False),
            "column_groups": get_column_groups(),
        },
    )


def _item_values_from_plan_item(item) -> dict:
    weekday = ""
    try:
        weekday = item.get_mold_change_weekday_display()
    except Exception:
        weekday = str(getattr(item, "mold_change_weekday", "") or "")
    return {
        "uid": str(getattr(item, "uid", "") or ""),
        "product_code": item.product.code if item.product_id else "",
        "product_name": item.product.name if item.product_id else "",
        "unit": f"واحد {item.machine.unit.number}" if item.machine_id and item.machine.unit_id else "",
        "machine": str(item.machine.number) if item.machine_id else "",
        "mold_change_day": weekday,
        "mold_change_date": format_jdate(getattr(item, "mold_change_date", None)),
        "cavities": str(getattr(item, "active_cavities", "") or ""),
    }


def _context_fill_rows(ctx: str, obj_id: int, item_id: int | None = None) -> list[dict]:
    """Return one dict per data row for filling extended form fields."""
    rows: list[dict] = []
    if ctx == "weekly_plan":
        from planning.models import WeeklyPlan, WeeklyPlanItem
        plan = WeeklyPlan.objects.select_related("created_by").filter(pk=obj_id).first()
        if not plan:
            return rows
        base = {
            "program_number": str(plan.program_number),
            "date": format_jdate(plan.date),
            "weekday": plan.weekday_name,
            "status": plan.get_status_display(),
            "created_by": plan.created_by.username if plan.created_by_id else "",
        }
        qs = WeeklyPlanItem.objects.select_related("product", "machine__unit").filter(plan=plan).order_by("id")
        if item_id:
            qs = qs.filter(pk=item_id)
        items = list(qs)
        if not items:
            rows.append(dict(base))
            return rows
        for item in items:
            row = dict(base)
            row.update(_item_values_from_plan_item(item))
            rows.append(row)
        return rows
    if ctx == "prod_fitting":
        from production.models import ProductionDayEntry, ProductionProgram
        program = (
            ProductionProgram.objects.select_related(
                "item__product", "item__machine__unit", "item__plan"
            )
            .filter(pk=obj_id)
            .first()
        )
        if not program:
            return rows
        entries = list(ProductionDayEntry.objects.filter(program=program))
        produced = sum(e.produced_quantity for e in entries)
        planned = sum(e.planned_quantity for e in entries)
        scrap = sum(e.scrap_quantity for e in entries)
        rows.append({
            "uid": str(getattr(program, "resolved_uid", None) or program.item.uid),
            "program_number": str(program.item.plan.program_number),
            "machine": program.machine_label,
            "product_code": program.item.product.code,
            "product_name": program.item.product.name,
            "status": program.get_status_display(),
            "produced": str(produced),
            "planned": str(planned),
            "scrap": str(scrap),
            "date": format_jdate(program.item.plan.date),
        })
        return rows
    if ctx == "prod_pipe":
        from production.models import PipeProduction
        pipe = PipeProduction.objects.select_related("unit", "line", "product").filter(pk=obj_id).first()
        if not pipe:
            return rows
        rows.append({
            "date": format_jdate(pipe.date),
            "unit": f"واحد {pipe.unit.number}",
            "line": str(pipe.line.number),
            "pipe_type": pipe.pipe_type,
            "product_code": pipe.product.code if pipe.product_id else "",
            "product_name": pipe.product.name if pipe.product_id else "",
            "produced": str(pipe.produced_quantity),
            "planned": str(pipe.planned_quantity),
            "deviation": str(pipe.deviation),
        })
        return rows
    if ctx == "report":
        report = SavedReport.objects.filter(pk=obj_id).first()
        if not report:
            return rows
        try:
            level = int(item_id or 1)
        except (TypeError, ValueError):
            level = 1
        from .columns import data_key, normalize_columns, persist_column_uids, storage_key

        persist_column_uids(report)
        level_cols = [
            c
            for c in normalize_columns(report.columns or [])
            if int(c.get("level") or 1) == level
        ]
        headers, data_rows, _payloads, _deeper = run_report(
            report.data_source,
            report.columns or [],
            level=level,
            filters={},
            entry_data=report.entry_data or {},
        )
        key_counts: dict[str, int] = {}
        for c in level_cols:
            dk = data_key(c)
            key_counts[dk] = key_counts.get(dk, 0) + 1
        for idx, data_row in enumerate(data_rows):
            row = {
                "report_title": report.title,
                "report_number": str(report.number),
            }
            for i, h in enumerate(headers):
                sk = ""
                dk = ""
                if i < len(level_cols):
                    sk = storage_key(level_cols[i])
                    dk = data_key(level_cols[i])
                if not sk:
                    sk = f"col_{i}"
                val = data_row[i] if i < len(data_row) else ""
                row[sk] = str(val)
                row[h] = str(val)
                # Backward-compatible bind by semantic key when unique.
                if dk and key_counts.get(dk, 0) == 1:
                    row[dk] = str(val)
            if idx < len(_payloads):
                try:
                    row["_sheet"] = int(_payloads[idx].get("_sheet") or 1)
                except (TypeError, ValueError):
                    row["_sheet"] = 1
            else:
                row["_sheet"] = 1
            rows.append(row)
        return rows
    return rows


def _context_row_values(ctx: str, obj_id: int, item_id: int | None = None) -> dict:
    """Backward-compatible single-row map (first fill row). """
    rows = _context_fill_rows(ctx, obj_id, item_id)
    return rows[0] if rows else {}


@login_required
def form_print_fill(request: HttpRequest, pk: int) -> HttpResponse:
    """Render a form filled with values from a planning/production/report context row."""
    form_obj = get_object_or_404(PrintForm.objects.select_related("linked_report"), pk=pk)
    if not can_view_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به مشاهده این فرم نیستید.")
    ctx = (request.GET.get("ctx") or "").strip()
    try:
        obj_id = int(request.GET.get("id") or 0)
    except ValueError:
        obj_id = 0
    item_id = request.GET.get("item")
    try:
        item_id_int = int(item_id) if item_id else None
    except ValueError:
        item_id_int = None
    fill_rows = _context_fill_rows(ctx, obj_id, item_id_int) if obj_id else []
    sheet_count = 1
    for fr in form_obj.frames or []:
        if isinstance(fr, dict):
            try:
                sheet_count = max(sheet_count, int(fr.get("sheet") or 1))
            except (TypeError, ValueError):
                pass
    for row in fill_rows:
        if isinstance(row, dict):
            try:
                sheet_count = max(sheet_count, int(row.get("_sheet") or 1))
            except (TypeError, ValueError):
                pass
    if form_obj.linked_report_id and getattr(form_obj, "linked_report", None):
        sheet_count = max(sheet_count, entry_sheet_count(form_obj.linked_report.entry_data))
    return render(
        request,
        "print_forms/print_fill.html",
        {
            "print_form": form_obj,
            "frames_json": json.dumps(form_obj.frames or [], ensure_ascii=False),
            "page_settings_json": json.dumps(form_obj.page_settings or {}, ensure_ascii=False),
            "fill_rows_json": json.dumps(fill_rows, ensure_ascii=False),
            "sheet_count": sheet_count,
            "auto_print": request.GET.get("autoprint") == "1",
        },
    )


@login_required
@require_POST
def form_delete(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_delete_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به حذف این فرم نیستید.")
    form_obj.delete()
    messages.success(request, "فرم حذف شد.")
    return redirect("print_form_list")


@login_required
@require_POST
def form_send(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_view_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به ارسال این فرم نیستید.")
    if not can_create_form(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ارسال فرم نیست.")
    if not (form_obj.owner_id == request.user.id or can_edit_form(request.user, form_obj)):
        return HttpResponseForbidden("فقط مالک فرم می‌تواند آن را ارسال کند.")

    form = SendOrCopyPrintFormForm(request.POST, sender=request.user, form_obj=form_obj, mode="send")
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("print_form_list")

    recipient = form.cleaned_data["recipient"]
    PrintForm.objects.create(
        owner=recipient,
        title=form.cleaned_data["title"],
        description=form.cleaned_data.get("description") or "",
        number=form.cleaned_data["number"],
        frames=list(form_obj.frames or []),
        page_width_mm=form_obj.page_width_mm,
        page_height_mm=form_obj.page_height_mm,
        is_standard=False,
        created_by=request.user,
        source_form=form_obj,
        sent_at=_now_jdt(),
    )
    messages.success(request, f"فرم برای «{recipient.username}» ارسال شد.")
    return redirect("print_form_list")


@login_required
@require_POST
def form_copy(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_view_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به کپی این فرم نیستید.")
    if not can_create_form(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد کپی نیست.")

    form = SendOrCopyPrintFormForm(request.POST, sender=request.user, form_obj=form_obj, mode="copy")
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("print_form_list")

    PrintForm.objects.create(
        owner=request.user,
        title=form.cleaned_data["title"],
        description=form.cleaned_data.get("description") or "",
        number=form.cleaned_data["number"],
        frames=list(form_obj.frames or []),
        page_width_mm=form_obj.page_width_mm,
        page_height_mm=form_obj.page_height_mm,
        is_standard=False,
        created_by=request.user,
        source_form=form_obj,
        sent_at=_now_jdt(),
    )
    messages.success(request, "کپی فرم ایجاد شد.")
    return redirect("print_form_list")
