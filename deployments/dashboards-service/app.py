"""
Workspace Dashboards API — compatible with app.plane.so /api/workspaces/{slug}/dashboards/

Reverse-engineered from Business cloud (access: private|public|shared, chart_type/chart_model).
Serves a cloud-matching Dashboards UI (list + detail) for self-hosted Plane without commercial images.
Does NOT include Pilot/Plane AI.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_FILE = Path(os.environ.get("DASHBOARDS_DATA_PATH") or "/tmp/plane-dashboards.json")
CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "*").split(",")
    if o.strip()
]

# access: 0 = private, 1 = public (workspace), cloud maps query strings
ACCESS_PRIVATE = 0
ACCESS_PUBLIC = 1

CHART_TYPES = [
    "BAR_CHART",
    "LINE_CHART",
    "AREA_CHART",
    "PIE_CHART",
    "DONUT_CHART",
    "NUMBER",
    "TABLE_CHART",
    "WORK_ITEMS_TABLE",
    "WORK_ITEMS_STATISTICS",
    "ASSIGNED_WORK_ITEMS_TABLE",
    "CYCLE_PROGRESS",
]
CHART_MODELS = ["BASIC", "STACKED", "GROUPED", "MULTI_LINE", "COMPARISON", "PROGRESS"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_db() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return {"dashboards": {}, "widgets": {}}


def save_db(db: Dict[str, Any]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, indent=2))


def user_key(request: Request) -> str:
    sid = request.cookies.get("session-id") or request.cookies.get("sessionid") or ""
    if sid:
        return f"sess:{sid[:48]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def access_label(access: int) -> str:
    return "public" if access == ACCESS_PUBLIC else "private"


def paginate(items: List[Any], cursor: str = "1000:0:0", per_page: int = 100) -> Dict[str, Any]:
    # cloud cursor format value:offset:is_prev — we use offset only
    try:
        parts = (cursor or "1000:0:0").split(":")
        offset = int(parts[1]) if len(parts) >= 2 else 0
    except Exception:
        offset = 0
    page = items[offset : offset + per_page]
    next_off = offset + per_page
    has_next = next_off < len(items)
    return {
        "prev_cursor": f"1000:{max(0, offset - per_page)}:1" if offset > 0 else "1000:-1:0",
        "cursor": f"1000:{offset}:0",
        "next_cursor": f"1000:{next_off}:0" if has_next else None,
        "prev_page_results": offset > 0,
        "next_page_results": has_next,
        "page_count": len(page),
        "total_results": len(items),
        "total_pages": max(1, (len(items) + per_page - 1) // per_page) if items else 0,
        "results": page,
    }


class DashboardCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    access: Any = 0  # 0 private, 1 public — also accept private/public strings
    logo_props: Optional[Dict[str, Any]] = Field(default_factory=dict)
    project_ids: Optional[List[str]] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    access: Optional[Any] = None
    logo_props: Optional[Dict[str, Any]] = None
    project_ids: Optional[List[str]] = None
    is_favorite: Optional[bool] = None


class WidgetCreate(BaseModel):
    name: str
    chart_type: str
    chart_model: str = "BASIC"
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    x_axis_coord: Optional[int] = None
    y_axis_coord: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    x_axis_property: Optional[str] = None
    y_axis_metric: Optional[str] = None
    group_by: Optional[str] = None


class WidgetUpdate(BaseModel):
    name: Optional[str] = None
    chart_type: Optional[str] = None
    chart_model: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    x_axis_coord: Optional[int] = None
    y_axis_coord: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class LayoutUpdate(BaseModel):
    widgets: List[Dict[str, Any]] = Field(default_factory=list)


app = FastAPI(title="Plane Dashboards (self-hosted)", version="3.0.0-cosmic")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/cosmic-dashboards/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def parse_access(value: Any) -> int:
    if value is None:
        return ACCESS_PRIVATE
    if isinstance(value, int):
        return ACCESS_PUBLIC if value == 1 else ACCESS_PRIVATE
    s = str(value).lower()
    if s in ("public", "1", "workspace"):
        return ACCESS_PUBLIC
    if s in ("shared",):
        # shared is membership share flag; access stays private-like in cloud for owned list
        return ACCESS_PRIVATE
    return ACCESS_PRIVATE


def serialize_dashboard(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": d["id"],
        "deleted_at": None,
        "project_ids": d.get("project_ids") or [],
        "is_favorite": d.get("is_favorite", False),
        "is_shared": d.get("is_shared", False),
        "is_published": d.get("is_published", False),
        "member_access": d.get("member_access"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
        "pql_filters": d.get("pql_filters") or {"json": {}, "stripped": ""},
        "rich_filters": d.get("rich_filters") or {},
        "last_used_filter": d.get("last_used_filter") or "rich_filters",
        "name": d.get("name") or "Untitled",
        "description": d.get("description") or "",
        "filters": d.get("filters") or {},
        "logo_props": d.get("logo_props") or {},
        "access": d.get("access", ACCESS_PRIVATE),
        "archived_at": d.get("archived_at"),
        "created_by": d.get("created_by"),
        "updated_by": d.get("updated_by"),
        "workspace": d.get("workspace"),
        "owned_by": d.get("owned_by"),
        "workspace_slug": d.get("workspace_slug"),
    }


def serialize_widget(w: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": w["id"],
        "deleted_at": None,
        "x_axis_coord": w.get("x_axis_coord", 0),
        "y_axis_coord": w.get("y_axis_coord", 0),
        "height": w.get("height", 1),
        "width": w.get("width", 1),
        "filters": w.get("filters") or {},
        "pql_filters": w.get("pql_filters") or {"json": {}, "stripped": ""},
        "last_used_filter": w.get("last_used_filter") or "rich_filters",
        "chart_type": w.get("chart_type"),
        "chart_model": w.get("chart_model") or "BASIC",
        "x_axis_property": w.get("x_axis_property"),
        "y_axis_metric": w.get("y_axis_metric"),
        "x_axis_date_grouping": w.get("x_axis_date_grouping"),
        "group_by": w.get("group_by"),
        "created_at": w.get("created_at"),
        "updated_at": w.get("updated_at"),
        "name": w.get("name"),
        "config": w.get("config") or {},
        "created_by": w.get("created_by"),
        "updated_by": w.get("updated_by"),
        "workspace": w.get("workspace"),
        "dashboard_id": w.get("dashboard_id"),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "plane-dashboards"}


@app.get("/cosmic-dashboards/ui")
@app.get("/cosmic-dashboards/ui/{full_path:path}")
def ui(full_path: str = ""):
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": "ui missing"}, status_code=500)
    return FileResponse(index, media_type="text/html")


@app.get("/cosmic-dashboards/inject.js")
def inject():
    path = STATIC_DIR / "inject.js"
    return FileResponse(path, media_type="application/javascript")


# ---------------------------------------------------------------------------
# Cloud-compatible API paths
# ---------------------------------------------------------------------------


@app.get("/api/workspaces/{slug}/dashboards/")
def list_dashboards(
    slug: str,
    request: Request,
    access: Optional[str] = Query(None),
    cursor: str = Query("1000:0:0"),
    per_page: int = Query(100),
):
    if access is not None and access not in ("private", "public", "shared"):
        return JSONResponse(
            {
                "message": "Invalid 'access' query param. Must be 'private', 'public', or 'shared'.",
                "code": "INVALID_ACCESS_PARAM",
            },
            status_code=400,
        )
    db = load_db()
    uk = user_key(request)
    rows = [
        serialize_dashboard(d)
        for d in db["dashboards"].values()
        if d.get("workspace_slug") == slug
        and d.get("owner") == uk
        and not d.get("archived_at")
    ]
    if access == "private":
        rows = [d for d in rows if d.get("access") == ACCESS_PRIVATE and not d.get("is_shared")]
    elif access == "public":
        rows = [d for d in rows if d.get("access") == ACCESS_PUBLIC]
    elif access == "shared":
        rows = [d for d in rows if d.get("is_shared")]
    rows.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return paginate(rows, cursor=cursor, per_page=per_page)


@app.post("/api/workspaces/{slug}/dashboards/")
async def create_dashboard(slug: str, body: DashboardCreate, request: Request):
    db = load_db()
    uk = user_key(request)
    did = str(uuid.uuid4())
    access = parse_access(body.access)
    row = {
        "id": did,
        "name": body.name,
        "description": body.description or "",
        "access": access,
        "logo_props": body.logo_props or {},
        "project_ids": body.project_ids or [],
        "is_favorite": False,
        "is_shared": False,
        "is_published": False,
        "member_access": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "pql_filters": {"json": {}, "stripped": ""},
        "rich_filters": {},
        "last_used_filter": "rich_filters",
        "filters": {},
        "archived_at": None,
        "created_by": uk,
        "updated_by": uk,
        "workspace": slug,
        "workspace_slug": slug,
        "owned_by": uk,
        "owner": uk,
    }
    db["dashboards"][did] = row
    save_db(db)
    return serialize_dashboard(row)


@app.get("/api/workspaces/{slug}/dashboards/{dashboard_id}/")
def get_dashboard(slug: str, dashboard_id: str, request: Request):
    db = load_db()
    d = db["dashboards"].get(dashboard_id)
    if not d or d.get("workspace_slug") != slug:
        raise HTTPException(404, "not found")
    return serialize_dashboard(d)


@app.patch("/api/workspaces/{slug}/dashboards/{dashboard_id}/")
async def patch_dashboard(slug: str, dashboard_id: str, body: DashboardUpdate, request: Request):
    db = load_db()
    d = db["dashboards"].get(dashboard_id)
    if not d or d.get("workspace_slug") != slug:
        raise HTTPException(404, "not found")
    data = body.model_dump(exclude_unset=True)
    if "access" in data:
        data["access"] = parse_access(data["access"])
    d.update(data)
    d["updated_at"] = now_iso()
    d["updated_by"] = user_key(request)
    save_db(db)
    return serialize_dashboard(d)


@app.delete("/api/workspaces/{slug}/dashboards/{dashboard_id}/")
def delete_dashboard(slug: str, dashboard_id: str, request: Request):
    db = load_db()
    d = db["dashboards"].get(dashboard_id)
    if not d or d.get("workspace_slug") != slug:
        raise HTTPException(404, "not found")
    del db["dashboards"][dashboard_id]
    # cascade widgets
    for wid, w in list(db["widgets"].items()):
        if w.get("dashboard_id") == dashboard_id:
            del db["widgets"][wid]
    save_db(db)
    return {"ok": True}


@app.get("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/")
def list_widgets(slug: str, dashboard_id: str, request: Request):
    db = load_db()
    d = db["dashboards"].get(dashboard_id)
    if not d or d.get("workspace_slug") != slug:
        raise HTTPException(404, "not found")
    rows = [
        serialize_widget(w)
        for w in db["widgets"].values()
        if w.get("dashboard_id") == dashboard_id
    ]
    rows.sort(key=lambda x: (x.get("y_axis_coord") or 0, x.get("x_axis_coord") or 0))
    return rows


@app.post("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/")
async def create_widget(slug: str, dashboard_id: str, body: WidgetCreate, request: Request):
    db = load_db()
    d = db["dashboards"].get(dashboard_id)
    if not d or d.get("workspace_slug") != slug:
        raise HTTPException(404, "not found")
    if body.chart_type not in CHART_TYPES:
        return JSONResponse(
            {"chart_type": [f"Value error, Invalid chart_type: '{body.chart_type}'. Valid choices: {CHART_TYPES}"]},
            status_code=400,
        )
    if body.chart_model not in CHART_MODELS:
        return JSONResponse(
            {"chart_model": [f"Value error, Invalid chart_model: '{body.chart_model}'. Valid choices: {CHART_MODELS}"]},
            status_code=400,
        )
    existing = [w for w in db["widgets"].values() if w.get("dashboard_id") == dashboard_id]
    wid = str(uuid.uuid4())
    # place on next free grid row
    next_y = max([w.get("y_axis_coord", 0) + w.get("height", 1) for w in existing] or [0])
    default_w, default_h = (1, 1) if body.chart_type == "NUMBER" else (2, 2)
    row = {
        "id": wid,
        "dashboard_id": dashboard_id,
        "name": body.name,
        "chart_type": body.chart_type,
        "chart_model": body.chart_model,
        "config": body.config or {},
        "filters": body.filters or {},
        "pql_filters": {"json": {}, "stripped": ""},
        "last_used_filter": "rich_filters",
        "x_axis_coord": body.x_axis_coord if body.x_axis_coord is not None else 0,
        "y_axis_coord": body.y_axis_coord if body.y_axis_coord is not None else next_y,
        "width": body.width or default_w,
        "height": body.height or default_h,
        "x_axis_property": body.x_axis_property,
        "y_axis_metric": body.y_axis_metric,
        "x_axis_date_grouping": None,
        "group_by": body.group_by,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user_key(request),
        "updated_by": None,
        "workspace": d.get("workspace"),
        "workspace_slug": slug,
    }
    db["widgets"][wid] = row
    d["updated_at"] = now_iso()
    save_db(db)
    return serialize_widget(row)


@app.patch("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/{widget_id}/")
async def patch_widget(
    slug: str, dashboard_id: str, widget_id: str, body: WidgetUpdate, request: Request
):
    db = load_db()
    w = db["widgets"].get(widget_id)
    if not w or w.get("dashboard_id") != dashboard_id:
        raise HTTPException(404, "not found")
    data = body.model_dump(exclude_unset=True)
    if "chart_type" in data and data["chart_type"] not in CHART_TYPES:
        return JSONResponse({"chart_type": ["Invalid chart_type"]}, status_code=400)
    if "chart_model" in data and data["chart_model"] not in CHART_MODELS:
        return JSONResponse({"chart_model": ["Invalid chart_model"]}, status_code=400)
    w.update(data)
    w["updated_at"] = now_iso()
    w["updated_by"] = user_key(request)
    save_db(db)
    return serialize_widget(w)


@app.delete("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/{widget_id}/")
def delete_widget(slug: str, dashboard_id: str, widget_id: str):
    db = load_db()
    w = db["widgets"].get(widget_id)
    if not w or w.get("dashboard_id") != dashboard_id:
        raise HTTPException(404, "not found")
    del db["widgets"][widget_id]
    save_db(db)
    return {"ok": True}


@app.post("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/layout/")
async def update_layout(slug: str, dashboard_id: str, body: LayoutUpdate):
    db = load_db()
    for item in body.widgets:
        wid = item.get("id")
        if not wid or wid not in db["widgets"]:
            continue
        w = db["widgets"][wid]
        if w.get("dashboard_id") != dashboard_id:
            continue
        for k in ("x_axis_coord", "y_axis_coord", "width", "height"):
            if k in item:
                w[k] = item[k]
        w["updated_at"] = now_iso()
    save_db(db)
    return {"ok": True}


@app.get("/api/workspaces/{slug}/dashboards/{dashboard_id}/widgets/{widget_id}/")
def get_widget(slug: str, dashboard_id: str, widget_id: str):
    db = load_db()
    w = db["widgets"].get(widget_id)
    if not w or w.get("dashboard_id") != dashboard_id:
        raise HTTPException(404, "not found")
    # attach simple sample series for charts
    out = serialize_widget(w)
    out["data"] = sample_widget_data(w)
    return out


def sample_widget_data(w: Dict[str, Any]) -> Dict[str, Any]:
    ct = w.get("chart_type")
    if ct == "NUMBER":
        return {"value": 0, "delta": 0, "label": w.get("name") or "Count"}
    if ct in ("BAR_CHART", "LINE_CHART", "AREA_CHART", "PIE_CHART", "DONUT_CHART"):
        return {
            "labels": ["Backlog", "Todo", "In Progress", "Done"],
            "datasets": [{"label": w.get("name") or "Series", "data": [3, 5, 2, 8]}],
        }
    if ct in ("WORK_ITEMS_TABLE", "ASSIGNED_WORK_ITEMS_TABLE", "TABLE_CHART"):
        return {"columns": ["Key", "Title", "State"], "rows": []}
    if ct == "WORK_ITEMS_STATISTICS":
        return {"total": 0, "completed": 0, "pending": 0, "overdue": 0}
    return {"value": 0}


@app.get("/")
def root():
    return {
        "service": "plane-dashboards",
        "ui": "/cosmic-dashboards/ui",
        "compatible_with": "app.plane.so dashboards API",
    }
