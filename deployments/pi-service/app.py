"""
Self-hosted Plane Intelligence (Pilot AI) — API-compatible with pi.plane.so.

Reverse-engineered from Business cloud (app.plane.so / pi.plane.so).
Also serves the Pilot UI shell + inject script for self-hosted web parity.
"""

from __future__ import annotations

import asyncio
import json
import re
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
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
LLM_MODEL = os.environ.get("LLM_MODEL") or "deepseek/deepseek-v4-flash"
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
ATTACHMENTS: Dict[str, Dict[str, Any]] = {}  # id -> meta
ATTACHMENT_BYTES: Dict[str, bytes] = {}

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

# Commercial SPA (app.plane.so mirror) needs CE-missing endpoints:
# permissions, payments/plan/flags, features, roles, enriched workspaces.
# Registered early; Caddy routes those paths here (not to CE API).
from commercial_compat import register_commercial_compat  # noqa: E402

register_commercial_compat(app)

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
    # Prefer the configured OpenRouter/DeepSeek id; map cloud-style names.
    aliases = {
        "deepseek-ai/DeepSeek-V4-Pro": DEFAULT_MODEL_ID if _is_deepseek(DEFAULT_MODEL_ID) else "deepseek/deepseek-v4-flash",
        "deepseek-chat": "deepseek/deepseek-chat",
        "deepseek/deepseek-chat": "deepseek/deepseek-chat",
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



# ---------------------------------------------------------------------------
# Agent tools (executed server-side — never leave raw tool XML in the chat)
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_work_items",
            "description": "Search work items/issues in the workspace by free text (title, identifier, keywords). Always use this before asking the user for an issue ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text, e.g. 'plane ai'"},
                    "project_id": {"type": "string", "description": "Optional project UUID to limit search"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_item",
            "description": "Get full details for one work item by project_id + issue_id (or sequence id with project).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "issue_id": {"type": "string", "description": "Issue UUID"},
                },
                "required": ["project_id", "issue_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_item",
            "description": "Update a work item (description, name/title, priority, etc.). Use after search_work_items found the target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Plain-text description to set (will be wrapped as HTML)",
                    },
                    "description_html": {
                        "type": "string",
                        "description": "Optional raw HTML description",
                    },
                    "name": {"type": "string", "description": "Optional new title"},
                    "priority": {"type": "string", "description": "urgent|high|medium|low|none"},
                },
                "required": ["project_id", "issue_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "List projects in the current workspace",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_work_items",
            "description": "List recent work items in a project (or first project if omitted)",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
]


