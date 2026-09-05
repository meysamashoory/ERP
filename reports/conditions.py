"""Report condition helpers: options, validation, and runtime evaluation."""

from __future__ import annotations

from typing import Any

from reports.models import ReportParameterDef

OPS = [
    ("=", "مساوی"),
    ("<>", "مخالف"),
    (">", "بزرگ‌تر"),
    (">=", "بزرگ‌تر یا مساوی"),
    ("<", "کوچک‌تر"),
    ("<=", "کوچک‌تر یا مساوی"),
    ("contains", "شامل"),
]

LOGIC_OPTIONS = [("", "—"), ("and", "AND"), ("or", "OR")]
PAREN_OPTIONS = [("", "—"), ("(", "("), (")", ")")]

# Column keys that may use parameter mode (and value+param presets).
PARAM_KEYS = {
    "date",
    "document_date",
    "file_document_date",
    "plan_date",
    "plan_start",
    "actual_start",
    "actual_end",
    "code",
    "product_code",
    "stock_finished",
    "stock_unassembled",
    "produced",
    "planned_qty",
    "actual_qty",
    "reorder_level",
    "depot_ceiling",
    "per_carton",
    "per_bag",
    "unit_weight_grams",
    "file_stock",
}

DATE_KEYS = {
    "date",
    "document_date",
    "file_document_date",
    "plan_date",
    "plan_start",
    "actual_start",
    "actual_end",
}
CODE_KEYS = {"code", "product_code"}
NUMBER_KEYS = PARAM_KEYS - DATE_KEYS - CODE_KEYS


def normalize_conditions(raw) -> dict:
    if not isinstance(raw, dict):
        return {"public": [], "private": {}}
    public = raw.get("public") if isinstance(raw.get("public"), list) else []
    private_raw = raw.get("private") if isinstance(raw.get("private"), dict) else {}
    private: dict[str, list] = {}
    for uid, rows in private_raw.items():
        if isinstance(rows, list) and uid:
            private[str(uid)] = [r for r in rows if isinstance(r, dict)]
    return {
        "public": [r for r in public if isinstance(r, dict)],
        "private": private,
    }


def field_supports_parameter(field_key: str) -> bool:
    return str(field_key or "") in PARAM_KEYS


def field_kind(field_key: str) -> str:
    key = str(field_key or "")
    if key in DATE_KEYS:
        return ReportParameterDef.KIND_DATE
    if key in CODE_KEYS:
        return ReportParameterDef.KIND_CODE
    if key in NUMBER_KEYS:
        return ReportParameterDef.KIND_NUMBER
    return ""


def list_parameters_for_field(field_key: str) -> list[dict]:
    kind = field_kind(field_key)
    if not kind:
        return []
    key = str(field_key or "")
    qs = ReportParameterDef.objects.filter(is_active=True).order_by("order", "code")
    out = []
    for p in qs:
        applies = p.applies_to_keys if isinstance(p.applies_to_keys, list) else []
        if applies and key not in applies and kind not in applies:
            continue
        if not applies and p.kind != kind:
            continue
        out.append(
            {
                "code": p.code,
                "label": p.label,
                "kind": p.kind,
                "sample_value": p.sample_value or "",
            }
        )
    return out


def field_value_choices(source: str, field_key: str) -> list[dict] | None:
    """Return dropdown choices for categorical fields, else None (= free text)."""
    key = str(field_key or "")
    try:
        if key in ("subgroup", "product_subgroup"):
            from catalog.models import ProductSubGroup

            return [
                {"value": str(s), "label": str(s)}
                for s in ProductSubGroup.objects.order_by("group__name", "name")[:500]
            ]
        if key in ("group", "product_group"):
            from catalog.models import ProductGroup

            return [
                {"value": g.name, "label": g.name}
                for g in ProductGroup.objects.order_by("name")[:500]
            ]
        if key in ("unit", "production_unit"):
            from catalog.models import ProductionUnit

            return [
                {"value": u.name, "label": u.name}
                for u in ProductionUnit.objects.order_by("name")[:500]
            ]
        if key in ("machine",):
            from catalog.models import Machine

            return [
                {"value": m.code, "label": f"{m.code} — {m.name}"}
                for m in Machine.objects.order_by("code")[:800]
            ]
    except Exception:
        return None
    if field_kind(key) in (ReportParameterDef.KIND_NUMBER, ""):
        return None
    # Categorical-ish text fields without a catalog: free text
    return None



def paren_open_of(row: dict) -> str:
    """Open parenthesis marker; supports legacy single `paren` field."""
    if not isinstance(row, dict):
        return ""
    if "paren_open" in row or "paren_close" in row:
        return "(" if str(row.get("paren_open") or "") == "(" else ""
    return "(" if str(row.get("paren") or "") == "(" else ""


