/**
 * Shared keyboard navigation for data tables.
 * - Arrow keys move between cells/rows
 * - Selected row: blue highlight (.is-row-selected)
 * - Current cell: non-blue background (.is-cell-focus)
 */
(function () {
  function isEditableTarget(el) {
    if (!el || !el.closest) return false;
    if (el.isContentEditable) return true;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") {
      return true;
    }
    return !!el.closest(".ts-wrapper, .excel-grid-wrap, [data-editing='1']");
  }

  function bodyRows(table) {
    return Array.prototype.slice.call(
      table.querySelectorAll("tbody tr")
    ).filter(function (tr) {
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
    table.dataset.tableNavBound = "1";
    table.classList.add("js-table-nav");
    if (!table.hasAttribute("tabindex")) table.setAttribute("tabindex", "0");

    var selRow = 0;
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
      if (isEditableTarget(e.target) && e.target.tagName !== "TD") {
        // Still allow selecting the row when clicking plain text in cell
      }
      var td = e.target.closest("td, th");
      if (!td || !table.contains(td)) return;
      var tr = td.parentElement;
      var rows = bodyRows(table);
      var ri = rows.indexOf(tr);
      if (ri < 0) return;
      var cells = focusableCells(tr);
      var ci = cells.indexOf(td);
      if (ci < 0) ci = 0;
      selectAt(ri, ci);
      table.focus({ preventScroll: true });
    });

    table.addEventListener("keydown", function (e) {
      if (isEditableTarget(document.activeElement) && document.activeElement !== table) return;
      if (table.getAttribute("data-editing") === "1") return;
      var rows = bodyRows(table);
      if (!rows.length) return;
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
        if (!tr) return;
        var href = tr.getAttribute("data-href");
        if (href) {
          e.preventDefault();
          window.location.href = href;
        }
      }
    });

    if (bodyRows(table).length) selectAt(0, 0);
  }

  function init(root) {
    var scope = root || document;
    scope.querySelectorAll(".table-scroll table.table, table.table.js-table-nav, table.table-nav-cells, table.table-list-nav").forEach(bindTable);
    // Also common list tables not wrapped the same way
    scope.querySelectorAll("main table.table").forEach(bindTable);
  }

  window.ERPTableNav = { init: init, bind: bindTable };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(); });
  } else {
    init();
  }
})();
