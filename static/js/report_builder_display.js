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
    var conditionOps = readJson("condition-ops", [
      { value: "=", label: "مساوی" },
      { value: "<>", label: "مخالف" },
      { value: ">", label: "بزرگ‌تر" },
      { value: ">=", label: "بزرگ‌تر یا مساوی" },
      { value: "<", label: "کوچک‌تر" },
      { value: "<=", label: "کوچک‌تر یا مساوی" },
      { value: "contains", label: "شامل" }
    ]);
    var parametersCatalog = readJson("parameters-catalog", {});
    var fieldChoicesCatalog = readJson("field-choices", {});
    var paramCapableKeys = readJson("param-capable-keys", []);
    var paramKeySet = {};
    (paramCapableKeys || []).forEach(function (k) { paramKeySet[k] = true; });

    function normalizeConditionsBlob(raw) {
      var out = { public: [], private: {} };
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
      if (Array.isArray(raw.public)) out.public = raw.public.slice();
      if (raw.private && typeof raw.private === "object") {
        Object.keys(raw.private).forEach(function (k) {
          if (Array.isArray(raw.private[k])) out.private[k] = raw.private[k].slice();
        });
      }
      return out;
    }
    var conditionsBlob = normalizeConditionsBlob(readJson("conditions-initial", {}));
    var condScope = "public";
    var condEditIdx = -1;

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
      var text = formatHeading() || "—";
      if (headingText) headingText.textContent = text;
      var winTitle = document.getElementById("rp-window-title");
      if (winTitle) winTitle.textContent = text;
      try { document.title = text; } catch (e) {}
    }

    function syncConditionsHidden() {
      if (!conditionsHidden) return;
      var cleaned = {};
      Object.keys(conditionsBlob.private || {}).forEach(function (k) {
        var arr = conditionsBlob.private[k] || [];
        if (arr.length) cleaned[k] = arr;
      });
      conditionsHidden.value = JSON.stringify({
        public: conditionsBlob.public || [],
        private: cleaned
      });
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
      syncConditionsHidden();
    }

    function privateCountFor(uid) {
      var arr = (conditionsBlob.private || {})[uid];
      return arr && arr.length ? arr.length : 0;
    }

    function currentCondList() {
      if (condScope === "public") return conditionsBlob.public || [];
      if (activeIdx < 0 || !selected[activeIdx]) return null;
      var uid = selected[activeIdx].uid;
      if (!conditionsBlob.private[uid]) conditionsBlob.private[uid] = [];
      return conditionsBlob.private[uid];
    }

    function setCurrentCondList(arr) {
      if (condScope === "public") conditionsBlob.public = arr;
      else if (activeIdx >= 0 && selected[activeIdx]) {
        conditionsBlob.private[selected[activeIdx].uid] = arr;
      }
      syncConditionsHidden();
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
    var deleteColBtn = document.getElementById("delete-col");
    var addCalcBtn = document.getElementById("add-calc-col");

    function updateMoveControls() {
      var has = activeIdx >= 0 && !!selected[activeIdx];
      [moveUp, moveDown, copyCol, deleteColBtn].forEach(function (b) {
        if (b) b.disabled = !has;
      });
    }

    if (moveUp) moveUp.addEventListener("click", function () { moveActive(-1); });
    if (moveDown) moveDown.addEventListener("click", function () { moveActive(1); });
    if (deleteColBtn) {
      deleteColBtn.addEventListener("click", function () {
        if (activeIdx < 0 || !selected[activeIdx]) return;
        var removed = selected[activeIdx];
        selected.splice(activeIdx, 1);
        if (removed && conditionsBlob.private[removed.uid]) {
          delete conditionsBlob.private[removed.uid];
        }
        if (activeIdx >= selected.length) activeIdx = selected.length - 1;
        renderTrees();
        renderSelected();
        renderConditions();
        syncHidden();
      });
    }
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
        activeIdx = -1;
        updatePath();
        updateMoveControls();
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
        var privN = privateCountFor(c.uid);
        var privCell = privN
          ? '<span class="rb-private-badge" title="دارای شرط خصوصی">P</span>'
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
          '<td class="priv-cell">' + privCell + "</td>";
        list.appendChild(tr);
      });
      updatePath();
      updateMoveControls();
    }

    if (list) {
      list.addEventListener("click", function (e) {
        var fx = e.target.closest("[data-fx]");
        if (fx) {
          openFormulaDialog(parseInt(fx.getAttribute("data-fx"), 10));
          return;
        }
        if (e.target.closest("select") || e.target.closest("input") || e.target.closest("button")) return;
        var row = e.target.closest(".display-col-row");
        if (!row) return;
        activeIdx = parseInt(row.dataset.idx, 10);
        renderSelected();
        if (condScope === "private") renderConditions();
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

    function opLabel(v) {
      var hit = conditionOps.find(function (o) { return o.value === v; });
      return hit ? hit.label : v;
    }

    function fieldSupportsParam(fieldKey) {
      return !!paramKeySet[fieldKey];
    }

    function fillCondSources(sel, selectedSource) {
      if (!sel) return;
      var html = '<option value="">— منبع —</option>';
      groups.forEach(function (g) {
        if (!sourceAllowedForAccess(g.id)) return;
        html += '<option value="' + g.id + '"' + (g.id === selectedSource ? " selected" : "") + ">" +
          g.label + "</option>";
      });
      sel.innerHTML = html;
    }

    function fillCondFields(sel, sourceId, selectedField) {
      if (!sel) return;
      var g = groups.find(function (x) { return x.id === sourceId; });
      var html = '<option value="">— فیلد —</option>';
      if (g && g.columns) {
        g.columns.forEach(function (pair) {
          var k = pair[0];
          var lab = pair[1];
          html += '<option value="' + k + '"' + (k === selectedField ? " selected" : "") + ">" +
            lab + "</option>";
        });
      }
      sel.innerHTML = html;
    }

    function fillCondOps(sel, selectedOp) {
      if (!sel) return;
      sel.innerHTML = conditionOps.map(function (o) {
        return '<option value="' + o.value + '"' + (o.value === selectedOp ? " selected" : "") + ">" +
          o.label + "</option>";
      }).join("");
    }

    function refreshCondValueModeOptions() {
      var modeSel = document.getElementById("cond-value-mode");
      var fieldSel = document.getElementById("cond-field");
      if (!modeSel) return;
      var fieldKey = fieldSel ? fieldSel.value : "";
      var allow = fieldSupportsParam(fieldKey);
      var cur = modeSel.value || "value";
      modeSel.innerHTML = '<option value="value">value</option>' +
        (allow ? '<option value="parameter">parameter</option>' : "");
      modeSel.value = allow && cur === "parameter" ? "parameter" : "value";
      refreshCondValueWidgets();
    }

    function refreshCondValueWidgets() {
      var modeSel = document.getElementById("cond-value-mode");
      var fieldSel = document.getElementById("cond-field");
      var valueEl = document.getElementById("cond-value");
      var paramEl = document.getElementById("cond-param");
      var offsetEl = document.getElementById("cond-value-offset");
      var mode = modeSel ? modeSel.value : "value";
      var fieldKey = fieldSel ? fieldSel.value : "";
      var choices = fieldChoicesCatalog[fieldKey] || null;
      var params = parametersCatalog[fieldKey] || [];
      var allowParam = fieldSupportsParam(fieldKey);

      if (paramEl) {
        if (mode === "parameter") {
          paramEl.hidden = false;
          paramEl.innerHTML = '<option value="">— پارامتر —</option>' +
            params.map(function (p) {
              return '<option value="' + p.code + '">' + p.label + "</option>";
            }).join("");
        } else {
          paramEl.hidden = true;
        }
      }

      if (valueEl) {
        if (mode === "parameter") {
          valueEl.hidden = true;
        } else {
          valueEl.hidden = false;
          // Rebuild as select or keep input
          var wrap = document.getElementById("cond-value-wrap");
          var useSelect = false;
          var options = [];
          if (choices && choices.length) {
            useSelect = true;
            options = choices;
          } else if (allowParam && params.length) {
            // value mode + param-capable: show params as selectable presets
            useSelect = true;
            options = params.map(function (p) {
              return { value: "__param__:" + p.code, label: p.label + " (پارامتر)" };
            });
          }
          if (useSelect) {
            if (valueEl.tagName !== "SELECT") {
              var sel = document.createElement("select");
              sel.className = "input";
              sel.id = "cond-value";
              sel.name = "cond_value";
              valueEl.parentNode.replaceChild(sel, valueEl);
              valueEl = sel;
            }
            valueEl.innerHTML = '<option value="">— مقدار —</option>' +
              options.map(function (c) {
                return '<option value="' + String(c.value).replace(/"/g, "&quot;") + '">' +
                  c.label + "</option>";
              }).join("");
          } else {
            if (valueEl.tagName !== "INPUT") {
              var inp = document.createElement("input");
              inp.className = "input";
              inp.id = "cond-value";
              inp.name = "cond_value";
              inp.type = "text";
              inp.autocomplete = "off";
              valueEl.parentNode.replaceChild(inp, valueEl);
              valueEl = inp;
            }
          }
          if (wrap) {
            var lab = wrap.querySelector("label");
            if (lab) lab.setAttribute("for", "cond-value");
          }
        }
      }

      if (offsetEl) {
        var valNow = document.getElementById("cond-value");
        var picked = valNow ? String(valNow.value || "") : "";
        var enableOffset = mode === "value" && allowParam && picked.indexOf("__param__:") === 0;
        offsetEl.disabled = !enableOffset;
        if (!enableOffset) offsetEl.value = "";
      }
    }

    function validateCondDraft(draft, list, editIdx) {
      if (!draft.source) return "منبع را انتخاب کنید.";
      if (!draft.field) return "فیلد را انتخاب کنید.";
      if (!draft.op) return "عملگر را انتخاب کنید.";
      if (editIdx <= 0 && (editIdx === 0 || (editIdx < 0 && !list.length))) {
        if (draft.logic) return "شرط اول نباید AND/OR داشته باشد.";
      } else if (editIdx !== 0) {
        var isFirst = editIdx < 0 ? !list.length : editIdx === 0;
        if (!isFirst && !draft.logic) return "برای شرط‌های بعدی AND یا OR را مشخص کنید.";
      }
      if (draft.value_mode === "parameter") {
        if (!fieldSupportsParam(draft.field)) return "این فیلد از پارامتر پشتیبانی نمی‌کند.";
        if (!draft.param_code) return "پارامتر را انتخاب کنید.";
      } else {
        if (draft.param_code) {
          if (!String(draft.value_offset || "").trim()) {
            return "برای قفل مقدار با پارامتر، عدد/مقدار افست را وارد کنید.";
          }
        } else if (!String(draft.value || "").trim() && draft.op !== "empty" && draft.op !== "not_empty") {
          return "مقدار شرط را وارد کنید.";
        }
      }
      var open = 0;
      list.forEach(function (c, i) {
        if (i === editIdx) return;
        if (c.paren === "(") open += 1;
        if (c.paren === ")") open -= 1;
      });
      if (draft.paren === "(") open += 1;
      if (draft.paren === ")") open -= 1;
      if (open < 0) return "پرانتز بسته بدون پرانتز باز مجاز نیست.";
      return "";
    }

    function openConditionDialog(editIdx) {
      var dialog = document.getElementById("condition-dialog");
      if (!dialog) return;
      if (condScope === "private" && (activeIdx < 0 || !selected[activeIdx])) {
        alert("برای شرط خصوصی ابتدا یک ستون را در نحوه نمایش انتخاب کنید.");
        return;
      }
      condEditIdx = typeof editIdx === "number" ? editIdx : -1;
      var errEl = document.getElementById("cond-dlg-error");
      if (errEl) { errEl.hidden = true; errEl.textContent = ""; }
      var titleEl = dialog.querySelector(".dialog-head h3");
      if (titleEl) titleEl.textContent = condEditIdx >= 0 ? "ویرایش شرط" : "شرط گزارش";

      var base = {
        logic: "", paren: "", source: "", field: "", op: "=",
        value_mode: "value", value: "", param_code: "", value_offset: ""
      };
      var list = currentCondList() || [];
      if (condEditIdx >= 0 && list[condEditIdx]) {
        base = Object.assign(base, list[condEditIdx]);
      }

      fillCondSources(document.getElementById("cond-source"), base.source);
      fillCondFields(document.getElementById("cond-field"), base.source, base.field);
      fillCondOps(document.getElementById("cond-operator"), base.op || "=");
      var logicEl = document.getElementById("cond-logic");
      var parenEl = document.getElementById("cond-paren");
      if (logicEl) logicEl.value = base.logic || "";
      if (parenEl) parenEl.value = base.paren || "";
      refreshCondValueModeOptions();
      var modeEl = document.getElementById("cond-value-mode");
      if (modeEl) {
        modeEl.value = base.value_mode === "parameter" ? "parameter" : "value";
      }
      refreshCondValueWidgets();
      if (base.value_mode === "parameter") {
        var pEl = document.getElementById("cond-param");
        if (pEl) pEl.value = base.param_code || "";
      } else {
        var vEl = document.getElementById("cond-value");
        if (vEl) {
          if (base.param_code) vEl.value = "__param__:" + base.param_code;
          else vEl.value = base.value || "";
        }
        refreshCondValueWidgets();
        var off = document.getElementById("cond-value-offset");
        if (off) off.value = base.value_offset || "";
      }
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    }

    function saveConditionDialog() {
      var list = currentCondList();
      if (!list) {
        alert("برای شرط خصوصی ابتدا یک ستون را انتخاب کنید.");
        return;
      }
      var modeEl = document.getElementById("cond-value-mode");
      var mode = modeEl ? modeEl.value : "value";
      var draft = {
        logic: (document.getElementById("cond-logic") || {}).value || "",
        paren: (document.getElementById("cond-paren") || {}).value || "",
        source: (document.getElementById("cond-source") || {}).value || "",
        field: (document.getElementById("cond-field") || {}).value || "",
        op: (document.getElementById("cond-operator") || {}).value || "=",
        value_mode: mode,
        value: "",
        param_code: "",
        value_offset: ""
      };
      if (mode === "parameter") {
        draft.param_code = (document.getElementById("cond-param") || {}).value || "";
      } else {
        var raw = (document.getElementById("cond-value") || {}).value || "";
        if (String(raw).indexOf("__param__:") === 0) {
          draft.param_code = String(raw).slice("__param__:".length);
          draft.value_offset = (document.getElementById("cond-value-offset") || {}).value || "";
          draft.value = draft.value_offset;
        } else {
          draft.value = String(raw).trim();
        }
      }
      var err = validateCondDraft(draft, list.slice(), condEditIdx);
      var errEl = document.getElementById("cond-dlg-error");
      if (err) {
        if (errEl) { errEl.hidden = false; errEl.textContent = err; }
        else alert(err);
        return;
      }
      if (condEditIdx >= 0) list[condEditIdx] = draft;
      else list.push(draft);
      setCurrentCondList(list);
      var dialog = document.getElementById("condition-dialog");
      if (dialog) {
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
      }
      renderConditions();
      renderSelected();
    }

    function renderConditions() {
      var box = document.getElementById("conditions-list");
      var empty = document.getElementById("conditions-empty");
      var table = document.getElementById("conditions-table");
      var tbody = document.getElementById("conditions-tbody");
      if (!box) return;

      if (tbody) tbody.innerHTML = "";
      else box.querySelectorAll(".condition-row").forEach(function (n) { n.remove(); });

      if (condScope === "private" && (activeIdx < 0 || !selected[activeIdx])) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = "برای شرط خصوصی ابتدا یک ستون را انتخاب کنید.";
        }
        if (table) table.hidden = true;
        return;
      }

      var list = currentCondList() || [];
      if (!list.length) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = condScope === "private"
            ? "شرط خصوصی برای این ستون ثبت نشده است."
            : "هنوز شرطی تعریف نشده است.";
        }
        if (table) table.hidden = true;
        syncConditionsHidden();
        return;
      }
      if (empty) empty.hidden = true;
      if (table) table.hidden = false;

      list.forEach(function (cond, idx) {
        var valShow = cond.value_mode === "parameter"
          ? ("پارامتر: " + (cond.param_code || "—"))
          : (cond.param_code
            ? ((cond.param_code || "") + " → " + (cond.value_offset || cond.value || ""))
            : (cond.value || ""));
        var html =
          "<td>" + (cond.logic ? String(cond.logic).toUpperCase() : "—") + "</td>" +
          "<td dir=\"ltr\">" + (cond.paren || "—") + "</td>" +
          "<td>" + groupLabel(cond.source) + "</td>" +
          "<td>" + labelOf(cond.source, cond.field) + "</td>" +
          "<td>" + opLabel(cond.op) + "</td>" +
          "<td>" + String(valShow) + "</td>" +
          '<td class="cond-row-actions">' +
            '<button type="button" class="btn btn-xs btn-ghost" data-cond-edit="' + idx + '">ویرایش</button> ' +
            '<button type="button" class="btn btn-xs btn-ghost" data-cond-rm="' + idx + '">حذف</button>' +
          "</td>";
        if (tbody) {
          var tr = document.createElement("tr");
          tr.className = "condition-row";
          tr.innerHTML = html;
          tbody.appendChild(tr);
        } else {
          var row = document.createElement("div");
          row.className = "condition-row";
          row.innerHTML = html;
          box.appendChild(row);
        }
      });
      syncConditionsHidden();
    }

    document.querySelectorAll(".cond-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll(".cond-tab").forEach(function (t) {
          t.classList.toggle("is-active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        condScope = tab.getAttribute("data-cond-scope") || "public";
        var listEl = document.getElementById("conditions-list");
        if (listEl) listEl.setAttribute("data-active-scope", condScope);
        renderConditions();
      });
    });

    var addCondBtn = document.getElementById("add-condition-btn");
    if (addCondBtn) {
      addCondBtn.addEventListener("click", function () {
        openConditionDialog(-1);
      });
    }
    var condSaveBtn = document.getElementById("condition-save-btn");
    if (condSaveBtn) condSaveBtn.addEventListener("click", saveConditionDialog);
    var condCancelBtn = document.getElementById("condition-cancel-btn");
    if (condCancelBtn) {
      condCancelBtn.addEventListener("click", function () {
        var dialog = document.getElementById("condition-dialog");
        if (dialog) {
          if (typeof dialog.close === "function") dialog.close();
          else dialog.removeAttribute("open");
        }
      });
    }
    var condSource = document.getElementById("cond-source");
    if (condSource) {
      condSource.addEventListener("change", function () {
        fillCondFields(document.getElementById("cond-field"), condSource.value, "");
        refreshCondValueModeOptions();
      });
    }
    var condField = document.getElementById("cond-field");
    if (condField) condField.addEventListener("change", refreshCondValueModeOptions);
    var condMode = document.getElementById("cond-value-mode");
    if (condMode) condMode.addEventListener("change", refreshCondValueWidgets);
    document.addEventListener("change", function (e) {
      if (e.target && e.target.id === "cond-value") refreshCondValueWidgets();
    });

    var condBox = document.getElementById("conditions-list");
    if (condBox) {
      condBox.addEventListener("click", function (e) {
        var edit = e.target.closest("[data-cond-edit]");
        if (edit) {
          openConditionDialog(parseInt(edit.getAttribute("data-cond-edit"), 10));
          return;
        }
        var rm = e.target.closest("[data-cond-rm]");
        if (!rm) return;
        var list = currentCondList();
        if (!list) return;
        list.splice(parseInt(rm.getAttribute("data-cond-rm"), 10), 1);
        setCurrentCondList(list);
        renderConditions();
        renderSelected();
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
