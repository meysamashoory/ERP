/**
 * Excel table → system destination transfer dialog (column mapping + alarms).
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
  const mapBody = document.getElementById("transfer-map-body");
  const resultBox = document.getElementById("transfer-result");
  const submitBtn = document.getElementById("transfer-submit");
  let activeTableId = null;

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

  function excelOptions(headers) {
    let html = '<option value="-1">— انتخاب نشده —</option>';
    (headers || []).forEach(function (h, i) {
      const label = (h || "ستون " + (i + 1)) + " (" + colLetter(i) + ")";
      html += '<option value="' + i + '">' + escapeHtml(label) + "</option>";
    });
    return html;
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
        if (labels[j] && (h === labels[j] || h.indexOf(labels[j]) !== -1 || labels[j].indexOf(h) !== -1)) {
          return i;
        }
      }
    }
    // Persian common aliases
    const aliases = {
      program_uid: ["شناسه", "uid", "id برنامه", "شماره شناسه", "شناسه تعویض"],
      product_code: ["کد کالا", "کد محصول", "کد"],
      product_name: ["نام جنس", "نام محصول", "نام قطعه", "نام"],
      machine_number: ["دستگاه", "شماره دستگاه"],
      unit_number: ["واحد", "شماره واحد"],
      plan_date: ["تاریخ برنامه", "تاریخ برنامه‌ریزی", "تاریخ"],
      plan_number: ["شماره برنامه"],
      planned_qty: ["مقدار برنامه", "مقدار تولید برنامه", "برنامه"],
      produced_qty: ["مقدار تولید", "مقدار تولید واقعی", "تولید"],
      scrap_qty: ["ضایعات", "ضایعات تولید"],
      planned_cycle: ["سیکل تولید برنامه", "سیکل برنامه"],
      last_cycle: ["آخرین سیکل"],
      plan_start_date: ["تاریخ شروع برنامه"],
      actual_start_date: ["تاریخ شروع واقعی", "تاریخ راه‌اندازی"],
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

  function renderMap() {
    const dest = currentDest();
    const table = byId[String(activeTableId)];
    mapBody.innerHTML = "";
    if (!dest || !table) return;
    const headers = Array.isArray(table.headers) ? table.headers : [];
    const opts = excelOptions(headers);
    dest.fields.forEach(function (f) {
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
        '">' +
        opts +
        "</select></td>";
      mapBody.appendChild(tr);
      const sel = tr.querySelector("select");
      if (guessed >= 0) sel.value = String(guessed);
    });
  }

  function openFor(tableId) {
    activeTableId = tableId;
    resultBox.hidden = true;
    resultBox.innerHTML = "";
    submitBtn.disabled = false;
    if (!destSelect.value && destinations[0]) destSelect.value = destinations[0].id;
    renderMap();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");
  }

  destSelect.addEventListener("change", renderMap);

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
      openFor(pane.dataset.tableId);
    });
  });

  submitBtn.addEventListener("click", async function () {
    const dest = currentDest();
    const table = byId[String(activeTableId)];
    if (!dest || !table) return;
    const mapping = {};
    mapBody.querySelectorAll(".transfer-col-select").forEach(function (sel) {
      mapping[sel.dataset.field] = parseInt(sel.value, 10);
    });
    const requiredMissing = (dest.fields || []).some(function (f) {
      return f.required && (mapping[f.key] === undefined || mapping[f.key] < 0);
    });
    if (requiredMissing) {
      alert("ستون‌های الزامی مقصد را نگاشت کنید.");
      return;
    }
    if (
      !confirm(
        "پس از انتقال، جدول «" +
          (table.name || "") +
          "» از بخش بارگذاری حذف می‌شود. ادامه؟"
      )
    ) {
      return;
    }
    submitBtn.disabled = true;
    const url = transferTpl.replace(/\/0\/transfer\/?$/, "/" + table.id + "/transfer/");
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ destination: dest.id, mapping: mapping }),
      });
      const data = await resp.json();
      if (!data.ok) {
        alert(data.error || "انتقال ناموفق بود.");
        submitBtn.disabled = false;
        return;
      }
      let html = "<p><strong>" + escapeHtml(data.message || "انجام شد") + "</strong></p>";
      if (data.alarms && data.alarms.length) {
        html += '<ul class="transfer-alarms">';
        data.alarms.forEach(function (a) {
          html += "<li>" + escapeHtml(a) + "</li>";
        });
        html += "</ul>";
      }
      resultBox.innerHTML = html;
      resultBox.hidden = false;
      setTimeout(function () {
        window.location.href = data.redirect_url || "/data/excel/";
      }, data.alarms && data.alarms.length ? 1800 : 600);
    } catch (err) {
      alert("خطا در ارتباط با سرور.");
      submitBtn.disabled = false;
    }
  });
})();
