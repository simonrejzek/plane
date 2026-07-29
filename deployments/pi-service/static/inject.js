/**
 * Cosmic shell inject — full-page Wiki + Pilot AI only.
 * Does not patch the project App Rail (rail is built into web: Projects / Wiki / AI).
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

  // --- Full-page Pilot ---
  const piMatch = path.match(/^\/([^/]+)\/(ai-chat|pi-chat)(\/.*)?$/);
  if (piMatch) {
    const ws = piMatch[1];
    const rest = piMatch[3] || "";
    const chatQ =
      rest && rest !== "/new" ? `&chat_id=${encodeURIComponent(rest.replace(/^\//, ""))}` : "";
    document.documentElement.innerHTML = "";
    const body = document.createElement("body");
    body.style.cssText = "margin:0;background:#0e0f10";
    const iframe = document.createElement("iframe");
    iframe.src = `/cosmic-pilot/ui?workspace=${encodeURIComponent(ws)}${chatQ}`;
    iframe.style.cssText =
      "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
    body.appendChild(iframe);
    document.documentElement.appendChild(body);
    document.title = "AI · Plane Intelligence";
    return;
  }

  // SPA navigations into wiki/ai need a real reload so the takeover above runs.
  const _push = history.pushState;
  const _replace = history.replaceState;
  function maybeReloadForShell() {
    const p = location.pathname || "";
    if (isWikiPath(p) || isAiPath(p)) {
      setTimeout(() => location.reload(), 0);
    }
  }
  history.pushState = function () {
    _push.apply(this, arguments);
    maybeReloadForShell();
  };
  history.replaceState = function () {
    _replace.apply(this, arguments);
    maybeReloadForShell();
  };
  window.addEventListener("popstate", maybeReloadForShell);
})();