def _flatten_issue_results(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    results = data.get("results", data.get("data"))
    if isinstance(results, list):
        return [x for x in results if isinstance(x, dict)]
    if isinstance(results, dict):
        out: List[Dict[str, Any]] = []
        for v in results.values():
            if isinstance(v, dict) and isinstance(v.get("results"), list):
                out.extend([x for x in v["results"] if isinstance(x, dict)])
            elif isinstance(v, list):
                out.extend([x for x in v if isinstance(x, dict)])
        return out
    # global search shape: {results: {issue: [...]}}
    nested = data.get("results")
    if isinstance(nested, dict) and isinstance(nested.get("issue"), list):
        return [x for x in nested["issue"] if isinstance(x, dict)]
    return []


def _issue_brief(issue: Dict[str, Any], project_identifier: str = "") -> Dict[str, Any]:
    pid = issue.get("project_id") or issue.get("project")
    ident = project_identifier or issue.get("project__identifier") or ""
    seq = issue.get("sequence_id")
    key = f"{ident}-{seq}" if ident and seq is not None else (str(seq) if seq is not None else "")
    return {
        "id": issue.get("id"),
        "project_id": pid,
        "sequence_id": seq,
        "key": key,
        "name": issue.get("name"),
        "priority": issue.get("priority"),
        "state_id": issue.get("state_id"),
        "description_html": (issue.get("description_html") or "")[:500],
    }


async def _projects(workspace_slug: str, cookie: str, csrf: str) -> List[Dict[str, Any]]:
    res = await plane_api("GET", f"/api/workspaces/{workspace_slug}/projects/", cookie, csrf)
    if res.get("status") != 200:
        return []
    data = res.get("data")
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        rows = data.get("results") or data.get("data") or []
        return [p for p in rows if isinstance(p, dict)] if isinstance(rows, list) else []
    return []


async def tool_search_work_items(
    workspace_slug: str, cookie: str, csrf: str, query: str, project_id: Optional[str] = None
) -> Dict[str, Any]:
    from urllib.parse import quote

    q = (query or "").strip()
    hits: List[Dict[str, Any]] = []
    # 1) Global workspace search
    if q:
        res = await plane_api(
            "GET",
            f"/api/workspaces/{workspace_slug}/search/?search={quote(q)}&query={quote(q)}",
            cookie,
            csrf,
        )
        if res.get("status") == 200:
            for issue in _flatten_issue_results(res.get("data")):
                hits.append(_issue_brief(issue))

    # 2) Per-project list + local filter (more reliable)
    projects = await _projects(workspace_slug, cookie, csrf)
    proj_map = {p.get("id"): p for p in projects}
    targets = [p for p in projects if not project_id or p.get("id") == project_id]
    ql = q.lower()
    for p in targets[:10]:
        pid = p.get("id")
        if not pid:
            continue
        res = await plane_api(
            "GET",
            f"/api/workspaces/{workspace_slug}/projects/{pid}/issues/?per_page=100",
            cookie,
            csrf,
        )
        if res.get("status") != 200:
            continue
        for issue in _flatten_issue_results(res.get("data")):
            name = (issue.get("name") or "").lower()
            seq = str(issue.get("sequence_id") or "")
            ident = (p.get("identifier") or "").lower()
            key = f"{ident}-{seq}"
            if not ql or ql in name or ql in seq or ql in key or any(tok in name for tok in ql.split() if len(tok) > 2):
                brief = _issue_brief(issue, p.get("identifier") or "")
                brief["project_id"] = pid
                brief["project_name"] = p.get("name")
                brief["project_identifier"] = p.get("identifier")
                # dedupe by id
                if not any(h.get("id") == brief.get("id") for h in hits):
                    hits.append(brief)

    # Prefer stronger title matches first
    if ql:
        hits.sort(key=lambda h: (0 if ql in (h.get("name") or "").lower() else 1, (h.get("name") or "")))
    return {"count": len(hits), "results": hits[:25]}


async def tool_get_work_item(
    workspace_slug: str, cookie: str, csrf: str, project_id: str, issue_id: str
) -> Dict[str, Any]:
    res = await plane_api(
        "GET",
        f"/api/workspaces/{workspace_slug}/projects/{project_id}/issues/{issue_id}/",
        cookie,
        csrf,
    )
    return res


async def tool_update_work_item(
    workspace_slug: str,
    cookie: str,
    csrf: str,
    project_id: str,
    issue_id: str,
    description: Optional[str] = None,
    description_html: Optional[str] = None,
    name: Optional[str] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if priority is not None:
        payload["priority"] = priority
    if description_html is not None:
        payload["description_html"] = description_html
    elif description is not None:
        # simple paragraph HTML
        safe = (
            description.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n\n", "</p><p>")
            .replace("\n", "<br/>")
        )
        payload["description_html"] = f"<p>{safe}</p>"
    if not payload:
        return {"status": 400, "error": "No fields to update"}
    res = await plane_api(
        "PATCH",
        f"/api/workspaces/{workspace_slug}/projects/{project_id}/issues/{issue_id}/",
        cookie,
        csrf,
        payload,
    )
    return res


async def dispatch_agent_tool(
    name: str,
    args: Dict[str, Any],
    workspace_slug: str,
    cookie: str,
    csrf: str,
) -> Any:
    try:
        if name in ("search_work_items", "search_issues", "search_issue"):
            return await tool_search_work_items(
                workspace_slug, cookie, csrf, args.get("query") or "", args.get("project_id")
            )
        if name in ("get_work_item", "get_issue"):
            return await tool_get_work_item(
                workspace_slug, cookie, csrf, args.get("project_id") or "", args.get("issue_id") or ""
            )
        if name in ("update_work_item", "update_issue", "edit_work_item"):
            return await tool_update_work_item(
                workspace_slug,
                cookie,
                csrf,
                args.get("project_id") or "",
                args.get("issue_id") or "",
                description=args.get("description"),
                description_html=args.get("description_html"),
                name=args.get("name") or args.get("title"),
                priority=args.get("priority"),
            )
        if name == "list_projects":
            projects = await _projects(workspace_slug, cookie, csrf)
            return {
                "results": [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "identifier": p.get("identifier"),
                    }
                    for p in projects
                ]
            }
        if name in ("list_work_items", "list_issues"):
            projects = await _projects(workspace_slug, cookie, csrf)
            pid = args.get("project_id") or (projects[0].get("id") if projects else None)
            if not pid:
                return {"error": "No project found"}
            res = await plane_api(
                "GET",
                f"/api/workspaces/{workspace_slug}/projects/{pid}/issues/?per_page={int(args.get('limit') or 20)}",
                cookie,
                csrf,
            )
            issues = _flatten_issue_results(res.get("data"))
            proj = next((p for p in projects if p.get("id") == pid), {})
            return {
                "project_id": pid,
                "results": [_issue_brief(i, proj.get("identifier") or "") for i in issues[:30]],
            }
        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def strip_tool_call_artifacts(text: str) -> str:
    """Remove leaked native tool-call markup (DSML / XML / JSON tool blocks) from model output."""
    if not text:
        return text
    cleaned = text
    patterns = [
        # ASCII control-token style: <|DSML|tool_calls> ...
        r"<\|DSML\|[^>]*>.*?(?:</\|DSML\|[^>]*>|$)",
        r"<\|tool_calls?\|?>.*?(?:<\|/?tool_calls?\|?>|$)",
        # Fullwidth/unicode fence style often emitted by Grok/DeepSeek: <｜DSML｜...>
        r"<｜DSML｜[^>]*>.*?(?:</｜DSML｜[^>]*>|$)",
        r"<｜[^｜]*tool_calls?[^｜]*｜>.*?(?:</｜[^｜]*｜>|$)",
        r"<tool_call>.*?</tool_call>",
        r"<tool_calls>.*?</tool_calls>",
        r"```(?:json|xml|tool)?\s*\{[^{}]*\"name\"\s*:\s*\"(?:search_issues|search_work_items)\".*?\}```",
        r"invoke\s+name=\"[^\"]+\".*?(?:</invoke>|$)",
        r"<parameter\s+name=\"[^\"]+\">.*?</parameter>",
        # Bare function-call dumps without fences
        r"(?is)(?:tool_calls?|function_call)\s*[:=]\s*\{.*?\}",
        r"(?is)\b(?:search_issues|search_work_items|update_work_item|get_work_item)\s*\(\s*\{.*?\}\s*\)",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.I | re.S)
    # Drop orphaned function-call lines / leftover parameter noise
    cleaned = re.sub(
        r"(?m)^\s*(?:search_issues|search_work_items|update_work_item|get_work_item|list_projects|list_work_items)\s*$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?m)^\s*(?:workspace_slug|query|project_id|issue_id)\s*[:=].*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    # Convert accidental HTML-only assistant blobs to plain text
    # e.g. '<p class="font-normal">Hi</p>' should render as 'Hi'
    if re.search(r"<\s*(p|div|span|br|strong|em|ul|ol|li|h[1-6])\b", cleaned, re.I):
        plain = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.I)
        plain = re.sub(r"</p\s*>", "\n\n", plain, flags=re.I)
        plain = re.sub(r"<[^>]+>", "", plain)
        plain = re.sub(r"&nbsp;", " ", plain)
        plain = re.sub(r"&amp;", "&", plain)
        plain = re.sub(r"&lt;", "<", plain)
        plain = re.sub(r"&gt;", ">", plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        if plain:
            cleaned = plain
    # If nothing useful remains after stripping tool junk, say so clearly
    if not cleaned or cleaned in ("Thoughts", "Let me search for it.", "Let me search for it"):
        return ""
    return cleaned


async def llm_complete(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Any = None,
) -> Dict[str, Any]:
    """Non-streaming chat completion (for tool loop)."""
    if not LLM_API_KEY:
        return {"content": "Pilot AI is not configured: missing LLM_API_KEY.", "tool_calls": []}
    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": f"https://{APP_DOMAIN}",
        "X-Title": "Plane Intelligence Self-Hosted",
    }
    body: Dict[str, Any] = {
        "model": resolve_llm(model),
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, headers=headers, json=body)
            if r.status_code >= 400:
                return {
                    "content": f"LLM error ({r.status_code}): {r.text[:400]}",
                    "tool_calls": [],
                }
            data = r.json()
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            return {
                "content": msg.get("content") or "",
                "tool_calls": msg.get("tool_calls") or [],
                "raw": msg,
            }
    except Exception as e:
        return {"content": f"LLM request failed: {e}", "tool_calls": []}


async def run_agent_with_tools(
    messages: List[Dict[str, Any]],
    model: str,
    workspace_slug: str,
    cookie: str,
    csrf: str,
    max_rounds: int = 4,
) -> str:
    """Tool-calling loop then final natural-language answer (no raw tool markup)."""
    msgs: List[Dict[str, Any]] = list(messages)
    for _ in range(max_rounds):
        result = await llm_complete(msgs, model, tools=AGENT_TOOLS, tool_choice="auto")
        tool_calls = result.get("tool_calls") or []
        content = result.get("content") or ""
        if not tool_calls:
            return strip_tool_call_artifacts(content)

        # Append assistant message with tool_calls for the API conversation
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content or None}
        assistant_msg["tool_calls"] = tool_calls
        msgs.append(assistant_msg)

        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            args = _parse_args(fn.get("arguments"))
            tool_result = await dispatch_agent_tool(name, args, workspace_slug, cookie, csrf)
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or str(uuid.uuid4()),
                    "name": name,
                    "content": json.dumps(tool_result, ensure_ascii=False)[:8000],
                }
            )

    # Final answer without tools
    final = await llm_complete(msgs + [
        {
            "role": "user",
            "content": "Using the tool results above, give the final answer to the user. Do not emit tool calls.",
        }
    ], model, tools=None)
    return strip_tool_call_artifacts(final.get("content") or "")


