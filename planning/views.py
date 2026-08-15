from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permissions import get_profile
from production.models import FittingProduction

from .forms import WeeklyPlanForm, WeeklyPlanItemForm, WeeklyPlanLineFormSet
from .insights import resolve_insights
from .models import WeeklyPlan, WeeklyPlanItem
from .mold_stats import mold_change_stats
from .utils import mold_change_date_candidates
from catalog.models import Product


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
            plan.status = WeeklyPlan.Status.DRAFT
            plan.save()
            messages.success(request, "برنامه ایجاد شد. اکنون کالاها را اضافه کنید.")
            return redirect("plan_detail", pk=plan.pk)
    else:
        form = WeeklyPlanForm()
    return render(request, "planning/plan_form.html", {"form": form})


def _can_edit_plan(profile, plan):
    return bool(profile and profile.can_create_plans and plan.status == WeeklyPlan.Status.DRAFT)


@login_required
def plan_edit(request, pk):
    """Inline edit of a plan's program number and date."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not profile or not profile.can_create_plans:
        raise PermissionDenied("اجازه ویرایش برنامه ندارید.")
    if request.method == "POST":
        form = WeeklyPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "شماره و تاریخ برنامه به‌روزرسانی شد.")
        else:
            messages.error(request, "مقادیر واردشده معتبر نیست.")
    return redirect("plan_detail", pk=pk)


@login_required
def plan_detail(request, pk):
    plan = get_object_or_404(
        WeeklyPlan.objects.prefetch_related(
            "items__lines",
            "items__product",
            "items__unit",
            "items__subgroup__group",
        ),
        pk=pk,
    )
    profile = get_profile(request.user)
    editable = _can_edit_plan(profile, plan)

    editing_item = None
    edit_id = request.GET.get("edit")
    if editable and edit_id:
        editing_item = plan.items.filter(pk=edit_id).first()

    item_form = WeeklyPlanItemForm(plan_date=plan.date, instance=editing_item)
    line_formset = WeeklyPlanLineFormSet(instance=editing_item, prefix="lines")
    edit_form = WeeklyPlanForm(instance=plan)
    mold_stats = mold_change_stats(plan)

    return render(
        request,
        "planning/plan_detail.html",
        {
            "plan": plan,
            "profile": profile,
            "editable": editable,
            "item_form": item_form,
            "line_formset": line_formset,
            "editing_item": editing_item,
            "edit_form": edit_form,
            "mold_stats": mold_stats,
        },
    )


@login_required
def item_save(request, pk):
    """Create a new کالا, or update an existing one (with its production rows)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_edit_plan(profile, plan):
        raise PermissionDenied("برنامه در حالت «در انتظار تأیید» نیست یا اجازه ویرایش ندارید.")
    if request.method != "POST":
        return redirect("plan_detail", pk=pk)

    item_id = request.POST.get("item_id") or None
    instance = plan.items.filter(pk=item_id).first() if item_id else None

    form = WeeklyPlanItemForm(request.POST, plan_date=plan.date, instance=instance)
    if form.is_valid():
        item = form.save(commit=False)
        item.plan = plan
        has_history = FittingProduction.objects.filter(machine=item.machine).exists()
        item.history_alarm = not has_history
        if instance is None:
            # Sequence position among items on the same machine in this plan.
            item.sequence = plan.items.filter(machine=item.machine).count() + 1
        item.save()
        formset = WeeklyPlanLineFormSet(request.POST, instance=item, prefix="lines")
        if formset.is_valid():
            formset.save()
        # Transient warning only (not stored permanently).
        if item.history_alarm:
            messages.warning(request, f"دستگاه {item.machine} در سوابق تولید ثبت نشده است.")
        messages.success(request, "کالا ذخیره شد." if instance else "کالا اضافه شد.")
        return redirect("plan_detail", pk=pk)

    messages.error(request, "خطا در ثبت کالا. مقادیر را بررسی کنید.")
    line_formset = WeeklyPlanLineFormSet(request.POST, instance=instance, prefix="lines")
    return render(
        request,
        "planning/plan_detail.html",
        {
            "plan": plan,
            "profile": profile,
            "editable": True,
            "item_form": form,
            "line_formset": line_formset,
            "editing_item": instance,
            "edit_form": WeeklyPlanForm(instance=plan),
            "mold_stats": mold_change_stats(plan),
        },
    )


@login_required
def product_insights(request):
    """JSON: glass-panel metrics for the selected product."""
    product_id = request.GET.get("product")
    product = Product.objects.filter(pk=product_id).first() if product_id else None
    return JsonResponse({"insights": resolve_insights(product)})


@login_required
def plan_set_status(request, pk):
    """Toggle a plan between «در انتظار تأیید» (draft) and «تأییدشده» (approved)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not profile or not profile.can_create_plans:
        raise PermissionDenied("اجازه تعیین وضعیت ندارید.")
    if request.method != "POST":
        return redirect("plan_list")
    target = request.POST.get("status")
    if target == WeeklyPlan.Status.APPROVED:
        plan.status = WeeklyPlan.Status.APPROVED
        plan.approved_by = request.user
        plan.approved_at = timezone.now()
        # Create an execution program (وضعیت: در انتظار تولید) for each کالا.
        from production.models import ProductionProgram
        for item in plan.items.all():
            ProductionProgram.objects.get_or_create(item=item)
        messages.success(request, f"برنامه {plan.program_number} تأیید شد.")
    else:
        plan.status = WeeklyPlan.Status.DRAFT
        plan.approved_by = None
        plan.approved_at = None
        messages.info(request, f"برنامه {plan.program_number} به حالت «در انتظار تأیید» درآمد.")
    plan.save()
    return redirect(request.POST.get("next") or "plan_list")


@login_required
def mold_change_dates(request):
    """JSON endpoint powering the dynamic تاریخ تعویض قالب dropdown."""
    plan_id = request.GET.get("plan")
    weekday = request.GET.get("weekday")
    plan = get_object_or_404(WeeklyPlan, pk=plan_id)
    try:
        weekday_int = int(weekday)
    except (TypeError, ValueError):
        return JsonResponse({"dates": []})
    candidates = mold_change_date_candidates(plan.date, weekday_int)
    return JsonResponse({"dates": [c.strftime("%Y-%m-%d") for c in candidates]})
