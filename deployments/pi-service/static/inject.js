/**
 * Cosmic shell inject — NON-DESTRUCTIVE only.
 *
 * Do NOT wipe the document or force full-page pilot/wiki iframes.
 * The commercial SPA already has native Wiki + AI routes; taking over
 * left users stuck on a dark grey blank (#0e0f10).
 *
 * This script only:
 *  - merges fixed English i18n (ICU plurals expanded)
 *  - marks tours dismissed in localStorage
 *  - soft-fixes raw ICU text that leaks into the DOM
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;

  // ---- Fixed English i18n dictionary (no UI takeover) ----
  (function loadFixedI18n() {
    try {
      var u = "/cosmic-pilot/en-i18n-fallbacks-v7.js?v=20";
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

  // ---- Soft UI fixes (never replace document / never force dark void) ----
  (function cosmicUiFixes() {
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
      if (++n > 30) clearInterval(timer);
    }, 2000);
    document.addEventListener("DOMContentLoaded", function () {
      fixIcuText(document.body);
    });
  })();
})();
