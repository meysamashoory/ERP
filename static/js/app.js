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
    // Only position while open. Never force display while closed — that left a
    // half-open «انتخاب...» panel; also never block open() by hiding mid-open.
    if (!ts.isOpen) return;
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
    dropdown.style.visibility = "visible";
    if (openUp) {
      dropdown.style.top = "auto";
      dropdown.style.bottom = Math.round(window.innerHeight - rect.top + gap) + "px";
    } else {
      dropdown.style.top = Math.round(rect.bottom + gap) + "px";
      dropdown.style.bottom = "auto";
    }
  }

  function clearFieldError(el) {
    var field = el && el.closest ? el.closest(".field") : null;
    if (!field || !field.classList.contains("has-error")) return;
    field.classList.remove("has-error");
    field.removeAttribute("title");
  }

  function wireClearErrors(root) {
    root.querySelectorAll(".field.has-error").forEach(function (field) {
      if (field.dataset.errorClearWired) return;
      field.dataset.errorClearWired = "1";
      field.addEventListener("input", function (e) { clearFieldError(e.target); }, true);
      field.addEventListener("change", function (e) { clearFieldError(e.target); }, true);
      field.querySelectorAll("select").forEach(function (sel) {
        var ts = tsOf(sel);
        if (ts) ts.on("change", function () { clearFieldError(sel); });
      });
    });
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
        openOnFocus: false,
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
        onDropdownClose: function () {
          if (this.dropdown) {
            this.dropdown.style.display = "none";
            this.dropdown.style.visibility = "hidden";
          }
        },
      });
      // openOnFocus:false avoids auto-open on load/tab; click must open explicitly.
      ts.control.addEventListener("mousedown", function (e) {
        if (ts.isLocked || ts.isDisabled) return;
        if (ts.isOpen) return;
        e.preventDefault();
        ts.focus();
        ts.open();
      });
      // Override library positioning so menus never jump to the page bottom.
      ts.positionDropdown = function () { pinDropdown(ts); };
      // Start closed without leaving a visible empty menu.
      if (ts.isOpen) ts.close();
      if (ts.dropdown) {
        ts.dropdown.style.display = "none";
        ts.dropdown.style.visibility = "hidden";
      }
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
    // Clear first when not preserving, so a machine from another unit never
    // remains selected (and must not mutate native <select> via innerHTML —
    // that breaks Tom Select click/open).
    if (!(opts && opts.preserve)) ts.clear(true);
    ts.clearOptions();
    items.forEach(function (it) {
      ts.addOption({
        value: String(it.value),
        text: it.text,
        subgroup_id: it.subgroup_id,
        code: it.code,
      });
    });
    // Do not call refreshOptions(true) — that opens the dropdown on load.
    var keep = opts && opts.preserve && prev &&
      items.some(function (it) { return String(it.value) === String(prev); });
    if (keep) ts.setValue(String(prev), true);
    else if (opts && opts.preserve) { /* keep empty */ }
    if (ts.isOpen) ts.close();
  }

  function wireUnitMachine(root) {
    root.querySelectorAll("[data-role=unit]").forEach(function (unitSel) {
      var form = unitSel.closest("form"); if (!form) return;
      var machineSel = form.querySelector("[data-role=machine]"); if (!machineSel) return;
      if (unitSel.dataset.wired) return; unitSel.dataset.wired = "1";
      var mtype = machineSel.getAttribute("data-machine-type") || "injection";
      function refresh(preserve) {
        var unit = valOf(unitSel);
        var mts = tsOf(machineSel);
        if (!preserve && mts) {
          mts.clear(true);
          if (mts.isOpen) mts.close();
        }
        if (!unit) { repopulate(machineSel, [], {}); return; }
        fetch(window.API.machines + "?unit=" + encodeURIComponent(unit) + "&type=" + mtype)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            repopulate(machineSel, (d.results || []).map(function (m) {
              return { value: m.id, text: m.label };
            }), { preserve: preserve });
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
      var silencing = false;
      var kind = form.getAttribute("data-product-kind") || "fitting";

      function mapProducts(res) {
        return (res || []).map(function (p) {
          return { value: p.id, text: p.name, subgroup_id: p.subgroup_id, code: p.code };
        });
      }
      function mapCodes(res) {
        return (res || []).map(function (p) {
          return { value: p.id, text: p.code, subgroup_id: p.subgroup_id };
        });
      }
      function refresh(preserve) {
        var sg = valOf(sgSel);
        var url = window.API.products + "?kind=" + encodeURIComponent(kind);
        if (sg) url += "&subgroup=" + encodeURIComponent(sg);
        fetch(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var res = d.results || [];
            var pts = tsOf(prodSel);
            var prev = pts ? pts.getValue() : prodSel.value;
            if (pts) {
              // Avoid clear()+refreshOptions — that opens the product menu on page load.
              var keep = preserve && prev && res.some(function (p) { return String(p.id) === String(prev); });
              if (!keep) pts.clear(true);
              pts.clearOptions();
              res.forEach(function (p) {
                pts.addOption({
                  value: String(p.id), text: p.name,
                  subgroup_id: p.subgroup_id, code: p.code
                });
              });
              if (keep) {
                pts.setValue(String(prev), true);
                // Silent setValue does not fire change — sync code manually.
                if (codeSel) {
                  var ctsSync = tsOf(codeSel);
                  if (ctsSync && ctsSync.getValue() !== String(prev)) {
                    ctsSync.setValue(String(prev), true);
                  }
                }
              }
              if (pts.isOpen) pts.close();
            } else {
              repopulate(prodSel, mapProducts(res), { preserve: preserve });
            }
            if (codeSel) {
              var cts = tsOf(codeSel);
              if (cts) {
                var cprev = cts.getValue();
                var ckeep = preserve && cprev && res.some(function (p) { return String(p.id) === String(cprev); });
                if (!ckeep) cts.clear(true);
                cts.clearOptions();
                res.forEach(function (p) {
                  cts.addOption({
                    value: String(p.id), text: p.code,
                    subgroup_id: p.subgroup_id
                  });
                });
                if (ckeep) cts.setValue(String(cprev), true);
                if (cts.isOpen) cts.close();
              } else {
                repopulate(codeSel, mapCodes(res), { preserve: preserve });
              }
            }
            // Ensure no combo is left open after async option load.
            [prodSel, codeSel, sgSel].forEach(function (el) {
              var t = tsOf(el);
              if (t && t.isOpen) t.close();
            });
          });
      }

      function syncSubgroupFromProduct(productId) {
        var pts = tsOf(prodSel);
        if (!pts || !productId) return;
        var opt = pts.options[productId];
        if (!opt || !opt.subgroup_id) return;
        var sgts = tsOf(sgSel);
        var next = String(opt.subgroup_id);
        if (sgts) {
          if (String(sgts.getValue()) === next) return;
          silencing = true;
          sgts.setValue(next, true);
          silencing = false;
        } else if (String(sgSel.value) !== next) {
          silencing = true;
          sgSel.value = next;
          silencing = false;
        }
      }

      var sgts = tsOf(sgSel);
      if (sgts) sgts.on("change", function () { if (!silencing) refresh(false); });
      else sgSel.addEventListener("change", function () { if (!silencing) refresh(false); });

      if (codeSel) {
        var pts = tsOf(prodSel), cts = tsOf(codeSel);
        if (pts) pts.on("change", function (v) {
          if (cts && cts.getValue() !== v) cts.setValue(v, true);
          syncSubgroupFromProduct(v);
        });
        if (cts) cts.on("change", function (v) {
          if (pts && pts.getValue() !== v) pts.setValue(v, true);
          syncSubgroupFromProduct(v);
        });
      } else {
        var ptsOnly = tsOf(prodSel);
        if (ptsOnly) ptsOnly.on("change", function (v) { syncSubgroupFromProduct(v); });
      }

      // Always load product list (all fitting products when subgroup empty).
      refresh(true);
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
    wireClearErrors(root);
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

        if (btn.getAttribute("data-require-first-type") === "1") {
          var firstRow = container.querySelector("[data-formset-row]");
          var typeSel = firstRow && firstRow.querySelector('select[name$="-production_type"]');
          var typeVal = valOf(typeSel);
          if (!typeVal) {
            window.alert("برای افزودن ردیف بعدی، ابتدا «نوع تولید» ردیف اول را انتخاب کنید.");
            return;
          }
        }

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
        if (btn.getAttribute("data-number-line-labels") === "1" &&
            window.ERP_PLAN && window.ERP_PLAN.renumberLines) {
          window.ERP_PLAN.renumberLines();
        }
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
