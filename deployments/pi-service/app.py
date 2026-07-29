"""
Self-hosted Plane Intelligence (Pilot AI) — API-compatible with pi.plane.so.

Reverse-engineered from Business cloud (app.plane.so / pi.plane.so).
Also serves the Pilot UI shell + inject script for self-hosted web parity.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = (os.environ.get("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL") or "deepseek/deepseek-chat"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER") or "custom"
DEFAULT_MODEL_ID = os.environ.get("PI_DEFAULT_MODEL") or LLM_MODEL
# Plane API for agent tools (create/edit work items, pages, etc.)
PLANE_API_BASE = (os.environ.get("PLANE_API_BASE") or "http://api:8000").rstrip("/")
CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "*").split(",")
    if o.strip()
]
APP_DOMAIN = os.environ.get("APP_DOMAIN") or "plane.cosmicboosts.store"
# Only DeepSeek models are exposed in this self-host build.
ALLOWED_MODEL_PREFIXES = ("deepseek",)

CHATS: Dict[str, Dict[str, Any]] = {}
STREAMS: Dict[str, Dict[str, Any]] = {}
FAVORITES: Dict[str, set] = {}


def load_json(name: str, default: Any) -> Any:
    path = BASE_DIR / name
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


SKILLS_SEED = load_json("skills.json", [])
MODELS_SEED = load_json("models.json", {}).get("models") or []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_key(request: Request) -> str:
    sid = request.cookies.get("session-id") or request.cookies.get("sessionid") or ""
    if sid:
        return f"sess:{sid[:48]}"
    auth = request.headers.get("authorization") or ""
    if auth:
        return f"auth:{auth[-48:]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class InitChatBody(BaseModel):
    workspace_slug: Optional[str] = None
    workspace_id: Optional[str] = None
    title: Optional[str] = None
    llm: Optional[str] = None
    project_id: Optional[str] = None
    mcp_connector_ids: Optional[List[str]] = None
    workspace_in_context: Optional[bool] = False


class QueueAnswerBody(BaseModel):
    chat_id: str
    query: str
    is_new: bool = False
    is_temp: bool = False
    workspace_in_context: bool = False
    source: str = "WEB"
    llm: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    workspace_slug: Optional[str] = None
    workspace_id: Optional[str] = None
    attachment_ids: Optional[List[str]] = Field(default_factory=list)
    mode: str = "ask"
    is_websearch_enabled: bool = False
    mcp_connector_ids: Optional[List[str]] = Field(default_factory=list)
    project_id: Optional[str] = None
    pi_sidebar_open: Optional[bool] = None
    sidebar_open_url: Optional[str] = None
    skill_id: Optional[str] = None


class RenameBody(BaseModel):
    chat_id: str
    title: str
    workspace_id: Optional[str] = None
    workspace_slug: Optional[str] = None


class ChatIdBody(BaseModel):
    chat_id: str
    workspace_id: Optional[str] = None
    workspace_slug: Optional[str] = None


class FeedbackBody(BaseModel):
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    rating: Optional[str] = None
    feedback: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_slug: Optional[str] = None


class SetPromptsBody(BaseModel):
    workspace_id: Optional[str] = None
    workspace_slug: Optional[str] = None
    mode: str = "ask"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Plane Intelligence (self-hosted)", version="3.0.0-cosmic")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/cosmic-pilot/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _is_deepseek(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return any(mid.startswith(p) or p in mid for p in ALLOWED_MODEL_PREFIXES)


def model_catalog() -> List[Dict[str, Any]]:
    """DeepSeek-only catalog (other cloud models are disabled on this instance)."""
    models: List[Dict[str, Any]] = []
    for m in MODELS_SEED or []:
        row = dict(m)
        if not _is_deepseek(str(row.get("id") or "")):
            continue
        row.setdefault("type", "language_model")
        row.setdefault("supports_web_search", False)
        row.setdefault("supports_thinking", False)
        row["is_default"] = False
        models.append(row)

    default_id = DEFAULT_MODEL_ID if _is_deepseek(DEFAULT_MODEL_ID) else "deepseek/deepseek-chat"
    if not any(m["id"] == default_id for m in models):
        models.insert(
            0,
            {
                "id": default_id,
                "name": "DeepSeek Chat",
                "provider": "DeepSeek",
                "description": "Only model enabled on this self-hosted Pilot.",
                "type": "language_model",
                "supports_web_search": False,
                "supports_thinking": False,
                "is_default": True,
            },
        )
    for m in models:
        m["is_default"] = m["id"] == default_id
    if not models:
        models = [
            {
                "id": "deepseek/deepseek-chat",
                "name": "DeepSeek Chat",
                "provider": "DeepSeek",
                "description": "Only model enabled on this self-hosted Pilot.",
                "type": "language_model",
                "supports_web_search": False,
                "supports_thinking": False,
                "is_default": True,
            }
        ]
    return models


def resolve_llm(model_id: Optional[str]) -> str:
    """Force DeepSeek only — never route to OpenAI/Anthropic/etc."""
    mid = model_id or DEFAULT_MODEL_ID
    if not _is_deepseek(mid):
        mid = DEFAULT_MODEL_ID if _is_deepseek(DEFAULT_MODEL_ID) else "deepseek/deepseek-chat"
    aliases = {
        "deepseek-ai/DeepSeek-V4-Pro": "deepseek/deepseek-chat",
        "deepseek/deepseek-v4-flash": "deepseek/deepseek-chat",
        "deepseek-chat": "deepseek/deepseek-chat",
    }
    return aliases.get(mid, mid)



async def plane_api(
    method: str,
    path: str,
    cookie: str = "",
    csrf: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call self-hosted Plane REST API (for agent tools)."""
    url = f"{PLANE_API_BASE}{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "plane-intelligence/self-host",
    }
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRFToken"] = csrf
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.request(method, url, headers=headers, json=payload)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:2000]}
            return {"status": r.status_code, "data": data}
    except Exception as e:
        return {"status": 0, "error": str(e)}