async def execute_plane_tools(
    mode: str,
    query: str,
    workspace_slug: Optional[str],
    cookie: str,
    csrf: str,
) -> str:
    """Keyword-triggered tools + pre-search when user mentions work items / descriptions."""
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
            "set ",
            "change ",
            "description",
        )
    )

    # Proactive search when the user references a work item without giving an ID
    wants_item = any(
        k in q
        for k in (
            "work item",
            "issue",
            "ticket",
            "task",
            "description",
            "find ",
            "search ",
            "plane ai",
            "update ",
            "edit ",
            "add a description",
            "add description",
        )
    )
    if wants_item:
        # Extract quoted title or last free-text phrase after verbs
        search_q = query
        m = re.search(r'["“](.+?)["”]', query)
        if m:
            search_q = m.group(1)
        else:
            for sep in (
                "work item ",
                "issue ",
                "task ",
                "called ",
                "named ",
                "titled ",
                "for ",
                "to ",
            ):
                if sep in q:
                    search_q = query[q.index(sep) + len(sep) :].strip(" .\"'")
                    break
        # Strip trailing "work item" noise
        search_q = re.sub(
            r"\b(work item|issue|task|description|please|the|a|an)\b",
            " ",
            search_q,
            flags=re.I,
        ).strip()
        if len(search_q) >= 2:
            found = await tool_search_work_items(workspace_slug, cookie, csrf, search_q)
            notes.append(f"search_work_items({search_q!r}) => {json.dumps(found, ensure_ascii=False)[:3500]}")

            # Auto-update description if clearly requested and we found a match
            if can_mutate and found.get("results") and any(
                k in q for k in ("description", "describe", "add desc", "set desc", "write desc")
            ):
                target = found["results"][0]
                # Extract description text after "description" keywords
                desc = None
                for pat in (
                    r"description[:\s]+(.+)$",
                    r"describe (?:it|this|the work item)?\s*(?:as|with)?\s*[:\-]?\s*(.+)$",
                    r"add (?:a )?description\s*[:\-]\s*(.+)$",
                ):
                    mm = re.search(pat, query, flags=re.I | re.S)
                    if mm:
                        desc = mm.group(1).strip()
                        break
                if desc and target.get("project_id") and target.get("id"):
                    upd = await tool_update_work_item(
                        workspace_slug,
                        cookie,
                        csrf,
                        target["project_id"],
                        target["id"],
                        description=desc,
                    )
                    notes.append(
                        f"update_work_item({target.get('key') or target.get('id')}) => {json.dumps(upd)[:1500]}"
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
@app.get("/api/v1/health/")
@app.get("/api/v1/health")
@app.get("/health/")
@app.get("/live/")
@app.get("/ready/")
def healthz():
    return {
        "ok": True,
        "status": "alive",
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
@app.get("/api/v1/chat/get-models")
def get_models(workspace_id: Optional[str] = None):
    return {"models": model_catalog()}


@app.get("/api/v1/models")
@app.get("/api/v1/models/")
@app.get("/api/v1/models/list/")
@app.get("/api/v1/models/list")
def get_models_alias(workspace_id: Optional[str] = None):
    """Official mobile probes /api/v1/models; cloud PI also exposes get-models under chat/."""
    catalog = model_catalog()
    # Some clients expect {models:[...]}, others a bare list
    return {"models": catalog, "results": catalog, "count": len(catalog)}


@app.get("/api/v1/chat/start/auth-check/")
@app.get("/api/v1/chat/start/auth-check")
def auth_check(
    workspace_slug: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
):
    """Cloud requires workspace context; accept slug and/or id like pi.plane.so."""
    has = False
    for c in CHATS.values():
        if not c.get("messages") and not c.get("dialogue"):
            continue
        if workspace_slug and c.get("workspace_slug") == workspace_slug:
            has = True
            break
        if workspace_id and c.get("workspace_id") == workspace_id:
            has = True
            break
    return {"is_authorized": True, "oauth_url": None, "has_chats": has}


@app.get("/api/v1/flags/")
@app.get("/api/v1/flags")
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
            # Mobile product surface — Pilot AI + app rail + pages
            "PI_CHAT": True,
            "PI_CHAT_MOBILE": True,
            "PI_DEDUPE": True,
            "PI_DEDUPE_MOBILE": True,
            "PI_CONVERSE": True,
            "PI_ACTIONS": True,
            "APP_RAIL": True,
            "WORKSPACE_PAGES": True,
            "NESTED_PAGES": True,
            "PAGE_PUBLISH": True,
            "EDITOR_AI_OPS": True,
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
        "CRITICAL RULES: "
        "1) NEVER invent or print tool-call XML/JSON/markup (no search_issues, no DSML, no tool_calls tags). "
        "2) NEVER ask the user for an issue ID or project if you can look it up with tools. "
        "3) When the user asks to edit/find a work item by name (e.g. 'plane ai'), call search_work_items first, then act. "
        "4) Prefer doing the action over asking clarifying questions. "
        "In Ask mode: answer questions about the workspace. "
        "In Build mode: create and edit work items, pages, and plans using tools; explain results. "
        "In Autopilot mode: proactively execute multi-step changes with tools. "
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
        reasoning_log = []

        async def emit_reason(header: str, content: str = ""):
            reasoning_log.append({"chunk_type": "reasoning", "header": header, "content": content})
            yield_payload = "event: reasoning\ndata: " + json.dumps({"header": header, "content": content}) + "\n\n"
            return yield_payload

        # Prefer tool-calling agent for action/find queries; stream the final answer
        q_lower = (job.get("query") or "").lower()
        # Always tool-call when workspace is known for action/find language — including
        # short follow-ups like "just find it yourself?" that rely on chat history.
        use_tools = bool(job.get("workspace_slug")) and (
            any(
                k in q_lower
                for k in (
                    "work item",
                    "issue",
                    "task",
                    "description",
                    "find",
                    "search",
                    "update",
                    "edit",
                    "add ",
                    "create",
                    "plane ai",
                    "module",
                    "project",
                    "list ",
                    "show ",
                    "assign",
                    "priority",
                    "yourself",
                    "look it",
                    "look up",
                    "look for",
                    "locate",
                    "where is",
                    "which issue",
                    "which work",
                )
            )
            or (job.get("mode") or "").lower() in ("build", "autopilot")
        )

        # Progress messages timed to what is actually happening right now
        if use_tools:
            h = "\n\nSearching the workspace for matching work items...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.15)
            h = "\n\nGathering context and deciding next steps...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.1)
        else:
            h = "\n\nReading your question and workspace context...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.1)

        full = []
        if use_tools:
            h = "\n\nRunning tools and applying changes...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            try:
                answer = await run_agent_with_tools(
                    msgs,
                    job.get("llm") or DEFAULT_MODEL_ID,
                    job.get("workspace_slug") or "",
                    cookie,
                    csrf,
                )
            except Exception as e:
                answer = f"Agent error: {e}"
            answer = strip_tool_call_artifacts(answer)
            h = "\n\nGenerating final response...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.05)
            # Fake-stream for UI parity
            step = 24
            for i in range(0, len(answer), step):
                chunk = answer[i : i + step]
                full.append(chunk)
                yield "event: delta\ndata: " + json.dumps({"chunk": chunk}) + "\n\n"
                await asyncio.sleep(0)
        else:
            h = "\n\nGenerating final response...\n\n"
            reasoning_log.append({"chunk_type": "reasoning", "header": h, "content": ""})
            yield "event: reasoning\ndata: " + json.dumps({"header": h, "content": ""}) + "\n\n"
            await asyncio.sleep(0.05)
            async for chunk in llm_stream(msgs, job.get("llm") or DEFAULT_MODEL_ID):
                chunk = strip_tool_call_artifacts(chunk) if ("<" in chunk or "search_issues" in chunk) else chunk
                if not chunk:
                    continue
                full.append(chunk)
                yield "event: delta\ndata: " + json.dumps({"chunk": chunk}) + "\n\n"
                await asyncio.sleep(0)

        answer = strip_tool_call_artifacts("".join(full))
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
        f"Workspace: {ws or 'unknown'}. Mode: {mode}. "
        "Never emit raw tool-call XML. Use tools to find work items yourself — do not ask for issue IDs."
    )
    ws_ctx = await gather_workspace_context(ws, cookie, csrf)
    if ws_ctx:
        system += "\n\n" + ws_ctx
    tool_notes = await execute_plane_tools(mode, query, ws, cookie, csrf)
    if tool_notes:
        system += "\n\nTool results:\n" + tool_notes
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": query}]
    if ws:
        answer = await run_agent_with_tools(msgs, llm, ws, cookie, csrf)
    else:
        chunks: List[str] = []
        async for chunk in llm_stream(msgs, llm):
            chunks.append(chunk)
        answer = "".join(chunks)
    answer = strip_tool_call_artifacts(answer)
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
    # Prefer DeepSeek-generated short title; fall back to truncated query
    title = ""
    if LLM_API_KEY and q:
        try:
            result = await llm_complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate a concise chat title (max 6 words) for the user message. "
                            "Return ONLY the title text — no quotes, no punctuation fluff, no HTML."
                        ),
                    },
                    {"role": "user", "content": str(q)[:500]},
                ],
                DEFAULT_MODEL_ID,
            )
            title = strip_tool_call_artifacts((result.get("content") or "").strip())
            title = title.strip(" \"'`")
            title = title.split("\n")[0].strip()[:80]
        except Exception:
            title = ""
    if not title:
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
async def list_attachments(chat_id: Optional[str] = None):
    rows = [
        a for a in ATTACHMENTS.values()
        if not chat_id or a.get("chat_id") == chat_id
    ]
    return {"attachments": rows}


