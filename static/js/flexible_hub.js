/**
 * Flexible hub (product data / vouchers): render dynamic columns + edit mode.
 */
(function () {
  const root = document.getElementById("flexible-hub-root");
  if (!root) return;

  const canEditPermission = root.dataset.canEditPermission === "1";
  const tab = root.dataset.tab || "";
  const saveUrl = root.dataset.saveUrl || "";
  const deleteUrl = root.dataset.deleteUrl || "";
  const csrf =
    (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
    (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
    "";

  const colsEl = document.getElementById("flexible-columns");
  const rowsEl = document.getElementById("flexible-rows");
  let columns = [];
  let rows = [];
  try {
    columns = colsEl ? JSON.parse(colsEl.textContent || "[]") : [];
  } catch (e) {
    columns = [];
  }
  try {
    rows = rowsEl ? JSON.parse(rowsEl.textContent || "[]") : [];
  } catch (e) {
    rows = [];
  }

  const table = document.getElementById("flexible-data-table");
  if (!table) return;
  const theadRow = table.querySelector("thead tr");
  const tbody = table.querySelector("tbody");
  const toggleBtn = document.getElementById("flexible-edit-toggle");
  const hint = document.getElementById("flexible-view-hint");
  const actions = root.querySelector(".product-data-actions");

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderHead() {
    let html = "";
    columns.forEach(function (c) {
      html +=
        "<th data-col=\"" +
        escapeHtml(c.key) +
        "\">" +
        escapeHtml(c.label) +
        (c.is_key ? ' <span class="muted">(کلیدی)</span>' : "") +
        "</th>";
    });
    html += '<th style="width:110px" class="col-ops">عملیات</th>';
    theadRow.innerHTML = html;
  }

  function renderBody() {
    if (!rows.length) {
      tbody.innerHTML =
        '<tr class="empty-row"><td colspan="' +
        (columns.length + 1) +
        '" class="empty">ردیفی ثبت نشده است.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    rows.forEach(function (r) {
      const tr = document.createElement("tr");
      if (r.id) tr.setAttribute("data-id", String(r.id));
      columns.forEach(function (c) {
        const td = document.createElement("td");
        const val = r[c.key] == null ? "" : String(r[c.key]);
        td.innerHTML =
          '<span class="cell-view">' +
          escapeHtml(val) +
          '</span><input class="input input-sm cell-edit" data-field="' +
          escapeHtml(c.key) +
          '" value="' +
          escapeHtml(val) +
          '">';
        tr.appendChild(td);
      });
      const ops = document.createElement("td");
      ops.className = "col-ops";
      ops.innerHTML =
        '<button type="button" class="btn btn-sm btn-danger-soft cell-edit flexible-row-delete">حذف</button>';
      tr.appendChild(ops);
      tbody.appendChild(tr);
    });
  }

  function setEditMode(on) {
    root.dataset.canEdit = on ? "1" : "0";
    table.classList.toggle("view-mode", !on);
    table.classList.toggle("edit-mode", on);
    if (actions) actions.hidden = !on;
    if (hint) {
      hint.textContent = on
        ? "حالت ویرایش — پس از تغییر، ذخیره را بزنید."
        : "حالت مشاهده — برای تغییر داده‌ها از «ویرایش» در بالای صفحه استفاده کنید.";
    }
    if (toggleBtn) toggleBtn.textContent = on ? "انصراف از ویرایش" : "ویرایش";
  }

  renderHead();
  renderBody();
  setEditMode(false);

  if (toggleBtn && canEditPermission) {
    toggleBtn.addEventListener("click", function () {
      setEditMode(root.dataset.canEdit !== "1");
    });
  }

  const addBtn = document.getElementById("flexible-add-row");
  if (addBtn) {
    addBtn.addEventListener("click", function () {
      const empty = { id: null };
      columns.forEach(function (c) {
        empty[c.key] = "";
      });
      rows.push(empty);
      renderBody();
      setEditMode(true);
    });
  }

  tbody.addEventListener("click", function (ev) {
    const btn = ev.target.closest(".flexible-row-delete");
    if (!btn) return;
    const tr = btn.closest("tr");
    if (!tr) return;
    const id = tr.getAttribute("data-id");
    if (id && deleteUrl) {
      if (!confirm("این ردیف حذف شود؟")) return;
      fetch(deleteUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ tab: tab, id: Number(id) }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) {
            alert(data.error || "حذف ناموفق بود.");
            return;
          }
          rows = rows.filter(function (r) {
            return String(r.id) !== String(id);
          });
          renderBody();
        })
        .catch(function () {
          alert("خطا در حذف ردیف.");
        });
    } else {
      const idx = Array.prototype.indexOf.call(tbody.children, tr);
      if (idx >= 0) rows.splice(idx, 1);
      renderBody();
    }
  });

  const saveBtn = document.getElementById("flexible-save-btn");
  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      const payloadRows = [];
      tbody.querySelectorAll("tr[data-id], tr:not(.empty-row)").forEach(function (tr) {
        if (tr.classList.contains("empty-row")) return;
        const item = {};
        const id = tr.getAttribute("data-id");
        if (id) item.id = Number(id);
        tr.querySelectorAll(".cell-edit[data-field]").forEach(function (inp) {
          item[inp.dataset.field] = inp.value;
        });
        payloadRows.push(item);
      });
      fetch(saveUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ tab: tab, rows: payloadRows }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) {
            alert(data.error || "ذخیره ناموفق بود.");
            return;
          }
          location.reload();
        })
        .catch(function () {
          alert("خطا در ذخیره.");
        });
    });
  }
})();
