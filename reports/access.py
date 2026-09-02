"""Visibility and mutation rules for reports and print forms."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from accounts.permissions import get_profile

from .models import PrintForm, SavedReport


def visible_reports(user) -> QuerySet[SavedReport]:
    if not user.is_authenticated:
        return SavedReport.objects.none()
    return (
        SavedReport.objects.filter(
            Q(is_standard=True) | Q(owner=user) | Q(viewers=user)
        )
        .distinct()
        .select_related("owner", "created_by")
    )


def can_view_report(user, report: SavedReport) -> bool:
    if not user.is_authenticated:
        return False
    if report.is_standard:
        return True
    if report.owner_id == user.id:
        return True
    return report.viewers.filter(pk=user.id).exists()


def can_edit_report(user, report: SavedReport) -> bool:
    profile = get_profile(user)
    if not profile or not profile.can_enter_data:
        return False
    if report.is_standard:
        return bool(profile.is_manager)
    return report.owner_id == user.id


def can_delete_report(user, report: SavedReport) -> bool:
    return can_edit_report(user, report)


def can_create_report(user) -> bool:
    profile = get_profile(user)
    return bool(profile and profile.can_enter_data)


def visible_forms(user) -> QuerySet[PrintForm]:
    if not user.is_authenticated:
        return PrintForm.objects.none()
    return (
        PrintForm.objects.filter(
            Q(is_standard=True) | Q(owner=user) | Q(viewers=user)
        )
        .distinct()
        .select_related("owner", "created_by")
    )


def can_view_form(user, form_obj: PrintForm) -> bool:
    if not user.is_authenticated:
        return False
    if form_obj.is_standard:
        return True
    if form_obj.owner_id == user.id:
        return True
    return form_obj.viewers.filter(pk=user.id).exists()


def can_edit_form(user, form_obj: PrintForm) -> bool:
    profile = get_profile(user)
    if not profile or not profile.can_enter_data:
        return False
    if form_obj.is_standard:
        return bool(profile.is_manager)
    return form_obj.owner_id == user.id


def can_delete_form(user, form_obj: PrintForm) -> bool:
    return can_edit_form(user, form_obj)


def can_create_form(user) -> bool:
    return can_create_report(user)
