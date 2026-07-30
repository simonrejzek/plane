/**
 * Cosmic inject — soft fixes only.
 *
 * Do NOT overlay custom Wiki/AI shells. The commercial SPA already ships
 * real Wiki (:workspaceSlug/wiki) and AI (:workspaceSlug/ai-chat) route
 * modules (layout-CFpI-AZP, page-CvY-jB5L2, pi-chat layouts, etc.).
 * Overlaying /cosmic-pilot/* replaced app.plane.so UI with a homemade shell.
 *
 * This script only:
 *  - merges fixed English i18n (ICU plurals)
 *  - marks product tours dismissed
 *  - soft-fixes raw ICU text that leaks into the DOM
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;

  // Remove any leftover overlay from previous inject versions
  try {
    var old = document.getElementById("cosmic-shell-overlay");
    if (old && old.parentNode) old.parentNode.removeChild(old);
    document.documentElement.removeAttribute("data-cosmic-shell");
  } catch (_) {}

  // ---- Fixed English i18n dictionary ----
  (function loadFixedI18n() {
    try {
      var u = "/cosmic-pilot/en-i18n-fallbacks-v7.js?v=26";
      fetch(u, { credentials: "same-origin", cache: "no-store" })
        .then(function (r) {
          return r.text();
        })
        .then(function (txt) {
          try {
            var fn = new Function(
              txt +
                ";return window.__PLANE_EN_I18N__ || (typeof __PLANE_EN_I18N__!=='undefined'?__PLANE_EN_I18N__:null);"
            );
            var dict = fn();
            if (dict && typeof dict === "object") {
              window.__PLANE_EN_I18N__ = dict;
              try {
                if (window.i18n && window.i18n.addResourceBundle) {
                  window.i18n.addResourceBundle("en", "translations", dict, true, true);
                  window.i18n.addResourceBundle("en", "common", dict, true, true);
                }
              } catch (_) {}
            }
          } catch (e) {
            console.warn("cosmic i18n merge failed", e);
          }
        })
        .catch(function () {});
    } catch (_) {}
  })();

  // ---- Tours dismissed ----
  try {
    [
      "plane.product_tour.completed",
      "plane.tour.completed",
      "is_tour_completed",
      "is_navigation_tour_completed",
      "product_tour_dismissed",
    ].forEach(function (k) {
      try {
        localStorage.setItem(k, "true");
      } catch (_) {}
    });
  } catch (_) {}

  // ---- Soft ICU text fix ----
  (function cosmicUiFixes() {
    function fixIcuText(root) {
      try {
        var re = /\{count,\s*plural,\s*one\s*\{([^}]*)\}\s*other\s*\{([^}]*)\}\}/gi;
        var walk = function (node) {
          if (!node) return;
          if (node.nodeType === 3) {
            var v = node.nodeValue;
            if (v && v.indexOf("plural") !== -1) {
              node.nodeValue = v.replace(re, "$2");
            }
            return;
          }
          if (node.nodeType === 1) {
            var tag = (node.tagName || "").toLowerCase();
            if (tag === "script" || tag === "style") return;
            for (var i = 0; i < node.childNodes.length; i++) walk(node.childNodes[i]);
          }
        };
        walk(root || document.body);
      } catch (_) {}
    }
    var n = 0;
    var timer = setInterval(function () {
      fixIcuText(document.body);
      // Keep clearing any accidental re-injection of the shell overlay
      try {
        var el = document.getElementById("cosmic-shell-overlay");
        if (el && el.parentNode) el.parentNode.removeChild(el);
      } catch (_) {}
      if (++n > 40) clearInterval(timer);
    }, 1500);
  })();
})();
