"""
Commercial app.plane.so SPA ↔ Plane CE API compatibility.

The mirrored Business web UI calls cloud-only endpoints (permissions, plan,
feature flags, roles). CE does not implement those. Without them the SPA
renders "Workspace not found" for every workspace URL.

This module synthesizes those responses from CE membership/role data and
static Business plan/flag payloads. It never mutates the Plane database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

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

# CE role integers (EUserWorkspaceRoles)
ROLE_MAP = {
    20: "owner",  # CE admin / owner-equivalent
    15: "member",
    5: "guest",
}

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
    # CSRF often expects header when cookie present
    csrf = request.cookies.get("csrftoken")
    if csrf and "x-csrftoken" not in {k.lower() for k in headers}:
        headers["X-CSRFToken"] = csrf
    return headers


async def ce_get(path: str, request: Request) -> Tuple[int, Any, Dict[str, str]]:
    url = f"{PLANE_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        r = await client.get(url, headers=_forward_headers(request))
    body: Any
    try:
        body = r.json()
    except Exception:
        body = r.text
    # pass through set-cookie rarely needed for GET
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
    # fallback: full owner grants for admin-like, minimal otherwise
    if relation in ("owner", "admin"):
        return {
            "relation": relation,
            "permission_grants": list(OWNER_PERMISSIONS.get("permission_grants") or []),
        }
    return {"relation": relation, "permission_grants": list(OWNER_PERMISSIONS.get("permission_grants") or [])}


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


def enrich_workspace(ws: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ws)
    role = out.get("role")
    try:
        role_i = int(role) if role is not None else None
    except Exception:
        role_i = None
    relation = relation_for_ce_role(role_i)
    # commercial store expects role_slug + plan chrome
    out.setdefault("role_slug", relation if relation != "owner" else "owner")
    if role_i is not None and role_i >= 20:
        out["role_slug"] = "owner"
    out.setdefault("current_plan", "BUSINESS")
    out.setdefault("is_on_trial", False)
    return out


async def resolve_membership(slug: str, request: Request) -> Tuple[Optional[int], Optional[int], Optional[Dict[str, Any]]]:
    """
    Returns (http_status_or_none_on_success_path, ce_role, error_body).
    Success: (None, role, None)
    Auth failure: (401/403, None, body)
    Not a member / missing: (404, None, body)
    """
    # Prefer CE workspace-members/me (returns membership incl. role)
    status, body, _ = await ce_get(f"/api/workspaces/{slug}/workspace-members/me/", request)
    if status == 401:
        return 401, None, body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."}
    if status == 403:
        return 403, None, body if isinstance(body, dict) else {"error": "Not authorized"}
    if status == 404:
        return 404, None, body if isinstance(body, dict) else {"error": "Workspace not found"}
    if status >= 400:
        # Fall back to workspace list
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
    # empty / null membership
    if body.get("id") is None and body.get("role") is None and body.get("member") is None:
        # Serializer of None may return empty-ish
        return 404, None, {"error": "Workspace not found"}
    role = body.get("role")
    try:
        role_i = int(role)
    except Exception:
        # If membership object exists without role, treat as member
        role_i = 15
    return None, role_i, None


def register_commercial_compat(app: FastAPI) -> None:
    """Attach commercial SPA compatibility routes to the PI FastAPI app."""

    @app.get("/api/workspaces/{slug}/permissions/")
    async def workspace_permissions(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            # SPA: 403 → Not Authorized, other errors → Workspace not found
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        relation = relation_for_ce_role(role)
        return permissions_payload(relation)

    @app.get("/api/payments/workspaces/{slug}/current-plan/")
    async def workspace_current_plan(slug: str, request: Request):
        # Auth-gated so random scanners don't get plan JSON; membership optional
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        plan = dict(SELFHOST_PLAN)
        # try to fill occupied seats from membership count if available
        err_status, role, _ = await resolve_membership(slug, request)
        if err_status == 404:
            # still return plan so billing banners don't brick non-members oddly
            pass
        return plan

    @app.get("/api/payments/workspaces/{slug}/flags/")
    async def workspace_flags(slug: str, request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        values = dict((BUSINESS_FLAGS or {}).get("values") or BUSINESS_FLAGS or {})
        # Force core chrome on for self-host commercial mirror
        values.update(
            {
                "APP_RAIL": True,
                "AI_CHAT": True,
                "AI_CONVERSE": True,
                "AI_PAGES_EDIT": True,
                "AI_PAGES_SUMMARY": True,
                "AI_PAGES_BLOCKS": True,
                "WIKI": True if "WIKI" in values else values.get("WIKI", True),
            }
        )
        # Ensure all known flags true for max UI surface on self-host
        for k in list(values.keys()):
            values[k] = True
        return {"values": values}

    @app.get("/api/workspaces/{slug}/features/")
    async def workspace_features_get(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # Try to attach real workspace id from CE list
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

    @app.get("/api/workspaces/{slug}/workspace-project-features/")
    async def workspace_project_features(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return {}

    @app.get("/api/workspaces/{slug}/projects/{project_id}/features/")
    async def project_features_get(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return {
            "id": project_id,
            "project_id": project_id,
            "is_project_updates_enabled": False,
            "is_cycle_enabled": True,
            "is_module_enabled": True,
            "is_view_enabled": True,
            "is_page_enabled": True,
            "is_intake_enabled": True,
            "is_issue_type_enabled": False,
            "is_time_tracking_enabled": True,
            "is_issue_estimate_enabled": True,
        }

    @app.patch("/api/workspaces/{slug}/projects/{project_id}/features/")
    async def project_features_patch(slug: str, project_id: str, request: Request):
        base = await project_features_get(slug, project_id, request)
        if isinstance(base, JSONResponse):
            return base
        try:
            patch = await request.json()
        except Exception:
            patch = {}
        if isinstance(patch, dict) and isinstance(base, dict):
            base.update(patch)
        return base

    @app.get("/api/users/me/workspaces/")
    async def users_me_workspaces(request: Request):
        """Proxy CE list and add commercial fields (current_plan, role_slug)."""
        status, body, headers = await ce_get("/api/users/me/workspaces/", request)
        if status != 200:
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
        if isinstance(body, list):
            body = [enrich_workspace(w) if isinstance(w, dict) else w for w in body]
        return body

    # Soft-empty commercial-only collections so UI doesn't hard-crash
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

    @app.api_route("/api/payments/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    async def payments_fallback(path: str, request: Request):
        """Any other payments/* call: safe stub (never hits CE 404)."""
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
