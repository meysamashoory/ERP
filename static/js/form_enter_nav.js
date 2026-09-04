/* Enter in text fields → next field; on last field → save/submit.
 * Usage: ERPFormEnterNav.bind(root, { saveSelector: "#btn" })
 *        ERPFormEnterNav.bind(root)  // uses form submit / [type=submit] / [data-enter-save]
 */
(function (global) {
  "use strict";

  var FIELD_SEL =
    'input:not([type="hidden"]):not([type="button"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([disabled]),' +
    "select:not([disabled]), textarea:not([disabled])";

  function isVisible(el) {
    if (!el || el.disabled) return false;
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return false;
    var st = global.getComputedStyle ? getComputedStyle(el) : null;
    if (st) {
      if (st.display === "none" || st.visibility === "hidden") return false;
      if (parseFloat(st.opacity || "1") === 0) return false;
    }
    // Do not use offsetParent — it is null for many visible nodes inside <dialog>.
    if (typeof el.getClientRects === "function" && el.getClientRects().length === 0) {
      // Still allow zero-size when parent dialog is open but not yet laid out
      var dlg = el.closest && el.closest("dialog");
      if (dlg && dlg.open) return true;
      return false;
    }
    return true;
  }

  function collectFields(root) {
    return Array.prototype.slice.call(root.querySelectorAll(FIELD_SEL)).filter(isVisible);
  }

  function findSave(root, opts) {
    opts = opts || {};
    if (opts.saveSelector) {
      var el = root.querySelector(opts.saveSelector);
      if (el) return el;
    }
    var byData = root.querySelector("[data-enter-save]");
    if (byData) return byData;
    var submitBtn = root.querySelector('button[type="submit"], input[type="submit"]');
    if (submitBtn) return submitBtn;
    var form = root.tagName === "FORM" ? root : root.querySelector("form") || root.closest("form");
    if (form) return form;
    return null;
  }

  function triggerSave(saveEl) {
    if (!saveEl) return;
    if (saveEl.tagName === "FORM") {
      if (typeof saveEl.requestSubmit === "function") saveEl.requestSubmit();
      else saveEl.submit();
      return;
    }
    saveEl.click();
  }

  function bind(root, opts) {
    if (!root || root._erpEnterNavBound) return;
    root._erpEnterNavBound = true;
    opts = opts || {};

    root.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
      var target = e.target;
      if (!target || !root.contains(target)) return;
      if (target.tagName === "TEXTAREA" && !opts.textareaAdvances) return;
      if (target.matches && !target.matches(FIELD_SEL)) return;
      if (target.closest && target.closest("[data-enter-nav-off]")) return;

      var fields = collectFields(root);
      if (!fields.length) return;
      var idx = fields.indexOf(target);
      if (idx < 0) return;

      e.preventDefault();
      if (idx < fields.length - 1) {
        var next = fields[idx + 1];
        try {
          next.focus();
          if (typeof next.select === "function" && next.tagName === "INPUT") next.select();
        } catch (err) {}
        return;
      }
      triggerSave(findSave(root, opts));
    });
  }

  global.ERPFormEnterNav = { bind: bind, collectFields: collectFields };
})(window);
