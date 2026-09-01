/**
 * Product-data tabs: view-first; enable edit via topbar «ویرایش».
 */
(function () {
  const root = document.getElementById("product-data-root");
  if (!root) return;

  const canEditPermission = root.dataset.canEditPermission === "1";
  const tab = root.dataset.tab || "info";
  const saveUrl = root.dataset.saveUrl || "";
  const deleteUrl = root.dataset.deleteUrl || "";
  const csrf =
    (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
    (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
    "";

  let groups = [];
  let subgroups = [];
  try {
    groups = JSON.parse(root.dataset.groups || "[]");
  } catch (e) {
    groups = [];
  }
  try {
    subgroups = JSON.parse(root.dataset.subgroups || "[]");
  } catch (e) {
    subgroups = [];
  }

  const table = root.querySelector(".product-data-table");
  const tbody = table ? table.querySelector("tbody") : null;
  const toggleBtn = document.getElementById("product-edit-toggle");
  const hint = document.getElementById("product-view-hint");
  const actions = root.querySelector(".product-data-actions");

  function parseGroupId(name) {
    const g = groups.find(function (x) {
      return x.name === name;
    });
    return g ? g.id : null;
  }

  function fillSubgroupSelect(select, groupName, current) {
    if (!select) return;
    const gid = parseGroupId(groupName);
    const opts = subgroups.filter(function (s) {
      return !gid || s.group_id === gid;
    });
    const cur = current || select.getAttribute("data-current") || select.value || "";
    select.innerHTML = '<option value="">—</option>';
    opts.forEach(function (s) {
      const opt = document.createElement("option");
      opt.value = s.name;
      opt.textContent = s.name;
      if (s.name === cur) opt.selected = true;
      select.appendChild(opt);
    });
    if (cur && !opts.some(function (s) { return s.name === cur; })) {
      const opt = document.createElement("option");
      opt.value = cur;
      opt.textContent = cur;
      opt.selected = true;
      select.appendChild(opt);
    }
  }

  function initGroupSubgroupRows() {
    if (!tbody) return;
    tbody.querySelectorAll("tr").forEach(function (tr) {
      const gSel = tr.querySelector("[data-group-select]");
      const sSel = tr.querySelector("[data-subgroup-select]");
      if (!gSel || !sSel) return;
      fillSubgroupSelect(sSel, gSel.value, sSel.getAttribute("data-current") || sSel.value);
      gSel.addEventListener("change", function () {
        fillSubgroupSelect(sSel, gSel.value, "");
      });
    });
  }

  function setEditable(on) {
    root.dataset.canEdit = on ? "1" : "0";
    if (hint) {
      hint.textContent = on
        ? "حالت ویرایش — پس از تغییر، «ذخیره تغییرات» را بزنید."
        : "حالت مشاهده — برای تغییر داده‌ها از «ویرایش» در بالای صفحه استفاده کنید.";
    }
    if (actions) actions.hidden = !on;
    if (toggleBtn) toggleBtn.textContent = on ? "پایان ویرایش" : "ویرایش";
    if (!tbody) return;
    tbody.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.type === "checkbox" || el.tagName === "SELECT") {
        el.disabled = !on;
      } else {
        if (on) el.removeAttribute("readonly");
        else el.setAttribute("readonly", "readonly");
      }
    });
    tbody.querySelectorAll("[data-delete-row]").forEach(function (btn) {
      btn.hidden = !on;
    });
  }

  initGroupSubgroupRows();
  setEditable(false);

  if (toggleBtn && canEditPermission) {
    toggleBtn.addEventListener("click", function () {
      const next = root.dataset.canEdit !== "1";
      setEditable(next);
    });
  }

  if (!tbody) return;

  function fieldValue(el) {
    if (!el) return "";
    if (el.type === "checkbox") return el.checked;
    return el.value;
  }

  function collectRows() {
    const rows = [];
    tbody.querySelectorAll("tr[data-id], tr[data-new]").forEach(function (tr) {
      if (tr.classList.contains("empty-row")) return;
      const row = {};
      const id = tr.getAttribute("data-id");
      if (id) row.id = parseInt(id, 10);
      tr.querySelectorAll("[data-field]").forEach(function (el) {
        row[el.dataset.field] = fieldValue(el);
      });
      rows.push(row);
    });
    return rows;
  }

  function groupOptionsHtml(selected) {
    let html = '<option value="">—</option>';
    groups.forEach(function (g) {
      html +=
        '<option value="' +
        g.name +
        '"' +
        (g.name === selected ? " selected" : "") +
        ">" +
        g.name +
        "</option>";
    });
    return html;
  }

  function blankRowHtml() {
    if (tab === "info") {
      return (
        '<tr data-new="1">' +
        '<td><input class="input input-sm" data-field="code" value=""></td>' +
        '<td><input class="input input-sm" data-field="name" value=""></td>' +
        '<td><select class="input input-sm" data-field="group_name" data-group-select>' +
        groupOptionsHtml("") +
        "</select></td>" +
        '<td><select class="input input-sm" data-field="subgroup_name" data-subgroup-select data-current="">' +
        '<option value="">—</option></select></td>' +
        '<td><select class="input input-sm" data-field="counting_unit">' +
        '<option value="count">عدد</option>' +
        '<option value="branch">شاخه</option>' +
        '<option value="coil">کلاف</option>' +
        '<option value="meter">متر</option>' +
        "</select></td>" +
        '<td><input class="input input-sm num" data-field="unit_weight_grams" value="0"></td>' +
        '<td><input class="input input-sm num" data-field="per_carton" value=""></td>' +
        '<td><input class="input input-sm num" data-field="stock_finished" value="0"></td>' +
        '<td class="num"><input type="checkbox" data-field="needs_assembly"></td>' +
        '<td class="col-ops"><button type="button" class="btn btn-sm btn-ghost" data-remove-new>حذف</button></td>' +
        "</tr>"
      );
    }
    if (tab === "bom") {
      return (
        '<tr data-new="1">' +
        '<td><input class="input input-sm" data-field="parent_code" value=""></td>' +
        '<td class="muted">—</td>' +
        '<td><input class="input input-sm" data-field="component_code" value=""></td>' +
        '<td><input class="input input-sm" data-field="component_name" value=""></td>' +
        '<td><input class="input input-sm num" data-field="quantity" value="1"></td>' +
        '<td><input class="input input-sm" data-field="unit" value="عدد"></td>' +
        '<td><input class="input input-sm" data-field="notes" value=""></td>' +
        '<td class="col-ops"><button type="button" class="btn btn-sm btn-ghost" data-remove-new>حذف</button></td>' +
        "</tr>"
      );
    }
    return (
      '<tr data-new="1">' +
      '<td><input class="input input-sm" data-field="product_code" value=""></td>' +
      '<td class="muted">—</td>' +
      '<td><input class="input input-sm" data-field="material_code" value=""></td>' +
      '<td><input class="input input-sm" data-field="material_name" value=""></td>' +
      '<td><input class="input input-sm num" data-field="quantity_per_unit" value="0"></td>' +
      '<td><input class="input input-sm" data-field="unit" value="گرم"></td>' +
      '<td><input class="input input-sm" data-field="notes" value=""></td>' +
      '<td class="col-ops"><button type="button" class="btn btn-sm btn-ghost" data-remove-new>حذف</button></td>' +
      "</tr>"
    );
  }

  root.querySelectorAll("[data-add-row]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (root.dataset.canEdit !== "1") return;
      const empty = tbody.querySelector(".empty-row");
      if (empty) empty.remove();
      tbody.insertAdjacentHTML("beforeend", blankRowHtml());
      const tr = tbody.lastElementChild;
      const gSel = tr.querySelector("[data-group-select]");
      const sSel = tr.querySelector("[data-subgroup-select]");
      if (gSel && sSel) {
        fillSubgroupSelect(sSel, gSel.value, "");
        gSel.addEventListener("change", function () {
          fillSubgroupSelect(sSel, gSel.value, "");
        });
      }
    });
  });

  tbody.addEventListener("click", function (e) {
    if (root.dataset.canEdit !== "1") return;
    const removeNew = e.target.closest("[data-remove-new]");
    if (removeNew) {
      const tr = removeNew.closest("tr");
      if (tr) tr.remove();
      return;
    }
    const del = e.target.closest("[data-delete-row]");
    if (!del) return;
    const tr = del.closest("tr");
    if (!tr || !tr.dataset.id) return;
    if (!confirm("این ردیف حذف شود؟")) return;
    fetch(deleteUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      body: JSON.stringify({ tab: tab, id: parseInt(tr.dataset.id, 10) }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "حذف ناموفق بود.");
          return;
        }
        tr.remove();
      })
      .catch(function () {
        alert("خطا در ارتباط با سرور.");
      });
  });

  root.querySelectorAll("[data-save-tab]").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      if (root.dataset.canEdit !== "1") return;
      const rows = collectRows();
      if (!rows.length) {
        alert("ردیفی برای ذخیره نیست.");
        return;
      }
      btn.disabled = true;
      try {
        const resp = await fetch(saveUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
          },
          body: JSON.stringify({ tab: tab, rows: rows }),
        });
        const data = await resp.json();
        if (!data.ok) {
          alert(data.error || "ذخیره ناموفق بود.");
          btn.disabled = false;
          return;
        }
        alert(data.message || "ذخیره شد.");
        window.location.reload();
      } catch (err) {
        alert("خطا در ارتباط با سرور.");
        btn.disabled = false;
      }
    });
  });
})();
