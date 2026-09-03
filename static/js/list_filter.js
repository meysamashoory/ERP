/**
 * Column-scoped search/filter for list tables.
 * Expects th[data-col] headers and td[data-col][data-value] cells.
 *
 * Numeric queries (only digits, incl. Persian) match the cell's numeric value
 * exactly — searching "35" will not match "135". Text queries stay substring.
 */
(function () {
  function toEnDigits(s) {
    return String(s || "").replace(/[۰-۹٠-٩]/g, function (ch) {
      var code = ch.charCodeAt(0);
      if (code >= 0x06f0 && code <= 0x06f9) return String(code - 0x06f0);
      if (code >= 0x0660 && code <= 0x0669) return String(code - 0x0660);
      return ch;
    });
  }

  function normalize(s) {
    return toEnDigits(s)
      .toLowerCase()
      .replace(/ي/g, "ی")
      .replace(/ك/g, "ک")
      .trim();
  }

  function isNumericQuery(q) {
    return /^[0-9]+$/.test(toEnDigits(q).trim());
  }

  function numericValue(s) {
    var digits = toEnDigits(s).replace(/[^\d]/g, "");
    if (!digits) return null;
    // Avoid treating leading zeros specially for equality of the digit string
    return String(parseInt(digits, 10));
  }

  function cellMatches(hay, q, exactNumber) {
    if (!q) return true;
    if (exactNumber) {
      var hv = numericValue(hay);
      var qv = numericValue(q);
      if (hv === null || qv === null) return false;
      return hv === qv;
    }
    return normalize(hay).indexOf(normalize(q)) !== -1;
  }

  window.initColumnFilter = function (opts) {
    var table = document.getElementById(opts.tableId);
    var colSelect = document.getElementById(opts.colSelectId);
    var queryInput = document.getElementById(opts.queryId);
    var clearBtn = document.getElementById(opts.clearId);
    var countEl = opts.countId ? document.getElementById(opts.countId) : null;
    if (!table || !colSelect || !queryInput) return;

    var headers = Array.from(table.querySelectorAll("thead th[data-col]"));
    colSelect.innerHTML = "";
    var allOpt = document.createElement("option");
    allOpt.value = "*";
    allOpt.textContent = "همه ستون‌ها";
    colSelect.appendChild(allOpt);
    headers.forEach(function (th) {
      var opt = document.createElement("option");
      opt.value = th.getAttribute("data-col") || "";
      opt.textContent = (th.textContent || "").trim();
      colSelect.appendChild(opt);
    });
    if (opts.defaultCol) {
      var has = Array.from(colSelect.options).some(function (o) {
        return o.value === opts.defaultCol;
      });
      if (has) colSelect.value = opts.defaultCol;
    }

    function apply() {
      var col = colSelect.value || "*";
      var rawQ = queryInput.value || "";
      var q = normalize(rawQ);
      var exactNumber = isNumericQuery(rawQ);
      var rows = table.querySelectorAll("tbody tr");
      var visible = 0;
      rows.forEach(function (tr) {
        if (!q) {
          tr.hidden = false;
          visible += 1;
          return;
        }
        var match = false;
        if (col === "*") {
          var cells = Array.from(tr.querySelectorAll("td[data-value], td[data-col]"));
          match = cells.some(function (td) {
            var hay = td.getAttribute("data-value") || td.textContent || "";
            return cellMatches(hay, rawQ, exactNumber);
          });
        } else {
          var td = tr.querySelector('td[data-col="' + col + '"]');
          var hay = td
            ? td.getAttribute("data-value") || td.textContent || ""
            : "";
          match = cellMatches(hay, rawQ, exactNumber);
        }
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
