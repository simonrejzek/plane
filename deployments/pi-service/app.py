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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
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

# Workspace wiki pages (cloud: /api/workspaces/{slug}/pages/) — CE lacks this; PI hosts it.
WIKI_DATA_DIR = Path(os.environ.get("WIKI_DATA_DIR") or (BASE_DIR / "data" / "wiki"))
WIKI_DATA_DIR.mkdir(parents=True, exist_ok=True)
WIKI_PAGES: Dict[str, Dict[str, Dict[str, Any]]] = {}  # slug -> {page_id -> page}


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


def _wiki_path(slug: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (slug or "default"))
    return WIKI_DATA_DIR / f"{safe}.json"


def load_wiki(slug: str) -> Dict[str, Dict[str, Any]]:
    if slug in WIKI_PAGES:
        return WIKI_PAGES[slug]
    path = _wiki_path(slug)
    pages: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                pages = {k: v for k, v in raw.items() if isinstance(v, dict)}
            elif isinstance(raw, list):
                pages = {p["id"]: p for p in raw if isinstance(p, dict) and p.get("id")}
        except Exception:
            pages = {}
    if not pages:
        # Seed a welcome page like cloud workspaces
        pid = str(uuid.uuid4())
        pages[pid] = {
            "id": pid,
            "name": "Welcome to Company's Wiki",
            "owned_by": None,
            "access": 0,
            "color": "",
            "is_favorite": False,
            "is_locked": False,
            "archived_at": None,
            "workspace": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "created_by": None,
            "updated_by": None,
            "view_props": {"full_width": False},
            "logo_props": {},
            "label_ids": [],
            "anchor": None,
            "parent_id": None,
            "collection_id": None,
            "sub_pages_count": None,
            "shared_access": None,
            "is_shared": False,
            "sort_order": 65535.0,
            "projects": [],
            "description": "This is your workspace wiki. Create pages to capture knowledge, processes, and notes — same surface as app.plane.so Wiki.",
            "description_html": "<p>This is your workspace wiki. Create pages to capture knowledge, processes, and notes — same surface as app.plane.so Wiki.</p>",
            "description_stripped": "This is your workspace wiki. Create pages to capture knowledge, processes, and notes — same surface as app.plane.so Wiki.",
        }
        save_wiki(slug, pages)
    WIKI_PAGES[slug] = pages
    return pages


def save_wiki(slug: str, pages: Dict[str, Dict[str, Any]]) -> None:
    WIKI_PAGES[slug] = pages
    path = _wiki_path(slug)
    try:
        path.write_text(json.dumps(pages, indent=2, default=str))
    except Exception:
        pass


def page_public(page: Dict[str, Any], include_body: bool = False) -> Dict[str, Any]:
    out = {k: v for k, v in page.items() if k not in ("description", "description_html", "description_stripped") or include_body}
    if include_body:
        out["description"] = page.get("description") or ""
        out["description_html"] = page.get("description_html") or ""
        out["description_stripped"] = page.get("description_stripped") or page.get("description") or ""
    return out


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


def _extract_title(query: str, default: str = "Untitled") -> str:
    q = (query or "").lower()
    title = query or default
    for sep in ("called ", "titled ", "named ", "title ", ": "):
        if sep in q:
            title = query[q.index(sep) + len(sep) :].strip(" .\"'")
            break
    # strip leading intent verbs
    for prefix in (
        "create work item ",
        "create issue ",
        "add issue ",
        "new issue ",
        "new work item ",
        "create wiki page ",
        "create wiki ",
        "create page ",
        "new wiki ",
        "new page ",
        "add page ",
        "update page ",
        "edit page ",
        "rename page ",
    ):
        if title.lower().startswith(prefix):
            title = title[len(prefix) :].strip()
    return (title[:200] or default).strip()


