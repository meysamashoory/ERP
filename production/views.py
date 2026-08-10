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
    ProgramStopForm,
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
    profile = _profile(request)
    active = (
        ProductionProgram.objects.filter(
            status__in=[ProductionProgram.Status.RUNNING, ProductionProgram.Status.TEMP_STOP]
        )
        .select_related("item__product", "item__machine__unit")
        .order_by("item__machine__unit__number", "item__machine__number", "item__sequence")
    )
    programs = []
    for p in active:
        programs.append({"program": p, "totals": program_totals(p)})

    pipes = PipeProduction.objects.select_related("unit", "line", "product", "created_by")[:50]
    for rec in pipes:
        rec.can_edit = bool(profile and profile.can_edit_record(rec))

    return render(request, "production/list.html",
                  {"programs": programs, "pipes": pipes, "profile": profile})


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
    profile = _profile(request)
    programs = (
        ProductionProgram.objects.select_related(
            "item__product", "item__machine__unit", "item__plan"
        )
        .order_by("-item__plan__date", "item__machine__unit__number", "item__machine__number", "item__sequence")
    )
    rows = [{"program": p, "totals": program_totals(p)} for p in programs]
    return render(request, "production/program_list.html", {"rows": rows, "profile": profile})


def _earlier_incomplete_on_machine(program):
    """Return an earlier-sequence program on the same machine that isn't finished."""
    item = program.item
    earlier_items = item.plan.items.filter(
        machine=item.machine, sequence__lt=item.sequence
    )
    return ProductionProgram.objects.filter(
        item__in=earlier_items
    ).exclude(status=ProductionProgram.Status.FINISHED).select_related("item").first()


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
                blocker = _earlier_incomplete_on_machine(program)
                if blocker:
                    messages.error(
                        request,
                        f"ابتدا باید تولید «{blocker.item.product.name}» روی همین دستگاه به «اتمام تولید» برسد.",
                    )
                    return redirect("program_status", pk=pk)
                cd = form.cleaned_data
                program.change_type = cd["change_type"]
                program.change_reason = cd.get("change_reason")
                program.production_type = int(cd["production_type"])
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
        return render(request, "production/program_status.html",
                      {"program": program, "form": form, "phase": "start"})

    # RUNNING or TEMP_STOP -> can توقف موقت / اتمام تولید (and resume)
    if status in (ProductionProgram.Status.RUNNING, ProductionProgram.Status.TEMP_STOP):
        if action == "resume" and status == ProductionProgram.Status.TEMP_STOP and request.method == "POST":
            program.status = ProductionProgram.Status.RUNNING
            program.stop_date = None
            program.stop_time = None
            program.save()
            messages.success(request, "تولید از سر گرفته شد.")
            return redirect("program_list")

        if request.method == "POST" and action in ("temp_stop", "finish"):
            form = ProgramStopForm(request.POST)
            if form.is_valid():
                program.stop_date = form.cleaned_data["stop_date"]
                program.stop_time = form.cleaned_data["stop_time"]
                program.status = (
                    ProductionProgram.Status.TEMP_STOP if action == "temp_stop"
                    else ProductionProgram.Status.FINISHED
                )
                program.save()
                # Recompute entries (stop time affects the day windows).
                for e in program.entries.all():
                    e.save()
                messages.success(request, "وضعیت به‌روزرسانی شد.")
                return redirect("program_list")
        else:
            import datetime
            import jdatetime
            form = ProgramStopForm(initial={
                "stop_date": jdatetime.date.today(),
                "stop_time": datetime.datetime.now().strftime("%H:%M"),
            })
        return render(request, "production/program_status.html",
                      {"program": program, "form": form, "phase": "stop"})

    # FINISHED
    return render(request, "production/program_status.html",
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
