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

  function masterFieldRows(frames, pageH, marginBottom) {
    var n = 0;
    (frames || []).forEach(function (f) {
      if (f.hidden || f.kind !== "field" || !f.data_extend) return;
      n = Math.max(n, estimateExtendRows(pageH, marginBottom, f));
    });
    return n;
  }

  function masterRowHeight(frames) {
    var h = 0;
    (frames || []).forEach(function (f) {
      if (f.hidden || f.kind !== "field" || !f.data_extend) return;
      h = Math.max(h, f.height || 0);
    });
    return h || 8;
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

  /** Suppress shared edges: top box wins horizontally; right box wins vertically. */
  function applyBoxBorders(inst, all, borderStyles, lastLineStyle) {
    var bs = borderStyles || {};
    var top = bs.top || "solid";
    var right = bs.right || "solid";
    var bottom = lastLineStyle || bs.bottom || "solid";
    var left = bs.left || "solid";

    all.forEach(function (other) {
      if (other === inst) return;
      // Shared horizontal edge: other is above this → this suppresses top (top box wins)
      if (near(other.y + other.h, inst.y) && horizontalOverlap(inst, other)) {
        top = "none";
      }
      // Shared vertical edge: other is to the right → this suppresses right (right box wins)
      if (near(inst.x + inst.w, other.x) && verticalOverlap(inst, other)) {
        right = "none";
      }
    });

    return {
      top: borderCss(top),
      right: borderCss(right),
      bottom: borderCss(bottom),
      left: borderCss(left)
    };
  }

  function render(options) {
    var canvas = options.canvas;
    var frames = options.frames || [];
    var pageW = options.pageWidthMm || 210;
    var pageH = options.pageHeightMm || 297;
    var settings = options.pageSettings || {};
    var groups = options.columnGroups || [];
    var fillValues = options.fillValues || {};
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

    var masterRows = masterFieldRows(frames, pageH, settings.margin_bottom);
    var rowStep = masterRowHeight(frames);

    var boxInstances = [];
    var pending = [];

    frames.forEach(function (f, zi) {
      if (f.hidden) return;
      var copies = 1;
      if (f.data_extend) {
        if (f.kind === "field") copies = estimateExtendRows(pageH, settings.margin_bottom, f);
        else if (masterRows > 0) copies = masterRows;
        else copies = 1;
      }
      var step = (f.kind === "field") ? (f.height || 8) : rowStep;

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
      var el = document.createElement("div");
      el.className = "form-sheet-frame kind-" + (f.kind || "box");
      el.style.position = "absolute";
      el.style.left = len(item.x);
      el.style.top = len(item.y);
      el.style.width = len(item.w);
      el.style.height = len(item.h);
      el.style.zIndex = String(2 + item.zi);
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
        var isLast = f.data_extend && (item.i === item.copies - 1) && f.last_line_enable;
        var lastStyle = isLast ? (f.last_line_style || "solid") : null;
        var borders = applyBoxBorders(item, boxInstances, f.border_styles, lastStyle);
        el.style.borderTop = borders.top;
        el.style.borderRight = borders.right;
        el.style.borderBottom = borders.bottom;
        el.style.borderLeft = borders.left;
        if (f.label && !(f.data_extend && item.i > 0)) el.textContent = f.label;
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
        if (f._filled != null && f._filled !== "") {
          el.textContent = f._filled;
        } else if (fillValues && f.source_key && fillValues[f.source_key] != null) {
          el.textContent = String(fillValues[f.source_key]);
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
    defaultFillColors: defaultFillColors
  };
})(window);
