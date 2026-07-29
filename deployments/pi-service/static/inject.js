/**
 * Cosmic shell inject.
 *
 * Preferred path: native /ai-chat React route (in-shell App Rail, like app.plane.so).
 * Fallback: if this script runs on an /ai-chat path, take over with Pilot UI so a
 * missing/stale SPA route never leaves users on a 404 (App Rail AI link).
 *
 * Wiki still uses full-page takeover (no CE wiki product surface yet).
 */
(function () {
  if (window.__cosmicShellInjected) return;
  window.__cosmicShellInjected = true;

  const path = location.pathname || "";
  if (
    path.startsWith("/sign-in") ||
    path.startsWith("/sign-up") ||
    path.startsWith("/god-mode") ||
    path.startsWith("/spaces") ||
    path.startsWith("/cosmic-pilot")
  ) {
    return;
  }

  function isWikiPath(p) {
    return /^\/[^/]+\/wiki(\/|$)/.test(p || "");
  }
  function isAiPath(p) {
    return /^\/[^/]+\/(ai-chat|pi-chat)(\/|$)/.test(p || "");
  }

  // Prefer native in-shell AI when the SPA already mounted the embed iframe.
  function hasNativeAiShell() {
    try {
      return !!document.querySelector('iframe[title="Plane Intelligence"]');
    } catch (_) {
      return false;
    }
  }

  function mountAi(ws, rest) {
    if (hasNativeAiShell()) return;
    const chatQ =
      rest && rest !== "/new" ? `&chat_id=${encodeURIComponent(rest.replace(/^\//, ""))}` : "";
    document.documentElement.innerHTML = "";
    const body = document.createElement("body");
    body.style.cssText = "margin:0;background:#0e0f10";
    const iframe = document.createElement("iframe");
    iframe.src = `/cosmic-pilot/ui?embed=1&workspace=${encodeURIComponent(ws)}${chatQ}`;
    iframe.style.cssText =
      "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
    iframe.title = "Plane Intelligence";
    body.appendChild(iframe);
    document.documentElement.appendChild(body);
    document.title = "AI · Plane Intelligence";
  }

  // --- Full-page Wiki ---
  const wikiMatch = path.match(/^\/([^/]+)\/wiki(\/.*)?$/);
  if (wikiMatch) {
    const ws = wikiMatch[1];
    document.documentElement.innerHTML = "";
    const body = document.createElement("body");
    body.style.cssText = "margin:0;background:#0e0f10";
    const iframe = document.createElement("iframe");
    iframe.src = `/cosmic-pilot/wiki?workspace=${encodeURIComponent(ws)}`;
    iframe.style.cssText = "position:fixed;inset:0;width:100%;height:100%;border:0";
    body.appendChild(iframe);
    document.documentElement.appendChild(body);
    document.title = "Wiki · Plane";
    return;
  }

  // --- AI fallback (when native route missing or still hydrating 404) ---
  const piMatch = path.match(/^\/([^/]+)\/(ai-chat|pi-chat)(\/.*)?$/);
  if (piMatch) {
    // Delay slightly so a correct SPA route can mount first.
    setTimeout(() => {
      if (!hasNativeAiShell()) {
        mountAi(piMatch[1], piMatch[3] || "");
      }
    }, 400);
  }

  // SPA navigations into wiki/ai: reload wiki; for AI try inject if no native shell.
  const _push = history.pushState;
  const _replace = history.replaceState;
  function maybeHandleShellNav() {
    const p = location.pathname || "";
    if (isWikiPath(p)) {
      setTimeout(() => location.reload(), 0);
      return;
    }
    if (isAiPath(p)) {
      setTimeout(() => {
        if (hasNativeAiShell()) return;
        const m = p.match(/^\/([^/]+)\/(ai-chat|pi-chat)(\/.*)?$/);
        if (m) mountAi(m[1], m[3] || "");
      }, 400);
    }
  }
  history.pushState = function () {
    _push.apply(this, arguments);
    maybeHandleShellNav();
  };
  history.replaceState = function () {
    _replace.apply(this, arguments);
    maybeHandleShellNav();
  };
  window.addEventListener("popstate", maybeHandleShellNav);


  // ---- Cosmic fixes: hide tours, soft-fix raw ICU labels ----
  (function cosmicUiFixes() {
    try {
      // Mark product tours dismissed in localStorage (covers SPA variants)
      const keys = [
        "plane.product_tour.completed",
        "plane.tour.completed",
        "is_tour_completed",
        "is_navigation_tour_completed",
        "product_tour_dismissed",
      ];
      keys.forEach((k) => {
        try {
          localStorage.setItem(k, "true");
        } catch (_) {}
      });
    } catch (_) {}

    // Soft-replace raw ICU plural blobs that leak into DOM text nodes
    function fixIcuText(root) {
      try {
        const re = /\{count,\s*plural,\s*one\s*\{([^}]*)\}\s*other\s*\{([^}]*)\}\}/gi;
        const walk = (node) => {
          if (!node) return;
          if (node.nodeType === 3) {
            const v = node.nodeValue;
            if (v && v.indexOf("plural") !== -1) {
              node.nodeValue = v.replace(re, "$2");
            }
            return;
          }
          if (node.nodeType === 1) {
            const tag = (node.tagName || "").toLowerCase();
            if (tag === "script" || tag === "style") return;
            for (let i = 0; i < node.childNodes.length; i++) walk(node.childNodes[i]);
          }
        };
        walk(root || document.body);
      } catch (_) {}
    }

    // Run periodically for first minute after load
    let n = 0;
    const timer = setInterval(() => {
      fixIcuText(document.body);
      if (++n > 30) clearInterval(timer);
    }, 2000);
    document.addEventListener("DOMContentLoaded", () => fixIcuText(document.body));

    // Wiki/theme blank: if main content is empty for 3s on non-auth routes, force light surface
    setTimeout(() => {
      try {
        const main = document.querySelector("main") || document.getElementById("root");
        if (!main) return;
        const text = (main.innerText || "").trim();
        const rect = main.getBoundingClientRect();
        if (text.length < 2 && rect.height > 100) {
          // prevent pure grey void — ensure theme attribute and background
          const d = document.documentElement;
          if (!d.getAttribute("data-theme")) d.setAttribute("data-theme", "dark");
          d.style.background = getComputedStyle(d).backgroundColor || "#0e0f10";
        }
      } catch (_) {}
    }, 3500);
  })();

})();
