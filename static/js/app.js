/* UI wiring: Jalali date picker, searchable comboboxes, dependent dropdowns. */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    // --- Jalali date picker (attaches to inputs with data-jdp) ----------
    if (window.jalaliDatepicker) {
      window.jalaliDatepicker.startWatch({
        time: false,
        persianDigit: false,
        separatorChars: { date: "/" },
        autoHide: true,
        hideAfterChange: true,
      });
    }

    // --- Searchable/typeable comboboxes --------------------------------
    if (window.TomSelect) {
      document.querySelectorAll("select[data-combo]").forEach(function (sel) {
        if (sel.tomselect) return;
        new TomSelect(sel, {
          create: false,
          allowEmptyOption: true,
          maxOptions: 2000,
          placeholder: sel.getAttribute("placeholder") || "انتخاب یا جستجو...",
          render: {
            no_results: function () {
              return '<div class="no-results">موردی یافت نشد</div>';
            },
          },
        });
      });
    }

    function tsOf(el) { return el ? el.tomselect : null; }
    function valOf(el) {
      var ts = tsOf(el);
      return ts ? ts.getValue() : (el ? el.value : "");
    }

    function repopulate(sel, items, opts) {
      // items: [{value, text}]; preserves current value when possible.
      var ts = tsOf(sel);
      if (!ts) return;
      var prev = ts.getValue();
      ts.clearOptions();
      items.forEach(function (it) { ts.addOption({ value: String(it.value), text: it.text }); });
      ts.refreshOptions(false);
      var keep = opts && opts.preserve && prev &&
        items.some(function (it) { return String(it.value) === String(prev); });
      if (keep) ts.setValue(prev, true);
      else ts.clear(true);
    }

    // --- Dependent: unit -> machine ------------------------------------
    document.querySelectorAll("[data-role=unit]").forEach(function (unitSel) {
      var form = unitSel.closest("form");
      if (!form) return;
      var machineSel = form.querySelector("[data-role=machine]");
      if (!machineSel) return;
      var mtype = machineSel.getAttribute("data-machine-type") || "injection";

      function refresh(preserve) {
        var unit = valOf(unitSel);
        if (!unit) { repopulate(machineSel, [], {}); return; }
        fetch(window.API.machines + "?unit=" + encodeURIComponent(unit) + "&type=" + mtype)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var items = (d.results || []).map(function (m) { return { value: m.id, text: m.label }; });
            repopulate(machineSel, items, { preserve: preserve });
          });
      }
      var ts = tsOf(unitSel);
      if (ts) ts.on("change", function () { refresh(false); });
      else unitSel.addEventListener("change", function () { refresh(false); });
      if (valOf(unitSel)) refresh(true);
    });

    // --- Dependent: subgroup -> product <-> code -----------------------
    document.querySelectorAll("[data-role=subgroup]").forEach(function (sgSel) {
      var form = sgSel.closest("form");
      if (!form) return;
      var prodSel = form.querySelector("[data-role=product]");
      var codeSel = form.querySelector("[data-role=code]");
      if (!prodSel) return;

      function refresh(preserve) {
        var sg = valOf(sgSel);
        if (!sg) { repopulate(prodSel, [], {}); if (codeSel) repopulate(codeSel, [], {}); return; }
        fetch(window.API.products + "?subgroup=" + encodeURIComponent(sg))
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var res = d.results || [];
            repopulate(prodSel, res.map(function (p) { return { value: p.id, text: p.name }; }), { preserve: preserve });
            if (codeSel) repopulate(codeSel, res.map(function (p) { return { value: p.id, text: p.code }; }), { preserve: preserve });
          });
      }
      var sgts = tsOf(sgSel);
      if (sgts) sgts.on("change", function () { refresh(false); });
      else sgSel.addEventListener("change", function () { refresh(false); });

      // Two-way sync between product name and code (same underlying id).
      if (codeSel) {
        var pts = tsOf(prodSel), cts = tsOf(codeSel);
        if (pts) pts.on("change", function (v) { if (cts && cts.getValue() !== v) cts.setValue(v, true); });
        if (cts) cts.on("change", function (v) { if (pts && pts.getValue() !== v) pts.setValue(v, true); });
      }
      if (valOf(sgSel)) refresh(true);
    });

    // --- Pipe: enable only fields relevant to the chosen subgroup ------
    var pipeMapEl = document.getElementById("pipe-field-map");
    if (pipeMapEl) {
      var PIPE_FIELDS = {};
      try { PIPE_FIELDS = JSON.parse(pipeMapEl.textContent || "{}"); } catch (e) { PIPE_FIELDS = {}; }
      var conditional = [
        "socket_length", "bling_machine", "nominal_pressure", "thickness",
        "thickness_unit", "material_grade", "dripper_spec", "nominal_flow",
        "dripper_spacing", "color", "length_meters",
      ];
      var form = pipeMapEl.closest("form") || document;
      var sgSel = form.querySelector("[data-role=subgroup]");

      function toggleFields() {
        var sg = valOf(sgSel);
        var allowed = PIPE_FIELDS[sg] || [];
        conditional.forEach(function (name) {
          var wrap = form.querySelector('[data-field="' + name + '"]');
          if (!wrap) return;
          var show = allowed.indexOf(name) !== -1;
          wrap.style.display = show ? "" : "none";
          wrap.querySelectorAll("input, select, textarea").forEach(function (inp) {
            inp.disabled = !show;
          });
        });
      }
      var sgts = tsOf(sgSel);
      if (sgts) sgts.on("change", toggleFields);
      else if (sgSel) sgSel.addEventListener("change", toggleFields);
      toggleFields();
    }

    // --- Add-row for repeatable formsets (data-formset-add) ------------
    document.querySelectorAll("[data-formset-add]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var prefix = btn.getAttribute("data-formset-add");
        var container = document.querySelector('[data-formset="' + prefix + '"]');
        var totalEl = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
        if (!container || !totalEl) return;
        var tmpl = container.querySelector("[data-formset-row]");
        if (!tmpl) return;
        var idx = parseInt(totalEl.value, 10);
        var clone = tmpl.cloneNode(true);
        clone.innerHTML = clone.innerHTML.replace(
          new RegExp(prefix + "-(\\d+)-", "g"), prefix + "-" + idx + "-"
        );
        // Reset values on the clone and strip any TomSelect wrappers.
        clone.querySelectorAll(".ts-wrapper").forEach(function (w) { w.remove(); });
        clone.querySelectorAll("input, select, textarea").forEach(function (inp) {
          inp.style.display = "";
          if (inp.type !== "hidden") inp.value = "";
          inp.removeAttribute("data-combo");
        });
        container.appendChild(clone);
        totalEl.value = idx + 1;
      });
    });
  });
})();