async def execute_plane_tools(
    mode: str,
    query: str,
    workspace_slug: Optional[str],
    cookie: str,
    csrf: str,
) -> str:
    """Agent actions for Ask/Build/Autopilot — list, create, edit work items and wiki pages."""
    if not workspace_slug:
        return ""
    q = (query or "").lower()
    notes: List[str] = []
    can_mutate = mode in ("build", "autopilot") or any(
        k in q
        for k in (
            "create ",
            "add ",
            "new ",
            "update ",
            "edit ",
            "rename ",
            "delete ",
            "make ",
            "write ",
        )
    )

    # Always allow read-style tools in any mode
    if any(
        k in q
        for k in (
            "my work",
            "assigned to me",
            "my issues",
            "my work items",
            "what am i working",
            "list issues",
            "list work items",
            "show issues",
            "show work items",
            "pending",
            "open work",
        )
    ):
        res = await plane_api(
            "GET", f"/api/workspaces/{workspace_slug}/user-issues/", cookie, csrf
        )
        if res.get("status") != 200:
            res = await plane_api(
                "GET", f"/api/users/me/workspaces/{workspace_slug}/issues/", cookie, csrf
            )
        notes.append(f"User work items: {json.dumps(res)[:2000]}")

    if any(k in q for k in ("list projects", "show projects", "what projects", "project list")):
        projects = await plane_api(
            "GET", f"/api/workspaces/{workspace_slug}/projects/", cookie, csrf
        )
        notes.append(f"Projects: {json.dumps(projects)[:2000]}")

    if any(k in q for k in ("list wiki", "list pages", "wiki pages", "show wiki", "what pages")):
        pages = load_wiki(workspace_slug)
        summary = [
            {"id": p.get("id"), "name": p.get("name"), "updated_at": p.get("updated_at")}
            for p in pages.values()
        ]
        notes.append(f"Wiki pages ({len(summary)}): {json.dumps(summary)[:2000]}")

    if can_mutate and any(
        k in q
        for k in (
            "create work item",
            "create issue",
            "add issue",
            "new issue",
            "new work item",
            "make a work item",
            "make an issue",
            "create a task",
            "add a task",
        )
    ):
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
        title = _extract_title(query, "New work item")
        if project_id:
            res = await plane_api(
                "POST",
                f"/api/workspaces/{workspace_slug}/projects/{project_id}/issues/",
                cookie,
                csrf,
                {"name": title, "project_id": project_id},
            )
            notes.append(f"Create work item result: {json.dumps(res)[:1200]}")
        else:
            notes.append("Could not resolve a project to create the work item in.")

    if can_mutate and any(
        k in q
        for k in (
            "create wiki",
            "create page",
            "new wiki",
            "new page",
            "add page",
            "make a page",
            "write a page",
            "add wiki",
        )
    ):
        title = _extract_title(query, "Untitled")
        pages = load_wiki(workspace_slug)
        pid = str(uuid.uuid4())
        body = ""
        if "content:" in q:
            body = query[q.index("content:") + len("content:") :].strip()
        page = {
            "id": pid,
            "name": title or "Untitled",
            "owned_by": None,
            "access": 0,
            "color": "",
            "is_favorite": False,
            "is_locked": False,
            "archived_at": None,
            "workspace": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "created_by": None,
            "updated_by": None,
            "view_props": {"full_width": False},
            "logo_props": {},
            "label_ids": [],
            "anchor": None,
            "parent_id": None,
            "collection_id": None,
            "sub_pages_count": None,
            "shared_access": None,
            "is_shared": False,
            "sort_order": 65535.0,
            "projects": [],
            "description": body,
            "description_html": f"<p>{body}</p>" if body else "",
            "description_stripped": body,
        }
        pages[pid] = page
        save_wiki(workspace_slug, pages)
        notes.append(f"Created wiki page id={pid} name={title!r}")

    if can_mutate and any(k in q for k in ("update page", "edit page", "rename page", "update wiki")):
        pages = load_wiki(workspace_slug)
        target = None
        for p in pages.values():
            name = (p.get("name") or "").lower()
            if name and name in q:
                target = p
                break
        if not target and pages:
            # fall back to most recently updated
            target = sorted(pages.values(), key=lambda x: x.get("updated_at") or "", reverse=True)[0]
        if target:
            new_title = _extract_title(query, target.get("name") or "Untitled")
            if any(k in q for k in ("rename", "title")):
                target["name"] = new_title
            if "content:" in q:
                body = query[q.index("content:") + len("content:") :].strip()
                target["description"] = body
                target["description_html"] = f"<p>{body}</p>"
                target["description_stripped"] = body
            target["updated_at"] = now_iso()
            pages[target["id"]] = target
            save_wiki(workspace_slug, pages)
            notes.append(f"Updated wiki page id={target['id']} name={target.get('name')!r}")
        else:
            notes.append("No wiki page found to update.")

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
@app.get("/cosmic-pilot/wiki/")
def wiki_ui():
    index = STATIC_DIR / "wiki.html"
    if not index.exists():
        return HTMLResponse("<h1>Wiki UI missing</h1>", status_code=500)
    return FileResponse(index, media_type="text/html")


@app.get("/cosmic-pilot/ui")
@app.get("/cosmic-pilot/ui/")
def pilot_ui():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Pilot UI missing</h1>", status_code=500)
    return FileResponse(index, media_type="text/html")


def _inject_response():
    path = STATIC_DIR / "inject.js"
    if not path.exists():
        return HTMLResponse("// inject missing", status_code=500, media_type="application/javascript")
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/cosmic-pilot/inject.js")
@app.get("/cosmic-pilot-inject.js")
@app.get("/inject.js")
def inject_js():
    return _inject_response()


# ---------------------------------------------------------------------------
# Workspace Wiki API — cloud-compatible paths (proxied here from Caddy)
# ---------------------------------------------------------------------------


# Also expose under /api/v1/wiki/... so routing always hits PI (Caddy /api/v1/* → pi)
@app.get("/api/v1/wiki/workspaces/{slug}/pages/")
@app.get("/api/workspaces/{slug}/pages/")
def wiki_list_pages(slug: str, cursor: Optional[str] = None, per_page: int = 100):
    pages = list(load_wiki(slug).values())
    pages.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    results = [page_public(p, include_body=False) for p in pages]
    return {
        "grouped_by": None,
        "sub_grouped_by": None,
        "total_count": len(results),
        "next_cursor": None,
        "prev_cursor": None,
        "next_page_results": False,
        "prev_page_results": False,
        "count": len(results),
        "total_pages": 1,
        "total_results": len(results),
        "total_groups": None,
        "next_group_offset": None,
        "sub_total_groups": None,
        "sub_next_group_offset": None,
        "extra_stats": None,
        "results": results,
    }


