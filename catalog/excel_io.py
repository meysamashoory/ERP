"""Read Excel/CSV workbooks into preview and import payloads."""

from __future__ import annotations

import csv
import io
from typing import Any


MAX_PREVIEW_ROWS = 5
MAX_IMPORT_ROWS = 5000
MAX_COLS = 80


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_headers(raw: list[Any], width: int) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i in range(width):
        base = _cell_str(raw[i]) if i < len(raw) else ""
        if not base:
            base = f"ستون {i + 1}"
        base = base[:120]
        n = seen.get(base, 0)
        seen[base] = n + 1
        headers.append(base if n == 0 else f"{base} ({n + 1})")
    return headers


def _rows_from_matrix(matrix: list[list[Any]]) -> tuple[list[str], list[list[str]]]:
    if not matrix:
        return [], []
    width = min(MAX_COLS, max(len(r) for r in matrix))
    if width <= 0:
        return [], []
    headers = _normalize_headers(matrix[0], width)
    rows: list[list[str]] = []
    for raw in matrix[1:MAX_IMPORT_ROWS + 1]:
        row = [_cell_str(raw[i]) if i < len(raw) else "" for i in range(width)]
        if any(row):
            rows.append(row)
    return headers, rows


def preview_workbook(uploaded_file) -> list[dict]:
    """Return sheet previews: name, headers, row_count, preview_rows."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    content = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        matrix = [list(r) for r in reader]
        headers, rows = _rows_from_matrix(matrix)
        sheet_name = (getattr(uploaded_file, "name", "") or "Sheet1").rsplit("/", 1)[-1]
        if sheet_name.lower().endswith(".csv"):
            sheet_name = sheet_name[:-4] or "Sheet1"
        return [{
            "name": sheet_name[:200] or "Sheet1",
            "headers": headers,
            "row_count": len(rows),
            "column_count": len(headers),
            "preview_rows": rows[:MAX_PREVIEW_ROWS],
        }]

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheets = []
    try:
        for ws in wb.worksheets:
            matrix: list[list[Any]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > MAX_IMPORT_ROWS:
                    break
                matrix.append(list(row) if row is not None else [])
            headers, rows = _rows_from_matrix(matrix)
            if not headers and not rows:
                # Keep empty sheets selectable but mark zero rows
                headers = []
                rows = []
            sheets.append({
                "name": str(ws.title or f"Sheet{len(sheets) + 1}")[:200],
                "headers": headers,
                "row_count": len(rows),
                "column_count": len(headers),
                "preview_rows": rows[:MAX_PREVIEW_ROWS],
            })
    finally:
        wb.close()
    return sheets


def read_sheet_data(uploaded_file, sheet_name: str) -> tuple[list[str], list[list[str]]]:
    """Return full headers+rows for one sheet by name."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    content = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        matrix = [list(r) for r in reader]
        return _rows_from_matrix(matrix)

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        target = None
        for ws in wb.worksheets:
            if str(ws.title) == sheet_name:
                target = ws
                break
        # Never fall back to sheet 1 — wrong sheet would be imported under another name.
        if target is None:
            raise ValueError(f"شیت «{sheet_name}» در فایل یافت نشد.")
        matrix = []
        for i, row in enumerate(target.iter_rows(values_only=True)):
            if i > MAX_IMPORT_ROWS:
                break
            matrix.append(list(row) if row is not None else [])
        return _rows_from_matrix(matrix)
    finally:
        wb.close()
