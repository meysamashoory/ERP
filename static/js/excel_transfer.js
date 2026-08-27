/**
 * Excel table → system destination transfer / update dialog (column mapping + levels).
 */
(function () {
  const root = document.getElementById("excel-editor");
  const dialog = document.getElementById("excel-transfer-dialog");
  if (!root || !dialog) return;
  if (root.dataset.canTransfer !== "1") return;

  const csrf =
    (root.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
    (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
    "";
  const transferTpl = root.dataset.transferUrlTemplate || "";
  const destEl = document.getElementById("excel-transfer-destinations");
  const destinations = destEl ? JSON.parse(destEl.textContent || "[]") : [];
  const tablesEl = document.getElementById("excel-tables-data");
  const tables = tablesEl ? JSON.parse(tablesEl.textContent || "[]") : [];
  const byId = {};
  tables.forEach(function (t) {
    byId[String(t.id)] = t;
  });

  const destSelect = document.getElementById("transfer-destination");
  const levelSelect = document.getElementById("transfer-level");
  const mapBody = document.getElementById("transfer-map-body");
  const resultBox = document.getElementById("transfer-result");
  const submitBtn = document.getElementById("transfer-submit");
  const dialogTitle = document.getElementById("transfer-dialog-title");
  const dialogHint = document.getElementById("transfer-dialog-hint");
  let activeTableId = null;
  let activeMode = "transfer";

  destinations.forEach(function (d) {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.label;
    destSelect.appendChild(opt);
  });

  function currentDest() {
    return destinations.find(function (d) {
      return d.id === destSelect.value;
    });
  }

  function currentLevel() {
    const dest = currentDest();
    if (!dest || !dest.levels) return null;
    return (
      dest.levels.find(function (l) {
        return l.id === levelSelect.value;
      }) ||
      dest.levels[0] ||
      null
    );
  }

  function refreshLevels() {
    const dest = currentDest();
    levelSelect.innerHTML = "";
    (dest && dest.levels ? dest.levels : []).forEach(function (lv) {
      const opt = document.createElement("option");
      opt.value = lv.id;
      opt.textContent = lv.label;
      levelSelect.appendChild(opt);
    });
    if (dest && dest.levels && dest.levels[0]) levelSelect.value = dest.levels[0].id;
  }

  function colLetter(index) {
    let n = index + 1;
    let s = "";
    while (n > 0) {
      n -= 1;
      s = String.fromCharCode(65 + (n % 26)) + s;
      n = Math.floor(n / 26);
    }
    return s;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function guessIndex(headers, field) {
    const labels = [field.label, field.key].map(function (x) {
      return String(x || "").toLowerCase();
    });
    for (let i = 0; i < headers.length; i++) {
      const h = String(headers[i] || "").toLowerCase();
      if (!h) continue;
      for (let j = 0; j < labels.length; j++) {
        if (
          labels[j] &&
          (h === labels[j] || h.indexOf(labels[j]) !== -1 || labels[j].indexOf(h) !== -1)
        ) {
          return i;
        }
      }
    }
    const aliases = {
      program_uid: ["شناسه", "uid", "شناسه تعویض"],
      product_code: ["کد کالا", "کد محصول", "کد"],
      product_name: ["نام جنس", "نام محصول", "نام"],
      machine_number: ["دستگاه", "شماره دستگاه"],
      unit_number: ["واحد", "شماره واحد"],
      plan_date: ["تاریخ برنامه", "تاریخ برنامه‌ریزی"],
      plan_number: ["شماره برنامه"],
      planned_qty: ["مقدار تولید برنامه", "مقدار برنامه"],
      produced_qty: ["مقدار تولید واقعی", "مقدار تولید شده", "تولید"],
      scrap_qty: ["ضایعات"],
      plan_start_date: ["تاریخ شروع برنامه"],
      actual_start_date: ["تاریخ شروع واقعی", "راه‌اندازی"],
      actual_end_date: ["تاریخ پایان", "پایان تولید"],
      work_date: ["تاریخ سند", "تاریخ"],
      code: ["کد کالا", "کد محصول", "کد"],
      name: ["نام قطعه", "نام جنس", "نام محصول", "نام"],
      group_name: ["گروه"],
      subgroup_name: ["زیرگروه"],
      parent_code: ["کد محصول والد", "کد والد"],
      component_code: ["کد جزء", "کد قطعه"],
      component_name: ["نام جزء", "نام قطعه"],
      material_code: ["کد ماده", "کد مواد"],
      material_name: ["نام ماده", "نام مواد"],
      quantity_per_unit: ["مقدار به ازای", "مقدار مصرف"],
      status: ["وضعیت", "وضعیت تولید"],
    };
    const list = aliases[field.key] || [];
    for (let i = 0; i < headers.length; i++) {
      const h = String(headers[i] || "");
      for (let j = 0; j < list.length; j++) {
        if (h.indexOf(list[j]) !== -1) return i;
      }
    }
    return -1;
  }

  function selectedIndexes(exceptField) {
    const used = {};
    mapBody.querySelectorAll(".transfer-col-select").forEach(function (sel) {
      if (exceptField && sel.dataset.field === exceptField) return;
      const v = parseInt(sel.value, 10);
      if (!isNaN(v) && v >= 0) used[v] = true;
    });
    return used;
  }

  function buildOptions(headers, selected, exceptField) {
    const used = selectedIndexes(exceptField);
    let html = '<option value="-1">— انتخاب نشده —</option>';
    (headers || []).forEach(function (h, i) {
      if (used[i] && i !== selected) return;
      const label = (h || "ستون " + (i + 1)) + " (" + colLetter(i) + ")";
      html +=
        '<option value="' +
        i +
        '"' +
        (i === selected ? " selected" : "") +
        ">" +
        escapeHtml(label) +
        "</option>";
    });
    return html;
  }

  function refreshExclusiveOptions() {
    const table = byId[String(activeTableId)];
    if (!table) return;
    const headers = Array.isArray(table.headers) ? table.headers : [];
    mapBody.querySelectorAll(".transfer-col-select").forEach(function (sel) {
      const cur = parseInt(sel.value, 10);
      const selected = isNaN(cur) ? -1 : cur;
      const keep = selected;
      sel.innerHTML = buildOptions(headers, keep >= 0 ? keep : -1, sel.dataset.field);
      if (keep >= 0) sel.value = String(keep);
      else sel.value = "-1";
    });
  }

  function renderMap() {
    const level = currentLevel();
    const table = byId[String(activeTableId)];
    mapBody.innerHTML = "";
    if (!level || !table) return;
    const headers = Array.isArray(table.headers) ? table.headers : [];
    const fields = level.fields || [];
    fields.forEach(function (f) {
      const tr = document.createElement("tr");
      const guessed = guessIndex(headers, f);
      tr.innerHTML =
        "<td>" +
        escapeHtml(f.label) +
        (f.required ? ' <span style="color:#b91c1c">*</span>' : "") +
        '</td><td class="muted">' +
        escapeHtml(f.type) +
        '</td><td><select class="input transfer-col-select" data-field="' +
        escapeHtml(f.key) +
        '"></select></td>';
      mapBody.appendChild(tr);
      const sel = tr.querySelector("select");
      sel.innerHTML = buildOptions(headers, guessed >= 0 ? guessed : -1, f.key);
      if (guessed >= 0) sel.value = String(guessed);
      sel.addEventListener("change", refreshExclusiveOptions);
    });
    refreshExclusiveOptions();
  }

  function setTableTransferStatus(tableId, text, isDone) {
    const pane = root.querySelector('.excel-pane[data-table-id="' + tableId + '"]');
    if (!pane) return;
    let badge = pane.querySelector(".excel-transfer-status");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "excel-transfer-status muted";
      const meta = pane.querySelector(".excel-pane-meta");
      if (meta) meta.appendChild(badge);
    }
    badge.textContent = text || "";
    badge.classList.toggle("is-done", !!isDone);
    badge.classList.toggle("is-busy", !!text && !isDone);
  }

  function applyModeUi(mode) {
    activeMode = mode === "update" ? "update" : "transfer";
    if (dialogTitle) {
      dialogTitle.textContent =
        activeMode === "update" ? "بروزرسانی داده جدول" : "انتقال داده جدول";
    }
    if (dialogHint) {
      dialogHint.textContent =
        activeMode === "update"
          ? "فقط ردیف‌های از قبل موجود در سامانه اصلاح می‌شوند؛ ردیف جدید اضافه نمی‌شود. نگاشت ستون‌ها مانند انتقال است و جدول اکسل حذف نمی‌شود."
          : "بخش مقصد و سطح را انتخاب کنید؛ سرستون‌های همان سطح نمایش داده می‌شوند. هر ستون اکسل فقط به یک فیلد نگاشت می‌شود. جدول پس از انتقال حذف نمی‌شود.";
    }
    if (submitBtn) {
      submitBtn.textContent = activeMode === "update" ? "بروزرسانی" : "انتقال";
    }
  }

  function openFor(tableId, mode) {
    activeTableId = tableId;
    applyModeUi(mode || "transfer");
    resultBox.hidden = true;
    resultBox.innerHTML = "";
    submitBtn.disabled = false;
    if (!destSelect.value && destinations[0]) destSelect.value = destinations[0].id;
    refreshLevels();
    renderMap();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");
  }

  destSelect.addEventListener("change", function () {
    refreshLevels();
    renderMap();
  });
  levelSelect.addEventListener("change", renderMap);

  dialog.querySelectorAll("[data-transfer-close]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    });
  });

  root.querySelectorAll(".btn-transfer-table").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const pane = btn.closest(".excel-pane");
      if (!pane) return;
      openFor(pane.dataset.tableId, btn.dataset.transferMode || "transfer");
    });
  });

  submitBtn.addEventListener("click", async function () {
    const dest = currentDest();
    const level = currentLevel();
    const table = byId[String(activeTableId)];
    if (!dest || !level || !table) return;
    const mapping = {};
    mapBody.querySelectorAll(".transfer-col-select").forEach(function (sel) {
      mapping[sel.dataset.field] = parseInt(sel.value, 10);
    });
    const anyMapped = Object.keys(mapping).some(function (k) {
      return mapping[k] >= 0;
    });
    if (!anyMapped) {
      alert("حداقل یک ستون اکسل را به یک فیلد مقصد نگاشت کنید.");
      return;
    }
    const isUpdate = activeMode === "update";
    const baseBusy = isUpdate ? "در حال بروزرسانی" : "در حال انتقال دیتا";
    submitBtn.disabled = true;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    setTableTransferStatus(activeTableId, baseBusy + "… ۰٪", false);

    const url = transferTpl.replace(/\/0\/transfer\/?$/, "/" + table.id + "/transfer/");
    const chunkHistory =
      (dest.id === "production_history" || dest.id === "history") &&
      (level.id === "history_list" || level.id === "list" || !level.id);
    const chunkSize = chunkHistory ? 80 : null;

    try {
      let offset = 0;
      let totalTransferred = 0;
      let totalFailed = 0;
      let lastMessage = "";
      let allAlarms = [];
      let done = false;
      let guard = 0;

      while (!done && guard < 5000) {
        guard += 1;
        const body = {
          destination: dest.id,
          level: level.id,
          mapping: mapping,
          mode: activeMode,
          offset: offset,
        };
        if (chunkSize != null) body.limit = chunkSize;

        const resp = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
          },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        const progress = data.progress || {};
        const percent = typeof progress.percent === "number" ? progress.percent : 100;
        setTableTransferStatus(activeTableId, baseBusy + "… " + percent + "٪", false);

        if (!data.ok && !(data.transferred > 0) && offset === 0) {
          const failLabel = isUpdate ? "✕ بروزرسانی ناموفق" : "✕ انتقال ناموفق";
          setTableTransferStatus(activeTableId, failLabel, false);
          alert(data.error || data.message || failLabel);
          submitBtn.disabled = false;
          return;
        }

        totalTransferred += data.transferred || 0;
        totalFailed += data.failed || 0;
        lastMessage = data.message || lastMessage;
        if (Array.isArray(data.alarms)) allAlarms = allAlarms.concat(data.alarms);

        if (chunkSize == null || progress.done !== false) {
          done = true;
        } else {
          offset = progress.next_offset || offset + chunkSize;
          if (progress.total_rows && offset >= progress.total_rows) done = true;
        }
      }

      const detail =
        allAlarms.length > 0
          ? "\n\nجزئیات خطا:\n• " + allAlarms.slice(0, 8).join("\n• ")
          : "";
      const failLabel = isUpdate ? "✕ بروزرسانی ناموفق" : "✕ انتقال ناموفق";
      const partialLabel = isUpdate ? "بروزرسانی ناقص" : "انتقال ناقص";
      const okLabel = isUpdate ? "بروزرسانی موفق" : "انتقال موفق";

      if (totalFailed > 0 && totalTransferred === 0) {
        setTableTransferStatus(activeTableId, failLabel, false);
        alert((lastMessage || failLabel) + detail);
      } else if (totalFailed > 0) {
        setTableTransferStatus(activeTableId, "⚠ " + (lastMessage || partialLabel) + " — ۱۰۰٪", false);
        alert((lastMessage || partialLabel + " انجام شد.") + detail);
      } else {
        setTableTransferStatus(activeTableId, "✓ " + (lastMessage || okLabel) + " — ۱۰۰٪", true);
        alert(lastMessage || (isUpdate ? "بروزرسانی با موفقیت انجام شد." : "انتقال با موفقیت انجام شد."));
      }
      submitBtn.disabled = false;
    } catch (err) {
      setTableTransferStatus(activeTableId, "", false);
      alert("خطا در ارتباط با سرور. در صورت تکرار، آلارم سیستم را بررسی کنید.");
      submitBtn.disabled = false;
    }
  });

})();
