/**
 * Cosmic inject v38 — dual sidebars, board group_by, epic tour, route fixes,
 * CSS modulepreload fix, faster first paint, CosmicBoosts blank-board recovery.
 * No service workers. No reloads (except one-shot blank-board recovery).
 *
 * Board blank with "Work items N" but empty body:
 * - group_by type/parent_type → no CE columns (if (!groups) return null)
 * - group_by state before states-lite loads → same blank, intermittent
 * Coerce display filters to state; prefetch states-lite into
 * window.__cosmicStateIdsByProject for work-item-layout fallback; one-shot
 * reload if count badge shows with zero issue rows.
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;
  window.__cosmicInjectVersion = 38;

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

  // CosmicBoosts blank-board recovery helpers (states + group_by)
  window.__cosmicStateIdsByProject = window.__cosmicStateIdsByProject || {};
  function projectIdFromPath() {
    try {
      var path =
        (typeof location !== "undefined" && location.pathname) ||
        (window.location && window.location.pathname) ||
        "";
      var m = path.match(
        /\/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i
      );
      return m ? m[1] : null;
    } catch (_) {
      return null;
    }
  }
  function workspaceSlugFromPath() {
    try {
      var path =
        (typeof location !== "undefined" && location.pathname) ||
        (window.location && window.location.pathname) ||
        "";
      var p = path.split("/").filter(Boolean);
      return p[0] || null;
    } catch (_) {
      return null;
    }
  }
  function prefetchProjectStates(slug, projectId) {
    if (!slug || !projectId) return;
    if (window.__cosmicStateIdsByProject[projectId] && window.__cosmicStateIdsByProject[projectId].length)
      return;
    var url =
      "/api/workspaces/" +
      encodeURIComponent(slug) +
      "/projects/" +
      encodeURIComponent(projectId) +
      "/states-lite/";
    try {
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          var rows = [];
          if (Array.isArray(data)) rows = data;
          else if (data && Array.isArray(data.results)) rows = data.results;
          var ids = rows
            .map(function (s) {
              return s && s.id ? String(s.id) : null;
            })
            .filter(Boolean);
          if (ids.length) {
            window.__cosmicStateIdsByProject[projectId] = ids;
            window.__cosmicRouterProjectId = projectId;
            // Nudge React: toggle a storage event many boards subscribe to
            try {
              window.dispatchEvent(new Event("local-storage:issue_local_filters"));
            } catch (_) {}
          }
        })
        .catch(function () {});
    } catch (_) {}
  }
  function ensureBoardGroupByState(slug, projectId) {
    if (!slug || !projectId) return;
    var url =
      "/api/workspaces/" +
      encodeURIComponent(slug) +
      "/projects/" +
      encodeURIComponent(projectId) +
      "/user-properties/";
    try {
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          if (!data || typeof data !== "object") return;
          var df = data.display_filters || {};
          var gb = df.group_by;
          var bad =
            gb === "type" ||
            gb === "parent_type" ||
            gb === "type_id" ||
            gb === "parent_id" ||
            gb === "milestone" ||
            gb === "release";
          // Also force when group_by missing on kanban layouts
          var layout = df.layout;
          if (!bad && !(layout === "kanban" && (gb == null || gb === ""))) return;
          var next = Object.assign({}, data, {
            display_filters: Object.assign({}, df, {
              group_by: "state",
              sub_group_by:
                df.sub_group_by === "type" ||
                df.sub_group_by === "parent_type"
                  ? null
                  : df.sub_group_by,
            }),
          });
          var csrf = null;
          try {
            var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
            csrf = m ? decodeURIComponent(m[1]) : null;
          } catch (_) {}
          fetch(url, {
            method: "PATCH",
            credentials: "same-origin",
            headers: {
              "content-type": "application/json",
              ...(csrf ? { "X-CSRFToken": csrf } : {}),
            },
            body: JSON.stringify({
              display_filters: next.display_filters,
            }),
          }).catch(function () {});
        })
        .catch(function () {});
    } catch (_) {}
  }
  function isIssuesPath() {
    try {
      var path =
        (typeof location !== "undefined" && location.pathname) ||
        (window.location && window.location.pathname) ||
        "";
      return /\/projects\/[^/]+\/issues\/?/.test(path);
    } catch (_) {
      return false;
    }
  }
  function runBoardWarmup() {
    if (!isIssuesPath()) return;
    var slug = workspaceSlugFromPath();
    var pid = projectIdFromPath();
    window.__cosmicRouterProjectId = pid;
    prefetchProjectStates(slug, pid);
    ensureBoardGroupByState(slug, pid);
  }
  runBoardWarmup();
  // SPA client navigations
  try {
    var _ps = history.pushState;
    var _rs = history.replaceState;
    history.pushState = function () {
      var r = _ps.apply(this, arguments);
      setTimeout(runBoardWarmup, 0);
      return r;
    };
    history.replaceState = function () {
      var r = _rs.apply(this, arguments);
      setTimeout(runBoardWarmup, 0);
      return r;
    };
    window.addEventListener("popstate", function () {
      setTimeout(runBoardWarmup, 0);
    });
  } catch (_) {}

  // One-shot recovery: count badge present, zero issue rows → fix filters + reload
  function blankBoardRecovery() {
    if (!isIssuesPath()) return;
    if (sessionStorage.getItem("cosmic_blank_board_reloaded") === "1") return;
    try {
      var text = (document.body && document.body.innerText) || "";
      var countMatch = text.match(/Work items?\s+(\d+)/i);
      var count = countMatch ? parseInt(countMatch[1], 10) : 0;
      if (!(count > 0)) return;
      // issue rows / kanban cards
      var rows =
        document.querySelectorAll(
          '[id^="issue-"], a[href*="/issues/"][href*="-"], .group\\/kanban-block'
        ).length || 0;
      // Also count list rows with sequence-like DEMO-1
      if (rows < 1 && /[A-Z]{2,5}-\d+/.test(text)) rows = 1;
      if (rows >= 1) return;
      // pure empty main with badge — recover once
      sessionStorage.setItem("cosmic_blank_board_reloaded", "1");
      coerceIssueLocalFiltersStorage();
      var slug = workspaceSlugFromPath();
      var pid = projectIdFromPath();
      ensureBoardGroupByState(slug, pid);
      // Force local filters to state for this view
      try {
        var raw = localStorage.getItem("issue_local_filters");
        if (raw) {
          var arr = JSON.parse(raw);
          if (Array.isArray(arr)) {
            arr.forEach(function (entry) {
              if (!entry || !entry.filters) return;
              var df =
                entry.filters.display_filters ||
                entry.filters.displayFilters ||
                {};
              if (typeof df === "object") {
                df.group_by = "state";
                if (
                  df.sub_group_by === "type" ||
                  df.sub_group_by === "parent_type"
                )
                  df.sub_group_by = null;
                if (entry.filters.display_filters) entry.filters.display_filters = df;
                if (entry.filters.displayFilters) entry.filters.displayFilters = df;
              }
            });
            localStorage.setItem("issue_local_filters", JSON.stringify(arr));
          }
        }
      } catch (_) {}
      setTimeout(function () {
        try {
          (window.location || location).reload();
        } catch (_) {}
      }, 200);
    } catch (_) {}
  }
  setTimeout(blankBoardRecovery, 2500);
  setTimeout(blankBoardRecovery, 5000);
  setTimeout(function () {
    try {
      sessionStorage.removeItem("cosmic_blank_board_reloaded");
    } catch (_) {}
  }, 30000);
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

  // localStorage early (before SPA MobX hydrate).
  expandDualSidebars();
  // CSS immediately so Projects panel width is correct on first paint (fixes
  // intermittent blank main / missing panel while waiting for load).
  injectForceOpenCss();

  /** Commercial root modulepreloads *.css as scripts → MIME "text/css" errors. */
  function fixCssModulePreloads(root) {
    try {
      var scope = root || document;
      var links = scope.querySelectorAll
        ? scope.querySelectorAll('link[rel="modulepreload"]')
        : [];
      for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute("href") || "";
        if (/\.css(\?|#|$)/i.test(href)) {
          links[i].setAttribute("rel", "stylesheet");
          links[i].removeAttribute("as");
          links[i].removeAttribute("crossorigin");
        }
      }
    } catch (_) {}
  }
  fixCssModulePreloads(document);

  /** Map dead CE/self-host URLs onto commercial SPA routes. */
  function fixClientRoutes() {
    try {
      var path = location.pathname || "";
      // /{ws}/projects/{uuid} → issues (commercial uses /overview or /issues)
      var m = path.match(
        /^\/([^/]+)\/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i
      );
      if (m) {
        location.replace("/" + m[1] + "/projects/" + m[2] + "/issues/");
        return true;
      }
      m = path.match(/^\/([^/]+)\/workspace-drafts\/?$/i);
      if (m) {
        location.replace("/" + m[1] + "/drafts/");
        return true;
      }
      m = path.match(/^\/([^/]+)\/profile\/?$/i);
      if (m) {
        var uid = null;
        try {
          uid = localStorage.getItem("cosmic_user_id");
        } catch (_) {}
        if (uid) {
          location.replace("/" + m[1] + "/profile/" + uid + "/");
          return true;
        }
      }
    } catch (_) {}
    return false;
  }
  if (fixClientRoutes()) return;

  // Capture user id for /profile redirects
  function rememberUserId(data) {
    try {
      if (data && data.id) localStorage.setItem("cosmic_user_id", String(data.id));
    } catch (_) {}
  }

  // Drop splash once SPA root mounts so first paint is not a long spinner.
  function clearSplashSoon() {
    try {
      var d = document.documentElement;
      var tries = 0;
      var t = setInterval(function () {
        tries += 1;
        var root = document.getElementById("root") || document.querySelector("[data-reactroot]");
        var hasApp =
          document.getElementById("main-sidebar") ||
          document.querySelector('a[href*="/wiki"]') ||
          (document.body && document.body.innerText && document.body.innerText.length > 80);
        if (hasApp || tries > 40) {
          try {
            d.removeAttribute("data-splash-screen");
          } catch (_) {}
          clearInterval(t);
        }
      }, 100);
    } catch (_) {}
  }
  clearSplashSoon();

  function afterFirstPaint() {
    injectForceOpenCss();
    forceMainSidebarDom();
    fixCssModulePreloads(document);
  }
  // Toggle/DOM nudge shortly after first paint (not only on full load)
  setTimeout(afterFirstPaint, 50);
  setTimeout(afterFirstPaint, 400);
  if (document.readyState === "complete") {
    setTimeout(afterFirstPaint, 0);
  } else {
    window.addEventListener("load", function () {
      setTimeout(afterFirstPaint, 0);
    });
  }

  // Keep converting CSS modulepreloads as SPA injects more <link>s
  try {
    if (typeof MutationObserver !== "undefined") {
      var moCss = new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          var nodes = muts[i].addedNodes || [];
          for (var j = 0; j < nodes.length; j++) {
            var n = nodes[j];
            if (n && n.nodeType === 1) fixCssModulePreloads(n);
          }
        }
      });
      moCss.observe(document.documentElement, { childList: true, subtree: true });
      setTimeout(function () {
        try {
          moCss.disconnect();
        } catch (_) {}
      }, 20000);
    }
  } catch (_) {}

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
      if (/\/api\/users\/me\/?(\?|$)/.test(u) && u.indexOf("/profile") === -1) return "me";
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
          // Keep project list on flat page (no commercial group_by groups API)
          data.is_project_grouping_enabled = false;
          return data;
        }
        if (kind === "flags") {
          if (!data.values) data.values = {};
          data.values.AI_CHAT = true;
          data.values.APP_RAIL = true;
          data.values.WORKSPACE_PAGES = true;
          data.values.PI_CHAT = true;
          // Avoid commercial project-list grouping path
          data.values.PROJECT_GROUPING = false;
        }
        if (kind === "userprops") {
          coerceGroupByDeep(data);
        }
        if (kind === "prefs") {
          ensureEpicExplored(data);
        }
        if (kind === "me") {
          rememberUserId(data);
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
  var ticks = 0;
  var timer = setInterval(function () {
    expandDualSidebars();
    injectForceOpenCss();
    forceMainSidebarDom();
    fixCssModulePreloads(document);
    ticks += 1;
    if (ticks >= 48) clearInterval(timer); // ~12s
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
