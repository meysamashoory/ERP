"""Excel-like formula evaluation for report calculation columns.

Supported: + - * /, ROUND, ROUNDUP, ROUNDDOWN, SUM, SUMIF, SUMIFS,
COUNT, COUNTIF, COUNTIFS, AVERAGE, MIN, MAX, ABS, IF, AND, OR, NOT.
Column refs use codes like A1, B2 (case-insensitive).
"""

from __future__ import annotations

import math
import re
from typing import Any


FORMULA_FUNCTION_CATALOG: list[dict[str, Any]] = [
    {
        "id": "math",
        "label": "ریاضی",
        "functions": [
            {"name": "ROUND", "hint": "ROUND(عدد; ارقام)", "insert": "ROUND(,)"},
            {"name": "ROUNDUP", "hint": "ROUNDUP(عدد; ارقام)", "insert": "ROUNDUP(,)"},
            {"name": "ROUNDDOWN", "hint": "ROUNDDOWN(عدد; ارقام)", "insert": "ROUNDDOWN(,)"},
            {"name": "ABS", "hint": "ABS(عدد)", "insert": "ABS()"},
            {"name": "MIN", "hint": "MIN(عدد1; عدد2; …)", "insert": "MIN(,)"},
            {"name": "MAX", "hint": "MAX(عدد1; عدد2; …)", "insert": "MAX(,)"},
            {"name": "AVERAGE", "hint": "AVERAGE(عدد1; …)", "insert": "AVERAGE(,)"},
        ],
    },
    {
        "id": "aggregate",
        "label": "تجمیع",
        "functions": [
            {"name": "SUM", "hint": "SUM(عدد1; …)", "insert": "SUM(,)"},
            {"name": "SUMIF", "hint": "SUMIF(محدوده; شرط; [جمع])", "insert": "SUMIF(,,)"},
            {"name": "SUMIFS", "hint": "SUMIFS(جمع; شرط1; مقدار1; …)", "insert": "SUMIFS(,,,)"},
            {"name": "COUNT", "hint": "COUNT(مقدار1; …)", "insert": "COUNT(,)"},
            {"name": "COUNTIF", "hint": "COUNTIF(محدوده; شرط)", "insert": "COUNTIF(,)"},
            {"name": "COUNTIFS", "hint": "COUNTIFS(شرط1; مقدار1; …)", "insert": "COUNTIFS(,)"},
        ],
    },
    {
        "id": "logic",
        "label": "منطقی",
        "functions": [
            {"name": "IF", "hint": "IF(شرط; اگرصحیح; اگرغلط)", "insert": "IF(,,)"},
            {"name": "AND", "hint": "AND(شرط1; شرط2; …)", "insert": "AND(,)"},
            {"name": "OR", "hint": "OR(شرط1; شرط2; …)", "insert": "OR(,)"},
            {"name": "NOT", "hint": "NOT(شرط)", "insert": "NOT()"},
        ],
    },
]


_COL_REF_RE = re.compile(r"\b([A-Za-z]{1,3})(\d{1,3})\b")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def to_number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return default
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def normalize_col_code(code: str) -> str:
    return str(code or "").strip().lower()