async def gather_workspace_context(
    workspace_slug: Optional[str], cookie: str, csrf: str
) -> str:
    if not workspace_slug:
        return ""
    parts: List[str] = []
    projects = await plane_api(
        "GET", f"/api/workspaces/{workspace_slug}/projects/", cookie, csrf
    )
    if projects.get("status") == 200:
        rows = projects.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("results") or rows.get("data") or []
        names = []
        for p in (rows or [])[:15]:
            if isinstance(p, dict):
                names.append(
                    f"- {p.get('identifier') or ''} {p.get('name')} (id={p.get('id')})"
                )
        if names:
            parts.append("Projects:\n" + "\n".join(names))
    pages = await plane_api(
        "GET", f"/api/workspaces/{workspace_slug}/pages/", cookie, csrf
    )
    if pages.get("status") == 200:
        data = pages.get("data") or {}
        results = data.get("results") if isinstance(data, dict) else data
        names = []
        for p in (results or [])[:15]:
            if isinstance(p, dict):
                names.append(f"- {p.get('name') or 'Untitled'} (id={p.get('id')})")
        if names:
            parts.append("Wiki pages:\n" + "\n".join(names))
    return "\n\n".join(parts)


async def execute_plane_tools(
    mode: str,
    query: str,
    workspace_slug: Optional[str],
    cookie: str,
    csrf: str,
) -> str:
    """Agent actions for Build/Autopilot — create work items and wiki pages via Plane API."""
    if mode not in ("build", "autopilot") or not workspace_slug:
        return ""
    q = (query or "").lower()
    notes: List[str] = []

    if any(k in q for k in ("create work item", "create issue", "add issue", "new issue", "new work item")):
        projects = await plane_api(
            "GET", f"/api/workspaces/{workspace_slug}/projects/", cookie, csrf
        )
        proj_list = projects.get("data") or []
        if isinstance(proj_list, dict):
            proj_list = proj_list.get("results") or []
        project_id = None
        for p in proj_list or []:
            ident = (p.get("identifier") or "").lower()
            name = (p.get("name") or "").lower()
            if ident and ident in q:
                project_id = p.get("id")
                break
            if name and name in q:
                project_id = p.get("id")
                break
        if not project_id and proj_list:
            project_id = proj_list[0].get("id")
        title = query
        for sep in ("called ", "titled ", "named ", ": "):
            if sep in q:
                title = query[q.index(sep) + len(sep) :].strip(" .\"'")
                break
        title = title[:200] or "New work item"
        if project_id:
            res = await plane_api(
                "POST",
                f"/api/workspaces/{workspace_slug}/projects/{project_id}/issues/",
                cookie,
                csrf,
                {"name": title, "project_id": project_id},
            )
            notes.append(f"Create work item result: {json.dumps(res)[:800]}")
        else:
            notes.append("Could not resolve a project to create the work item in.")

    if any(k in q for k in ("create wiki", "create page", "new wiki", "new page", "add page")):
        title = "Untitled"
        for sep in ("called ", "titled ", "named ", ": "):
            if sep in q:
                title = query[q.index(sep) + len(sep) :].strip(" .\"'")[:200]
                break
        res = await plane_api(
            "POST",
            f"/api/workspaces/{workspace_slug}/pages/",
            cookie,
            csrf,
            {"name": title or "Untitled"},
        )
        notes.append(f"Create wiki page result: {json.dumps(res)[:800]}")

    if any(k in q for k in ("my work", "assigned to me", "my issues", "my work items", "what am i working")):
        res = await plane_api(
            "GET", f"/api/workspaces/{workspace_slug}/user-issues/", cookie, csrf
        )
        if res.get("status") != 200:
            res = await plane_api(
                "GET", f"/api/users/me/workspaces/{workspace_slug}/issues/", cookie, csrf
            )
        notes.append(f"User work items: {json.dumps(res)[:1200]}")

    return "\n".join(notes)


