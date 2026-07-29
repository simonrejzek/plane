/* Plane Intelligence Pilot client — API-compatible with pi.plane.so */
(function () {
  const qs = new URLSearchParams(location.search);
  const pathParts = location.pathname.split("/").filter(Boolean);
  const isEmbed = qs.get("embed") === "1" || window.parent !== window;
  // /{workspace}/ai-chat[/...] or /cosmic-pilot/ui
  let workspaceSlug =
    qs.get("workspace") ||
    (pathParts[0] && pathParts[0] !== "cosmic-pilot" && pathParts[0] !== "ai-chat"
      ? pathParts[0]
      : null) ||
    localStorage.getItem("pilot_workspace") ||
    "";
  const PI_BASE = window.PI_BASE_URL || ""; // same-origin /api/v1 via proxy
  const state = {
    workspaceSlug,
    workspaceId: qs.get("workspace_id") || localStorage.getItem("pilot_workspace_id") || "",
    chatId: qs.get("chat_id") || null,
    mode: localStorage.getItem("pilot_mode") || "ask",
    llm: localStorage.getItem("pilot_llm") || "",
    models: [],
    threads: [],
    favorites: [],
    skills: [],
    prompts: [],
    messages: [],
    streaming: false,
    websearch: false,
    skillId: null,
    user: null,
  };

  function notifyParent(payload) {
    if (!isEmbed) return;
    try {
      window.parent.postMessage({ source: "plane-pilot", ...payload }, window.location.origin);
    } catch (_) {}
  }

  function syncShellPath(chatId, opts) {
    if (!state.workspaceSlug) return;
    const path =
      chatId && chatId !== "new"
        ? `/${state.workspaceSlug}/ai-chat/${chatId}`
        : `/${state.workspaceSlug}/ai-chat/`;
    if (isEmbed) {
      notifyParent({ type: "navigate", path, replace: !!(opts && opts.replace) });
      return;
    }
    history.replaceState({}, "", path);
  }

  const $ = (sel) => document.querySelector(sel);
  const el = {
    app: $("#app"),
    threads: $("#thread-list"),
    favorites: $("#favorite-list"),
    messages: $("#messages-inner"),
    title: $("#chat-title"),
    model: $("#model-select"),
    input: $("#composer-input"),
    send: $("#send-btn"),
    newChat: $("#new-chat-btn"),
    modeTabs: document.querySelectorAll(".mode-tab"),
    skills: $("#skills-row"),
    websearch: $("#websearch-btn"),
    favBtn: $("#favorite-btn"),
    renameBtn: $("#rename-btn"),
    deleteBtn: $("#delete-btn"),
    sidebar: $("#sidebar"),
    menuBtn: $("#menu-btn"),
  };

  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function api(path, opts = {}) {
    const url = `${PI_BASE}${path}`;
    const headers = {
      Accept: "application/json",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
      "X-CSRFToken": csrf(),
      ...(opts.headers || {}),
    };
    const res = await fetch(url, {
      method: opts.method || "GET",
      headers,
      credentials: "include",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${path}: ${text.slice(0, 200)}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderMarkdownLite(text) {
    // minimal markdown: code fences, inline code, bold, links, newlines
    let html = escapeHtml(text);
    html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code}</code></pre>`);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    html = html.replace(/\n/g, "<br>");
    return html;
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

  function setMode(mode) {
    state.mode = mode;
    localStorage.setItem("pilot_mode", mode);
    el.modeTabs.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }

  function renderThreads() {
    const favIds = new Set((state.favorites || []).map((f) => f.chat_id));
    el.favorites.innerHTML = (state.favorites || [])
      .map(
        (t) => `
      <button class="thread-item ${t.chat_id === state.chatId ? "active" : ""}" data-id="${t.chat_id}">
        <div class="thread-title">★ ${escapeHtml(t.title || "New Conversation")}</div>
        <div class="thread-meta"><span>${relativeTime(t.last_modified)}</span></div>
      </button>`
      )
      .join("") || `<div class="section-label" style="opacity:.7;text-transform:none;letter-spacing:0">No favorites</div>`;

    el.threads.innerHTML = (state.threads || [])
      .filter((t) => !favIds.has(t.chat_id))
      .map(
        (t) => `
      <button class="thread-item ${t.chat_id === state.chatId ? "active" : ""}" data-id="${t.chat_id}">
        <div class="thread-title">${escapeHtml(t.title || "New Conversation")}</div>
        <div class="thread-meta">
          <span>${escapeHtml(t.mode || "ask")}</span>
          <span>${relativeTime(t.last_modified)}</span>
        </div>
      </button>`
      )
      .join("") || `<div class="section-label" style="opacity:.7;text-transform:none;letter-spacing:0">No chats yet</div>`;

    el.threads.querySelectorAll(".thread-item").forEach((btn) => {
      btn.onclick = () => openChat(btn.dataset.id);
    });
    el.favorites.querySelectorAll(".thread-item").forEach((btn) => {
      btn.onclick = () => openChat(btn.dataset.id);
    });
  }

  function renderSkills() {
    el.skills.innerHTML = (state.skills || [])
      .slice(0, 12)
      .map(
        (s) =>
          `<button class="skill-chip ${state.skillId === s.id ? "active" : ""}" data-id="${s.id}" data-slug="${escapeHtml(
            s.slug || ""
          )}" title="${escapeHtml(s.description || "")}">${escapeHtml(s.slug || s.name || "skill")}</button>`
      )
      .join("");
    el.skills.querySelectorAll(".skill-chip").forEach((btn) => {
      btn.onclick = () => {
        state.skillId = state.skillId === btn.dataset.id ? null : btn.dataset.id;
        const skill = state.skills.find((s) => s.id === state.skillId);
        if (skill && skill.instructions) {
          el.input.value = skill.instructions.split("\n")[0];
          el.input.focus();
        }
        renderSkills();
      };
    });
  }

  function renderMessages() {
    if (!state.messages.length) {
      el.messages.innerHTML = `
        <div class="empty">
          <h1>How can I help?</h1>
          <p>Ask questions, draft plans, and work across your workspace.</p>
          <div class="prompt-grid">
            ${(state.prompts.length
              ? state.prompts
              : [
                  { text: "Show me my urgent work items that are still pending" },
                  { text: "What work items are assigned to me that are blocked, and which ones are blocking them?" },
                  { text: "Show me recent activity on my pending work items" },
                ]
            )
              .map((p) => `<button class="prompt-card" data-q="${escapeHtml(p.text)}">${escapeHtml(p.text)}</button>`)
              .join("")}
          </div>
        </div>`;
      el.messages.querySelectorAll(".prompt-card").forEach((btn) => {
        btn.onclick = () => {
          el.input.value = btn.dataset.q;
          sendMessage();
        };
      });
      el.title.textContent = "New Conversation";
      return;
    }

    el.messages.innerHTML = state.messages
      .map((m) => {
        const isUser = m.role === "user";
        const reasoning =
          m.reasoning && m.reasoning.length
            ? `<details class="reasoning" ${m.thinking ? "open" : ""}>
                <summary>${m.thinking ? "Thinking…" : "Reasoning"}</summary>
                <div class="reasoning-body">${escapeHtml(
                  m.reasoning.map((r) => r.header || r.content || "").join("")
                )}</div>
              </details>`
            : m.thinking
              ? `<div class="thinking-dot"><span></span><span></span><span></span> Thinking…</div>`
              : "";
        return `
        <div class="msg">
          <div class="avatar ${isUser ? "user" : "assistant"}">${isUser ? "U" : "π"}</div>
          <div class="msg-body">
            <div class="msg-role">${isUser ? "You" : "Pilot"}</div>
            ${reasoning}
            <div class="msg-content">${isUser ? escapeHtml(m.content).replace(/\n/g, "<br>") : renderMarkdownLite(m.content || "")}</div>
          </div>
        </div>`;
      })
      .join("");
    const scroller = $(".messages");
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  async function detectWorkspace() {
    if (state.workspaceSlug && state.workspaceId) return;
    try {
      const meWs = await fetch("/api/users/me/workspaces/", {
        credentials: "include",
        headers: { Accept: "application/json", "X-CSRFToken": csrf() },
      });
      if (meWs.ok) {
        const list = await meWs.json();
        if (Array.isArray(list) && list.length) {
          const match =
            list.find((w) => w.slug === state.workspaceSlug) ||
            list.find((w) => w.slug === pathParts[0]) ||
            list[0];
          state.workspaceSlug = match.slug;
          state.workspaceId = match.id;
          localStorage.setItem("pilot_workspace", state.workspaceSlug);
          localStorage.setItem("pilot_workspace_id", state.workspaceId);
        }
      }
    } catch (_) {}
    // try user
    try {
      const me = await fetch("/api/users/me/", {
        credentials: "include",
        headers: { Accept: "application/json", "X-CSRFToken": csrf() },
      });
      if (me.ok) state.user = await me.json();
    } catch (_) {}
  }

  async function loadBootstrap() {
    await detectWorkspace();
    const slugQ = state.workspaceSlug ? `?workspace_slug=${encodeURIComponent(state.workspaceSlug)}` : "";
    const idQ = state.workspaceId ? `${slugQ ? "&" : "?"}workspace_id=${encodeURIComponent(state.workspaceId)}` : "";
    try {
      const models = await api(`/api/v1/chat/get-models/`);
      state.models = models.models || models || [];
      el.model.innerHTML = state.models
        .map((m) => `<option value="${escapeHtml(m.id)}" ${m.is_default ? "selected" : ""}>${escapeHtml(m.name || m.id)}</option>`)
        .join("");
      if (!state.llm) {
        const def = state.models.find((m) => m.is_default) || state.models[0];
        state.llm = def ? def.id : "";
      }
      if (state.llm) el.model.value = state.llm;
    } catch (e) {
      console.warn("models", e);
    }

    try {
      const threads = await api(
        `/api/v1/chat/get-user-threads/?workspace_slug=${encodeURIComponent(state.workspaceSlug || "")}&workspace_id=${encodeURIComponent(
          state.workspaceId || ""
        )}`
      );
      state.threads = threads.results || [];
    } catch (e) {
      console.warn("threads", e);
    }

    try {
      const favs = await api(
        `/api/v1/chat/get-favorite-chats/?workspace_id=${encodeURIComponent(state.workspaceId || "")}`
      );
      state.favorites = Array.isArray(favs) ? favs : favs.results || [];
    } catch (_) {
      state.favorites = [];
    }

    try {
      const skills = await api(`/api/v1/skills/?workspace_slug=${encodeURIComponent(state.workspaceSlug || "")}`);
      state.skills = skills.items || [];
    } catch (_) {
      state.skills = [];
    }

    try {
      if (state.workspaceId) {
        const prompts = await api(`/api/v1/chat/start/set-prompts/`, {
          method: "POST",
          body: { workspace_id: state.workspaceId, workspace_slug: state.workspaceSlug, mode: state.mode },
        });
        state.prompts = prompts.templates || prompts.prompts || [];
      }
    } catch (_) {}

    renderThreads();
    renderSkills();
    renderMessages();

    // open chat from path /{ws}/ai-chat/{id}
    const chatIdx = pathParts.indexOf("ai-chat");
    if (chatIdx >= 0 && pathParts[chatIdx + 1] && pathParts[chatIdx + 1] !== "new") {
      await openChat(pathParts[chatIdx + 1]);
    } else if (state.chatId) {
      await openChat(state.chatId);
    }
  }

  async function openChat(chatId) {
    state.chatId = chatId;
    try {
      const hist = await api(
        `/api/v1/chat/get-chat-history-object/?chat_id=${encodeURIComponent(chatId)}&workspace_id=${encodeURIComponent(
          state.workspaceId || ""
        )}`
      );
      const results = hist.results || hist;
      el.title.textContent = results.title || "Conversation";
      state.llm = results.llm || state.llm;
      if (state.llm) el.model.value = state.llm;
      state.mode = results.mode || state.mode;
      setMode(state.mode);
      const dialogue = results.dialogue || [];
      state.messages = [];
      for (const d of dialogue) {
        state.messages.push({ role: "user", content: d.query || d.parsed_query || "" });
        state.messages.push({
          role: "assistant",
          content: d.answer || "",
          reasoning: d.reasoning || [],
        });
      }
      renderMessages();
      renderThreads();
      syncShellPath(chatId, { replace: true });
      notifyParent({ type: "title", title: results.title || "Conversation" });
    } catch (e) {
      console.warn("history", e);
    }
  }

  async function ensureChat() {
    if (state.chatId) return state.chatId;
    const res = await api(`/api/v1/chat/initialize-chat/`, {
      method: "POST",
      body: {
        workspace_slug: state.workspaceSlug,
        workspace_id: state.workspaceId,
        title: "New Conversation",
        llm: state.llm || el.model.value,
        workspace_in_context: true,
      },
    });
    state.chatId = res.chat_id;
    syncShellPath(state.chatId, { replace: true });
    return state.chatId;
  }

  async function sendMessage() {
    const query = (el.input.value || "").trim();
    if (!query || state.streaming) return;
    state.streaming = true;
    el.send.disabled = true;
    el.input.value = "";

    state.messages.push({ role: "user", content: query });
    const assistant = { role: "assistant", content: "", reasoning: [], thinking: true };
    state.messages.push(assistant);
    renderMessages();

    try {
      const chatId = await ensureChat();
      const isNew = state.messages.filter((m) => m.role === "user").length <= 1;
      const queue = await api(`/api/v1/chat/queue-answer/`, {
        method: "POST",
        body: {
          chat_id: chatId,
          query,
          is_new: isNew,
          is_temp: false,
          workspace_in_context: true,
          source: "WEB",
          llm: el.model.value || state.llm,
          context: {
            first_name: state.user?.first_name || "",
            last_name: state.user?.last_name || "",
            email: state.user?.email || "",
            user_id: state.user?.id || "",
          },
          workspace_slug: state.workspaceSlug,
          workspace_id: state.workspaceId,
          attachment_ids: [],
          mode: state.mode,
          is_websearch_enabled: state.websearch,
          mcp_connector_ids: [],
          skill_id: state.skillId,
        },
      });
      const token = queue.stream_token;
      await streamAnswer(token, assistant);
      // refresh title/threads
      try {
        await api(`/api/v1/chat/generate-title/`, {
          method: "POST",
          body: { chat_id: chatId, workspace_id: state.workspaceId, workspace_slug: state.workspaceSlug },
        });
      } catch (_) {}
      await refreshThreads();
      await openChat(chatId);
    } catch (e) {
      assistant.thinking = false;
      assistant.content = `Error: ${e.message || e}`;
      renderMessages();
    } finally {
      state.streaming = false;
      el.send.disabled = false;
      el.input.focus();
    }
  }

  async function streamAnswer(token, assistant) {
    const res = await fetch(`${PI_BASE}/api/v1/chat/stream-answer/${token}`, {
      credentials: "include",
      headers: { Accept: "text/event-stream", "X-CSRFToken": csrf() },
    });
    if (!res.ok || !res.body) {
      throw new Error(`stream failed ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const lines = part.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        let payload = {};
        try {
          payload = JSON.parse(data);
        } catch {
          payload = { chunk: data };
        }
        if (event === "reasoning") {
          assistant.reasoning = assistant.reasoning || [];
          assistant.reasoning.push({ header: payload.header || "", content: payload.content || "" });
          assistant.thinking = true;
          renderMessages();
        } else if (event === "delta") {
          assistant.thinking = false;
          assistant.content += payload.chunk || payload.content || "";
          renderMessages();
        } else if (event === "done") {
          assistant.thinking = false;
          renderMessages();
        } else if (event === "error") {
          assistant.thinking = false;
          assistant.content += `\n${payload.error || "stream error"}`;
          renderMessages();
        }
      }
    }
    assistant.thinking = false;
    renderMessages();
  }

  async function refreshThreads() {
    try {
      const threads = await api(
        `/api/v1/chat/get-user-threads/?workspace_slug=${encodeURIComponent(state.workspaceSlug || "")}&workspace_id=${encodeURIComponent(
          state.workspaceId || ""
        )}`
      );
      state.threads = threads.results || [];
      renderThreads();
    } catch (_) {}
  }

  async function newChat() {
    state.chatId = null;
    state.messages = [];
    state.skillId = null;
    el.title.textContent = "New Conversation";
    renderMessages();
    renderSkills();
    if (state.workspaceSlug) {
      const path = `/${state.workspaceSlug}/ai-chat/new`;
      if (isEmbed) notifyParent({ type: "navigate", path, replace: true });
      else history.replaceState({}, "", path);
    }
    notifyParent({ type: "title", title: "New Conversation" });
    el.input.focus();
  }

  // events
  el.send.onclick = sendMessage;
  el.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  el.model.onchange = () => {
    state.llm = el.model.value;
    localStorage.setItem("pilot_llm", state.llm);
  };
  el.modeTabs.forEach((btn) => {
    btn.onclick = () => setMode(btn.dataset.mode);
  });
  el.newChat.onclick = newChat;
  el.websearch.onclick = () => {
    state.websearch = !state.websearch;
    el.websearch.classList.toggle("active", state.websearch);
  };
  el.favBtn.onclick = async () => {
    if (!state.chatId) return;
    try {
      await api(`/api/v1/chat/favorite-chat/`, {
        method: "POST",
        body: { chat_id: state.chatId, workspace_id: state.workspaceId, workspace_slug: state.workspaceSlug },
      });
      const favs = await api(`/api/v1/chat/get-favorite-chats/?workspace_id=${encodeURIComponent(state.workspaceId || "")}`);
      state.favorites = Array.isArray(favs) ? favs : favs.results || [];
      renderThreads();
    } catch (e) {
      alert(e.message);
    }
  };
  el.renameBtn.onclick = async () => {
    if (!state.chatId) return;
    const title = prompt("Rename chat", el.title.textContent || "Conversation");
    if (!title) return;
    await api(`/api/v1/chat/rename-chat/`, {
      method: "POST",
      body: { chat_id: state.chatId, title, workspace_id: state.workspaceId, workspace_slug: state.workspaceSlug },
    });
    el.title.textContent = title;
    await refreshThreads();
  };
  el.deleteBtn.onclick = async () => {
    if (!state.chatId) return;
    if (!confirm("Delete this chat?")) return;
    await fetch(`${PI_BASE}/api/v1/chat/delete-chat/`, {
      method: "DELETE",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ chat_id: state.chatId, workspace_id: state.workspaceId }),
    });
    await newChat();
    await refreshThreads();
  };
  if (el.menuBtn) {
    el.menuBtn.onclick = () => el.sidebar.classList.toggle("open");
  }

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

  setMode(state.mode);
  loadBootstrap();
})();
