"""
Commercial app.plane.so SPA ↔ Plane CE API compatibility.

Synthesizes Business-only endpoints CE lacks. Never mutates Postgres.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DATA_DIR = Path(__file__).resolve().parent / "data"
PLANE_API_BASE = (os.environ.get("PLANE_API_BASE") or "http://api:8000").rstrip("/")


def _load(name: str, default: Any) -> Any:
    path = DATA_DIR / name
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


GRANTS_BY_RELATION: Dict[str, Dict[str, Any]] = _load("grants_by_relation.json", {})
OWNER_PERMISSIONS: Dict[str, Any] = _load(
    "owner_permissions.json",
    {"relation": "owner", "permission_grants": []},
)
BUSINESS_FLAGS: Dict[str, Any] = _load("business_flags.json", {"values": {}})
WORKSPACE_ROLES: List[Dict[str, Any]] = _load("workspace_roles.json", [])

PREF_STORE: Dict[str, Dict[str, Any]] = {}

SELFHOST_PLAN = {
    "is_cancelled": False,
    "purchased_seats": 9999,
    "current_period_end_date": None,
    "interval": "YEARLY",
    "product": "BUSINESS",
    "is_offline_payment": True,
    "trial_end_date": None,
    "has_activated_free_trial": False,
    "has_added_payment_method": True,
    "subscription": None,
    "is_self_managed": True,
    "is_on_trial": False,
    "is_trial_allowed": False,
    "remaining_trial_days": 0,
    "has_upgraded": True,
    "show_payment_button": False,
    "show_trial_banner": False,
    "free_seats": 9999,
    "occupied_seats": 1,
    "show_seats_banner": False,
    "current_period_start_date": None,
    "is_trial_ended": False,
    "billable_members": 1,
    "is_free_member_count_exceeded": False,
    "can_delete_workspace": True,
    "show_verification_failed_banner": False,
}


def _forward_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key in ("cookie", "authorization", "x-csrftoken", "x-forwarded-for", "user-agent", "accept"):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    csrf = request.cookies.get("csrftoken")
    if csrf and "x-csrftoken" not in {k.lower() for k in headers}:
        headers["X-CSRFToken"] = csrf
    return headers


async def ce_get(path: str, request: Request, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Any, Dict[str, str]]:
    url = f"{PLANE_API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url, headers=_forward_headers(request))
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body, dict(r.headers)


async def ce_post(
    path: str,
    request: Request,
    *,
    json_body: Any = None,
    form_body: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Any, Dict[str, str]]:
    """POST to CE API (JSON or form). Used for mobile auth shims."""
    url = f"{PLANE_API_BASE}{path}"
    headers = _forward_headers(request)
    # Prefer content-type matching payload
    headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        if form_body is not None:
            r = await client.post(url, headers=headers, data=form_body)
        else:
            headers["Content-Type"] = "application/json"
            r = await client.post(url, headers=headers, json=json_body if json_body is not None else {})
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body, dict(r.headers)


def relation_for_ce_role(role: Optional[int]) -> str:
    if role is None:
        return "guest"
    if role >= 20:
        return "owner"
    if role >= 15:
        return "member"
    return "guest"


def permissions_payload(relation: str) -> Dict[str, Any]:
    packed = GRANTS_BY_RELATION.get(relation)
    if packed and packed.get("permission_grants"):
        return {
            "relation": packed.get("relation") or relation,
            "permission_grants": list(packed["permission_grants"]),
        }
    if relation in ("owner", "admin"):
        return {
            "relation": relation,
            "permission_grants": list(OWNER_PERMISSIONS.get("permission_grants") or []),
        }
    return {
        "relation": relation,
        "permission_grants": list(OWNER_PERMISSIONS.get("permission_grants") or []),
    }


def features_payload(workspace_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": workspace_id or "selfhost-features",
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_project_grouping_enabled": False,
        "is_initiative_enabled": False,
        "is_teams_enabled": False,
        "is_customer_enabled": False,
        "is_wiki_enabled": True,
        "is_pi_enabled": True,
        "is_release_enabled": False,
        "is_milestones_enabled": False,
        "is_work_item_types_enabled": False,
        "is_workitem_hierarchy_enabled": False,
        "is_cross_project_sub_work_items_enabled": True,
        "work_item_type_default_level": 0,
        "is_state_duration_enabled": False,
        "created_by": None,
        "updated_by": None,
        "workspace": workspace_id,
    }



def as_page(items: Any, total: Optional[int] = None) -> Dict[str, Any]:
    """Commercial SPA list loaders expect {results, next_cursor, total_count} not bare arrays."""
    if isinstance(items, dict) and "results" in items:
        return items
    if not isinstance(items, list):
        items = []
    return {
        "results": items,
        "next_cursor": None,
        "prev_cursor": None,
        "next_page_results": False,
        "prev_page_results": False,
        "count": len(items),
        "total_count": total if total is not None else len(items),
        "total_pages": 1,
        "total_results": total if total is not None else len(items),
        "extra_stats": None,
        "grouped_by": None,
        "sub_grouped_by": None,
    }

def enrich_workspace(ws: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ws)
    role = out.get("role")
    try:
        role_i = int(role) if role is not None else None
    except Exception:
        role_i = None
    relation = relation_for_ce_role(role_i)
    if role_i is not None and role_i >= 20:
        out["role_slug"] = "owner"
    else:
        out.setdefault("role_slug", relation)
    out.setdefault("current_plan", "BUSINESS")
    out.setdefault("is_on_trial", False)
    return out


def project_role_relation(member_role: Any) -> str:
    try:
        r = int(member_role)
    except Exception:
        r = 15
    if r >= 20:
        return "admin"
    if r >= 15:
        return "member"
    return "guest"


def to_project_lite(p: Dict[str, Any]) -> Dict[str, Any]:
    """Map CE project row → commercial projects-lite shape."""
    role = p.get("member_role")
    relation = project_role_relation(role)
    perms = permissions_payload("owner" if relation == "admin" else relation)
    # project relation uses admin/member/guest not owner
    if relation == "admin":
        perms = permissions_payload("admin") if GRANTS_BY_RELATION.get("admin") else permissions_payload("owner")
        perms = {**perms, "relation": "admin"}
    else:
        perms = {**permissions_payload(relation), "relation": relation}

    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "identifier": p.get("identifier"),
        "sort_order": p.get("sort_order"),
        "logo_props": p.get("logo_props"),
        "member_role": role if role is not None else 20,
        "intake_count": p.get("intake_count") or 0,
        "is_favorite": bool(p.get("is_favorite", False)),
        "archived_at": p.get("archived_at"),
        "workspace": p.get("workspace"),
        "cycle_view": bool(p.get("cycle_view", True)),
        "issue_views_view": bool(p.get("issue_views_view", True)),
        "module_view": bool(p.get("module_view", True)),
        "page_view": bool(p.get("page_view", True)),
        "intake_view": bool(p.get("intake_view", p.get("inbox_view", False))),
        "priority": p.get("priority"),
        "project_lead": p.get("project_lead"),
        "start_date": p.get("start_date"),
        "state_id": p.get("state_id"),
        "target_date": p.get("target_date"),
        "created_at": p.get("created_at"),
        "created_by": p.get("created_by"),
        "updated_at": p.get("updated_at"),
        "updated_by": p.get("updated_by"),
        "network": p.get("network"),
        "_permissions": {
            "relation": perms.get("relation"),
            "permission_grants": perms.get("permission_grants") or [],
        },
    }


def project_features_row(project_id: str) -> Dict[str, Any]:
    return {
        "id": project_id,
        "project_id": project_id,
        "is_project_updates_enabled": False,
        "is_epic_enabled": False,
        "is_issue_type_enabled": False,
        "is_time_tracking_enabled": True,
        "is_workflow_enabled": False,
        "is_milestone_enabled": False,
        "is_automated_cycle_enabled": False,
        "is_parallel_cycles_enabled": False,
        "is_manually_start_end_cycles_enabled": False,
        # CE-ish feature toggles the UI also reads sometimes
        "is_cycle_enabled": True,
        "is_module_enabled": True,
        "is_view_enabled": True,
        "is_page_enabled": True,
        "is_intake_enabled": True,
        "is_issue_estimate_enabled": True,
    }


async def resolve_membership(slug: str, request: Request) -> Tuple[Optional[int], Optional[int], Optional[Dict[str, Any]]]:
    status, body, _ = await ce_get(f"/api/workspaces/{slug}/workspace-members/me/", request)
    if status == 401:
        return 401, None, body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."}
    if status == 403:
        return 403, None, body if isinstance(body, dict) else {"error": "Not authorized"}
    if status == 404:
        return 404, None, body if isinstance(body, dict) else {"error": "Workspace not found"}
    if status >= 400:
        status2, body2, _ = await ce_get("/api/users/me/workspaces/", request)
        if status2 == 401:
            return 401, None, body2 if isinstance(body2, dict) else {"detail": "Authentication credentials were not provided."}
        if status2 >= 400:
            return status, None, body if isinstance(body, dict) else {"error": "Failed to resolve membership"}
        if not isinstance(body2, list):
            return 404, None, {"error": "Workspace not found"}
        match = next((w for w in body2 if isinstance(w, dict) and w.get("slug") == slug), None)
        if not match:
            return 404, None, {"error": "Workspace not found"}
        try:
            return None, int(match.get("role")), None
        except Exception:
            return None, 20, None

    if not isinstance(body, dict):
        return 404, None, {"error": "Workspace not found"}
    if body.get("id") is None and body.get("role") is None and body.get("member") is None:
        return 404, None, {"error": "Workspace not found"}
    role = body.get("role")
    try:
        role_i = int(role)
    except Exception:
        role_i = 15
    return None, role_i, None


async def fetch_ce_projects(slug: str, request: Request) -> Tuple[Optional[int], List[Dict[str, Any]], Any]:
    status, body, _ = await ce_get(f"/api/workspaces/{slug}/projects/", request)
    if status != 200:
        return status, [], body
    if not isinstance(body, list):
        return 500, [], {"error": "unexpected projects payload"}
    return None, [p for p in body if isinstance(p, dict)], None


def register_commercial_compat(app: FastAPI) -> None:
    @app.get("/api/workspaces/{slug}/permissions/")
    async def workspace_permissions(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return permissions_payload(relation_for_ce_role(role))

    @app.get("/api/payments/workspaces/{slug}/current-plan/")
    async def workspace_current_plan(slug: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        return dict(SELFHOST_PLAN)

    @app.get("/api/payments/workspaces/{slug}/flags/")
    async def workspace_flags(slug: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        values = dict((BUSINESS_FLAGS or {}).get("values") or BUSINESS_FLAGS or {})
        for k in list(values.keys()):
            values[k] = True
        values.update({"APP_RAIL": True, "AI_CHAT": True, "AI_CONVERSE": True})
        return {"values": values}

    @app.get("/api/workspaces/{slug}/features/")
    async def workspace_features_get(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get("/api/users/me/workspaces/", request)
        workspace_id = None
        if status == 200 and isinstance(body, list):
            match = next((w for w in body if isinstance(w, dict) and w.get("slug") == slug), None)
            if match:
                workspace_id = match.get("id")
        return features_payload(workspace_id)

    @app.patch("/api/workspaces/{slug}/features/")
    async def workspace_features_patch(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        try:
            patch = await request.json()
        except Exception:
            patch = {}
        base = features_payload()
        if isinstance(patch, dict):
            for k, v in patch.items():
                if k.startswith("is_") or k in base:
                    base[k] = v
        return base

    @app.get("/api/workspaces/{slug}/roles/")
    async def workspace_roles(slug: str, request: Request, namespace: Optional[str] = None):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        roles = list(WORKSPACE_ROLES or [])
        if namespace:
            roles = [r for r in roles if r.get("namespace") == namespace]
        return roles

    @app.get("/api/workspaces/{slug}/permission-schemes/")
    async def permission_schemes(slug: str, request: Request, namespace: Optional[str] = None):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    # ---- CRITICAL: projects list for commercial SPA ----
    @app.get("/api/workspaces/{slug}/projects-lite/")
    async def projects_lite(slug: str, request: Request, ids: Optional[str] = None):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, projects, body = await fetch_ce_projects(slug, request)
        if status is not None:
            return JSONResponse(body if isinstance(body, dict) else {"error": "Failed to load projects"}, status_code=status)
        lite = [to_project_lite(p) for p in projects]
        if ids:
            wanted = {x.strip() for x in ids.split(",") if x.strip()}
            lite = [p for p in lite if str(p.get("id")) in wanted]
        return lite

    @app.get("/api/workspaces/{slug}/workspace-project-features/")
    async def workspace_project_features(slug: str, request: Request):
        """Must return a LIST — SPA does `for (let e of t)`."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, projects, body = await fetch_ce_projects(slug, request)
        if status is not None:
            return JSONResponse(body if isinstance(body, dict) else {"error": "Failed to load projects"}, status_code=status)
        return [project_features_row(str(p["id"])) for p in projects if p.get("id")]

    @app.get("/api/workspaces/{slug}/projects/{project_id}/features/")
    async def project_features_get(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return project_features_row(project_id)

    @app.patch("/api/workspaces/{slug}/projects/{project_id}/features/")
    async def project_features_patch(slug: str, project_id: str, request: Request):
        base = project_features_row(project_id)
        try:
            patch = await request.json()
        except Exception:
            patch = {}
        if isinstance(patch, dict):
            base.update(patch)
        return base

    # modules (+ lite) → CE modules, wrapped for commercial paginated loader
    @app.get("/api/workspaces/{slug}/projects/{project_id}/modules/")
    async def modules_list(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # forward query string (cursor/filters) if present
        q = str(request.url.query or "")
        path = f"/api/workspaces/{slug}/projects/{project_id}/modules/"
        if q:
            path = f"{path}?{q}"
        status, body, _ = await ce_get(path, request)
        if status != 200:
            return JSONResponse(body if isinstance(body, (dict, list)) else {"error": str(body)}, status_code=status)
        return as_page(body)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/modules-lite/")
    async def modules_lite(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/projects/{project_id}/modules/", request)
        if status != 200:
            return JSONResponse(body if isinstance(body, (dict, list)) else {"error": str(body)}, status_code=status)
        return as_page(body)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/cycles-lite/")
    async def cycles_lite_project(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/projects/{project_id}/cycles/", request)
        if status != 200:
            # empty page if CE endpoint missing/fails
            return as_page([])
        return as_page(body)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues/total-count/")
    async def issues_total_count(slug: str, project_id: str, request: Request):
        """Commercial kanban calls this; synthesize from CE issues total_count."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # try CE issues list with same query params minus layout-only fields
        q = dict(request.query_params)
        # fetch a grouped issues page to get totals when possible
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params=q or None,
        )
        if status == 200 and isinstance(body, dict):
            # group counts if results are dict of buckets
            results = body.get("results")
            if isinstance(results, dict):
                counts = {}
                for gid, bucket in results.items():
                    if isinstance(bucket, dict):
                        counts[gid] = bucket.get("total_results") or len(bucket.get("results") or [])
                    elif isinstance(bucket, list):
                        counts[gid] = len(bucket)
                return {
                    "total_count": body.get("total_count") or body.get("total_results") or sum(counts.values()),
                    "grouped_count": counts,
                    "counts": counts,
                }
            return {
                "total_count": body.get("total_count") or body.get("total_results") or 0,
                "grouped_count": {},
                "counts": {},
            }
        return {"total_count": 0, "grouped_count": {}, "counts": {}}

    def _module_rows_from_body(body: Any) -> List[Dict[str, Any]]:
        if isinstance(body, list):
            return [x for x in body if isinstance(x, dict)]
        if isinstance(body, dict):
            maybe = body.get("results") or body.get("data") or []
            if isinstance(maybe, list):
                return [x for x in maybe if isinstance(x, dict)]
        return []

    async def _collect_workspace_modules(slug: str, request: Request) -> List[Dict[str, Any]]:
        """Aggregate modules so board can resolve module_ids → names."""
        rows: List[Dict[str, Any]] = []
        seen: set = set()

        status, body, _ = await ce_get(f"/api/workspaces/{slug}/modules/", request)
        if status == 200:
            for r in _module_rows_from_body(body):
                rid = str(r.get("id") or "")
                if rid and rid not in seen:
                    seen.add(rid)
                    rows.append(r)

        # Always also pull per-project modules (CE workspace /modules/ can be sparse)
        _, projects, _ = await fetch_ce_projects(slug, request)
        for p in projects[:40]:
            pid = p.get("id")
            if not pid:
                continue
            st, body2, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{pid}/modules/", request
            )
            if st != 200:
                continue
            for r in _module_rows_from_body(body2):
                rid = str(r.get("id") or "")
                if rid and rid not in seen:
                    seen.add(rid)
                    rows.append(r)
        return rows

    @app.get("/api/workspaces/{slug}/modules-lite/")
    async def workspace_modules_lite(slug: str, request: Request):
        """Commercial SPA:
        - getModulesByIds → bare array filtered by ?ids=
        - listWorkspaceLite → paginated {results:...}
        """
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)

        raw_ids = request.query_params.get("ids") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        raw_pids = request.query_params.get("project_ids") or ""
        wanted_projects = {x.strip() for x in raw_pids.split(",") if x.strip()}

        rows = await _collect_workspace_modules(slug, request)
        if wanted_projects:
            rows = [
                r
                for r in rows
                if str(r.get("project_id") or r.get("project") or "") in wanted_projects
            ]
        if wanted:
            rows = [r for r in rows if str(r.get("id")) in wanted]
            # batch-id loader expects a bare list
            return rows

        # list loader expects paginated commercial shape
        return as_page(rows)

    def _member_lite_from_user(
        user: Dict[str, Any],
        *,
        workspace_id: Any = None,
        role: Any = None,
        membership_id: Any = None,
        is_active: Any = True,
    ) -> Dict[str, Any]:
        uid = user.get("id")
        display = (
            user.get("display_name")
            or " ".join(
                x
                for x in [user.get("first_name") or "", user.get("last_name") or ""]
                if x
            ).strip()
            or user.get("email")
            or str(uid or "")
        )
        return {
            "id": uid,
            "display_name": display,
            "first_name": user.get("first_name") or "",
            "last_name": user.get("last_name") or "",
            "avatar": user.get("avatar") or "",
            "avatar_url": user.get("avatar_url"),
            "is_bot": bool(user.get("is_bot")),
            "email": user.get("email") or "",
            "last_login_medium": user.get("last_login_medium") or "email",
            "workspace_id": workspace_id,
            "role": role,
            "role_slug": "admin" if (isinstance(role, int) and role >= 20) else "member",
            "is_active": True if is_active is None else bool(is_active),
            "membership_id": membership_id,
        }

    async def _workspace_user_map(slug: str, request: Request) -> Dict[str, Dict[str, Any]]:
        """Map user_id → CE user profile from workspace members."""
        out: Dict[str, Dict[str, Any]] = {}
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/members/", request)
        if status != 200:
            return out
        rows = body if isinstance(body, list) else (body.get("results") if isinstance(body, dict) else [])
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            member = row.get("member")
            if isinstance(member, dict) and member.get("id"):
                out[str(member["id"])] = member
            elif isinstance(member, str):
                out.setdefault(member, {"id": member})
        # ensure current user is present (fresh first/last name)
        st, me, _ = await ce_get("/api/users/me/", request)
        if st == 200 and isinstance(me, dict) and me.get("id"):
            out[str(me["id"])] = {**out.get(str(me["id"]), {}), **me}
        return out

    @app.get("/api/workspaces/{slug}/projects/{project_id}/members-lite/")
    async def project_members_lite(slug: str, project_id: str, request: Request):
        """SPA assignee avatars/names load via members-lite (CE only has /members/)."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)

        users = await _workspace_user_map(slug, request)
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/members/", request
        )
        rows_in: List[Dict[str, Any]] = []
        if status == 200:
            if isinstance(body, list):
                rows_in = [x for x in body if isinstance(x, dict)]
            elif isinstance(body, dict):
                maybe = body.get("results") or []
                if isinstance(maybe, list):
                    rows_in = [x for x in maybe if isinstance(x, dict)]

        # workspace id for lite shape
        ws_id = None
        st_ws, ws_body, _ = await ce_get(f"/api/workspaces/{slug}/", request)
        if st_ws == 200 and isinstance(ws_body, dict):
            ws_id = ws_body.get("id")

        lite: List[Dict[str, Any]] = []
        for row in rows_in:
            mid = row.get("member")
            user_id = None
            user_obj: Dict[str, Any] = {}
            if isinstance(mid, dict):
                user_id = str(mid.get("id") or "")
                user_obj = mid
            elif mid is not None:
                user_id = str(mid)
            if not user_id:
                continue
            profile = {**users.get(user_id, {}), **user_obj, "id": user_id}
            lite.append(
                _member_lite_from_user(
                    profile,
                    workspace_id=ws_id,
                    role=row.get("role"),
                    membership_id=row.get("id"),
                    is_active=row.get("is_active", True),
                )
            )

        # search filter (optional)
        search = (request.query_params.get("search") or "").strip().lower()
        if search:
            lite = [
                m
                for m in lite
                if search in (m.get("display_name") or "").lower()
                or search in (m.get("email") or "").lower()
            ]
        return as_page(lite)

    @app.get("/api/workspaces/{slug}/members-lite/")
    async def workspace_members_lite(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/members/", request)
        if status != 200:
            return as_page([])
        rows = body if isinstance(body, list) else (body.get("results") if isinstance(body, dict) else [])
        if not isinstance(rows, list):
            rows = []
        ws_id = None
        st_ws, ws_body, _ = await ce_get(f"/api/workspaces/{slug}/", request)
        if st_ws == 200 and isinstance(ws_body, dict):
            ws_id = ws_body.get("id")
        lite: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            member = row.get("member")
            if not isinstance(member, dict):
                continue
            lite.append(
                _member_lite_from_user(
                    member,
                    workspace_id=ws_id,
                    role=row.get("role"),
                    membership_id=row.get("id"),
                    is_active=row.get("is_active", True),
                )
            )
        raw_ids = request.query_params.get("ids") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        if wanted:
            return [m for m in lite if str(m.get("id")) in wanted]
        return as_page(lite)

    @app.post("/auth/mobile/email-check/")
    @app.post("/auth/mobile/email-check")
    async def mobile_email_check(request: Request):
        """Official mobile WebView (/m/auth) posts here; CE only has /auth/email-check/.

        Without this shim, Continue after email does nothing (404 swallowed by SPA).
        """
        try:
            payload = await request.json()
        except Exception:
            # form fallback
            form = await request.form()
            payload = {k: form.get(k) for k in form.keys()}
        if not isinstance(payload, dict):
            payload = {}
        # normalize email key
        email = payload.get("email") or payload.get("Email") or ""
        status, body, _ = await ce_post(
            "/auth/email-check/",
            request,
            json_body={"email": str(email).strip().lower()},
        )
        if status == 200 and isinstance(body, dict):
            # Always force CREDENTIAL when magic/SMTP isn't usable so password UI shows
            if body.get("status") == "MAGIC_CODE":
                # if instances say magic disabled, still return CREDENTIAL
                body = {**body, "status": "CREDENTIAL"}
            return JSONResponse(body, status_code=200)
        if isinstance(body, dict):
            return JSONResponse(body, status_code=status if status >= 400 else 400)
        return JSONResponse(
            {"error": "email-check failed", "detail": str(body)[:300]},
            status_code=status if status >= 400 else 502,
        )

    @app.post("/auth/mobile/magic-generate/")
    @app.post("/auth/mobile/magic-generate")
    async def mobile_magic_generate(request: Request):
        """Proxy magic generate if CE has it; otherwise clear error for mobile SPA."""
        try:
            payload = await request.json()
        except Exception:
            form = await request.form()
            payload = {k: form.get(k) for k in form.keys()}
        if not isinstance(payload, dict):
            payload = {}
        # CE web path
        status, body, _ = await ce_post("/auth/magic-generate/", request, json_body=payload)
        if status < 400:
            return JSONResponse(body if isinstance(body, dict) else {"ok": True}, status_code=status)
        # Magic often disabled without SMTP — tell client clearly
        return JSONResponse(
            {
                "error_code": "MAGIC_LINK_LOGIN_DISABLED",
                "error_message": "MAGIC_LINK_LOGIN_DISABLED",
                "error": "Magic login is not configured. Use email + password.",
            },
            status_code=400,
        )

    @app.get("/api/instances/")
    async def instances_version_spoof(request: Request):
        """Advertise Plane 3.0 / Business so mobile + commercial SPA unlock AI features."""
        status, body, _ = await ce_get("/api/instances/", request)
        if status != 200 or not isinstance(body, dict):
            return JSONResponse(
                body if isinstance(body, dict) else {"error": "instances unavailable"},
                status_code=status if status else 502,
            )
        out = dict(body)
        inst = dict(out.get("instance") or {})
        # Mobile / cloud apps gate on current_version (target: 3.0.0 family)
        spoof = os.environ.get("PLANE_SPOOF_VERSION") or "3.0.0"
        inst["current_version"] = spoof
        inst["latest_version"] = spoof
        inst["edition"] = inst.get("edition") or "PLANE_BUSINESS"
        inst["is_current_version_deprecated"] = False
        out["instance"] = inst
        cfg = dict(out.get("config") or {})
        cfg.setdefault("has_llm_configured", True)
        cfg.setdefault("is_email_password_enabled", True)
        # Keep magic off unless SMTP works — avoid empty "continue" into magic code
        cfg.setdefault("is_magic_login_enabled", False)
        cfg.setdefault("enable_turnstile", False)
        out["config"] = cfg
        return out

    @app.get("/api/workspaces/{slug}/cycles-lite/")
    async def cycles_lite(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    @app.get("/api/workspaces/{slug}/preferences/")
    async def workspace_preferences_get(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return PREF_STORE.get(slug, {})

    @app.api_route("/api/workspaces/{slug}/preferences/", methods=["PATCH", "PUT", "POST"])
    async def workspace_preferences_write(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        try:
            patch = await request.json()
        except Exception:
            patch = {}
        cur = dict(PREF_STORE.get(slug, {}))
        if isinstance(patch, dict):
            cur.update(patch)
        PREF_STORE[slug] = cur
        return cur

    @app.get("/api/workspaces/{slug}/workflows/")
    async def workflows(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # commercial store does t.results.forEach(...)
        return {"results": [], "count": 0, "total_count": 0, "next_cursor": None, "next_page_results": False}

    @app.get("/api/workspaces/{slug}/work-item-types/")
    async def work_item_types(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    @app.get("/api/workspaces/{slug}/workitems/templates/")
    async def workitem_templates(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    @app.get("/api/workspaces/{slug}/work-item-relation-definitions/")
    async def relation_defs(slug: str, request: Request, is_default: Optional[bool] = None):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    @app.get("/api/apps/{workspace_id}/enabled-integrations/")
    async def enabled_integrations(workspace_id: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        return []

    @app.get("/api/connections/{workspace_id}/user/{user_id}")
    @app.get("/api/connections/{workspace_id}/user/{user_id}/")
    async def user_connections(workspace_id: str, user_id: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        return []

    @app.get("/api/silo/workspaces/{slug}/mcp-applications/")
    async def mcp_apps(slug: str, request: Request, featured: Optional[bool] = None):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    @app.get("/api/users/me/workspaces/")
    async def users_me_workspaces(request: Request):
        status, body, headers = await ce_get("/api/users/me/workspaces/", request)
        if status != 200:
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
        if isinstance(body, list):
            body = [enrich_workspace(w) if isinstance(w, dict) else w for w in body]
        return body

    @app.get("/api/workspaces/{slug}/teamspaces/")
    @app.get("/api/workspaces/{slug}/customers/")
    @app.get("/api/workspaces/{slug}/releases/")
    @app.get("/api/workspaces/{slug}/releases-lite/")
    @app.get("/api/workspaces/{slug}/initiatives/")
    async def empty_commercial_lists(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []


    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues/meta/")
    async def issues_meta(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # Prefer real counts from CE issues list so commercial board isn't empty
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params={"per_page": "1"},
        )
        total = 0
        if status == 200 and isinstance(body, dict):
            total = int(body.get("total_count") or body.get("total_results") or body.get("count") or 0)
        return {"count": total, "total_count": total, "results": []}

    def _normalize_state_lite(r: Dict[str, Any], project_id: Any = None) -> Dict[str, Any]:
        is_default = bool(r.get("default") if r.get("default") is not None else r.get("is_default"))
        return {
            "id": r.get("id"),
            "name": r.get("name"),
            "color": r.get("color") or "#60646C",
            "group": r.get("group") or r.get("group_key") or "backlog",
            "sequence": r.get("sequence"),
            "order": r.get("order") if r.get("order") is not None else r.get("sequence"),
            "project_id": r.get("project_id") or r.get("project") or project_id,
            "workspace_id": r.get("workspace_id") or r.get("workspace"),
            # CE uses "default"; commercial SPA reads is_default in several places
            "default": is_default,
            "is_default": is_default,
            "allow_issue_creation": bool(
                r.get("allow_issue_creation") if r.get("allow_issue_creation") is not None else True
            ),
            "description": r.get("description") or "",
        }

    def _paginate_results(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commercial SPA: getStatesLite uses data.results; listStatesLite uses W(data)."""
        n = len(rows)
        return {
            "grouped_by": None,
            "sub_grouped_by": None,
            "total_count": n,
            "count": n,
            "total_results": n,
            "total_pages": 1,
            "next_cursor": "1000:1:0",
            "prev_cursor": "1000:-1:1",
            "next_page_results": False,
            "prev_page_results": False,
            "results": rows,
            "extra_stats": None,
        }

    @app.get("/api/workspaces/{slug}/states-lite/")
    async def states_lite(slug: str, request: Request):
        """Commercial SPA loads state labels/colors via states-lite?ids=...

        getStatesByIds / getWorkspaceStatesLite expect a bare array body.
        """
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        raw_ids = request.query_params.get("ids") or request.query_params.get("id") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        raw_pids = request.query_params.get("project_ids") or ""
        wanted_projects = {x.strip() for x in raw_pids.split(",") if x.strip()}

        # CE: workspace-level states list (all projects)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/states/", request)
        rows: List[Dict[str, Any]] = []
        if status == 200:
            if isinstance(body, list):
                rows = [x for x in body if isinstance(x, dict)]
            elif isinstance(body, dict):
                maybe = body.get("results") or body.get("data") or []
                if isinstance(maybe, list):
                    rows = [x for x in maybe if isinstance(x, dict)]

        # Fallback: aggregate per-project states if workspace endpoint is sparse
        if not rows:
            st, projects, _ = await ce_get(f"/api/workspaces/{slug}/projects/", request)
            proj_list: List[Dict[str, Any]] = []
            if st == 200:
                if isinstance(projects, list):
                    proj_list = [p for p in projects if isinstance(p, dict)]
                elif isinstance(projects, dict):
                    pr = projects.get("results") or []
                    if isinstance(pr, list):
                        proj_list = [p for p in pr if isinstance(p, dict)]
            for p in proj_list[:30]:
                pid = p.get("id")
                if not pid:
                    continue
                if wanted_projects and str(pid) not in wanted_projects:
                    continue
                st2, body2, _ = await ce_get(
                    f"/api/workspaces/{slug}/projects/{pid}/states/", request
                )
                if st2 == 200 and isinstance(body2, list):
                    rows.extend([x for x in body2 if isinstance(x, dict)])

        if wanted_projects and rows:
            rows = [
                r
                for r in rows
                if str(r.get("project_id") or r.get("project") or "") in wanted_projects
            ]
        if wanted:
            rows = [r for r in rows if str(r.get("id")) in wanted]

        return [_normalize_state_lite(r) for r in rows]

    @app.get("/api/workspaces/{slug}/projects/{project_id}/states-lite/")
    async def project_states_lite(slug: str, project_id: str, request: Request):
        """SPA getStatesLite expects data.results; listStatesLite expects paginated body."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        raw_ids = request.query_params.get("ids") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/states/", request
        )
        rows: List[Dict[str, Any]] = []
        if status == 200 and isinstance(body, list):
            rows = [x for x in body if isinstance(x, dict)]
        if wanted:
            rows = [r for r in rows if str(r.get("id")) in wanted]
        out = [_normalize_state_lite(r, project_id) for r in rows]
        return _paginate_results(out)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/")
    async def work_items_alias(slug: str, project_id: str, request: Request):
        """Alias commercial work-items list to CE issues, preserving query string."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        q = str(request.url.query or "")
        path = f"/api/workspaces/{slug}/projects/{project_id}/issues/"
        if q:
            path = f"{path}?{q}"
        status, body, _ = await ce_get(path, request)
        if status != 200:
            return JSONResponse(body if isinstance(body, (dict, list)) else {"error": str(body)}, status_code=status)
        return body

    @app.api_route("/api/payments/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    async def payments_fallback(path: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        if path.endswith("current-plan/") or path.endswith("current-plan"):
            return dict(SELFHOST_PLAN)
        if path.endswith("flags/") or path.endswith("flags"):
            values = dict((BUSINESS_FLAGS or {}).get("values") or {})
            for k in list(values.keys()):
                values[k] = True
            return {"values": values}
        if request.method == "GET":
            return {}
        return {"ok": True, "status": "selfhost_stub"}
