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
DATE_KEYS = {
    "date",
    "document_date",
    "file_document_date",
    "plan_date",
    "plan_start",
    "actual_start",
    "actual_end",
    "planning_date",
    "start_date",
}
PRODUCT_CODE_KEYS = {"code", "product_code"}
UNIQUE_CODE_KEYS = {"unique_code"}
MOLD_NUMBER_KEYS = {"mold_number"}
VOUCHER_NUMBER_KEYS = {"voucher_number", "voucher_no", "voucher"}
CODE_KEYS = set(PRODUCT_CODE_KEYS)
PARAM_KEYS = (
    DATE_KEYS
    | PRODUCT_CODE_KEYS
    | UNIQUE_CODE_KEYS
    | MOLD_NUMBER_KEYS
    | VOUCHER_NUMBER_KEYS
)
NUMBER_KEYS: set[str] = set()


def keys_for_parameter_kind(kind: str) -> list[str]:
    kind = str(kind or "")
    if kind in (
        ReportParameterDef.KIND_DAY_DATE,
        ReportParameterDef.KIND_YEAR,
        "date",
    ):
        return sorted(DATE_KEYS)
    if kind in (ReportParameterDef.KIND_PRODUCT_CODE, "code"):
        return sorted(PRODUCT_CODE_KEYS)
    if kind == ReportParameterDef.KIND_UNIQUE_CODE:
        return sorted(UNIQUE_CODE_KEYS)
    if kind == ReportParameterDef.KIND_MOLD_NUMBER:
        return sorted(MOLD_NUMBER_KEYS)
    if kind == ReportParameterDef.KIND_VOUCHER_NUMBER:
        return sorted(VOUCHER_NUMBER_KEYS)
    return []


def _normalize_kind(kind: str) -> str:
    raw = str(kind or "")
    if raw in {"date", ReportParameterDef.KIND_DAY_DATE}:
        return ReportParameterDef.KIND_DAY_DATE
    if raw in {"code", ReportParameterDef.KIND_PRODUCT_CODE}:
        return ReportParameterDef.KIND_PRODUCT_CODE
    if raw == "number":
        return ""
    return raw


def infer_field_param_kind(field_key: str, label: str = "", source: str = "") -> str:
    """Map a report column to a parameter kind, or empty if not parameter-capable."""
    key = str(field_key or "").strip()
    if not key:
        return ""
    key_l = key.lower()
    label_l = str(label or "")
    source_l = str(source or "").lower()

    if key in DATE_KEYS or "date" in key_l or "تاریخ" in label_l:
        return ReportParameterDef.KIND_DAY_DATE
    if key in UNIQUE_CODE_KEYS or "کد یکتا" in label_l:
        return ReportParameterDef.KIND_UNIQUE_CODE
    if key in MOLD_NUMBER_KEYS or "شماره قالب" in label_l:
        return ReportParameterDef.KIND_MOLD_NUMBER
    if (
        key in VOUCHER_NUMBER_KEYS
        or "حواله" in label_l
        or key_l in {"voucher_number", "voucher_no", "voucher"}
        or ("voucher" in source_l and ("شماره" in label_l or "number" in key_l))
    ):
        return ReportParameterDef.KIND_VOUCHER_NUMBER
    if key in PRODUCT_CODE_KEYS or label_l.strip() in {"کد کالا", "کد"} or key_l == "product_code":
        return ReportParameterDef.KIND_PRODUCT_CODE
    return ""


def field_param_kinds(field_key: str, label: str = "", source: str = "") -> set[str]:
    base = infer_field_param_kind(field_key, label=label, source=source)
    if base == ReportParameterDef.KIND_DAY_DATE:
        return {ReportParameterDef.KIND_DAY_DATE, ReportParameterDef.KIND_YEAR}
    if base:
        return {base}
    return set()


def _column_label_index() -> dict[tuple[str, str], str]:
    """(source, key) -> label from the live report source catalog."""
    out: dict[tuple[str, str], str] = {}
    try:
        from reports.columns import get_column_groups

        for group in get_column_groups():
            source = str(group.get("id") or "")
            for item in group.get("columns") or []:
                if isinstance(item, (list, tuple)) and item:
                    key = str(item[0])
                    label = str(item[1]) if len(item) > 1 else key
                    out[(source, key)] = label
    except Exception:
        return out
    return out


