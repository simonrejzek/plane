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
    iframe.style.cssText = "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
    body.appendChild(iframe);
    document.documentElement.appendChild(body);
    document.title = "AI · Plane Intelligence";
    return;
  }

  function workspaceSlug() {
    return (path.split("/").filter(Boolean)[0] || "").trim();
  }

  function hideNode(node) {
    if (!node || !node.style) return;
    node.style.display = "none";
    node.setAttribute("data-cosmic-hidden", "1");
  }

  function isDashboardsLink(a) {
    const href = (a.getAttribute("href") || "").toLowerCase();
    const label = (a.textContent || "").trim().toLowerCase();
    const title = (a.getAttribute("title") || "").toLowerCase();
    const aria = (a.getAttribute("aria-label") || "").toLowerCase();
    return (
      href.includes("/dashboards") ||
      label === "dashboards" ||
      label === "dashboard" ||
      title === "dashboards" ||
      aria === "dashboards"
    );
  }

  function findRail() {
    return (
      document.querySelector("[class*='app-rail']") ||
      document.querySelector("[class*='AppRail']") ||
      document.querySelector("aside nav") ||
      document.querySelector("nav") ||
      null
    );
  }

  function ensureDockLink(rail, slug, href, title, glyph, bg, color) {
    const existing = Array.from(document.querySelectorAll("a[href]")).some((a) =>
      (a.getAttribute("href") || "").includes(href.replace(/\/$/, ""))
    );
    if (existing) return;
    let wrap = document.getElementById("cosmic-dock-extra");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "cosmic-dock-extra";
      wrap.style.cssText =
        "display:flex;flex-direction:column;gap:6px;padding:8px 0;align-items:center";
      rail.appendChild(wrap);
    }
    if (wrap.querySelector(`a[data-cosmic-dock="${title}"]`)) return;
    const a = document.createElement("a");
    a.href = href;
    a.title = title;
    a.setAttribute("data-cosmic-dock", title);
    a.setAttribute("aria-label", title);
    a.textContent = glyph;
    a.style.cssText = `width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:${bg};color:${color};text-decoration:none;font-weight:700;font-size:13px;margin:2px 0`;
    wrap.appendChild(a);
  }

  // --- Patch app rail dock: remove Dashboards, ensure Wiki + AI ---
  function patchDock() {
    try {
      const slug = workspaceSlug();
      if (!slug || slug === "api" || slug === "auth") return;

      const links = Array.from(document.querySelectorAll("a[href], button"));
      links.forEach((el) => {
        if (el.tagName === "A" && isDashboardsLink(el)) {
          // climb to dock item container
          let p = el;
          for (let i = 0; i < 6 && p; i++) {
            const text = (p.textContent || "").trim().toLowerCase();
            if (text === "dashboards" || text === "dashboard" || (p.getAttribute("href") || "").includes("/dashboards")) {
              hideNode(p);
            }
            p = p.parentElement;
          }
          hideNode(el);
        }
        // also hide pure label nodes
        if ((el.textContent || "").trim().toLowerCase() === "dashboards") {
          const item = el.closest("a, button, [role='link'], li, div");
          if (item) hideNode(item);
        }
      });

      const rail = findRail();
      if (!rail) return;
      ensureDockLink(rail, slug, `/${slug}/wiki/`, "Wiki", "W", "#1e1b4b", "#c4b5fd");
      ensureDockLink(rail, slug, `/${slug}/pi-chat/`, "AI", "π", "#172554", "#93c5fd");
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
    if (tries > 40) clearInterval(t);
  }, 400);

  // SPA route changes — reload so wiki/ai full-page takeovers apply
  const _push = history.pushState;
  const _replace = history.replaceState;
  function onRoute() {
    const p = location.pathname || "";
    if (/\/[^/]+\/(wiki|pi-chat|ai-chat)(\/|$)/.test(p)) {
      setTimeout(() => location.reload(), 0);
    } else {
      setTimeout(boot, 50);
    }
  }
  history.pushState = function () {
    _push.apply(this, arguments);
    onRoute();
  };
  history.replaceState = function () {
    _replace.apply(this, arguments);
    onRoute();
  };
  window.addEventListener("popstate", onRoute);
})();
