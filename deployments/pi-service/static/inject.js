/**
 * Cosmic shell inject — Wiki full-page takeover only.
 *
 * AI is a first-class in-shell route (App Rail stays visible), same layout
 * model as app.plane.so. Do NOT wipe the document for /ai-chat.
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

  // --- Full-page Wiki (CE has no wiki product surface yet) ---
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

  // SPA navigations into wiki need a real reload so the takeover above runs.
  // AI uses native React routes — no reload.
  const _push = history.pushState;
  const _replace = history.replaceState;
  function maybeReloadForWiki() {
    const p = location.pathname || "";
    if (isWikiPath(p)) {
      setTimeout(() => location.reload(), 0);
    }
  }
  history.pushState = function () {
    _push.apply(this, arguments);
    maybeReloadForWiki();
  };
  history.replaceState = function () {
    _replace.apply(this, arguments);
    maybeReloadForWiki();
  };
  window.addEventListener("popstate", maybeReloadForWiki);
})();
