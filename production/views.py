import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import get_profile

from .forms import (
    DayEntryForm,
    PipeProductionForm,
    ProgramStartForm,
    ProgramStatusForm,
    StoppageFormSetPipe,
    pipe_field_map,
)
from .models import PipeProduction, ProductionDayEntry, ProductionProgram


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(request):
    return get_profile(request.user)


def _require_data_entry(request):
    profile = _profile(request)
    if not profile or not profile.can_enter_data:
        raise PermissionDenied("شما اجازه ثبت داده ندارید.")
    return profile


def program_totals(program):
    agg = program.entries.aggregate(
        produced=Sum("produced_quantity"),
        planned=Sum("planned_quantity"),
        seconds=Sum("active_seconds"),
    )
    produced = agg["produced"] or 0
    planned = agg["planned"] or 0
    seconds = agg["seconds"] or 0
    return {
        "produced": produced,
        "planned": planned,
        "deviation": planned - produced,
        "hours": round(seconds / 3600, 1),
    }


# ---------------------------------------------------------------------------
# ثبت تولید روزانه (plan-driven for fittings) + pipes
# ---------------------------------------------------------------------------

@login_required
def production_list(request):
    # Daily production is merged into the برنامه‌های تولید hub.
    return redirect("program_list")


@login_required
def entry_create(request, program_pk):
    _require_data_entry(request)
    program = get_object_or_404(
        ProductionProgram.objects.select_related("item__product", "item__machine__unit"),
        pk=program_pk,
    )
    if program.status == ProductionProgram.Status.TEMP_STOP:
        messages.error(request, "برنامه در حالت «توقف موقت» است؛ برای ثبت آمار ابتدا آن را از سر بگیرید.")
        return redirect("production_list")
    if program.status != ProductionProgram.Status.RUNNING:
        messages.error(request, "این برنامه در حال تولید نیست.")
        return redirect("production_list")

    if request.method == "POST":
        form = DayEntryForm(request.POST, program=program)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.program = program
            entry.created_by = request.user
            entry.save()
            messages.success(request, "آمار تولید ثبت شد.")
            return redirect("entry_create", program_pk=program.pk)
    else:
        form = DayEntryForm(program=program)

    return render(request, "production/entry_form.html", {
        "form": form, "program": program, "totals": program_totals(program),
        "entries": program.entries.select_related("deviation_reason").all(),
        "mode": "create",
    })


@login_required
def entry_edit(request, pk):
    entry = get_object_or_404(ProductionDayEntry.objects.select_related("program__item"), pk=pk)
    profile = _profile(request)
    if not profile or not (profile.is_manager or entry.created_by_id == request.user.id or profile.can_edit_others):
        raise PermissionDenied("فقط مدیر یا ثبت‌کننده می‌تواند ویرایش کند.")
    program = entry.program
    if request.method == "POST":
        form = DayEntryForm(request.POST, instance=entry, program=program)
        if form.is_valid():
            form.save()
            messages.success(request, "آمار ویرایش شد.")
            return redirect("entry_create", program_pk=program.pk)
    else:
        form = DayEntryForm(instance=entry, program=program)
    return render(request, "production/entry_form.html", {
        "form": form, "program": program, "totals": program_totals(program),
        "entries": program.entries.select_related("deviation_reason").all(),
        "mode": "edit",
    })


# ---------------------------------------------------------------------------
# برنامه‌های تولید + تعیین وضعیت (state machine)
# ---------------------------------------------------------------------------

