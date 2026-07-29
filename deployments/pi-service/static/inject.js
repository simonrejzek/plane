/**
 * Cosmic Plane shell inject:
 * - Full-page Wiki at /{ws}/wiki
 * - Full-page Pilot AI at /{ws}/pi-chat and /{ws}/ai-chat
 * - App rail dock: Projects, Wiki, AI (remove Dashboards)
 * - Floating Pilot FAB
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
    iframe.style.cssText = "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
    body.appendChild(iframe);
    document.documentElement.appendChild(body);
    return;
  }

  // --- Patch app rail dock: remove Dashboards, ensure Wiki + AI ---
  function patchDock() {
    try {
      const links = Array.from(document.querySelectorAll("a[href]"));
      const slug = (path.split("/").filter(Boolean)[0] || "").trim();
      if (!slug) return;

      // Hide dashboards dock entries
      links.forEach((a) => {
        const href = a.getAttribute("href") || "";
        const label = (a.textContent || "").trim().toLowerCase();
        if (href.includes(`/${slug}/dashboards`) || label === "dashboards") {
          const item = a.closest("[class*='rail'], [class*='dock'], button, a") || a;
          if (item && item.style) item.style.display = "none";
          // also hide parent list item
          let p = a.parentElement;
          for (let i = 0; i < 4 && p; i++) {
            if (p.querySelectorAll("a").length <= 2) {
              p.style.display = "none";
              break;
            }
            p = p.parentElement;
          }
        }
      });

      // Inject Wiki / AI dock chips if missing (best-effort visual parity)
      const hasWiki = links.some((a) => (a.getAttribute("href") || "").includes(`/${slug}/wiki`));
      const hasAi = links.some(
        (a) =>
          (a.getAttribute("href") || "").includes(`/${slug}/pi-chat`) ||
          (a.getAttribute("href") || "").includes(`/${slug}/ai-chat`)
      );
      if (hasWiki && hasAi) return;

      // Find a vertical rail-ish container near left edge
      let rail =
        document.querySelector("[class*='app-rail']") ||
        document.querySelector("[class*='AppRail']") ||
        document.querySelector("nav");
      if (!rail) return;
      if (!document.getElementById("cosmic-dock-extra")) {
        const wrap = document.createElement("div");
        wrap.id = "cosmic-dock-extra";
        wrap.style.cssText =
          "display:flex;flex-direction:column;gap:6px;padding:8px;align-items:center";
        if (!hasWiki) {
          const a = document.createElement("a");
          a.href = `/${slug}/wiki/`;
          a.title = "Wiki";
          a.textContent = "W";
          a.style.cssText =
            "width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:#1e1b4b;color:#c4b5fd;text-decoration:none;font-weight:700;font-size:13px";
          wrap.appendChild(a);
        }
        if (!hasAi) {
          const a = document.createElement("a");
          a.href = `/${slug}/pi-chat/`;
          a.title = "AI / Pilot";
          a.textContent = "π";
          a.style.cssText =
            "width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:#172554;color:#93c5fd;text-decoration:none;font-weight:700;font-size:16px";
          wrap.appendChild(a);
        }
        rail.appendChild(wrap);
      }
    } catch (_) {}
  }

  // --- Floating Pilot FAB ---
  function mountFab() {
    if (document.getElementById("cosmic-pilot-root")) return;
    if (path.includes("/settings/") || path.includes("/ai-chat") || path.includes("/pi-chat") || path.includes("/wiki"))
      return;

    const parts = path.split("/").filter(Boolean);
    const workspace = parts[0] || localStorage.getItem("pilot_workspace") || "";
    if (!workspace || workspace === "api" || workspace === "auth") return;

    if (!document.querySelector('link[href="/cosmic-pilot/static/pilot.css"]')) {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "/cosmic-pilot/static/pilot.css";
      document.head.appendChild(css);
    }

    const root = document.createElement("div");
    root.id = "cosmic-pilot-root";
    root.innerHTML = `
      <button id="cosmic-pilot-fab" type="button" title="Pilot" aria-label="Open Pilot">π</button>
      <div id="cosmic-pilot-panel" role="dialog" aria-label="Pilot chat">
        <iframe title="Pilot" src="/cosmic-pilot/ui?embed=1&workspace=${encodeURIComponent(
          workspace
        )}"></iframe>
      </div>
    `;
    document.body.appendChild(root);
    const fab = document.getElementById("cosmic-pilot-fab");
    const panel = document.getElementById("cosmic-pilot-panel");
    fab.addEventListener("click", () => panel.classList.toggle("open"));
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        panel.classList.toggle("open");
      }
    });
  }

  function boot() {
    patchDock();
    mountFab();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  let tries = 0;
  const t = setInterval(() => {
    tries += 1;
    if (document.body) boot();
    if (tries > 30) clearInterval(t);
  }, 500);

  // SPA route changes
  const _push = history.pushState;
  history.pushState = function () {
    _push.apply(this, arguments);
    setTimeout(() => location.reload(), 0); // ensure full-page wiki/ai takeovers
  };
})();
