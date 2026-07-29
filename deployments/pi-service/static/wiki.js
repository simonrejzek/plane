/* Workspace Wiki — uses /api/workspaces/{slug}/pages/ like app.plane.so */
(function () {
  const qs = new URLSearchParams(location.search);
  const parts = location.pathname.split("/").filter(Boolean);
  let workspace =
    qs.get("workspace") ||
    (parts[0] && parts[0] !== "cosmic-pilot" && parts[0] !== "wiki" ? parts[0] : "") ||
    localStorage.getItem("wiki_workspace") ||
    "";
  localStorage.setItem("wiki_workspace", workspace);

  const state = { pages: [], activeId: null, dirty: false };

  const $ = (s) => document.querySelector(s);
  const listEl = $("#page-list");
  const emptyEl = $("#empty-state");
  const editorEl = $("#editor");
  const titleEl = $("#page-title");
  const bodyEl = $("#page-body");
  const metaEl = $("#page-meta");

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
      throw new Error(`${res.status}: ${t.slice(0, 200)}`);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  function fmtDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  function renderList(filter = "") {
    const q = filter.trim().toLowerCase();
    const pages = state.pages.filter((p) => !q || (p.name || "").toLowerCase().includes(q));
    listEl.innerHTML = pages
      .map(
        (p) => `
      <button type="button" class="page-item ${p.id === state.activeId ? "active" : ""}" data-id="${p.id}">
        ${escapeHtml(p.name || "Untitled")}
        <span class="muted">${fmtDate(p.updated_at)}</span>
      </button>`
      )
      .join("");
    listEl.querySelectorAll(".page-item").forEach((btn) => {
      btn.addEventListener("click", () => openPage(btn.getAttribute("data-id")));
    });
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadPages() {
    if (!workspace) {
      listEl.innerHTML = `<div style="padding:12px;color:#9aa0a6;font-size:13px">Missing workspace slug</div>`;
      return;
    }
    const data = await api(`/api/workspaces/${encodeURIComponent(workspace)}/pages/`);
    const results = Array.isArray(data) ? data : data?.results || [];
    state.pages = results;
    renderList($("#wiki-search").value || "");
    if (!results.length) {
      emptyEl.classList.remove("hidden");
      editorEl.classList.add("hidden");
    } else if (!state.activeId) {
      openPage(results[0].id);
    }
  }

  async function openPage(id) {
    if (state.dirty && !confirm("Discard unsaved changes?")) return;
    const page = await api(`/api/workspaces/${encodeURIComponent(workspace)}/pages/${id}/`);
    state.activeId = id;
    state.dirty = false;
    emptyEl.classList.add("hidden");
    emptyEl.style.display = "none";
    editorEl.classList.remove("hidden");
    titleEl.value = page.name || "";
    // description_html or description may exist; fall back empty
    bodyEl.value =
      page.description_html?.replace(/<[^>]+>/g, "") ||
      page.description ||
      page.description_stripped ||
      "";
    metaEl.textContent = `Updated ${fmtDate(page.updated_at)} · id ${page.id}`;
    renderList($("#wiki-search").value || "");
  }

  async function createPage() {
    const name = prompt("Page title", "Untitled") || "Untitled";
    const page = await api(`/api/workspaces/${encodeURIComponent(workspace)}/pages/`, {
      method: "POST",
      body: { name },
    });
    await loadPages();
    if (page?.id) openPage(page.id);
  }

  async function savePage() {
    if (!state.activeId) return;
    const body = {
      name: titleEl.value || "Untitled",
      description_html: `<p>${escapeHtml(bodyEl.value).replace(/\n/g, "<br>")}</p>`,
      description: bodyEl.value,
    };
    await api(`/api/workspaces/${encodeURIComponent(workspace)}/pages/${state.activeId}/`, {
      method: "PATCH",
      body,
    });
    state.dirty = false;
    metaEl.textContent = `Saved · ${new Date().toLocaleTimeString()}`;
    await loadPages();
  }

  async function deletePage() {
    if (!state.activeId) return;
    if (!confirm("Delete this page?")) return;
    await api(`/api/workspaces/${encodeURIComponent(workspace)}/pages/${state.activeId}/`, {
      method: "DELETE",
    });
    state.activeId = null;
    state.dirty = false;
    await loadPages();
    if (state.pages[0]) openPage(state.pages[0].id);
    else {
      editorEl.classList.add("hidden");
      emptyEl.style.display = "";
      emptyEl.classList.remove("hidden");
    }
  }

  $("#new-page-btn").addEventListener("click", () => createPage().catch(alert));
  $("#empty-new-btn").addEventListener("click", () => createPage().catch(alert));
  $("#save-btn").addEventListener("click", () => savePage().catch(alert));
  $("#delete-btn").addEventListener("click", () => deletePage().catch(alert));
  $("#wiki-search").addEventListener("input", (e) => renderList(e.target.value));
  titleEl.addEventListener("input", () => (state.dirty = true));
  bodyEl.addEventListener("input", () => (state.dirty = true));

  loadPages().catch((e) => {
    listEl.innerHTML = `<div style="padding:12px;color:#f87171;font-size:13px">${escapeHtml(
      e.message
    )}<br><br>Workspace pages API may be unavailable on this CE backend. Wiki still opens; create/list needs workspace pages support.</div>`;
  });
})();
