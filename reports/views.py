from __future__ import annotations

import json

import jdatetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import get_profile
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
from .columns import run_report
from .forms import (
    PrintFormForm,
    SavedReportForm,
    SendPrintFormForm,
    SendReportForm,
)
from .models import PrintForm, SavedReport


def _parse_jdatetime(value: str):
    value = (value or "").strip()
    now = jdatetime.datetime.now()
    if not value:
        return now
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            parsed = jdatetime.datetime.strptime(value, fmt)
            if fmt == "%Y/%m/%d":
                parsed = parsed.replace(hour=now.hour, minute=now.minute, second=now.second)
            return parsed
        except ValueError:
            continue
    return now


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@login_required
def report_list(request: HttpRequest) -> HttpResponse:
    reports = visible_reports(request.user)
    profile = get_profile(request.user)
    rows = []
    for report in reports:
        rows.append(
            {
                "report": report,
                "can_edit": can_edit_report(request.user, report),
                "can_delete": can_delete_report(request.user, report),
            }
        )
    return render(
        request,
        "reports/list.html",
        {
            "rows": rows,
            "can_create": can_create_report(request.user),
            "profile": profile,
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
            report.columns = form.cleaned_data["columns"]
            if report.is_standard:
                # Standard reports stay owned by the manager who created them.
                report.owner = request.user
            report.save()
            form.save_m2m()
            messages.success(request, "گزارش ایجاد شد.")
            return redirect("report_detail", pk=report.pk)
    else:
        initial = {}
        source = request.GET.get("source")
        if source in {"fitting", "pipe", "product"}:
            initial["data_source"] = source
        form = SavedReportForm(user=request.user, initial=initial)
    return render(
        request,
        "reports/form.html",
        {
            "form": form,
            "column_groups": form.column_groups,
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
            obj.columns = form.cleaned_data["columns"]
            # Non-managers cannot flip standard; clean already enforces.
            obj.save()
            form.save_m2m()
            messages.success(request, "گزارش به‌روزرسانی شد.")
            return redirect("report_detail", pk=report.pk)
    else:
        form = SavedReportForm(instance=report, user=request.user)
    return render(
        request,
        "reports/form.html",
        {
            "form": form,
            "column_groups": form.column_groups,
            "mode": "edit",
            "page_title": "ویرایش گزارش",
            "report": report,
        },
    )


@login_required
def report_detail(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(SavedReport, pk=pk)
    if not can_view_report(request.user, report):
        return HttpResponseForbidden("مجاز به مشاهده این گزارش نیستید.")

    headers, rows = run_report(report.data_source, list(report.columns or []))
    export = request.GET.get("export")
    if export == "excel":
        return export_excel(f"report_{report.number}", headers, rows, report.title)
    if export == "pdf":
        return export_pdf(f"report_{report.number}", headers, rows, report.title)

    send_form = None
    if can_edit_report(request.user, report) or (
        can_create_report(request.user) and report.owner_id == request.user.id
    ):
        send_form = SendReportForm(sender=request.user, report=report)

    return render(
        request,
        "reports/detail.html",
        {
            "report": report,
            "headers": headers,
            "rows": rows,
            "can_edit": can_edit_report(request.user, report),
            "can_delete": can_delete_report(request.user, report),
            "can_send": bool(send_form),
            "send_form": send_form,
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
    # Owner or someone with edit rights (manager on standard) may send.
    if not (report.owner_id == request.user.id or can_edit_report(request.user, report)):
        return HttpResponseForbidden("فقط مالک گزارش می‌تواند آن را ارسال کند.")

    form = SendReportForm(request.POST, sender=request.user, report=report)
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("report_detail", pk=report.pk)

    recipient = form.cleaned_data["recipient"]
    copy = SavedReport.objects.create(
        owner=recipient,
        title=form.cleaned_data["title"],
        number=form.cleaned_data["number"],
        data_source=report.data_source,
        columns=list(report.columns or []),
        is_standard=False,
        created_by=request.user,
        source_report=report,
        sent_at=_parse_jdatetime(form.cleaned_data.get("sent_at", "")),
    )
    messages.success(request, f"گزارش برای «{recipient.username}» ارسال شد.")
    return redirect("report_detail", pk=copy.pk)


# ---------------------------------------------------------------------------
# Print forms
# ---------------------------------------------------------------------------


@login_required
def form_list(request: HttpRequest) -> HttpResponse:
    forms_qs = visible_forms(request.user)
    rows = []
    for form_obj in forms_qs:
        rows.append(
            {
                "form": form_obj,
                "can_edit": can_edit_form(request.user, form_obj),
                "can_delete": can_delete_form(request.user, form_obj),
            }
        )
    return render(
        request,
        "print_forms/list.html",
        {
            "rows": rows,
            "can_create": can_create_form(request.user),
        },
    )


@login_required
def form_create(request: HttpRequest) -> HttpResponse:
    if not can_create_form(request.user):
        return HttpResponseForbidden("مشاهده‌گر مجاز به ایجاد فرم نیست.")
    if request.method == "POST":
        form = PrintFormForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.created_by = request.user
            obj.frames = form.cleaned_data.get("frames_json") or []
            obj.save()
            form.save_m2m()
            messages.success(request, "فرم ایجاد شد.")
            return redirect("print_form_detail", pk=obj.pk)
    else:
        form = PrintFormForm(user=request.user)
    return render(
        request,
        "print_forms/form.html",
        {
            "form": form,
            "mode": "create",
            "page_title": "ایجاد فرم",
            "frames_json": "[]",
        },
    )


@login_required
def form_edit(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_edit_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به ویرایش این فرم نیستید.")
    if request.method == "POST":
        form = PrintFormForm(request.POST, instance=form_obj, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.frames = form.cleaned_data.get("frames_json") or []
            obj.save()
            form.save_m2m()
            messages.success(request, "فرم به‌روزرسانی شد.")
            return redirect("print_form_detail", pk=obj.pk)
    else:
        form = PrintFormForm(instance=form_obj, user=request.user)
    return render(
        request,
        "print_forms/form.html",
        {
            "form": form,
            "mode": "edit",
            "page_title": "ویرایش فرم",
            "print_form": form_obj,
            "frames_json": json.dumps(form_obj.frames or [], ensure_ascii=False),
        },
    )


@login_required
def form_detail(request: HttpRequest, pk: int) -> HttpResponse:
    form_obj = get_object_or_404(PrintForm, pk=pk)
    if not can_view_form(request.user, form_obj):
        return HttpResponseForbidden("مجاز به مشاهده این فرم نیستید.")
    send_form = None
    if form_obj.owner_id == request.user.id or can_edit_form(request.user, form_obj):
        if can_create_form(request.user):
            send_form = SendPrintFormForm(sender=request.user, form_obj=form_obj)
    return render(
        request,
        "print_forms/detail.html",
        {
            "print_form": form_obj,
            "can_edit": can_edit_form(request.user, form_obj),
            "can_delete": can_delete_form(request.user, form_obj),
            "can_send": bool(send_form),
            "send_form": send_form,
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

    form = SendPrintFormForm(request.POST, sender=request.user, form_obj=form_obj)
    if not form.is_valid():
        for err in form.errors.values():
            for msg in err:
                messages.error(request, msg)
        return redirect("print_form_detail", pk=form_obj.pk)

    recipient = form.cleaned_data["recipient"]
    copy = PrintForm.objects.create(
        owner=recipient,
        title=form.cleaned_data["title"],
        number=form.cleaned_data["number"],
        frames=list(form_obj.frames or []),
        page_width_mm=form_obj.page_width_mm,
        page_height_mm=form_obj.page_height_mm,
        is_standard=False,
        created_by=request.user,
        source_form=form_obj,
        sent_at=_parse_jdatetime(form.cleaned_data.get("sent_at", "")),
    )
    messages.success(request, f"فرم برای «{recipient.username}» ارسال شد.")
    return redirect("print_form_detail", pk=copy.pk)
