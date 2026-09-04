/* Report builder: sources, levels, width, key columns. */
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

  function init(opts) {
    opts = opts || {};
    var mode = opts.mode || "create";
    var hasErrors = !!opts.hasErrors;
    var groups = readJson("column-groups", []);
    var keyability = readJson("column-keyability", {});
    var hidden = document.getElementById("id_columns_json");
    var linksHidden = document.getElementById("id_source_links_json");
    if (!hidden) return;

    var selected = readJson("columns-initial", []);
    var sourceLinks = readJson("links-initial", []);

    function canBeKey(source, key) {
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
      if (g && Array.isArray(g.columns)) {
        for (var i = 0; i < g.columns.length; i++) {
          var pair = g.columns[i];
          if (!pair || pair[0] !== key) continue;
          if (pair.length > 2) {
            var fromPair = clampWidth(pair[2]);
            if (fromPair) return fromPair;
          }
          break;
        }
      }
      return 160;
    }

    selected = (selected || []).map(function (item) {
      if (typeof item === "string") {
        return {
          key: item, source: "fitting", level: 1, label: item, origLabel: item,
          uid: newUid(), width: defaultWidthFor("fitting", item), is_key: false
        };
      }
      item.origLabel = item.origLabel || item.label || item.key;
      if (!item.uid) item.uid = newUid();
      item.width = clampWidth(item.width || 0);
      item.is_key = !!item.is_key && canBeKey(item.source || "", item.key || "");
      return item;
    });

    var addedSources = [];
    selected.forEach(function (c) {
      if (c.source && addedSources.indexOf(c.source) < 0) addedSources.push(c.source);
    });
    var activeIdx = -1;

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
      var text = formatHeading();
      if (headingText) headingText.textContent = text || "—";
    }

    function syncHidden() {
      hidden.value = JSON.stringify(selected);
      if (linksHidden) linksHidden.value = JSON.stringify(sourceLinks);
    }

    function groupLabel(sid) {
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
    if (accessInput) {
      accessInput.addEventListener("change", function () { fillSourceMenu(); });
    }

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
      if (linkBtn && addedSources.filter(function (s) { return s !== "file"; }).length >= 2) {
        linkBtn.hidden = false;
      }
    }

    function removeSource(sid) {
      var count = selected.filter(function (c) { return c.source === sid; }).length;
      if (count && !confirm("از این منبع " + count + " ستون انتخاب شده است. با حذف منبع حذف می‌شوند. ادامه؟")) return;
      selected = selected.filter(function (c) { return c.source !== sid; });
      addedSources = addedSources.filter(function (s) { return s !== sid; });
      sourceLinks = sourceLinks.filter(function (L) {
        return !(L.keys && L.keys[sid]);
      });
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
          cb.checked = selected.some(function (c) { return c.key === key && c.source === sid; });
          cb.addEventListener("change", function () {
            if (cb.checked) {
              selected.push({
                key: key, source: sid, level: 1, label: lab, origLabel: lab,
                uid: newUid(), width: defaultWidthFor(sid, key), is_key: false
              });
            } else {
              selected = selected.filter(function (c) { return !(c.key === key && c.source === sid); });
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
          label: (src.label || src.origLabel || src.key) + " (کپی)",
          origLabel: src.origLabel || src.label || src.key,
          uid: newUid(),
          width: clampWidth(src.width || 0) || defaultWidthFor(src.source || "", src.key || ""),
          is_key: false
        };
        selected.splice(activeIdx + 1, 0, copy);
        activeIdx = activeIdx + 1;
        renderSelected();
        syncHidden();
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
        (c.origLabel || labelOf(c.source, c.key)) + " (" + c.key + ")"
      ];
      if (c.is_key) bits.push("کلید سطح");
      if (c.width) bits.push("عرض " + c.width + "px");
      pathEl.textContent = bits.join("  ←  ");
    }

    function renderSelected() {
      if (!list) return;
      list.innerHTML = "";
      if (!selected.length) {
        list.innerHTML = '<p class="muted">ستونی انتخاب نشده است.</p>';
        updatePath();
        return;
      }
      selected.forEach(function (c, idx) {
        var row = document.createElement("div");
        row.className = "selected-col-row" + (idx === activeIdx ? " is-active" : "");
        row.dataset.idx = String(idx);
        var opts = "";
        for (var n = 1; n <= 10; n++) {
          opts += '<option value="' + n + '"' + (Number(c.level) === n ? " selected" : "") + ">" + n + "</option>";
        }
        var keyable = canBeKey(c.source || "", c.key || "");
        var keyChecked = c.is_key && keyable ? " checked" : "";
        var keyDisabled = keyable ? "" : " disabled";
        var keyTitle = keyable ? "ستون کلید برای اتصال سطوح" : "مقادیر عددی نمی‌توانند کلید باشند";
        row.innerHTML =
          '<input class="input sel-rename" data-label="' + idx + '" value="' + String(c.label || "").replace(/"/g, "&quot;") + '">' +
          '<label class="level-label">سطح <select data-level="' + idx + '">' + opts + "</select></label>" +
          '<label class="width-label" title="عرض ستون (پیکسل)">عرض <input class="input sel-width" type="number" min="40" max="800" step="1" data-width="' + idx + '" value="' + (clampWidth(c.width) || "") + '" placeholder="خودکار"></label>' +
          '<label class="key-label chk" title="' + keyTitle + '"><input type="checkbox" data-key="' + idx + '"' + keyChecked + keyDisabled + '> کلید</label>' +
          '<button type="button" class="btn btn-xs btn-danger" data-rm="' + idx + '">×</button>';
        list.appendChild(row);
      });
      updatePath();
    }

    if (list) {
      list.addEventListener("click", function (e) {
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
        if (e.target.closest("select") || e.target.closest("input")) return;
        var row = e.target.closest(".selected-col-row");
        if (!row) return;
        activeIdx = parseInt(row.dataset.idx, 10);
        renderSelected();
      });
      list.addEventListener("change", function (e) {
        var sel = e.target.closest("[data-level]");
        if (sel) {
          selected[parseInt(sel.getAttribute("data-level"), 10)].level = parseInt(sel.value, 10);
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
            alert("مقادیر عددی نمی‌توانند کلید باشند.");
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
          var i = parseInt(inp.getAttribute("data-label"), 10);
          selected[i].label = inp.value;
          syncHidden();
          return;
        }
        var wInp = e.target.closest("[data-width]");
        if (wInp) {
          var wi = parseInt(wInp.getAttribute("data-width"), 10);
          selected[wi].width = clampWidth(wInp.value);
          syncHidden();
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
        if (!box) return;
        box.innerHTML = "";
        addedSources.forEach(function (sid) {
          var g = groups.find(function (x) { return x.id === sid; });
          if (!g) return;
          var field = document.createElement("div");
          field.className = "field";
          var lab = document.createElement("label");
          lab.textContent = "ستون مشترک در «" + g.label + "»";
          var sel = document.createElement("select");
          sel.dataset.source = sid;
          sel.innerHTML = '<option value="">انتخاب ستون…</option>';
          g.columns.forEach(function (pair) {
            var opt = document.createElement("option");
            opt.value = pair[0];
            opt.textContent = pair[1];
            var existing = sourceLinks[0] && sourceLinks[0].keys && sourceLinks[0].keys[sid];
            if (existing === pair[0]) opt.selected = true;
            sel.appendChild(opt);
          });
          field.appendChild(lab);
          field.appendChild(sel);
          box.appendChild(field);
        });
        if (linkDialog) {
          if (typeof linkDialog.showModal === "function") linkDialog.showModal();
          else linkDialog.setAttribute("open", "");
        }
      });
    }

    var saveLinksBtn = document.getElementById("save-links-btn");
    if (saveLinksBtn) {
      saveLinksBtn.addEventListener("click", function () {
        var keys = {};
        document.querySelectorAll("#link-fields select").forEach(function (sel) {
          if (sel.value) keys[sel.dataset.source] = sel.value;
        });
        if (Object.keys(keys).length < 2) {
          alert("حداقل برای دو منبع ستون مشترک انتخاب کنید.");
          return;
        }
        sourceLinks = [{ keys: keys }];
        syncHidden();
        updateLinkUi();
        if (linkDialog) {
          if (typeof linkDialog.close === "function") linkDialog.close();
          else linkDialog.removeAttribute("open");
        }
      });
    }
    if (linkDialog) {
      linkDialog.addEventListener("click", function (e) {
        if (e.target.closest("[data-dialog-close]")) {
          if (typeof linkDialog.close === "function") linkDialog.close();
          else linkDialog.removeAttribute("open");
        }
      });
    }

    if (formEl) {
      formEl.addEventListener("submit", function (e) {
        var levels = {};
        selected.forEach(function (c) {
          var lv = Number(c.level) || 1;
          if (!levels[lv]) levels[lv] = [];
          levels[lv].push(c);
        });
        var levelNums = Object.keys(levels).map(Number).sort(function (a, b) { return a - b; });
        if (levelNums.length > 1) {
          for (var i = 0; i < levelNums.length; i++) {
            var lv = levelNums[i];
            var hasKey = levels[lv].some(function (c) { return c.is_key; });
            if (!hasKey) {
              e.preventDefault();
              alert("سطح " + lv + ": برای گزارش چندسطحی حداقل یک ستون کلید مشخص کنید.");
              return;
            }
          }
        }
        syncHidden();
      });
    }

    function renderAll() {
      fillSourceMenu();
      renderTrees();
      renderSelected();
      updateLinkUi();
      syncHidden();
    }

    if (hasErrors) {
      showMetaEditor();
      renderAll();
    } else if (mode === "edit") {
      showBuilder();
    } else {
      showMetaEditor();
      renderAll();
    }
  }

  global.ERPReportBuilderDisplay = { init: init };
})(window);