def source_choices() -> list[tuple[str, str]]:
    try:
        from reports.columns import get_column_groups

        return [
            (str(g.get("id") or ""), str(g.get("label") or g.get("id") or ""))
            for g in get_column_groups()
            if g.get("id")
        ]
    except Exception:
        return []


def param_to_dict(p: ReportParameterDef) -> dict:
    return {
        "code": p.code,
        "label": p.label,
        "kind": _normalize_kind(p.kind),
        "source_key": str(p.source_key or ""),
        "sample_value": p.sample_value or "",
    }


def list_active_parameters() -> list[dict]:
    qs = ReportParameterDef.objects.filter(is_active=True).order_by("order", "code")
    return [param_to_dict(p) for p in qs]


def parameter_matches_field(
    param: dict | ReportParameterDef,
    field_key: str,
    *,
    source: str = "",
    label: str = "",
) -> bool:
    if isinstance(param, ReportParameterDef):
        param = param_to_dict(param)
    kind = _normalize_kind(param.get("kind"))
    if not kind:
        return False
    source_key = str(param.get("source_key") or "").strip()
    if source_key and source and source_key != source:
        return False
    kinds = field_param_kinds(field_key, label=label, source=source)
    if kind in kinds:
        return True
    applies = param.get("applies_to_keys") if isinstance(param, dict) else None
    if isinstance(applies, list) and field_key in applies:
        return True
    return False


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


def field_supports_parameter(field_key: str, source: str = "", label: str = "") -> bool:
    if label or source:
        return bool(field_param_kinds(field_key, label=label, source=source))
    labels = _column_label_index()
    if source:
        label = labels.get((source, str(field_key or "")), "")
        return bool(field_param_kinds(field_key, label=label, source=source))
    if field_param_kinds(field_key, label="", source=""):
        return True
    for (src, key), lbl in labels.items():
        if key == str(field_key or "") and field_param_kinds(key, label=lbl, source=src):
            return True
    return False


def field_kind(field_key: str) -> str:
    kinds = field_param_kinds(field_key)
    if ReportParameterDef.KIND_DAY_DATE in kinds:
        return ReportParameterDef.KIND_DAY_DATE
    if kinds:
        return next(iter(kinds))
    return ""