def paren_close_of(row: dict) -> str:
    """Close parenthesis marker; supports legacy single `paren` field."""
    if not isinstance(row, dict):
        return ""
    if "paren_open" in row or "paren_close" in row:
        return ")" if str(row.get("paren_close") or "") == ")" else ""
    return ")" if str(row.get("paren") or "") == ")" else ""


def validate_condition_row(row: dict, *, is_first: bool) -> str | None:
    logic = str(row.get("logic") or "").lower()
    p_open = paren_open_of(row)
    p_close = paren_close_of(row)
    source = str(row.get("source") or "").strip()
    field = str(row.get("field") or "").strip()
    op = str(row.get("op") or "").strip()
    mode = str(row.get("value_mode") or "value").lower()
    if logic not in ("", "and", "or"):
        return "مقدار AND/OR نامعتبر است."
    if p_open not in ("", "(") or p_close not in ("", ")"):
        return "پرانتز نامعتبر است."
    if is_first and logic:
        return "اولین شرط نباید AND/OR داشته باشد."
    if not is_first and not logic:
        return "شرط‌های بعدی باید AND یا OR داشته باشند."
    if not source or not field:
        return "منبع و زیرشاخه را انتخاب کنید."
    if op not in {o[0] for o in OPS}:
        return "عملگر مقایسه نامعتبر است."
    if mode == "parameter":
        if not field_supports_parameter(field):
            return "این ستون از پارامتر پشتیبانی نمی‌کند."
        if not str(row.get("param_code") or "").strip():
            return "پارامتر را انتخاب کنید."
    else:
        # value mode: either free value, or preset param + optional offset
        has_value = str(row.get("value") or "").strip() != ""
        has_param = str(row.get("param_code") or "").strip() != ""
        if not has_value and not has_param:
            return "مقدار شرط را وارد کنید."
        if has_param and str(row.get("value_offset") or "").strip() == "":
            # offset required when locking a preset as fixed value
            return "برای حالت مقدار با پارامتر از پیش‌تعریف، عدد را وارد کنید."
    return None


def validate_conditions_blob(raw) -> list[str]:
    data = normalize_conditions(raw)
    errors: list[str] = []
    open_parens = 0

    def _check_list(rows: list, label: str) -> None:
        nonlocal open_parens
        open_parens = 0
        for i, row in enumerate(rows):
            err = validate_condition_row(row, is_first=(i == 0))
            if err:
                errors.append(f"{label} ردیف {i + 1}: {err}")
            if paren_open_of(row) == "(":
                open_parens += 1
            if paren_close_of(row) == ")":
                open_parens -= 1
                if open_parens < 0:
                    errors.append(f"{label}: پرانتز بسته بدون باز.")
                    open_parens = 0
        if open_parens:
            errors.append(f"{label}: پرانتز باز بدون بسته.")

    _check_list(data["public"], "عمومی")
    for uid, rows in data["private"].items():
        _check_list(rows, f"خصوصی({uid})")
    return errors


def _cmp(left: Any, op: str, right: Any) -> bool:
    if op == "contains":
        return str(right) in str(left)
    # numeric compare when possible
    try:
        ln = float(str(left).replace(",", ""))
        rn = float(str(right).replace(",", ""))
        left_v, right_v = ln, rn
        numeric = True
    except (TypeError, ValueError):
        left_v, right_v = str(left), str(right)
        numeric = False
    if op == "=":
        return left_v == right_v if numeric else str(left) == str(right)
    if op == "<>":
        return left_v != right_v if numeric else str(left) != str(right)
    if not numeric:
        # fallback string ordering
        if op == ">":
            return str(left) > str(right)
        if op == ">=":
            return str(left) >= str(right)
        if op == "<":
            return str(left) < str(right)
        if op == "<=":
            return str(left) <= str(right)
        return False
    if op == ">":
        return left_v > right_v
    if op == ">=":
        return left_v >= right_v
    if op == "<":
        return left_v < right_v
    if op == "<=":
        return left_v <= right_v
    return False


def resolve_condition_value(row: dict, param_values: dict | None) -> Any:
    mode = str(row.get("value_mode") or "value").lower()
    param_values = param_values or {}
    if mode == "parameter":
        code = str(row.get("param_code") or "")
        return param_values.get(code, "")
    # value mode with locked preset + offset → use value_offset as concrete value
    # (builder stores final literal in `value` when possible)
    if str(row.get("value") or "").strip() != "":
        return row.get("value")
    if str(row.get("value_offset") or "").strip() != "":
        return row.get("value_offset")
    return ""


