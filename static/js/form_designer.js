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
  var csrf = (formEl.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";

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
  });

  var groups = [];
  try { groups = JSON.parse(document.getElementById("column-groups").textContent || "[]"); } catch (e) {}

  var selectedId = null;
  var zoom = 1;
  var snap = pageSettings.snap_mm || 2;
  var uid = 1;
  var history = [];
  var future = [];
  var previewMode = false;
  var guidesEnabled = true;
  var dragGuide = null;

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
  }
  function restoreState(raw) {
    var s = JSON.parse(raw);
    frames = s.frames || [];
    pageSettings = Object.assign(pageSettings, s.pageSettings || {});
    pageWInput.value = s.pageW; pageHInput.value = s.pageH;
    snap = pageSettings.snap_mm || 2;
    selectedId = null;
    syncUiChecks();
    render();
  }
  function undo() {
    if (!history.length) return;
    future.push(cloneState());
    restoreState(history.pop());
  }
  function redo() {
    if (!future.length) return;
    history.push(cloneState());
    restoreState(future.pop());
  }

  function syncHidden() {
    frames.forEach(function (f) { f.x = f.left; });
    hiddenFrames.value = JSON.stringify(frames);
    hiddenSettings.value = JSON.stringify(pageSettings);
  }

  function kindLabel(k) {
    return ({ header: "عنوان", box: "کادر", field: "فیلد", line: "خط", logo: "لوگو", row_number: "شمارش" })[k] || k;
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
  }

  function drawRulers() {
    if (!pageSettings.show_ruler) { rulerH.innerHTML = ""; rulerV.innerHTML = ""; return; }
    var w = pageW(), h = pageH();
    var scrollLeft = scrollEl.scrollLeft;
    var scrollTop = scrollEl.scrollTop;
    var pad = 24; // stage padding
    rulerH.innerHTML = "";
    rulerV.innerHTML = "";
    rulerH.style.width = px(w) + pad * 2 + "px";
    rulerV.style.height = px(h) + pad * 2 + "px";
    for (var x = 0; x <= w; x += 1) {
      if (x % 5 !== 0 && snap > 1) continue;
      var tick = document.createElement("div");
      tick.className = "dz-tick" + (x % 10 === 0 ? " major" : "");
      tick.style.left = (pad + px(x) - scrollLeft) + "px";
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
      tick2.style.top = (pad + px(y) - scrollTop) + "px";
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

  function extendMasterRows() {
    var masters = frames.filter(function (f) {
      return !f.hidden && (f.kind === "field") && f.data_extend;
    });
    if (!masters.length) return 0;
    return estimateExtendRows(masters[0]);
  }

  function renderLayers() {
    var list = document.getElementById("layers-list");
    list.innerHTML = "";
    frames.slice().reverse().forEach(function (f) {
      var row = document.createElement("div");
      row.className = "dz-clip" + (f.id === selectedId ? " is-active" : "") + (f.hidden ? " is-hidden" : "");
      row.innerHTML =
        '<span class="name">' + kindLabel(f.kind) + " — " + (f.label || "بدون نام") + "</span>" +
        '<button type="button" class="dz-icon-btn dz-eye' + (f.hidden ? " off" : "") + '" title="مخفی/نمایش" aria-label="مخفی">👁</button>' +
        '<button type="button" class="dz-icon-btn del" title="حذف">×</button>';
      row.addEventListener("click", function (e) {
        if (e.target.closest(".dz-icon-btn")) return;
        selectedId = f.id; render();
      });
      row.querySelector(".dz-eye").addEventListener("click", function (e) {
        e.stopPropagation();
        pushHistory();
        f.hidden = !f.hidden;
        render();
      });
      row.querySelector(".del").addEventListener("click", function (e) {
        e.stopPropagation();
        pushHistory();
        frames = frames.filter(function (x) { return x.id !== f.id; });
        if (selectedId === f.id) selectedId = null;
        render();
      });
      list.appendChild(row);
    });
  }

  function updateAlignButtons() {
    var f = find(selectedId);
    // Alignment like Word/Excel: only for title / text field / box / row number
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
    document.getElementById("logo-props").hidden = f.kind !== "logo";
    document.getElementById("field-bind-props").hidden = f.kind !== "field";
    document.getElementById("row-number-props").hidden = f.kind !== "row_number";
    if (f.kind === "field") {
      document.getElementById("prop-data-extend").checked = !!f.data_extend;
      fillSources(f);
    }
    if (f.kind === "row_number") {
      document.getElementById("prop-row-extend").checked = !!f.data_extend;
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
      var g = px(snap);
      grid.style.backgroundSize = g + "px " + g + "px";
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
      pageSettings.guides.forEach(function (g) {
        var el = document.createElement("div");
        el.className = "dz-guide " + g.axis;
        if (g.axis === "h") el.style.top = px(g.pos) + "px";
        else el.style.left = px(g.pos) + "px";
        canvas.appendChild(el);
      });
    }

    var masterRows = extendMasterRows();

    frames.forEach(function (f) {
      if (previewMode && f.hidden) return;

      // Preview expansion for extend fields / row numbers
      var copies = 1;
      if (previewMode && f.data_extend && (f.kind === "field" || f.kind === "row_number")) {
        copies = f.kind === "row_number" ? (masterRows || estimateExtendRows(f)) : estimateExtendRows(f);
      }

      for (var i = 0; i < copies; i++) {
        var el = document.createElement("div");
        el.className = "dz-frame kind-" + (f.kind || "box") + (f.id === selectedId && i === 0 ? " selected" : "") + (f.hidden ? " is-hidden" : "");
        el.style.left = px(f.left || 0) + "px";
        el.style.top = px((f.y || 0) + i * (f.height || 8)) + "px";
        el.style.width = px(f.width || 20) + "px";
        el.style.height = px(f.height || 10) + "px";
        el.style.transform = "rotate(" + (f.rotation || 0) + "deg)";
        if (f.stroke && f.kind !== "line" && f.kind !== "field" && f.kind !== "row_number") {
          el.style.borderWidth = px(f.stroke) + "px";
        }
        var inner = document.createElement("div");
        inner.className = "inner";
        inner.style.justifyContent = f.align === "left" ? "flex-end" : (f.align === "right" ? "flex-start" : "center");
        inner.style.alignItems = f.valign === "top" ? "flex-start" : (f.valign === "bottom" ? "flex-end" : "center");
        inner.style.textAlign = f.align || "center";

        if (f.kind === "logo" && f.image_data) {
          var img = document.createElement("img");
          img.src = f.image_data; img.alt = f.label || "لوگو";
          inner.appendChild(img);
        } else if (f.kind === "line") {
          /* border-top only */
        } else if (f.kind === "row_number") {
          inner.textContent = previewMode ? String(i + 1) : (f.label || "شمارش");
        } else if (f.kind === "field") {
          var txt = f.label || "فیلد";
          if (f.source && f.source_key && !previewMode) txt += " ⟨" + f.source + "." + f.source_key + "⟩";
          if (previewMode && f.source_key) txt = "{" + f.source_key + "}";
          inner.textContent = txt;
        } else {
          inner.textContent = f.label || kindLabel(f.kind);
        }
        el.appendChild(inner);

        if (!previewMode && f.data_extend && i === 0) {
          var badge = document.createElement("span");
          badge.className = "badge-extend";
          badge.textContent = "امتداد";
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
            }
          }
        }
        canvas.appendChild(el);
      }
    });

    drawRulers();
    renderLayers();
    renderProps();
  }

  function applyProps() {
    var f = find(selectedId); if (!f) return;
    pushHistory();
    f.label = document.getElementById("prop-label").value;
    f.left = snapMm(Math.max(0, parseFloat(document.getElementById("prop-x").value) || 0));
    f.y = snapMm(Math.max(0, parseFloat(document.getElementById("prop-y").value) || 0));
    f.width = Math.max(snap, snapMm(parseFloat(document.getElementById("prop-w").value) || snap));
    f.height = Math.max(0.5, snapMm(parseFloat(document.getElementById("prop-h").value) || 1));
    if (f.kind === "line") { f.height = Math.max(0.5, f.height); }
    render();
  }
  ["prop-label","prop-x","prop-y","prop-w","prop-h"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", applyProps);
  });
  document.getElementById("prop-data-extend").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "field") return;
    pushHistory(); f.data_extend = this.checked; render();
  });
  document.getElementById("prop-row-extend").addEventListener("change", function () {
    var f = find(selectedId); if (!f || f.kind !== "row_number") return;
    pushHistory(); f.data_extend = this.checked; render();
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
      var f = find(selectedId); if (!f || btn.disabled) return;
      pushHistory();
      if (btn.dataset.align) f.align = btn.dataset.align;
      if (btn.dataset.valign) f.valign = btn.dataset.valign;
      render();
    });
  });

  // Paper / margins
  var PRESETS = { "A4-P": [210, 297], "A4-L": [297, 210], "A5-P": [148, 210], "A5-L": [210, 148] };
  document.getElementById("paper-preset").addEventListener("change", function () {
    var v = this.value; if (!PRESETS[v]) return;
    pushHistory();
    pageWInput.value = PRESETS[v][0]; pageHInput.value = PRESETS[v][1]; render();
  });
  ["prop-page-w","prop-page-h"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
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

  // Drag / resize
  var drag = null;
  function startDrag(e) {
    if (e.target.classList.contains("dz-handle")) return;
    e.preventDefault();
    selectedId = e.currentTarget.dataset.id;
    var f = find(selectedId);
    pushHistory();
    drag = { mode: "move", id: selectedId, startX: e.clientX, startY: e.clientY, ox: f.left || 0, oy: f.y || 0 };
    render();
  }
  function startResize(e) {
    e.preventDefault(); e.stopPropagation();
    var id = e.currentTarget.parentElement.dataset.id;
    var f = find(id); selectedId = id;
    pushHistory();
    drag = {
      mode: "resize", corner: e.currentTarget.dataset.corner, id: id,
      startX: e.clientX, startY: e.clientY, ox: f.left || 0, oy: f.y || 0, ow: f.width, oh: f.height
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
      render();
      return;
    }
    if (!drag) return;
    var f = find(drag.id); if (!f) return;
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
      pushHistory();
      pageSettings.guides.push({ axis: dragGuide.axis, pos: dragGuide.pos });
      dragGuide = null;
      render();
    }
    drag = null;
  });

  canvas.addEventListener("mousedown", function (e) {
    if (e.target === canvas || e.target.classList.contains("dz-grid") || e.target.classList.contains("dz-margin") || e.target.classList.contains("dz-guide")) {
      selectedId = null; render();
    }
  });

  // Guides from rulers (Visio-like)
  function startGuideFromRuler(axis, e) {
    if (!guidesEnabled || !pageSettings.show_ruler) return;
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    dragGuide = {
      axis: axis,
      pos: axis === "h"
        ? snapMm(Math.max(0, mmFromPx(e.clientY - rect.top)))
        : snapMm(Math.max(0, mmFromPx(e.clientX - rect.left)))
    };
  }
  rulerH.addEventListener("mousedown", function (e) { startGuideFromRuler("h", e); });
  rulerV.addEventListener("mousedown", function (e) { startGuideFromRuler("v", e); });

  scrollEl.addEventListener("scroll", function () { drawRulers(); });

  document.querySelectorAll("[data-add]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      pushHistory();
      var kind = btn.getAttribute("data-add");
      var f = {
        id: "f" + Date.now() + "-" + (uid++),
        label: kind === "header" ? "عنوان" : kind === "field" ? "فیلد" : kind === "logo" ? "لوگو" : kind === "row_number" ? "ردیف" : kind === "line" ? "" : "کادر",
        kind: kind, left: 15, x: 15, y: 20 + frames.length * 8,
        width: (kind === "line" || kind === "header") ? Math.max(40, pageW() - 30) : (kind === "logo" ? 40 : 60),
        height: kind === "line" ? 1 : kind === "header" ? 12 : kind === "logo" ? 28 : 14,
        rotation: 0, stroke: 0.5, align: "center", valign: "middle", hidden: false
      };
      if (kind === "field" || kind === "row_number") {
        f.source = ""; f.source_key = ""; f.data_extend = false;
      }
      frames.push(f); selectedId = f.id; render();
    });
  });

  document.getElementById("btn-undo").addEventListener("click", undo);
  document.getElementById("btn-redo").addEventListener("click", redo);

  function setPreview(on) {
    previewMode = on;
    document.body.classList.toggle("preview-mode", on);
    wrap.classList.toggle("preview-mode", on);
    var exitBtn = document.getElementById("btn-exit-preview");
    if (exitBtn) exitBtn.hidden = !on;
    var prevBtn = document.getElementById("btn-preview");
    if (prevBtn) prevBtn.textContent = on ? "بازگشت به طراحی" : "پیش‌نمایش چاپ";
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

  function gatherPayload() {
    syncHidden();
    var fd = new FormData(formEl);
    return fd;
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
        saveUrl = data.save_url || saveUrl;
        formEl.setAttribute("data-save-url", saveUrl);
        if (data.title) document.getElementById("dz-window-title").textContent = "ویرایش فرم — " + data.title;
      }
      toast("ذخیره شد");
      if (thenClose) {
        if (window.opener && !window.opener.closed) {
          try { window.opener.location.href = listUrl; } catch (e) {}
          window.close();
        } else {
          window.location.href = listUrl;
        }
      }
    }).catch(function () { toast("خطای شبکه در ذخیره"); });
  }

  document.getElementById("btn-save").addEventListener("click", function () { saveAjax(false); });
  document.getElementById("btn-register").addEventListener("click", function () { saveAjax(true); });

  // Window chrome helpers
  document.getElementById("dz-close").addEventListener("click", function () {
    if (window.opener) window.close();
    else window.location.href = listUrl;
  });
  document.getElementById("dz-minimize").addEventListener("click", function () {
    // Browsers restrict minimize; blur as soft minimize fallback.
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

  // Init
  syncFormMetaUi();
  syncUiChecks();
  render();
})();