@app.post("/api/v1/wiki/workspaces/{slug}/pages/")
@app.post("/api/workspaces/{slug}/pages/")
async def wiki_create_page(slug: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    pages = load_wiki(slug)
    pid = str(uuid.uuid4())
    name = (body.get("name") or "Untitled").strip() or "Untitled"
    description = body.get("description") or ""
    description_html = body.get("description_html") or (f"<p>{description}</p>" if description else "")
    page = {
        "id": pid,
        "name": name,
        "owned_by": None,
        "access": body.get("access", 0),
        "color": body.get("color") or "",
        "is_favorite": False,
        "is_locked": False,
        "archived_at": None,
        "workspace": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": None,
        "updated_by": None,
        "view_props": body.get("view_props") or {"full_width": False},
        "logo_props": body.get("logo_props") or {},
        "label_ids": body.get("label_ids") or [],
        "anchor": None,
        "parent_id": body.get("parent_id"),
        "collection_id": body.get("collection_id"),
        "sub_pages_count": None,
        "shared_access": None,
        "is_shared": False,
        "sort_order": float(body.get("sort_order") or 65535.0),
        "projects": body.get("projects") or [],
        "description": description,
        "description_html": description_html,
        "description_stripped": body.get("description_stripped") or description,
    }
    pages[pid] = page
    save_wiki(slug, pages)
    return page_public(page, include_body=True)


@app.get("/api/v1/wiki/workspaces/{slug}/pages/{page_id}/")
@app.get("/api/workspaces/{slug}/pages/{page_id}/")
def wiki_get_page(slug: str, page_id: str):
    pages = load_wiki(slug)
    page = pages.get(page_id)
    if not page:
        return JSONResponse({"error": "Page not found."}, status_code=404)
    return page_public(page, include_body=True)


@app.patch("/api/v1/wiki/workspaces/{slug}/pages/{page_id}/")
@app.patch("/api/workspaces/{slug}/pages/{page_id}/")
async def wiki_patch_page(slug: str, page_id: str, request: Request):
    pages = load_wiki(slug)
    page = pages.get(page_id)
    if not page:
        return JSONResponse({"error": "Page not found."}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    for key in ("name", "access", "color", "view_props", "logo_props", "parent_id", "sort_order", "is_favorite"):
        if key in body:
            page[key] = body[key]
    if "description" in body:
        page["description"] = body["description"] or ""
        page["description_stripped"] = body.get("description_stripped") or page["description"]
    if "description_html" in body:
        page["description_html"] = body["description_html"] or ""
        if "description" not in body:
            # strip tags lightly
            import re as _re

            page["description"] = _re.sub(r"<[^>]+>", "", page["description_html"] or "")
            page["description_stripped"] = page["description"]
    page["updated_at"] = now_iso()
    pages[page_id] = page
    save_wiki(slug, pages)
    return page_public(page, include_body=True)


@app.delete("/api/v1/wiki/workspaces/{slug}/pages/{page_id}/")
@app.delete("/api/workspaces/{slug}/pages/{page_id}/")
def wiki_delete_page(slug: str, page_id: str):
    pages = load_wiki(slug)
    if page_id in pages:
        del pages[page_id]
        save_wiki(slug, pages)
    return Response(status_code=204)


@app.get("/api/v1/wiki/workspaces/{slug}/pages/{page_id}/description/")
@app.get("/api/workspaces/{slug}/pages/{page_id}/description/")
def wiki_get_description(slug: str, page_id: str):
    pages = load_wiki(slug)
    page = pages.get(page_id)
    if not page:
        return JSONResponse({"error": "Page not found."}, status_code=404)
    return {
        "description": page.get("description") or "",
        "description_html": page.get("description_html") or "",
        "description_stripped": page.get("description_stripped") or page.get("description") or "",
    }


@app.patch("/api/v1/wiki/workspaces/{slug}/pages/{page_id}/description/")
@app.patch("/api/workspaces/{slug}/pages/{page_id}/description/")
async def wiki_patch_description(slug: str, page_id: str, request: Request):
    pages = load_wiki(slug)
    page = pages.get(page_id)
    if not page:
        return JSONResponse({"error": "Page not found."}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if "description_html" in body:
        page["description_html"] = body["description_html"] or ""
    if "description" in body:
        page["description"] = body["description"] or ""
    elif "description_html" in body:
        import re as _re

        page["description"] = _re.sub(r"<[^>]+>", "", page["description_html"] or "")
    page["description_stripped"] = body.get("description_stripped") or page.get("description") or ""
    page["updated_at"] = now_iso()
    pages[page_id] = page
    save_wiki(slug, pages)
    return {
        "description": page.get("description") or "",
        "description_html": page.get("description_html") or "",
        "description_stripped": page.get("description_stripped") or "",
    }


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
