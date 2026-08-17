/* Fullscreen Visio-like print form designer */
(function () {
  "use strict";
  var MM = 3.7795275591;
  var formEl = document.getElementById("designer-form");
  if (!formEl) return;

  var mode = formEl.getAttribute("data-mode") || "create";
  var pk = formEl.getAttribute("data-pk") || "";
  var saveUrl = formEl.getAttribute("data-save-url");
  var listUrl = formEl.getAttribute("data-list-url");

  var frames = [];
  var pageSettings = {
    margin_top: 10, margin_bottom: 10, margin_left: 10, margin_right: 10,
    show_grid: true, show_ruler: true, guides: [], snap_mm: 2
  };
  try { frames = JSON.parse(document.getElementById("frames-initial").textContent || "[]") || []; } catch (e) { frames = []; }
  try { Object.assign(pageSettings, JSON.parse(document.getElementById("page-settings-initial").textContent || "{}") || {}); } catch (e) {}
  if (!Array.isArray(pageSettings.guides)) pageSettings.guides = [];

  frames.forEach(function (f) {
    if (f.left == null && f.x != null) f.left = f.x;
    if (f.left == null) f.left = 0;
    if (!f.align) f.align = "center";
    if (!f.valign) f.valign = "middle";
    if (f.hidden == null) f.hidden = false;
    if (f.locked == null) f.locked = false;
    if (f.rotation == null) f.rotation = 0;
    if (f.data_extend == null) f.data_extend = false;
    if (f.kind === "line" && !f.orientation) f.orientation = (f.height > f.width) ? "v" : "h";
    if (f.kind === "line" && !f.line_style) f.line_style = "solid";
    if (f.kind === "box" && (!f.fill_colors || !f.fill_colors.length)) f.fill_colors = ["#ffffff", "#e8f0fe"];
    if (f.kind === "box" && !f.border_styles) {
      f.border_styles = { top: "solid", right: "solid", bottom: "solid", left: "solid" };
    }
    if (f.kind === "box" && f.last_line_enable == null) f.last_line_enable = false;
    if (f.kind === "box" && !f.last_line_style) f.last_line_style = "solid";
  });

  var groups = [];
  try { groups = JSON.parse(document.getElementById("column-groups").textContent || "[]"); } catch (e) {}

  var selectedId = null;
  var selectedGuideIdx = null;
  var zoom = 1;
  var snap = pageSettings.snap_mm || 2;
  var uid = 1;
  var history = [];
  var future = [];
  var previewMode = false;
  var guidesEnabled = true;
  var dragGuide = null;
  var clipboard = null;
  var drag = null;
  var layerDragId = null;

  var hiddenFrames = document.getElementById("id_frames_json");
  var hiddenSettings = document.getElementById("id_page_settings_json");
  var pageWInput = document.getElementById("id_page_width_mm");
  var pageHInput = document.getElementById("id_page_height_mm");
  var canvas = document.getElementById("form-canvas");
  var scrollEl = document.getElementById("designer-scroll");
  var wrap = document.getElementById("canvas-wrap");
  var rulerH = document.getElementById("ruler-h");
  var rulerV = document.getElementById("ruler-v");

  function pageW() { return parseFloat(pageWInput.value) || 210; }
  function pageH() { return parseFloat(pageHInput.value) || 297; }
  function px(mm) { return mm * MM * zoom; }
  function mmFromPx(v) { return v / (MM * zoom); }
  function snapMm(v) { return Math.round(v / snap) * snap; }
  function find(id) { return frames.find(function (f) { return f.id === id; }); }
  function findIndex(id) { return frames.findIndex(function (f) { return f.id === id; }); }
  function toast(msg) {
    var t = document.getElementById("dz-toast");
    t.textContent = msg; t.classList.add("show");
    setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  function cloneState() {
    return JSON.stringify({ frames: frames, pageSettings: pageSettings, pageW: pageW(), pageH: pageH() });
  }
  function pushHistory() {
    history.push(cloneState());
    if (history.length > 80) history.shift();
    future = [];
    updateHistoryButtons();
  }
  function restoreState(raw) {
    var s = JSON.parse(raw);
    frames = s.frames || [];
    pageSettings = Object.assign(pageSettings, s.pageSettings || {});
    if (!Array.isArray(pageSettings.guides)) pageSettings.guides = [];
    pageWInput.value = s.pageW; pageHInput.value = s.pageH;
    snap = pageSettings.snap_mm || 2;
    if (snap < 1) snap = 1;
    if (snap > 10) snap = 10;
    pageSettings.snap_mm = snap;
    selectedId = null;
    selectedGuideIdx = null;
    syncUiChecks();
    render();
  }
  function updateHistoryButtons() {
    var u = document.getElementById("btn-undo");
    var r = document.getElementById("btn-redo");
    if (u) u.disabled = !history.length;
    if (r) r.disabled = !future.length;
  }
  function undo() {
    if (!history.length) return;
    future.push(cloneState());
    restoreState(history.pop());
    updateHistoryButtons();
  }
  function redo() {
    if (!future.length) return;
    history.push(cloneState());
    restoreState(future.pop());
    updateHistoryButtons();
  }

  function syncHidden() {
    frames.forEach(function (f) { f.x = f.left; });
    hiddenFrames.value = JSON.stringify(frames);
    hiddenSettings.value = JSON.stringify(pageSettings);
  }

  function kindLabel(k, f) {
    if ((k === "line" || !k) && f && f.orientation === "v") return "خط عمودی";
    if ((k === "line" || !k) && f && f.orientation === "h") return "خط افقی";
    return ({
      header: "عنوان", box: "کادر", field: "کلید منابع",
      line: "خط", line_h: "خط افقی", line_v: "خط عمودی",
      logo: "لوگو", row_number: "ردیف"
    })[k] || k;
  }

  function isLineKind(k) { return k === "line" || k === "line_h" || k === "line_v"; }

  function borderCss(style) {
    if (style === "none") return "none";
    if (style === "dashed") return "1.5px dashed #111";
    if (style === "dotted") return "1.5px dotted #111";
    if (style === "dashdot") return "1.5px dashed #111";
    return "1.5px solid #111";
  }

  function defaultFillColors() {
    return ["#ffffff", "#e8f0fe"];
  }

  function updateClipboardButtons() {
    var copyBtn = document.getElementById("btn-copy");
    var pasteBtn = document.getElementById("btn-paste");
    if (copyBtn) {
      copyBtn.disabled = !selectedId;
      copyBtn.classList.toggle("is-ready", !!selectedId);
    }
    if (pasteBtn) {
      pasteBtn.disabled = !clipboard;
      pasteBtn.classList.toggle("is-ready", !!clipboard);
    }
  }

  function columnLabel(source, key) {
    if (window.ERPFormSheetRender && window.ERPFormSheetRender.columnLabel) {
      return window.ERPFormSheetRender.columnLabel(groups, source, key);
    }
    if (!source || !key) return "";
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].id !== source) continue;
      var cols = groups[i].columns || [];
      for (var j = 0; j < cols.length; j++) {
        if (cols[j][0] === key) return cols[j][1] || key;
      }
    }
    return key;
  }

  function nearMm(a, b) { return Math.abs(a - b) <= 0.6; }
  function vertOverlap(a, b) {
    return Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 0.5;
  }
  function horizOverlap(a, b) {
    return Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 0.5;
  }

  /** Shared edges: top box wins (bottom neighbor hides top); right box wins (left neighbor hides right). */
  function resolveBoxBorders(inst, allBoxes, bs, lastStyle) {
    var top = (bs && bs.top) || "solid";
    var right = (bs && bs.right) || "solid";
    var bottom = lastStyle || (bs && bs.bottom) || "solid";
    var left = (bs && bs.left) || "solid";
    allBoxes.forEach(function (other) {
      if (other === inst) return;
      if (nearMm(other.y + other.h, inst.y) && horizOverlap(inst, other)) top = "none";
      if (nearMm(inst.x + inst.w, other.x) && vertOverlap(inst, other)) right = "none";
    });
    return {
      top: borderCss(top),
      right: borderCss(right),
      bottom: borderCss(bottom),
      left: borderCss(left)
    };
  }

  function syncUiChecks() {
    document.getElementById("chk-grid").checked = !!pageSettings.show_grid;
    document.getElementById("chk-ruler").checked = !!pageSettings.show_ruler;
    document.getElementById("chk-guides").checked = guidesEnabled;
    wrap.classList.toggle("no-ruler", !pageSettings.show_ruler);
    document.getElementById("margin-top").value = pageSettings.margin_top;
    document.getElementById("margin-bottom").value = pageSettings.margin_bottom;
    document.getElementById("margin-left").value = pageSettings.margin_left;
    document.getElementById("margin-right").value = pageSettings.margin_right;
    document.getElementById("prop-page-w").value = pageW();
    document.getElementById("prop-page-h").value = pageH();
    document.getElementById("snap-mm").value = String(snap);
    var PRESETS = { "A4-P": [210, 297], "A4-L": [297, 210], "A5-P": [148, 210], "A5-L": [210, 148] };
    var found = "custom", w = pageW(), h = pageH();
    Object.keys(PRESETS).forEach(function (k) { if (PRESETS[k][0] === w && PRESETS[k][1] === h) found = k; });
    document.getElementById("paper-preset").value = found;
    var wEl = document.getElementById("prop-page-w");
    var hEl = document.getElementById("prop-page-h");
    var isCustom = found === "custom";
    wEl.disabled = !isCustom;
    hEl.disabled = !isCustom;
    wEl.title = isCustom ? "" : "برای تغییر اندازه، «سفارشی» را انتخاب کنید";
    hEl.title = isCustom ? "" : "برای تغییر اندازه، «سفارشی» را انتخاب کنید";
    updateHistoryButtons();
  }

  /* Horizontal ruler: 0 at left → width at right */
  function drawRulers() {
    if (!pageSettings.show_ruler) { rulerH.innerHTML = ""; rulerV.innerHTML = ""; return; }
    var w = pageW(), h = pageH();
    rulerH.innerHTML = "";
    rulerV.innerHTML = "";

    var paperRect = canvas.getBoundingClientRect();
    var hRect = rulerH.getBoundingClientRect();
    var vRect = rulerV.getBoundingClientRect();
    var paperLeftInH = paperRect.left - hRect.left;
    var paperTopInV = paperRect.top - vRect.top;

    for (var x = 0; x <= w; x += 1) {
      if (x % 5 !== 0 && snap > 1) continue;
      var tick = document.createElement("div");
      tick.className = "dz-tick" + (x % 10 === 0 ? " major" : "");
      tick.style.left = (paperLeftInH + px(x)) + "px";
      if (x % 10 === 0) {
        var lab = document.createElement("span");
        lab.textContent = String(x);
        tick.appendChild(lab);
      }
      rulerH.appendChild(tick);
    }
    for (var y = 0; y <= h; y += 1) {
      if (y % 5 !== 0 && snap > 1) continue;
      var tick2 = document.createElement("div");
      tick2.className = "dz-tick" + (y % 10 === 0 ? " major" : "");
      tick2.style.top = (paperTopInV + px(y)) + "px";
      if (y % 10 === 0) {
        var lab2 = document.createElement("span");
        lab2.textContent = String(y);
        tick2.appendChild(lab2);
      }
      rulerV.appendChild(tick2);
    }
  }

  function estimateExtendRows(f) {
    var mb = pageSettings.margin_bottom || 0;
    var avail = pageH() - (f.y || 0) - mb;
    var rowH = Math.max(f.height || 8, 6);
    return Math.max(1, Math.floor(avail / rowH));
  }

  /** Row count comes from the first extended data field (not page bottom alone). */
  function extendMasterRows() {
    var masters = frames.filter(function (f) {
      return !f.hidden && f.kind === "field" && f.data_extend;
    });
    if (!masters.length) return 0;
    return estimateExtendRows(masters[0]);
  }

  function masterRowHeight() {
    var masters = frames.filter(function (f) {
      return !f.hidden && f.kind === "field" && f.data_extend;
    });
    if (!masters.length) return 14;
    return Math.max(masters[0].height || 8, 6);
  }

  function copiesForFrame(f, masterRows) {
    if (!f.data_extend) return 1;
    if (f.kind === "field") return estimateExtendRows(f);
    // row_number / box / line / others with extend follow master data field count
    if (masterRows > 0) return masterRows;
    return 1;
  }

  function renderLayers() {
    var list = document.getElementById("layers-list");
    list.innerHTML = "";
    frames.slice().reverse().forEach(function (f) {
      var row = document.createElement("div");
      row.className = "dz-clip" + (f.id === selectedId ? " is-active" : "") + (f.hidden ? " is-layer-hidden" : "") + (f.locked ? " is-locked" : "");
      row.draggable = true;
      row.dataset.id = f.id;
      row.innerHTML =
        '<span class="dz-drag-handle" title="جابجایی لایه">⋮⋮</span>' +
        '<span class="name">' + kindLabel(f.kind, f) + " — " + (f.label || "بدون نام") + "</span>" +
        '<button type="button" class="dz-icon-btn dz-lock' + (f.locked ? " on" : "") + '" title="' + (f.locked ? "باز کردن قفل" : "قفل کردن") + '">' +
          (f.locked
            ? '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2" fill="currentColor"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><rect x="11" y="14.2" width="2" height="3.2" rx="0.6" fill="#1a1d24"/></svg>'
            : '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 11V8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M8 8c0-3.2 2.2-5.5 5.2-5.5 2.4 0 4.3 1.4 5 3.4" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="16" r="1.2" fill="currentColor"/></svg>') +
        "</button>" +
        '<button type="button" class="dz-icon-btn dz-eye' + (f.hidden ? " off" : "") + '" title="مخفی/نمایش"' + (f.locked ? " disabled" : "") + ">" +
          '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.2C4.2 3.2 1.3 6.1.5 8c.8 1.9 3.7 4.8 7.5 4.8S14.7 9.9 15.5 8C14.7 6.1 11.8 3.2 8 3.2zm0 7.6A2.8 2.8 0 1 1 8 5.2a2.8 2.8 0 0 1 0 5.6z"/></svg>' +
        "</button>" +
        '<button type="button" class="dz-icon-btn del" title="حذف"' + (f.locked ? " disabled" : "") + ">" +
          '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.2 4.2 8 8l3.8-3.8 1.2 1.2L9.2 9.2l3.8 3.8-1.2 1.2L8 10.4l-3.8 3.8-1.2-1.2 3.8-3.8-3.8-3.8z"/></svg>' +
        "</button>";
      row.addEventListener("click", function (e) {
        if (e.target.closest(".dz-icon-btn")) return;
        selectedId = f.id; selectedGuideIdx = null; render();
      });
      row.querySelector(".dz-eye").addEventListener("click", function (e) {
        e.stopPropagation();
        if (f.locked) return;
        pushHistory();
        f.hidden = !f.hidden;
        render();
      });
      row.querySelector(".dz-lock").addEventListener("click", function (e) {
        e.stopPropagation();
        pushHistory();
        f.locked = !f.locked;
        render();
      });
      row.querySelector(".del").addEventListener("click", function (e) {
        e.stopPropagation();
        if (f.locked) return;
        pushHistory();
        frames = frames.filter(function (x) { return x.id !== f.id; });
        if (selectedId === f.id) selectedId = null;
        render();
      });
      row.addEventListener("dragstart", function (e) {
        layerDragId = f.id;
        e.dataTransfer.effectAllowed = "move";
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", function () {
        layerDragId = null;
        row.classList.remove("dragging");
      });
      row.addEventListener("dragover", function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      });
      row.addEventListener("drop", function (e) {
        e.preventDefault();
        if (!layerDragId || layerDragId === f.id) return;
        pushHistory();
        var from = findIndex(layerDragId);
        var to = findIndex(f.id);
        if (from < 0 || to < 0) return;
        var item = frames.splice(from, 1)[0];
        frames.splice(to, 0, item);
        selectedId = layerDragId;
        render();
      });
      list.appendChild(row);
    });
  }

  function updateAlignButtons() {
    var f = find(selectedId);
    var textish = f && (f.kind === "header" || f.kind === "field" || f.kind === "box" || f.kind === "row_number");
    document.querySelectorAll("#align-group button").forEach(function (btn) {
      btn.disabled = !textish;
      btn.classList.toggle("active",
        !!(textish && ((btn.dataset.align && btn.dataset.align === f.align) ||
          (btn.dataset.valign && btn.dataset.valign === f.valign)))
      );
    });
  }

  function syncFormMetaUi() {
    var titleHidden = document.getElementById("id_title");
    var numberHidden = document.getElementById("id_number");
    var titleUi = document.getElementById("ui-form-title");
    var numberUi = document.getElementById("ui-form-number");
    if (titleUi && titleHidden && !titleUi.dataset.bound) {
      titleUi.value = titleHidden.value || "";
      titleUi.addEventListener("input", function () {
        titleHidden.value = titleUi.value;
        document.getElementById("dz-window-title").textContent =
          (mode === "edit" ? "ویرایش فرم — " : "ایجاد فرم — ") + (titleUi.value || "بدون عنوان");
      });
      titleUi.dataset.bound = "1";
    }
    if (numberUi && numberHidden && !numberUi.dataset.bound) {
      numberUi.value = numberHidden.value || "";
      numberUi.addEventListener("input", function () {
        numberHidden.value = numberUi.value;
      });
      numberUi.dataset.bound = "1";
    }
  }

  function renderFillPatternUI(f) {
    var list = document.getElementById("fill-pattern-list");
    if (!list) return;
    if (!Array.isArray(f.fill_colors) || !f.fill_colors.length) {
      f.fill_colors = defaultFillColors();
    }
    list.innerHTML = "";
    f.fill_colors.forEach(function (color, idx) {
      var row = document.createElement("div");
      row.className = "dz-fill-row";
      row.innerHTML =
        '<span class="dz-fill-label">الگو ' + (idx + 1) + "</span>" +
        '<input type="color" value="' + color + '" data-fill-idx="' + idx + '">' +
        (idx >= 2 ? '<button type="button" class="dz-icon-btn del" data-fill-del="' + idx + '" title="حذف">×</button>' : "");
      list.appendChild(row);
    });
    list.querySelectorAll("input[type=color]").forEach(function (inp) {
      inp.addEventListener("change", function () {
        pushHistory();
        f.fill_colors[parseInt(inp.getAttribute("data-fill-idx"), 10)] = inp.value;
        render();
      });
    });
    list.querySelectorAll("[data-fill-del]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var i = parseInt(btn.getAttribute("data-fill-del"), 10);
        if (f.fill_colors.length <= 2) return;
        pushHistory();
        f.fill_colors.splice(i, 1);
        render();
      });
    });
    var addBtn = document.getElementById("btn-add-fill");
    if (addBtn) {
      addBtn.disabled = f.fill_colors.length >= 9;
      addBtn.onclick = function () {
        if (f.fill_colors.length >= 9) return;
        pushHistory();
        f.fill_colors.push("#f8fafc");
        render();
      };
    }
  }

  function renderProps() {
    var empty = document.getElementById("props-empty");
    var fields = document.getElementById("props-fields");
    var f = find(selectedId);
    updateAlignButtons();
    if (!f) { empty.hidden = false; fields.hidden = true; return; }
    empty.hidden = true; fields.hidden = false;
    document.getElementById("prop-label").value = f.label || "";
    document.getElementById("prop-x").value = f.left || 0;
    document.getElementById("prop-y").value = f.y || 0;
    document.getElementById("prop-w").value = f.width;
    document.getElementById("prop-h").value = f.height;
    document.getElementById("prop-rotation").value = f.rotation || 0;
    document.getElementById("logo-props").hidden = f.kind !== "logo";
    document.getElementById("field-bind-props").hidden = f.kind !== "field";
    document.getElementById("row-number-props").hidden = f.kind !== "row_number";
    document.getElementById("shape-extend-props").hidden = !(f.kind === "box" || isLineKind(f.kind));
    document.getElementById("line-style-props").hidden = !isLineKind(f.kind);
    document.getElementById("box-style-props").hidden = f.kind !== "box";
    if (f.kind === "field") {
      document.getElementById("prop-data-extend").checked = !!f.data_extend;
      fillSources(f);
    }
    if (f.kind === "row_number") {
      document.getElementById("prop-row-extend").checked = !!f.data_extend;
    }
    if (f.kind === "box" || isLineKind(f.kind)) {
      document.getElementById("prop-shape-extend").checked = !!f.data_extend;
    }
    if (isLineKind(f.kind)) {
      document.getElementById("prop-line-style").value = f.line_style || "solid";
    }
    if (f.kind === "box") {
      var bs = f.border_styles || {};
      document.getElementById("prop-border-top").value = bs.top || "solid";
      document.getElementById("prop-border-bottom").value = bs.bottom || "solid";
      document.getElementById("prop-border-right").value = bs.right || "solid";
      document.getElementById("prop-border-left").value = bs.left || "solid";
      document.getElementById("prop-last-line-enable").checked = !!f.last_line_enable;
      document.getElementById("last-line-wrap").hidden = !f.last_line_enable;
      document.getElementById("prop-last-line-style").value = f.last_line_style || "solid";
      renderFillPatternUI(f);
    }
  }

  function fillSources(f) {
    var srcSel = document.getElementById("prop-source");
    var keySel = document.getElementById("prop-source-key");
    srcSel.innerHTML = '<option value="">— منبع —</option>';
    groups.forEach(function (g) {
      var o = document.createElement("option");
      o.value = g.id; o.textContent = g.label; srcSel.appendChild(o);
    });
    srcSel.value = f.source || "";
    function fillKeys() {
      keySel.innerHTML = '<option value="">— ستون —</option>';
      var g = groups.find(function (x) { return x.id === srcSel.value; });
      if (g) (g.columns || []).forEach(function (c) {
        var o = document.createElement("option"); o.value = c[0]; o.textContent = c[1]; keySel.appendChild(o);
      });
      keySel.value = f.source_key || "";
      document.getElementById("field-bind-path").textContent =
        (f.source && f.source_key) ? ("آدرس: " + f.source + " → " + f.source_key) : "وصل نشده";
    }
    fillKeys();
    srcSel.onchange = function () { pushHistory(); f.source = srcSel.value; f.source_key = ""; fillKeys(); render(); };
    keySel.onchange = function () { pushHistory(); f.source_key = keySel.value; fillKeys(); render(); };
  }

  function render() {
    syncHidden();
    syncUiChecks();
    var w = pageW(), h = pageH();
    canvas.style.width = px(w) + "px";
    canvas.style.height = px(h) + "px";
    canvas.innerHTML = "";

    if (pageSettings.show_grid && !previewMode) {
      var grid = document.createElement("div");
      grid.className = "dz-grid";
      var gsz = px(snap);
      grid.style.backgroundSize = gsz + "px " + gsz + "px";
      canvas.appendChild(grid);
    }

    if (!previewMode) {
      var mt = pageSettings.margin_top || 0, mb = pageSettings.margin_bottom || 0;
      var ml = pageSettings.margin_left || 0, mr = pageSettings.margin_right || 0;
      var margin = document.createElement("div");
      margin.className = "dz-margin";
      margin.style.top = px(mt) + "px";
      margin.style.left = px(ml) + "px";
      margin.style.width = px(Math.max(1, w - ml - mr)) + "px";
      margin.style.height = px(Math.max(1, h - mt - mb)) + "px";
      canvas.appendChild(margin);
    }

    if (guidesEnabled && !previewMode) {
      pageSettings.guides.forEach(function (g, gi) {
        var el = document.createElement("div");
        el.className = "dz-guide " + g.axis;
        el.dataset.guideIndex = String(gi);
        if (g.axis === "h") el.style.top = px(g.pos) + "px";
        else el.style.left = px(g.pos) + "px";
        el.addEventListener("mousedown", function (e) {
          e.preventDefault();
          e.stopPropagation();
          selectedGuideIdx = gi;
          selectedId = null;
          dragGuide = { axis: g.axis, pos: g.pos, index: gi, moving: true };
          render();
        });
        canvas.appendChild(el);
      });
      if (dragGuide && !dragGuide.moving) {
        var tmp = document.createElement("div");
        tmp.className = "dz-guide " + dragGuide.axis;
        if (dragGuide.axis === "h") tmp.style.top = px(dragGuide.pos) + "px";
        else tmp.style.left = px(dragGuide.pos) + "px";
        canvas.appendChild(tmp);
      }
    }

    var masterRows = extendMasterRows();
    var rowStep = masterRowHeight();

    var pending = [];
    var boxInstances = [];

    frames.forEach(function (f, zi) {
      if (f.hidden) return;
      var copies = 1;
      if (previewMode && f.data_extend) {
        copies = copiesForFrame(f, masterRows);
      }
      var step = (f.kind === "field") ? (f.height || 8) : rowStep;
      for (var i = 0; i < copies; i++) {
        var item = {
          f: f, i: i, copies: copies, zi: zi,
          x: f.left || 0,
          y: (f.y || 0) + i * step,
          w: f.width || 20,
          h: f.height || 10
        };
        pending.push(item);
        if (f.kind === "box") boxInstances.push(item);
      }
    });

    pending.forEach(function (item) {
        var f = item.f;
        var i = item.i;
        var el = document.createElement("div");
        el.className = "dz-frame kind-" + (f.kind || "box") +
          (f.id === selectedId && i === 0 && !previewMode ? " selected" : "") +
          (f.locked ? " is-locked" : "");
        el.style.zIndex = String(2 + item.zi);
        el.style.left = px(item.x) + "px";
        el.style.top = px(item.y) + "px";
        el.style.width = px(item.w) + "px";
        el.style.height = px(item.h) + "px";
        el.style.transform = "rotate(" + (f.rotation || 0) + "deg)";
        el.style.printColorAdjust = "exact";
        el.style.webkitPrintColorAdjust = "exact";
        var inner = document.createElement("div");
        inner.className = "inner";
        inner.style.justifyContent = f.align === "left" ? "flex-end" : (f.align === "right" ? "flex-start" : "center");
        inner.style.alignItems = f.valign === "top" ? "flex-start" : (f.valign === "bottom" ? "flex-end" : "center");
        inner.style.textAlign = f.align || "center";

        if (f.kind === "box") {
          var fills = (f.fill_colors && f.fill_colors.length) ? f.fill_colors : defaultFillColors();
          el.style.background = fills[i % fills.length];
          var bs = f.border_styles || {};
          var isLast = previewMode && f.data_extend && (i === item.copies - 1) && f.last_line_enable;
          var lastStyle = isLast ? (f.last_line_style || "solid") : null;
          var borders = resolveBoxBorders(item, boxInstances, bs, lastStyle);
          el.style.borderTop = borders.top;
          el.style.borderRight = borders.right;
          el.style.borderLeft = borders.left;
          el.style.borderBottom = borders.bottom;
        } else if (isLineKind(f.kind)) {
          var ls = f.line_style || "solid";
          el.style.background = "transparent";
          el.style.border = "0";
          if (f.orientation === "v" || f.kind === "line_v") {
            el.style.borderLeft = borderCss(ls);
            el.style.minWidth = "1px";
          } else {
            el.style.borderTop = borderCss(ls);
            el.style.minHeight = "1px";
          }
        } else if (f.stroke && f.kind !== "field" && f.kind !== "row_number") {
          el.style.borderWidth = px(f.stroke) + "px";
        }

        if (f.kind === "logo" && f.image_data) {
          var img = document.createElement("img");
          img.src = f.image_data; img.alt = f.label || "لوگو";
          inner.appendChild(img);
        } else if (isLineKind(f.kind)) {
          /* styled via borders */
        } else if (f.kind === "row_number") {
          inner.textContent = previewMode ? String(i + 1) : (f.label || "ردیف");
        } else if (f.kind === "field") {
          if (previewMode) {
            inner.textContent = columnLabel(f.source, f.source_key) || "";
          } else {
            var txt = f.label || "کلید منابع";
            if (f.source && f.source_key) txt += " ⟨" + f.source + "." + f.source_key + "⟩";
            inner.textContent = txt;
          }
        } else if (f.kind !== "box") {
          inner.textContent = f.label || kindLabel(f.kind);
        } else if (f.label && !previewMode) {
          inner.textContent = f.label;
        } else if (f.label && previewMode && !f.data_extend) {
          inner.textContent = f.label;
        }
        el.appendChild(inner);

        if (!previewMode && f.data_extend && i === 0) {
          var badge = document.createElement("span");
          badge.className = "badge-extend";
          badge.textContent = f.kind === "row_number" ? "وابسته به فیلد" : "امتداد";
          el.appendChild(badge);
        }

        if (i === 0) {
          el.dataset.id = f.id;
          if (!previewMode) {
            el.addEventListener("mousedown", startDrag);
            if (f.id === selectedId) {
              ["nw","n","ne","e","se","s","sw","w"].forEach(function (c) {
                var hndl = document.createElement("span");
                hndl.className = "dz-handle " + c;
                hndl.dataset.corner = c;
                hndl.addEventListener("mousedown", startResize);
                el.appendChild(hndl);
              });
              var rot = document.createElement("span");
              rot.className = "dz-handle rotate";
              rot.title = "چرخش";
              rot.addEventListener("mousedown", startRotate);
              el.appendChild(rot);
            }
          }
        }
        canvas.appendChild(el);
    });

    drawRulers();
    renderLayers();
    renderProps();
    updateClipboardButtons();
  }

  function applyProps() {
    var f = find(selectedId); if (!f) return;
    if (f.locked) return;
    pushHistory();
    function mm1(v) { return Math.round(Math.max(0, parseFloat(v) || 0)); }
    f.label = document.getElementById("prop-label").value;
    f.left = mm1(document.getElementById("prop-x").value);
    f.y = mm1(document.getElementById("prop-y").value);
    f.width = Math.max(1, mm1(document.getElementById("prop-w").value) || 1);
    f.height = Math.max(1, Math.max(0.5, parseFloat(document.getElementById("prop-h").value) || 1));
    f.height = Math.round(f.height);
    f.rotation = Math.round(parseFloat(document.getElementById("prop-rotation").value) || 0);
    if (f.kind === "line") { f.height = Math.max(1, f.height); if (f.orientation === "v") f.width = Math.max(1, f.width); }
    render();
  }
  ["prop-label","prop-x","prop-y","prop-w","prop-h","prop-rotation"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("change", applyProps);
  });
  document.getElementById("prop-data-extend").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "field") return;
    pushHistory(); f.data_extend = this.checked; render();
  });
  document.getElementById("prop-row-extend").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "row_number") return;
    pushHistory(); f.data_extend = this.checked; render();
  });
  document.getElementById("prop-shape-extend").addEventListener("change", function () {
    var f = find(selectedId); if (!f || (f.kind !== "box" && !isLineKind(f.kind))) return;
    pushHistory(); f.data_extend = this.checked; render();
  });
  document.getElementById("prop-line-style").addEventListener("change", function () {
    var f = find(selectedId); if (!f || !isLineKind(f.kind)) return;
    pushHistory(); f.line_style = this.value; render();
  });
  ["prop-border-top","prop-border-bottom","prop-border-right","prop-border-left"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
      var f = find(selectedId); if (!f || f.kind !== "box") return;
      pushHistory();
      f.border_styles = f.border_styles || {};
      f.border_styles.top = document.getElementById("prop-border-top").value;
      f.border_styles.bottom = document.getElementById("prop-border-bottom").value;
      f.border_styles.right = document.getElementById("prop-border-right").value;
      f.border_styles.left = document.getElementById("prop-border-left").value;
      render();
    });
  });
  document.getElementById("prop-last-line-enable").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "box") return;
    pushHistory();
    f.last_line_enable = this.checked;
    document.getElementById("last-line-wrap").hidden = !this.checked;
    render();
  });
  document.getElementById("prop-last-line-style").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "box") return;
    pushHistory(); f.last_line_style = this.value; render();
  });
  document.getElementById("prop-logo-file").addEventListener("change", function (e) {
    var f = find(selectedId); if (!f || f.kind !== "logo") return;
    var file = e.target.files && e.target.files[0]; if (!file) return;
    var reader = new FileReader();
    reader.onload = function () { pushHistory(); f.image_data = reader.result; render(); };
    reader.readAsDataURL(file);
  });

  document.querySelectorAll("#align-group button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = find(selectedId); if (!f || btn.disabled || f.locked) return;
      pushHistory();
      if (btn.dataset.align) f.align = btn.dataset.align;
      if (btn.dataset.valign) f.valign = btn.dataset.valign;
      render();
    });
  });

  var PRESETS = { "A4-P": [210, 297], "A4-L": [297, 210], "A5-P": [148, 210], "A5-L": [210, 148] };
  document.getElementById("paper-preset").addEventListener("change", function () {
    var v = this.value;
    if (PRESETS[v]) {
      pushHistory();
      pageWInput.value = PRESETS[v][0]; pageHInput.value = PRESETS[v][1];
    }
    render();
  });
  ["prop-page-w","prop-page-h"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
      if (this.disabled) return;
      pushHistory();
      pageWInput.value = document.getElementById("prop-page-w").value;
      pageHInput.value = document.getElementById("prop-page-h").value;
      document.getElementById("paper-preset").value = "custom";
      render();
    });
  });
  ["margin-top","margin-bottom","margin-left","margin-right"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
      pushHistory();
      pageSettings.margin_top = parseFloat(document.getElementById("margin-top").value) || 0;
      pageSettings.margin_bottom = parseFloat(document.getElementById("margin-bottom").value) || 0;
      pageSettings.margin_left = parseFloat(document.getElementById("margin-left").value) || 0;
      pageSettings.margin_right = parseFloat(document.getElementById("margin-right").value) || 0;
      render();
    });
  });
  document.getElementById("snap-mm").addEventListener("change", function () {
    pushHistory();
    snap = parseFloat(this.value) || 2;
    pageSettings.snap_mm = snap;
    render();
  });
  document.getElementById("chk-grid").addEventListener("change", function () {
    pageSettings.show_grid = this.checked; render();
  });
  document.getElementById("chk-ruler").addEventListener("change", function () {
    pageSettings.show_ruler = this.checked; render();
  });
  document.getElementById("chk-guides").addEventListener("change", function () {
    guidesEnabled = this.checked; render();
  });

  function startDrag(e) {
    if (e.target.classList.contains("dz-handle")) return;
    e.preventDefault();
    selectedId = e.currentTarget.dataset.id;
    selectedGuideIdx = null;
    var f = find(selectedId);
    if (!f) return;
    if (f.locked) { render(); return; }
    pushHistory();
    drag = { mode: "move", id: selectedId, startX: e.clientX, startY: e.clientY, ox: f.left || 0, oy: f.y || 0 };
    render();
  }
  function startResize(e) {
    e.preventDefault(); e.stopPropagation();
    var id = e.currentTarget.parentElement.dataset.id;
    var f = find(id); if (!f || f.locked) return;
    selectedId = id; selectedGuideIdx = null;
    pushHistory();
    drag = {
      mode: "resize", corner: e.currentTarget.dataset.corner, id: id,
      startX: e.clientX, startY: e.clientY, ox: f.left || 0, oy: f.y || 0, ow: f.width, oh: f.height
    };
  }
  function startRotate(e) {
    e.preventDefault(); e.stopPropagation();
    var id = e.currentTarget.parentElement.dataset.id;
    var f = find(id); if (!f || f.locked) return;
    selectedId = id;
    pushHistory();
    var rect = e.currentTarget.parentElement.getBoundingClientRect();
    drag = {
      mode: "rotate", id: id,
      cx: rect.left + rect.width / 2, cy: rect.top + rect.height / 2,
      startAngle: f.rotation || 0,
      startMouse: Math.atan2(e.clientY - (rect.top + rect.height / 2), e.clientX - (rect.left + rect.width / 2)) * 180 / Math.PI
    };
  }

  window.addEventListener("mousemove", function (e) {
    if (dragGuide) {
      var rect = canvas.getBoundingClientRect();
      if (dragGuide.axis === "h") {
        dragGuide.pos = snapMm(Math.max(0, Math.min(pageH(), mmFromPx(e.clientY - rect.top))));
      } else {
        dragGuide.pos = snapMm(Math.max(0, Math.min(pageW(), mmFromPx(e.clientX - rect.left))));
      }
      if (dragGuide.moving && dragGuide.index != null) {
        pageSettings.guides[dragGuide.index].pos = dragGuide.pos;
      }
      render();
      return;
    }
    if (!drag) return;
    var f = find(drag.id); if (!f) return;
    if (drag.mode === "rotate") {
      var ang = Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180 / Math.PI;
      f.rotation = Math.round((drag.startAngle + (ang - drag.startMouse)) / 5) * 5;
      render();
      return;
    }
    var dx = mmFromPx(e.clientX - drag.startX);
    var dy = mmFromPx(e.clientY - drag.startY);
    if (drag.mode === "move") {
      f.left = snapMm(Math.max(0, drag.ox + dx));
      f.y = snapMm(Math.max(0, drag.oy + dy));
    } else {
      var c = drag.corner;
      if (c.indexOf("e") >= 0) f.width = snapMm(Math.max(snap, drag.ow + dx));
      if (c.indexOf("s") >= 0) f.height = snapMm(Math.max(1, drag.oh + dy));
      if (c.indexOf("w") >= 0) {
        f.left = snapMm(Math.max(0, drag.ox + dx));
        f.width = snapMm(Math.max(snap, drag.ow - dx));
      }
      if (c.indexOf("n") >= 0) {
        f.y = snapMm(Math.max(0, drag.oy + dy));
        f.height = snapMm(Math.max(1, drag.oh - dy));
      }
    }
    render();
  });
  window.addEventListener("mouseup", function () {
    if (dragGuide) {
      if (!dragGuide.moving) {
        pushHistory();
        pageSettings.guides.push({ axis: dragGuide.axis, pos: dragGuide.pos });
        selectedGuideIdx = pageSettings.guides.length - 1;
      }
      dragGuide = null;
      render();
    }
    drag = null;
  });

  canvas.addEventListener("mousedown", function (e) {
    if (e.target === canvas || e.target.classList.contains("dz-grid") || e.target.classList.contains("dz-margin")) {
      selectedId = null; selectedGuideIdx = null; render();
    }
  });

  function startGuideFromRuler(axis, e) {
    if (!guidesEnabled || !pageSettings.show_ruler) return;
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    selectedId = null;
    dragGuide = {
      axis: axis,
      pos: axis === "h"
        ? snapMm(Math.max(0, mmFromPx(e.clientY - rect.top)))
        : snapMm(Math.max(0, mmFromPx(e.clientX - rect.left))),
      moving: false
    };
  }
  rulerH.addEventListener("mousedown", function (e) { startGuideFromRuler("h", e); });
  rulerV.addEventListener("mousedown", function (e) { startGuideFromRuler("v", e); });

  scrollEl.addEventListener("scroll", function () { drawRulers(); });
  window.addEventListener("resize", function () { drawRulers(); });

  document.querySelectorAll("[data-add]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      pushHistory();
      var kind = btn.getAttribute("data-add");
      var f = {
        id: "f" + Date.now() + "-" + (uid++),
        label: kind === "header" ? "عنوان" : kind === "field" ? "کلید منابع" : kind === "logo" ? "لوگو" : kind === "row_number" ? "ردیف" : kind === "box" ? "کادر" : "",
        kind: kind, left: 15, x: 15, y: 20 + frames.length * 8,
        width: 60, height: 14,
        rotation: 0, stroke: 0.5, align: "center", valign: "middle", hidden: false, locked: false, data_extend: false
      };
      if (kind === "line_h" || kind === "line") {
        f.kind = "line"; f.orientation = "h"; f.width = Math.max(40, pageW() - 30); f.height = 1; f.line_style = "solid";
      } else if (kind === "line_v") {
        f.kind = "line"; f.orientation = "v"; f.width = 1; f.height = 40; f.line_style = "solid";
      } else if (kind === "header") {
        f.width = Math.max(40, pageW() - 30); f.height = 12;
      } else if (kind === "logo") {
        f.width = 40; f.height = 28;
      } else if (kind === "box") {
        f.width = 80; f.height = 24;
        f.fill_colors = defaultFillColors();
        f.border_styles = { top: "solid", right: "solid", bottom: "solid", left: "solid" };
        f.last_line_enable = false;
        f.last_line_style = "solid";
      }
      if (kind === "field" || kind === "row_number") {
        f.source = ""; f.source_key = "";
      }
      frames.push(f); selectedId = f.id; render();
    });
  });

  document.getElementById("btn-undo").addEventListener("click", undo);
  document.getElementById("btn-redo").addEventListener("click", redo);

  function setPreview(on) {
    previewMode = !!on;
    document.body.classList.toggle("preview-mode", previewMode);
    wrap.classList.toggle("preview-mode", previewMode);
    var exitBtn = document.getElementById("btn-exit-preview");
    if (exitBtn) exitBtn.hidden = !previewMode;
    var prevBtn = document.getElementById("btn-preview");
    if (prevBtn) prevBtn.textContent = previewMode ? "بازگشت به طراحی" : "پیش‌نمایش چاپ";
    selectedId = null;
    selectedGuideIdx = null;
    render();
  }
  document.getElementById("btn-preview").addEventListener("click", function () {
    setPreview(!previewMode);
  });
  document.getElementById("btn-exit-preview").addEventListener("click", function () {
    setPreview(false);
  });
  document.getElementById("btn-print").addEventListener("click", function () {
    var was = previewMode;
    setPreview(true);
    setTimeout(function () {
      window.print();
      if (!was) setPreview(false);
    }, 50);
  });

  function deleteSelected() {
    if (selectedGuideIdx != null) {
      pushHistory();
      pageSettings.guides.splice(selectedGuideIdx, 1);
      selectedGuideIdx = null;
      render();
      return;
    }
    var f = find(selectedId);
    if (!f || f.locked) return;
    pushHistory();
    frames = frames.filter(function (x) { return x.id !== f.id; });
    selectedId = null;
    render();
  }
  function copySelected() {
    var f = find(selectedId);
    if (!f) return;
    clipboard = JSON.parse(JSON.stringify(f));
    updateClipboardButtons();
    toast("کپی شد");
  }
  function cutSelected() {
    var f = find(selectedId);
    if (!f || f.locked) return;
    clipboard = JSON.parse(JSON.stringify(f));
    pushHistory();
    frames = frames.filter(function (x) { return x.id !== f.id; });
    selectedId = null;
    render();
    toast("برش شد");
  }
  function pasteClipboard() {
    if (!clipboard) return;
    pushHistory();
    var f = JSON.parse(JSON.stringify(clipboard));
    f.id = "f" + Date.now() + "-" + (uid++);
    f.left = snapMm((f.left || 0) + 5);
    f.y = snapMm((f.y || 0) + 5);
    f.x = f.left;
    f.locked = false;
    frames.push(f);
    selectedId = f.id;
    clipboard = null;
    render();
    toast("جای‌گذاری شد");
  }

  var copyBtnEl = document.getElementById("btn-copy");
  var pasteBtnEl = document.getElementById("btn-paste");
  if (copyBtnEl) copyBtnEl.addEventListener("click", function () { copySelected(); });
  if (pasteBtnEl) pasteBtnEl.addEventListener("click", function () { pasteClipboard(); });

  window.addEventListener("keydown", function (e) {
    if (previewMode) return;
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") { e.preventDefault(); copySelected(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "x") { e.preventDefault(); cutSelected(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "v") { e.preventDefault(); pasteClipboard(); return; }
    if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); deleteSelected(); return; }

    var f = find(selectedId);
    if (!f || f.locked) return;
    var step = e.shiftKey ? Math.max(1, snap) : 1;
    var moved = false;
    function nudge(v, d) {
      var next = Math.round(((v || 0) + d) * 100) / 100;
      return next < 0 ? 0 : next;
    }
    if (e.key === "ArrowLeft") { f.left = nudge(f.left, -step); moved = true; }
    if (e.key === "ArrowRight") { f.left = nudge(f.left, step); moved = true; }
    if (e.key === "ArrowUp") { f.y = nudge(f.y, -step); moved = true; }
    if (e.key === "ArrowDown") { f.y = nudge(f.y, step); moved = true; }
    if (moved) {
      e.preventDefault();
      if (!drag) pushHistory();
      render();
    }
  });

  function gatherPayload() {
    syncHidden();
    return new FormData(formEl);
  }

  function saveAjax(thenClose) {
    var title = document.getElementById("id_title");
    var titleUi = document.getElementById("ui-form-title");
    var numberUi = document.getElementById("ui-form-number");
    var numberHidden = document.getElementById("id_number");
    if (titleUi && title) title.value = titleUi.value || title.value;
    if (numberUi && numberHidden) numberHidden.value = numberUi.value || numberHidden.value;
    if (title && !title.value) title.value = "فرم جدید";
    fetch(saveUrl, {
      method: "POST",
      body: gatherPayload(),
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) {
        toast(data.error || "خطا در ذخیره");
        return;
      }
      if (data.pk) {
        pk = String(data.pk);
        formEl.setAttribute("data-pk", pk);
        formEl.setAttribute("data-mode", "edit");
        mode = "edit";
        saveUrl = data.save_url || saveUrl;
        formEl.setAttribute("data-save-url", saveUrl);
        if (data.title) document.getElementById("dz-window-title").textContent = "ویرایش فرم — " + data.title;
      }
      toast("ذخیره شد");
      if (thenClose) {
        if (window.opener && !window.opener.closed) {
          try { window.opener.location.href = listUrl; } catch (err) {}
          window.close();
        } else {
          window.location.href = listUrl;
        }
      }
    }).catch(function () { toast("خطای شبکه در ذخیره"); });
  }

  document.getElementById("btn-save").addEventListener("click", function () { saveAjax(false); });
  document.getElementById("btn-register").addEventListener("click", function () { saveAjax(true); });

  document.getElementById("dz-close").addEventListener("click", function () {
    if (window.opener) window.close();
    else window.location.href = listUrl;
  });
  document.getElementById("dz-minimize").addEventListener("click", function () {
    try { window.blur(); } catch (e) {}
    toast("از نوار وظیفه مرورگر می‌توانید بازگردید");
  });
  document.getElementById("dz-maximize").addEventListener("click", function () {
    try {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen();
      else document.exitFullscreen();
    } catch (e) {
      try { window.moveTo(0, 0); window.resizeTo(screen.availWidth, screen.availHeight); } catch (err) {}
    }
  });

  // Force LTR number inputs so spinners stay put
  document.querySelectorAll('input[type="number"]').forEach(function (inp) {
    inp.setAttribute("lang", "en");
    inp.setAttribute("dir", "ltr");
    inp.style.unicodeBidi = "isolate";
  });

  syncFormMetaUi();
  syncUiChecks();
  render();
})();
