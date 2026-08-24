"""Helpers for registering and describing system alarms."""

from __future__ import annotations

from catalog.models import SystemAlarm


def register_alarm(
    *,
    title: str,
    message: str,
    suggestion: str = "",
    severity: str = SystemAlarm.Severity.SERIOUS,
    kind: str = SystemAlarm.Kind.OTHER,
    details: dict | None = None,
    dedupe: bool = True,
) -> SystemAlarm:
    """Create an alarm; optionally skip duplicate open alarms with same text."""
    details = details or {}
    if dedupe:
        existing = SystemAlarm.objects.filter(
            status=SystemAlarm.Status.OPEN,
            kind=kind,
            title=title,
            message=message,
        ).first()
        if existing:
            return existing
    return SystemAlarm.objects.create(
        severity=severity,
        kind=kind,
        title=title,
        message=message,
        suggestion=suggestion,
        details=details,
    )


def uid_collision_suggestion(*, uid: str, owner_label: str, program_number: str) -> str:
    """Human-readable fix hint for a duplicate program UID."""
    return (
        f"شناسه «{uid}» هم‌اکنون برای {owner_label} استفاده شده است. "
        "پیشنهادها: "
        "۱) تاریخ تعویض قالب یا ترتیب کالاها را بازبینی کنید تا ردیف قالب عوض شود؛ "
        "۲) اگر شماره برنامه از ۹۹۹ گذشته (یا با شماره‌ای قبلی پس از چرخش ۳ رقم یکی شده)، "
        f"در «قانون شناسه برنامه» ارقام شماره برنامه را افزایش دهید (شماره فعلی برنامه: {program_number})؛ "
        "۳) پس از اصلاح، از اکشن بازسازی شناسه‌ها استفاده کنید."
    )
