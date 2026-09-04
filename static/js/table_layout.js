/* Global table row height + per-section column resize / lock.
 * Fit-width from RTL start: table grows/shrinks with column widths.
 * Clipped cells: constant-speed seamless marquee while selected. */
(function (global) {
  "use strict";

  var STORAGE_PREFIX = "erp.table.colwidths.";
  var MIN_COL = 40;
  var MAX_COL = 800;
  /** Constant marquee speed (px/s) — independent of text length. */
  var REVEAL_SPEED_PX_PER_SEC = 52;
  var REVEAL_GAP_EM = 3;
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
    } catch (e) {}
  }

  function headCells(table) {
    if (!table.tHead || !table.tHead.rows.length) return [];
    return Array.prototype.slice.call(table.tHead.rows[0].cells);
  }

  function measureCurrentWidths(table) {
    return headCells(table).map(function (th) {
      return Math.max(MIN_COL, Math.round(th.getBoundingClientRect().width));
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

    if (!loadWidths(table) || !table.style.width || table.style.width === "100%") {
      lockAllColumnWidths(table);
    }

    cells.forEach(function (th, idx) {
      if (th.querySelector(".col-resizer")) return;
      var inScroll = !!(th.closest && th.closest(".table-scroll, .table-scroll-wide"));
      if (inScroll) {
        th.style.position = "sticky";
        th.style.top = "0";
        if (!th.style.zIndex) th.style.zIndex = "6";
      } else if (!th.style.position || th.style.position === "static") {
        th.style.position = "relative";
      }
      var handle = document.createElement("span");
      handle.className = "col-resizer";
      if (idx >= cells.length - 1) {
        handle.className = "col-resizer col-resizer-edge";
        handle.title = "تغییر عرض ستون (لبه چپ جدول)";
      } else {
        handle.title = "تغییر عرض ستون";
      }
      handle.addEventListener("mousedown", function (e) {
        e.preventDefault();
        e.stopPropagation();
        stopReveal();

        var widths = lockAllColumnWidths(table);
        var startX = e.clientX;
        var startW = widths[idx];

        function onMove(ev) {
          var dx = startX - ev.clientX;
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

  function teardownMarqueeDom(track) {
    if (!track) return;
    var inner = track.querySelector(":scope > .cell-reveal-inner");
    if (!inner) {
      track.style.transform = "";
      track.style.transition = "";
      track.style.width = "";
      track.style.maxWidth = "";
      track.style.whiteSpace = "";
      track.classList.remove("is-revealing");
      return;
    }
    var seg = inner.querySelector(".cell-reveal-seg");
    track.style.transform = "";
    track.style.transition = "";
    track.style.width = "";
    track.style.maxWidth = "";
    track.style.whiteSpace = "";
    track.classList.remove("is-revealing");
    while (track.firstChild) track.removeChild(track.firstChild);
    if (seg) {
      while (seg.firstChild) track.appendChild(seg.firstChild);
    }
  }

  function buildMarqueeDom(track) {
    teardownMarqueeDom(track);
    var frag = document.createDocumentFragment();
    while (track.firstChild) frag.appendChild(track.firstChild);

    var inner = document.createElement("span");
    inner.className = "cell-reveal-inner";
    var seg1 = document.createElement("span");
    seg1.className = "cell-reveal-seg";
    seg1.appendChild(frag);
    var gap = document.createElement("span");
    gap.className = "cell-reveal-gap";
    gap.style.width = REVEAL_GAP_EM + "em";
    gap.setAttribute("aria-hidden", "true");
    var seg2 = seg1.cloneNode(true);
    seg2.setAttribute("aria-hidden", "true");
    inner.appendChild(seg1);
    inner.appendChild(gap);
    inner.appendChild(seg2);
    track.appendChild(inner);
    return { inner: inner, seg: seg1, gap: gap };
  }

  function selectionGuarded(cell) {
    var table = cell && cell.closest("table");
    if (!table) return false;
    if (table.getAttribute("data-erp-nav") === "off") return false;
    return (
      table.classList.contains("js-table-nav") ||
      table.getAttribute("data-table-nav-bound") === "1" ||
      table.dataset.tableNavBound === "1"
    );
  }

  function cellStillSelected(cell) {
    if (!cell || !cell.isConnected) return false;
    if (!selectionGuarded(cell)) return true;
    return cell.classList.contains("is-cell-focus");
  }

  function stopReveal() {
    if (!activeReveal) return;
    if (activeReveal.raf) cancelAnimationFrame(activeReveal.raf);
    if (activeReveal.timer) clearTimeout(activeReveal.timer);
    teardownMarqueeDom(activeReveal.track);
    activeReveal = null;
  }

  function playCellReveal(cell) {
    if (!cell || (cell.tagName !== "TD" && cell.tagName !== "TH")) return;
    if (cellHasOwnControls(cell)) return;

    if (activeReveal && activeReveal.cell === cell && activeReveal.running) {
      return;
    }

    var track = ensureRevealTrack(cell);
    if (!track) return;

    // Measure horizontal overflow only — never wrap (row height must stay fixed).
    track.classList.add("is-revealing");
    track.style.whiteSpace = "nowrap";
    track.style.width = "max-content";
    track.style.maxWidth = "none";
    track.style.transform = "translate(0, 0)";
    track.style.transition = "none";
    void track.offsetWidth;

    var overflowX = Math.max(0, Math.ceil(track.scrollWidth - cell.clientWidth + 2));
    if (overflowX <= 1) {
      track.classList.remove("is-revealing");
      track.style.whiteSpace = "";
      track.style.width = "";
      track.style.maxWidth = "";
      return;
    }

    stopReveal();
    track = ensureRevealTrack(cell);
    if (!track) return;

    var parts = buildMarqueeDom(track);
    track.classList.add("is-revealing");
    track.style.whiteSpace = "nowrap";
    track.style.width = "max-content";
    track.style.maxWidth = "none";
    track.style.transition = "none";
    void track.offsetWidth;

    var loopWidth = Math.max(1, Math.ceil(parts.seg.offsetWidth + parts.gap.offsetWidth));
    var startTs = null;
    // RTL tables: positive X reveals clipped content on the left.
    var dir = 1;

    function frame(ts) {
      if (!activeReveal || activeReveal.track !== track) return;
      if (!cellStillSelected(cell)) {
        stopReveal();
        return;
      }
      if (startTs == null) startTs = ts;
      var elapsed = (ts - startTs) / 1000;
      var dist = (elapsed * REVEAL_SPEED_PX_PER_SEC) % loopWidth;
      track.style.transform = "translate(" + dir * dist + "px, 0)";
      activeReveal.raf = requestAnimationFrame(frame);
    }

    activeReveal = {
      track: track,
      cell: cell,
      raf: null,
      timer: null,
      running: true,
      loopWidth: loopWidth,
    };
    activeReveal.raf = requestAnimationFrame(frame);
  }

  function onCellSelected(cell) {
    if (!cell) {
      stopReveal();
      return;
    }
    playCellReveal(cell);
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
    document
      .querySelectorAll(
        'table.table[data-table-section="reports"], [data-table-section="reports"] table.table'
      )
      .forEach(enhanceTable);
    // Marquee reveal for all scrollable data tables (height stays locked via CSS).
    document
      .querySelectorAll(".table-scroll table.table, .table-scroll-wide table.table")
      .forEach(bindReveal);
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
    playCellReveal: playCellReveal,
    onCellSelected: onCellSelected,
    REVEAL_SPEED_PX_PER_SEC: REVEAL_SPEED_PX_PER_SEC,
  };
})(window);
