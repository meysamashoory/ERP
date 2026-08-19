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
from .utils import format_jdate, mold_change_date_candidates
from catalog.models import Product


@login_required
def plan_list(request):
    from reports.form_purposes import PURPOSE_WEEKLY, forms_for_purpose
    profile = get_profile(request.user)
    plans = list(WeeklyPlan.objects.select_related("created_by", "approved_by").all())
    for plan in plans:
        plan.can_edit_by_user = _can_request_edit(request.user, profile, plan)
    forms_weekly = [
        {"id": f.pk, "number": f.number, "title": f.title}
        for f in forms_for_purpose(request.user, PURPOSE_WEEKLY)
    ]
    return render(
        request,
        "planning/plan_list.html",
        {
            "plans": plans,
            "profile": profile,
            "forms_weekly": forms_weekly,
            "forms_weekly_json": __import__("json").dumps(forms_weekly, ensure_ascii=False),
        },
    )


@login_required
def plan_calendar_json(request):
    """Read-only mold-change matrix for the plan-list calendar dialog."""
    plan = get_object_or_404(WeeklyPlan, pk=request.GET.get("plan"))
    stats = mold_change_stats(plan)
    return JsonResponse({
        "matrix_units": stats["matrix_units"],
        "matrix_rows": stats["matrix_rows"],
        "glass_rows": stats["glass_rows"],
    })


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


def _is_plan_owner(user, plan) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(plan.created_by_id and plan.created_by_id == user.id)


def _can_edit_plan(user, profile, plan) -> bool:
    """Creator with create-permission may edit their own draft plan."""
    return bool(
        profile
        and profile.can_create_plans
        and _is_plan_owner(user, plan)
        and plan.status == WeeklyPlan.Status.DRAFT
    )


def _can_request_edit(user, profile, plan) -> bool:
    """Creator may choose ویرایش (approved plans are reopened to draft)."""
    return bool(profile and profile.can_create_plans and _is_plan_owner(user, plan))


@login_required
def plan_operate(request, pk):
    """List operations: مشاهده (default) or ویرایش (owner only)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    action = (request.POST.get("action") or "view").strip()
    if request.method != "POST":
        return redirect("plan_detail", pk=pk)
    if action == "edit":
        if not _can_request_edit(request.user, profile, plan):
            raise PermissionDenied("فقط ایجادکنندهٔ برنامه می‌تواند آن را ویرایش کند.")
        if plan.status != WeeklyPlan.Status.DRAFT:
            plan.status = WeeklyPlan.Status.DRAFT
            plan.approved_by = None
            plan.approved_at = None
            plan.save(update_fields=["status", "approved_by", "approved_at"])
            messages.info(request, "برنامه برای ویرایش باز شد.")
        return redirect("plan_detail", pk=pk)
    return redirect("plan_detail", pk=pk)


@login_required
def plan_edit(request, pk):
    """Inline edit of a plan's program number and date."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_edit_plan(request.user, profile, plan):
        raise PermissionDenied("اجازه ویرایش برنامه ندارید.")
    if request.method == "POST":
        form = WeeklyPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "شماره و تاریخ برنامه به‌روزرسانی شد.")
        else:
            messages.error(request, "مقادیر واردشده معتبر نیست.")
    return redirect("plan_detail", pk=pk)


def _alarm_items_for_plan(plan):
    return [
        {
            "id": it.pk,
            "uid": it.uid,
            "code": it.product.code,
            "name": it.product.name,
            "machine": f"{it.machine.number}/{it.unit.number}",
        }
        for it in plan.items.select_related("product", "machine", "unit").all()
        if it.history_alarm
    ]


@login_required
def plan_detail(request, pk):
    plan = get_object_or_404(
        WeeklyPlan.objects.prefetch_related(
            "items__lines__mold",
            "items__lines__production_type",
            "items__product",
            "items__unit",
            "items__machine",
            "items__subgroup__group",
        ),
        pk=pk,
    )
    profile = get_profile(request.user)
    editable = _can_edit_plan(request.user, profile, plan)

    editing_item = None
    edit_id = request.GET.get("edit")
    if editable and edit_id:
        editing_item = plan.items.filter(pk=edit_id).first()

    item_form = WeeklyPlanItemForm(plan_date=plan.date, instance=editing_item)
    line_formset = WeeklyPlanLineFormSet(instance=editing_item, prefix="lines")
    edit_form = WeeklyPlanForm(instance=plan)
    mold_stats = mold_change_stats(plan)
    insight_product = editing_item.product if editing_item else None
    insights = resolve_insights(insight_product) if editable else []
    alarm_items = _alarm_items_for_plan(plan)

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
            "insights": insights,
            "alarm_items": alarm_items,
        },
    )


