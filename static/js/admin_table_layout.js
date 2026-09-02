/**
 * Excel-like column resize + header label edit for Django admin tables
 * inside the ERP system-data chrome (body.admin-embed).
 */
(function () {
  if (!document.body || !document.body.classList.contains("admin-embed")) return;
  if (document.body.classList.contains("popup")) return;

  var STORAGE_PREFIX = "erp-admin-table-layout:v1:";
  var storageKey = STORAGE_PREFIX + location.pathname;

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function saveState(state) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
    } catch (e) {
      /* ignore quota */
    }
  }

  function tableId(table) {
    if (table.id) return table.id;
    var inline = table.closest(".inline-group");
    if (inline && inline.id) return "inline:" + inline.id;
    var module = table.closest(".module");
    if (module) {
      var cap = module.querySelector("caption, h2");
      if (cap) return "mod:" + (cap.textContent || "").trim().slice(0, 40);
    }
    return "tbl:" + Array.prototype.indexOf.call(document.querySelectorAll("table"), table);
  }

  function ensureColgroup(table, colCount) {
    var cg = table.querySelector("colgroup");
    if (!cg) {
      cg = document.createElement("colgroup");
      table.insertBefore(cg, table.firstChild);
    }
    while (cg.children.length < colCount) {
      cg.appendChild(document.createElement("col"));
    }
    while (cg.children.length > colCount) {
      cg.removeChild(cg.lastChild);
    }
    return cg;
  }

  function headerCells(table) {
    var row =
      table.querySelector("thead tr") ||
      table.querySelector("tr");
    if (!row) return [];
    return Array.prototype.slice.call(row.children).filter(function (el) {
      return el.tagName === "TH" || el.tagName === "TD";
    });
  }

  function applyWidths(table, widths) {
    var cells = headerCells(table);
    if (!cells.length) return;
    var cg = ensureColgroup(table, cells.length);
    table.style.tableLayout = "fixed";
    table.style.width = "100%";
    cells.forEach(function (th, i) {
      var w = widths && widths[i];
      if (!w || w < 40) return;
      cg.children[i].style.width = w + "px";
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
      th.style.maxWidth = w + "px";
    });
  }

  function applyHeaderLabels(table, labels) {
    if (!labels) return;
    var cells = headerCells(table);
    cells.forEach(function (th, i) {
      if (!labels[i]) return;
      var labelEl = th.querySelector(".admin-th-label");
      if (labelEl) labelEl.textContent = labels[i];
    });
  }

  function measureText(text) {
    var canvas = measureText._c || (measureText._c = document.createElement("canvas"));
    var ctx = canvas.getContext("2d");
    ctx.font = "13px Vazirmatn, Tahoma, sans-serif";
    return Math.ceil(ctx.measureText(String(text || "")).width) + 28;
  }

  function wrapHeaderLabel(th) {
    var existing = th.querySelector(".admin-th-label");
    if (existing) return existing;
    if (th.querySelector("input:not(.admin-th-input), select, textarea")) return null;

    var textWrap = th.querySelector(".text");
    var sortLink = (textWrap && textWrap.querySelector("a")) || th.querySelector("a");
    if (sortLink) {
      var label = document.createElement("span");
      label.className = "admin-th-label";
      label.textContent = (sortLink.textContent || "").trim();
      sortLink.textContent = "";
      sortLink.appendChild(label);
      return label;
    }

    if (textWrap) {
      var label2 = document.createElement("span");
      label2.className = "admin-th-label";
      label2.textContent = (textWrap.textContent || "").trim();
      textWrap.textContent = "";
      textWrap.appendChild(label2);
      return label2;
    }

    var txt = (th.textContent || "").trim();
    if (!txt) return null;
    // Keep non-text children (e.g. action checkbox) then add label
    var kids = Array.prototype.slice.call(th.childNodes);
    var keepEls = [];
    kids.forEach(function (n) {
      if (n.nodeType === 1) keepEls.push(n);
    });
    th.textContent = "";
    keepEls.forEach(function (el) {
      th.appendChild(el);
    });
    var label3 = document.createElement("span");
    label3.className = "admin-th-label";
    label3.textContent = txt;
    th.appendChild(label3);
    return label3;
  }

  function startHeaderEdit(table, th, colIndex) {
    if (th.querySelector("input.admin-th-input")) return;
    var label = wrapHeaderLabel(th) || th.querySelector(".admin-th-label");
    if (!label) return;
    var original = label.textContent;
    var input = document.createElement("input");
    input.type = "text";
    input.className = "admin-th-input";
    input.value = original;
    label.replaceWith(input);
    input.focus();
    input.select();

    function finish(commit) {
      if (!input.parentNode) return;
      var next = commit ? input.value.trim() : original;
      if (!next) next = original;
      var span = document.createElement("span");
      span.className = "admin-th-label";
      span.textContent = next;
      input.replaceWith(span);
      if (commit && next !== original) {
        var state = loadState();
        var id = tableId(table);
        state[id] = state[id] || {};
        state[id].labels = state[id].labels || {};
        state[id].labels[colIndex] = next;
        saveState(state);
        // Persist to system naming registry (server-side)
        try {
          var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
          var fieldName = th.getAttribute("data-field") || th.className.match(/column-(\w+)/);
          fieldName = typeof fieldName === "string" ? fieldName : (fieldName && fieldName[1]) || "";
          fetch("/data/system/admin-header/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrf,
              "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({
              path: location.pathname,
              field: fieldName,
              col_index: colIndex,
              label: next
            })
          }).catch(function () { /* offline/local-only ok */ });
        } catch (err) { /* ignore */ }
      }
    }

    input.addEventListener("keydown", function (e) {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        finish(true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        finish(false);
      }
    });
    input.addEventListener("blur", function () {
      finish(true);
    });
    input.addEventListener("mousedown", function (e) {
      e.stopPropagation();
    });
    input.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  function bindResize(table, th, colIndex) {
    if (th.querySelector(".admin-col-resizer")) return;
    th.classList.add("admin-th-resizable");
    if (getComputedStyle(th).position === "static") {
      th.style.position = "relative";
    }
    var handle = document.createElement("span");
    handle.className = "admin-col-resizer";
    handle.title = "کشیدن = تغییر عرض · دوبار کلیک = اندازه متن";
    th.appendChild(handle);

    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startW = th.getBoundingClientRect().width;
      document.body.classList.add("admin-resizing-col");

      function onMove(ev) {
        // RTL: dragging handle toward the left (decreasing clientX) widens column
        var dx = startX - ev.clientX;
        var w = Math.max(48, Math.min(640, Math.round(startW + dx)));
        var cells = headerCells(table);
        var cg = ensureColgroup(table, cells.length);
        table.style.tableLayout = "fixed";
        cg.children[colIndex].style.width = w + "px";
        th.style.width = w + "px";
        th.style.minWidth = w + "px";
        th.style.maxWidth = w + "px";
      }

      function onUp() {
        document.body.classList.remove("admin-resizing-col");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        var state = loadState();
        var id = tableId(table);
        state[id] = state[id] || {};
        var widths = state[id].widths || [];
        var cells = headerCells(table);
        while (widths.length < cells.length) widths.push(null);
        widths[colIndex] = Math.round(th.getBoundingClientRect().width);
        state[id].widths = widths;
        saveState(state);
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });

    handle.addEventListener("dblclick", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var label = th.querySelector(".admin-th-label");
      var text = label ? label.textContent : th.textContent;
      var w = Math.max(56, Math.min(480, measureText(text)));
      var cells = headerCells(table);
      var cg = ensureColgroup(table, cells.length);
      table.style.tableLayout = "fixed";
      cg.children[colIndex].style.width = w + "px";
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
      th.style.maxWidth = w + "px";
      var state = loadState();
      var id = tableId(table);
      state[id] = state[id] || {};
      var widths = state[id].widths || [];
      while (widths.length < cells.length) widths.push(null);
      widths[colIndex] = w;
      state[id].widths = widths;
      saveState(state);
    });
  }

  function enhanceTable(table) {
    if (!table || table.dataset.adminColLayout === "1") return;
    var cells = headerCells(table);
    if (cells.length < 2) return;
    table.dataset.adminColLayout = "1";
    table.classList.add("admin-resizable-table");

    cells.forEach(function (th, i) {
      // Skip action checkbox column resize label wrap carefully
      wrapHeaderLabel(th);
      bindResize(table, th, i);
      function onHeaderDblClick(e) {
        if (e.target.closest(".admin-col-resizer")) return;
        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();
        startHeaderEdit(table, th, i);
      }
      th.addEventListener("dblclick", onHeaderDblClick, true);
      th.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("dblclick", onHeaderDblClick, true);
      });
    });

    var state = loadState();
    var saved = state[tableId(table)] || {};
    applyWidths(table, saved.widths);
    applyHeaderLabels(table, saved.labels);
  }

  function enhanceAll() {
    document
      .querySelectorAll("#result_list, .inline-group table, form table, #content table")
      .forEach(enhanceTable);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }
})();