@app.post("/api/v1/attachments/upload-attachment/")
async def upload_attachment(
    request: Request,
    file: Optional[UploadFile] = File(None),
    chat_id: Optional[str] = Form(None),
    workspace_id: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    file_size: Optional[str] = Form(None),
):
    """Accept multipart image/file uploads for Pilot chat (SPA requires {id})."""
    upload = file
    content: bytes = b""
    fname = filename or "upload.bin"
    content_type = "application/octet-stream"
    cid = chat_id or ""

    if upload is not None:
        content = await upload.read()
        fname = filename or upload.filename or fname
        content_type = upload.content_type or content_type
    else:
        # Fallback: parse form manually (some clients)
        try:
            form = await request.form()
            upload2 = form.get("file") or form.get("attachment") or form.get("image")
            cid = str(form.get("chat_id") or form.get("chatId") or cid or "")
            if upload2 is not None and hasattr(upload2, "read"):
                content = await upload2.read()  # type: ignore[misc]
                fname = getattr(upload2, "filename", None) or fname
                content_type = getattr(upload2, "content_type", None) or content_type
        except Exception:
            raw = await request.body()
            content = raw or b""

    if not content:
        # Still succeed with empty placeholder so UI unsticks; SPA checks i.id
        content = b""

    att_id = str(uuid.uuid4())
    ATTACHMENT_BYTES[att_id] = content
    meta = {
        "id": att_id,
        "attachment_id": att_id,
        "asset_id": att_id,
        "chat_id": str(cid) if cid else None,
        "workspace_id": workspace_id,
        "name": fname,
        "filename": fname,
        "content_type": content_type,
        "mime_type": content_type,
        "size": len(content),
        "file_size": len(content),
        "url": f"/api/v1/attachments/{att_id}/",
        "asset_url": f"/api/v1/attachments/{att_id}/",
        "created_at": now_iso(),
        "status": "uploaded",
    }
    ATTACHMENTS[att_id] = meta
    return meta