def list_parameters_for_field(field_key: str, source: str = "", label: str = "") -> list[dict]:
    kinds = field_param_kinds(field_key, label=label, source=source)
    if not kinds:
        return []
    key = str(field_key or "")
    out = []
    for p in ReportParameterDef.objects.filter(is_active=True).order_by("order", "code"):
        payload = param_to_dict(p)
        payload["applies_to_keys"] = p.applies_to_keys if isinstance(p.applies_to_keys, list) else []
        if not parameter_matches_field(payload, key, source=source, label=label):
            continue
        out.append(
            {
                "code": payload["code"],
                "label": payload["label"],
                "kind": payload["kind"],
                "source_key": payload["source_key"],
                "sample_value": payload["sample_value"],
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
    if field_kind(key) == "":
        return None
    # Categorical-ish text fields without a catalog: free text
    return None



PAREN_OPEN_CHOICES = ("", "(", "((")
PAREN_CLOSE_CHOICES = ("", ")", "))")


def paren_open_of(row: dict) -> str:
    """Open parenthesis marker; supports legacy single `paren` field."""
    if not isinstance(row, dict):
        return ""
    if "paren_open" in row or "paren_close" in row:
        raw = str(row.get("paren_open") or "").strip()
        return raw if raw in ("(", "((") else ""
    return "(" if str(row.get("paren") or "") == "(" else ""


def paren_close_of(row: dict) -> str:
    """Close parenthesis marker; supports legacy single `paren` field."""
    if not isinstance(row, dict):
        return ""
    if "paren_open" in row or "paren_close" in row:
        raw = str(row.get("paren_close") or "").strip()
        return raw if raw in (")", "))") else ""
    return ")" if str(row.get("paren") or "") == ")" else ""


def paren_open_weight(marker: str) -> int:
    return 2 if marker == "((" else (1 if marker == "(" else 0)


def paren_close_weight(marker: str) -> int:
    return 2 if marker == "))" else (1 if marker == ")" else 0)


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
    if p_open not in PAREN_OPEN_CHOICES or p_close not in PAREN_CLOSE_CHOICES:
        return "پرانتز نامعتبر است."
    if p_open and p_close:
        return "در یک شرط فقط پرانتز باز یا پرانتز بسته مجاز است."
    if is_first and logic:
        return "اولین شرط نباید AND/OR داشته باشد."
    if not is_first and not logic:
        return "شرط‌های بعدی باید AND یا OR داشته باشند."
    if not source or not field:
        return "منبع و زیرشاخه را انتخاب کنید."
    if op not in {o[0] for o in OPS}:
        return "عملگر مقایسه نامعتبر است."
    if mode == "parameter":
        if not field_supports_parameter(field, source=source):
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
            open_parens += paren_open_weight(paren_open_of(row))
            open_parens -= paren_close_weight(paren_close_of(row))
            if open_parens < 0:
                errors.append(f"{label}: پرانتز بسته بدون باز.")
                open_parens = 0
        if open_parens:
            errors.append(f"{label}: پرانتز باز بدون بسته.")

    _check_list(data["public"], "عمومی")
    for uid, rows in data["private"].items():
        _check_list(rows, f"خصوصی({uid})")
    return errors


def compact_jalali_day(value: Any) -> int | None:
    """Normalize a jalali date to YYYYMMDD int (1405/07/16 and 14050716 are equal)."""
    if value is None:
        return None
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            y, m, d = int(value.year), int(value.month), int(value.day)
            if 1200 <= y <= 1599 and 1 <= m <= 12 and 1 <= d <= 31:
                return y * 10000 + m * 100 + d
        except (TypeError, ValueError):
            pass
    text = str(value).strip().replace("٫", "/")
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        try:
            y, m, d = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
        except ValueError:
            return None
        if 1200 <= y <= 1599 and 1 <= m <= 12 and 1 <= d <= 31:
            return y * 10000 + m * 100 + d
        return None
    parts = [p for p in text.replace("-", "/").split("/") if p]
    if len(parts) == 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if 1200 <= y <= 1599 and 1 <= m <= 12 and 1 <= d <= 31:
            return y * 10000 + m * 100 + d
    return None


def jalali_year_value(value: Any) -> int | None:
    compact = compact_jalali_day(value)
    if compact is not None:
        return compact // 10000
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        try:
            year = int(digits[:4])
        except ValueError:
            return None
        if 1200 <= year <= 1599:
            return year
    return None


def _compare_ordered(left_v: Any, op: str, right_v: Any) -> bool:
    if op == "=":
        return left_v == right_v
    if op == "<>":
        return left_v != right_v
    if op == ">":
        return left_v > right_v
    if op == ">=":
        return left_v >= right_v
    if op == "<":
        return left_v < right_v
    if op == "<=":
        return left_v <= right_v
    return False


def _cmp(left: Any, op: str, right: Any, *, kind: str = "") -> bool:
    if op == "contains":
        return str(right) in str(left)
    kind = _normalize_kind(kind)
    if kind == ReportParameterDef.KIND_YEAR:
        ly, ry = jalali_year_value(left), jalali_year_value(right)
        if ly is not None and ry is not None:
            return _compare_ordered(ly, op, ry)
    if kind == ReportParameterDef.KIND_DAY_DATE or compact_jalali_day(left) is not None:
        ld, rd = compact_jalali_day(left), compact_jalali_day(right)
        if ld is not None and rd is not None:
            return _compare_ordered(ld, op, rd)
        if kind == ReportParameterDef.KIND_DAY_DATE:
            ly, ry = jalali_year_value(left), jalali_year_value(right)
            if ly is not None and ry is not None and compact_jalali_day(right) is None:
                return _compare_ordered(ly, op, ry)
    # numeric compare when possible
    try:
        ln = float(str(left).replace(",", ""))
        rn = float(str(right).replace(",", ""))
        left_v, right_v = ln, rn
        numeric = True
    except (TypeError, ValueError):
        left_v, right_v = str(left), str(right)
        numeric = False
    if not numeric:
        return _compare_ordered(str(left), op, str(right))
    return _compare_ordered(left_v, op, right_v)


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

    codes = [
        str(cond.get("param_code") or "").strip()
        for cond in conditions
        if str(cond.get("param_code") or "").strip()
    ]
    kind_by_code = {
        p.code: _normalize_kind(p.kind)
        for p in ReportParameterDef.objects.filter(code__in=codes)
    } if codes else {}

    for i, cond in enumerate(conditions):
        logic = str(cond.get("logic") or "").lower()
        if i > 0 and logic in ("and", "or"):
            while ops and ops[-1] != "(" and _prec(ops[-1]) >= _prec(logic):
                apply_op()
            ops.append(logic)
        for _ in range(paren_open_weight(paren_open_of(cond))):
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
        param_code = str(cond.get("param_code") or "").strip()
        cmp_kind = kind_by_code.get(param_code) or infer_field_param_kind(field, source=src)
        values.append(_cmp(left, str(cond.get("op") or "="), right, kind=cmp_kind))

        for _ in range(paren_close_weight(paren_close_of(cond))):
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
                "kind": _normalize_kind(p.kind if p else field_kind(str(row.get("field") or ""))),
                "source_key": str(p.source_key or "") if p else "",
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
    """Field-key → parameters. Each entry includes source_key for client filtering."""
    labels = _column_label_index()
    keys: set[str] = set(PARAM_KEYS)
    for _src, key in labels:
        keys.add(key)
    catalog: dict[str, list[dict]] = {}
    defs = list(ReportParameterDef.objects.filter(is_active=True).order_by("order", "code"))
    payloads = []
    for p in defs:
        item = param_to_dict(p)
        item["applies_to_keys"] = p.applies_to_keys if isinstance(p.applies_to_keys, list) else []
        payloads.append(item)
    for key in sorted(keys):
        matched: list[dict] = []
        seen: set[str] = set()
        related_labels = [(src, lbl) for (src, k), lbl in labels.items() if k == key]
        if not related_labels:
            related_labels = [("", "")]
        for src, lbl in related_labels:
            for payload in payloads:
                if not parameter_matches_field(payload, key, source=src, label=lbl):
                    continue
                token = f"{payload['code']}::{payload.get('source_key') or ''}"
                if token in seen:
                    continue
                seen.add(token)
                matched.append(
                    {
                        "code": payload["code"],
                        "label": payload["label"],
                        "kind": payload["kind"],
                        "source_key": payload["source_key"],
                        "sample_value": payload["sample_value"],
                    }
                )
        if matched:
            catalog[key] = matched
    return catalog


def build_field_param_kind_map() -> dict[str, str]:
    """Maps `source:key` and bare `key` to the primary parameter kind."""
    out: dict[str, str] = {}
    labels = _column_label_index()
    for (source, key), label in labels.items():
        kind = infer_field_param_kind(key, label=label, source=source)
        if not kind:
            continue
        out[f"{source}:{key}"] = kind
        out.setdefault(key, kind)
    for key in PARAM_KEYS:
        out.setdefault(key, infer_field_param_kind(key))
    return {k: v for k, v in out.items() if v}


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
        ("date_today", "امروز", ReportParameterDef.KIND_DAY_DATE, "", "14050101"),
        ("year_current", "سال جاری", ReportParameterDef.KIND_YEAR, "", "1405"),
        ("code_selected", "کد کالای انتخابی", ReportParameterDef.KIND_PRODUCT_CODE, "", ""),
    ]
    created = 0
    for i, (code, label, kind, source_key, sample) in enumerate(defaults):
        obj, was = ReportParameterDef.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "kind": kind,
                "source_key": source_key,
                "applies_to_keys": keys_for_parameter_kind(kind),
                "sample_value": sample,
                "order": i,
                "is_active": True,
            },
        )
        if was:
            created += 1
            continue
        changed = False
        if obj.kind in {"date", "code"}:
            obj.kind = kind
            obj.applies_to_keys = keys_for_parameter_kind(kind)
            changed = True
        if not (obj.sample_value or "").strip() and sample:
            obj.sample_value = sample
            changed = True
        if changed:
            obj.save()
    ReportParameterDef.objects.filter(kind="number").update(is_active=False)
    return created
