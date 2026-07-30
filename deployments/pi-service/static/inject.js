/**
 * Cosmic shell inject — NON-DESTRUCTIVE for normal SPA routes.
 *
 * Critical: commercial mirror wiki-main / pi-chat-main are stubs that
 * `return null`, so /{ws}/wiki and /{ws}/ai-chat paint pure black.
 * We overlay the working PI shells (cosmic-pilot/wiki + /ui) only on those
 * routes, with workspace slug from the URL. Other routes are untouched.
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;

  var OVERLAY_ID = "cosmic-shell-overlay";
  var SHELL_VER = "24";

  // ---- Fixed English i18n dictionary ----
  (function loadFixedI18n() {
    try {
      var u = "/cosmic-pilot/en-i18n-fallbacks-v7.js?v=" + SHELL_VER;
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
      if (++n > 20) clearInterval(timer);
    }, 2000);
  })();

  // ---- Wiki / AI shell overlay (only when SPA stubs would render null) ----
  function matchShellRoute() {
    var path = location.pathname || "";
    // /{workspace}/wiki[...] or /{workspace}/ai-chat[...]
    var m = path.match(/^\/([^/]+)\/(wiki|ai-chat)(?:\/|$)/i);
    if (!m) return null;
    var slug = m[1];
    // Skip reserved first segments
    if (
      /^(cosmic-pilot|api|assets|auth|god-mode|spaces|m|sign-in|sign-up|accounts)$/i.test(slug)
    ) {
      return null;
    }
    return { workspace: slug, kind: m[2].toLowerCase() };
  }

  function shellSrc(route) {
    var q =
      "workspace=" +
      encodeURIComponent(route.workspace) +
      "&embed=1&v=" +
      SHELL_VER;
    if (route.kind === "wiki") {
      return "/cosmic-pilot/wiki?" + q;
    }
    return "/cosmic-pilot/ui?" + q;
  }

  function removeOverlay() {
    var el = document.getElementById(OVERLAY_ID);
    if (el && el.parentNode) el.parentNode.removeChild(el);
    try {
      document.documentElement.removeAttribute("data-cosmic-shell");
    } catch (_) {}
  }

  function mountOverlay(route) {
    var src = shellSrc(route);
    var el = document.getElementById(OVERLAY_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = OVERLAY_ID;
      // Sit above SPA content but leave browser chrome alone.
      // Full viewport: SPA wiki/ai stubs paint pure black otherwise.
      el.style.cssText =
        "position:fixed;inset:0;z-index:2147483000;background:#f4f5f6;margin:0;padding:0;";
      document.documentElement.setAttribute("data-cosmic-shell", route.kind);
      document.body.appendChild(el);
    }
    var iframe = el.querySelector("iframe");
    if (!iframe || iframe.getAttribute("data-src") !== src) {
      el.innerHTML = "";
      iframe = document.createElement("iframe");
      iframe.setAttribute("data-src", src);
      iframe.src = src;
      iframe.title = route.kind === "wiki" ? "Wiki" : "Plane AI";
      iframe.allow = "clipboard-read; clipboard-write";
      iframe.style.cssText =
        "border:0;width:100%;height:100%;display:block;background:#f4f5f6;";
      el.appendChild(iframe);
    }
  }

  function syncShell() {
    try {
      var route = matchShellRoute();
      if (!route) {
        removeOverlay();
        return;
      }
      mountOverlay(route);
    } catch (e) {
      console.warn("cosmic shell sync failed", e);
    }
  }

  // Hook SPA client-side navigation
  try {
    var _push = history.pushState;
    var _replace = history.replaceState;
    history.pushState = function () {
      var r = _push.apply(this, arguments);
      setTimeout(syncShell, 0);
      return r;
    };
    history.replaceState = function () {
      var r = _replace.apply(this, arguments);
      setTimeout(syncShell, 0);
      return r;
    };
    window.addEventListener("popstate", function () {
      setTimeout(syncShell, 0);
    });
  } catch (_) {}

  // Initial + poll (SPA may race)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncShell);
  } else {
    syncShell();
  }
  setInterval(syncShell, 800);

  // Listen for close messages from pilot shell (optional)
  window.addEventListener("message", function (ev) {
    try {
      if (!ev.data || ev.data.source !== "plane-pilot") return;
      if (ev.data.type === "close" || ev.data.action === "close") {
        // Navigate SPA back to workspace home if possible
        var route = matchShellRoute();
        if (route) {
          history.pushState({}, "", "/" + route.workspace + "/");
          syncShell();
        }
      }
    } catch (_) {}
  });
})();
