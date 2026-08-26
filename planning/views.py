from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
    from django.db.models import Count

    from core.natsort import natural_key
    from production.sync import sync_all_history_to_planning
    from reports.form_purposes import PURPOSE_WEEKLY, forms_for_purpose

    profile = get_profile(request.user)
    # History → planning: ensure archive plan numbers appear as editable plans
    sync_all_history_to_planning(user=request.user)

    sort = (request.GET.get("sort") or "date").strip()
    direction = (request.GET.get("dir") or "desc").strip().lower()
    if sort not in {"number", "date"}:
        sort = "date"
    if direction not in {"asc", "desc"}:
        direction = "desc"

    plans = list(
        WeeklyPlan.objects.select_related("created_by", "approved_by")
        .annotate(mold_count=Count("items", distinct=True))
    )
    reverse = direction == "desc"
    if sort == "number":
        plans.sort(key=lambda p: natural_key(p.program_number), reverse=reverse)
    else:
        plans.sort(key=lambda p: (p.date, p.id), reverse=reverse)

    for plan in plans:
        plan.can_edit_by_user = _can_request_edit(request.user, profile, plan)
        plan.can_delete_by_user = _can_delete_plan(request.user, profile)
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
            "sort": sort,
            "dir": direction,
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
            return redirect(f"{reverse('plan_detail', args=[plan.pk])}?mode=edit")
    else:
        form = WeeklyPlanForm()
    return render(request, "planning/plan_form.html", {"form": form})


def _is_plan_owner(user, plan) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(plan.created_by_id and plan.created_by_id == user.id)


def _is_planning_manager(user, profile) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return bool(profile and profile.is_manager)


def _can_edit_plan(user, profile, plan) -> bool:
    """Creator or planning manager may edit a draft plan."""
    if not profile or not profile.can_create_plans:
        return False
    if plan.status != WeeklyPlan.Status.DRAFT:
        return False
    return _is_planning_manager(user, profile) or _is_plan_owner(user, plan)


def _can_request_edit(user, profile, plan) -> bool:
    """Creator or manager may choose ویرایش (approved plans reopen to draft)."""
    if not profile or not profile.can_create_plans:
        return False
    return _is_planning_manager(user, profile) or _is_plan_owner(user, plan)


def _can_delete_plan(user, profile) -> bool:
    """Only planning manager (or superuser) may delete a plan."""
    return _is_planning_manager(user, profile)


