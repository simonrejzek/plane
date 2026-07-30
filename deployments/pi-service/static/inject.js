/**
 * Cosmic inject v36 — dual sidebars + board group_by coerce + epic tour dismiss.
 * No service workers. No reloads. No import maps. No module remaps.
 *
 * Keeps APP_RAIL on (icon rail) and forces the Projects panel expanded.
 *
 * Why CSS/DOM as well as localStorage:
 * The commercial SPA hydrates MobX `sidebarCollapsed` once from
 * `app_sidebar_collapsed`. After that, rewriting localStorage alone does
 * nothing — ResizableSidebar keeps `#main-sidebar` at width 0. We therefore
 * (1) keep the storage key false, (2) block setItem(true), (3) force the
 * real #main-sidebar open via CSS + optional toggle click (after hydrate).
 *
 * Board blank with "Work items N": commercial SPA group_by type/parent_type
 * needs work-item-types (CE empty) / parent_type always void 0 →
 * getGroupByColumns returns undefined → if (!groups) return null.
 * Coerce those display filters to "state" in localStorage + user-properties.
 *
 * Epics walkthrough: preferences must include explored_features.epic_migration.
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;
  window.__cosmicInjectVersion = 36;

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

  /** Commercial-only group keys that blank the CE board. */
  var BAD_GROUP_BY = {
    type: 1,
    parent_type: 1,
    type_id: 1,
    parent_id: 1,
  };

  function isBadGroupBy(v) {
    return v != null && BAD_GROUP_BY[String(v)] === 1;
  }

  function coerceDisplayFilters(df) {
    if (!df || typeof df !== "object") return false;
    var changed = false;
    if (isBadGroupBy(df.group_by)) {
      df.group_by = "state";
      changed = true;
    }
    if (isBadGroupBy(df.sub_group_by)) {
      df.sub_group_by = null;
      changed = true;
    }
    return changed;
  }

  /** Walk any JSON tree and fix display_filters.group_by in place. */
  function coerceGroupByDeep(node) {
    if (!node || typeof node !== "object") return false;
    var changed = false;
    if (Object.prototype.hasOwnProperty.call(node, "display_filters")) {
      if (coerceDisplayFilters(node.display_filters)) changed = true;
    }
    if (Object.prototype.hasOwnProperty.call(node, "group_by") && isBadGroupBy(node.group_by)) {
      // bare display-filter objects
      if (
        Object.prototype.hasOwnProperty.call(node, "layout") ||
        Object.prototype.hasOwnProperty.call(node, "order_by") ||
        Object.prototype.hasOwnProperty.call(node, "sub_group_by")
      ) {
        node.group_by = "state";
        changed = true;
      }
    }
    if (Object.prototype.hasOwnProperty.call(node, "sub_group_by") && isBadGroupBy(node.sub_group_by)) {
      if (
        Object.prototype.hasOwnProperty.call(node, "layout") ||
        Object.prototype.hasOwnProperty.call(node, "order_by") ||
        Object.prototype.hasOwnProperty.call(node, "group_by")
      ) {
        node.sub_group_by = null;
        changed = true;
      }
    }
    if (Array.isArray(node)) {
      for (var i = 0; i < node.length; i++) {
        if (coerceGroupByDeep(node[i])) changed = true;
      }
    } else {
      for (var k in node) {
        if (!Object.prototype.hasOwnProperty.call(node, k)) continue;
        var v = node[k];
        if (v && typeof v === "object") {
          if (coerceGroupByDeep(v)) changed = true;
        }
      }
    }
    return changed;
  }

  function coerceIssueLocalFiltersRaw(raw) {
    if (raw == null || raw === "") return { value: raw, changed: false };
    try {
      var parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (!coerceGroupByDeep(parsed)) {
        return { value: typeof raw === "string" ? raw : JSON.stringify(parsed), changed: false };
      }
      return { value: JSON.stringify(parsed), changed: true };
    } catch (_) {
      return { value: raw, changed: false };
    }
  }

  function coerceIssueLocalFiltersStorage() {
    try {
      var raw = localStorage.getItem("issue_local_filters");
      if (!raw) return;
      var out = coerceIssueLocalFiltersRaw(raw);
      if (out.changed) {
        // use native setItem if we already wrapped it
        localStorage.setItem("issue_local_filters", out.value);
      }
    } catch (_) {}
  }

  /**
   * Exact keys the mirrored SPA reads for dual-sidebar layout:
   * - payments/feature flags: APP_RAIL
   * - theme hydrate (store-wrapper): app_sidebar_collapsed
   * - projects panel width (layout / useLocalStorage): sidebarWidth (JSON number)
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

  // Prevent SPA / toggle from re-collapsing via storage after we expand
  // Also coerce bad board group_by when SPA writes issue_local_filters.
  try {
    var _setItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
      if (key === "app_sidebar_collapsed" && String(value) === "true") {
        return _setItem(key, "false");
      }
      if (key === "issue_local_filters") {
        var c = coerceIssueLocalFiltersRaw(value);
        return _setItem(key, c.value);
      }
      return _setItem(key, value);
    };
  } catch (_) {}

  // Fix any already-persisted type/parent_type grouping before SPA hydrates.
  coerceIssueLocalFiltersStorage();
  // CSS force: ResizableSidebar sets inline width:0 when MobX says collapsed.
  // !important beats those inline styles so the Projects panel stays visible.
  function injectForceOpenCss() {
    try {
      if (document.getElementById("cosmic-force-projects-sidebar")) return;
      var style = document.createElement("style");
      style.id = "cosmic-force-projects-sidebar";
      style.textContent = [
        "/* Cosmic dual-sidebar: keep Projects panel open beside app rail */",
        "#main-sidebar{",
        "  width:250px !important;",
        "  min-width:250px !important;",
        "  max-width:350px !important;",
        "  opacity:1 !important;",
        "  transform:translateX(0) !important;",
        "  pointer-events:auto !important;",
        "}",
        /* spacer fallback while ProjectAppSidebar lazy-loads */
        'div.h-full.shrink-0.bg-surface-1[aria-hidden="true"]{',
        "  width:250px !important;",
        "}",
      ].join("\n");
      var root = document.head || document.documentElement;
      root.appendChild(style);
    } catch (_) {}
  }

  function forceMainSidebarDom() {
    try {
      var el = document.getElementById("main-sidebar");
      if (!el) return;
      var rect = el.getBoundingClientRect();
      if (rect.width >= 180) return;
      // Prefer real React toggle so MobX matches visible state
      try {
        var toggles = document.querySelectorAll(
          'button[aria-label*="sidebar" i], button[aria-label*="Sidebar" i]'
        );
        for (var i = 0; i < toggles.length; i++) {
          var b = toggles[i];
          if (b && typeof b.click === "function") {
            b.click();
            break;
          }
        }
      } catch (_) {}
      el.style.setProperty("width", "250px", "important");
      el.style.setProperty("min-width", "250px", "important");
      el.style.setProperty("max-width", "350px", "important");
      el.style.setProperty("opacity", "1", "important");
      el.style.setProperty("transform", "translateX(0)", "important");
    } catch (_) {}
  }

  // localStorage early (before SPA MobX hydrate). DOM/CSS force waits so we
  // don't fight React hydration (minified error #418 text mismatches).
  expandDualSidebars();
  function afterHydrateShell() {
    injectForceOpenCss();
    forceMainSidebarDom();
  }
  if (document.readyState === "complete") {
    setTimeout(afterHydrateShell, 0);
  } else {
    window.addEventListener("load", function () {
      setTimeout(afterHydrateShell, 0);
    });
  }

  // Soft-force critical flags (APP_RAIL must stay true for icon rail)
  // + coerce type/parent_type group_by on user-properties responses
  // + dismiss Epics migration walkthrough via preferences.explored_features.
  (function forceFlags() {
    function kindOf(url) {
      if (!url) return null;
      var u = String(url);
      if (u.indexOf("/api/v1/chat/start/auth-check") !== -1) return "auth";
      if (u.indexOf("/api/v1/flags") !== -1) return "flags";
      if (/\/api\/workspaces\/[^/]+\/features\/?(\?|$)/.test(u)) return "features";
      if (/\/api\/payments\/workspaces\/[^/]+\/flags/.test(u)) return "flags";
      // Project/cycle/module/workspace user-properties hold display_filters.group_by
      if (u.indexOf("/user-properties") !== -1) return "userprops";
      if (/\/api\/workspaces\/[^/]+\/preferences\/?(\?|$)/.test(u)) return "prefs";
      return null;
    }
    function ensureEpicExplored(data) {
      if (!data || typeof data !== "object") return data;
      if (!data.explored_features || typeof data.explored_features !== "object") {
        data.explored_features = {};
      }
      data.explored_features.epic_migration = true;
      return data;
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
        if (kind === "userprops") {
          coerceGroupByDeep(data);
        }
        if (kind === "prefs") {
          ensureEpicExplored(data);
        }
      } catch (_) {}
      return data;
    }
    function maybeCoerceBody(body) {
      if (body == null || body === "") return body;
      try {
        if (typeof body === "string") {
          var parsed = JSON.parse(body);
          if (coerceGroupByDeep(parsed)) return JSON.stringify(parsed);
          return body;
        }
        if (typeof body === "object" && !(typeof Blob !== "undefined" && body instanceof Blob)) {
          coerceGroupByDeep(body);
        }
      } catch (_) {}
      return body;
    }
    try {
      var XO = XMLHttpRequest.prototype.open,
        XS = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (m, url) {
        this.__k = kindOf(url);
        this.__m = m ? String(m).toUpperCase() : "GET";
        return XO.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function (body) {
        var x = this,
          k = x.__k;
        // Coerce PATCH/PUT bodies so SPA can't re-persist type grouping
        if (k === "userprops" && body != null) {
          body = maybeCoerceBody(body);
        }
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
        return XS.call(this, body);
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
        var nextInit = init;
        if (k === "userprops" && init && init.body != null) {
          nextInit = Object.assign({}, init, {
            body: maybeCoerceBody(init.body),
          });
        }
        return _f.call(this, input, nextInit).then(function (res) {
          if (!k) return res;
          return res
            .clone()
            .json()
            .then(function (data) {
              return new Response(JSON.stringify(patch(k, data)), {
                status: res.status,
                statusText: res.statusText,
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

  // Re-apply after SPA theme hydrate. No full-page reloads.
  // Start after first paint so React can hydrate without our forced width.
  var ticks = 0;
  var timer = setInterval(function () {
    expandDualSidebars();
    if (document.readyState === "complete" || ticks > 2) {
      injectForceOpenCss();
      forceMainSidebarDom();
    }
    ticks += 1;
    if (ticks >= 40) clearInterval(timer); // ~10s
  }, 250);

  // Keep CSS in DOM if SPA rewrites head; re-check panel on navigation
  try {
    if (typeof MutationObserver !== "undefined") {
      var mo = new MutationObserver(function () {
        injectForceOpenCss();
        forceMainSidebarDom();
      });
      mo.observe(document.documentElement, {
        childList: true,
        subtree: true,
      });
      setTimeout(function () {
        try {
          mo.disconnect();
        } catch (_) {}
      }, 15000);
    }
  } catch (_) {}

  try {
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        expandDualSidebars();
        injectForceOpenCss();
        forceMainSidebarDom();
      }
    });
    window.addEventListener("focus", function () {
      expandDualSidebars();
      injectForceOpenCss();
      forceMainSidebarDom();
    });
  } catch (_) {}
})();