async def llm_stream(messages: List[Dict[str, str]], model: str):
    if not LLM_API_KEY:
        yield "Pilot AI is not configured: missing LLM_API_KEY on the server."
        return

    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": f"https://{APP_DOMAIN}",
        "X-Title": "Plane Intelligence Self-Hosted",
    }
    body = {
        "model": resolve_llm(model),
        "messages": messages,
        "stream": True,
        "temperature": 0.4,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    err = await resp.aread()
                    yield f"LLM error ({resp.status_code}): {err.decode('utf-8', 'ignore')[:400]}"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                            delta = (
                                payload.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content")
                            )
                            if delta:
                                yield delta
                        except Exception:
                            continue
    except Exception as e:
        yield f"LLM connection error: {e}"


# ---------------------------------------------------------------------------
# UI routes
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "llm_configured": bool(LLM_API_KEY),
        "default_model": DEFAULT_MODEL_ID,
        "skills": len(SKILLS_SEED),
        "models": len(model_catalog()),
    }


@app.get("/cosmic-pilot/wiki")
def wiki_ui():
    index = STATIC_DIR / "wiki.html"
    if not index.exists():
        return HTMLResponse("<h1>Wiki UI missing</h1>", status_code=500)
    return FileResponse(index, media_type="text/html")


@app.get("/cosmic-pilot/ui")
def pilot_ui():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Pilot UI missing</h1>", status_code=500)
    return FileResponse(index, media_type="text/html")


@app.get("/cosmic-pilot/inject.js")
def inject_js():
    path = STATIC_DIR / "inject.js"
    return FileResponse(path, media_type="application/javascript")


# ---------------------------------------------------------------------------
# API — match pi.plane.so /api/v1/
# ---------------------------------------------------------------------------


@app.get("/api/v1/chat/get-models/")
def get_models(workspace_id: Optional[str] = None):
    return {"models": model_catalog()}


@app.get("/api/v1/chat/start/auth-check/")
def auth_check(workspace_slug: str = Query(...)):
    has = any(
        c.get("workspace_slug") == workspace_slug and c.get("messages")
        for c in CHATS.values()
    )
    return {"is_authorized": True, "oauth_url": None, "has_chats": has}


@app.get("/api/v1/flags/")
def flags(workspace_slug: Optional[str] = None):
    return {
        "values": {
            "AI_CHAT": True,
            "AI_DEDUPE": True,
            "AI_CONVERSE": True,
            "AI_FILE_UPLOADS": True,
            "AI_PAGES_BLOCKS": True,
            "AI_PAGES_SUMMARY": True,
            "AI_LABEL_PREDICTION": True,
            "AI_MCP_CONNECTORS": True,
            "AI_TEXT_TO_PQL": True,
            "AI_PAGES_EDIT": True,
            "AI_AUTOPILOT": True,
            "AI_SKILLS": True,
        }
    }