@app.get("/api/v1/attachments/{attachment_id}/")
async def get_attachment(attachment_id: str):
    meta = ATTACHMENTS.get(attachment_id)
    data = ATTACHMENT_BYTES.get(attachment_id)
    if not meta or data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(
        content=data,
        media_type=meta.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{meta.get("filename") or "file"}"'},
    )


@app.post("/api/v1/transcription/")
@app.post("/api/v1/transcribe/")
@app.post("/api/v1/audio/transcriptions/")
@app.post("/api/v1/chat/transcribe/")
async def transcribe_audio(request: Request):
    """Whisper transcription via OpenRouter using the same LLM API key."""
    if not LLM_API_KEY:
        return JSONResponse({"error": "LLM_API_KEY not configured"}, status_code=503)
    form = await request.form()
    upload = form.get("file") or form.get("audio") or form.get("voice")
    if upload is None:
        raw = await request.body()
        if not raw:
            return JSONResponse({"error": "no audio"}, status_code=400)
        content = raw
        filename = "audio.webm"
        content_type = request.headers.get("content-type") or "audio/webm"
    else:
        content = await upload.read()  # type: ignore[attr-defined]
        filename = getattr(upload, "filename", None) or "audio.webm"
        content_type = getattr(upload, "content_type", None) or "audio/webm"

    # OpenRouter OpenAI-compatible audio transcriptions
    url = f"{LLM_BASE_URL}/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "HTTP-Referer": f"https://{APP_DOMAIN}",
        "X-Title": "Plane Intelligence Transcription",
    }
    files = {"file": (filename, content, content_type)}
    data = {"model": "openai/whisper-large-v3"}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, headers=headers, files=files, data=data)
        if r.status_code >= 400:
            # Fallback: some OpenRouter paths use chat with audio input
            return JSONResponse(
                {"error": f"transcription failed: {r.status_code}", "detail": r.text[:400]},
                status_code=502,
            )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text}
        text = body.get("text") if isinstance(body, dict) else str(body)
        return {"text": text or "", "transcript": text or "", "result": text or ""}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/v1/chat/search/")
