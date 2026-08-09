from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import get_profile

import json

from .forms import (
    FittingProductionForm,
    PipeProductionForm,
    StoppageFormSetFitting,
    StoppageFormSetPipe,
    pipe_field_map,
)
from .models import FittingProduction, PipeProduction


@login_required
def production_list(request):
    profile = get_profile(request.user)
    fittings = FittingProduction.objects.select_related(
        "unit", "machine", "product", "created_by"
    )[:50]
    pipes = PipeProduction.objects.select_related("unit", "line", "product", "created_by")[:50]
    # Annotate edit permission for the template.
    for rec in list(fittings) + list(pipes):
        rec.can_edit = bool(profile and profile.can_edit_record(rec))
    return render(
        request,
        "production/list.html",
        {"fittings": fittings, "pipes": pipes, "profile": profile},
    )


def _require_data_entry(request):
    profile = get_profile(request.user)
    if not profile or not profile.can_enter_data:
        raise PermissionDenied("شما اجازه ثبت داده ندارید.")
    return profile


def _handle_form(request, form_class, formset_class, instance=None, title=""):
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        formset = formset_class(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.created_by_id is None:
                obj.created_by = request.user
            obj.save()
            formset.instance = obj
            if formset.is_valid():
                formset.save()
            messages.success(request, "اطلاعات با موفقیت ثبت شد.")
            return None  # signal success
        return form, formset
    form = form_class(instance=instance)
    formset = formset_class(instance=instance)
    return form, formset


@login_required
def fitting_create(request):
    _require_data_entry(request)
    result = _handle_form(request, FittingProductionForm, StoppageFormSetFitting)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/fitting_form.html",
                  {"form": form, "formset": formset, "mode": "create"})


@login_required
def pipe_create(request):
    _require_data_entry(request)
    result = _handle_form(request, PipeProductionForm, StoppageFormSetPipe)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/pipe_form.html",
                  {"form": form, "formset": formset, "mode": "create",
                   "pipe_field_map": json.dumps(pipe_field_map())})


def _require_edit(request, record):
    profile = get_profile(request.user)
    if not profile or not profile.can_edit_record(record):
        raise PermissionDenied("فقط مدیر یا ثبت‌کنندهٔ همین رکورد می‌تواند ویرایش کند.")
    return profile


@login_required
def fitting_edit(request, pk):
    rec = get_object_or_404(FittingProduction, pk=pk)
    _require_edit(request, rec)
    result = _handle_form(request, FittingProductionForm, StoppageFormSetFitting, instance=rec)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/fitting_form.html",
                  {"form": form, "formset": formset, "mode": "edit"})


@login_required
def pipe_edit(request, pk):
    rec = get_object_or_404(PipeProduction, pk=pk)
    _require_edit(request, rec)
    result = _handle_form(request, PipeProductionForm, StoppageFormSetPipe, instance=rec)
    if result is None:
        return redirect("production_list")
    form, formset = result
    return render(request, "production/pipe_form.html",
                  {"form": form, "formset": formset, "mode": "edit",
                   "pipe_field_map": json.dumps(pipe_field_map())})
