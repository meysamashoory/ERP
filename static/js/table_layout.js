/* Global table row height + per-section column resize / lock. */
(function (global) {
  "use strict";

  var STORAGE_PREFIX = "erp.table.colwidths.";

  function locksFromBody() {
    try {
      var raw = document.body.getAttribute("data-table-width-locks") || "{}";
      return JSON.parse(raw) || {};
    } catch (e) {
      return {};
    }
  }

  function sectionOf(table) {
    return (
      table.getAttribute("data-table-section") ||
      (table.closest("[data-table-section]") &&
        table.closest("[data-table-section]").getAttribute("data-table-section")) ||
      ""
    );
  }

  function tableStorageKey(table) {
    var section = sectionOf(table) || "global";
    var id = table.id || table.getAttribute("data-table-id") || "anon";
    var colCount = table.tHead && table.tHead.rows[0] ? table.tHead.rows[0].cells.length : 0;
    return STORAGE_PREFIX + section + "." + id + ".c" + colCount;
  }

  function loadWidths(table) {
    try {
      var raw = localStorage.getItem(tableStorageKey(table));
      if (!raw) return null;
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : null;
    } catch (e) {
      return null;
    }
  }

  function saveWidths(table, widths) {
    try {
      localStorage.setItem(tableStorageKey(table), JSON.stringify(widths));
    } catch (e) { /* ignore quota */ }
  }

  function applyFixedWidths(table, widths) {
    var headRow = table.tHead && table.tHead.rows[0];
    if (!headRow) return;
    Array.prototype.forEach.call(headRow.cells, function (th, i) {
      var w = widths[i];
      if (!w || w <= 0) return;
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
      th.style.maxWidth = w + "px";
    });
  }

  function clearResizers(table) {
    table.querySelectorAll(".col-resizer").forEach(function (el) { el.remove(); });
    table.classList.remove("col-resize-enabled");
    table.classList.add("col-width-locked");
  }

  function enableResize(table) {
    var headRow = table.tHead && table.tHead.rows[0];
    if (!headRow || headRow.cells.length < 2) return;
    table.classList.remove("col-width-locked");
    table.classList.add("col-resize-enabled");
    Array.prototype.forEach.call(headRow.cells, function (th, idx) {
      if (idx >= headRow.cells.length - 1) return; // no handle after last col in LTR sense; RTL: after each except last
      if (th.querySelector(".col-resizer")) return;
      th.style.position = th.style.position || "relative";
      var handle = document.createElement("span");
      handle.className = "col-resizer";
      handle.title = "تغییر عرض ستون";
      handle.addEventListener("mousedown", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var startX = e.clientX;
        var startW = th.offsetWidth;
        function onMove(ev) {
          var dx = startX - ev.clientX; // RTL: drag toward start increases width
          var next = Math.max(40, Math.min(800, startW + dx));
          th.style.width = next + "px";
          th.style.minWidth = next + "px";
          th.style.maxWidth = next + "px";
        }
        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-col-resizing");
          var widths = Array.prototype.map.call(headRow.cells, function (cell) {
            return Math.round(cell.offsetWidth);
          });
          saveWidths(table, widths);
        }
        document.body.classList.add("is-col-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
      th.appendChild(handle);
    });
  }

  function enhanceTable(table) {
    if (!table || table.getAttribute("data-layout-ready") === "1") return;
    if (table.getAttribute("data-erp-nav") === "off" && table.closest(".system-acc-body")) {
      // still apply height/borders via CSS; resize ok too
    }
    table.setAttribute("data-layout-ready", "1");
    var section = sectionOf(table);
    var locks = locksFromBody();
    var locked = section ? !!locks[section] : false;

    // Report tables may carry explicit widths from display_meta
    var metaWidths = null;
    if (table.id === "report-data-table") {
      var metaEl = document.getElementById("report-display-meta");
      if (metaEl) {
        try {
          var meta = JSON.parse(metaEl.textContent || "[]") || [];
          metaWidths = meta.map(function (m) { return parseInt(m.width, 10) || 0; });
        } catch (e) {
          metaWidths = null;
        }
      }
    }
    var stored = loadWidths(table);
    if (metaWidths && metaWidths.some(function (w) { return w > 0; })) {
      applyFixedWidths(table, metaWidths);
    } else if (stored) {
      applyFixedWidths(table, stored);
    }

    if (locked) {
      clearResizers(table);
    } else {
      enableResize(table);
    }
  }

  function enhanceAll() {
    document.querySelectorAll("table.table").forEach(enhanceTable);
  }

  function boot() {
    enhanceAll();
    if (global.MutationObserver) {
      var obs = new MutationObserver(function () { enhanceAll(); });
      obs.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  global.ERPTableLayout = { enhanceAll: enhanceAll, enhanceTable: enhanceTable };
})(window);
