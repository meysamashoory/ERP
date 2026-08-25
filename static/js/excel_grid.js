/**
 * Excel-like grid for imported catalog tables.
 * - Data cells are read-only.
 * - Table name + column headers editable (header via double-click).
 * - Click row/col header to select; Delete / toolbar removes selection.
 * - Drag headers to reorder; drag edges to resize.
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

  const DEFAULT_COL_W = 120;
  const DEFAULT_ROW_H = 28;
  const ROW_HEAD_W = 48;

  const tablesData = JSON.parse(
    document.getElementById("excel-tables-data").textContent || "[]"
  );
  const byId = {};
  tablesData.forEach(function (t) {
    byId[String(t.id)] = normalizeTable(t);
  });

  function normalizeTable(t) {
    const headers = Array.isArray(t.headers) ? t.headers.map(String) : [];
    const rows = Array.isArray(t.rows)
      ? t.rows.map(function (r) {
          return Array.isArray(r) ? r.map(function (c) { return c == null ? "" : String(c); }) : [];
        })
      : [];
    const layout = t.layout && typeof t.layout === "object" ? t.layout : {};
    const colWidths = Array.isArray(layout.colWidths) ? layout.colWidths.slice() : [];
    const rowHeights = Array.isArray(layout.rowHeights) ? layout.rowHeights.slice() : [];
    while (colWidths.length < headers.length) colWidths.push(DEFAULT_COL_W);
    while (rowHeights.length < rows.length) rowHeights.push(DEFAULT_ROW_H);
    return {
      id: t.id,
      name: t.name || "",
      sheet_name: t.sheet_name || "",
      headers: headers,
      rows: rows,
      colWidths: colWidths.slice(0, headers.length),
      rowHeights: rowHeights.slice(0, rows.length),
      selection: null, // { type: "row"|"col", index: n }
    };
  }

  function stateOf(pane) {
    return byId[pane.dataset.tableId];
  }

  function ensureLayout(st) {
    while (st.colWidths.length < st.headers.length) st.colWidths.push(DEFAULT_COL_W);
    while (st.rowHeights.length < st.rows.length) st.rowHeights.push(DEFAULT_ROW_H);
    st.colWidths.length = st.headers.length;
    st.rowHeights.length = st.rows.length;
  }

  function updateDeleteBtn(pane) {
    const btn = pane.querySelector(".btn-delete-selection");
    if (!btn) return;
    const st = stateOf(pane);
    btn.disabled = !(st && st.selection);
  }

  function syncTabLabel(pane) {
    const st = stateOf(pane);
    const tab = root.querySelector('.excel-tab[data-table-id="' + pane.dataset.tableId + '"]');
    if (tab && st) tab.textContent = st.name;
  }

  function clearSelection(pane) {
    const st = stateOf(pane);
    if (st) st.selection = null;
    pane.querySelectorAll(".is-selected-row, .is-selected-col").forEach(function (el) {
      el.classList.remove("is-selected-row", "is-selected-col");
    });
    updateDeleteBtn(pane);
  }

  function applySelectionClasses(pane) {
    const st = stateOf(pane);
    pane.querySelectorAll(".is-selected-row, .is-selected-col").forEach(function (el) {
      el.classList.remove("is-selected-row", "is-selected-col");
    });
    if (!st || !st.selection) {
      updateDeleteBtn(pane);
      return;
    }
    if (st.selection.type === "row") {
      const tr = pane.querySelector('tbody tr[data-row="' + st.selection.index + '"]');
      if (tr) tr.classList.add("is-selected-row");
    } else if (st.selection.type === "col") {
      pane.querySelectorAll('[data-col="' + st.selection.index + '"]').forEach(function (el) {
        el.classList.add("is-selected-col");
      });
    }
    updateDeleteBtn(pane);
  }

  function selectRow(pane, index) {
    const st = stateOf(pane);
    st.selection = { type: "row", index: index };
    applySelectionClasses(pane);
  }

  function selectCol(pane, index) {
    const st = stateOf(pane);
    st.selection = { type: "col", index: index };
    applySelectionClasses(pane);
  }

  function deleteSelection(pane) {
    if (!canEdit) return;
    const st = stateOf(pane);
    if (!st || !st.selection) return;
    if (st.selection.type === "row") {
      const i = st.selection.index;
      if (!confirm("ردیف " + (i + 1) + " حذف شود؟")) return;
      st.rows.splice(i, 1);
      st.rowHeights.splice(i, 1);
      st.selection = null;
      renderGrid(pane);
      return;
    }
    if (st.selection.type === "col") {
      const i = st.selection.index;
      if (st.headers.length <= 1) {
        alert("حداقل یک ستون لازم است.");
        return;
      }
      if (!confirm("ستون «" + st.headers[i] + "» حذف شود؟")) return;
      st.headers.splice(i, 1);
      st.colWidths.splice(i, 1);
      st.rows = st.rows.map(function (r) {
        const next = r.slice();
        next.splice(i, 1);
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

  function moveRow(st, from, to) {
    if (from === to || from < 0 || to < 0 || from >= st.rows.length || to >= st.rows.length) return;
    const r = st.rows.splice(from, 1)[0];
    const h = st.rowHeights.splice(from, 1)[0];
    st.rows.splice(to, 0, r);
    st.rowHeights.splice(to, 0, h);
  }

  function startHeaderEdit(pane, th, ci) {
    if (!canEdit) return;
    const st = stateOf(pane);
    const label = th.querySelector(".excel-header-label");
    if (!label || th.querySelector(".excel-header-input")) return;
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "excel-header-input";
    inp.value = st.headers[ci] || "";
    label.replaceWith(inp);
    inp.focus();
    inp.select();
    function commit() {
      st.headers[ci] = inp.value.trim() || "ستون " + (ci + 1);
      renderGrid(pane);
      if (st.selection && st.selection.type === "col") selectCol(pane, ci);
    }
    inp.addEventListener("blur", commit);
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        inp.blur();
      } else if (e.key === "Escape") {
        e.preventDefault();
        renderGrid(pane);
      }
    });
  }

  function bindResizeCol(pane, handle, ci) {
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      const startX = e.clientX;
      const startW = st.colWidths[ci] || DEFAULT_COL_W;
      function onMove(ev) {
        // RTL: dragging left (decreasing clientX) should widen
        const dx = startX - ev.clientX;
        st.colWidths[ci] = Math.max(40, Math.min(800, startW + dx));
        const col = pane.querySelector('colgroup col[data-col="' + ci + '"]');
        if (col) col.style.width = st.colWidths[ci] + "px";
        pane.querySelectorAll('th[data-col="' + ci + '"], td[data-col="' + ci + '"]').forEach(function (cell) {
          cell.style.width = st.colWidths[ci] + "px";
          cell.style.minWidth = st.colWidths[ci] + "px";
        });
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function bindResizeRow(pane, handle, ri) {
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const st = stateOf(pane);
      const startY = e.clientY;
      const startH = st.rowHeights[ri] || DEFAULT_ROW_H;
      function onMove(ev) {
        const dy = ev.clientY - startY;
        st.rowHeights[ri] = Math.max(18, Math.min(200, startH + dy));
        const tr = pane.querySelector('tbody tr[data-row="' + ri + '"]');
        if (tr) tr.style.height = st.rowHeights[ri] + "px";
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function bindDragCol(pane, th, ci) {
    if (!canEdit) return;
    th.draggable = true;
    th.addEventListener("dragstart", function (e) {
      if (e.target.closest(".excel-col-resizer")) {
        e.preventDefault();
        return;
      }
      e.dataTransfer.setData("text/excel-col", String(ci));
      e.dataTransfer.effectAllowed = "move";
      th.classList.add("is-dragging");
      selectCol(pane, ci);
    });
    th.addEventListener("dragend", function () {
      th.classList.remove("is-dragging");
    });
    th.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
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
      const st = stateOf(pane);
      moveColumn(st, from, ci);
      st.selection = { type: "col", index: ci };
      renderGrid(pane);
    });
  }

  function bindDragRow(pane, rh, ri) {
    if (!canEdit) return;
    rh.draggable = true;
    rh.addEventListener("dragstart", function (e) {
      if (e.target.closest(".excel-row-resizer")) {
        e.preventDefault();
        return;
      }
      e.dataTransfer.setData("text/excel-row", String(ri));
      e.dataTransfer.effectAllowed = "move";
      rh.classList.add("is-dragging");
      selectRow(pane, ri);
    });
    rh.addEventListener("dragend", function () {
      rh.classList.remove("is-dragging");
    });
    rh.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
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
      const st = stateOf(pane);
      moveRow(st, from, ri);
      st.selection = { type: "row", index: ri };
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

    const hr = document.createElement("tr");
    const corner = document.createElement("th");
    corner.className = "excel-corner";
    corner.textContent = "";
    hr.appendChild(corner);

    st.headers.forEach(function (h, ci) {
      const th = document.createElement("th");
      th.className = "excel-col-head";
      th.dataset.col = String(ci);
      th.style.width = (st.colWidths[ci] || DEFAULT_COL_W) + "px";
      th.style.minWidth = (st.colWidths[ci] || DEFAULT_COL_W) + "px";

      const wrap = document.createElement("div");
      wrap.className = "excel-col-head-inner";
      const label = document.createElement("span");
      label.className = "excel-header-label";
      label.textContent = h;
      wrap.appendChild(label);
      th.appendChild(wrap);

      const resizer = document.createElement("span");
      resizer.className = "excel-col-resizer";
      resizer.title = "تغییر عرض ستون";
      th.appendChild(resizer);
      bindResizeCol(pane, resizer, ci);

      th.addEventListener("click", function (e) {
        if (e.target.closest(".excel-col-resizer") || e.target.closest(".excel-header-input")) return;
        selectCol(pane, ci);
      });
      th.addEventListener("dblclick", function (e) {
        if (e.target.closest(".excel-col-resizer")) return;
        e.preventDefault();
        startHeaderEdit(pane, th, ci);
      });
      bindDragCol(pane, th, ci);
      hr.appendChild(th);
    });
    thead.appendChild(hr);

    st.rows.forEach(function (row, ri) {
      const tr = document.createElement("tr");
      tr.dataset.row = String(ri);
      tr.style.height = (st.rowHeights[ri] || DEFAULT_ROW_H) + "px";

      const rh = document.createElement("th");
      rh.className = "excel-row-head";
      rh.dataset.row = String(ri);
      const num = document.createElement("span");
      num.className = "excel-row-num";
      num.textContent = String(ri + 1);
      rh.appendChild(num);
      const rowResizer = document.createElement("span");
      rowResizer.className = "excel-row-resizer";
      rowResizer.title = "تغییر ارتفاع ردیف";
      rh.appendChild(rowResizer);
      bindResizeRow(pane, rowResizer, ri);
      rh.addEventListener("click", function (e) {
        if (e.target.closest(".excel-row-resizer")) return;
        selectRow(pane, ri);
      });
      bindDragRow(pane, rh, ri);
      tr.appendChild(rh);

      st.headers.forEach(function (_, ci) {
        const td = document.createElement("td");
        td.className = "excel-data-cell";
        td.dataset.col = String(ci);
        td.dataset.row = String(ri);
        td.style.width = (st.colWidths[ci] || DEFAULT_COL_W) + "px";
        td.style.minWidth = (st.colWidths[ci] || DEFAULT_COL_W) + "px";
        td.textContent = row[ci] != null ? String(row[ci]) : "";
        td.title = td.textContent;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    applySelectionClasses(pane);
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
      if (!canEdit) return;
      if ((e.key === "Delete" || e.key === "Backspace") && stateOf(pane).selection) {
        const active = document.activeElement;
        if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
        e.preventDefault();
        deleteSelection(pane);
      }
      if (e.key === "Escape") clearSelection(pane);
    });

    pane.querySelector(".btn-add-row") &&
      pane.querySelector(".btn-add-row").addEventListener("click", function () {
        st.rows.push(st.headers.map(function () { return ""; }));
        st.rowHeights.push(DEFAULT_ROW_H);
        renderGrid(pane);
      });

    pane.querySelector(".btn-add-col") &&
      pane.querySelector(".btn-add-col").addEventListener("click", function () {
        const name = prompt("نام ستون جدید:", "ستون جدید");
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
