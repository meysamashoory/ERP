/**
 * Column-scoped search/filter for list tables.
 * Expects th[data-col] headers and td[data-col][data-value] cells.
 */
(function () {
  function normalize(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/ي/g, "ی")
      .replace(/ك/g, "ک")
      .trim();
  }

  window.initColumnFilter = function (opts) {
    const table = document.getElementById(opts.tableId);
    const colSelect = document.getElementById(opts.colSelectId);
    const queryInput = document.getElementById(opts.queryId);
    const clearBtn = document.getElementById(opts.clearId);
    const countEl = opts.countId ? document.getElementById(opts.countId) : null;
    if (!table || !colSelect || !queryInput) return;

    const headers = Array.from(table.querySelectorAll("thead th[data-col]"));
    colSelect.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "*";
    allOpt.textContent = "همه ستون‌ها";
    colSelect.appendChild(allOpt);
    headers.forEach(function (th) {
      const opt = document.createElement("option");
      opt.value = th.getAttribute("data-col") || "";
      opt.textContent = (th.textContent || "").trim();
      colSelect.appendChild(opt);
    });
    if (opts.defaultCol) {
      const has = Array.from(colSelect.options).some(function (o) {
        return o.value === opts.defaultCol;
      });
      if (has) colSelect.value = opts.defaultCol;
    }

    function apply() {
      const col = colSelect.value || "*";
      const q = normalize(queryInput.value);
      const rows = table.querySelectorAll("tbody tr");
      let visible = 0;
      rows.forEach(function (tr) {
        if (!q) {
          tr.hidden = false;
          visible += 1;
          return;
        }
        let hay = "";
        if (col === "*") {
          hay = Array.from(tr.querySelectorAll("td[data-value], td[data-col]"))
            .map(function (td) {
              return td.getAttribute("data-value") || td.textContent || "";
            })
            .join(" ");
        } else {
          const td = tr.querySelector('td[data-col="' + col + '"]');
          hay = td
            ? td.getAttribute("data-value") || td.textContent || ""
            : "";
        }
        const match = normalize(hay).indexOf(q) !== -1;
        tr.hidden = !match;
        if (match) visible += 1;
      });
      if (countEl) {
        countEl.textContent = q
          ? visible + " از " + rows.length + " ردیف"
          : rows.length + " ردیف";
      }
    }

    colSelect.addEventListener("change", apply);
    queryInput.addEventListener("input", apply);
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        queryInput.value = "";
        apply();
        queryInput.focus();
      });
    }
    apply();
  };
})();
