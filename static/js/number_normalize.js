/**
 * Strip leading zeros from report/form number inputs (01 → 1).
 */
(function () {
  function toAsciiDigits(s) {
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var ch = s.charAt(i);
      var p = "۰۱۲۳۴۵۶۷۸۹".indexOf(ch);
      if (p >= 0) {
        out += String(p);
        continue;
      }
      var a = "٠١٢٣٤٥٦٧٨٩".indexOf(ch);
      if (a >= 0) {
        out += String(a);
        continue;
      }
      out += ch;
    }
    return out;
  }

  function normalize(value) {
    var raw = toAsciiDigits(String(value == null ? "" : value)).trim();
    if (!raw) return "";
    // Keep only digits for report/form numbers (01 → 1)
    var digits = raw.replace(/[^\d]/g, "");
    if (!digits) return "";
    var n = parseInt(digits, 10);
    if (!isFinite(n) || n < 1) return "";
    if (n > 999) n = 999;
    return String(n);
  }

  function bindInput(el) {
    if (!el || el.dataset.numNormBound === "1") return;
    el.dataset.numNormBound = "1";
    function apply() {
      var next = normalize(el.value);
      if (next !== String(el.value)) el.value = next;
    }
    el.addEventListener("input", apply);
    el.addEventListener("change", apply);
    el.addEventListener("blur", apply);
    apply();
  }

  function init(root) {
    var scope = root || document;
    scope.querySelectorAll(
      'input[name="number"][type="number"], input[name="number"].js-report-number, #id_number, #ui-form-number'
    ).forEach(bindInput);
  }

  window.ERPNormalizeNumbers = { init: init, normalize: normalize, bind: bindInput };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      init();
    });
  } else {
    init();
  }
})();
