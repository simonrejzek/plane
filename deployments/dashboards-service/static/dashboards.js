(function () {
  const pathParts = location.pathname.split("/").filter(Boolean);
  // Paths:
  //   /{ws}/dashboards[/{id}]
  //   /cosmic-dashboards/ui/{ws}/dashboards[/{id}]
  //   /cosmic-dashboards/ui?workspace=
  const qs = new URLSearchParams(location.search);
  let workspaceSlug = qs.get("workspace") || "";
  if (!workspaceSlug && pathParts[0] === "cosmic-dashboards" && pathParts[1] === "ui" && pathParts[2]) {
    workspaceSlug = pathParts[2];
  } else if (!workspaceSlug && pathParts[0] && pathParts[0] !== "cosmic-dashboards") {
    workspaceSlug = pathParts[0];
  }
  workspaceSlug = workspaceSlug || localStorage.getItem("dash_workspace") || "";
  const state = {
    workspaceSlug,
    access: "private",
    dashboards: [],
    dashboardId: null,
    dashboard: null,
    widgets: [],
  };

  const $ = (s) => document.querySelector(s);
  const listView = $("#view-list");
  const detailView = $("#view-detail");
  const grid = $("#dashboard-grid");
  const empty = $("#dashboard-empty");
  const widgetGrid = $("#widget-grid");
  const widgetEmpty = $("#widget-empty");

  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      method: opts.method || "GET",
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
        "X-CSRFToken": csrf(),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`${res.status} ${path}: ${t.slice(0, 200)}`);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function relativeTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "";
    const s = Math.max(1, Math.floor((Date.now() - t) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  function openModal(id) {
    document.getElementById(id).classList.remove("hidden");
  }
  function closeModal(id) {
    document.getElementById(id).classList.add("hidden");
  }

  async function detectWorkspace() {
    if (state.workspaceSlug && state.workspaceSlug !== "cosmic-dashboards") return;
    try {
      const list = await api("/api/users/me/workspaces/");
      if (Array.isArray(list) && list.length) {
        const match = list.find((w) => w.slug === pathParts[0]) || list[0];
        state.workspaceSlug = match.slug;
        localStorage.setItem("dash_workspace", state.workspaceSlug);
      }
    } catch (_) {}
  }

  function showList() {
    listView.classList.remove("hidden");
    detailView.classList.add("hidden");
    state.dashboardId = null;
    if (state.workspaceSlug) {
      history.replaceState({}, "", `/${state.workspaceSlug}/dashboards/`);
    }
  }

  function showDetail() {
    listView.classList.add("hidden");
    detailView.classList.remove("hidden");
  }

  async function loadList() {
    await detectWorkspace();
    if (!state.workspaceSlug) {
      empty.classList.remove("hidden");
      empty.querySelector("p").textContent = "Could not detect workspace. Open from a workspace URL.";
      return;
    }
    const data = await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/?access=${encodeURIComponent(state.access)}`
    );
    state.dashboards = data.results || [];
    renderList();
  }

  function renderList() {
    if (!state.dashboards.length) {
      grid.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    grid.innerHTML = state.dashboards
      .map(
        (d) => `
      <button type="button" class="dash-card" data-id="${d.id}">
        <h3>${escapeHtml(d.name || "Untitled")}</h3>
        <div class="meta">
          <span>${d.access === 1 ? "Public" : "Private"}</span>
          <span>${relativeTime(d.updated_at || d.created_at)}</span>
        </div>
      </button>`
      )
      .join("");
    grid.querySelectorAll(".dash-card").forEach((btn) => {
      btn.onclick = () => openDashboard(btn.dataset.id);
    });
  }

  async function openDashboard(id) {
    state.dashboardId = id;
    state.dashboard = await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(id)}/`
    );
    state.widgets = await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(id)}/widgets/`
    );
    $("#detail-title").textContent = state.dashboard.name || "Dashboard";
    $("#detail-access").textContent = state.dashboard.access === 1 ? "Public" : "Private";
    renderWidgets();
    showDetail();
    history.replaceState({}, "", `/${state.workspaceSlug}/dashboards/${id}`);
  }

  function renderWidgets() {
    if (!state.widgets.length) {
      widgetGrid.innerHTML = "";
      widgetEmpty.classList.remove("hidden");
      return;
    }
    widgetEmpty.classList.add("hidden");
    widgetGrid.innerHTML = state.widgets
      .map((w) => {
        const span = Math.min(4, Math.max(1, w.width || 1));
        return `
        <article class="widget-card w${span}" data-id="${w.id}">
          <div class="widget-head">
            <h3>${escapeHtml(w.name || "Widget")}</h3>
            <div style="display:flex;gap:6px;align-items:center">
              <span class="widget-type">${escapeHtml(w.chart_type || "")}</span>
              <button type="button" class="btn ghost" data-del="${w.id}" style="height:28px;padding:0 8px">Delete</button>
            </div>
          </div>
          <div class="widget-body" id="wb-${w.id}">Loading…</div>
        </article>`;
      })
      .join("");
    widgetGrid.querySelectorAll("[data-del]").forEach((btn) => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("Delete widget?")) return;
        await api(
          `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(
            state.dashboardId
          )}/widgets/${encodeURIComponent(btn.dataset.del)}/`,
          { method: "DELETE" }
        );
        await openDashboard(state.dashboardId);
      };
    });
    state.widgets.forEach((w) => hydrateWidget(w));
  }

  async function hydrateWidget(w) {
    const el = document.getElementById(`wb-${w.id}`);
    if (!el) return;
    try {
      const full = await api(
        `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(
          state.dashboardId
        )}/widgets/${encodeURIComponent(w.id)}/`
      );
      const data = full.data || {};
      if (w.chart_type === "NUMBER") {
        el.innerHTML = `<div class="number-value">${escapeHtml(data.value ?? 0)}</div>`;
      } else if (
        ["BAR_CHART", "LINE_CHART", "AREA_CHART", "PIE_CHART", "DONUT_CHART"].includes(w.chart_type)
      ) {
        const vals = (data.datasets && data.datasets[0] && data.datasets[0].data) || [1, 2, 3, 4];
        const max = Math.max(...vals, 1);
        el.innerHTML = `<div class="chart-bars">${vals
          .map((v) => `<div class="bar" style="height:${Math.round((v / max) * 100)}%"></div>`)
          .join("")}</div>`;
      } else if (w.chart_type === "WORK_ITEMS_STATISTICS") {
        el.innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;width:100%;font-size:12px">
          <div><div class="widget-type">Total</div><strong>${data.total ?? 0}</strong></div>
          <div><div class="widget-type">Completed</div><strong>${data.completed ?? 0}</strong></div>
          <div><div class="widget-type">Pending</div><strong>${data.pending ?? 0}</strong></div>
          <div><div class="widget-type">Overdue</div><strong>${data.overdue ?? 0}</strong></div>
        </div>`;
      } else {
        const cols = data.columns || ["Key", "Title", "State"];
        el.innerHTML = `<table class="table-mini"><thead><tr>${cols
          .map((c) => `<th>${escapeHtml(c)}</th>`)
          .join("")}</tr></thead><tbody><tr><td colspan="${cols.length}" style="color:var(--text-subtle)">No rows</td></tr></tbody></table>`;
      }
    } catch (e) {
      el.textContent = "Failed to load";
    }
  }

  // events
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      state.access = tab.dataset.access;
      loadList().catch((e) => alert(e.message));
    };
  });

  $("#btn-create-dashboard").onclick = $("#btn-create-empty").onclick = () => {
    $("#input-dash-name").value = "";
    openModal("modal-dashboard");
  };
  $("#btn-dash-save").onclick = async () => {
    const name = $("#input-dash-name").value.trim();
    if (!name) return alert("Name required");
    const access = Number($("#input-dash-access").value);
    const created = await api(`/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/`, {
      method: "POST",
      body: { name, access },
    });
    closeModal("modal-dashboard");
    await openDashboard(created.id);
  };

  $("#btn-back").onclick = async () => {
    showList();
    await loadList();
  };
  $("#btn-rename").onclick = async () => {
    const name = prompt("Rename dashboard", state.dashboard?.name || "");
    if (!name) return;
    await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(state.dashboardId)}/`,
      { method: "PATCH", body: { name } }
    );
    await openDashboard(state.dashboardId);
  };
  $("#btn-delete").onclick = async () => {
    if (!confirm("Delete this dashboard?")) return;
    await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(state.dashboardId)}/`,
      { method: "DELETE" }
    );
    showList();
    await loadList();
  };
  $("#btn-add-widget").onclick = $("#btn-add-widget-empty").onclick = () => {
    $("#input-widget-name").value = "";
    openModal("modal-widget");
  };
  $("#btn-widget-save").onclick = async () => {
    const name = $("#input-widget-name").value.trim() || "Widget";
    const chart_type = $("#input-widget-type").value;
    const chart_model = $("#input-widget-model").value;
    await api(
      `/api/workspaces/${encodeURIComponent(state.workspaceSlug)}/dashboards/${encodeURIComponent(
        state.dashboardId
      )}/widgets/`,
      { method: "POST", body: { name, chart_type, chart_model } }
    );
    closeModal("modal-widget");
    await openDashboard(state.dashboardId);
  };

  document.querySelectorAll("[data-close]").forEach((btn) => {
    btn.onclick = () => closeModal(btn.dataset.close);
  });
  document.querySelectorAll(".modal").forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.classList.add("hidden");
    });
  });

  // theme
  try {
    const theme = localStorage.getItem("theme") || "system";
    const dark =
      theme.includes("dark") ||
      (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  } catch (_) {
    document.documentElement.setAttribute("data-theme", "dark");
  }

  // boot from URL
  (async () => {
    await detectWorkspace();
    const idx = pathParts.indexOf("dashboards");
    const idFromPath = idx >= 0 ? pathParts[idx + 1] : null;
    const idFromQuery = qs.get("id");
    const id = idFromPath || idFromQuery;
    if (id && id !== "private" && id !== "public" && id !== "shared" && id !== "new") {
      await openDashboard(id);
    } else {
      showList();
      await loadList();
    }
  })().catch((e) => {
    console.error(e);
    alert(e.message || e);
  });
})();
