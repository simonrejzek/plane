/**
 * Route Plane workspace /dashboards/* to the cloud-parity Dashboards UI shell.
 * Does not load Pilot / Plane AI.
 */
(function () {
  if (window.__cosmicDashboardsInjected) return;
  window.__cosmicDashboardsInjected = true;

  const path = location.pathname || "";
  const m = path.match(/^\/([^/]+)\/dashboards(\/.*)?$/);
  if (!m) return;

  const ws = m[1];
  const rest = (m[2] || "").replace(/^\//, "");
  // Don't hijack if already on cosmic shell
  if (path.startsWith("/cosmic-dashboards")) return;

  document.documentElement.innerHTML = "";
  const iframe = document.createElement("iframe");
  iframe.title = "Dashboards";
  iframe.src =
    `/cosmic-dashboards/ui?workspace=${encodeURIComponent(ws)}` +
    (rest && !["private", "public", "shared"].includes(rest.split("/")[0])
      ? `&id=${encodeURIComponent(rest.split("/")[0])}`
      : "");
  // if id in path, dashboards.js also reads path when not embed - use full path iframe
  iframe.src = `/cosmic-dashboards/ui/${ws}/dashboards/${rest}`.replace(/\/$/, "/");
  // Prefer path-based so dashboards.js path parser works: rewrite iframe to same origin path via history...
  // Use dedicated path that includes workspace:
  iframe.src = `/cosmic-dashboards/ui?workspace=${encodeURIComponent(ws)}${
    rest && !["private", "public", "shared", "new"].includes(rest.split("/")[0])
      ? ``
      : ``
  }`;

  // Best: navigate iframe to a path the SPA understands by using replace on load
  // Load UI then set location inside - simpler: use src with path under UI route that FastAPI still serves index
  const dashId =
    rest && !["private", "public", "shared", "new"].includes(rest.split("/")[0]) ? rest.split("/")[0] : "";
  iframe.src = dashId
    ? `/cosmic-dashboards/ui/${encodeURIComponent(ws)}/dashboards/${encodeURIComponent(dashId)}`
    : `/cosmic-dashboards/ui/${encodeURIComponent(ws)}/dashboards/`;

  iframe.style.cssText = "position:fixed;inset:0;width:100%;height:100%;border:0;background:#0e0f10";
  if (!document.body) document.appendChild(document.createElement("body"));
  document.body.style.margin = "0";
  document.body.appendChild(iframe);
})();
