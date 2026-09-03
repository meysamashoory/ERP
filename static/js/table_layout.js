/* Global table row height + per-section column resize / lock.
 * Fit-width from RTL start: table grows/shrinks with column widths.
 * Click clipped cells to slowly reveal full text. */
(function (global) {
  "use strict";

  var STORAGE_PREFIX = "erp.table.colwidths.";
  var MIN_COL = 40;
  var MAX_COL = 800;
  var activeReveal = null;

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

  function headCells(table) {
    var headRow = table.tHead && table.tHead.rows[0];
    if (!headRow) return [];
    return Array.prototype.slice.call(headRow.cells);
  }

  function measureCurrentWidths(table) {
    return headCells(table).map(function (cell) {
      return Math.max(MIN_COL, Math.round(cell.getBoundingClientRect().width));
    });
  }

  function applyFitWidth(table, widths) {
    var total = 0;
    var i;
    for (i = 0; i < widths.length; i++) {
      total += widths[i] > 0 ? widths[i] : 0;
    }
    if (total <= 0) return;
    table.classList.add("table-fit-width");
    table.style.tableLayout = "fixed";
    table.style.width = total + "px";
    table.style.minWidth = total + "px";
    table.style.maxWidth = "none";
    table.style.marginInlineStart = "0";
    table.style.marginInlineEnd = "auto";
  }

  function applyFixedWidths(table, widths) {
    var cells = headCells(table);
    if (!cells.length) return;
    cells.forEach(function (th, i) {
      var w = widths[i];
      if (!w || w <= 0) return;
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
      th.style.maxWidth = w + "px";
    });
    applyFitWidth(table, widths);
  }

  function lockAllColumnWidths(table) {
    var widths = measureCurrentWidths(table);
    applyFixedWidths(table, widths);
    return widths;
  }

  function clearResizers(table) {
    table.querySelectorAll(".col-resizer").forEach(function (el) { el.remove(); });
    table.classList.remove("col-resize-enabled");
    table.classList.add("col-width-locked");
  }

  function enableResize(table) {
    var cells = headCells(table);
    if (cells.length < 2) return;
    table.classList.remove("col-width-locked");
    table.classList.add("col-resize-enabled");

    // Baseline: lock every column so resize changes table size, not redistribution.
    if (!loadWidths(table) || !table.style.width || table.style.width === "100%") {
      lockAllColumnWidths(table);
    }

    cells.forEach(function (th, idx) {
      if (idx >= cells.length - 1) return;
      if (th.querySelector(".col-resizer")) return;
      if (!th.style.position || th.style.position === "static") {
        th.style.position = "relative";
      }
      var handle = document.createElement("span");
      handle.className = "col-resizer";
      handle.title = "تغییر عرض ستون";
      handle.addEventListener("mousedown", function (e) {
        e.preventDefault();
        e.stopPropagation();
        stopReveal();

        var widths = lockAllColumnWidths(table);
        var startX = e.clientX;
        var startW = widths[idx];

        function onMove(ev) {
          var dx = startX - ev.clientX; // RTL: drag toward start increases width
          var next = Math.max(MIN_COL, Math.min(MAX_COL, startW + dx));
          widths[idx] = Math.round(next);
          th.style.width = next + "px";
          th.style.minWidth = next + "px";
          th.style.maxWidth = next + "px";
          applyFitWidth(table, widths);
        }

        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-col-resizing");
          var finalWidths = measureCurrentWidths(table);
          applyFixedWidths(table, finalWidths);
          saveWidths(table, finalWidths);
        }

        document.body.classList.add("is-col-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
      th.appendChild(handle);
    });
  }

  function isInteractiveTarget(el) {
    return !!(
      el.closest &&
      el.closest(
        "a, button, input, select, textarea, label, .col-resizer, .admin-col-resizer, .cell-no-reveal"
      )
    );
  }

  function cellHasOwnControls(cell) {
    return !!cell.querySelector(
      "a, button, input, select, textarea, .col-resizer, .admin-col-resizer"
    );
  }

  function ensureRevealTrack(cell) {
    var existing = cell.querySelector(":scope > .cell-reveal-track");
    if (existing) return existing;
    if (cellHasOwnControls(cell)) return null;

    var track = document.createElement("span");
    track.className = "cell-reveal-track";
    while (cell.firstChild) {
      track.appendChild(cell.firstChild);
    }
    cell.appendChild(track);
    return track;
  }

  function stopReveal() {
    if (!activeReveal) return;
    var track = activeReveal.track;
    var timer = activeReveal.timer;
    if (timer) clearTimeout(timer);
    if (track) {
      track.style.transition = "transform 0.35s ease";
      track.style.transform = "translate(0, 0)";
      track.classList.remove("is-revealing");
    }
    activeReveal = null;
  }

  function playCellReveal(cell) {
    if (!cell || (cell.tagName !== "TD" && cell.tagName !== "TH")) return;
    if (cellHasOwnControls(cell)) return;

    var track = ensureRevealTrack(cell);
    if (!track) return;

    // Measure true overflow: prefer single-line horizontal reveal (RTL),
    // then vertical if row height still clips wrapped text.
    track.classList.add("is-revealing");
    track.style.whiteSpace = "nowrap";
    track.style.width = "max-content";
    track.style.maxWidth = "none";
    track.style.transform = "translate(0, 0)";
    track.style.transition = "none";
    void track.offsetWidth;

    var overflowX = Math.max(0, Math.ceil(track.scrollWidth - cell.clientWidth + 4));
    var overflowY = 0;
    if (overflowX <= 1) {
      track.style.whiteSpace = "normal";
      track.style.width = cell.clientWidth + "px";
      void track.offsetWidth;
      overflowY = Math.max(0, Math.ceil(track.scrollHeight - cell.clientHeight + 2));
      track.style.width = "max-content";
    }
    if (overflowX <= 1 && overflowY <= 1) {
      track.classList.remove("is-revealing");
      track.style.whiteSpace = "";
      track.style.width = "";
      track.style.maxWidth = "";
      return;
    }

    stopReveal();
    track.classList.add("is-revealing");
    if (overflowX > 1) {
      track.style.whiteSpace = "nowrap";
    }

    // RTL: clipped text sits toward the left; move content right (+) to reveal.
    var tx = overflowX > 1 ? overflowX : 0;
    var ty = overflowY > 1 ? -overflowY : 0;
    var distance = Math.abs(tx) + Math.abs(ty);
    var duration = Math.max(1400, Math.min(6000, distance * 28));

    track.style.transition = "none";
    track.style.transform = "translate(0, 0)";
    void track.offsetWidth;
    track.style.transition = "transform " + duration + "ms linear";
    track.style.transform = "translate(" + tx + "px, " + ty + "px)";

    var timer = setTimeout(function () {
      track.style.transition = "transform 0.45s ease";
      track.style.transform = "translate(0, 0)";
      var resetTimer = setTimeout(function () {
        track.classList.remove("is-revealing");
        track.style.whiteSpace = "";
        track.style.width = "";
        track.style.maxWidth = "";
        if (activeReveal && activeReveal.track === track) activeReveal = null;
      }, 480);
      if (activeReveal && activeReveal.track === track) {
        activeReveal.timer = resetTimer;
      }
    }, duration + 280);

    activeReveal = { track: track, timer: timer, cell: cell };
  }

  function bindReveal(table) {
    if (table.getAttribute("data-reveal-bound") === "1") return;
    table.setAttribute("data-reveal-bound", "1");
    table.addEventListener("click", function (e) {
      if (document.body.classList.contains("is-col-resizing")) return;
      if (isInteractiveTarget(e.target)) return;
      var cell = e.target.closest("td, th");
      if (!cell || !table.contains(cell)) return;
      if (cell.querySelector(".col-resizer") && e.target.classList.contains("col-resizer")) return;
      playCellReveal(cell);
    });
  }

  function enhanceTable(table) {
    if (!table || table.getAttribute("data-layout-ready") === "1") return;
    table.setAttribute("data-layout-ready", "1");
    var section = sectionOf(table);
    var locks = locksFromBody();
    var locked = section ? !!locks[section] : false;

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
    } else {
      // First visit: measure natural widths then fit to content from RTL start.
      requestAnimationFrame(function () {
        lockAllColumnWidths(table);
      });
    }

    if (locked) {
      clearResizers(table);
    } else {
      enableResize(table);
    }
    bindReveal(table);
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

  global.ERPTableLayout = {
    enhanceAll: enhanceAll,
    enhanceTable: enhanceTable,
    stopReveal: stopReveal,
  };
})(window);
