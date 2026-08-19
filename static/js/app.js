/* UI wiring: comboboxes, Jalali date picker, dependent dropdowns, tabs,
   in-page status dialog, and auto-dismissing (transient) alerts. */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function tsOf(el) { return el ? el.tomselect : null; }
  function valOf(el) { var ts = tsOf(el); return ts ? ts.getValue() : (el ? el.value : ""); }

  function dropdownLayerHost(el) {
    // <dialog> is in the top layer; menus appended to body stay behind it.
    return (el && el.closest("dialog")) || document.body;
  }

  function pinDropdown(ts) {
    if (!ts || !ts.dropdown || !ts.control) return;
    var control = ts.control;
    var dropdown = ts.dropdown;
    var host = dropdownLayerHost(control);
    if (dropdown.parentElement !== host) host.appendChild(dropdown);

    var rect = control.getBoundingClientRect();
    var gap = 4;
    var maxH = Math.min(280, Math.max(120, window.innerHeight - rect.bottom - 16));
    // If not enough space below, open upward.
    var openUp = rect.bottom + Math.min(maxH, 180) > window.innerHeight - 8 && rect.top > 160;
    dropdown.style.position = "fixed";
    dropdown.style.left = Math.round(rect.left) + "px";
    dropdown.style.width = Math.round(rect.width) + "px";
    dropdown.style.right = "auto";
    dropdown.style.zIndex = "100002";
    dropdown.style.maxHeight = maxH + "px";
    dropdown.style.overflowY = "auto";
    dropdown.style.display = "block";
    if (openUp) {
      dropdown.style.top = "auto";
      dropdown.style.bottom = Math.round(window.innerHeight - rect.top + gap) + "px";
    } else {
      dropdown.style.top = Math.round(rect.bottom + gap) + "px";
      dropdown.style.bottom = "auto";
    }
  }

  function initCombos(root) {
    if (!window.TomSelect) return;
    root.querySelectorAll("select[data-combo]").forEach(function (sel) {
      if (sel.tomselect) return;
      // Prevent double border: Tom Select copies select.className onto .ts-wrapper.
      sel.classList.remove("input");
      // Search lives inside the open menu (dropdown_input) so:
      // - selected label stays visible in the control
      // - control size never changes on focus
      // - typing still filters options
      var ts = new TomSelect(sel, {
        plugins: ["dropdown_input"],
        create: false,
        allowEmptyOption: true,
        maxOptions: 2000,
        controlInput: null,
        placeholder: sel.getAttribute("placeholder") || "انتخاب...",
        render: { no_results: function () { return '<div class="no-results">موردی یافت نشد</div>'; } },
        onDropdownOpen: function () {
          var self = this;
          pinDropdown(self);
          requestAnimationFrame(function () { pinDropdown(self); });
          setTimeout(function () { pinDropdown(self); }, 20);
          // Focus the in-dropdown search box for typing.
          var inp = self.dropdown && self.dropdown.querySelector("input");
          if (inp) setTimeout(function () { inp.focus(); }, 0);
        },
      });
      // Override library positioning so menus never jump to the page bottom.
      ts.positionDropdown = function () { pinDropdown(ts); };
      var repin = function () { if (ts.isOpen) pinDropdown(ts); };
      window.addEventListener("scroll", repin, true);
      window.addEventListener("resize", repin);
    });
  }

  function jdpEls() {
    return {
      container: document.querySelector("jdp-container") || document.querySelector(".jdp-container"),
      overlay: document.querySelector("jdp-overlay") || document.querySelector(".jdp-overlay"),
    };
  }

  function placeDatepicker(input) {
    var els = jdpEls();
    var container = els.container;
    if (!input || !container) return;
    var host = dropdownLayerHost(input);
    if (container.parentElement !== host) host.appendChild(container);
    if (els.overlay && els.overlay.parentElement !== host) host.appendChild(els.overlay);

    var rect = input.getBoundingClientRect();
    var width = container.offsetWidth || 308;
    var left = rect.left;
    if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
    if (left < 8) left = 8;
    var top = rect.bottom + 4;
    var height = container.offsetHeight || 280;
    if (top + height > window.innerHeight - 8 && rect.top > height + 8) {
      top = rect.top - height - 4;
    }
    container.style.position = "fixed";
    container.style.top = Math.round(top) + "px";
    container.style.left = Math.round(left) + "px";
    container.style.right = "auto";
    container.style.bottom = "auto";
    container.style.zIndex = "100000";
  }

  function initDatepicker() {
    if (!window.jalaliDatepicker) return;
    if (!window.__jdpStarted) {
      window.jalaliDatepicker.startWatch({
        time: false,
        persianDigit: false,
        separatorChars: { date: "/" },
        autoHide: true,
        hideAfterChange: true,
        zIndex: 100000,
        container: "body",
      });
      window.__jdpStarted = true;
    }
  }

  function wireDatepickerHost(root) {
    root.querySelectorAll("input[data-jdp]").forEach(function (inp) {
      if (inp.dataset.jdpHostWired) return;
      inp.dataset.jdpHostWired = "1";
      function fix() {
        placeDatepicker(inp);
        requestAnimationFrame(function () {
          placeDatepicker(inp);
          setTimeout(function () { placeDatepicker(inp); }, 30);
        });
      }
      inp.addEventListener("focus", fix);
      inp.addEventListener("click", fix);
    });

    if (!window.__jdpPlaceObserver && typeof MutationObserver !== "undefined") {
      window.__jdpPlaceObserver = new MutationObserver(function () {
        var active = document.activeElement;
        if (active && active.matches && active.matches("input[data-jdp]")) {
          placeDatepicker(active);
        }
      });
      var watch = function () {
        var els = jdpEls();
        if (els.container) {
          window.__jdpPlaceObserver.observe(els.container, {
            attributes: true, attributeFilter: ["style", "class"],
          });
        } else {
          setTimeout(watch, 200);
        }
      };
      watch();
    }
  }

  function repopulate(sel, items, opts) {
    var ts = tsOf(sel); if (!ts) return;
    var prev = ts.getValue();
    ts.clearOptions();
    items.forEach(function (it) { ts.addOption({ value: String(it.value), text: it.text }); });
    ts.refreshOptions(false);
    var keep = opts && opts.preserve && prev &&
      items.some(function (it) { return String(it.value) === String(prev); });
    if (keep) ts.setValue(prev, true); else ts.clear(true);
  }

  function wireUnitMachine(root) {
    root.querySelectorAll("[data-role=unit]").forEach(function (unitSel) {
      var form = unitSel.closest("form"); if (!form) return;
      var machineSel = form.querySelector("[data-role=machine]"); if (!machineSel) return;
      if (unitSel.dataset.wired) return; unitSel.dataset.wired = "1";
      var mtype = machineSel.getAttribute("data-machine-type") || "injection";
      function refresh(preserve) {
        var unit = valOf(unitSel);
        if (!unit) { repopulate(machineSel, [], {}); return; }
        fetch(window.API.machines + "?unit=" + encodeURIComponent(unit) + "&type=" + mtype)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            repopulate(machineSel, (d.results || []).map(function (m) { return { value: m.id, text: m.label }; }), { preserve: preserve });
          });
      }
      var ts = tsOf(unitSel);
      if (ts) ts.on("change", function () { refresh(false); });
      else unitSel.addEventListener("change", function () { refresh(false); });
      if (valOf(unitSel)) refresh(true);
    });
  }

  function wireSubgroupProduct(root) {
    root.querySelectorAll("[data-role=subgroup]").forEach(function (sgSel) {
      var form = sgSel.closest("form"); if (!form) return;
      var prodSel = form.querySelector("[data-role=product]");
      var codeSel = form.querySelector("[data-role=code]");
      if (!prodSel || sgSel.dataset.wired) return; sgSel.dataset.wired = "1";
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
      if (codeSel) {
        var pts = tsOf(prodSel), cts = tsOf(codeSel);
        if (pts) pts.on("change", function (v) { if (cts && cts.getValue() !== v) cts.setValue(v, true); });
        if (cts) cts.on("change", function (v) { if (pts && pts.getValue() !== v) pts.setValue(v, true); });
      }
      if (valOf(sgSel)) refresh(true);
    });
  }

  function wireChangeType(root) {
    var ct = root.querySelector('[data-role="change-type"]');
    if (!ct || ct.dataset.wired) return; ct.dataset.wired = "1";
    var wrap = root.querySelector('[data-field="change_reason"]');
    function sync() {
      var v = valOf(ct);
      if (wrap) wrap.style.display = (v === "change") ? "" : "none";
    }
    var ts = tsOf(ct);
    if (ts) ts.on("change", sync); else ct.addEventListener("change", sync);
    sync();
  }

  function enhance(root) {
    root = root || document;
    initCombos(root);
    initDatepicker();
    wireDatepickerHost(root);
    wireUnitMachine(root);
    wireSubgroupProduct(root);
    wireChangeType(root);
  }

  window.ERP = { enhance: enhance };
  window.enhance = enhance;

  ready(function () {
    enhance(document);

    // --- Logout confirmation ------------------------------------------
    var logoutForm = document.getElementById("logout-form");
    if (logoutForm) {
      logoutForm.addEventListener("submit", function (e) {
        if (!window.confirm("آیا برای خروج از سامانه اطمینان دارید؟")) {
          e.preventDefault();
        }
      });
    }

    // --- Floating toasts (no layout shift) ------------------------------
    document.querySelectorAll(".toast-stack .toast").forEach(function (el) {
      var hold = el.classList.contains("toast-error") || el.classList.contains("toast-danger") ? 7000 : 4200;
      setTimeout(function () {
        el.classList.add("is-leaving");
        setTimeout(function () {
          el.remove();
          var stack = document.getElementById("toast-stack");
          if (stack && !stack.querySelector(".toast")) stack.remove();
        }, 380);
      }, hold);
    });
    // Legacy inline alerts (if any remain outside toast-stack)
    document.querySelectorAll(".messages .alert").forEach(function (el) {
      setTimeout(function () {
        el.style.transition = "opacity .4s"; el.style.opacity = "0";
        setTimeout(function () { el.remove(); }, 400);
      }, 5000);
    });

    // --- Tabs (folder-option style) ------------------------------------
    document.querySelectorAll("[data-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var group = btn.closest("[data-tabs]");
        var name = btn.getAttribute("data-tab");
        group.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("active", b === btn); });
        group.querySelectorAll("[data-tab-panel]").forEach(function (p) {
          p.style.display = (p.getAttribute("data-tab-panel") === name) ? "" : "none";
        });
      });
    });

    // --- In-page status dialog -----------------------------------------
    var dialog = document.getElementById("status-dialog");
    if (dialog) {
      var body = dialog.querySelector("[data-dialog-body]");
      document.body.addEventListener("click", function (e) {
        var trigger = e.target.closest("[data-status-url]");
        if (!trigger) return;
        e.preventDefault();
        body.innerHTML = '<p class="muted">در حال بارگذاری...</p>';
        if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
        fetch(trigger.getAttribute("data-status-url"))
          .then(function (r) { return r.text(); })
          .then(function (html) { body.innerHTML = html; enhance(body); });
      });
      dialog.addEventListener("click", function (e) {
        if (e.target.closest("[data-dialog-close]")) {
          e.preventDefault();
          if (typeof dialog.close === "function") dialog.close(); else dialog.removeAttribute("open");
        }
      });
    }

    // --- Add-row for repeatable formsets -------------------------------
    document.querySelectorAll("[data-formset-add]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var prefix = btn.getAttribute("data-formset-add");
        var container = document.querySelector('[data-formset="' + prefix + '"]');
        var totalEl = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
        if (!container || !totalEl) return;
        var idx = parseInt(totalEl.value, 10);
        var clone;
        var emptyTpl = document.querySelector('[data-formset-empty="' + prefix + '"]');
        if (emptyTpl && emptyTpl.content) {
          // Prefer pristine Django empty_form — selects still have all options.
          clone = emptyTpl.content.firstElementChild.cloneNode(true);
          clone.innerHTML = clone.innerHTML.replace(/__prefix__/g, String(idx));
        } else {
          var tmpl = container.querySelector("[data-formset-row]");
          if (!tmpl) return;
          clone = tmpl.cloneNode(true);
          // Recover <select> from Tom Select wrappers before wiping the clone.
          clone.querySelectorAll(".ts-wrapper").forEach(function (w) {
            var sel = w.querySelector("select");
            if (sel) {
              sel.classList.remove("tomselected", "ts-hidden-accessible");
              sel.removeAttribute("tabindex");
              sel.style.display = "";
              sel.removeAttribute("id");
              if (!sel.getAttribute("data-combo")) sel.setAttribute("data-combo", "1");
              w.parentNode.insertBefore(sel, w);
            }
            w.remove();
          });
          clone.querySelectorAll(".ts-dropdown").forEach(function (d) { d.remove(); });
          clone.innerHTML = clone.innerHTML.replace(
            new RegExp(prefix + "-(\\d+)-", "g"),
            prefix + "-" + idx + "-"
          );
        }
        clone.querySelectorAll("input, select, textarea").forEach(function (inp) {
          if (inp.type === "hidden" && /TOTAL_FORMS|INITIAL_FORMS|MIN_NUM|MAX_NUM/.test(inp.name || "")) return;
          if (inp.type !== "hidden") inp.value = "";
          inp.removeAttribute("data-wired");
        });
        container.appendChild(clone);
        totalEl.value = idx + 1;
        enhance(clone);
      });
    });

    // --- Pipe: enable only fields relevant to the chosen subgroup ------
    var pipeMapEl = document.getElementById("pipe-field-map");
    if (pipeMapEl) {
      var PIPE_FIELDS = {};
      try { PIPE_FIELDS = JSON.parse(pipeMapEl.textContent || "{}"); } catch (e) {}
      var conditional = ["socket_length", "bling_machine", "nominal_pressure", "thickness",
        "thickness_unit", "material_grade", "dripper_spec", "nominal_flow", "dripper_spacing", "color", "length_meters"];
      var form = pipeMapEl.closest("form") || document;
      var sgSel = form.querySelector("[data-role=subgroup]");
      function toggleFields() {
        var allowed = PIPE_FIELDS[valOf(sgSel)] || [];
        conditional.forEach(function (name) {
          var wrap = form.querySelector('[data-field="' + name + '"]');
          if (!wrap) return;
          var show = allowed.indexOf(name) !== -1;
          wrap.style.display = show ? "" : "none";
          wrap.querySelectorAll("input, select, textarea").forEach(function (inp) { inp.disabled = !show; });
        });
      }
      var sgts = tsOf(sgSel);
      if (sgts) sgts.on("change", toggleFields); else if (sgSel) sgSel.addEventListener("change", toggleFields);
      toggleFields();
    }
  });
})();
