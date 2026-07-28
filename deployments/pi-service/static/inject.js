/**
 * Inject Plane Pilot (floating bot + ai-chat routes) into self-hosted Plane web.
 * Mirrors cloud floating-bot + /{workspace}/ai-chat experience.
 */
(function () {
  if (window.__cosmicPilotInjected) return;
  window.__cosmicPilotInjected = true;

  const path = location.pathname || "";
  // skip auth / god-mode / spaces
  if (
    path.startsWith("/sign-in") ||
    path.startsWith("/sign-up") ||
    path.startsWith("/god-mode") ||
    path.startsWith("/spaces") ||
    path.startsWith("/cosmic-pilot")
  ) {
    return;
  }

  // Full-page Pilot takeover for /{ws}/ai-chat/*
  const m = path.match(/^\/([^/]+)\/(ai-chat|pi-chat)(\/.*)?$/);
  if (m) {
    const ws = m[1];
    const rest = m[3] || "";
    // replace document with pilot shell
    document.documentElement.innerHTML = "";
    const iframe = document.createElement("iframe");
    iframe.src = `/cosmic-pilot/ui?workspace=${encodeURIComponent(ws)}${
      rest && rest !== "/new" ? `&chat_id=${encodeURIComponent(rest.replace(/^\//, ""))}` : ""
    }`;
    iframe.style.cssText = "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
    document.documentElement.appendChild(iframe);
    // ensure body exists
    if (!document.body) {
      document.appendChild(document.createElement("body"));
    }
    document.body.style.margin = "0";
    document.body.appendChild(iframe);
    return;
  }

  // Settings: plane-intelligence page
  if (path.match(/^\/[^/]+\/settings\/plane-intelligence\/?$/)) {
    const ws = path.split("/")[1];
    document.documentElement.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.style.cssText =
      "font-family:Inter,system-ui,sans-serif;max-width:720px;margin:48px auto;padding:24px;color:#e8eaed;background:#0e0f10;min-height:100vh";
    wrap.innerHTML = `
      <h1 style="font-size:24px;margin:0 0 8px">Plane Intelligence</h1>
      <p style="color:#9aa0a6;line-height:1.5;margin:0 0 20px">
        Pilot AI is enabled on this self-hosted instance. Models, skills, chat history, and streaming
        match the Plane cloud Pilot API (<code>pi.plane.so</code> compatible).
      </p>
      <div style="border:1px solid #2a2d31;border-radius:12px;padding:16px;background:#15171a;margin-bottom:16px">
        <div style="font-weight:600;margin-bottom:8px">Status</div>
        <div id="pi-status" style="color:#9aa0a6;font-size:14px">Checking…</div>
      </div>
      <a href="/${ws}/ai-chat/new" style="display:inline-flex;align-items:center;gap:8px;background:#3b82f6;color:white;text-decoration:none;padding:10px 16px;border-radius:10px;font-weight:600">
        Open Pilot →
      </a>
    `;
    document.documentElement.appendChild(document.createElement("body"));
    document.body.style.margin = "0";
    document.body.style.background = "#0e0f10";
    document.body.appendChild(wrap);
    fetch("/api/v1/chat/get-models/", { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        const n = (d.models || []).length;
        document.getElementById("pi-status").textContent = `Connected · ${n} models available · flags AI_CHAT enabled`;
      })
      .catch(() => {
        document.getElementById("pi-status").textContent = "PI service unreachable — check /api/v1/ routing";
      });
    return;
  }

  // Floating Pilot button on app pages
  function mountFab() {
    if (document.getElementById("cosmic-pilot-root")) return;
    // hide on certain routes like cloud floating-bot logic
    if (path.includes("/settings/") || path.includes("/ai-chat") || path.includes("/pi-chat")) return;

    const parts = path.split("/").filter(Boolean);
    const workspace = parts[0] || localStorage.getItem("pilot_workspace") || "";
    if (!workspace || workspace === "api" || workspace === "auth") return;

    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/cosmic-pilot/static/pilot.css";
    document.head.appendChild(css);

    const root = document.createElement("div");
    root.id = "cosmic-pilot-root";
    root.innerHTML = `
      <button id="cosmic-pilot-fab" type="button" title="Pilot" aria-label="Open Pilot">π</button>
      <div id="cosmic-pilot-panel" role="dialog" aria-label="Pilot chat">
        <iframe title="Pilot" src="/cosmic-pilot/ui?embed=1&workspace=${encodeURIComponent(workspace)}"></iframe>
      </div>
    `;
    document.body.appendChild(root);
    const fab = document.getElementById("cosmic-pilot-fab");
    const panel = document.getElementById("cosmic-pilot-panel");
    fab.addEventListener("click", () => {
      panel.classList.toggle("open");
    });
    // keyboard shortcut Cmd/Ctrl+J
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        panel.classList.toggle("open");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountFab);
  } else {
    // SPA may mount late — retry a few times
    mountFab();
    let tries = 0;
    const t = setInterval(() => {
      tries += 1;
      if (document.body) mountFab();
      if (tries > 20) clearInterval(t);
    }, 500);
  }
})();