@app.get("/api/v1/skills/")
def skills(workspace_slug: str = Query(...)):
    items = SKILLS_SEED or [
        {
            "id": "default-ask",
            "slug": "my-work",
            "description": "Your open work items across the workspace",
            "instructions": "Show my open work items.",
            "is_active": True,
            "scope": "system",
            "is_system": True,
            "has_parameters": False,
            "parameters": [],
            "user_id": None,
            "workspace_id": None,
            "created_by_id": None,
        }
    ]
    return {"items": items}


@app.post("/api/v1/chat/initialize-chat/")
async def initialize_chat(body: InitChatBody, request: Request):
    chat_id = str(uuid.uuid4())
    CHATS[chat_id] = {
        "chat_id": chat_id,
        "title": body.title or "New Conversation",
        "workspace_slug": body.workspace_slug,
        "workspace_id": body.workspace_id,
        "project_id": body.project_id,
        "llm": body.llm or DEFAULT_MODEL_ID,
        "mode": "ask",
        "created_at": now_iso(),
        "last_modified": now_iso(),
        "is_favorite": False,
        "messages": [],
        "owner": user_key(request),
        "dialogue": [],
        "is_websearch_enabled": False,
        "mcp_connector_ids": body.mcp_connector_ids or [],
    }
    return {"chat_id": chat_id}


@app.post("/api/v1/chat/queue-answer/")
async def queue_answer(body: QueueAnswerBody, request: Request):
    chat = CHATS.get(body.chat_id)
    if not chat:
        chat = {
            "chat_id": body.chat_id,
            "title": "New Conversation",
            "workspace_slug": body.workspace_slug,
            "workspace_id": body.workspace_id,
            "llm": body.llm or DEFAULT_MODEL_ID,
            "mode": body.mode or "ask",
            "created_at": now_iso(),
            "last_modified": now_iso(),
            "is_favorite": False,
            "messages": [],
            "owner": user_key(request),
            "dialogue": [],
            "is_websearch_enabled": body.is_websearch_enabled,
            "mcp_connector_ids": body.mcp_connector_ids or [],
        }
        CHATS[body.chat_id] = chat

    stream_token = str(uuid.uuid4())
    query_id = stream_token  # cloud reuses stream token as query_id in history
    STREAMS[stream_token] = {
        "chat_id": body.chat_id,
        "query": body.query,
        "query_id": query_id,
        "llm": body.llm or chat.get("llm") or DEFAULT_MODEL_ID,
        "mode": body.mode or "ask",
        "created_at": time.time(),
        "context": body.context or {},
        "workspace_slug": body.workspace_slug or chat.get("workspace_slug"),
        "workspace_id": body.workspace_id or chat.get("workspace_id"),
        "skill_id": body.skill_id,
        "is_websearch_enabled": body.is_websearch_enabled,
    }

    chat["messages"].append(
        {"role": "user", "content": body.query, "id": query_id, "ts": now_iso()}
    )
    chat["mode"] = body.mode or chat.get("mode") or "ask"
    chat["llm"] = body.llm or chat.get("llm")
    chat["last_modified"] = now_iso()
    chat["is_websearch_enabled"] = body.is_websearch_enabled
    if body.workspace_id:
        chat["workspace_id"] = body.workspace_id
    if body.workspace_slug:
        chat["workspace_slug"] = body.workspace_slug
    if body.is_new or chat.get("title") in (None, "New Chat", "New Conversation"):
        chat["title"] = (body.query[:48] + ("…" if len(body.query) > 48 else "")) or "New Conversation"

    return {"stream_token": stream_token}