@login_required
def plan_operate(request, pk):
    """List operations: مشاهده / ویرایش / حذف برنامه."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    action = (request.POST.get("action") or "view").strip()
    if request.method != "POST":
        return redirect(f"{reverse('plan_detail', args=[pk])}?mode=view")
    if action == "delete":
        if not _can_delete_plan(request.user, profile):
            raise PermissionDenied("فقط مدیر برنامه‌ریزی می‌تواند برنامه را حذف کند.")
        plan.delete()
        messages.success(request, "برنامه حذف شد.")
        return redirect("plan_list")
    if action == "edit":
        if not _can_request_edit(request.user, profile, plan):
            raise PermissionDenied("فقط ایجادکننده یا مدیر می‌تواند برنامه را ویرایش کند.")
        if plan.status != WeeklyPlan.Status.DRAFT:
            plan.status = WeeklyPlan.Status.DRAFT
            plan.approved_by = None
            plan.approved_at = None
            plan.save(update_fields=["status", "approved_by", "approved_at"])
            messages.info(request, "برنامه برای ویرایش باز شد.")
        return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")
    return redirect(f"{reverse('plan_detail', args=[pk])}?mode=view")


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
    return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")


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


def _product_collision_in_plan(plan, *, product, mold, type_ids, exclude_item_id=None) -> bool:
    """Same product may only reappear if mold or production type differs."""
    if product is None:
        return False
    mold_id = mold.pk if mold is not None else None
    new_types = {t for t in type_ids if t}
    qs = plan.items.filter(product_id=product.pk).prefetch_related("lines")
    if exclude_item_id:
        qs = qs.exclude(pk=exclude_item_id)
    for other in qs:
        if (other.mold_id or None) != mold_id:
            continue
        other_types = {
            tid for tid in other.lines.values_list("production_type_id", flat=True) if tid
        }
        # No distinguishing type difference (both empty, or shared type).
        if not new_types and not other_types:
            return True
        if new_types & other_types:
            return True
    return False


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
    mode = (request.GET.get("mode") or "view").strip().lower()
    # مشاهده is always read-only; ویرایش requires ownership + draft.
    editable = bool(mode == "edit" and _can_edit_plan(request.user, profile, plan))
    if mode == "edit" and not editable:
        # Owner requested edit but plan isn't editable (or not owner) → fall back to view.
        return redirect(f"{reverse('plan_detail', args=[pk])}?mode=view")

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
            "view_mode": not editable,
            "item_form": item_form,
            "line_formset": line_formset,
            "editing_item": editing_item,
            "edit_form": edit_form,
            "mold_stats": mold_stats,
            "insights": insights,
            "alarm_items": alarm_items,
        },
    )


def _plan_item_form_context(request, plan, profile, *, form, formset, editing_item):
    insight_product = None
    if getattr(form, "cleaned_data", None) and form.cleaned_data.get("product"):
        insight_product = form.cleaned_data.get("product")
    elif editing_item is not None:
        insight_product = editing_item.product
    return {
        "plan": plan,
        "profile": profile,
        "editable": True,
        "view_mode": False,
        "item_form": form,
        "line_formset": formset,
        "editing_item": editing_item,
        "edit_form": WeeklyPlanForm(instance=plan),
        "mold_stats": mold_change_stats(plan),
        "insights": resolve_insights(insight_product),
        "alarm_items": _alarm_items_for_plan(plan),
    }


@login_required
def item_save(request, pk):
    """Create a new کالا, or update an existing one (with its production rows)."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_edit_plan(request.user, profile, plan):
        raise PermissionDenied("فقط ایجادکنندهٔ برنامه می‌تواند آن را ویرایش کند.")
    if request.method != "POST":
        return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")

    item_id = request.POST.get("item_id") or None
    instance = plan.items.filter(pk=item_id).first() if item_id else None

    form = WeeklyPlanItemForm(request.POST, plan_date=plan.date, instance=instance)
    formset = WeeklyPlanLineFormSet(request.POST, instance=instance, prefix="lines")

    # Validate everything BEFORE any DB write so incomplete rows never create a کالا.
    if not (form.is_valid() and formset.is_valid()):
        messages.error(request, "خطا در ثبت کالا. مقادیر را بررسی کنید.")
        return render(
            request,
            "planning/plan_detail.html",
            _plan_item_form_context(
                request, plan, profile,
                form=form, formset=formset, editing_item=instance,
            ),
        )

    filled_forms = [
        f for f in formset.forms
        if getattr(f, "cleaned_data", None) and not f.is_empty_row()
    ]
    if not filled_forms:
        messages.error(request, "خطا در ثبت کالا. مقادیر را بررسی کنید.")
        return render(
            request,
            "planning/plan_detail.html",
            _plan_item_form_context(
                request, plan, profile,
                form=form, formset=formset, editing_item=instance,
            ),
        )

    type_ids = []
    for line_form in filled_forms:
        ptype = line_form.cleaned_data.get("production_type")
        type_ids.append(ptype.pk if ptype else None)
    if _product_collision_in_plan(
        plan,
        product=form.cleaned_data.get("product"),
        mold=form.cleaned_data.get("mold"),
        type_ids=type_ids,
        exclude_item_id=instance.pk if instance else None,
    ):
        form.add_error(
            "product",
            "این کالا با همین قالب و نوع تولید قبلاً در این برنامه ثبت شده است.",
        )
        mold = form.cleaned_data.get("mold")
        if mold is not None:
            form.add_error("mold", "قالب با ردیف قبلی یکسان است؛ برای ثبت مجدد کالا باید قالب یا نوع تولید فرق کند.")
        for line_form in filled_forms:
            if line_form.cleaned_data.get("production_type"):
                line_form.add_error(
                    "production_type",
                    "نوع تولید با ردیف قبلی یکسان است.",
                )
        messages.error(request, "این کالا تکراری است. قالب یا نوع تولید باید متفاوت باشد.")
        return render(
            request,
            "planning/plan_detail.html",
            _plan_item_form_context(
                request, plan, profile,
                form=form, formset=formset, editing_item=instance,
            ),
        )

    with transaction.atomic():
        item = form.save(commit=False)
        item.plan = plan
        has_history = FittingProduction.objects.filter(machine=item.machine).exists()
        item.history_alarm = not has_history
        if instance is None:
            item.sequence = plan.items.filter(machine=item.machine).count() + 1
        item.save()

        saved_lines = []
        for line_form in filled_forms:
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

        item.active_cavities = saved_lines[0].active_cavities or 1
        item.save(update_fields=["active_cavities"])

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
    return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")


@login_required
def item_delete(request, pk, item_id):
    """Delete one کالا (and its production rows) from the plan."""
    plan = get_object_or_404(WeeklyPlan, pk=pk)
    profile = get_profile(request.user)
    if not _can_edit_plan(request.user, profile, plan):
        raise PermissionDenied("فقط ایجادکنندهٔ برنامه می‌تواند آن را ویرایش کند.")
    if request.method != "POST":
        return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")
    item = get_object_or_404(WeeklyPlanItem, pk=item_id, plan=plan)
    item.delete()
    from .uid import refresh_plan_uids
    refresh_plan_uids(plan)
    messages.success(request, "ردیف انتخاب‌شده حذف شد.")
    return redirect(f"{reverse('plan_detail', args=[pk])}?mode=edit")


@login_required
def product_insights(request):
    """JSON: glass-panel metrics for the selected product."""
    from .insights import resolve_insight_details

    product_id = request.GET.get("product")
    product = Product.objects.filter(pk=product_id).first() if product_id else None
    details = request.GET.get("details") == "1"
    if details:
        return JsonResponse(resolve_insight_details(product))
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
