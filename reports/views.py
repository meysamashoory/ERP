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
from .columns import COLUMN_GROUPS, normalize_columns, run_report
from .forms import (
    PrintFormForm,
    SavedReportForm,
    SendOrCopyPrintFormForm,
    SendOrCopyReportForm,
)
from .models import PrintForm, SavedReport

User = get_user_model()


def _now_jdt():
    return jdatetime.datetime.now()


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
    reports = visible_reports(request.user)
    sort = request.GET.get("sort", "number")
    direction = request.GET.get("dir", "asc")
    title_q = request.GET.get("title", "").strip()
    if title_q:
        reports = reports.filter(title__icontains=title_q)

    sort_map = {
        "number": "number",
        "title": "title",
        "type": "is_standard",
    }
    order = sort_map.get(sort, "number")
    if direction == "desc":
        order = f"-{order}"
    reports = reports.order_by(order, "id")

    rows = []
    for report in reports:
        rows.append(
            {
                "report": report,
                "can_edit": can_edit_report(request.user, report),
                "can_delete": can_delete_report(request.user, report),
                "can_send": can_create_report(request.user)
                and (report.owner_id == request.user.id or can_edit_report(request.user, report)),
                "can_copy": can_create_report(request.user)
                and (report.owner_id == request.user.id or can_view_report(request.user, report)),
            }
        )
    return render(
        request,
        "reports/list.html",
        {
            "rows": rows,
            "sort": sort,
            "dir": direction,
            "title_q": title_q,
            "users": User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("username"),
        },
    )


@login_required
def report_create(request: HttpRequest) -> HttpResponse:
    if not can_create_report(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد گزارش نیست.")
    if request.method == "POST":
        form = SavedReportForm(request.POST, user=request.user)
        if form.is_valid():
            report = form.save(commit=False)
            report.owner = request.user
            report.created_by = request.user
            report.columns = form.cleaned_data["columns_json"]
            report.data_source = form.primary_source()
            try:
                report.source_links = json.loads(request.POST.get("source_links_json") or "[]")
            except json.JSONDecodeError:
                report.source_links = []
            report.save()
            messages.success(request, "گزارش ایجاد شد.")
            return redirect("report_detail", pk=report.pk)
    else:
        form = SavedReportForm(user=request.user)
    return render(
        request,
        "reports/form.html",
        {
            "form": form,
            "column_groups": COLUMN_GROUPS,
            "columns_data": [],
            "source_links_data": [],
            "mode": "create",
            "page_title": "ایجاد گزارش",
        },
    )


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
            try:
                obj.source_links = json.loads(request.POST.get("source_links_json") or "[]")
            except json.JSONDecodeError:
                obj.source_links = []
            obj.save()
            messages.success(request, "گزارش به‌روزرسانی شد.")
            return redirect("report_detail", pk=report.pk)
    else:
        form = SavedReportForm(instance=report, user=request.user)
    return render(
        request,
        "reports/form.html",
        {
            "form": form,
            "column_groups": COLUMN_GROUPS,
            "columns_data": normalize_columns(report.columns or []),
            "source_links_data": list(report.source_links or []),
            "mode": "edit",
            "page_title": f"ویرایش گزارش — {report.title}",
            "report": report,
        },
    )


@login_required
def report_detail(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_view_report(request.user, report):
        return HttpResponseForbidden("مجاز به مشاهده این گزارش نیستید.")

    try:
        level = int(request.GET.get("level") or 1)
    except ValueError:
        level = 1
    filters = _parse_filters(request)

    headers, rows, payloads, deeper = run_report(
        report.data_source,
        report.columns or [],
        level=level,
        filters=filters,
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
        # Back goes to previous crumb
        prev = crumbs[max(0, level - 2)] if level - 2 < len(crumbs) else crumbs[0]
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

    return render(
        request,
        "reports/detail.html",
        {
            "report": report,
            "headers": headers,
            "rows": rows,
            "payloads": payloads,
            "deeper": deeper,
            "level": level,
            "filters": filters,
            "path_label": path_label,
            "parent_level": max(1, level - 1),
            "parent_query": parent_query,
            "can_go_back": level > 1 or bool(filters),
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
        columns=list(report.columns or []),
        source_links=list(report.source_links or []),
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
        columns=list(report.columns or []),
        source_links=list(report.source_links or []),
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
    forms_qs = visible_forms(request.user)
    sort = request.GET.get("sort", "number")
    direction = request.GET.get("dir", "asc")
    title_q = request.GET.get("title", "").strip()
    if title_q:
        forms_qs = forms_qs.filter(title__icontains=title_q)
    sort_map = {"number": "number", "title": "title", "type": "is_standard"}
    order = sort_map.get(sort, "number")
    if direction == "desc":
        order = f"-{order}"
    forms_qs = forms_qs.order_by(order, "id")

    rows = []
    for form_obj in forms_qs:
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
            "column_groups": COLUMN_GROUPS,
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
            "column_groups": COLUMN_GROUPS,
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
            "column_groups": COLUMN_GROUPS,
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