@login_required
def program_list(request):
    """Hub with two tabs: دستگاه تزریق (fitting programs) and خط لوله (pipes)."""
    profile = _profile(request)
    programs = (
        ProductionProgram.objects.select_related(
            "item__product", "item__machine__unit", "item__plan"
        )
        .order_by("-item__plan__date", "item__machine__unit__number",
                  "item__machine__number", "item__sequence")
    )
    rows = [{"program": p, "totals": program_totals(p)} for p in programs]

    pipes = PipeProduction.objects.select_related("unit", "line", "product", "created_by")[:50]
    for rec in pipes:
        rec.can_edit = bool(profile and profile.can_edit_record(rec))

    active_tab = request.GET.get("tab", "injection")
    from reports.form_purposes import PURPOSE_PRODUCTION, forms_for_purpose
    import json as _json
    forms_production = [
        {"id": f.pk, "number": f.number, "title": f.title}
        for f in forms_for_purpose(request.user, PURPOSE_PRODUCTION)
    ]
    return render(request, "production/hub.html",
                  {
                      "rows": rows,
                      "pipes": pipes,
                      "profile": profile,
                      "active_tab": active_tab,
                      "forms_production": forms_production,
                      "forms_production_json": _json.dumps(forms_production, ensure_ascii=False),
                  })


ACTIVE_STATUSES = [ProductionProgram.Status.RUNNING, ProductionProgram.Status.TEMP_STOP]


def machine_running_conflict(program):
    """Another program currently RUNNING on the same machine (only one mold at a time)."""
    return (
        ProductionProgram.objects.filter(
            item__machine=program.item.machine, status=ProductionProgram.Status.RUNNING
        )
        .exclude(pk=program.pk)
        .select_related("item__product")
        .first()
    )


def product_mold_conflict(program, mold):
    """Another active program for the same product with the same mold.

    A product may run on two machines at once only with *different* molds.
    """
    qs = (
        ProductionProgram.objects.filter(
            item__product=program.item.product, status__in=ACTIVE_STATUSES
        )
        .exclude(pk=program.pk)
        .select_related("item__machine__unit")
    )
    for other in qs:
        if other.mold_id == (mold.id if mold else None):
            return other
    return None


