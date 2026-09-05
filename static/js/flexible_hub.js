/**
 * Flexible hub (product data): view-only dynamic table + keyboard nav.
 */
(function () {
  const root = document.getElementById("flexible-hub-root");
  if (!root) return;

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
        '<th data-col="' +
        escapeHtml(c.key) +
        '">' +
        escapeHtml(c.label) +
        (c.is_key ? ' <span class="muted">(کلیدی)</span>' : "") +
        "</th>";
    });
    theadRow.innerHTML = html;
  }

  function renderBody() {
    if (!rows.length) {
      tbody.innerHTML =
        '<tr class="empty-row"><td colspan="' +
        Math.max(columns.length, 1) +
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
        td.textContent = val;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function scrollToRtlStart() {
    if (window.ERPTableLayout && typeof window.ERPTableLayout.scrollTableToRtlStart === "function") {
      window.ERPTableLayout.scrollTableToRtlStart(table);
    }
  }

  renderHead();
  renderBody();
  scrollToRtlStart();
  requestAnimationFrame(function () {
    requestAnimationFrame(scrollToRtlStart);
  });

  if (window.ERPTableNav && typeof window.ERPTableNav.bind === "function") {
    delete table.dataset.tableNavBound;
    window.ERPTableNav.bind(table);
  }
})();
