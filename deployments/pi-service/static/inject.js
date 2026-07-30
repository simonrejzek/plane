/**
 * Cosmic inject v29 — soft fixes only. NO reloads. NO service workers.
 *
 * Commercial SPA Wiki/AI modules are the capture from app.plane.so.
 * This script only:
 *  - unregisters broken SW from v28 (was causing click→reload bounce)
 *  - forces PI/Wiki flags + auth-check on XHR/fetch
 *  - i18n + tour dismiss
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;
  window.__cosmicInjectVersion = 29;

  // ---- KILL v28 service worker + never reload ----
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

  // Remove leftover overlay shells
  try {
    var old = document.getElementById("cosmic-shell-overlay");
    if (old && old.parentNode) old.parentNode.removeChild(old);
    document.documentElement.removeAttribute("data-cosmic-shell");
  } catch (_) {}

  // ---- Force PI/Wiki API responses (XHR + fetch) — capture SPA expects these ----
  (function forcePiWikiFlags() {
    function isTarget(url) {
      if (!url) return null;
      var u = String(url);
      if (u.indexOf("/api/v1/chat/start/auth-check") !== -1) return "auth-check";
      if (u.indexOf("/api/v1/flags") !== -1) return "v1-flags";
      if (/\/api\/workspaces\/[^/]+\/features\/?(\?|$)/.test(u)) return "features";
      if (/\/api\/payments\/workspaces\/[^/]+\/flags\/?(\?|$)/.test(u)) return "pay-flags";
      if (u.indexOf("/api/feature-flags") !== -1) return "feature-flags";
      return null;
    }

    function patchBody(kind, data) {
      try {
        if (data == null) data = {};
        if (typeof data !== "object") return data;
        if (kind === "auth-check") {
          data.is_authorized = true;
          if (data.oauth_url === undefined) data.oauth_url = null;
          if (data.has_chats === undefined) data.has_chats = false;
          return data;
        }
        if (kind === "features") {
          data.is_pi_enabled = true;
          data.is_wiki_enabled = true;
          return data;
        }
        if (kind === "pay-flags" || kind === "v1-flags" || kind === "feature-flags") {
          if (!data.values || typeof data.values !== "object") data.values = {};
          [
            "AI_CHAT", "AI_DEDUPE", "AI_CONVERSE", "AI_FILE_UPLOADS", "AI_PAGES_BLOCKS",
            "AI_PAGES_SUMMARY", "AI_MCP_CONNECTORS", "AI_TEXT_TO_PQL", "AI_PAGES_EDIT",
            "AI_AUTOPILOT", "AI_SKILLS", "PI_CHAT", "APP_RAIL", "WORKSPACE_PAGES",
            "NESTED_PAGES", "EDITOR_AI_OPS", "BRIDGE", "PAGE_TEMPLATES",
          ].forEach(function (k) {
            data.values[k] = true;
          });
          if (data.default && typeof data.default === "object") {
            Object.keys(data.values).forEach(function (k) {
              data.default[k] = true;
            });
          }
          return data;
        }
      } catch (_) {}
      return data;
    }

    function rewriteResponseText(kind, text) {
      try {
        var data = JSON.parse(text);
        return JSON.stringify(patchBody(kind, data));
      } catch (_) {
        if (kind === "auth-check")
          return JSON.stringify({ is_authorized: true, oauth_url: null, has_chats: false });
        if (kind === "v1-flags" || kind === "pay-flags")
          return JSON.stringify({ values: { AI_CHAT: true, APP_RAIL: true, WORKSPACE_PAGES: true } });
        if (kind === "features")
          return JSON.stringify({ is_pi_enabled: true, is_wiki_enabled: true });
        return text;
      }
    }

    try {
      var XO = XMLHttpRequest.prototype.open;
      var XS = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (method, url) {
        this.__cosmicUrl = url;
        this.__cosmicKind = isTarget(url);
        return XO.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function () {
        var xhr = this;
        var kind = xhr.__cosmicKind;
        if (kind) {
          xhr.addEventListener("readystatechange", function () {
            if (xhr.readyState !== 4) return;
            try {
              var fixed = rewriteResponseText(kind, xhr.responseText);
              try {
                Object.defineProperty(xhr, "responseText", { get: function () { return fixed; } });
              } catch (_) {}
              try {
                Object.defineProperty(xhr, "response", { get: function () { return fixed; } });
              } catch (_) {}
              try {
                Object.defineProperty(xhr, "status", { get: function () { return 200; } });
              } catch (_) {}
            } catch (_) {}
          });
        }
        return XS.apply(this, arguments);
      };
    } catch (e) {
      console.warn("cosmic xhr patch failed", e);
    }

    try {
      var _f = window.fetch;
      window.fetch = function (input, init) {
        var url =
          typeof input === "string" ? input : input && input.url ? input.url : String(input);
        var kind = isTarget(url);
        return _f.call(this, input, init).then(function (res) {
          if (!kind) return res;
          return res
            .clone()
            .text()
            .then(function (text) {
              return new Response(rewriteResponseText(kind, text), {
                status: 200,
                statusText: "OK",
                headers: { "content-type": "application/json" },
              });
            })
            .catch(function () {
              return res;
            });
        });
      };
    } catch (e) {
      console.warn("cosmic fetch patch failed", e);
    }
  })();

  // ---- Fixed English i18n ----
  (function loadFixedI18n() {
    try {
      fetch("/cosmic-pilot/en-i18n-fallbacks-v7.js?v=29", {
        credentials: "same-origin",
        cache: "no-store",
      })
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
            if (v && v.indexOf("plural") !== -1) node.nodeValue = v.replace(re, "$2");
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
      try {
        var el = document.getElementById("cosmic-shell-overlay");
        if (el && el.parentNode) el.parentNode.removeChild(el);
      } catch (_) {}
      if (++n > 40) clearInterval(timer);
    }, 1500);
  })();
})();