@login_required
def program_status(request, pk):
    program = get_object_or_404(
        ProductionProgram.objects.select_related("item__product", "item__machine__unit"), pk=pk
    )
    profile = _profile(request)
    if not profile or not profile.can_enter_data:
        raise PermissionDenied("اجازه تعیین وضعیت ندارید.")

    action = request.POST.get("action") or request.GET.get("action") or "auto"
    status = program.status
    partial = request.GET.get("partial") == "1"
    base_template = "production/_status_dialog.html" if partial else "production/program_status.html"

    # Manager-only re-open of a finished program (ignores the last status).
    if action == "reopen":
        if not profile.is_manager:
            raise PermissionDenied("فقط مدیر می‌تواند برنامهٔ خاتمه‌یافته را باز کند.")
        if request.method == "POST":
            program.status = ProductionProgram.Status.RUNNING
            program.stop_date = None
            program.stop_time = None
            program.save()
            messages.info(request, "برنامه مجدداً باز شد؛ آخرین وضعیت نادیده گرفته شد.")
            return redirect("program_list")

    if status == ProductionProgram.Status.AWAITING:
        if request.method == "POST":
            form = ProgramStartForm(request.POST, program=program)
            if form.is_valid():
                cd = form.cleaned_data
                production_type = int(cd["production_type"])
                lines = list(program.item.lines.all())
                line_idx = production_type - 1
                line = lines[line_idx] if 0 <= line_idx < len(lines) else None
                mold = line.mold if line else None
                machine_conflict = machine_running_conflict(program)
                if machine_conflict:
                    messages.error(
                        request,
                        f"روی «{program.machine_label}» قالب «{machine_conflict.item.product.name}» "
                        f"در حال تولید است؛ تا زمان تعیین وضعیت (اتمام آمار) آن، راه‌اندازی قالب جدید ممکن نیست.",
                    )
                    return redirect("program_status", pk=pk)
                prod_conflict = product_mold_conflict(program, mold)
                if prod_conflict:
                    messages.error(
                        request,
                        f"محصول «{program.item.product.name}» هم‌اکنون روی «{prod_conflict.machine_label}» "
                        f"با همین قالب فعال است؛ برای تولید هم‌زمان، باید قالب متفاوتی در برنامه‌ریزی انتخاب کنید.",
                    )
                    return redirect("program_status", pk=pk)
                program.change_type = cd["change_type"]
                program.change_reason = cd.get("change_reason")
                program.production_type = production_type
                program.mold = mold
                program.start_date = cd["start_date"]
                program.start_time = cd["start_time"]
                program.status = ProductionProgram.Status.RUNNING
                program.save()
                messages.success(request, "برنامه راه‌اندازی شد و تولید آغاز شد.")
                return redirect("program_list")
        else:
            import datetime
            import jdatetime
            form = ProgramStartForm(program=program, initial={
                "start_date": jdatetime.date.today(),
                "start_time": datetime.datetime.now().strftime("%H:%M"),
                "change_type": "setup",
                "production_type": "1",
            })
        return render(request, base_template,
                      {"program": program, "form": form, "phase": "start"})

    # RUNNING or TEMP_STOP -> status dropdown (ادامه / توقف موقت / اتمام تولید)
    if status in (ProductionProgram.Status.RUNNING, ProductionProgram.Status.TEMP_STOP):
        if request.method == "POST":
            form = ProgramStatusForm(request.POST, current=status)
            if form.is_valid():
                new_status = form.cleaned_data["new_status"]
                if new_status == ProductionProgram.Status.RUNNING:
                    conflict = machine_running_conflict(program)
                    if conflict and status == ProductionProgram.Status.TEMP_STOP:
                        messages.error(
                            request,
                            f"روی «{program.machine_label}» قالب دیگری در حال تولید است؛ ازسرگیری ممکن نیست.",
                        )
                        return redirect("program_status", pk=pk)
                    program.status = ProductionProgram.Status.RUNNING
                    program.stop_date = None
                    program.stop_time = None
                else:
                    program.stop_date = form.cleaned_data["stop_date"]
                    program.stop_time = form.cleaned_data["stop_time"]
                    program.status = new_status
                program.save()
                for e in program.entries.all():  # stop time affects day windows
                    e.save()
                messages.success(request, "وضعیت به‌روزرسانی شد.")
                return redirect("program_list")
        else:
            import datetime
            import jdatetime
            form = ProgramStatusForm(current=status, initial={
                "stop_date": jdatetime.date.today(),
                "stop_time": datetime.datetime.now().strftime("%H:%M"),
            })
        return render(request, base_template,
                      {"program": program, "form": form, "phase": "status"})

    # FINISHED
    return render(request, base_template,
                  {"program": program, "form": None, "phase": "finished"})


# ---------------------------------------------------------------------------
# Pipe production (unchanged free entry; pipes have no weekly plan)
# ---------------------------------------------------------------------------

def _handle_pipe(request, instance=None):
    if request.method == "POST":
        form = PipeProductionForm(request.POST, instance=instance)
        formset = StoppageFormSetPipe(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.created_by_id is None:
                obj.created_by = request.user
            obj.save()
            formset.instance = obj
            if formset.is_valid():
                formset.save()
            messages.success(request, "اطلاعات با موفقیت ثبت شد.")
            return None
        return form, formset
    return PipeProductionForm(instance=instance), StoppageFormSetPipe(instance=instance)


@login_required
def pipe_create(request):
    _require_data_entry(request)
    result = _handle_pipe(request)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/pipe_form.html",
                  {"form": form, "formset": formset, "mode": "create",
                   "pipe_field_map": json.dumps(pipe_field_map())})


@login_required
def pipe_edit(request, pk):
    rec = get_object_or_404(PipeProduction, pk=pk)
    profile = _profile(request)
    if not profile or not profile.can_edit_record(rec):
        raise PermissionDenied("فقط مدیر یا ثبت‌کننده می‌تواند ویرایش کند.")
    result = _handle_pipe(request, instance=rec)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/pipe_form.html",
                  {"form": form, "formset": formset, "mode": "edit",
                   "pipe_field_map": json.dumps(pipe_field_map())})
