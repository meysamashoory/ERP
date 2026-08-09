from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permissions import get_profile
from production.models import FittingProduction

from .forms import WeeklyPlanForm, WeeklyPlanItemForm, WeeklyPlanLineFormSet
from .models import WeeklyPlan, WeeklyPlanItem
from .utils import mold_change_date_candidates


@login_required
def plan_list(request):
    plans = WeeklyPlan.objects.select_related("created_by", "approved_by").all()
    return render(
        request,
        "planning/plan_list.html",
        {"plans": plans, "profile": get_profile(request.user)},
    )


@login_required
def plan_create(request):
    profile = get_profile(request.user)
    if not profile or not profile.can_create_plans:
        raise PermissionDenied("شما اجازه ایجاد برنامه ندارید.")
    if request.method == "POST":
        form = WeeklyPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.created_by = request.user
            plan.save()
            messages.success(request, "برنامه ایجاد شد. اکنون اقلام را اضافه کنید.")
            return redirect("plan_detail", pk=plan.pk)
    else:
        form = WeeklyPlanForm()
    return render(request, "planning/plan_form.html", {"form": form})


@login_required
def plan_detail(request, pk):
    plan = get_object_or_404(
        WeeklyPlan.objects.prefetch_related("items__lines", "items__product"), pk=pk
    )
    profile = get_profile(request.user)
    item_form = WeeklyPlanItemForm(plan_date=plan.date)
    line_formset = WeeklyPlanLineFormSet()
    return render(
        request,
        "planning/plan_detail.html",
        {
            "plan": plan,
            "profile": profile,
            "item_form": item_form,
            "line_formset": line_formset,
        },
    )


@login_required
def item_add(request, pk):
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not profile or not profile.can_create_plans:
        raise PermissionDenied("شما اجازه ویرایش برنامه ندارید.")
    if request.method != "POST":
        return redirect("plan_detail", pk=pk)

    form = WeeklyPlanItemForm(request.POST, plan_date=plan.date)
    if form.is_valid():
        item = form.save(commit=False)
        item.plan = plan
        # Machine-history alarm (does not block saving).
        has_history = FittingProduction.objects.filter(machine=item.machine).exists()
        item.history_alarm = not has_history
        item.save()
        formset = WeeklyPlanLineFormSet(request.POST, instance=item)
        if formset.is_valid():
            formset.save()
        if item.history_alarm:
            note = f"دستگاه {item.machine} در سوابق تولید ثبت نشده است."
            plan.alarms = (plan.alarms + "\n" + note).strip() if plan.alarms else note
            plan.save(update_fields=["alarms"])
            messages.warning(request, note)
        messages.success(request, "قلم برنامه اضافه شد.")
    else:
        messages.error(request, "خطا در ثبت قلم برنامه. مقادیر را بررسی کنید.")
    return redirect("plan_detail", pk=pk)


@login_required
def plan_submit(request, pk):
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not profile or not profile.can_create_plans:
        raise PermissionDenied()
    # Managers approve directly; experts submit for approval.
    if profile.can_approve_plans:
        plan.status = WeeklyPlan.Status.APPROVED
        plan.approved_by = request.user
        plan.approved_at = timezone.now()
        messages.success(request, "برنامه تأیید شد.")
    else:
        plan.status = WeeklyPlan.Status.PENDING
        messages.success(request, "برنامه برای تأیید مدیر ارسال شد.")
    plan.save()
    return redirect("plan_detail", pk=pk)


@login_required
def plan_approve(request, pk):
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not profile or not profile.can_approve_plans:
        raise PermissionDenied("فقط مدیر می‌تواند تأیید کند.")
    decision = request.POST.get("decision", "approve")
    if decision == "reject":
        plan.status = WeeklyPlan.Status.REJECTED
        messages.info(request, "برنامه رد شد.")
    else:
        plan.status = WeeklyPlan.Status.APPROVED
        plan.approved_by = request.user
        plan.approved_at = timezone.now()
        messages.success(request, "برنامه تأیید شد.")
    plan.save()
    return redirect("plan_detail", pk=pk)


@login_required
def mold_change_dates(request):
    """JSON endpoint powering the dynamic تاریخ تعویض قالب dropdown."""
    import jdatetime

    plan_id = request.GET.get("plan")
    weekday = request.GET.get("weekday")
    plan = get_object_or_404(WeeklyPlan, pk=plan_id)
    try:
        weekday_int = int(weekday)
    except (TypeError, ValueError):
        return JsonResponse({"dates": []})
    candidates = mold_change_date_candidates(plan.date, weekday_int)
    return JsonResponse({"dates": [c.strftime("%Y-%m-%d") for c in candidates]})
