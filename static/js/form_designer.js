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
    try {
      f.sheet = Math.max(1, Math.min(200, parseInt(f.sheet, 10) || 1));
    } catch (e) {
      f.sheet = 1;
    }
    var isShape = f.kind === "box" || f.kind === "line" || f.kind === "line_h" || f.kind === "line_v";
    if (isShape) {
      if (f.extend_mode !== "page" && f.extend_mode !== "field" && f.extend_mode !== "none" && f.extend_mode !== "count") {
        f.extend_mode = f.data_extend ? "field" : "none";
      }
      if (f.extend_mode === "count") {
        var ec = parseInt(f.extend_count, 10);
        f.extend_count = Math.max(1, Math.min(99, isNaN(ec) ? 2 : ec));
      }
    } else {
      delete f.extend_mode;
      delete f.extend_count;
    }
    delete f.data_extend;
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
  var selectedIds = [];
  var selectedGuideIdx = null;
  var zoom = 1;
  var snap = pageSettings.snap_mm || 2;
  var uid = 1;
  var history = [];
  var future = [];
  var previewMode = false;
  var guidesEnabled = true;
  var paperCustomMode = false;
  var formPurpose = "";
  var linkedReportId = "";
  var reportLevelFilter = "";
  var currentSheet = 1;
  var purposeCatalogs = {};
  var savedReports = [];
  try { purposeCatalogs = JSON.parse(document.getElementById("purpose-catalogs").textContent || "{}") || {}; } catch (e) {}
  try { savedReports = JSON.parse(document.getElementById("saved-reports").textContent || "[]") || []; } catch (e) {}
  var purposeHidden = document.getElementById("id_purpose");
  var linkedReportHidden = document.getElementById("id_linked_report");
  if (purposeHidden) formPurpose = purposeHidden.value || "";
  if (linkedReportHidden) linkedReportId = linkedReportHidden.value || "";
  var dragGuide = null;
  var clipboard = null;
  var drag = null;
  var layerDragId = null;

  var hiddenFrames = document.getElementById("id_frames_json");
  var hiddenSettings = document.getElementById("id_page_settings_json");
  var pageWInput = document.getElementById("id_page_width_mm");
  var pageHInput = document.getElementById("id_page_height_mm");
  (function () {
    var PRESETS0 = { "A4-P": [210, 297], "A4-L": [297, 210], "A5-P": [148, 210], "A5-L": [210, 148] };
    var w0 = parseFloat(pageWInput && pageWInput.value) || 210;
    var h0 = parseFloat(pageHInput && pageHInput.value) || 297;
    var match0 = false;
    Object.keys(PRESETS0).forEach(function (k) {
      if (PRESETS0[k][0] === w0 && PRESETS0[k][1] === h0) match0 = true;
    });
    paperCustomMode = !match0;
  })();
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

  function frameSheet(f) {
    try {
      return Math.max(1, Math.min(200, parseInt(f && f.sheet, 10) || 1));
    } catch (e) {
      return 1;
    }
  }

  function linkedReportMeta() {
    if (!linkedReportId) return null;
    return savedReports.find(function (r) { return String(r.id) === String(linkedReportId); }) || null;
  }

  function reportSheetCount() {
    var rep = linkedReportMeta();
    var n = 1;
    if (rep) {
      try { n = Math.max(1, parseInt(rep.sheet_count, 10) || 1); } catch (e) { n = 1; }
    }
    frames.forEach(function (f) {
      n = Math.max(n, frameSheet(f));
    });
    return n;
  }

  function sheetsEnabled() {
    if (formPurpose !== "reports" || !linkedReportId) return false;
    var rep = linkedReportMeta();
    return !!(rep && rep.access_mode === "editable");
  }

  function visibleFrames() {
    if (!sheetsEnabled()) return frames;
    return frames.filter(function (f) { return frameSheet(f) === currentSheet; });
  }
  function isSelected(id) { return selectedIds.indexOf(id) >= 0; }
  function clearSelection() { selectedId = null; selectedIds = []; }
  function selectOnly(id) {
    selectedId = id || null;
    selectedIds = id ? [id] : [];
  }
  function toggleSelect(id) {
    var idx = selectedIds.indexOf(id);
    if (idx >= 0) selectedIds.splice(idx, 1);
    else selectedIds.push(id);
    selectedId = selectedIds.length ? selectedIds[selectedIds.length - 1] : null;
  }
  function toast(msg) {
    var t = document.getElementById("dz-toast");
    t.textContent = msg; t.classList.add("show");
    setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  function cloneState() {
    return JSON.stringify({
      frames: frames,
      pageSettings: pageSettings,
      pageW: pageW(),
      pageH: pageH(),
      currentSheet: currentSheet
    });
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
    if (s.currentSheet != null) {
      try { currentSheet = Math.max(1, parseInt(s.currentSheet, 10) || 1); } catch (e) { currentSheet = 1; }
    }
    clearSelection();
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
    if (style === "thick") return "3px solid #111";
    if (style === "dashed") return "1.5px dashed #111";
    if (style === "dotted") return "1.5px dotted #111";
    if (style === "dashdot") return "2px dashed #333";
    return "1.5px solid #111";
  }

  var LINE_STYLE_OPTS = [
    { v: "solid", t: "ممتد", preview: "solid" },
    { v: "thick", t: "ضخیم", preview: "thick" },
    { v: "dashed", t: "خط‌چین", preview: "dashed" },
    { v: "dotted", t: "نقطه‌چین", preview: "dotted" },
    { v: "dashdot", t: "ترکیبی", preview: "dashdot" },
    { v: "none", t: "بدون خط", preview: "none" }
  ];

  function lineOptByValue(value) {
    for (var i = 0; i < LINE_STYLE_OPTS.length; i++) {
      if (LINE_STYLE_OPTS[i].v === value) return LINE_STYLE_OPTS[i];
    }
    return LINE_STYLE_OPTS[0];
  }

  function closeAllLineMenus(except) {
    document.querySelectorAll(".line-style-picker.is-open").forEach(function (p) {
      if (p !== except) p.classList.remove("is-open");
    });
  }

  function buildLineStylePickers() {
    document.querySelectorAll("[data-line-picker]").forEach(function (picker) {
      if (picker.dataset.built) return;
      picker.dataset.built = "1";
      picker.classList.add("ls-dropdown");
      var allowNone = picker.getAttribute("data-allow-none") === "1";
      var targetId = picker.getAttribute("data-line-picker");

      var trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "ls-trigger";
      trigger.innerHTML =
        '<span class="ls-preview ls-solid" data-ls-preview></span>' +
        '<span class="ls-caption" data-ls-label>ممتد</span>' +
        '<span class="ls-caret">▾</span>';

      var menu = document.createElement("div");
      menu.className = "ls-menu";
      menu.hidden = true;

      LINE_STYLE_OPTS.forEach(function (opt) {
        if (opt.v === "none" && !allowNone) return;
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ls-btn";
        btn.dataset.value = opt.v;
        btn.title = opt.t;
        btn.innerHTML =
          '<span class="ls-preview ls-' + opt.preview + '"></span>' +
          '<span class="ls-caption">' + opt.t + "</span>";
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          if (picker.classList.contains("is-disabled")) return;
          var hidden = document.getElementById(targetId);
          if (!hidden) return;
          hidden.value = opt.v;
          syncLinePicker(picker, opt.v);
          picker.classList.remove("is-open");
          menu.hidden = true;
          hidden.dispatchEvent(new Event("change", { bubbles: true }));
        });
        menu.appendChild(btn);
      });

      trigger.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (picker.classList.contains("is-disabled")) return;
        var open = !picker.classList.contains("is-open");
        closeAllLineMenus(picker);
        picker.classList.toggle("is-open", open);
        menu.hidden = !open;
      });

      picker.appendChild(trigger);
      picker.appendChild(menu);
      syncLinePicker(picker, (document.getElementById(targetId) || {}).value || "solid");
    });

    if (!window.__lsMenuDocWired) {
      window.__lsMenuDocWired = true;
      document.addEventListener("click", function () {
        closeAllLineMenus(null);
        document.querySelectorAll(".ls-menu").forEach(function (m) { m.hidden = true; });
      });
    }
  }

  function syncLinePicker(picker, value) {
    if (!picker) return;
    var opt = lineOptByValue(value || "solid");
    var preview = picker.querySelector("[data-ls-preview]");
    var label = picker.querySelector("[data-ls-label]");
    if (preview) {
      preview.className = "ls-preview ls-" + opt.preview;
      preview.setAttribute("data-ls-preview", "");
    }
    if (label) label.textContent = opt.t;
    picker.querySelectorAll(".ls-btn").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.dataset.value === opt.v);
    });
  }

  function setLinePickerValue(inputId, value) {
    var hidden = document.getElementById(inputId);
    if (hidden) hidden.value = value;
    var picker = document.querySelector('[data-line-picker="' + inputId + '"]');
    syncLinePicker(picker, value);
  }

  function setLinePickerDisabled(inputId, disabled) {
    var picker = document.querySelector('[data-line-picker="' + inputId + '"]');
    if (!picker) return;
    picker.classList.toggle("is-disabled", !!disabled);
    if (disabled) {
      picker.classList.remove("is-open");
      var menu = picker.querySelector(".ls-menu");
      if (menu) menu.hidden = true;
    }
  }

  var THEME_COLORS = [
    "#ffffff", "#000000", "#e7e6e6", "#44546a", "#5b9bd5", "#ed7d31", "#a5a5a5", "#ffc000", "#4472c4", "#70ad47",
    "#f2f2f2", "#7f7f7f", "#d0cece", "#d6dce4", "#ddebf7", "#fce4d6", "#ededed", "#fff2cc", "#d6dce4", "#e2efda",
    "#d8d8d8", "#595959", "#aeabab", "#adb9ca", "#bdd7ee", "#f8cbad", "#dbdbdb", "#ffe699", "#b4c6e7", "#c6efce",
    "#bfbfbf", "#3f3f3f", "#757070", "#8496b0", "#9bc2e6", "#f4b183", "#c9c9c9", "#ffd966", "#8ea9db", "#a9d08e",
    "#a5a5a5", "#262626", "#3a3838", "#323f4f", "#2f5496", "#c65911", "#7b7b7b", "#bf8f00", "#2f5496", "#548235",
    "#7f7f7f", "#0d0d0d", "#171616", "#222a35", "#1f4e79", "#833c0c", "#525252", "#806000", "#1f4e79", "#375623"
  ];
  var STANDARD_COLORS = [
    "#c00000", "#ff0000", "#ffc000", "#ffff00", "#92d050", "#00b050", "#00b0f0", "#0070c0", "#002060", "#7030a0"
  ];

  function closeColorPanel() {
    var panel = document.getElementById("tb-color-panel");
    if (panel) panel.hidden = true;
  }

  function syncColorSwatch(hex) {
    var sw = document.getElementById("tb-font-color-swatch");
    var hidden = document.getElementById("tb-font-color");
    var native = document.getElementById("tb-font-color-native");
    if (hidden) hidden.value = hex;
    if (native) native.value = hex;
    if (sw) sw.style.background = hex;
  }

  function buildColorPalette() {
    var theme = document.getElementById("tb-color-theme");
    var standard = document.getElementById("tb-color-standard");
    if (!theme || theme.dataset.built) return;
    theme.dataset.built = "1";
    function addSwatches(host, colors) {
      colors.forEach(function (hex) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "dz-color-chip";
        b.style.background = hex;
        b.title = hex;
        b.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          applyFontColor(hex);
          closeColorPanel();
        });
        host.appendChild(b);
      });
    }
    addSwatches(theme, THEME_COLORS);
    addSwatches(standard, STANDARD_COLORS);
  }

  function applyFontColor(hex) {
    var f = find(selectedId);
    if (!isTextish(f) || f.locked) return;
    pushHistory();
    f.font_color = hex;
    syncColorSwatch(hex);
    render();
  }

  function applyTextStyle(el, f) {
    if (!el || !f) return;
    el.style.fontFamily = f.font_family || "";
    el.style.fontSize = f.font_size ? (f.font_size + "px") : "";
    el.style.color = f.font_color || "";
    el.style.fontWeight = f.font_bold ? "700" : "";
    el.style.fontStyle = f.font_italic ? "italic" : "";
    el.style.textDecoration = f.font_underline ? "underline" : "";
  }

  function isTextish(f) {
    return !!(f && (f.kind === "header" || f.kind === "field" || f.kind === "box" || f.kind === "row_number"));
  }

  function defaultFillColors() {
    return ["#ffffff", "#e8f0fe"];
  }

  function updateClipboardButtons() {
    var copyBtn = document.getElementById("btn-copy");
    var pasteBtn = document.getElementById("btn-paste");
    if (copyBtn) {
      copyBtn.disabled = !selectedIds.length;
      copyBtn.classList.toggle("is-ready", !!selectedIds.length);
    }
    if (pasteBtn) {
      pasteBtn.disabled = !clipboard;
      pasteBtn.classList.toggle("is-ready", !!clipboard);
    }
  }

  function ensureBindings(f) {
    if (!f) return [];
    if (!Array.isArray(f.bindings) || !f.bindings.length) {
      if (f.source || f.source_key) {
        f.bindings = [{ source: f.source || "", source_key: f.source_key || "" }];
      } else {
        f.bindings = [{ source: "", source_key: "" }];
      }
    }
    f.source = f.bindings[0].source || "";
    f.source_key = f.bindings[0].source_key || "";
    return f.bindings;
  }

  function bindingPathText(f) {
    var binds = ensureBindings(f);
    var parts = [];
    binds.forEach(function (b) {
      if (b.source && b.source_key) parts.push(b.source + " → " + b.source_key);
    });
    return parts.length ? ("آدرس: " + parts.join("  |  ")) : "وصل نشده";
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
    if (!paperCustomMode) {
      Object.keys(PRESETS).forEach(function (k) { if (PRESETS[k][0] === w && PRESETS[k][1] === h) found = k; });
    }
    document.getElementById("paper-preset").value = found;
    var wEl = document.getElementById("prop-page-w");
    var hEl = document.getElementById("prop-page-h");
    var isCustom = found === "custom" || paperCustomMode;
    if (isCustom) paperCustomMode = true;
    wEl.disabled = !isCustom;
    hEl.disabled = !isCustom;
    wEl.readOnly = !isCustom;
    hEl.readOnly = !isCustom;
    wEl.classList.toggle("is-locked-size", !isCustom);
    hEl.classList.toggle("is-locked-size", !isCustom);
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

  function extendModeOf(f) {
    if (f.extend_mode === "page" || f.extend_mode === "field" || f.extend_mode === "none" || f.extend_mode === "count") {
      return f.extend_mode;
    }
    if (f.data_extend) return "field";
    return "none";
  }

  /** Designer preview mirrors detail view: fields = 1; box/line page = bottom; count = N; field = 1. */
  function copiesForFrame(f) {
    var mode = extendModeOf(f);
    if (f.kind === "field" || f.kind === "row_number") {
      return 1;
    }
    if (f.kind === "box" || isLineKind(f.kind)) {
      if (mode === "page") return estimateExtendRows(f);
      if (mode === "count") {
        var n = parseInt(f.extend_count, 10);
        return Math.max(1, Math.min(99, isNaN(n) ? 1 : n));
      }
      return 1;
    }
    return 1;
  }

  function renderLayers() {
    var list = document.getElementById("layers-list");
    list.innerHTML = "";
    visibleFrames().slice().reverse().forEach(function (f) {
      var row = document.createElement("div");
      row.className = "dz-clip" + (isSelected(f.id) ? " is-active" : "") + (f.hidden ? " is-layer-hidden" : "") + (f.locked ? " is-locked" : "");
      row.draggable = true;
      row.dataset.id = f.id;
      row.innerHTML =
        '<span class="dz-drag-handle" title="جابجایی لایه">⋮⋮</span>' +
        '<span class="name">' + kindLabel(f.kind, f) + " — " + (f.label || "بدون نام") + "</span>" +
        '<button type="button" class="dz-icon-btn dz-lock' + (f.locked ? " on" : "") + '" title="' + (f.locked ? "باز کردن قفل" : "قفل کردن") + '">' +
          (f.locked
            ? '<span class="dz-lock-glyph" aria-hidden="true">🔒</span>'
            : '<span class="dz-lock-glyph" aria-hidden="true">🔓</span>') +
        "</button>" +
        '<button type="button" class="dz-icon-btn dz-eye' + (f.hidden ? " off" : "") + '" title="مخفی/نمایش"' + (f.locked ? " disabled" : "") + ">" +
          '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.2C4.2 3.2 1.3 6.1.5 8c.8 1.9 3.7 4.8 7.5 4.8S14.7 9.9 15.5 8C14.7 6.1 11.8 3.2 8 3.2zm0 7.6A2.8 2.8 0 1 1 8 5.2a2.8 2.8 0 0 1 0 5.6z"/></svg>' +
        "</button>" +
        '<button type="button" class="dz-icon-btn del" title="حذف"' + (f.locked ? " disabled" : "") + ">" +
          '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.2 4.2 8 8l3.8-3.8 1.2 1.2L9.2 9.2l3.8 3.8-1.2 1.2L8 10.4l-3.8 3.8-1.2-1.2 3.8-3.8-3.8-3.8z"/></svg>' +
        "</button>";
      row.addEventListener("click", function (e) {
        if (e.target.closest(".dz-icon-btn")) return;
        if (e.ctrlKey || e.metaKey) toggleSelect(f.id);
        else selectOnly(f.id);
        selectedGuideIdx = null; render();
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
        selectedIds = selectedIds.filter(function (id) { return id !== f.id; });
        selectedId = selectedIds.length ? selectedIds[selectedIds.length - 1] : null;
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
        selectOnly(layerDragId);
        render();
      });
      list.appendChild(row);
    });
  }

  function updateAlignButtons() {
    var f = find(selectedId);
    var textish = isTextish(f);
    document.querySelectorAll("#align-group button").forEach(function (btn) {
      btn.disabled = !textish;
      btn.classList.toggle("active",
        !!(textish && ((btn.dataset.align && btn.dataset.align === f.align) ||
          (btn.dataset.valign && btn.dataset.valign === f.valign)))
      );
    });
    updateFontToolbar();
  }

  function updateFontToolbar() {
    var f = find(selectedId);
    var textish = isTextish(f) && !(f && f.locked);
    var fam = document.getElementById("tb-font-family");
    var size = document.getElementById("tb-font-size");
    var colorBtn = document.getElementById("tb-font-color-btn");
    var bold = document.getElementById("tb-font-bold");
    var italic = document.getElementById("tb-font-italic");
    var under = document.getElementById("tb-font-underline");
    [fam, size, colorBtn, bold, italic, under].forEach(function (el) {
      if (el) el.disabled = !textish;
    });
    if (!textish) closeColorPanel();
    if (!textish || !f) {
      if (bold) bold.classList.remove("active");
      if (italic) italic.classList.remove("active");
      if (under) under.classList.remove("active");
      return;
    }
    if (fam) {
      var want = f.font_family || "Tahoma";
      var matched = false;
      Array.prototype.forEach.call(fam.options, function (o) {
        if (o.value === want) matched = true;
      });
      if (!matched) {
        var opt = document.createElement("option");
        opt.value = want;
        opt.textContent = want.split(",")[0].replace(/['"]/g, "");
        fam.appendChild(opt);
      }
      fam.value = want;
    }
    if (size) size.value = String(f.font_size || 12);
    syncColorSwatch(f.font_color || "#111111");
    if (bold) bold.classList.toggle("active", !!f.font_bold);
    if (italic) italic.classList.toggle("active", !!f.font_italic);
    if (under) under.classList.toggle("active", !!f.font_underline);
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

  function syncSheetUi() {
    var wrapEl = document.getElementById("report-sheet-controls");
    var sheetUi = document.getElementById("ui-form-sheet");
    var transferUi = document.getElementById("ui-transfer-from");
    if (!wrapEl || !sheetUi || !transferUi) return;
    var enabled = sheetsEnabled();
    wrapEl.hidden = !enabled;
    if (!enabled) {
      currentSheet = 1;
      return;
    }
    var count = reportSheetCount();
    if (currentSheet > count) currentSheet = 1;
    sheetUi.innerHTML = "";
    for (var i = 1; i <= count; i++) {
      var o = document.createElement("option");
      o.value = String(i);
      o.textContent = "برگه " + i;
      sheetUi.appendChild(o);
    }
    sheetUi.value = String(currentSheet);
    transferUi.innerHTML = '<option value="">— انتخاب برگه —</option>';
    for (var j = 1; j <= count; j++) {
      if (j === currentSheet) continue;
      var t = document.createElement("option");
      t.value = String(j);
      t.textContent = "برگه " + j;
      transferUi.appendChild(t);
    }
  }

  function transferSheetFrom(sourceSheet) {
    sourceSheet = parseInt(sourceSheet, 10);
    if (isNaN(sourceSheet) || sourceSheet < 1 || sourceSheet === currentSheet) {
      toast("برگه مبدأ معتبر نیست");
      return;
    }
    var srcFrames = frames.filter(function (f) { return frameSheet(f) === sourceSheet; });
    if (!srcFrames.length) {
      toast("برگه مبدأ خالی است");
      return;
    }
    pushHistory();
    frames = frames.filter(function (f) { return frameSheet(f) !== currentSheet; });
    srcFrames.forEach(function (src, i) {
      var f = JSON.parse(JSON.stringify(src));
      f.id = "f" + Date.now() + "-" + (uid++) + "-t" + i;
      f.sheet = currentSheet;
      frames.push(f);
    });
    clearSelection();
    render();
    toast("محتوای برگه " + sourceSheet + " به برگه " + currentSheet + " منتقل شد");
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
      fillSources(f);
    }
    if (f.kind === "box" || isLineKind(f.kind)) {
      document.getElementById("prop-extend-mode").value = extendModeOf(f);
      var countWrap = document.getElementById("extend-count-wrap");
      var countInp = document.getElementById("prop-extend-count");
      var isCount = extendModeOf(f) === "count";
      if (countWrap) countWrap.hidden = false;
      if (countInp) {
        countInp.disabled = !isCount;
        countInp.value = f.extend_count || 2;
      }
    }
    if (isLineKind(f.kind)) {
      setLinePickerValue("prop-line-style", f.line_style || "solid");
    }
    if (f.kind === "box") {
      var bs = f.border_styles || {};
      setLinePickerValue("prop-border-top", bs.top || "solid");
      setLinePickerValue("prop-border-bottom", bs.bottom || "solid");
      setLinePickerValue("prop-border-right", bs.right || "solid");
      setLinePickerValue("prop-border-left", bs.left || "solid");
      document.getElementById("prop-last-line-enable").checked = !!f.last_line_enable;
      setLinePickerValue("prop-last-line-style", f.last_line_style || "solid");
      setLinePickerDisabled("prop-last-line-style", !f.last_line_enable);
      renderFillPatternUI(f);
    }
  }

  function activeSourceGroups() {
    if (formPurpose === "reports") {
      var rep = savedReports.find(function (r) { return String(r.id) === String(linkedReportId); });
      return (rep && rep.levels) ? rep.levels : [];
    }
    if (formPurpose && purposeCatalogs[formPurpose]) {
      return purposeCatalogs[formPurpose];
    }
    return groups;
  }

  function fillSources(f) {
    var srcSel = document.getElementById("prop-source");
    var keySel = document.getElementById("prop-source-key");
    var levelWrap = document.getElementById("report-level-wrap");
    var levelSel = document.getElementById("prop-report-level");
    var extraHost = document.getElementById("extra-key-bindings");
    var addBindBtn = document.getElementById("btn-add-key-bind");
    var active = activeSourceGroups();
    var binds = ensureBindings(f);

    function populateSourceSelect(sel, selected) {
      sel.innerHTML = '<option value="">— منبع —</option>';
      active.forEach(function (g) {
        if (g.enabled === false) {
          var oDis = document.createElement("option");
          oDis.value = g.id;
          oDis.textContent = g.label + " (هنوز ایجاد نشده)";
          oDis.disabled = true;
          sel.appendChild(oDis);
          return;
        }
        var o = document.createElement("option");
        o.value = g.id;
        o.textContent = g.label;
        sel.appendChild(o);
      });
      sel.value = selected || "";
    }

    function populateKeySelect(sel, sourceId, selected) {
      sel.innerHTML = '<option value="">— ستون —</option>';
      var g = active.find(function (x) { return x.id === sourceId; });
      if (g) (g.columns || []).forEach(function (c) {
        var o = document.createElement("option");
        o.value = c[0];
        o.textContent = c[1];
        sel.appendChild(o);
      });
      sel.value = selected || "";
    }

    function populateLevelSelect(sel, selected) {
      sel.innerHTML = "";
      active.forEach(function (g) {
        var o = document.createElement("option");
        o.value = g.id;
        o.textContent = g.label;
        sel.appendChild(o);
      });
      sel.value = selected || (active[0] && active[0].id) || "";
    }

    if (levelWrap && levelSel) {
      var showLevel = formPurpose === "reports" && !!linkedReportId && active.length > 0;
      levelWrap.hidden = !showLevel;
      if (showLevel) {
        populateLevelSelect(levelSel, binds[0].source || reportLevelFilter);
        reportLevelFilter = levelSel.value;
        binds[0].source = levelSel.value;
        f.source = levelSel.value;
        levelSel.onchange = function () {
          pushHistory();
          reportLevelFilter = levelSel.value;
          binds[0].source = levelSel.value;
          binds[0].source_key = "";
          f.source = levelSel.value;
          f.source_key = "";
          fillSources(f);
          render();
        };
      }
    }

    populateSourceSelect(srcSel, binds[0].source || "");
    if (formPurpose === "reports" && (binds[0].source || reportLevelFilter)) {
      srcSel.value = binds[0].source || reportLevelFilter;
      binds[0].source = srcSel.value;
      f.source = srcSel.value;
    }

    populateKeySelect(keySel, srcSel.value, binds[0].source_key || "");
    document.getElementById("field-bind-path").textContent = bindingPathText(f);

    srcSel.onchange = function () {
      pushHistory();
      binds[0].source = srcSel.value;
      binds[0].source_key = "";
      f.source = srcSel.value;
      f.source_key = "";
      if (formPurpose === "reports") reportLevelFilter = srcSel.value;
      fillSources(f);
      render();
    };
    keySel.onchange = function () {
      pushHistory();
      binds[0].source_key = keySel.value;
      f.source_key = keySel.value;
      document.getElementById("field-bind-path").textContent = bindingPathText(f);
      render();
    };

    if (extraHost) {
      extraHost.innerHTML = "";
      for (var bi = 1; bi < binds.length; bi++) {
        (function (bindIndex) {
          var block = document.createElement("div");
          block.className = "key-bind-extra";
          block.style.cssText = "margin-top:8px;padding-top:8px;border-top:1px dashed #cbd5e1";
          var head = document.createElement("div");
          head.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:4px";
          head.innerHTML = "<strong style='font-size:12px'>اتصال " + (bindIndex + 1) + "</strong>";
          var rm = document.createElement("button");
          rm.type = "button";
          rm.className = "btn btn-xs btn-ghost";
          rm.textContent = "حذف";
          rm.onclick = function () {
            pushHistory();
            binds.splice(bindIndex, 1);
            ensureBindings(f);
            fillSources(f);
            render();
          };
          head.appendChild(rm);
          block.appendChild(head);

          if (formPurpose === "reports" && linkedReportId && active.length) {
            var lvField = document.createElement("div");
            lvField.className = "dz-field";
            lvField.innerHTML = "<label>انتخاب سطح گزارش</label>";
            var lv = document.createElement("select");
            populateLevelSelect(lv, binds[bindIndex].source || "");
            lv.onchange = function () {
              pushHistory();
              binds[bindIndex].source = lv.value;
              binds[bindIndex].source_key = "";
              fillSources(f);
              render();
            };
            lvField.appendChild(lv);
            block.appendChild(lvField);
          }

          var srcField = document.createElement("div");
          srcField.className = "dz-field";
          srcField.innerHTML = "<label>منبع</label>";
          var src = document.createElement("select");
          populateSourceSelect(src, binds[bindIndex].source || "");
          src.onchange = function () {
            pushHistory();
            binds[bindIndex].source = src.value;
            binds[bindIndex].source_key = "";
            fillSources(f);
            render();
          };
          srcField.appendChild(src);
          block.appendChild(srcField);

          var keyField = document.createElement("div");
          keyField.className = "dz-field";
          keyField.innerHTML = "<label>ستون</label>";
          var key = document.createElement("select");
          populateKeySelect(key, binds[bindIndex].source || "", binds[bindIndex].source_key || "");
          key.onchange = function () {
            pushHistory();
            binds[bindIndex].source_key = key.value;
            document.getElementById("field-bind-path").textContent = bindingPathText(f);
            render();
          };
          keyField.appendChild(key);
          block.appendChild(keyField);
          extraHost.appendChild(block);
        })(bi);
      }
    }

    if (addBindBtn) {
      addBindBtn.onclick = function () {
        pushHistory();
        ensureBindings(f).push({ source: "", source_key: "" });
        fillSources(f);
        render();
      };
    }
  }

  function syncPurposeUi() {
    var purposeSel = document.getElementById("ui-form-purpose");
    var reportWrap = document.getElementById("report-name-wrap");
    var reportSel = document.getElementById("ui-linked-report");
    if (purposeSel) purposeSel.value = formPurpose || "";
    if (purposeHidden) purposeHidden.value = formPurpose || "";
    if (linkedReportHidden) linkedReportHidden.value = linkedReportId || "";
    if (reportWrap && reportSel) {
      var showRep = formPurpose === "reports";
      reportWrap.hidden = !showRep;
      if (showRep) {
        reportSel.innerHTML = '<option value="">— انتخاب گزارش —</option>';
        savedReports.forEach(function (r) {
          var o = document.createElement("option");
          o.value = String(r.id);
          o.textContent = r.number + " — " + r.title;
          reportSel.appendChild(o);
        });
        reportSel.value = linkedReportId || "";
      }
    }
  }

  function render() {
    syncHidden();
    syncUiChecks();
    syncPurposeUi();
    syncFormMetaUi();
    syncSheetUi();
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
          clearSelection();
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

    var sheetFrames = visibleFrames();
    var masterField = sheetFrames.find(function (fr) {
      return !fr.hidden && fr.kind === "field";
    });
    var rowStep = masterField ? Math.max(masterField.height || 8, 6) : 14;

    var pending = [];
    var boxInstances = [];

    sheetFrames.forEach(function (f, zi) {
      if (f.hidden) return;
      var copies = 1;
      if (previewMode) {
        copies = copiesForFrame(f);
      }
      var step = (f.kind === "field" || f.kind === "row_number")
        ? Math.max(f.height || 8, 6)
        : rowStep;
      if ((f.kind === "box" || isLineKind(f.kind)) && extendModeOf(f) === "count") {
        step = rowStep;
      }
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
        var mode = extendModeOf(f);
        var el = document.createElement("div");
        el.className = "dz-frame kind-" + (f.kind || "box") +
          (isSelected(f.id) && i === 0 && !previewMode ? " selected" : "") +
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
        applyTextStyle(inner, f);

        if (f.kind === "box") {
          var fills = (f.fill_colors && f.fill_colors.length) ? f.fill_colors : defaultFillColors();
          el.style.background = fills[i % fills.length];
          var bs = f.border_styles || {};
          var repeats = mode === "page" || mode === "field" || mode === "count";
          var isLast = previewMode && repeats && (i === item.copies - 1) && f.last_line_enable;
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
            if (window.ERPFormSheetRender && window.ERPFormSheetRender.resolveFieldDisplay) {
              inner.textContent = window.ERPFormSheetRender.resolveFieldDisplay(activeSourceGroups(), f, {}) || "";
            } else {
              inner.textContent = columnLabel(f.source, f.source_key) || "";
            }
          } else {
            var txt = f.label || "کلید منابع";
            var binds = ensureBindings(f).filter(function (b) { return b.source && b.source_key; });
            if (binds.length) {
              txt += " ⟨" + binds.map(function (b) { return b.source + "." + b.source_key; }).join(" + ") + "⟩";
            }
            inner.textContent = txt;
          }
        } else if (f.kind !== "box") {
          inner.textContent = f.label || kindLabel(f.kind);
        } else if (f.label && !previewMode) {
          inner.textContent = f.label;
        } else if (f.label && previewMode && mode === "none") {
          inner.textContent = f.label;
        }
        el.appendChild(inner);

        if (!previewMode && i === 0 && (f.kind === "box" || isLineKind(f.kind))) {
          if (mode === "page" || mode === "field" || mode === "count") {
            var badge = document.createElement("span");
            badge.className = "badge-extend";
            if (mode === "page") badge.textContent = "تا پایین صفحه";
            else if (mode === "field") badge.textContent = "وابسته به فیلد";
            else badge.textContent = "تعداد: " + (f.extend_count || 1);
            el.appendChild(badge);
          }
        }

        if (i === 0) {
          el.dataset.id = f.id;
          if (!previewMode) {
            el.addEventListener("mousedown", startDrag);
            if (isSelected(f.id) && selectedIds.length === 1) {
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
  document.getElementById("prop-extend-mode").addEventListener("change", function () {
    var f = find(selectedId); if (!f || (f.kind !== "box" && !isLineKind(f.kind))) return;
    pushHistory();
    f.extend_mode = this.value;
    delete f.data_extend;
    if (f.extend_mode === "count" && !f.extend_count) f.extend_count = 2;
    var countInp = document.getElementById("prop-extend-count");
    if (countInp) {
      countInp.disabled = f.extend_mode !== "count";
      if (f.extend_mode === "count") countInp.value = f.extend_count || 2;
    }
    render();
  });
  document.getElementById("prop-extend-count").addEventListener("change", function () {
    var f = find(selectedId); if (!f || (f.kind !== "box" && !isLineKind(f.kind))) return;
    pushHistory();
    var n = parseInt(this.value, 10);
    f.extend_count = Math.max(1, Math.min(99, isNaN(n) ? 1 : n));
    this.value = f.extend_count;
    render();
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
    setLinePickerDisabled("prop-last-line-style", !this.checked);
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

  function wireFontToolbar() {
    var fam = document.getElementById("tb-font-family");
    var size = document.getElementById("tb-font-size");
    var colorBtn = document.getElementById("tb-font-color-btn");
    var colorPanel = document.getElementById("tb-color-panel");
    var colorMore = document.getElementById("tb-color-more");
    var colorNative = document.getElementById("tb-font-color-native");
    var bold = document.getElementById("tb-font-bold");
    var italic = document.getElementById("tb-font-italic");
    var under = document.getElementById("tb-font-underline");
    function applyFont(mutator) {
      var f = find(selectedId);
      if (!isTextish(f) || f.locked) return;
      pushHistory();
      mutator(f);
      render();
    }
    buildColorPalette();
    syncColorSwatch("#111111");
    if (fam) fam.addEventListener("change", function () {
      applyFont(function (f) { f.font_family = fam.value; });
    });
    if (size) size.addEventListener("change", function () {
      applyFont(function (f) { f.font_size = parseInt(size.value, 10) || 12; });
    });
    if (colorBtn && colorPanel) {
      colorBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (colorBtn.disabled) return;
        colorPanel.hidden = !colorPanel.hidden;
      });
    }
    if (colorMore && colorNative) {
      colorMore.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeColorPanel();
        colorNative.click();
      });
    }
    if (colorNative) {
      colorNative.addEventListener("input", function () {
        applyFontColor(colorNative.value);
      });
    }
    if (bold) bold.addEventListener("click", function () {
      applyFont(function (f) { f.font_bold = !f.font_bold; });
    });
    if (italic) italic.addEventListener("click", function () {
      applyFont(function (f) { f.font_italic = !f.font_italic; });
    });
    if (under) under.addEventListener("click", function () {
      applyFont(function (f) { f.font_underline = !f.font_underline; });
    });
    document.addEventListener("click", function (e) {
      var wrap = document.getElementById("tb-color-wrap");
      if (wrap && !wrap.contains(e.target)) closeColorPanel();
    });
  }
  wireFontToolbar();
  buildLineStylePickers();

  var PRESETS = { "A4-P": [210, 297], "A4-L": [297, 210], "A5-P": [148, 210], "A5-L": [210, 148] };
  document.getElementById("paper-preset").addEventListener("change", function () {
    var v = this.value;
    if (v === "custom") {
      paperCustomMode = true;
      render();
      return;
    }
    if (PRESETS[v]) {
      pushHistory();
      paperCustomMode = false;
      pageWInput.value = PRESETS[v][0]; pageHInput.value = PRESETS[v][1];
    }
    render();
  });
  ["prop-page-w","prop-page-h"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
      if (this.disabled) return;
      pushHistory();
      paperCustomMode = true;
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
    var id = e.currentTarget.dataset.id;
    selectedGuideIdx = null;
    if (e.ctrlKey || e.metaKey) {
      toggleSelect(id);
      render();
      return;
    }
    if (!isSelected(id) || selectedIds.length <= 1) {
      selectOnly(id);
    } else {
      selectedId = id;
    }
    var f = find(selectedId);
    if (!f) return;
    if (f.locked && selectedIds.length === 1) { render(); return; }
    pushHistory();
    var origins = {};
    selectedIds.forEach(function (sid) {
      var ff = find(sid);
      if (!ff) return;
      origins[sid] = { ox: ff.left || 0, oy: ff.y || 0 };
    });
    drag = {
      mode: "move",
      id: selectedId,
      ids: selectedIds.slice(),
      origins: origins,
      startX: e.clientX,
      startY: e.clientY,
      ox: f.left || 0,
      oy: f.y || 0
    };
    render();
  }
  function startResize(e) {
    e.preventDefault(); e.stopPropagation();
    var id = e.currentTarget.parentElement.dataset.id;
    var f = find(id); if (!f || f.locked) return;
    selectOnly(id); selectedGuideIdx = null;
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
    selectOnly(id);
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
      if (drag.ids && drag.origins) {
        drag.ids.forEach(function (sid) {
          var ff = find(sid);
          var o = drag.origins[sid];
          if (!ff || !o || ff.locked) return;
          ff.left = snapMm(Math.max(0, o.ox + dx));
          ff.y = snapMm(Math.max(0, o.oy + dy));
        });
      } else {
        f.left = snapMm(Math.max(0, drag.ox + dx));
        f.y = snapMm(Math.max(0, drag.oy + dy));
      }
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
      clearSelection(); selectedGuideIdx = null; render();
    }
  });

  function startGuideFromRuler(axis, e) {
    if (!guidesEnabled || !pageSettings.show_ruler) return;
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    clearSelection();
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
        kind: kind, left: 15, x: 15, y: 20 + visibleFrames().length * 8,
        width: 60, height: 14,
        rotation: 0, stroke: 0.5, align: "center", valign: "middle", hidden: false, locked: false,
        sheet: sheetsEnabled() ? currentSheet : 1
      };
      if (kind === "line_h" || kind === "line") {
        f.kind = "line"; f.orientation = "h"; f.width = Math.max(40, pageW() - 30); f.height = 1; f.line_style = "solid";
        f.extend_mode = "none";
      } else if (kind === "line_v") {
        f.kind = "line"; f.orientation = "v"; f.width = 1; f.height = 40; f.line_style = "solid";
        f.extend_mode = "none";
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
        f.extend_mode = "none";
      }
      if (kind === "field" || kind === "row_number") {
        f.source = ""; f.source_key = ""; f.bindings = [{ source: "", source_key: "" }];
      }
      frames.push(f); selectOnly(f.id); render();
    });
  });

  document.getElementById("btn-undo").addEventListener("click", undo);
  document.getElementById("btn-redo").addEventListener("click", redo);

  function setPreview(on) {
    previewMode = !!on;
    document.documentElement.classList.toggle("preview-mode", previewMode);
    document.body.classList.toggle("preview-mode", previewMode);
    wrap.classList.toggle("preview-mode", previewMode);
    var exitBtn = document.getElementById("btn-exit-preview");
    if (exitBtn) exitBtn.hidden = !previewMode;
    var prevBtn = document.getElementById("btn-preview");
    if (prevBtn) prevBtn.textContent = previewMode ? "بازگشت به طراحی" : "پیش‌نمایش چاپ";
    clearSelection();
    selectedGuideIdx = null;
    render();
    if (previewMode) {
      window.scrollTo(0, 0);
    }
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
    if (!selectedIds.length) return;
    var ids = selectedIds.slice();
    if (ids.length === 1) {
      var one = find(ids[0]);
      if (!one || one.locked) return;
    }
    pushHistory();
    frames = frames.filter(function (x) {
      if (ids.indexOf(x.id) < 0) return true;
      return !!x.locked;
    });
    clearSelection();
    render();
  }
  function copySelected() {
    if (!selectedIds.length) return;
    if (selectedIds.length === 1) {
      var f = find(selectedId);
      if (!f) return;
      clipboard = JSON.parse(JSON.stringify(f));
    } else {
      clipboard = selectedIds.map(function (id) {
        var ff = find(id);
        return ff ? JSON.parse(JSON.stringify(ff)) : null;
      }).filter(Boolean);
    }
    updateClipboardButtons();
    toast("کپی شد");
  }
  function cutSelected() {
    if (!selectedIds.length) return;
    copySelected();
    var ids = selectedIds.slice();
    pushHistory();
    frames = frames.filter(function (x) {
      if (ids.indexOf(x.id) < 0) return true;
      return !!x.locked;
    });
    clearSelection();
    render();
    toast("برش شد");
  }
  function pasteClipboard() {
    if (!clipboard) return;
    pushHistory();
    var items = Array.isArray(clipboard) ? clipboard : [clipboard];
    var newIds = [];
    items.forEach(function (src, i) {
      if (!src) return;
      var f = JSON.parse(JSON.stringify(src));
      f.id = "f" + Date.now() + "-" + (uid++) + "-" + i;
      f.left = snapMm((f.left || 0) + 5);
      f.y = snapMm((f.y || 0) + 5);
      f.x = f.left;
      f.locked = false;
      f.sheet = sheetsEnabled() ? currentSheet : (f.sheet || 1);
      frames.push(f);
      newIds.push(f.id);
    });
    selectedIds = newIds;
    selectedId = newIds.length ? newIds[newIds.length - 1] : null;
    clipboard = null;
    render();
    toast("جای‌گذاری شد");
  }

  var copyBtnEl = document.getElementById("btn-copy");
  var pasteBtnEl = document.getElementById("btn-paste");
  if (copyBtnEl) copyBtnEl.addEventListener("click", function () { copySelected(); });
  if (pasteBtnEl) pasteBtnEl.addEventListener("click", function () { pasteClipboard(); });

  var purposeSelEl = document.getElementById("ui-form-purpose");
  if (purposeSelEl) {
    purposeSelEl.addEventListener("change", function () {
      formPurpose = this.value || "";
      if (formPurpose !== "reports") {
        linkedReportId = "";
        reportLevelFilter = "";
        currentSheet = 1;
      }
      if (purposeHidden) purposeHidden.value = formPurpose;
      if (linkedReportHidden) linkedReportHidden.value = linkedReportId;
      render();
    });
  }
  var linkedReportSel = document.getElementById("ui-linked-report");
  if (linkedReportSel) {
    linkedReportSel.addEventListener("change", function () {
      linkedReportId = this.value || "";
      reportLevelFilter = "";
      currentSheet = 1;
      if (linkedReportHidden) linkedReportHidden.value = linkedReportId;
      render();
    });
  }

  var formSheetSel = document.getElementById("ui-form-sheet");
  if (formSheetSel) {
    formSheetSel.addEventListener("change", function () {
      var n = parseInt(this.value || "1", 10);
      if (isNaN(n) || n < 1) n = 1;
      currentSheet = n;
      clearSelection();
      render();
    });
  }
  var transferBtn = document.getElementById("btn-transfer-sheet");
  if (transferBtn) {
    transferBtn.addEventListener("click", function () {
      var src = document.getElementById("ui-transfer-from");
      if (!src || !src.value) {
        toast("برگه مبدأ را انتخاب کنید");
        return;
      }
      transferSheetFrom(src.value);
    });
  }

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
    if (purposeHidden) purposeHidden.value = formPurpose || "";
    if (linkedReportHidden) linkedReportHidden.value = linkedReportId || "";
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