def row_matches_conditions(row: dict, conditions: list[dict], param_values: dict | None = None) -> bool:
    """Evaluate a list of condition rows with AND/OR and parentheses (Excel-like)."""
    if not conditions:
        return True

    # Build RPN / shunting-yard style boolean evaluation
    values: list[bool] = []
    ops: list[str] = []

    def apply_op():
        if len(values) < 2 or not ops:
            return
        op = ops.pop()
        b = values.pop()
        a = values.pop()
        values.append((a and b) if op == "and" else (a or b))

    for i, cond in enumerate(conditions):
        logic = str(cond.get("logic") or "").lower()
        if i > 0 and logic in ("and", "or"):
            while ops and ops[-1] != "(" and _prec(ops[-1]) >= _prec(logic):
                apply_op()
            ops.append(logic)
        if paren_open_of(cond) == "(":
            ops.append("(")

        field = str(cond.get("field") or "")
        # row keys may be storage uid or plain field key
        left = row.get(field, "")
        if left == "" and cond.get("uid_key"):
            left = row.get(str(cond.get("uid_key")), "")
        # also try source:key
        src = str(cond.get("source") or "")
        if left == "" and src:
            left = row.get(f"{src}:{field}", row.get(field, ""))
        right = resolve_condition_value(cond, param_values)
        values.append(_cmp(left, str(cond.get("op") or "="), right))

        if paren_close_of(cond) == ")":
            while ops and ops[-1] != "(":
                apply_op()
            if ops and ops[-1] == "(":
                ops.pop()

    while ops:
        if ops[-1] == "(":
            ops.pop()
            continue
        apply_op()
    return all(values) if len(values) != 1 else values[0]


def _prec(op: str) -> int:
    return 2 if op == "and" else 1


def collect_runtime_parameters(conditions_blob) -> list[dict]:
    """Unique parameter codes required when opening a report."""
    data = normalize_conditions(conditions_blob)
    rows: list[dict] = list(data["public"])
    for lst in data["private"].values():
        rows.extend(lst)
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        if str(row.get("value_mode") or "").lower() != "parameter":
            continue
        code = str(row.get("param_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        p = ReportParameterDef.objects.filter(code=code, is_active=True).first()
        out.append(
            {
                "code": code,
                "label": p.label if p else code,
                "kind": p.kind if p else field_kind(str(row.get("field") or "")),
                "sample_value": (p.sample_value if p else "") or "",
                "field": str(row.get("field") or ""),
            }
        )
    return out


def flatten_active_conditions(conditions_blob, column_uids: list[str] | None = None) -> list[dict]:
    data = normalize_conditions(conditions_blob)
    rows = list(data["public"])
    private = data["private"]
    if column_uids is None:
        for lst in private.values():
            rows.extend(lst)
    else:
        for uid in column_uids:
            rows.extend(private.get(str(uid), []))
    return rows


def build_parameters_catalog() -> dict[str, list[dict]]:
    return {key: list_parameters_for_field(key) for key in sorted(PARAM_KEYS)}


def build_field_choices_catalog() -> dict[str, list[dict]]:
    """Choices for categorical fields; missing keys mean free-text input."""
    out: dict[str, list[dict]] = {}
    for key in (
        "subgroup",
        "product_subgroup",
        "group",
        "product_group",
        "unit",
        "production_unit",
        "machine",
    ):
        choices = field_value_choices("", key)
        if choices:
            out[key] = choices
    return out


def ops_for_frontend() -> list[dict]:
    return [{"value": v, "label": lab} for v, lab in OPS]


def seed_default_parameters() -> int:
    defaults = [
        ("date_today", "امروز", ReportParameterDef.KIND_DATE, ["date", "document_date", "file_document_date", "plan_date"], ""),
        ("date_week_start", "ابتدای هفته", ReportParameterDef.KIND_DATE, ["date", "document_date", "plan_date"], ""),
        ("date_month_start", "ابتدای ماه", ReportParameterDef.KIND_DATE, ["date", "document_date", "plan_date"], ""),
        ("code_selected", "کد کالای انتخابی", ReportParameterDef.KIND_CODE, ["code", "product_code"], ""),
        ("qty_threshold", "آستانه تعداد", ReportParameterDef.KIND_NUMBER, ["stock_finished", "produced", "planned_qty", "actual_qty"], "0"),
    ]
    created = 0
    for i, (code, label, kind, keys, sample) in enumerate(defaults):
        obj, was = ReportParameterDef.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "kind": kind,
                "applies_to_keys": keys,
                "sample_value": sample,
                "order": i,
                "is_active": True,
            },
        )
        if was:
            created += 1
    return created
