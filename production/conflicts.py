"""Production conflict detection — قالب تکراری + تقدم/تاخر.

Replaces the old machine-occupancy-only rules.

قالب تکراری
-----------
Same ``unique_code`` (کد یکتا) across different plan numbers, with the same or
unknown mold type, cannot sit unresolved in more than one program.

Conflict when:
- both awaiting
- both running / temp_stop
- older awaiting + newer occupying
NOT conflict when: older occupying + newer awaiting (until newer starts producing)

Live planning: existing occupying → block add; existing awaiting → allow with warning.
Status change: blocked while any conflict involves the program (message names conflict type).

تقدم/تاخر
---------
Different products on the same machine: order by actual start, else planned start.
Conflict when the later mold occupies while an earlier one is still active.
Both awaiting, or later still awaiting → OK.

Excel
-----
Empty ``unique_code`` rows must not transfer into history; re-import replaces by UID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.urls import reverse

from .models import ProductionHistoryRecord, ProductionProgram
from .sync import _normalize_status_label, infer_history_status, resolve_machine, status_label


KIND_DUPLICATE = "duplicate"  # قالب تکراری
KIND_PRECEDENCE = "precedence"  # تقدم/تاخر

OCCUPYING = frozenset({"running", "temp_stop"})
ACTIVE = frozenset({"awaiting", "running", "temp_stop"})


def _fmt_date(value) -> str:
    if value is None:
        return "—"
    try:
        from catalog.jalali_dates import storage_to_jalali

        j = storage_to_jalali(value)
        if j is not None:
            return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
    except Exception:  # noqa: BLE001
        pass
    if hasattr(value, "strftime"):
        try:
            return f"{value.year:04d}/{value.month:02d}/{value.day:02d}"
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _to_order_date(*candidates) -> date | None:
    """First usable date among candidates (already storage/Jalali-ish date objects)."""
    from catalog.jalali_dates import storage_to_jalali

    for value in candidates:
        if value is None:
            continue
        try:
            j = storage_to_jalali(value)
            if j is not None:
                return j.togregorian()
        except Exception:  # noqa: BLE001
            pass
        if isinstance(value, date):
            return value
    return None


def _norm_code(raw: str) -> str:
    return (raw or "").strip()


def _mold_key(*, mold_id=None, mold_name: str = "", mold_number: str = "") -> str:
    if mold_id:
        return f"id:{mold_id}"
    name = (mold_name or "").strip()
    number = (mold_number or "").strip()
    if name or number:
        return f"txt:{(name + '|' + number).casefold()}"
    return ""  # unknown / empty → groups with other unknowns


def _mold_label(*, mold=None, mold_name: str = "", mold_number: str = "") -> str:
    if mold is not None:
        return str(mold)
    bits = [b for b in [(mold_name or "").strip(), (mold_number or "").strip()] if b]
    return " / ".join(bits) if bits else "نامشخص"


@dataclass
class ConflictParty:
    """One active mold/program side involved in conflict analysis."""

    ref: str  # live:<pk> | history:<pk>
    kind: str
    pk: int
    unique_code: str
    mold_key: str
    mold_label: str
    mold_id: int | None
    status: str
    plan_number: str
    plan_date: Any = None
    product_name: str = ""
    product_code: str = ""
    machine_id: int | None = None
    machine_label: str = ""
    unit_number: int | None = None
    machine_number: str = ""
    actual_start: Any = None
    actual_end: Any = None
    plan_start: Any = None
    order_date: date | None = None
    uid: str = ""
    weekday_name: str = ""

    def as_dict(self) -> dict:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "pk": self.pk,
            "unique_code": self.unique_code,
            "mold_key": self.mold_key,
            "mold_label": self.mold_label,
            "mold_id": self.mold_id,
            "status": self.status,
            "status_display": status_label(self.status),
            "plan_number": self.plan_number,
            "plan_date_display": _fmt_date(self.plan_date),
            "product_name": self.product_name,
            "product_code": self.product_code,
            "machine_id": self.machine_id,
            "machine_label": self.machine_label,
            "unit_number": self.unit_number,
            "machine_number": self.machine_number,
            "actual_start_display": _fmt_date(self.actual_start),
            "actual_end_display": _fmt_date(self.actual_end),
            "plan_start_display": _fmt_date(self.plan_start),
            "order_date_display": _fmt_date(self.order_date),
            "uid": self.uid,
            "weekday_name": self.weekday_name or "—",
        }


@dataclass
class ConflictGroup:
    conflict_kind: str  # duplicate | precedence
    title: str
    message: str
    parties: list[ConflictParty] = field(default_factory=list)
    unique_code: str = ""
    machine_label: str = ""

    def as_dict(self) -> dict:
        return {
            "conflict_kind": self.conflict_kind,
            "kind_label": kind_label(self.conflict_kind),
            "title": self.title,
            "message": self.message,
            "unique_code": self.unique_code,
            "machine_label": self.machine_label,
            "parties": [p.as_dict() for p in self.parties],
            "count": len(self.parties),
        }


def kind_label(kind: str) -> str:
    return {
        KIND_DUPLICATE: "قالب تکراری",
        KIND_PRECEDENCE: "تقدم/تاخر",
    }.get(kind, kind)


def _weekday_name(value) -> str:
    try:
        from planning.models import persian_weekday
        from catalog.jalali_dates import storage_to_jalali

        j = storage_to_jalali(value)
        if j is not None:
            return persian_weekday(j)
    except Exception:  # noqa: BLE001
        pass
    return ""


def collect_active_parties() -> list[ConflictParty]:
    """All non-finished live programs + archive rows (deduped by UID preferring live)."""
    parties: list[ConflictParty] = []
    live_uids: set[str] = set()

    # Map UID → unique_code from archives for live enrichment
    archive_by_uid: dict[str, ProductionHistoryRecord] = {}
    for rec in ProductionHistoryRecord.objects.all().iterator(chunk_size=400):
        uid = (rec.program_uid or "").strip()
        if uid:
            archive_by_uid[uid] = rec

    programs = (
        ProductionProgram.objects.exclude(status=ProductionProgram.Status.FINISHED)
        .select_related(
            "item__product",
            "item__machine__unit",
            "item__plan",
            "item__mold",
            "mold",
        )
        .prefetch_related("item__lines")
    )
    for prog in programs:
        status = prog.status
        if status not in ACTIVE:
            continue
        uid = (prog.resolved_uid or "").strip()
        if uid:
            live_uids.add(uid)
        arch = archive_by_uid.get(uid) if uid else None
        unique = _norm_code(getattr(arch, "unique_code", "") if arch else "")
        if not unique:
            try:
                unique = _norm_code(prog.item.product.code)
            except Exception:  # noqa: BLE001
                unique = ""
        mold_obj = prog.mold or (prog.item.mold if prog.item_id else None)
        mold_name = getattr(arch, "mold_name", "") if arch else ""
        mold_number = getattr(arch, "mold_number", "") if arch else ""
        plan = prog.item.plan if prog.item_id else None
        plan_start = prog.item.mold_change_date if prog.item_id else None
        if arch and arch.plan_start_date:
            plan_start = arch.plan_start_date
        actual_start = prog.start_date
        actual_end = prog.stop_date if status == ProductionProgram.Status.FINISHED else (
            arch.actual_end_date if arch else None
        )
        order = _to_order_date(actual_start, plan_start, plan.date if plan else None)
        machine = prog.item.machine if prog.item_id else None
        parties.append(
            ConflictParty(
                ref=f"live:{prog.pk}",
                kind="live",
                pk=prog.pk,
                unique_code=unique,
                mold_key=_mold_key(
                    mold_id=mold_obj.pk if mold_obj else None,
                    mold_name=mold_name,
                    mold_number=mold_number,
                ),
                mold_label=_mold_label(
                    mold=mold_obj, mold_name=mold_name, mold_number=mold_number
                ),
                mold_id=mold_obj.pk if mold_obj else None,
                status=status,
                plan_number=_norm_code(plan.program_number if plan else "") or "—",
                plan_date=plan.date if plan else None,
                product_name=prog.item.product.name if prog.item_id else "",
                product_code=prog.item.product.code if prog.item_id else "",
                machine_id=machine.pk if machine else None,
                machine_label=prog.machine_label,
                unit_number=machine.unit.number if machine else None,
                machine_number=str(machine.number) if machine else "",
                actual_start=actual_start,
                actual_end=actual_end,
                plan_start=plan_start,
                order_date=order,
                uid=uid,
                weekday_name=_weekday_name(plan.date if plan else plan_start),
            )
        )

    for rec in ProductionHistoryRecord.objects.iterator(chunk_size=400):
        uid = (rec.program_uid or "").strip()
        if uid and uid in live_uids:
            continue  # live twin already represents this mold
        status = infer_history_status(
            actual_start=rec.actual_start_date,
            actual_end=rec.actual_end_date,
            status_text=rec.status or "",
        )
        if status not in ACTIVE:
            continue
        unique = _norm_code(rec.unique_code)
        if not unique:
            # Incomplete Excel rows should not enter history; skip duplicate logic.
            continue
        machine = resolve_machine(
            unit_number=rec.unit_number, machine_number=rec.machine_number
        )
        plan_start = rec.plan_start_date or rec.mold_change_date
        order = _to_order_date(rec.actual_start_date, plan_start, rec.plan_date)
        machine_label = (
            f"دستگاه {machine.number} واحد {machine.unit.number}"
            if machine
            else (
                f"دستگاه {rec.machine_number or '—'} واحد {rec.unit_number or '—'}"
            )
        )
        parties.append(
            ConflictParty(
                ref=f"history:{rec.pk}",
                kind="history",
                pk=rec.pk,
                unique_code=unique,
                mold_key=_mold_key(
                    mold_name=rec.mold_name or "",
                    mold_number=rec.mold_number or "",
                ),
                mold_label=_mold_label(
                    mold_name=rec.mold_name or "", mold_number=rec.mold_number or ""
                ),
                mold_id=None,
                status=status,
                plan_number=_norm_code(rec.plan_number) or "—",
                plan_date=rec.plan_date,
                product_name=rec.product_name or "",
                product_code=rec.product_code or "",
                machine_id=machine.pk if machine else None,
                machine_label=machine_label,
                unit_number=rec.unit_number,
                machine_number=str(rec.machine_number or ""),
                actual_start=rec.actual_start_date,
                actual_end=rec.actual_end_date,
                plan_start=plan_start,
                order_date=order,
                uid=uid,
                weekday_name=_weekday_name(rec.plan_date or plan_start),
            )
        )

    return parties


def _pair_duplicate_conflict(a: ConflictParty, b: ConflictParty) -> bool:
    if a.plan_number == b.plan_number and a.plan_number not in ("", "—"):
        return False
    if a.mold_key != b.mold_key:
        return False
    sa, sb = a.status, b.status
    if sa in OCCUPYING and sb in OCCUPYING:
        return True
    if sa == "awaiting" and sb == "awaiting":
        return True
    # Mixed awaiting ↔ occupying — order by start dates
    def _key(p: ConflictParty):
        return (p.order_date or date.max, p.pk)

    older, newer = sorted([a, b], key=_key)
    if older.status == "awaiting" and newer.status in OCCUPYING:
        return True
    if older.status in OCCUPYING and newer.status == "awaiting":
        return False
    return False


def _pair_precedence_conflict(a: ConflictParty, b: ConflictParty) -> bool:
    """Different products on same machine."""
    if a.machine_id is None or a.machine_id != b.machine_id:
        return False
    if a.unique_code and b.unique_code and a.unique_code == b.unique_code:
        return False  # same product → duplicate mold path
    if a.product_code and b.product_code and a.product_code == b.product_code:
        if a.unique_code == b.unique_code:
            return False

    def _key(p: ConflictParty):
        return (p.order_date or date.max, p.pk)

    older, newer = sorted([a, b], key=_key)
    # OK if both awaiting OR the later mold is still awaiting
    if older.status == "awaiting" and newer.status == "awaiting":
        return False
    if newer.status == "awaiting":
        return False
    # Later occupies while earlier still active → conflict
    if newer.status in OCCUPYING and older.status in ACTIVE:
        return True
    return False


def collect_duplicate_conflicts(parties: list[ConflictParty] | None = None) -> list[ConflictGroup]:
    parties = parties if parties is not None else collect_active_parties()
    by_code: dict[str, list[ConflictParty]] = {}
    for p in parties:
        code = _norm_code(p.unique_code)
        if not code:
            continue
        by_code.setdefault(code.casefold(), []).append(p)

    groups: list[ConflictGroup] = []
    for _ck, group in by_code.items():
        # Split by mold_key
        by_mold: dict[str, list[ConflictParty]] = {}
        for p in group:
            by_mold.setdefault(p.mold_key, []).append(p)
        for mold_key, mold_parties in by_mold.items():
            # Distinct plan numbers involved in a true conflict pair
            conflicted: list[ConflictParty] = []
            seen_refs: set[str] = set()
            for i, a in enumerate(mold_parties):
                for b in mold_parties[i + 1 :]:
                    if _pair_duplicate_conflict(a, b):
                        for p in (a, b):
                            if p.ref not in seen_refs:
                                seen_refs.add(p.ref)
                                conflicted.append(p)
            if len(conflicted) < 2:
                continue
            plans = sorted({p.plan_number for p in conflicted})
            sample = conflicted[0]
            groups.append(
                ConflictGroup(
                    conflict_kind=KIND_DUPLICATE,
                    title=f"کد یکتا «{sample.unique_code}» — {sample.product_name or sample.product_code or '—'}",
                    message=(
                        f"نوع تداخل: قالب تکراری — کد یکتا «{sample.unique_code}» "
                        f"با نوع قالب «{sample.mold_label}» در برنامه‌های "
                        f"{'، '.join(plans)} به‌صورت بلاتکلیف مانده است."
                    ),
                    parties=sorted(
                        conflicted,
                        key=lambda p: (p.order_date or date.max, p.plan_number, p.pk),
                    ),
                    unique_code=sample.unique_code,
                )
            )
    return groups


def collect_precedence_conflicts(parties: list[ConflictParty] | None = None) -> list[ConflictGroup]:
    parties = parties if parties is not None else collect_active_parties()
    by_machine: dict[int, list[ConflictParty]] = {}
    for p in parties:
        if p.machine_id is None:
            continue
        by_machine.setdefault(p.machine_id, []).append(p)

    groups: list[ConflictGroup] = []
    for _mid, group in by_machine.items():
        conflicted: list[ConflictParty] = []
        seen: set[str] = set()
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if _pair_precedence_conflict(a, b):
                    for p in (a, b):
                        if p.ref not in seen:
                            seen.add(p.ref)
                            conflicted.append(p)
        if len(conflicted) < 2:
            continue
        sample = conflicted[0]
        groups.append(
            ConflictGroup(
                conflict_kind=KIND_PRECEDENCE,
                title=f"دستگاه «{sample.machine_label}»",
                message=(
                    f"نوع تداخل: تقدم/تاخر — روی «{sample.machine_label}» بیش از یک قالب "
                    f"با ترتیب شروع ناسازگار در وضعیت فعال است."
                ),
                parties=sorted(
                    conflicted,
                    key=lambda p: (p.order_date or date.max, p.pk),
                ),
                machine_label=sample.machine_label,
            )
        )
    return groups


def collect_all_conflicts() -> dict[str, list[ConflictGroup]]:
    parties = collect_active_parties()
    return {
        KIND_DUPLICATE: collect_duplicate_conflicts(parties),
        KIND_PRECEDENCE: collect_precedence_conflicts(parties),
    }


def conflict_counts() -> dict[str, int]:
    all_c = collect_all_conflicts()
    return {
        KIND_DUPLICATE: len(all_c[KIND_DUPLICATE]),
        KIND_PRECEDENCE: len(all_c[KIND_PRECEDENCE]),
        "total": len(all_c[KIND_DUPLICATE]) + len(all_c[KIND_PRECEDENCE]),
    }


# --- Backward-compatible wrappers (old call sites) ---------------------------


@dataclass
class ConflictItem:
    machine_label: str
    message: str
    links: list[dict]
    conflict_kind: str = KIND_PRECEDENCE


def collect_in_production_conflicts() -> list[ConflictItem]:
    """Flat list for alarms / hub banners (both kinds)."""
    items: list[ConflictItem] = []
    for kind, groups in collect_all_conflicts().items():
        for g in groups:
            items.append(
                ConflictItem(
                    machine_label=g.machine_label or g.unique_code or g.title,
                    message=g.message,
                    conflict_kind=kind,
                    links=[
                        {
                            "label": (
                                f"برنامه {p.plan_number} — {p.product_name or p.unique_code} "
                                f"[{status_label(p.status)}]"
                            ),
                            "url": "",  # fixes stay on conflict pages
                            "status": status_label(p.status),
                            "uid": p.uid or p.unique_code,
                            "product": p.product_name,
                            "actual_start": _fmt_date(p.actual_start),
                            "kind": p.kind,
                            "plan_number": p.plan_number,
                            "ref": p.ref,
                        }
                        for p in g.parties
                    ],
                )
            )
    return items


def conflicts_as_dicts(conflicts: list[ConflictItem] | None = None) -> list[dict]:
    items = conflicts if conflicts is not None else collect_in_production_conflicts()
    return [
        {
            "machine_label": c.machine_label,
            "message": c.message,
            "links": c.links,
            "conflict_kind": getattr(c, "conflict_kind", ""),
            "kind_label": kind_label(getattr(c, "conflict_kind", "")),
        }
        for c in items
    ]


def history_conflict_uids() -> set[str]:
    out: set[str] = set()
    for c in collect_in_production_conflicts():
        for link in c.links:
            uid = (link.get("uid") or "").strip()
            if uid:
                out.add(uid)
    return out


def history_conflict_unique_codes() -> set[str]:
    out: set[str] = set()
    for g in collect_duplicate_conflicts():
        if g.unique_code:
            out.add(g.unique_code.casefold())
    return out


# --- Live planning / status-change guards ------------------------------------


def evaluate_duplicate_for_new_item(
    *,
    unique_code: str,
    mold_id: int | None,
    plan_number: str,
    plan_start=None,
) -> dict[str, Any]:
    """Return {blocked, warn, message} for adding a new awaiting item."""
    code = _norm_code(unique_code)
    if not code:
        return {"blocked": False, "warn": False, "message": ""}
    mold_key = _mold_key(mold_id=mold_id)
    hypothetical = ConflictParty(
        ref="new:0",
        kind="new",
        pk=0,
        unique_code=code,
        mold_key=mold_key,
        mold_label="",
        mold_id=mold_id,
        status="awaiting",
        plan_number=_norm_code(plan_number) or "NEW",
        plan_start=plan_start,
        order_date=_to_order_date(plan_start),
    )
    others = [
        p
        for p in collect_active_parties()
        if _norm_code(p.unique_code).casefold() == code.casefold()
        and p.mold_key == mold_key
        and p.plan_number != hypothetical.plan_number
    ]
    if not others:
        return {"blocked": False, "warn": False, "message": ""}

    # If any existing is occupying → block (cannot add second while first produces)
    occupying = [p for p in others if p.status in OCCUPYING]
    awaiting = [p for p in others if p.status == "awaiting"]
    if occupying:
        # Mixed rule: if older occupying and new awaiting → allowed? User said only when
        # first is awaiting may second be added. So if any occupying exists → block.
        return {
            "blocked": True,
            "warn": False,
            "message": (
                "نوع تداخل: قالب تکراری — این کالا (کد یکتا) هم‌اکنون در برنامهٔ دیگری "
                f"در وضعیت «{status_label(occupying[0].status)}» است "
                f"(شماره برنامه {occupying[0].plan_number}). ابتدا تداخل را رفع کنید."
            ),
        }
    if awaiting:
        return {
            "blocked": False,
            "warn": True,
            "message": (
                "هشدار نوع تداخل: قالب تکراری — این کالا در برنامهٔ دیگری در انتظار تولید است "
                f"(شماره برنامه {awaiting[0].plan_number}). ثبت مجاز است اما تداخل ثبت می‌شود "
                "و تا رفع آن، تغییر وضعیت مسدود خواهد بود."
            ),
        }
    return {"blocked": False, "warn": False, "message": ""}


def _message_for_party_conflicts(
    *,
    ref: str,
    uid: str,
    dups: list[ConflictGroup],
    prec: list[ConflictGroup],
) -> str | None:
    for g in dups:
        if any(p.ref == ref or (uid and p.uid == uid) for p in g.parties):
            return f"ابتدا خطای موجود رفع شود — نوع تداخل: قالب تکراری. {g.message}"
    for g in prec:
        if any(p.ref == ref or (uid and p.uid == uid) for p in g.parties):
            return f"ابتدا خطای موجود رفع شود — نوع تداخل: تقدم/تاخر. {g.message}"
    return None


def evaluate_status_change_block(program: ProductionProgram, new_status: str) -> str | None:
    """Block status changes while this program is in conflict, or if the new status would create one.

    اتمام تولید always allowed (helps clear occupancy). Transitions into running/temp_stop
    are blocked when a قالب تکراری / تقدم‌تاخر error already exists or would appear.
    """
    if new_status == ProductionProgram.Status.FINISHED:
        return None
    if new_status == ProductionProgram.Status.AWAITING:
        return None

    if new_status in (ProductionProgram.Status.TEMP_STOP, "temp_stop"):
        target = "temp_stop"
    elif new_status in (ProductionProgram.Status.RUNNING, "running"):
        target = "running"
    else:
        return None

    uid = (program.resolved_uid or "").strip()
    ref = f"live:{program.pk}"

    # 1) Existing unresolved conflict involving this program → block immediately
    existing = collect_all_conflicts()
    existing_msg = _message_for_party_conflicts(
        ref=ref,
        uid=uid,
        dups=existing[KIND_DUPLICATE],
        prec=existing[KIND_PRECEDENCE],
    )
    if existing_msg:
        return existing_msg

    # 2) Simulate after the status change
    parties = collect_active_parties()
    simulated: list[ConflictParty] = []
    found = False
    for p in parties:
        if p.kind == "live" and p.pk == program.pk:
            found = True
            simulated.append(
                ConflictParty(
                    **{
                        **p.__dict__,
                        "status": target,
                        "actual_start": p.actual_start or p.plan_start,
                        "order_date": _to_order_date(
                            p.actual_start or p.plan_start, p.order_date
                        ),
                    }
                )
            )
        elif uid and p.uid == uid and p.kind == "history":
            continue
        else:
            simulated.append(p)
    if not found:
        try:
            product = program.item.product
            mold = program.mold or program.item.mold
            plan = program.item.plan
            machine = program.item.machine
            simulated.append(
                ConflictParty(
                    ref=ref,
                    kind="live",
                    pk=program.pk,
                    unique_code=_norm_code(product.code),
                    mold_key=_mold_key(mold_id=mold.pk if mold else None),
                    mold_label=_mold_label(mold=mold),
                    mold_id=mold.pk if mold else None,
                    status=target,
                    plan_number=_norm_code(plan.program_number),
                    plan_date=plan.date,
                    product_name=product.name,
                    product_code=product.code,
                    machine_id=machine.pk,
                    machine_label=program.machine_label,
                    unit_number=machine.unit.number,
                    machine_number=str(machine.number),
                    actual_start=program.start_date or program.item.mold_change_date,
                    plan_start=program.item.mold_change_date,
                    order_date=_to_order_date(
                        program.start_date, program.item.mold_change_date, plan.date
                    ),
                    uid=uid,
                )
            )
        except Exception:  # noqa: BLE001
            return None

    return _message_for_party_conflicts(
        ref=ref,
        uid=uid,
        dups=collect_duplicate_conflicts(simulated),
        prec=collect_precedence_conflicts(simulated),
    )


def party_from_ref(ref: str) -> ConflictParty | None:
    for p in collect_active_parties():
        if p.ref == ref:
            return p
    return None


# Keep occupancy_status for older tests that import it
def occupancy_status(*, actual_start, actual_end, status_text: str = "") -> str | None:
    hinted = _normalize_status_label(status_text or "")
    if hinted == "temp_stop":
        return "temp_stop"
    if actual_end or hinted == "finished":
        return None
    if hinted == "awaiting" and not actual_start:
        return None
    if actual_start and not actual_end:
        return "running"
    if hinted == "running":
        return "running"
    return None