@app.get("/api/v1/chat/stream-answer/{stream_token}")
async def stream_answer(stream_token: str, request: Request):
    job = STREAMS.get(stream_token)
    if not job:
        async def err():
            yield 'event: error\ndata: {"error":"invalid stream token"}\n\n'
            yield 'event: done\ndata: {"done": true}\n\n'

        return StreamingResponse(err(), media_type="text/event-stream")

    chat = CHATS.get(job["chat_id"], {})
    history = chat.get("messages") or []
    cookie = request.headers.get("cookie") or ""
    csrf = request.headers.get("x-csrftoken") or ""
    mode = job.get("mode") or "ask"
    system = (
        "You are Plane Intelligence (Pilot AI), the AI assistant inside Plane project management "
        "(same product as app.plane.so Pilot). Be concise, helpful, and structured. Use markdown. "
        f"Workspace: {job.get('workspace_slug') or 'unknown'}. Mode: {mode}. "
        "In Ask mode: answer questions about the workspace. "
        "In Build mode: help create and edit work items, pages, and plans; when tools ran, explain results. "
        "In Autopilot mode: proactively suggest and describe multi-step changes. "
        "Only DeepSeek models are available on this instance."
    )
    if job.get("skill_id") and SKILLS_SEED:
        skill = next((s for s in SKILLS_SEED if s.get("id") == job["skill_id"]), None)
        if skill and skill.get("instructions"):
            system += f"\n\nSkill ({skill.get('slug')}):\n{skill['instructions']}"

    ctx = job.get("context") or {}
    if ctx.get("first_name"):
        system += f" User: {ctx.get('first_name')} {ctx.get('last_name') or ''} ({ctx.get('email') or ''})."

    # Pull live workspace context + optional agent tool results
    ws_ctx = await gather_workspace_context(job.get("workspace_slug"), cookie, csrf)
    if ws_ctx:
        system += "\n\nWorkspace snapshot:\n" + ws_ctx
    tool_notes = await execute_plane_tools(
        mode, job.get("query") or "", job.get("workspace_slug"), cookie, csrf
    )
    if tool_notes:
        system += "\n\nTool results from this turn (use these facts):\n" + tool_notes

    msgs = [{"role": "system", "content": system}]
    for m in history[-12:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})

    async def event_gen():
        reasoning_headers = [
            "\n\nLooking for the cleanest angle...\n\n",
            "\n\nWeighing which step moves us forward...\n\n",
            "Generating final response...\n\n",
        ]
        reasoning_log = []
        for h in reasoning_headers:
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.05)

        full = []
        async for chunk in llm_stream(msgs, job.get("llm") or DEFAULT_MODEL_ID):
            full.append(chunk)
            yield "event: delta\ndata: " + json.dumps({"chunk": chunk}) + "\n\n"
            await asyncio.sleep(0)

        answer = "".join(full)
        answer_id = str(uuid.uuid4())
        if chat is not None:
            chat.setdefault("messages", []).append(
                {
                    "role": "assistant",
                    "content": answer,
                    "id": answer_id,
                    "ts": now_iso(),
                    "query_id": job.get("query_id"),
                }
            )
            chat["last_modified"] = now_iso()
            chat.setdefault("dialogue", []).append(
                {
                    "query": job.get("query"),
                    "answer": answer,
                    "reasoning": reasoning_log,
                    "todos": [],
                    "feedback": "",
                    "llm": job.get("llm"),
                    "parsed_query": job.get("query"),
                    "query_id": job.get("query_id"),
                    "answer_id": answer_id,
                    "attachment_ids": [],
                    "attachments": [],
                    "skill_id": job.get("skill_id"),
                    "skill_name": None,
                }
            )

        yield 'event: cta_available\ndata: ' + json.dumps({"type": "create_page"}) + "\n\n"
        yield 'event: done\ndata: ' + json.dumps({"done": True}) + "\n\n"
        STREAMS.pop(stream_token, None)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/chat/get-answer/")
