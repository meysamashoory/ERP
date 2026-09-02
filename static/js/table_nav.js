/**
 * Shared keyboard + click navigation for data tables.
 * - Arrow keys move between cells/rows
 * - Selected row: blue highlight (.is-row-selected)
 * - Current cell: non-blue background (.is-cell-focus)
 * - First click selects; second click on the SAME selected row enters next level
 *   (data-href or data-drill-index / erp-row-activate)
 * - Cursor: default on unselected rows; pointer on the selected row
 */
(function () {
  function isEditableTarget(el) {
    if (!el || !el.closest) return false;
    if (el.isContentEditable) return true;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") {
      return true;
    }
    return !!el.closest(".ts-wrapper, .excel-grid-wrap, [data-editing='1'], .col-ops, a.btn, button, select");
  }

  function bodyRows(table) {
    return Array.prototype.slice.call(
      table.querySelectorAll("tbody tr")
    ).filter(function (tr) {
      if (tr.style.display === "none") return false;
      return tr.querySelectorAll("td").length > 0 && !tr.classList.contains("empty-row");
    });
  }

  function focusableCells(tr) {
    return Array.prototype.slice.call(tr.children).filter(function (td) {
      if (td.tagName !== "TD" && td.tagName !== "TH") return false;
      if (td.classList.contains("col-ops") || td.classList.contains("row-actions")) return false;
      if (td.classList.contains("excel-row-head") || td.classList.contains("excel-corner")) return false;
      return true;
    });
  }

  function rowCanActivate(tr) {
    if (!tr) return false;
    return !!(tr.getAttribute("data-href") || tr.hasAttribute("data-drill-index"));
  }

  function activateRow(tr) {
    if (!tr) return false;
    var href = tr.getAttribute("data-href");
    if (href) {
      window.location.href = href;
      return true;
    }
    if (tr.hasAttribute("data-drill-index")) {
      tr.dispatchEvent(new CustomEvent("erp-row-activate", { bubbles: true }));
      return true;
    }
    return false;
  }

  function paint(table, selRow, selCol) {
    table.querySelectorAll("tbody tr.is-row-selected").forEach(function (tr) {
      tr.classList.remove("is-row-selected");
    });
    table.querySelectorAll("td.is-cell-focus, th.is-cell-focus").forEach(function (td) {
      td.classList.remove("is-cell-focus");
    });
    var rows = bodyRows(table);
    if (!rows.length || selRow < 0 || selRow >= rows.length) return;
    var tr = rows[selRow];
    tr.classList.add("is-row-selected");
    var cells = focusableCells(tr);
    if (!cells.length) return;
    var ci = Math.max(0, Math.min(selCol, cells.length - 1));
    var cell = cells[ci];
    cell.classList.add("is-cell-focus");
    try {
      cell.scrollIntoView({ block: "nearest", inline: "nearest" });
    } catch (e) {}
  }

  function bindTable(table) {
    if (!table || table.dataset.tableNavBound === "1") return;
    if (table.classList.contains("excel-grid")) return;
    if (table.classList.contains("plan-matrix-table")) return;
    if (table.classList.contains("product-data-table")) return;
    if (table.getAttribute("data-erp-nav") === "off") return;
    // System-data accordion / hub menus are not navigable data tables
    if (table.closest(".system-accordion, .system-acc-body, .system-acc-group")) return;
    table.dataset.tableNavBound = "1";
    table.classList.add("js-table-nav");
    if (!table.hasAttribute("tabindex")) table.setAttribute("tabindex", "0");

    var selRow = -1;
    var selCol = 0;
    var rtl = (table.getAttribute("dir") || document.documentElement.getAttribute("dir") || "rtl") === "rtl";

    function selectAt(ri, ci) {
      var rows = bodyRows(table);
      if (!rows.length) return;
      selRow = Math.max(0, Math.min(ri, rows.length - 1));
      var cells = focusableCells(rows[selRow]);
      selCol = cells.length ? Math.max(0, Math.min(ci, cells.length - 1)) : 0;
      paint(table, selRow, selCol);
    }

    table.addEventListener("click", function (e) {
      if (e.target.closest(".col-ops, button, select, a, input, textarea, label")) return;
      var td = e.target.closest("td, th");
      if (!td || !table.contains(td)) return;
      var tr = td.closest("tr");
      if (!tr || !table.contains(tr)) return;
      var rows = bodyRows(table);
      var ri = rows.indexOf(tr);
      if (ri < 0) return;
      var cells = focusableCells(tr);
      var ci = cells.indexOf(td);
      if (ci < 0) ci = 0;

      // Second click on the already-selected row → enter next level
      if (ri === selRow && tr.classList.contains("is-row-selected") && rowCanActivate(tr)) {
        e.preventDefault();
        activateRow(tr);
        return;
      }

      selectAt(ri, ci);
      table.focus({ preventScroll: true });
    });

    table.addEventListener("keydown", function (e) {
      if (isEditableTarget(document.activeElement) && document.activeElement !== table) return;
      if (table.getAttribute("data-editing") === "1") return;
      var rows = bodyRows(table);
      if (!rows.length) return;
      if (selRow < 0) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectAt(0, 0);
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectAt(selRow + 1, selCol);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectAt(selRow - 1, selCol);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        selectAt(selRow, rtl ? selCol + 1 : selCol - 1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        selectAt(selRow, rtl ? selCol - 1 : selCol + 1);
      } else if (e.key === "Enter" || e.key === " ") {
        var tr = rows[selRow];
        if (!tr || !rowCanActivate(tr)) return;
        e.preventDefault();
        activateRow(tr);
      }
    });
  }

  function init(root) {
    var scope = root || document;
    // Opt-in only: scrollable list tables and explicit nav classes.
    // Do NOT bind every main table (system-data accordion menus must stay plain).
    scope.querySelectorAll(
      ".table-scroll table.table, table.table.js-table-nav, table.table-nav-cells, table.table-list-nav"
    ).forEach(bindTable);
  }

  window.ERPTableNav = { init: init, bind: bindTable, activateRow: activateRow };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(); });
  } else {
    init();
  }
})();
