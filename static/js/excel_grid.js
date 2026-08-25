/**
 * Excel-like grid for imported Excel Tables (ListObjects).
 * - Column letters A,B,C… and row numbers 1,2,3…
 * - Blue header row (سرتیتر) editable; data cells read-only
 * - Cell navigation (click + arrows), row/col select, resize, autofit, reorder
 */
(function () {
  const root = document.getElementById("excel-editor");
  if (!root) return;

  const csrf =
    (root.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
    (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
    "";
  const saveTpl = root.dataset.saveUrlTemplate;
  const deleteTpl = root.dataset.deleteUrlTemplate;
  const canEdit = root.dataset.canEdit === "1";

  const DEFAULT_COL_W = 100;
  const DEFAULT_ROW_H = 28;
  const HEADER_ROW_H = 30;
  const ROW_HEAD_W = 46;

  const tablesData = JSON.parse(
    document.getElementById("excel-tables-data").textContent || "[]"
  );
  const byId = {};

  function colLetter(index) {
    let n = index + 1;
    let s = "";
    while (n > 0) {
      n -= 1;
      s = String.fromCharCode(65 + (n % 26)) + s;
      n = Math.floor(n / 26);
    }
    return s;
  }

  function normalizeTable(t) {
    const headers = Array.isArray(t.headers) ? t.headers.map(String) : [];
    const rows = Array.isArray(t.rows)
      ? t.rows.map(function (r) {
          return Array.isArray(r)
            ? r.map(function (c) {
                return c == null ? "" : String(c);
              })
            : [];
        })
      : [];
    const layout = t.layout && typeof t.layout === "object" ? t.layout : {};
    const colWidths = Array.isArray(layout.colWidths) ? layout.colWidths.slice() : [];
    const rowHeights = Array.isArray(layout.rowHeights) ? layout.rowHeights.slice() : [];
    // rowHeights[0] = header row; then data rows
    while (colWidths.length < headers.length) colWidths.push(DEFAULT_COL_W);
    const totalRows = 1 + rows.length;
    while (rowHeights.length < totalRows) {
      rowHeights.push(rowHeights.length === 0 ? HEADER_ROW_H : DEFAULT_ROW_H);
    }
    return {
      id: t.id,
      name: t.name || "",
      sheet_name: t.sheet_name || "",
      headers: headers,
      rows: rows,
      colWidths: colWidths.slice(0, headers.length),
      rowHeights: rowHeights.slice(0, totalRows),
      selection: null, // {type:'cell'|'row'|'col', row?, col?}
      editing: false,
    };
  }

  tablesData.forEach(function (t) {
    byId[String(t.id)] = normalizeTable(t);
  });

  function stateOf(pane) {
    return byId[pane.dataset.tableId];
  }

  function ensureLayout(st) {
    while (st.colWidths.length < st.headers.length) st.colWidths.push(DEFAULT_COL_W);
    st.colWidths.length = st.headers.length;
    const total = 1 + st.rows.length;
    while (st.rowHeights.length < total) {
      st.rowHeights.push(st.rowHeights.length === 0 ? HEADER_ROW_H : DEFAULT_ROW_H);
    }
    st.rowHeights.length = total;
  }

  function updateDeleteBtn(pane) {
    const btn = pane.querySelector(".btn-delete-selection");
    if (!btn) return;
    const st = stateOf(pane);
    const sel = st && st.selection;
    btn.disabled = !(sel && (sel.type === "row" || sel.type === "col"));
  }

  function syncTabLabel(pane) {
    const st = stateOf(pane);
    const tab = root.querySelector('.excel-tab[data-table-id="' + pane.dataset.tableId + '"]');
    if (tab && st) tab.textContent = st.name;
  }

  function measureTextWidth(text) {
    const canvas = measureTextWidth._c || (measureTextWidth._c = document.createElement("canvas"));
    const ctx = canvas.getContext("2d");
    ctx.font = "13px Tahoma, Arial, sans-serif";
    return Math.ceil(ctx.measureText(String(text || "")).width) + 24;
  }

  function autofitCol(st, ci) {
    let w = measureTextWidth(st.headers[ci] || "");
    st.rows.forEach(function (r) {
      w = Math.max(w, measureTextWidth(r[ci] || ""));
    });
    st.colWidths[ci] = Math.max(40, Math.min(480, w));
  }

  function autofitRow(st, ri) {
    // single-line grid: keep modest height based on content length
    if (ri === 0) {
      st.rowHeights[0] = HEADER_ROW_H;
      return;
    }
    const row = st.rows[ri - 1] || [];
    let maxLen = 0;
    row.forEach(function (c) {
      maxLen = Math.max(maxLen, String(c || "").length);
    });
    st.rowHeights[ri] = maxLen > 40 ? 44 : DEFAULT_ROW_H;
  }

  function applySelectionClasses(pane) {
    const st = stateOf(pane);
    pane.querySelectorAll(".is-selected-row, .is-selected-col, .is-cell-focus").forEach(function (el) {
      el.classList.remove("is-selected-row", "is-selected-col", "is-cell-focus");
    });
    if (!st || !st.selection) {
      updateDeleteBtn(pane);
      return;
    }
    const sel = st.selection;
    if (sel.type === "row") {
      const tr = pane.querySelector('tr[data-grid-row="' + sel.row + '"]');
      if (tr) tr.classList.add("is-selected-row");
    } else if (sel.type === "col") {
      pane.querySelectorAll('[data-col="' + sel.col + '"]').forEach(function (el) {
        el.classList.add("is-selected-col");
      });
    } else if (sel.type === "cell") {
      const td = pane.querySelector(
        'td[data-grid-row="' + sel.row + '"][data-col="' + sel.col + '"]'
      );
      if (td) {
        td.classList.add("is-cell-focus");
        td.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    }
    updateDeleteBtn(pane);
  }

  function setSelection(pane, sel) {
    const st = stateOf(pane);
    if (st.editing) return;
    st.selection = sel;
    applySelectionClasses(pane);
    pane.querySelector(".excel-grid-wrap").focus();
  }

  function deleteSelection(pane) {
    if (!canEdit) return;
    const st = stateOf(pane);
    if (!st || !st.selection) return;
    if (st.selection.type === "row") {
      const ri = st.selection.row;
      if (ri === 0) {
        alert("ردیف سرتیتر را نمی‌توان حذف کرد.");
        return;
      }
      if (!confirm("ردیف " + (ri + 1) + " حذف شود؟")) return;
      st.rows.splice(ri - 1, 1);
      st.rowHeights.splice(ri, 1);
      st.selection = null;
      renderGrid(pane);
      return;
    }
    if (st.selection.type === "col") {
      const ci = st.selection.col;
      if (st.headers.length <= 1) {
        alert("حداقل یک ستون لازم است.");
        return;
      }
      if (!confirm("ستون " + colLetter(ci) + " حذف شود؟")) return;
      st.headers.splice(ci, 1);
      st.colWidths.splice(ci, 1);
      st.rows = st.rows.map(function (r) {
        const next = r.slice();
        next.splice(ci, 1);
        return next;
      });
      st.selection = null;
      renderGrid(pane);
    }
  }

  function moveColumn(st, from, to) {
    if (from === to || from < 0 || to < 0 || from >= st.headers.length || to >= st.headers.length) return;
    const h = st.headers.splice(from, 1)[0];
    const w = st.colWidths.splice(from, 1)[0];
    st.headers.splice(to, 0, h);
    st.colWidths.splice(to, 0, w);
    st.rows = st.rows.map(function (r) {
      const next = r.slice();
      while (next.length < st.headers.length) next.push("");
      const cell = next.splice(from, 1)[0];
      next.splice(to, 0, cell);
      return next;
    });
  }

  function moveDataRow(st, fromGrid, toGrid) {
    // grid rows: 0=header, 1..=data → data index = grid-1
    if (fromGrid < 1 || toGrid < 1) return;
    const from = fromGrid - 1;
    const to = toGrid - 1;
    if (from === to || from >= st.rows.length || to >= st.rows.length) return;
    const r = st.rows.splice(from, 1)[0];
    const h = st.rowHeights.splice(fromGrid, 1)[0];
    st.rows.splice(to, 0, r);
    st.rowHeights.splice(toGrid, 0, h);
  }

  function startHeaderEdit(pane, td, ci) {
    if (!canEdit || td.querySelector("input")) return;
    const st = stateOf(pane);
    st.editing = true;
    const width = st.colWidths[ci] || DEFAULT_COL_W;
    const text = st.headers[ci] || "";
    const label = td.querySelector(".excel-header-label");
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "excel-header-input";
    inp.value = text;
    inp.style.width = width - 4 + "px";
    inp.style.maxWidth = width - 4 + "px";
    inp.style.boxSizing = "border-box";
    if (label) label.replaceWith(inp);
    else {
      td.textContent = "";
      td.appendChild(inp);
    }
    inp.focus();
    inp.select();

    function finish(commit) {
      if (!st.editing) return;
      st.editing = false;
      if (commit) {
        st.headers[ci] = inp.value.trim() || "ستون " + (ci + 1);
      }
      // keep column width unchanged
      renderGrid(pane);
      setSelection(pane, { type: "cell", row: 0, col: ci });
    }

    inp.addEventListener("keydown", function (e) {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        finish(true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        finish(false);
      } else if (e.key === "Tab") {
        e.preventDefault();
        finish(true);
        const next = e.shiftKey ? ci - 1 : ci + 1;
        if (next >= 0 && next < st.headers.length) {
          setSelection(pane, { type: "cell", row: 0, col: next });
          const nextTd = pane.querySelector('td[data-grid-row="0"][data-col="' + next + '"]');
          if (nextTd) startHeaderEdit(pane, nextTd, next);
        }
      }
    });
    inp.addEventListener("blur", function () {
      finish(true);
    });
    inp.addEventListener("mousedown", function (e) {
      e.stopPropagation();
    });
    inp.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  function bindColResize(pane, handle, ci) {
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      const startX = e.clientX;
      const startW = st.colWidths[ci] || DEFAULT_COL_W;
      document.body.classList.add("excel-resizing-col");
      function onMove(ev) {
        // Grid is LTR: dragging handle right increases width
        const dx = ev.clientX - startX;
        st.colWidths[ci] = Math.max(40, Math.min(800, startW + dx));
        const w = st.colWidths[ci] + "px";
        const col = pane.querySelector('colgroup col[data-col="' + ci + '"]');
        if (col) col.style.width = w;
        pane.querySelectorAll('[data-col="' + ci + '"]').forEach(function (cell) {
          if (cell.tagName === "COL") return;
          cell.style.width = w;
          cell.style.minWidth = w;
          cell.style.maxWidth = w;
        });
      }
      function onUp() {
        document.body.classList.remove("excel-resizing-col");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
    handle.addEventListener("dblclick", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      autofitCol(st, ci);
      renderGrid(pane);
    });
  }

  function bindRowResize(pane, handle, ri) {
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      const startY = e.clientY;
      const startH = st.rowHeights[ri] || DEFAULT_ROW_H;
      document.body.classList.add("excel-resizing-row");
      function onMove(ev) {
        st.rowHeights[ri] = Math.max(18, Math.min(200, startH + (ev.clientY - startY)));
        const tr = pane.querySelector('tr[data-grid-row="' + ri + '"]');
        if (tr) tr.style.height = st.rowHeights[ri] + "px";
      }
      function onUp() {
        document.body.classList.remove("excel-resizing-row");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
    handle.addEventListener("dblclick", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      autofitRow(st, ri);
      renderGrid(pane);
    });
  }

  function renderGrid(pane) {
    const st = stateOf(pane);
    ensureLayout(st);
    const table = pane.querySelector(".excel-grid");
    const colgroup = table.querySelector("colgroup");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    colgroup.innerHTML = "";
    thead.innerHTML = "";
    tbody.innerHTML = "";

    const colCorner = document.createElement("col");
    colCorner.style.width = ROW_HEAD_W + "px";
    colgroup.appendChild(colCorner);
    st.headers.forEach(function (_, ci) {
      const col = document.createElement("col");
      col.dataset.col = String(ci);
      col.style.width = (st.colWidths[ci] || DEFAULT_COL_W) + "px";
      colgroup.appendChild(col);
    });

    // Letter header row (A B C …) — not editable
    const letterRow = document.createElement("tr");
    letterRow.className = "excel-letter-row";
    const corner = document.createElement("th");
    corner.className = "excel-corner";
    letterRow.appendChild(corner);
    st.headers.forEach(function (_, ci) {
      const th = document.createElement("th");
      th.className = "excel-col-letter";
      th.dataset.col = String(ci);
      const w = st.colWidths[ci] || DEFAULT_COL_W;
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
      th.style.maxWidth = w + "px";
      th.textContent = colLetter(ci);

      const resizer = document.createElement("span");
      resizer.className = "excel-col-resizer";
      resizer.title = "تغییر عرض / دوبار کلیک = اندازه متن";
      th.appendChild(resizer);
      bindColResize(pane, resizer, ci);

      th.addEventListener("click", function (e) {
        if (e.target.closest(".excel-col-resizer")) return;
        setSelection(pane, { type: "col", col: ci });
      });

      if (canEdit) {
        th.draggable = true;
        th.addEventListener("dragstart", function (e) {
          if (e.target.closest(".excel-col-resizer")) {
            e.preventDefault();
            return;
          }
          e.dataTransfer.setData("text/excel-col", String(ci));
          e.dataTransfer.effectAllowed = "move";
        });
        th.addEventListener("dragover", function (e) {
          e.preventDefault();
          th.classList.add("is-drop-target");
        });
        th.addEventListener("dragleave", function () {
          th.classList.remove("is-drop-target");
        });
        th.addEventListener("drop", function (e) {
          e.preventDefault();
          th.classList.remove("is-drop-target");
          const from = parseInt(e.dataTransfer.getData("text/excel-col"), 10);
          if (Number.isNaN(from)) return;
          moveColumn(st, from, ci);
          renderGrid(pane);
          setSelection(pane, { type: "col", col: ci });
        });
      }
      letterRow.appendChild(th);
    });
    thead.appendChild(letterRow);

    function addRowResizer(rh, ri) {
      const rowResizer = document.createElement("span");
      rowResizer.className = "excel-row-resizer";
      rowResizer.title = "تغییر ارتفاع / دوبار کلیک = اندازه متن";
      rh.appendChild(rowResizer);
      bindRowResize(pane, rowResizer, ri);
    }

    // Header (سرتیتر) as grid row 0 — blue
    const headerTr = document.createElement("tr");
    headerTr.className = "excel-title-row";
    headerTr.dataset.gridRow = "0";
    headerTr.style.height = (st.rowHeights[0] || HEADER_ROW_H) + "px";
    const headerRh = document.createElement("th");
    headerRh.className = "excel-row-head";
    headerRh.dataset.gridRow = "0";
    headerRh.textContent = "1";
    addRowResizer(headerRh, 0);
    headerRh.addEventListener("click", function (e) {
      if (e.target.closest(".excel-row-resizer")) return;
      setSelection(pane, { type: "row", row: 0 });
    });
    headerTr.appendChild(headerRh);

    st.headers.forEach(function (h, ci) {
      const td = document.createElement("td");
      td.className = "excel-title-cell";
      td.dataset.col = String(ci);
      td.dataset.gridRow = "0";
      const w = st.colWidths[ci] || DEFAULT_COL_W;
      td.style.width = w + "px";
      td.style.minWidth = w + "px";
      td.style.maxWidth = w + "px";
      const span = document.createElement("span");
      span.className = "excel-header-label";
      span.textContent = h;
      td.appendChild(span);

      td.addEventListener("click", function (e) {
        if (st.editing) return;
        const already =
          st.selection &&
          st.selection.type === "cell" &&
          st.selection.row === 0 &&
          st.selection.col === ci;
        if (already && canEdit) {
          e.preventDefault();
          startHeaderEdit(pane, td, ci);
          return;
        }
        setSelection(pane, { type: "cell", row: 0, col: ci });
      });
      headerTr.appendChild(td);
    });
    tbody.appendChild(headerTr);

    // Data rows — grid row 1..n → display number 2..n+1
    st.rows.forEach(function (row, di) {
      const ri = di + 1;
      const tr = document.createElement("tr");
      tr.dataset.gridRow = String(ri);
      tr.style.height = (st.rowHeights[ri] || DEFAULT_ROW_H) + "px";

      const rh = document.createElement("th");
      rh.className = "excel-row-head";
      rh.dataset.gridRow = String(ri);
      rh.textContent = String(ri + 1);
      addRowResizer(rh, ri);
      rh.addEventListener("click", function (e) {
        if (e.target.closest(".excel-row-resizer")) return;
        setSelection(pane, { type: "row", row: ri });
      });
      if (canEdit) {
        rh.draggable = true;
        rh.addEventListener("dragstart", function (e) {
          if (e.target.closest(".excel-row-resizer")) {
            e.preventDefault();
            return;
          }
          e.dataTransfer.setData("text/excel-row", String(ri));
        });
        rh.addEventListener("dragover", function (e) {
          e.preventDefault();
          rh.classList.add("is-drop-target");
        });
        rh.addEventListener("dragleave", function () {
          rh.classList.remove("is-drop-target");
        });
        rh.addEventListener("drop", function (e) {
          e.preventDefault();
          rh.classList.remove("is-drop-target");
          const from = parseInt(e.dataTransfer.getData("text/excel-row"), 10);
          if (Number.isNaN(from)) return;
          moveDataRow(st, from, ri);
          renderGrid(pane);
          setSelection(pane, { type: "row", row: ri });
        });
      }
      tr.appendChild(rh);

      st.headers.forEach(function (_, ci) {
        const td = document.createElement("td");
        td.className = "excel-data-cell";
        td.dataset.col = String(ci);
        td.dataset.gridRow = String(ri);
        const w = st.colWidths[ci] || DEFAULT_COL_W;
        td.style.width = w + "px";
        td.style.minWidth = w + "px";
        td.style.maxWidth = w + "px";
        td.textContent = row[ci] != null ? String(row[ci]) : "";
        td.title = td.textContent;
        td.addEventListener("click", function () {
          setSelection(pane, { type: "cell", row: ri, col: ci });
        });
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    applySelectionClasses(pane);
  }

  function navigate(pane, dRow, dCol) {
    const st = stateOf(pane);
    if (!st.selection || st.selection.type !== "cell" || st.editing) return;
    const maxR = st.rows.length; // 0..rows.length
    const maxC = st.headers.length - 1;
    let r = st.selection.row + dRow;
    let c = st.selection.col + dCol;
    r = Math.max(0, Math.min(maxR, r));
    c = Math.max(0, Math.min(maxC, c));
    setSelection(pane, { type: "cell", row: r, col: c });
  }

  root.querySelectorAll(".excel-pane").forEach(function (pane) {
    const st = stateOf(pane);
    const nameInput = pane.querySelector(".excel-table-name-edit");
    if (nameInput) {
      nameInput.addEventListener("change", function () {
        const name = nameInput.value.trim();
        if (!name) {
          nameInput.value = st.name;
          return;
        }
        st.name = name;
        syncTabLabel(pane);
      });
    }

    renderGrid(pane);

    const wrap = pane.querySelector(".excel-grid-wrap");
    wrap.addEventListener("keydown", function (e) {
      if (st.editing) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (st.selection && st.selection.type === "cell") navigate(pane, 1, 0);
        else setSelection(pane, { type: "cell", row: 0, col: 0 });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        navigate(pane, -1, 0);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigate(pane, 0, -1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        navigate(pane, 0, 1);
      } else if (e.key === "F2" || (e.key === "Enter" && st.selection && st.selection.type === "cell" && st.selection.row === 0)) {
        if (!canEdit) return;
        e.preventDefault();
        const sel = st.selection;
        if (sel && sel.type === "cell" && sel.row === 0) {
          const td = pane.querySelector('td[data-grid-row="0"][data-col="' + sel.col + '"]');
          if (td) startHeaderEdit(pane, td, sel.col);
        }
      } else if ((e.key === "Delete" || e.key === "Backspace") && st.selection && (st.selection.type === "row" || st.selection.type === "col")) {
        const active = document.activeElement;
        if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
        e.preventDefault();
        deleteSelection(pane);
      } else if (e.key === "Escape") {
        st.selection = null;
        applySelectionClasses(pane);
      }
    });

    pane.querySelector(".btn-add-row") &&
      pane.querySelector(".btn-add-row").addEventListener("click", function () {
        st.rows.push(st.headers.map(function () { return ""; }));
        st.rowHeights.push(DEFAULT_ROW_H);
        renderGrid(pane);
      });

    pane.querySelector(".btn-add-col") &&
      pane.querySelector(".btn-add-col").addEventListener("click", function () {
        const name = prompt("نام سرتیتر ستون جدید:", "ستون جدید");
        if (name == null) return;
        st.headers.push(String(name).trim() || "ستون جدید");
        st.colWidths.push(DEFAULT_COL_W);
        st.rows = st.rows.map(function (r) {
          const next = r.slice();
          next.push("");
          return next;
        });
        renderGrid(pane);
      });

    pane.querySelector(".btn-delete-selection") &&
      pane.querySelector(".btn-delete-selection").addEventListener("click", function () {
        deleteSelection(pane);
      });

    pane.querySelector(".btn-save-table") &&
      pane.querySelector(".btn-save-table").addEventListener("click", async function () {
        const status = pane.querySelector(".excel-save-status");
        if (nameInput) {
          const name = nameInput.value.trim();
          if (name) st.name = name;
        }
        const id = pane.dataset.tableId;
        const url = saveTpl.replace("/0/", "/" + id + "/");
        status.textContent = "در حال ذخیره…";
        try {
          const res = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrf,
            },
            body: JSON.stringify({
              name: st.name,
              headers: st.headers,
              rows: st.rows,
              layout: { colWidths: st.colWidths, rowHeights: st.rowHeights },
            }),
            credentials: "same-origin",
          });
          const data = await res.json();
          if (!res.ok || !data.ok) throw new Error(data.error || "خطا");
          status.textContent = "ذخیره شد.";
          syncTabLabel(pane);
          setTimeout(function () {
            status.textContent = "";
          }, 2500);
        } catch (err) {
          status.textContent = err.message || "ذخیره ناموفق";
        }
      });

    pane.querySelector(".btn-delete-table") &&
      pane.querySelector(".btn-delete-table").addEventListener("click", function () {
        if (!confirm("این جدول برای همیشه حذف شود؟")) return;
        const id = pane.dataset.tableId;
        const url = deleteTpl.replace("/0/", "/" + id + "/");
        const form = document.createElement("form");
        form.method = "post";
        form.action = url;
        const token = document.createElement("input");
        token.type = "hidden";
        token.name = "csrfmiddlewaretoken";
        token.value = csrf;
        form.appendChild(token);
        document.body.appendChild(form);
        form.submit();
      });
  });

  root.querySelectorAll(".excel-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      const id = tab.dataset.tableId;
      root.querySelectorAll(".excel-tab").forEach(function (t) {
        const on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      root.querySelectorAll(".excel-pane").forEach(function (p) {
        const on = p.dataset.tableId === id;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
      });
    });
  });
})();