def excel_col_letter(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa (Excel-style lowercase)."""
    if index < 0:
        index = 0
    letters: list[str] = []
    n = index
    while True:
        letters.append(chr(ord("a") + (n % 26)))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(letters))


def letter_to_index(letter: str) -> int:
    letter = normalize_col_code(letter)
    if not letter or not letter.isalpha():
        return 0
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord("a") + 1)
    return n - 1


def assign_missing_col_codes(specs: list[dict]) -> list[dict]:
    """Ensure every column has a stable Excel-like col_code (a1, b1, …)."""
    used_letters: dict[str, int] = {}
    next_letter_idx = 0
    for spec in specs:
        code = normalize_col_code(spec.get("col_code") or "")
        m = _COL_REF_RE.fullmatch(code) if code else None
        if m:
            letter, num_s = m.group(1).lower(), m.group(2)
            num = int(num_s)
            used_letters[letter] = max(used_letters.get(letter, 0), num)
            next_letter_idx = max(next_letter_idx, letter_to_index(letter) + 1)
            spec["col_code"] = f"{letter}{num}"
            continue
        while True:
            letter = excel_col_letter(next_letter_idx)
            next_letter_idx += 1
            if letter not in used_letters:
                break
        used_letters[letter] = 1
        spec["col_code"] = f"{letter}1"
    return specs


def next_copy_col_code(source_code: str, existing_codes: list[str]) -> str:
    """For a copied column, keep letter and bump copy number (a1 -> a2)."""
    code = normalize_col_code(source_code)
    m = _COL_REF_RE.fullmatch(code) if code else None
    if not m:
        return ""
    letter = m.group(1).lower()
    max_n = 0
    for other in existing_codes:
        om = _COL_REF_RE.fullmatch(normalize_col_code(other))
        if om and om.group(1).lower() == letter:
            max_n = max(max_n, int(om.group(2)))
    return f"{letter}{max_n + 1}"


def _match_criteria(value: Any, criteria: Any) -> bool:
    crit = "" if criteria is None else str(criteria).strip()
    if crit == "":
        return str(value) == ""
    val_num = None
    try:
        val_num = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        val_num = None
    for op in (">=", "<=", "<>", "!=", ">", "<", "="):
        if crit.startswith(op):
            rhs = crit[len(op) :].strip()

            def _cmp(a: float, b: float, operator: str = op) -> bool:
                if operator == ">=":
                    return a >= b
                if operator == "<=":
                    return a <= b
                if operator in ("<>", "!="):
                    return a != b
                if operator == ">":
                    return a > b
                if operator == "<":
                    return a < b
                return a == b

            try:
                rhs_n = float(rhs.replace(",", ""))
                if val_num is None:
                    return False
                return _cmp(val_num, rhs_n)
            except ValueError:
                left = str(value)
                if op == "=":
                    return left == rhs
                if op in ("<>", "!="):
                    return left != rhs
                return False
    try:
        rhs_n = float(crit.replace(",", ""))
        if val_num is not None:
            return val_num == rhs_n
    except ValueError:
        pass
    return str(value) == crit


class _FormulaError(Exception):
    pass


def _tokenize(expr: str) -> list[tuple[str, str]]:
    s = expr.strip()
    if s.startswith("="):
        s = s[1:]
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch in ";,":
            tokens.append(("comma", ","))
            i += 1
            continue
        if ch in "+-*/()":
            tokens.append(("op", ch))
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            buf: list[str] = []
            while i < len(s) and s[i] != quote:
                buf.append(s[i])
                i += 1
            if i < len(s):
                i += 1
            tokens.append(("str", "".join(buf)))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            j = i + 1
            while j < len(s) and (s[j].isdigit() or s[j] == "."):
                j += 1
            tokens.append(("num", s[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            word = s[i:j]
            if _COL_REF_RE.fullmatch(word):
                tokens.append(("col", word.lower()))
            else:
                tokens.append(("name", word.upper()))
            i = j
            continue
        raise _FormulaError(f"نویسه نامعتبر در فرمول: {ch}")
    return tokens


class _Parser:
    def __init__(
        self,
        tokens: list[tuple[str, str]],
        values_by_code: dict[str, Any],
        row_list: list[dict[str, Any]] | None = None,
        code_to_key: dict[str, str] | None = None,
    ):
        self.tokens = tokens
        self.pos = 0
        self.values_by_code = {normalize_col_code(k): v for k, v in values_by_code.items()}
        self.row_list = row_list or []
        self.code_to_key = {normalize_col_code(k): v for k, v in (code_to_key or {}).items()}

    def peek(self) -> tuple[str, str] | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def eat(self, kind: str | None = None, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise _FormulaError("فرمول ناقص است")
        if kind and tok[0] != kind:
            raise _FormulaError("ساختار فرمول نامعتبر است")
        if value is not None and tok[1] != value:
            raise _FormulaError("ساختار فرمول نامعتبر است")
        self.pos += 1
        return tok

    def parse(self) -> Any:
        if not self.tokens:
            return 0
        val = self.parse_expr()
        if self.peek() is not None:
            raise _FormulaError("فرمول اضافی دارد")
        return val

    def parse_expr(self) -> Any:
        val = self.parse_term()
        while True:
            tok = self.peek()
            if tok and tok[0] == "op" and tok[1] in "+-":
                self.eat()
                right = self.parse_term()
                val = to_number(val) + to_number(right) if tok[1] == "+" else to_number(val) - to_number(right)
            else:
                break
        return val

    def parse_term(self) -> Any:
        val = self.parse_unary()
        while True:
            tok = self.peek()
            if tok and tok[0] == "op" and tok[1] in "*/":
                self.eat()
                right = self.parse_unary()
                if tok[1] == "*":
                    val = to_number(val) * to_number(right)
                else:
                    denom = to_number(right)
                    val = (to_number(val) / denom) if denom else 0
            else:
                break
        return val

    def parse_unary(self) -> Any:
        tok = self.peek()
        if tok and tok[0] == "op" and tok[1] in "+-":
            self.eat()
            val = self.parse_unary()
            return to_number(val) if tok[1] == "+" else -to_number(val)
        return self.parse_primary()

    def parse_primary(self) -> Any:
        tok = self.peek()
        if tok is None:
            raise _FormulaError("فرمول ناقص است")
        if tok[0] == "num":
            self.eat()
            return float(tok[1])
        if tok[0] == "str":
            self.eat()
            return tok[1]
        if tok[0] == "col":
            self.eat()
            return self.values_by_code.get(tok[1], 0)
        if tok[0] == "name":
            name = self.eat()[1]
            return self.parse_call(name)
        if tok[0] == "op" and tok[1] == "(":
            self.eat()
            val = self.parse_expr()
            self.eat("op", ")")
            return val
        raise _FormulaError("ساختار فرمول نامعتبر است")

    def parse_args(self) -> list[Any]:
        self.eat("op", "(")
        args: list[Any] = []
        nxt = self.peek()
        if nxt and not (nxt[0] == "op" and nxt[1] == ")"):
            args.append(self.parse_expr())
            while self.peek() and self.peek()[0] == "comma":
                self.eat()
                args.append(self.parse_expr())
        self.eat("op", ")")
        return args

    def _range_values(self, code_or_val: Any) -> list[Any]:
        code = normalize_col_code(str(code_or_val))
        if code in self.code_to_key and self.row_list:
            key = self.code_to_key[code]
            return [r.get(key, "") for r in self.row_list]
        if code in self.values_by_code:
            return [self.values_by_code[code]]
        return [code_or_val]

    def parse_call(self, name: str) -> Any:
        args = self.parse_args()
        fn = name.upper()
        if fn == "ROUND":
            num = to_number(args[0] if args else 0)
            digits = int(to_number(args[1] if len(args) > 1 else 0))
            return round(num, digits)
        if fn == "ROUNDUP":
            num = to_number(args[0] if args else 0)
            digits = int(to_number(args[1] if len(args) > 1 else 0))
            factor = 10 ** digits
            return math.ceil(num * factor - 1e-12) / factor if factor else math.ceil(num)
        if fn == "ROUNDDOWN":
            num = to_number(args[0] if args else 0)
            digits = int(to_number(args[1] if len(args) > 1 else 0))
            factor = 10 ** digits
            return math.floor(num * factor + 1e-12) / factor if factor else math.floor(num)
        if fn == "ABS":
            return abs(to_number(args[0] if args else 0))
        if fn == "SUM":
            total = 0.0
            for a in args:
                for v in self._range_values(a):
                    total += to_number(v)
            return total
        if fn == "AVERAGE":
            vals = [
                to_number(v)
                for a in args
                for v in self._range_values(a)
                if v != "" and v is not None
            ]
            return (sum(vals) / len(vals)) if vals else 0
        if fn == "MIN":
            vals = [to_number(v) for a in args for v in self._range_values(a)]
            return min(vals) if vals else 0
        if fn == "MAX":
            vals = [to_number(v) for a in args for v in self._range_values(a)]
            return max(vals) if vals else 0
        if fn == "COUNT":
            return sum(
                1
                for a in args
                for v in self._range_values(a)
                if v != "" and v is not None and _NUMBER_RE.match(str(v).replace(",", ""))
            )
        if fn == "COUNTIF":
            if len(args) < 2:
                return 0
            rng = self._range_values(args[0])
            return sum(1 for v in rng if _match_criteria(v, args[1]))
        if fn == "COUNTIFS":
            if len(args) < 2 or len(args) % 2 != 0:
                return 0
            ranges = [self._range_values(args[i]) for i in range(0, len(args), 2)]
            crits = [args[i + 1] for i in range(0, len(args), 2)]
            n = min(len(r) for r in ranges) if ranges else 0
            return sum(
                1
                for i in range(n)
                if all(_match_criteria(ranges[ri][i], crits[ri]) for ri in range(len(ranges)))
            )
        if fn == "SUMIF":
            if len(args) < 2:
                return 0
            rng = self._range_values(args[0])
            sum_rng = self._range_values(args[2]) if len(args) > 2 else rng
            total = 0.0
            for i, v in enumerate(rng):
                if _match_criteria(v, args[1]):
                    total += to_number(sum_rng[i] if i < len(sum_rng) else 0)
            return total
        if fn == "SUMIFS":
            if len(args) < 3:
                return 0
            sum_rng = self._range_values(args[0])
            pairs = args[1:]
            if len(pairs) % 2 != 0:
                return 0
            ranges = [self._range_values(pairs[i]) for i in range(0, len(pairs), 2)]
            crits = [pairs[i + 1] for i in range(0, len(pairs), 2)]
            n = min([len(sum_rng)] + [len(r) for r in ranges])
            total = 0.0
            for i in range(n):
                if all(_match_criteria(ranges[ri][i], crits[ri]) for ri in range(len(ranges))):
                    total += to_number(sum_rng[i])
            return total
        if fn == "IF":
            cond = args[0] if args else False
            if isinstance(cond, str):
                truthy = cond.strip().lower() not in ("", "0", "false", "no", "خیر")
            elif isinstance(cond, (int, float)):
                truthy = cond != 0
            else:
                truthy = bool(cond)
            return (args[1] if len(args) > 1 else True) if truthy else (args[2] if len(args) > 2 else False)
        if fn == "AND":
            return all(
                (a != 0 if isinstance(a, (int, float)) else bool(a)) for a in args
            )
        if fn == "OR":
            return any(
                (a != 0 if isinstance(a, (int, float)) else bool(a)) for a in args
            )
        if fn == "NOT":
            a = args[0] if args else False
            return not (a != 0 if isinstance(a, (int, float)) else bool(a))
        raise _FormulaError(f"تابع پشتیبانی نمی‌شود: {fn}")


def evaluate_formula(
    formula: str,
    values_by_code: dict[str, Any],
    *,
    row_list: list[dict[str, Any]] | None = None,
    code_to_key: dict[str, str] | None = None,
) -> Any:
    """Evaluate a formula; returns number/str or '' on error."""
    text = str(formula or "").strip()
    if not text:
        return ""
    try:
        tokens = _tokenize(text)
        parser = _Parser(tokens, values_by_code, row_list=row_list, code_to_key=code_to_key)
        return parser.parse()
    except Exception:  # noqa: BLE001
        return ""


NUMBER_FORMAT_PRESETS: list[dict[str, str]] = [
    {"value": "General", "label": "عمومی (General)"},
    {"value": "#,##0", "label": "#,##0"},
    {"value": "#,##0.0", "label": "#,##0.0"},
    {"value": "#,##0.##", "label": "#,##0.##"},
    {"value": "#,##0.00", "label": "#,##0.00"},
    {"value": "0", "label": "0"},
    {"value": "0.00", "label": "0.00"},
    {"value": "#.##", "label": "#.##"},
    {"value": "0%", "label": "0%"},
    {"value": "0.00%", "label": "0.00%"},
]


def format_excel_number(value: Any, pattern: str) -> str:
    """Apply a simplified Excel custom number format."""
    if value is None or value == "":
        return ""
    pattern = (pattern or "General").strip() or "General"
    if pattern.lower() == "general":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    num = to_number(value, default=float("nan"))
    if math.isnan(num):
        return str(value)

    pct = "%" in pattern
    work = pattern
    if pct:
        num *= 100
        work = work.replace("%", "")

    if "." in work:
        frac = work.split(".", 1)[1]
        if "#" in frac and "0" not in frac:
            max_d = len(frac)
            text = f"{num:.{max_d}f}".rstrip("0").rstrip(".")
        else:
            decimals = sum(1 for ch in frac if ch in "0#")
            text = f"{num:.{decimals}f}"
    else:
        text = str(int(round(num)))

    if "," in work:
        if "." in text:
            whole, frac_part = text.split(".", 1)
            sign = ""
            if whole.startswith("-"):
                sign, whole = "-", whole[1:]
            whole = f"{int(whole):,}" if whole.isdigit() else whole
            text = f"{sign}{whole}.{frac_part}"
        else:
            sign = ""
            whole = text
            if whole.startswith("-"):
                sign, whole = "-", whole[1:]
            if whole.isdigit():
                text = f"{sign}{int(whole):,}"

    if pct:
        text += "%"
    return text