@login_required
def item_save(request, pk):
    """Create a new کالا, or update an existing one (with its production rows)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_edit_plan(request.user, profile, plan):
        raise PermissionDenied("فقط ایجادکنندهٔ برنامه می‌تواند آن را ویرایش کند.")
    if request.method != "POST":
        return redirect("plan_detail", pk=pk)

    item_id = request.POST.get("item_id") or None
    instance = plan.items.filter(pk=item_id).first() if item_id else None

    form = WeeklyPlanItemForm(request.POST, plan_date=plan.date, instance=instance)
    formset = WeeklyPlanLineFormSet(request.POST, instance=instance, prefix="lines")
    if form.is_valid() and formset.is_valid():
        item = form.save(commit=False)
        item.plan = plan
        has_history = FittingProduction.objects.filter(machine=item.machine).exists()
        item.history_alarm = not has_history
        if instance is None:
            item.sequence = plan.items.filter(machine=item.machine).count() + 1
        item.save()

        # Bind formset to saved item (new items need pk for inline saves).
        formset = WeeklyPlanLineFormSet(request.POST, instance=item, prefix="lines")
        if not formset.is_valid():
            messages.error(request, "خطا در ردیف‌های تولید. مقادیر را بررسی کنید.")
            return render(
                request,
                "planning/plan_detail.html",
                {
                    "plan": plan,
                    "profile": profile,
                    "editable": True,
                    "item_form": form,
                    "line_formset": formset,
                    "editing_item": item,
                    "edit_form": WeeklyPlanForm(instance=plan),
                    "mold_stats": mold_change_stats(plan),
                    "insights": resolve_insights(item.product),
                    "alarm_items": _alarm_items_for_plan(plan),
                },
            )

        saved_lines = []
        for line_form in formset.forms:
            cd = line_form.cleaned_data
            if not cd or not cd.get("production_type"):
                continue
            line = line_form.save(commit=False)
            line.item = item
            line.mold = item.mold
            if not line.active_cavities:
                line.active_cavities = 1
            line.save()
            saved_lines.append(line)

        # Drop leftover DB lines that were cleared / removed from the formset.
        keep_ids = {ln.pk for ln in saved_lines}
        item.lines.exclude(pk__in=keep_ids).delete()

        if saved_lines:
            item.active_cavities = saved_lines[0].active_cavities or 1
            item.save(update_fields=["active_cavities"])
        else:
            messages.error(request, "حداقل یک ردیف تولید کامل (نوع، حفره، مقدار، سیکل) لازم است.")
            return render(
                request,
                "planning/plan_detail.html",
                {
                    "plan": plan,
                    "profile": profile,
                    "editable": True,
                    "item_form": form,
                    "line_formset": WeeklyPlanLineFormSet(instance=item, prefix="lines"),
                    "editing_item": item,
                    "edit_form": WeeklyPlanForm(instance=plan),
                    "mold_stats": mold_change_stats(plan),
                    "insights": resolve_insights(item.product),
                    "alarm_items": _alarm_items_for_plan(plan),
                },
            )

        from .uid import refresh_plan_uids
        collisions = refresh_plan_uids(plan)
        item.refresh_from_db(fields=["uid"])
        if item.history_alarm:
            messages.warning(
                request,
                f"دستگاه {item.machine} در سوابق تولید ثبت نشده است. "
                "پیشنهاد: پس از اولین ثبت تولید، این هشدار برطرف می‌شود.",
            )
        if collisions:
            first = collisions[0]
            messages.error(
                request,
                f"شناسه تکراری: {first['uid']}. {first.get('suggestion') or 'جزئیات در مدیریت داده‌ها ثبت شد.'}",
            )
        else:
            messages.success(request, "کالا ذخیره شد." if instance else "کالا اضافه شد.")
        return redirect("plan_detail", pk=pk)

    messages.error(request, "خطا در ثبت کالا. مقادیر را بررسی کنید.")
    return render(
        request,
        "planning/plan_detail.html",
        {
            "plan": plan,
            "profile": profile,
            "editable": True,
            "item_form": form,
            "line_formset": formset,
            "editing_item": instance,
            "edit_form": WeeklyPlanForm(instance=plan),
            "mold_stats": mold_change_stats(plan),
            "insights": resolve_insights(
                form.cleaned_data.get("product")
                if getattr(form, "cleaned_data", None)
                else (instance.product if instance else None)
            ),
            "alarm_items": _alarm_items_for_plan(plan),
        },
    )


@login_required
def product_insights(request):
    """JSON: glass-panel metrics for the selected product."""
    from .insights import resolve_insight_details

    product_id = request.GET.get("product")
    product = Product.objects.filter(pk=product_id).first() if product_id else None
    details = request.GET.get("details") == "1"
    if details:
        return JsonResponse({"sections": resolve_insight_details(product)})
    return JsonResponse({"insights": resolve_insights(product)})


@login_required
def plan_set_status(request, pk):
    """ذخیره = تأیید نهایی برنامه (فقط ایجادکننده)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_request_edit(request.user, profile, plan):
        raise PermissionDenied("فقط ایجادکنندهٔ برنامه می‌تواند آن را ذخیره کند.")
    if request.method != "POST":
        return redirect("plan_list")
    target = request.POST.get("status")
    if target == WeeklyPlan.Status.APPROVED:
        plan.status = WeeklyPlan.Status.APPROVED
        plan.approved_by = request.user
        plan.approved_at = timezone.now()
        from production.models import ProductionProgram
        for item in plan.items.all():
            ProductionProgram.objects.get_or_create(item=item)
        messages.success(request, f"برنامه ذخیره و تأیید شد.")
    else:
        plan.status = WeeklyPlan.Status.DRAFT
        plan.approved_by = None
        plan.approved_at = None
        messages.info(request, f"برنامه برای ویرایش باز شد.")
    plan.save()
    return redirect(request.POST.get("next") or "plan_list")


@login_required
def weekday_for_date(request):
    """JSON: Persian weekday name for a Jalali YYYY/MM/DD date."""
    from .models import persian_weekday
    from .utils import parse_jdate_string

    raw = request.GET.get("date") or ""
    try:
        d = parse_jdate_string(raw)
    except (TypeError, ValueError):
        return JsonResponse({"weekday": ""})
    return JsonResponse({"weekday": persian_weekday(d), "date": format_jdate(d)})


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
    return JsonResponse({"dates": [format_jdate(c) for c in candidates]})
