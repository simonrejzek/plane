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
LLM_MODEL = os.environ.get("LLM_MODEL") or "deepseek/deepseek-v4-flash"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER") or "custom"
DEFAULT_MODEL_ID = os.environ.get("PI_DEFAULT_MODEL") or LLM_MODEL
CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "*").split(",")
    if o.strip()
]
APP_DOMAIN = os.environ.get("APP_DOMAIN") or "plane.cosmicboosts.store"

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


def model_catalog() -> List[Dict[str, Any]]:
    """Prefer cloud-shaped catalog; ensure default maps to configured LLM."""
    if MODELS_SEED:
        models = []
        for m in MODELS_SEED:
            row = dict(m)
            # Keep cloud ids for UI parity; resolve_llm maps them for OpenRouter
            row.setdefault("type", "language_model")
            row.setdefault("supports_web_search", False)
            row.setdefault("supports_thinking", False)
            row["is_default"] = False
            models.append(row)
        # Mark first as default if none; also inject self-host default at top
        default_row = {
            "id": DEFAULT_MODEL_ID,
            "name": f"Default ({DEFAULT_MODEL_ID})",
            "provider": (LLM_PROVIDER or "Custom").title(),
            "description": "Workspace default model (OpenRouter / custom BYOK)",
            "type": "language_model",
            "supports_web_search": False,
            "supports_thinking": False,
            "is_default": True,
        }
        # If DEFAULT already in list, mark it default
        found = False
        for m in models:
            if m["id"] == DEFAULT_MODEL_ID:
                m["is_default"] = True
                found = True
                break
        if not found:
            models.insert(0, default_row)
        else:
            for m in models:
                if m["id"] != DEFAULT_MODEL_ID:
                    m["is_default"] = False
        return models

    return [
        {
            "id": DEFAULT_MODEL_ID,
            "name": f"Default ({DEFAULT_MODEL_ID})",
            "provider": (LLM_PROVIDER or "Custom").title(),
            "description": "Workspace default model",
            "type": "language_model",
            "supports_web_search": False,
            "supports_thinking": False,
            "is_default": True,
        }
    ]


def resolve_llm(model_id: Optional[str]) -> str:
    mid = model_id or DEFAULT_MODEL_ID
    aliases = {
        "gpt-5.2": "openai/gpt-4.1-mini",
        "gpt-5.4": "openai/gpt-4.1-mini",
        "gpt-5.6-terra": "openai/gpt-4.1-mini",
        "claude-sonnet-4-5": "anthropic/claude-sonnet-4",
        "claude-sonnet-4-6": "anthropic/claude-sonnet-4",
        "claude-sonnet-5": "anthropic/claude-sonnet-4",
        "zai-org/GLM-5.2": "z-ai/glm-4.5-air",
        "moonshotai/Kimi-K2.6": "moonshotai/kimi-k2",
        "deepseek-ai/DeepSeek-V4-Pro": "deepseek/deepseek-v4-flash",
    }
    return aliases.get(mid, mid)


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
    system = (
        "You are Plane Intelligence (Pilot AI), the AI assistant inside Plane project management. "
        "Be concise, helpful, and structured. Use markdown when useful. "
        f"Workspace: {job.get('workspace_slug') or 'unknown'}. Mode: {job.get('mode')}."
    )
    # skill instructions
    if job.get("skill_id") and SKILLS_SEED:
        skill = next((s for s in SKILLS_SEED if s.get("id") == job["skill_id"]), None)
        if skill and skill.get("instructions"):
            system += f"\n\nSkill ({skill.get('slug')}):\n{skill['instructions']}"

    ctx = job.get("context") or {}
    if ctx.get("first_name"):
        system += f" User: {ctx.get('first_name')} {ctx.get('last_name') or ''} ({ctx.get('email') or ''})."

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
