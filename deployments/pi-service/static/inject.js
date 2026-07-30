/**
 * Cosmic inject v33 — dual sidebars only.
 * No service workers. No reloads. No import maps. No module remaps.
 *
 * Keeps APP_RAIL on (icon rail) and forces the Projects panel expanded.
 * The commercial SPA hides that panel when app_sidebar_collapsed===true
 * (layout width 0) or when theme sidebarCollapsed hydrates to true.
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;
  window.__cosmicInjectVersion = 33;

  // Kill any SW left from broken experiments
  try {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.getRegistrations().then(function (regs) {
        regs.forEach(function (r) {
          try {
            r.unregister();
          } catch (_) {}
        });
      });
    }
  } catch (_) {}
  try {
    sessionStorage.removeItem("cosmic_ai_gate_sw_reloaded_v28");
  } catch (_) {}

  try {
    var old = document.getElementById("cosmic-shell-overlay");
    if (old && old.parentNode) old.parentNode.removeChild(old);
    document.documentElement.removeAttribute("data-cosmic-shell");
  } catch (_) {}

  /**
   * Exact keys the mirrored SPA reads for dual-sidebar layout:
   * - payments/feature flags: APP_RAIL
   * - theme hydrate (store-wrapper): app_sidebar_collapsed
   * - projects panel width (layout-DPbuSs0c / _sidebar): sidebarWidth (JSON number)
   * - hide-rail keys: APP_RAIL_${slug}
   */
  function expandDualSidebars() {
    try {
      Object.keys(localStorage).forEach(function (k) {
        if (k.indexOf("APP_RAIL_") === 0) localStorage.removeItem(k);
      });
      localStorage.setItem("app_sidebar_collapsed", "false");
      // useLocalStorage stores JSON.stringify(value)
      localStorage.setItem("sidebarWidth", JSON.stringify(250));
      try {
        window.dispatchEvent(
          new CustomEvent("local-storage:app_sidebar_collapsed", {
            detail: { key: "app_sidebar_collapsed", value: "false" },
          })
        );
        window.dispatchEvent(
          new Event("local-storage:app_sidebar_collapsed")
        );
        window.dispatchEvent(new Event("local-storage:sidebarWidth"));
      } catch (_) {}
    } catch (_) {}
  }

  // Run immediately (may still lose to deferred order; early index script also runs)
  expandDualSidebars();

  // Soft-force critical flags (APP_RAIL must stay true for icon rail)
  (function forceFlags() {
    function kindOf(url) {
      if (!url) return null;
      var u = String(url);
      if (u.indexOf("/api/v1/chat/start/auth-check") !== -1) return "auth";
      if (u.indexOf("/api/v1/flags") !== -1) return "flags";
      if (/\/api\/workspaces\/[^/]+\/features\/?(\?|$)/.test(u)) return "features";
      if (/\/api\/payments\/workspaces\/[^/]+\/flags/.test(u)) return "flags";
      return null;
    }
    function patch(kind, data) {
      try {
        if (!data || typeof data !== "object") return data;
        if (kind === "auth") {
          data.is_authorized = true;
          return data;
        }
        if (kind === "features") {
          data.is_pi_enabled = true;
          data.is_wiki_enabled = true;
          return data;
        }
        if (kind === "flags") {
          if (!data.values) data.values = {};
          data.values.AI_CHAT = true;
          data.values.APP_RAIL = true;
          data.values.WORKSPACE_PAGES = true;
          data.values.PI_CHAT = true;
        }
      } catch (_) {}
      return data;
    }
    try {
      var XO = XMLHttpRequest.prototype.open,
        XS = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (m, url) {
        this.__k = kindOf(url);
        return XO.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function () {
        var x = this,
          k = x.__k;
        if (k) {
          x.addEventListener("readystatechange", function () {
            if (x.readyState !== 4) return;
            try {
              var d = JSON.parse(x.responseText);
              d = patch(k, d);
              var t = JSON.stringify(d);
              try {
                Object.defineProperty(x, "responseText", {
                  get: function () {
                    return t;
                  },
                });
              } catch (_) {}
              try {
                Object.defineProperty(x, "response", {
                  get: function () {
                    return t;
                  },
                });
              } catch (_) {}
            } catch (_) {}
          });
        }
        return XS.apply(this, arguments);
      };
    } catch (_) {}
    try {
      var _f = window.fetch;
      window.fetch = function (input, init) {
        var url =
          typeof input === "string"
            ? input
            : (input && input.url) || String(input);
        var k = kindOf(url);
        return _f.call(this, input, init).then(function (res) {
          if (!k) return res;
          return res
            .clone()
            .json()
            .then(function (data) {
              return new Response(JSON.stringify(patch(k, data)), {
                status: res.status,
                headers: { "content-type": "application/json" },
              });
            })
            .catch(function () {
              return res;
            });
        });
      };
    } catch (_) {}
  })();

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

  // Re-apply after SPA theme hydrate (store-wrapper reads app_sidebar_collapsed once).
  // No full-page reloads — only preference re-write + storage events.
  var ticks = 0;
  var timer = setInterval(function () {
    expandDualSidebars();
    ticks += 1;
    if (ticks >= 24) clearInterval(timer); // ~6s
  }, 250);

  // Also on focus / visibility (user returns to tab after SPA mounted)
  try {
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) expandDualSidebars();
    });
    window.addEventListener("focus", expandDualSidebars);
  } catch (_) {}
})();
