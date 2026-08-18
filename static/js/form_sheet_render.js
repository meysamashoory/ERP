/* Shared print-sheet renderer for form detail / view / print */
(function (global) {
  "use strict";
  var MM = 3.7795275591;

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

  function isLineKind(k) {
    return k === "line" || k === "line_h" || k === "line_v";
  }

  function columnLabel(groups, source, key) {
    if (!groups || !source || !key) return "";
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      if (g.id !== source) continue;
      var cols = g.columns || [];
      for (var j = 0; j < cols.length; j++) {
        var c = cols[j];
        if (c[0] === key) return c[1] || key;
      }
    }
    return key;
  }

  function estimateExtendRows(pageH, marginBottom, f) {
    var mb = marginBottom || 0;
    var avail = pageH - (f.y || 0) - mb;
    var rowH = Math.max(f.height || 8, 6);
    return Math.max(1, Math.floor(avail / rowH));
  }

  /** Normalize legacy data_extend → extend_mode for box/line. */
  function extendModeOf(f) {
    if (f.extend_mode === "page" || f.extend_mode === "field" || f.extend_mode === "none") {
      return f.extend_mode;
    }
    if (f.data_extend) return "field";
    return "none";
  }

  function near(a, b, eps) {
    return Math.abs(a - b) <= (eps || 0.6);
  }

  function verticalOverlap(a, b) {
    var at = a.y, ab = a.y + a.h, bt = b.y, bb = b.y + b.h;
    return Math.min(ab, bb) - Math.max(at, bt) > 0.5;
  }

  function horizontalOverlap(a, b) {
    var al = a.x, ar = a.x + a.w, bl = b.x, br = b.x + b.w;
    return Math.min(ar, br) - Math.max(al, bl) > 0.5;
  }

  function applyBoxBorders(inst, all, borderStyles, lastLineStyle) {
    var bs = borderStyles || {};
    var top = bs.top || "solid";
    var right = bs.right || "solid";
    var bottom = lastLineStyle || bs.bottom || "solid";
    var left = bs.left || "solid";

    all.forEach(function (other) {
      if (other === inst) return;
      if (near(other.y + other.h, inst.y) && horizontalOverlap(inst, other)) top = "none";
      if (near(inst.x + inst.w, other.x) && verticalOverlap(inst, other)) right = "none";
    });

    return {
      top: borderCss(top),
      right: borderCss(right),
      bottom: borderCss(bottom),
      left: borderCss(left)
    };
  }

  /**
   * options:
   *  - fillRows: [{source_key: value}, ...] actual data rows from linked context
   *  - viewMode: "detail" (general view) | "context" (linked print)
   *  Without fillRows: field/field-dependent → 1 row; page → to bottom.
   */
  function render(options) {
    var canvas = options.canvas;
    var frames = options.frames || [];
    var pageW = options.pageWidthMm || 210;
    var pageH = options.pageHeightMm || 297;
    var settings = options.pageSettings || {};
    var groups = options.columnGroups || [];
    var fillRows = options.fillRows || [];
    if ((!fillRows || !fillRows.length) && options.fillValues && typeof options.fillValues === "object") {
      fillRows = [options.fillValues];
    }
    var dataCount = fillRows.length;
    var useMm = !!options.useMm;

    function len(v) {
      return useMm ? (v + "mm") : ((v * MM) + "px");
    }

    canvas.innerHTML = "";
    canvas.style.width = useMm ? (pageW + "mm") : (pageW * MM + "px");
    canvas.style.height = useMm ? (pageH + "mm") : (pageH * MM + "px");
    canvas.style.position = "relative";
    canvas.style.background = "#fff";
    canvas.style.boxSizing = "border-box";
    canvas.style.printColorAdjust = "exact";
    canvas.style.webkitPrintColorAdjust = "exact";

    function copiesFor(f) {
      var mode = extendModeOf(f);
      if (f.kind === "field" || f.kind === "row_number") {
        return dataCount > 0 ? dataCount : 1;
      }
      if (f.kind === "box" || isLineKind(f.kind)) {
        if (mode === "page") return estimateExtendRows(pageH, settings.margin_bottom, f);
        if (mode === "field") return dataCount > 0 ? dataCount : 1;
        return 1;
      }
      return 1;
    }

    var masterField = null;
    for (var mi = 0; mi < frames.length; mi++) {
      if (!frames[mi].hidden && frames[mi].kind === "field") {
        masterField = frames[mi];
        break;
      }
    }
    var masterStep = masterField ? Math.max(masterField.height || 8, 6) : 14;

    function rowStepFor(f) {
      if (f.kind === "field" || f.kind === "row_number") return Math.max(f.height || 8, 6);
      var mode = extendModeOf(f);
      if ((f.kind === "box" || isLineKind(f.kind)) && (mode === "field" || mode === "page")) {
        return masterStep;
      }
      return Math.max(f.height || 8, 6);
    }

    var boxInstances = [];
    var pending = [];

    frames.forEach(function (f, zi) {
      if (f.hidden) return;
      var copies = copiesFor(f);
      var step = rowStepFor(f);
      for (var i = 0; i < copies; i++) {
        var x = f.left != null ? f.left : (f.x || 0);
        var y = (f.y || 0) + i * step;
        var w = f.width || 20;
        var h = f.height || 10;
        var item = { f: f, i: i, copies: copies, zi: zi, x: x, y: y, w: w, h: h };
        pending.push(item);
        if (f.kind === "box") boxInstances.push(item);
      }
    });

    pending.forEach(function (item) {
      var f = item.f;
      var mode = extendModeOf(f);
      var el = document.createElement("div");
      el.className = "form-sheet-frame kind-" + (f.kind || "box");
      el.style.position = "absolute";
      el.style.left = len(item.x);
      el.style.top = len(item.y);
      el.style.width = len(item.w);
      el.style.height = len(item.h);
      el.style.zIndex = String(
        ((f.kind === "field" || f.kind === "row_number" || f.kind === "header" || f.kind === "logo")
          ? 80
          : 2) + item.zi
      );
      el.style.boxSizing = "border-box";
      el.style.overflow = "hidden";
      el.style.display = "flex";
      el.style.padding = "0 2px";
      el.style.fontSize = "12px";
      el.style.color = "#111";
      el.style.printColorAdjust = "exact";
      el.style.webkitPrintColorAdjust = "exact";
      if (f.rotation) el.style.transform = "rotate(" + f.rotation + "deg)";

      var justify = f.align === "left" ? "flex-end" : (f.align === "right" ? "flex-start" : "center");
      var align = f.valign === "top" ? "flex-start" : (f.valign === "bottom" ? "flex-end" : "center");
      el.style.justifyContent = justify;
      el.style.alignItems = align;
      el.style.textAlign = f.align || "center";

      if (f.kind === "box") {
        var fills = (f.fill_colors && f.fill_colors.length) ? f.fill_colors : defaultFillColors();
        el.style.background = fills[item.i % fills.length];
        var repeats = mode === "page" || mode === "field";
        var isLast = repeats && (item.i === item.copies - 1) && f.last_line_enable;
        var lastStyle = isLast ? (f.last_line_style || "solid") : null;
        var borders = applyBoxBorders(item, boxInstances, f.border_styles, lastStyle);
        el.style.borderTop = borders.top;
        el.style.borderRight = borders.right;
        el.style.borderBottom = borders.bottom;
        el.style.borderLeft = borders.left;
        if (f.label && item.i === 0 && !(fillRows && fillRows.length)) el.textContent = f.label;
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
      } else if (f.kind === "logo" && f.image_data) {
        el.style.border = "none";
        el.style.background = "transparent";
        var img = document.createElement("img");
        img.src = f.image_data;
        img.alt = f.label || "لوگو";
        img.style.maxWidth = "100%";
        img.style.maxHeight = "100%";
        img.style.objectFit = "contain";
        el.appendChild(img);
      } else if (f.kind === "row_number") {
        el.style.border = "none";
        el.style.background = "transparent";
        el.textContent = String(item.i + 1);
      } else if (f.kind === "field") {
        el.style.border = "none";
        el.style.background = "transparent";
        var row = fillRows[item.i] || {};
        if (f.source_key && row[f.source_key] != null && row[f.source_key] !== "") {
          el.textContent = String(row[f.source_key]);
        } else {
          el.textContent = columnLabel(groups, f.source, f.source_key) || "";
        }
      } else {
        el.style.border = "none";
        el.style.background = "transparent";
        el.textContent = f.label || "";
      }

      canvas.appendChild(el);
    });
  }

  global.ERPFormSheetRender = {
    render: render,
    borderCss: borderCss,
    columnLabel: columnLabel,
    applyBoxBorders: applyBoxBorders,
    isLineKind: isLineKind,
    defaultFillColors: defaultFillColors,
    extendModeOf: extendModeOf
  };
})(window);
