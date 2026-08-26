/**
 * Editable product-data tabs (info / BOM / consumables).
 */
(function () {
  const root = document.getElementById("product-data-root");
  if (!root || root.dataset.canEdit !== "1") return;

  const tab = root.dataset.tab || "info";
  const saveUrl = root.dataset.saveUrl || "";
  const deleteUrl = root.dataset.deleteUrl || "";
  const csrf =
    (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
    (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
    "";

  const table = root.querySelector(".product-data-table");
  if (!table) return;
  const tbody = table.querySelector("tbody");

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

  function blankRowHtml() {
    if (tab === "info") {
      return (
        '<tr data-new="1">' +
        '<td><input class="input input-sm" data-field="code" value=""></td>' +
        '<td><input class="input input-sm" data-field="name" value=""></td>' +
        '<td><input class="input input-sm" data-field="group_name" value=""></td>' +
        '<td><input class="input input-sm" data-field="subgroup_name" value=""></td>' +
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
      const empty = tbody.querySelector(".empty-row");
      if (empty) empty.remove();
      tbody.insertAdjacentHTML("beforeend", blankRowHtml());
    });
  });

  tbody.addEventListener("click", function (e) {
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