async def get_answer_legacy(request: Request):
    """Compatibility with older EE pi-chat store (non-SSE)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    chat_id = body.get("chat_id") or str(uuid.uuid4())
    query = body.get("query") or body.get("prompt") or ""
    cookie = request.headers.get("cookie") or ""
    csrf = request.headers.get("x-csrftoken") or ""
    mode = body.get("mode") or "ask"
    llm = body.get("llm") or DEFAULT_MODEL_ID
    ws = body.get("workspace_slug")
    system = (
        "You are Plane Intelligence (Pilot AI). Be helpful and concise. "
        f"Workspace: {ws or 'unknown'}. Mode: {mode}."
    )
    ws_ctx = await gather_workspace_context(ws, cookie, csrf)
    if ws_ctx:
        system += "\n\n" + ws_ctx
    tool_notes = await execute_plane_tools(mode, query, ws, cookie, csrf)
    if tool_notes:
        system += "\n\nTool results:\n" + tool_notes
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": query}]
    chunks: List[str] = []
    async for chunk in llm_stream(msgs, llm):
        chunks.append(chunk)
    answer = "".join(chunks)
    CHATS[chat_id] = {
        "chat_id": chat_id,
        "title": (query[:48] + ("…" if len(query) > 48 else "")) or "New Conversation",
        "workspace_slug": ws,
        "workspace_id": body.get("workspace_id"),
        "llm": llm,
        "mode": mode,
        "created_at": now_iso(),
        "last_modified": now_iso(),
        "is_favorite": False,
        "messages": [
            {"role": "user", "content": query, "ts": now_iso()},
            {"role": "assistant", "content": answer, "ts": now_iso()},
        ],
        "owner": user_key(request),
        "dialogue": [{"query": query, "answer": answer, "llm": llm}],
        "is_websearch_enabled": False,
        "mcp_connector_ids": [],
    }
    return {"answer": answer, "chat_id": chat_id, "response": answer}



@app.get("/api/v1/chat/get-user-threads/")
def get_user_threads(
    request: Request,
    workspace_id: Optional[str] = None,
    workspace_slug: Optional[str] = None,
    per_page: int = 30,
    cursor: str = "0",
):
    uk = user_key(request)
    rows = [
        c
        for c in CHATS.values()
        if c.get("owner") == uk
        and (
            not workspace_id
            or c.get("workspace_id") == workspace_id
            or (workspace_slug and c.get("workspace_slug") == workspace_slug)
            or not c.get("workspace_id")
        )
    ]
    rows.sort(key=lambda x: x.get("last_modified") or "", reverse=True)
    start = int(cursor or 0)
    page = rows[start : start + per_page]
    results = [
        {
            "chat_id": c["chat_id"],
            "title": c.get("title") or "New Conversation",
            "last_modified": c.get("last_modified"),
            "is_favorite": c.get("is_favorite", False),
            "llm": c.get("llm") or "",
            "workspace_id": c.get("workspace_id"),
            "mode": c.get("mode") or "ask",
        }
        for c in page
    ]
    next_cursor = str(start + per_page) if start + per_page < len(rows) else None
    return {
        "next_cursor": next_cursor,
        "prev_cursor": str(max(0, start - per_page)) if start > 0 else None,
        "next_page_results": bool(next_cursor),
        "prev_page_results": start > 0,
        "count": len(results),
        "total_pages": max(1, (len(rows) + per_page - 1) // per_page) if rows else 1,
        "total_results": len(rows),
        "results": results,
    }


@app.get("/api/v1/chat/get-recent-user-threads/")
def get_recent(
    request: Request,
    workspace_id: Optional[str] = None,
    workspace_slug: Optional[str] = None,
):
    data = get_user_threads(request, workspace_id, workspace_slug, per_page=10, cursor="0")
    return {"results": data["results"]}


@app.get("/api/v1/chat/get-favorite-chats/")
def get_favorites(request: Request, workspace_id: Optional[str] = None):
    uk = user_key(request)
    favs = FAVORITES.get(uk, set())
    return [
        {
            "chat_id": c["chat_id"],
            "title": c.get("title"),
            "last_modified": c.get("last_modified"),
            "is_favorite": True,
            "llm": c.get("llm") or "",
            "workspace_id": c.get("workspace_id"),
            "mode": c.get("mode") or "ask",
        }
        for c in CHATS.values()
        if c["chat_id"] in favs and c.get("owner") == uk
    ]


@app.get("/api/v1/chat/get-chat-history-object/")
def get_chat_history(chat_id: str, workspace_id: Optional[str] = None):
    c = CHATS.get(chat_id)
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    # Cloud shape: { results: { title, dialogue, llm, ... } }
    return {
        "results": {
            "title": c.get("title") or "New Conversation",
            "dialogue": c.get("dialogue") or [],
            "llm": c.get("llm") or "",
            "feedback": "",
            "reasoning": "",
            "is_focus_enabled": True,
            "is_websearch_enabled": c.get("is_websearch_enabled", False),
            "focus_entity_type": "workspace",
            "focus_entity_id": c.get("workspace_id"),
            "focus_project_id": c.get("project_id"),
            "focus_workspace_id": c.get("workspace_id"),
            "mode": c.get("mode") or "ask",
            "mcp_connector_ids": c.get("mcp_connector_ids") or [],
        }
    }


@app.post("/api/v1/chat/generate-title/")
async def generate_title(body: ChatIdBody):
    c = CHATS.get(body.chat_id)
    if not c:
        return {"title": "New Conversation"}
    q = next(
        (m["content"] for m in c.get("messages", []) if m.get("role") == "user"),
        c.get("title") or "New Conversation",
    )
    title = (q[:48] + ("…" if len(q) > 48 else "")) if q else "New Conversation"
    c["title"] = title
    c["last_modified"] = now_iso()
    return {"title": title}


@app.post("/api/v1/chat/rename-chat/")
async def rename_chat(body: RenameBody):
    c = CHATS.get(body.chat_id)
    if c:
        c["title"] = body.title
        c["last_modified"] = now_iso()
    return {"ok": True, "title": body.title}


@app.post("/api/v1/chat/favorite-chat/")
async def favorite_chat(body: ChatIdBody, request: Request):
    uk = user_key(request)
    FAVORITES.setdefault(uk, set()).add(body.chat_id)
    if body.chat_id in CHATS:
        CHATS[body.chat_id]["is_favorite"] = True
    return {"ok": True}


@app.post("/api/v1/chat/unfavorite-chat/")
async def unfavorite_chat(body: ChatIdBody, request: Request):
    uk = user_key(request)
    FAVORITES.setdefault(uk, set()).discard(body.chat_id)
    if body.chat_id in CHATS:
        CHATS[body.chat_id]["is_favorite"] = False
    return {"ok": True}


@app.delete("/api/v1/chat/delete-chat/")
async def delete_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    chat_id = body.get("chat_id")
    if chat_id and chat_id in CHATS:
        del CHATS[chat_id]
    return {"ok": True}


@app.post("/api/v1/chat/feedback/")
async def feedback(body: FeedbackBody):
    return {"ok": True}


@app.post("/api/v1/chat/start/set-prompts/")
async def set_prompts(body: SetPromptsBody):
    mode = body.mode or "ask"
    return {
        "templates": [
            {
                "text": "Show me recent activity on my pending work items",
                "type": "issues",
                "mode": mode,
                "id": [],
            },
            {
                "text": "What changed in my pending work items today?",
                "type": "issues",
                "mode": mode,
                "id": [],
            },
            {
                "text": "What work items are assigned to me and not yet completed, with start and end dates, priorities?",
                "type": "issues",
                "mode": mode,
                "id": [],
            },
        ]
    }


@app.post("/api/v1/chat/search-chats/")
async def search_chats(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    q = (body.get("query") or "").lower()
    uk = user_key(request)
    results = [
        {"chat_id": c["chat_id"], "title": c.get("title")}
        for c in CHATS.values()
        if c.get("owner") == uk and q in (c.get("title") or "").lower()
    ]
    return {"results": results}


@app.post("/api/v1/chat/execute-action/")
async def execute_action(request: Request):
    return {"ok": True, "status": "completed"}


@app.get("/api/v1/artifacts/chat/{chat_id}/")
async def list_artifacts(chat_id: str):
    return {"artifacts": []}


@app.get("/api/v1/attachments/chat/")
async def list_attachments(chat_id: str):
    return {"attachments": []}


@app.get("/")
def root():
    return {
        "service": "plane-intelligence",
        "compatible_with": "pi.plane.so",
        "llm_configured": bool(LLM_API_KEY),
        "default_model": DEFAULT_MODEL_ID,
        "ui": "/cosmic-pilot/ui",
        "inject": "/cosmic-pilot/inject.js",
    }
