/* Report builder: sources, calc columns, Excel-like levels/formats/formulas. */
(function (global) {
  "use strict";

  function readJson(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent || "null") || fallback;
    } catch (e) {
      return fallback;
    }
  }

  function newUid() {
    return "c" + Math.random().toString(16).slice(2, 10);
  }

  function clampWidth(n) {
    n = parseInt(n, 10);
    if (!n || n <= 0) return 0;
    return Math.max(40, Math.min(800, n));
  }

  function excelColLetter(index) {
    var s = "";
    var n = Math.max(0, index);
    while (true) {
      s = String.fromCharCode(97 + (n % 26)) + s;
      n = Math.floor(n / 26) - 1;
      if (n < 0) break;
    }
    return s;
  }

  function letterIndex(letter) {
    letter = String(letter || "").toLowerCase();
    var n = 0;
    for (var i = 0; i < letter.length; i++) {
      n = n * 26 + (letter.charCodeAt(i) - 96);
    }
    return n - 1;
  }

  var PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  function toPersianDigits(n) {
    return String(n).replace(/\d/g, function (d) { return PERSIAN_DIGITS[parseInt(d, 10)]; });
  }

  var LEVEL_OPTIONS = (function () {
    var opts = [];
    for (var i = 1; i <= 9; i++) {
      opts.push({ value: String(i), label: "سطح " + toPersianDigits(i) });
    }
    for (var u = 2; u <= 8; u++) {
      opts.push({ value: "upto_" + u, label: "تا سطح " + toPersianDigits(u) });
    }
    opts.push({ value: "all", label: "همه سطوح" });
    return opts;
  })();

  function init(opts) {
    opts = opts || {};
    var mode = opts.mode || "create";
    var groups = readJson("column-groups", []);
    var keyability = readJson("column-keyability", {});
    var formulaCatalog = readJson("formula-catalog", []);
    var formatPresets = readJson("number-format-presets", []);
    var hidden = document.getElementById("id_columns_json");
    var linksHidden = document.getElementById("id_source_links_json");
    var conditionsHidden = document.getElementById("id_report_conditions_json");
    if (!hidden) return;

    var selected = readJson("columns-initial", []);
    var sourceLinks = readJson("links-initial", []);
    var conditions = [];

    function canBeKey(source, key) {
      if (source === "_calc") return false;
      if (keyability[source] && Object.prototype.hasOwnProperty.call(keyability[source], key)) {
        return !!keyability[source][key];
      }
      var low = String(key || "").toLowerCase();
      if (/qty|quantity|weight|scrap|stock|hours|cycle|cavit|material|produced|planned|amount|count|total/.test(low)) {
        if (/code|uid|name|id|unique|product|mold|machine/.test(low) && !/^(cycle|last_cycle|planned_cycle)$/.test(low)) {
          return true;
        }
        return false;
      }
      return true;
    }

    function defaultWidthFor(source, key) {
      var g = groups.find(function (x) { return x.id === source; });
      if (g && g.default_widths && Object.prototype.hasOwnProperty.call(g.default_widths, key)) {
        var fromMap = clampWidth(g.default_widths[key]);
        if (fromMap) return fromMap;
      }
      return source === "_calc" ? 96 : 160;
    }

    function normalizeLevelMode(raw, legacy) {
      var t = String(raw || "").trim();
      if (LEVEL_OPTIONS.some(function (o) { return o.value === t; })) return t;
      var n = parseInt(legacy || raw || 1, 10);
      if (!n || n < 1) n = 1;
      if (n > 9) n = 9;
      return String(n);
    }

    function assignColCodes() {
      var used = {};
      var nextIdx = 0;
      selected.forEach(function (c) {
        var code = String(c.col_code || "").toLowerCase();
        var m = code.match(/^([a-z]{1,3})(\d{1,3})$/);
        if (m) {
          var letter = m[1];
          var num = parseInt(m[2], 10);
          used[letter] = Math.max(used[letter] || 0, num);
          nextIdx = Math.max(nextIdx, letterIndex(letter) + 1);
          c.col_code = letter + num;
          return;
        }
        var L;
        while (true) {
          L = excelColLetter(nextIdx++);
          if (!used[L]) break;
        }
        used[L] = 1;
        c.col_code = L + "1";
      });
    }

    function nextCopyCode(srcCode) {
      var m = String(srcCode || "").toLowerCase().match(/^([a-z]{1,3})(\d{1,3})$/);
      if (!m) return "";
      var letter = m[1];
      var maxN = 0;
      selected.forEach(function (c) {
        var om = String(c.col_code || "").toLowerCase().match(/^([a-z]{1,3})(\d{1,3})$/);
        if (om && om[1] === letter) maxN = Math.max(maxN, parseInt(om[2], 10));
      });
      return letter + (maxN + 1);
    }

    selected = (selected || []).map(function (item) {
      if (typeof item === "string") {
        return {
          key: item, source: "fitting", level: 1, level_mode: "1", label: item, origLabel: item,
          uid: newUid(), width: defaultWidthFor("fitting", item), is_key: false,
          kind: "field", col_code: "", number_format: "General", formula: ""
        };
      }
      item.kind = item.kind === "calc" ? "calc" : "field";
      item.origLabel = item.origLabel || item.label || item.key;
      if (!item.uid) item.uid = newUid();
      item.width = clampWidth(item.width || 0);
      item.level_mode = normalizeLevelMode(item.level_mode, item.level);
      item.number_format = item.number_format || "General";
      item.formula = item.formula || "";
      item.col_code = item.col_code || "";
      if (item.kind === "calc") {
        item.source = "_calc";
        item.key = item.key || "calc";
        item.is_key = false;
      } else {
        item.is_key = !!item.is_key && canBeKey(item.source || "", item.key || "");
      }
      return item;
    });
    assignColCodes();

    var addedSources = [];
    selected.forEach(function (c) {
      if (c.source && c.source !== "_calc" && addedSources.indexOf(c.source) < 0) {
        addedSources.push(c.source);
      }
    });
    var activeIdx = -1;
    var formulaEditIdx = -1;

    var metaEditor = document.getElementById("meta-editor");
    var builderPanel = document.getElementById("builder-panel");
    var topSubmit = document.getElementById("top-submit");
    var cancelBtn = document.getElementById("cancel-meta-btn");
    var titleInput = document.getElementById("id_title");
    var numberInput = document.getElementById("id_number");
    var descInput = document.getElementById("id_description");
    var accessInput = document.getElementById("id_access_mode");
    var headingView = document.getElementById("heading-view");
    var headingEdit = document.getElementById("heading-edit");
    var headingText = document.getElementById("heading-text");
    var confirmedOnce = mode === "edit";
    var trees = document.getElementById("source-trees");
    var list = document.getElementById("selected-cols");
    var pathEl = document.getElementById("col-path");
    var menuList = document.getElementById("source-menu-list");
    var linkBtn = document.getElementById("link-sources-btn");
    var linkSummary = document.getElementById("source-links-summary");
    var linkDialog = document.getElementById("source-link-dialog");
    var formulaDialog = document.getElementById("formula-dialog");
    var formulaTextarea = document.getElementById("formula-textarea");
    var formEl = document.getElementById("report-builder-form");

    function formatHeading() {
      var title = ((titleInput && titleInput.value) || "").trim();
      var desc = ((descInput && descInput.value) || "").trim();
      if (!title) return "";
      var text = (((numberInput && numberInput.value) || "").trim() || "—") + "- " + title;
      if (desc) text += " (" + desc + ")";
      return text;
    }

    function syncHeading() {
      if (headingText) headingText.textContent = formatHeading() || "—";
    }

    function syncHidden() {
      assignColCodes();
      hidden.value = JSON.stringify(selected.map(function (c) {
        return {
          key: c.key,
          source: c.source,
          level: parseInt(String(c.level_mode).replace("upto_", "").replace("all", "9"), 10) || 1,
          level_mode: c.level_mode,
          label: c.label,
          uid: c.uid,
          width: clampWidth(c.width),
          is_key: !!c.is_key,
          kind: c.kind || "field",
          col_code: c.col_code,
          number_format: c.number_format || "General",
          formula: c.kind === "calc" ? (c.formula || "") : ""
        };
      }));
      if (linksHidden) linksHidden.value = JSON.stringify(sourceLinks);
      if (conditionsHidden) conditionsHidden.value = JSON.stringify(conditions);
    }

    function groupLabel(sid) {
      if (sid === "_calc") return "ستون محاسبات";
      var g = groups.find(function (x) { return x.id === sid; });
      return g ? g.label : sid;
    }

    function labelOf(source, key) {
      var g = groups.find(function (x) { return x.id === source; });
      if (!g) return key;
      var hit = g.columns.find(function (c) { return c[0] === key; });
      return hit ? hit[1] : key;
    }

    function reportAccessMode() {
      return (accessInput && accessInput.value) || "readonly";
    }

    function sourceAllowedForAccess(sourceId) {
      var m = reportAccessMode();
      if (m === "editable") return sourceId === "data_entry";
      return sourceId !== "data_entry";
    }

    function showBuilder() {
      confirmedOnce = true;
      if (metaEditor) metaEditor.hidden = true;
      if (builderPanel) builderPanel.hidden = false;
      if (topSubmit) topSubmit.hidden = false;
      if (cancelBtn) cancelBtn.hidden = false;
      if (headingView) headingView.hidden = false;
      if (headingEdit) headingEdit.hidden = true;
      syncHeading();
      renderAll();
    }

    function showMetaEditor() {
      if (metaEditor) metaEditor.hidden = false;
      if (builderPanel) builderPanel.hidden = true;
      if (topSubmit) topSubmit.hidden = true;
      if (cancelBtn) cancelBtn.hidden = !confirmedOnce;
      if (confirmedOnce) {
        if (headingView) headingView.hidden = false;
        if (headingEdit) headingEdit.hidden = true;
      } else {
        if (headingView) headingView.hidden = true;
        if (headingEdit) headingEdit.hidden = false;
      }
    }

    var confirmBtn = document.getElementById("confirm-meta-btn");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", function () {
        if (!titleInput || !titleInput.value.trim()) { alert("عنوان گزارش را وارد کنید."); return; }
        if (!numberInput || !numberInput.value) { alert("شماره گزارش را وارد کنید."); return; }
        showBuilder();
      });
    }
    var editMetaBtn = document.getElementById("edit-meta-btn");
    if (editMetaBtn) editMetaBtn.addEventListener("click", showMetaEditor);
    if (cancelBtn) cancelBtn.addEventListener("click", showBuilder);
    if (accessInput) accessInput.addEventListener("change", function () { fillSourceMenu(); });

    function fillSourceMenu() {
      if (!menuList) return;
      menuList.innerHTML = "";
      var available = groups.filter(function (g) {
        return addedSources.indexOf(g.id) < 0 && sourceAllowedForAccess(g.id);
      });
      if (!available.length) {
        menuList.innerHTML = reportAccessMode() === "editable"
          ? '<p class="muted">منبع «ثبت داده» اضافه شده است.</p>'
          : '<p class="muted">همه منابع اضافه شده‌اند.</p>';
        return;
      }
      available.forEach(function (g) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "source-menu-item";
        btn.textContent = g.label;
        btn.addEventListener("click", function () {
          addSource(g.id);
          var menu = document.getElementById("source-menu");
          if (menu) menu.open = false;
        });
        menuList.appendChild(btn);
      });
    }

    function addSource(sid) {
      if (!sid || addedSources.indexOf(sid) >= 0) return;
      if (!sourceAllowedForAccess(sid)) return;
      addedSources.push(sid);
      renderAll();
    }

    function removeSource(sid) {
      var count = selected.filter(function (c) { return c.source === sid; }).length;
      if (count && !confirm("از این منبع " + count + " ستون انتخاب شده است. با حذف منبع حذف می‌شوند. ادامه؟")) return;
      selected = selected.filter(function (c) { return c.source !== sid; });
      addedSources = addedSources.filter(function (s) { return s !== sid; });
      sourceLinks = sourceLinks.filter(function (L) { return !(L.keys && L.keys[sid]); });
      if (activeIdx >= selected.length) activeIdx = -1;
      renderAll();
    }

    function renderTrees() {
      if (!trees) return;
      trees.innerHTML = "";
      addedSources.forEach(function (sid) {
        var g = groups.find(function (x) { return x.id === sid; });
        if (!g) return;
        var box = document.createElement("div");
        box.className = "source-tree";
        var head = document.createElement("div");
        head.className = "source-tree-head-row";
        var toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "source-tree-head";
        toggle.textContent = "▾ " + g.label;
        var body = document.createElement("div");
        body.className = "source-tree-body";
        toggle.addEventListener("click", function () {
          body.hidden = !body.hidden;
          toggle.textContent = (body.hidden ? "▸ " : "▾ ") + g.label;
        });
        var rm = document.createElement("button");
        rm.type = "button";
        rm.className = "btn btn-xs btn-ghost";
        rm.textContent = "حذف منبع";
        rm.addEventListener("click", function () { removeSource(sid); });
        head.appendChild(toggle);
        head.appendChild(rm);
        g.columns.forEach(function (pair) {
          var key = pair[0], lab = pair[1];
          var labEl = document.createElement("label");
          labEl.className = "chk";
          var cb = document.createElement("input");
          cb.type = "checkbox";
          cb.checked = selected.some(function (c) {
            return c.kind !== "calc" && c.key === key && c.source === sid;
          });
          cb.addEventListener("change", function () {
            if (cb.checked) {
              selected.push({
                key: key, source: sid, level: 1, level_mode: "1", label: lab, origLabel: lab,
                uid: newUid(), width: defaultWidthFor(sid, key), is_key: false,
                kind: "field", col_code: "", number_format: "General", formula: ""
              });
              assignColCodes();
            } else {
              selected = selected.filter(function (c) {
                return !(c.kind !== "calc" && c.key === key && c.source === sid);
              });
            }
            renderSelected();
            syncHidden();
          });
          labEl.appendChild(cb);
          labEl.appendChild(document.createTextNode(" " + lab));
          body.appendChild(labEl);
        });
        box.appendChild(head);
        box.appendChild(body);
        trees.appendChild(box);
      });
    }

    function moveActive(dir) {
      if (activeIdx < 0) return;
      var j = activeIdx + dir;
      if (j < 0 || j >= selected.length) return;
      var tmp = selected[activeIdx];
      selected[activeIdx] = selected[j];
      selected[j] = tmp;
      activeIdx = j;
      renderSelected();
      syncHidden();
    }

    var moveUp = document.getElementById("move-up");
    var moveDown = document.getElementById("move-down");
    var copyCol = document.getElementById("copy-col");
    var addCalcBtn = document.getElementById("add-calc-col");
    if (moveUp) moveUp.addEventListener("click", function () { moveActive(-1); });
    if (moveDown) moveDown.addEventListener("click", function () { moveActive(1); });
    if (copyCol) {
      copyCol.addEventListener("click", function () {
        if (activeIdx < 0 || !selected[activeIdx]) {
          alert("ابتدا یک ردیف را انتخاب کنید.");
          return;
        }
        var src = selected[activeIdx];
        var copy = {
          key: src.key,
          source: src.source,
          level: src.level,
          level_mode: src.level_mode,
          label: (src.label || src.origLabel || src.key) + " (کپی)",
          origLabel: src.origLabel || src.label || src.key,
          uid: newUid(),
          width: clampWidth(src.width || 0) || defaultWidthFor(src.source || "", src.key || ""),
          is_key: false,
          kind: src.kind || "field",
          col_code: nextCopyCode(src.col_code),
          number_format: src.number_format || "General",
          formula: src.kind === "calc" ? (src.formula || "") : ""
        };
        selected.splice(activeIdx + 1, 0, copy);
        activeIdx = activeIdx + 1;
        assignColCodes();
        renderSelected();
        syncHidden();
      });
    }
    if (addCalcBtn) {
      addCalcBtn.addEventListener("click", function () {
        selected.push({
          key: "calc",
          source: "_calc",
          level: 1,
          level_mode: "1",
          label: "محاسبات",
          origLabel: "محاسبات",
          uid: newUid(),
          width: 96,
          is_key: false,
          kind: "calc",
          col_code: "",
          number_format: "#,##0.##",
          formula: ""
        });
        assignColCodes();
        activeIdx = selected.length - 1;
        renderSelected();
        syncHidden();
        openFormulaDialog(activeIdx);
      });
    }

    function updatePath() {
      if (!pathEl) return;
      if (activeIdx < 0 || !selected[activeIdx]) {
        pathEl.textContent = "ردیفی انتخاب نشده است.";
        return;
      }
      var c = selected[activeIdx];
      var bits = [
        "منبع: " + groupLabel(c.source),
        "کد: " + (c.col_code || "—").toUpperCase(),
        (c.origLabel || labelOf(c.source, c.key)) + " (" + c.key + ")"
      ];
      if (c.is_key) bits.push("کلید سطح");
      if (c.width) bits.push("عرض " + c.width + "px");
      if (c.kind === "calc") bits.push("فرمول " + (c.formula || "—"));
      pathEl.textContent = bits.join("  ←  ");
    }

    function formatOptionsHtml(current) {
      var opts = "";
      var seen = {};
      formatPresets.forEach(function (p) {
        seen[p.value] = true;
        opts += '<option value="' + p.value.replace(/"/g, "&quot;") + '"' +
          (current === p.value ? " selected" : "") + ">" + p.label + "</option>";
      });
      if (current && !seen[current]) {
        opts += '<option value="' + String(current).replace(/"/g, "&quot;") + '" selected>' +
          String(current) + "</option>";
      }
      return opts;
    }

    function levelOptionsHtml(current) {
      return LEVEL_OPTIONS.map(function (o) {
        return '<option value="' + o.value + '"' + (current === o.value ? " selected" : "") + ">" +
          o.label + "</option>";
      }).join("");
    }

    function renderSelected() {
      if (!list) return;
      list.innerHTML = "";
      if (!selected.length) {
        list.innerHTML = '<tr><td colspan="8" class="muted empty">ستونی انتخاب نشده است.</td></tr>';
        updatePath();
        return;
      }
      selected.forEach(function (c, idx) {
        var tr = document.createElement("tr");
        tr.className = "display-col-row" + (idx === activeIdx ? " is-active" : "") +
          (c.kind === "calc" ? " is-calc" : "");
        tr.dataset.idx = String(idx);
        var keyable = c.kind !== "calc" && canBeKey(c.source || "", c.key || "");
        var keyChecked = c.is_key && keyable ? " checked" : "";
        var keyDisabled = keyable ? "" : " disabled";
        var fxCell = c.kind === "calc"
          ? '<button type="button" class="btn-fx" data-fx="' + idx + '" title="ویرایش فرمول">ƒx</button>'
          : '<span class="muted">—</span>';
        tr.innerHTML =
          '<td><input class="input sel-rename" data-label="' + idx + '" value="' +
            String(c.label || "").replace(/"/g, "&quot;") + '"></td>' +
          '<td class="col-code-cell" dir="ltr">' + String(c.col_code || "").toUpperCase() + "</td>" +
          '<td><select class="input" data-level="' + idx + '">' + levelOptionsHtml(c.level_mode) + "</select></td>" +
          '<td><input class="input sel-width" type="number" min="40" max="800" step="1" data-width="' + idx +
            '" value="' + (clampWidth(c.width) || "") + '"></td>' +
          '<td class="key-cell"><input type="checkbox" data-key="' + idx + '"' + keyChecked + keyDisabled + "></td>" +
          '<td><input class="input sel-format" list="fmt-presets-' + idx + '" data-format="' + idx +
            '" value="' + String(c.number_format || "General").replace(/"/g, "&quot;") + '">' +
            '<datalist id="fmt-presets-' + idx + '">' + formatOptionsHtml(c.number_format) + "</datalist></td>" +
          '<td class="fx-cell">' + fxCell + "</td>" +
          '<td><button type="button" class="btn btn-xs btn-danger" data-rm="' + idx + '">×</button></td>';
        list.appendChild(tr);
      });
      updatePath();
    }

    if (list) {
      list.addEventListener("click", function (e) {
        var fx = e.target.closest("[data-fx]");
        if (fx) {
          openFormulaDialog(parseInt(fx.getAttribute("data-fx"), 10));
          return;
        }
        var rm = e.target.closest("[data-rm]");
        if (rm) {
          var i = parseInt(rm.getAttribute("data-rm"), 10);
          selected.splice(i, 1);
          if (activeIdx === i) activeIdx = -1;
          else if (activeIdx > i) activeIdx -= 1;
          renderTrees();
          renderSelected();
          syncHidden();
          return;
        }
        if (e.target.closest("select") || e.target.closest("input") || e.target.closest("button")) return;
        var row = e.target.closest(".display-col-row");
        if (!row) return;
        activeIdx = parseInt(row.dataset.idx, 10);
        renderSelected();
      });
      list.addEventListener("dblclick", function (e) {
        var fx = e.target.closest("[data-fx], .fx-cell");
        if (!fx) return;
        var row = e.target.closest(".display-col-row");
        if (!row) return;
        openFormulaDialog(parseInt(row.dataset.idx, 10));
      });
      list.addEventListener("change", function (e) {
        var sel = e.target.closest("[data-level]");
        if (sel) {
          selected[parseInt(sel.getAttribute("data-level"), 10)].level_mode = sel.value;
          syncHidden();
          return;
        }
        var keyCb = e.target.closest("[data-key]");
        if (keyCb) {
          var ki = parseInt(keyCb.getAttribute("data-key"), 10);
          var col = selected[ki];
          if (!col) return;
          if (keyCb.checked && !canBeKey(col.source || "", col.key || "")) {
            keyCb.checked = false;
            alert("مقادیر عددی / محاسباتی نمی‌توانند کلید باشند.");
            return;
          }
          col.is_key = !!keyCb.checked;
          updatePath();
          syncHidden();
        }
      });
      list.addEventListener("input", function (e) {
        var inp = e.target.closest("[data-label]");
        if (inp) {
          selected[parseInt(inp.getAttribute("data-label"), 10)].label = inp.value;
          syncHidden();
          return;
        }
        var wInp = e.target.closest("[data-width]");
        if (wInp) {
          selected[parseInt(wInp.getAttribute("data-width"), 10)].width = clampWidth(wInp.value);
          syncHidden();
          return;
        }
        var fInp = e.target.closest("[data-format]");
        if (fInp) {
          selected[parseInt(fInp.getAttribute("data-format"), 10)].number_format = fInp.value || "General";
          syncHidden();
        }
      });
    }

    function renderFormulaCatalog() {
      var box = document.getElementById("formula-fn-catalog");
      if (!box) return;
      box.innerHTML = "";
      formulaCatalog.forEach(function (cat) {
        var det = document.createElement("details");
        det.className = "formula-fn-group";
        var sum = document.createElement("summary");
        sum.textContent = cat.label;
        det.appendChild(sum);
        var listEl = document.createElement("div");
        listEl.className = "formula-fn-list";
        (cat.functions || []).forEach(function (fn) {
          var item = document.createElement("div");
          item.className = "formula-fn-item";
          item.title = fn.hint || fn.name;
          item.textContent = fn.name;
          item.addEventListener("dblclick", function () {
            insertFormulaSnippet(fn.insert || (fn.name + "()"));
          });
          listEl.appendChild(item);
        });
        det.appendChild(listEl);
        box.appendChild(det);
      });
    }

    function renderFormulaChips() {
      var chips = document.getElementById("formula-col-chips");
      if (!chips) return;
      chips.innerHTML = "";
      var count = 0;
      selected.forEach(function (c, idx) {
        if (idx === formulaEditIdx) return;
        var code = String(c.col_code || "").toUpperCase();
        if (!code) return;
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "formula-chip";
        btn.textContent = code + " · " + (c.label || c.key);
        btn.title = groupLabel(c.source);
        btn.addEventListener("click", function () {
          insertFormulaSnippet(code);
        });
        chips.appendChild(btn);
        count += 1;
      });
      if (!count) {
        var hint = document.createElement("span");
        hint.className = "muted";
        hint.style.fontSize = "12px";
        hint.textContent = "ابتدا ستون‌های منبع را اضافه کنید تا کد آن‌ها اینجا قابل انتخاب باشد.";
        chips.appendChild(hint);
      }
    }

    function insertFormulaSnippet(text) {
      if (!formulaTextarea) return;
      var start = formulaTextarea.selectionStart || 0;
      var end = formulaTextarea.selectionEnd || 0;
      var val = formulaTextarea.value || "";
      formulaTextarea.value = val.slice(0, start) + text + val.slice(end);
      var pos = start + text.length;
      // place caret inside first empty ()
      var open = text.indexOf("(");
      if (open >= 0 && text.indexOf(")", open) === open + 1) {
        pos = start + open + 1;
      }
      formulaTextarea.focus();
      formulaTextarea.setSelectionRange(pos, pos);
    }

    function openFormulaDialog(idx) {
      var col = selected[idx];
      if (!col || col.kind !== "calc") return;
      formulaEditIdx = idx;
      renderFormulaCatalog();
      renderFormulaChips();
      if (formulaTextarea) {
        var f = col.formula || "";
        if (f.charAt(0) === "=") f = f.slice(1);
        formulaTextarea.value = f;
      }
      if (formulaDialog && formulaDialog.showModal) formulaDialog.showModal();
    }

    var formulaSave = document.getElementById("formula-save-btn");
    var formulaCancel = document.getElementById("formula-cancel-btn");
    if (formulaSave) {
      formulaSave.addEventListener("click", function () {
        if (formulaEditIdx < 0 || !selected[formulaEditIdx]) return;
        var raw = ((formulaTextarea && formulaTextarea.value) || "").trim();
        if (raw && raw.charAt(0) !== "=") raw = "=" + raw;
        selected[formulaEditIdx].formula = raw;
        if (formulaDialog) formulaDialog.close();
        formulaEditIdx = -1;
        renderSelected();
        syncHidden();
      });
    }
    if (formulaCancel) {
      formulaCancel.addEventListener("click", function () {
        if (formulaDialog) formulaDialog.close();
        formulaEditIdx = -1;
      });
    }
    if (formulaTextarea) {
      formulaTextarea.addEventListener("keydown", function (e) {
        if (e.key === "," || e.key === ";") {
          // after comma, user can click a chip — highlight picker
          var picker = document.querySelector(".formula-col-picker");
          if (picker) {
            picker.classList.add("is-pulse");
            setTimeout(function () { picker.classList.remove("is-pulse"); }, 700);
          }
        }
      });
    }

    function updateLinkUi() {
      if (!linkBtn || !linkSummary) return;
      var multi = addedSources.length >= 2;
      linkBtn.hidden = !multi;
      if (!sourceLinks.length) {
        linkSummary.textContent = multi ? "هنوز نقطه اشتراکی تعریف نشده است." : "";
        return;
      }
      linkSummary.textContent = sourceLinks.map(function (L) {
        return Object.keys(L.keys || {}).map(function (s) {
          return groupLabel(s) + " ← " + labelOf(s, L.keys[s]);
        }).join("  ≈  ");
      }).join(" | ");
    }

    if (linkBtn) {
      linkBtn.addEventListener("click", function () {
        var box = document.getElementById("link-fields");
        if (!box || !linkDialog) return;
        box.innerHTML = "";
        addedSources.filter(function (s) { return s !== "file"; }).forEach(function (sid) {
          var g = groups.find(function (x) { return x.id === sid; });
          if (!g) return;
          var row = document.createElement("div");
          row.className = "field";
          var lab = document.createElement("label");
          lab.textContent = g.label;
          var sel = document.createElement("select");
          sel.className = "input";
          sel.dataset.source = sid;
          g.columns.forEach(function (pair) {
            var opt = document.createElement("option");
            opt.value = pair[0];
            opt.textContent = pair[1];
            sel.appendChild(opt);
          });
          row.appendChild(lab);
          row.appendChild(sel);
          box.appendChild(row);
        });
        if (linkDialog.showModal) linkDialog.showModal();
      });
    }
    var saveLinks = document.getElementById("save-links-btn");
    if (saveLinks) {
      saveLinks.addEventListener("click", function () {
        var box = document.getElementById("link-fields");
        if (!box) return;
        var keys = {};
        box.querySelectorAll("select[data-source]").forEach(function (sel) {
          keys[sel.dataset.source] = sel.value;
        });
        sourceLinks = [{ keys: keys }];
        if (linkDialog) linkDialog.close();
        updateLinkUi();
        syncHidden();
      });
    }
    document.querySelectorAll("[data-dialog-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var dlg = btn.closest("dialog");
        if (dlg) dlg.close();
      });
    });

    function renderConditions() {
      var box = document.getElementById("conditions-list");
      var empty = document.getElementById("conditions-empty");
      if (!box) return;
      box.querySelectorAll(".condition-row").forEach(function (n) { n.remove(); });
      if (!conditions.length) {
        if (empty) empty.hidden = false;
        return;
      }
      if (empty) empty.hidden = true;
      conditions.forEach(function (cond, idx) {
        var row = document.createElement("div");
        row.className = "condition-row";
        row.innerHTML =
          '<select class="input cond-field" data-ci="' + idx + '">' +
          selected.map(function (c) {
            return '<option value="' + (c.col_code || c.uid) + '"' +
              ((cond.field === (c.col_code || c.uid)) ? " selected" : "") + ">" +
              String(c.col_code || "").toUpperCase() + " — " + (c.label || c.key) + "</option>";
          }).join("") +
          "</select>" +
          '<select class="input cond-op" data-ci="' + idx + '">' +
          ["=", "<>", ">", ">=", "<", "<=", "شامل"].map(function (op) {
            return '<option value="' + op + '"' + (cond.op === op ? " selected" : "") + ">" + op + "</option>";
          }).join("") +
          "</select>" +
          '<input class="input cond-val" data-ci="' + idx + '" value="' +
            String(cond.value || "").replace(/"/g, "&quot;") + '" placeholder="مقدار">' +
          '<button type="button" class="btn btn-xs btn-ghost" data-cond-rm="' + idx + '">حذف</button>';
        box.appendChild(row);
      });
    }

    var addCondBtn = document.getElementById("add-condition-btn");
    if (addCondBtn) {
      addCondBtn.addEventListener("click", function () {
        var first = selected[0];
        conditions.push({
          field: first ? (first.col_code || first.uid) : "",
          op: "=",
          value: ""
        });
        renderConditions();
        syncHidden();
      });
    }
    var condBox = document.getElementById("conditions-list");
    if (condBox) {
      condBox.addEventListener("click", function (e) {
        var rm = e.target.closest("[data-cond-rm]");
        if (!rm) return;
        conditions.splice(parseInt(rm.getAttribute("data-cond-rm"), 10), 1);
        renderConditions();
        syncHidden();
      });
      condBox.addEventListener("change", function (e) {
        var t = e.target;
        var ci = parseInt(t.getAttribute("data-ci"), 10);
        if (isNaN(ci) || !conditions[ci]) return;
        if (t.classList.contains("cond-field")) conditions[ci].field = t.value;
        if (t.classList.contains("cond-op")) conditions[ci].op = t.value;
        syncHidden();
      });
      condBox.addEventListener("input", function (e) {
        var t = e.target;
        if (!t.classList.contains("cond-val")) return;
        var ci = parseInt(t.getAttribute("data-ci"), 10);
        if (isNaN(ci) || !conditions[ci]) return;
        conditions[ci].value = t.value;
        syncHidden();
      });
    }

    function renderAll() {
      fillSourceMenu();
      renderTrees();
      renderSelected();
      updateLinkUi();
      renderConditions();
      syncHidden();
    }

    if (formEl) {
      formEl.addEventListener("submit", function (e) {
        syncHidden();
        var levels = {};
        selected.forEach(function (c) {
          var mode = c.level_mode || "1";
          if (mode === "all") {
            for (var i = 1; i <= 9; i++) levels[i] = true;
          } else if (String(mode).indexOf("upto_") === 0) {
            var up = parseInt(String(mode).slice(5), 10) || 1;
            for (var j = 1; j <= up; j++) levels[j] = true;
          } else {
            levels[parseInt(mode, 10) || 1] = true;
          }
        });
        var levelList = Object.keys(levels).map(Number).sort(function (a, b) { return a - b; });
        if (levelList.length > 1) {
          for (var li = 0; li < levelList.length; li++) {
            var lv = levelList[li];
            var hasKey = selected.some(function (c) {
              if (!c.is_key) return false;
              var mode = c.level_mode || "1";
              if (mode === "all") return true;
              if (String(mode).indexOf("upto_") === 0) {
                return lv <= (parseInt(String(mode).slice(5), 10) || 1);
              }
              return (parseInt(mode, 10) || 1) === lv;
            });
            if (!hasKey) {
              e.preventDefault();
              alert("سطح " + lv + ": برای گزارش چندسطحی حداقل یک ستون کلید مشخص کنید.");
              return;
            }
          }
        }
      });
    }

    if (mode === "edit" || opts.hasErrors) showBuilder();
    else {
      renderAll();
      showMetaEditor();
    }
  }

  global.ERPReportBuilderDisplay = { init: init };
})(window);
