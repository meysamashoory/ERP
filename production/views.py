from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import get_profile

from .forms import (
    FittingProductionForm,
    PipeProductionForm,
    StoppageFormSetFitting,
    StoppageFormSetPipe,
)
from .models import FittingProduction, PipeProduction


@login_required
def production_list(request):
    fittings = FittingProduction.objects.select_related("unit", "machine", "product")[:50]
    pipes = PipeProduction.objects.select_related("unit", "line")[:50]
    return render(
        request,
        "production/list.html",
        {"fittings": fittings, "pipes": pipes, "profile": get_profile(request.user)},
    )


def _require_data_entry(request):
    profile = get_profile(request.user)
    if not profile or not profile.can_enter_data:
        raise PermissionDenied("شما اجازه ثبت داده ندارید.")
    return profile


@login_required
def fitting_create(request):
    _require_data_entry(request)
    if request.method == "POST":
        form = FittingProductionForm(request.POST)
        formset = StoppageFormSetFitting(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            formset.instance = obj
            if formset.is_valid():
                formset.save()
            messages.success(request, "تولید اتصالات با موفقیت ثبت شد.")
            return redirect("production_list")
    else:
        form = FittingProductionForm()
        formset = StoppageFormSetFitting()
    return render(
        request,
        "production/fitting_form.html",
        {"form": form, "formset": formset},
    )


@login_required
def pipe_create(request):
    _require_data_entry(request)
    if request.method == "POST":
        form = PipeProductionForm(request.POST)
        formset = StoppageFormSetPipe(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            formset.instance = obj
            if formset.is_valid():
                formset.save()
            messages.success(request, "تولید لوله با موفقیت ثبت شد.")
            return redirect("production_list")
    else:
        form = PipeProductionForm()
        formset = StoppageFormSetPipe()
    return render(
        request,
        "production/pipe_form.html",
        {"form": form, "formset": formset},
    )