async def chat_search(
    request: Request,
    q: Optional[str] = Query(None),
    workspace_id: Optional[str] = None,
):
    query = (q or "").lower()
    uk = user_key(request)
    results = []
    for c in CHATS.values():
        if c.get("owner") != uk:
            continue
        if workspace_id and c.get("workspace_id") != workspace_id:
            continue
        title = c.get("title") or ""
        if query and query not in title.lower():
            continue
        results.append(
            {
                "id": c["chat_id"],
                "title": title,
                "snippet": title,
                "match_type": "title",
                "message_id": None,
            }
        )
    return {"next_cursor": None, "count": len(results), "results": results}


@app.post("/api/v1/pql/translate/")
@app.post("/api/v1/pql/translate")
async def pql_translate(request: Request):
    """AI Filter — natural language → Plane query language via DeepSeek."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    query = (body.get("query") or body.get("prompt") or body.get("text") or "").strip()
    if not query:
        return {"pql": "", "entities": {}, "query": "", "filters": {}, "result": ""}
    q = query.lower()
    parts = []
    # Deterministic mappings so AI Filter works even if LLM is slow/unavailable
    if any(x in q for x in ("assigned to me", "my issues", "my work", "assignee is me", "i am assigned")):
        parts.append("assignee = me")
    if "unassigned" in q or "no assignee" in q:
        parts.append("assignee = null")
    if any(x in q for x in ("high priority", "priority high", "p0", "urgent")):
        parts.append("priority = high")
    if "medium priority" in q:
        parts.append("priority = medium")
    if "low priority" in q:
        parts.append("priority = low")
    if any(x in q for x in ("in progress", "started", "doing")):
        parts.append("state_group = started")
    if any(x in q for x in ("todo", "to do", "unstarted", "not started")):
        parts.append("state_group = unstarted")
    if "backlog" in q:
        parts.append("state_group = backlog")
    if any(x in q for x in ("done", "completed", "finished", "closed")):
        parts.append("state_group = completed")
    if "cancel" in q:
        parts.append("state_group = cancelled")
    if "bug" in q:
        parts.append('label = "bug"')
    if any(x in q for x in ("created by me", "i created", "my created")):
        parts.append("created_by = me")
    pql = " AND ".join(parts) if parts else ""
    if not pql and LLM_API_KEY:
        system = (
            "Convert natural language to Plane PQL. Return ONLY a PQL expression, no markdown. "
            "Valid fields: assignee, priority, state_group, label, created_by, target_date. "
            "Examples: assignee = me AND priority = high ; state_group = started ; label = \"bug\""
        )
        try:
            result = await llm_complete(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                DEFAULT_MODEL_ID,
            )
            pql = strip_tool_call_artifacts((result.get("content") or "").strip())
            pql = pql.strip("`").strip().strip('"').strip("'")
            if pql.lower().startswith("pql:"):
                pql = pql[4:].strip()
            # drop fences / explanations
            pql = pql.split("\n")[0].strip()
        except Exception:
            pql = ""
    if not pql:
        # last resort: free-text contains match so the filter still does something
        safe = query.replace('"', "")
        pql = f'name ~ "{safe}"'
    # entities required by SPA pql→html converter (can be empty object)
    return {"pql": pql, "entities": {}, "query": pql, "filters": {}, "result": pql, "text": pql}


# Soft stubs so commercial UI feature calls do not hard-fail
@app.post("/api/v1/pages/summarize/")
@app.post("/api/v1/pages-edits/")
@app.post("/api/v1/pages/blocks/generate/")
@app.post("/api/v1/pages/blocks/revision/")
@app.post("/api/v1/wi-desc-edits/")
@app.post("/api/v1/predictions/{entity}/")
@app.post("/api/v1/dupes/issues/")
@app.post("/api/v1/dupes/issues/feedback/")
@app.post("/api/v1/chat-ctas/save-as-page/")
@app.post("/api/v1/feedback/{usage_type}/")
async def soft_ai_stub(request: Request, entity: Optional[str] = None, usage_type: Optional[str] = None):
    return {"ok": True, "status": "unsupported_on_selfhost", "result": None, "items": []}


@app.get("/api/v1/pages/blocks/types/")
@app.get("/api/v1/pages/blocks/revision/types/")
async def page_block_types():
    return {"types": []}


@app.get("/api/v1/pages/{page_id}/blocks/")
@app.get("/api/v1/pages/blocks/{block_id}/")
@app.get("/api/v1/pages/embeds/{embed_id}/")
async def page_blocks_empty(page_id: Optional[str] = None, block_id: Optional[str] = None, embed_id: Optional[str] = None):
    return {"blocks": [], "results": []}


@app.get("/api/v1/skills/{skill_id}/")
async def get_skill(skill_id: str, workspace_slug: Optional[str] = None):
    for s in SKILLS_SEED or []:
        if str(s.get("id")) == str(skill_id) or s.get("slug") == skill_id:
            return s
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/assets/en-i18n-fallbacks-v7.js")
@app.get("/cosmic-pilot/en-i18n-fallbacks-v7.js")
def en_i18n_fallbacks():
    path = STATIC_DIR / "en-i18n-fallbacks-v7.js"
    if path.exists():
        return FileResponse(path, media_type="application/javascript")
    return JSONResponse({"error": "missing"}, status_code=404)


@app.get("/")
def root():
    return {
        "service": "plane-intelligence",
        "compatible_with": "pi.plane.so",
        "llm_configured": bool(LLM_API_KEY),
        "default_model": DEFAULT_MODEL_ID,
        "ui": "/cosmic-pilot/ui",
        "inject": "/cosmic-pilot/inject.js",
        "mode": "cloud-ui-mirror + local-llm",
    }
