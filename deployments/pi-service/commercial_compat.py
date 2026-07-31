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

PREF_STORE: Dict[str, Dict[str, Any]] = {}
# work-item votes: key = f"{project_id}:{issue_id}" -> list of vote dicts
VOTE_STORE: Dict[str, List[Dict[str, Any]]] = {}
# work-item updates (status posts): key same
UPDATE_STORE: Dict[str, List[Dict[str, Any]]] = {}

# Prefer cloud-shaped plan so commercial mobile treats the workspace as SaaS AI surface.
# (is_self_managed=true hides Pilot on official clients even when feature flags are on.)
SELFHOST_PLAN = _load(
    "current_plan_cloud.json",
    {
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
        "is_self_managed": False,
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
    },
)
# Always force cloud AI surface flags regardless of on-disk plan snapshot.
# Kill trial banner ("Business trial ends in N days") and payment nags.
SELFHOST_PLAN = dict(SELFHOST_PLAN)
SELFHOST_PLAN["is_self_managed"] = False
SELFHOST_PLAN["product"] = SELFHOST_PLAN.get("product") or "BUSINESS"
SELFHOST_PLAN["show_payment_button"] = False
SELFHOST_PLAN["show_trial_banner"] = False
SELFHOST_PLAN["is_on_trial"] = False
SELFHOST_PLAN["is_trial_allowed"] = False
SELFHOST_PLAN["is_trial_ended"] = False
SELFHOST_PLAN["remaining_trial_days"] = 0
SELFHOST_PLAN["trial_end_date"] = None
SELFHOST_PLAN["has_activated_free_trial"] = False
SELFHOST_PLAN["has_upgraded"] = True
SELFHOST_PLAN["has_added_payment_method"] = True
SELFHOST_PLAN["is_free_member_count_exceeded"] = False
SELFHOST_PLAN["purchased_seats"] = max(int(SELFHOST_PLAN.get("purchased_seats") or 0), 9999)
SELFHOST_PLAN["free_seats"] = max(int(SELFHOST_PLAN.get("free_seats") or 0), 9999)
SELFHOST_PLAN["show_seats_banner"] = False
SELFHOST_PLAN["show_verification_failed_banner"] = False


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




async def ce_patch(path: str, request: Request, json_body: Any = None) -> Tuple[int, Any, Dict[str, str]]:
    url = f"{PLANE_API_BASE}{path}"
    headers = _forward_headers(request)
    headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.patch(url, headers=headers, json=json_body if json_body is not None else {})
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body, dict(r.headers)


async def ce_delete(path: str, request: Request) -> Tuple[int, Any, Dict[str, str]]:
    url = f"{PLANE_API_BASE}{path}"
    headers = _forward_headers(request)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.delete(url, headers=headers)
    try:
        body = r.json() if r.content else {}
    except Exception:
        body = r.text
    return r.status_code, body, dict(r.headers)


async def ce_request(method: str, path: str, request: Request, json_body: Any = None) -> Tuple[int, Any, Dict[str, str]]:
    m = (method or "GET").upper()
    if m == "GET":
        return await ce_get(path, request)
    if m == "POST":
        return await ce_post(path, request, json_body=json_body)
    if m == "PATCH":
        return await ce_patch(path, request, json_body=json_body)
    if m == "PUT":
        url = f"{PLANE_API_BASE}{path}"
        headers = _forward_headers(request)
        headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.put(url, headers=headers, json=json_body if json_body is not None else {})
        try:
            body = r.json()
        except Exception:
            body = r.text
        return r.status_code, body, dict(r.headers)
    if m == "DELETE":
        return await ce_delete(path, request)
    return 405, {"error": "method not allowed"}, {}

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


# Commercial SPA display group_by keys → CE ISSUE_GROUP_BY_ALLOWLIST field names.
# (EIssueGroupByToServerOptions in @plane/constants)
#
# type / parent_type are commercial-only. CE has no type_id grouping and
# parent_type columns are hard-coded void 0 in the cloud SPA bundle — both
# blank the board (getGroupByColumns → undefined → if (!groups) return null)
# while total-count still shows e.g. "Work items 21". Map them to state_id.
GROUP_BY_CLIENT_TO_CE: Dict[str, str] = {
    "state": "state_id",
    "priority": "priority",
    "labels": "labels__id",
    "state_detail.group": "state__group",
    "assignees": "assignees__id",
    "cycle": "cycle_id",
    "module": "issue_module__module_id",
    "target_date": "target_date",
    "project": "project_id",
    "team_project": "project_id",
    "created_by": "created_by",
    # commercial-only → safe CE default (state columns always load)
    "type": "state_id",
    "type_id": "state_id",
    "parent_type": "state_id",
    "parent_id": "state_id",
    # already-server forms (pass-through)
    "state_id": "state_id",
    "labels__id": "labels__id",
    "state__group": "state__group",
    "assignees__id": "assignees__id",
    "cycle_id": "cycle_id",
    "issue_module__module_id": "issue_module__module_id",
    "project_id": "project_id",
}

# Display-filter keys the SPA must not keep for CE boards.
_UNSUPPORTED_DISPLAY_GROUP_BY = frozenset(
    {"type", "parent_type", "type_id", "parent_id"}
)


def coerce_display_filters_group_by(payload: Any) -> Any:
    """Replace commercial-only group_by values with ``state`` in place.

    Used for user-properties-style JSON (and any nested display_filters).
    Returns the same object for chaining.
    """
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            for item in payload:
                coerce_display_filters_group_by(item)
        return payload

    df = payload.get("display_filters")
    if isinstance(df, dict):
        gb = df.get("group_by")
        if gb is not None and str(gb) in _UNSUPPORTED_DISPLAY_GROUP_BY:
            df["group_by"] = "state"
        # Self-host always-regroup is single-level (modules path). Commercial
        # kanban with sub_group_by expects nested buckets; that blanks /issues/
        # while module boards (no sub_group) still paint. Drop sub-groups.
        if df.get("sub_group_by") is not None:
            df["sub_group_by"] = None

    # Nested containers (filters envelope, arrays of view prefs, etc.)
    for v in payload.values():
        if isinstance(v, (dict, list)):
            coerce_display_filters_group_by(v)
    return payload
# Params commercial SPA always attaches that CE either ignores or mishandles.
_COMMERCIAL_ONLY_ISSUE_PARAMS = frozenset(
    {
        "layout",
        "sidecar",
        "skip_total_count",
        "group_offset",
        "group_per_page",
        "sub_group_offset",
        "sub_group_per_page",
    }
)


# Commercial SPA filter field names → CE ComplexFilterBackend / IssueFilterSet.
# SPA chips use plural relation names; CE only allows assignee_id / label_id / etc.
# Sending ``{"assignees":[...]}`` yields 400 ``Filtering on field 'assignees' is
# not allowed`` and the board paints headers with zero cards.
_FILTER_FIELD_TO_CE: Dict[str, str] = {
    "assignees": "assignee_id",
    "assignee": "assignee_id",
    "assignee_ids": "assignee_id",
    "assignees__id": "assignee_id",
    "labels": "label_id",
    "label": "label_id",
    "label_ids": "label_id",
    "labels__id": "label_id",
    "state": "state_id",
    "states": "state_id",
    "state_ids": "state_id",
    "cycle": "cycle_id",
    "cycles": "cycle_id",
    "module": "module_id",
    "modules": "module_id",
    "module_ids": "module_id",
    "created_by": "created_by_id",
    "subscribers": "subscriber_id",
    "subscriber": "subscriber_id",
    "mentions": "mention_id",
    "mention": "mention_id",
    "project": "project_id",
    "projects": "project_id",
    "state_group": "state_group",
    "priority": "priority",
    "is_archived": "is_archived",
    "is_draft": "is_draft",
    # already-CE forms
    "assignee_id": "assignee_id",
    "label_id": "label_id",
    "state_id": "state_id",
    "cycle_id": "cycle_id",
    "module_id": "module_id",
    "created_by_id": "created_by_id",
    "subscriber_id": "subscriber_id",
    "mention_id": "mention_id",
    "project_id": "project_id",
    "start_date": "start_date",
    "target_date": "target_date",
    "created_at": "created_at",
    "updated_at": "updated_at",
}

# Commercial-only filter keys CE cannot apply — drop rather than 400 the board.
_FILTER_FIELDS_DROP = frozenset(
    {
        "type",
        "type_id",
        "parent_type",
        "parent_id",
        "milestone",
        "milestone_id",
        "release",
        "release_id",
        "team_project",
    }
)


def sanitize_issue_filters(raw: Any) -> Optional[str]:
    """Normalize commercial SPA `filters` for CE ComplexFilterBackend.

    - Strip empty arrays (CE 400s on empty list filters).
    - Map commercial field names (``assignees``, ``labels``, ``state``) to CE
      IssueFilterSet fields (``assignee_id``, ``label_id``, ``state_id``).
    - Drop commercial-only keys (type / parent_type / milestone / release).
    - Multi-value lists become ``field__in`` which IssueFilterSet supports.
    """
    if raw is None:
        return None
    parsed: Any = raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        s = raw.strip()
        if s in ("", "{}", "null", "None", "[]"):
            return None
        try:
            parsed = json.loads(s)
        except Exception:
            # Leave non-JSON filters alone (CE may accept legacy forms)
            return s if s else None
    if not isinstance(parsed, dict):
        return None
    cleaned: Dict[str, Any] = {}
    for fk, fv in parsed.items():
        if fv is None:
            continue
        key = str(fk)
        if key in _FILTER_FIELDS_DROP:
            continue
        # Already __in / range forms from SPA — remap base then re-suffix
        suffix = ""
        base = key
        for sfx in ("__in", "__exact", "__range", "__gte", "__lte", "__gt", "__lt"):
            if key.endswith(sfx):
                base = key[: -len(sfx)]
                suffix = sfx
                break
        if base in _FILTER_FIELDS_DROP:
            continue
        mapped = _FILTER_FIELD_TO_CE.get(base)
        if mapped is None:
            # Unknown commercial field → drop (do not 400 the board)
            continue
        out_key = mapped + suffix

        if isinstance(fv, (list, tuple, set)):
            items = [x for x in fv if x is not None and x != ""]
            if not items:
                continue
            # CE list filters use __in
            if not suffix:
                out_key = mapped + "__in"
            # Merge if both singular and plural mapped to same key
            if out_key in cleaned and isinstance(cleaned[out_key], list):
                cleaned[out_key] = list(dict.fromkeys([*cleaned[out_key], *items]))
            else:
                cleaned[out_key] = list(items)
            continue
        if isinstance(fv, str) and fv.strip() == "":
            continue
        if isinstance(fv, dict) and not fv:
            continue
        cleaned[out_key] = fv
    if not cleaned:
        return None
    return json.dumps(cleaned, separators=(",", ":"))


def clean_ce_issue_params(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip commercial-only query keys and map group_by/sub_group_by for CE.

    Unsupported commercial group keys (type/parent_type) are mapped to
    state_id so CE returns state-grouped buckets instead of dropping group_by
    and returning a flat list that the SPA cannot render under type columns.
    """
    if not raw:
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if k in _COMMERCIAL_ONLY_ISSUE_PARAMS:
            continue
        if v is None:
            continue
        # Sanitize filters — empty arrays blank the board via CE 400s
        if k == "filters":
            cleaned = sanitize_issue_filters(v)
            if cleaned is None:
                continue
            out[k] = cleaned
            continue
        out[k] = v

    _CE_GROUP_ALLOWLIST = frozenset(
        {
            "state_id",
            "state__group",
            "priority",
            "labels__id",
            "assignees__id",
            "issue_module__module_id",
            "cycle_id",
            "project_id",
            "created_by",
            "target_date",
            "start_date",
        }
    ) | frozenset(GROUP_BY_CLIENT_TO_CE.values())

    # Never forward sub_group_by: SPA + flat regroup disagree on shape and
    # blank the project Work items tray (modules omit sub_group and work).
    out.pop("sub_group_by", None)

    if "group_by" in out:
        raw_val = str(out["group_by"])
        mapped = GROUP_BY_CLIENT_TO_CE.get(raw_val, raw_val)
        if mapped in _CE_GROUP_ALLOWLIST:
            out["group_by"] = mapped
        else:
            out["group_by"] = "state_id"
    return out

def _normalize_issue_item(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure commercial board fields exist with CE-compatible aliases."""
    out = dict(issue)
    # ids always strings for SPA Map keys
    if out.get("id") is not None:
        out["id"] = str(out["id"])
    if out.get("project_id") is not None:
        out["project_id"] = str(out["project_id"])
    if out.get("state_id") is not None:
        out["state_id"] = str(out["state_id"])
    elif out.get("state") is not None and not isinstance(out.get("state"), dict):
        out["state_id"] = str(out["state"])

    # assignee_ids / label_ids arrays as string uuids
    for arr_key in ("assignee_ids", "label_ids", "module_ids"):
        arr = out.get(arr_key)
        if isinstance(arr, list):
            out[arr_key] = [str(x) for x in arr if x is not None]
        elif arr is None:
            out[arr_key] = []

    # Commercial sometimes reads assignees as id list
    if "assignees" not in out and out.get("assignee_ids"):
        out["assignees"] = list(out["assignee_ids"])
    if "labels" not in out and out.get("label_ids"):
        out["labels"] = list(out["label_ids"])

    return out


def _normalize_group_bucket(bucket: Any) -> Dict[str, Any]:
    """processIssueResponse expects {results: Issue[], total_results: number}."""
    if isinstance(bucket, list):
        items = [_normalize_issue_item(x) if isinstance(x, dict) else x for x in bucket]
        return {"results": items, "total_results": len(items)}
    if not isinstance(bucket, dict):
        return {"results": [], "total_results": 0}
    results = bucket.get("results")
    if isinstance(results, list):
        items = [_normalize_issue_item(x) if isinstance(x, dict) else x for x in results]
        total = bucket.get("total_results")
        if total is None:
            total = bucket.get("total_count")
        if total is None:
            total = len(items)
        out = dict(bucket)
        out["results"] = items
        out["total_results"] = int(total) if total is not None else len(items)
        return out
    if isinstance(results, dict):
        # sub-grouped
        out = dict(bucket)
        norm_sub: Dict[str, Any] = {}
        for sk, sv in results.items():
            norm_sub[str(sk)] = _normalize_group_bucket(sv)
        out["results"] = norm_sub
        if out.get("total_results") is None:
            out["total_results"] = sum(
                int(b.get("total_results") or 0) for b in norm_sub.values() if isinstance(b, dict)
            )
        return out
    return {"results": [], "total_results": int(bucket.get("total_results") or 0)}


def normalize_issues_list_response(
    body: Any,
    *,
    force_flat_as_all_issues: bool = False,
) -> Dict[str, Any]:
    """Shape CE issues list for commercial processIssueResponse + referenced_resources.

    When CE drops unsupported group_by it returns a flat ``results: Issue[]``.
    The commercial SPA list/kanban path still expects either a grouped dict or
    a single ``All Issues`` bucket when group_by is null. Optionally wrap flat
    lists as ``{"All Issues": ...}`` so processIssueResponse can paint rows.
    """
    if isinstance(body, list):
        items = [_normalize_issue_item(x) if isinstance(x, dict) else x for x in body]
        if force_flat_as_all_issues:
            return {
                "results": {
                    "All Issues": {
                        "results": items,
                        "total_results": len(items),
                    }
                },
                "total_count": len(items),
                "total_results": len(items),
                "count": len(items),
                "next_cursor": None,
                "prev_cursor": None,
                "next_page_results": False,
                "prev_page_results": False,
                "grouped_by": None,
                "sub_grouped_by": None,
                "extra_stats": None,
                "referenced_resources": {},
                "total_groups": 1,
                "next_group_offset": None,
            }
        return {
            "results": items,
            "total_count": len(items),
            "total_results": len(items),
            "count": len(items),
            "next_cursor": None,
            "prev_cursor": None,
            "next_page_results": False,
            "prev_page_results": False,
            "grouped_by": None,
            "sub_grouped_by": None,
            "extra_stats": None,
            "referenced_resources": {},
            "total_groups": None,
            "next_group_offset": None,
        }

    if not isinstance(body, dict):
        return {
            "results": [],
            "total_count": 0,
            "total_results": 0,
            "count": 0,
            "next_cursor": None,
            "prev_cursor": None,
            "next_page_results": False,
            "prev_page_results": False,
            "grouped_by": None,
            "sub_grouped_by": None,
            "extra_stats": None,
            "referenced_resources": {},
        }

    out = dict(body)
    results = out.get("results")

    if isinstance(results, list):
        items = [_normalize_issue_item(x) if isinstance(x, dict) else x for x in results]
        if force_flat_as_all_issues:
            out["results"] = {
                "All Issues": {
                    "results": items,
                    "total_results": len(items),
                }
            }
            if out.get("total_groups") is None:
                out["total_groups"] = 1
        else:
            out["results"] = items
    elif isinstance(results, dict):
        norm: Dict[str, Any] = {}
        for gid, bucket in results.items():
            norm[str(gid)] = _normalize_group_bucket(bucket)
        out["results"] = norm
        # Ensure every group key is a string (SPA uses string state ids)
    elif results is None:
        out["results"] = []

    # total_count required by processIssueResponse for ALL_ISSUES
    if out.get("total_count") is None:
        out["total_count"] = out.get("total_results") or out.get("count") or 0
    try:
        out["total_count"] = int(out["total_count"])
    except Exception:
        out["total_count"] = 0

    if out.get("total_results") is None:
        out["total_results"] = out["total_count"]

    # Commercial SPA optional fields — never throw on missing
    if "referenced_resources" not in out or out["referenced_resources"] is None:
        out["referenced_resources"] = {}
    if "total_groups" not in out:
        out["total_groups"] = None
    if "next_group_offset" not in out:
        out["next_group_offset"] = None
    if "sub_total_groups" not in out:
        out["sub_total_groups"] = None
    if "sub_next_group_offset" not in out:
        out["sub_next_group_offset"] = None

    return out

def total_count_from_issues_body(body: Any) -> Dict[str, Any]:
    """Build commercial getWorkItemTotalCount payload from a CE issues list body."""
    if not isinstance(body, dict):
        return {"total_count": 0, "grouped_count": {}, "counts": {}}
    results = body.get("results")
    counts: Dict[str, int] = {}
    if isinstance(results, dict):
        for gid, bucket in results.items():
            if isinstance(bucket, dict):
                counts[str(gid)] = int(
                    bucket.get("total_results")
                    or bucket.get("total_count")
                    or len(bucket.get("results") or [])
                    or 0
                )
            elif isinstance(bucket, list):
                counts[str(gid)] = len(bucket)
    total = body.get("total_count") or body.get("total_results") or body.get("count")
    if total is None:
        total = sum(counts.values()) if counts else 0
    try:
        total_i = int(total)
    except Exception:
        total_i = 0
    return {"total_count": total_i, "grouped_count": counts, "counts": counts}


# CE group_by field → issue property for client-side regrouping.
# Multi-value fields (assignees, labels, modules) can place one issue in many buckets.
_CE_GROUP_TO_ISSUE_KEYS: Dict[str, Tuple[str, ...]] = {
    "state_id": ("state_id", "state"),
    "priority": ("priority",),
    "assignees__id": ("assignee_ids", "assignees"),
    "labels__id": ("label_ids", "labels"),
    "created_by": ("created_by",),
    "cycle_id": ("cycle_id", "cycle"),
    "issue_module__module_id": ("module_ids", "modules"),
    "project_id": ("project_id", "project"),
    "state__group": ("state__group",),
    "target_date": ("target_date",),
    "start_date": ("start_date",),
}


def _scalar_group_key(v: Any) -> Optional[str]:
    """Coerce a single group value to a SPA bucket key string."""
    if v is None or v == "":
        return "None"
    if isinstance(v, dict):
        if v.get("id") is not None:
            return str(v["id"])
        if v.get("pk") is not None:
            return str(v["pk"])
        return None
    return str(v)


def _issue_group_keys(issue: Dict[str, Any], group_by: str) -> List[str]:
    """Return group bucket keys for one issue under a CE group_by field."""
    keys = _CE_GROUP_TO_ISSUE_KEYS.get(group_by) or (group_by,)
    values: List[Any] = []
    for k in keys:
        if k == "state__group":
            detail = issue.get("state_detail")
            if isinstance(detail, dict) and detail.get("group"):
                values.append(detail.get("group"))
            elif issue.get("state__group"):
                values.append(issue.get("state__group"))
            continue
        v = issue.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            if not v:
                continue
            values.extend(v)
        elif isinstance(v, dict) and v.get("id") is not None:
            values.append(v.get("id"))
        else:
            values.append(v)
    if not values:
        return ["None"]
    out: List[str] = []
    for v in values:
        sk = _scalar_group_key(v)
        if sk is not None:
            out.append(sk)
    # de-dupe preserve order
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq or ["None"]


def regroup_issues_by_ce_field(
    items: List[Dict[str, Any]],
    group_by: str,
    sub_group_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Build commercial processIssueResponse buckets from a flat issue list.

    CE GroupedOffsetPaginator puts only the *global* page of issues into groups,
    leaving many buckets as ``{results:[], total_results: N}``. The SPA then
    paints headers with counts (e.g. Simon · 21) and **zero cards**.

    Self-host boards are small enough that we can fetch a large flat page and
    regroup fully so every non-empty group has its issue rows.

    When ``sub_group_by`` is set (project Work items kanban often uses
    ``created_by``), the commercial SPA expects **nested** buckets::

        results[groupId].results[subGroupId] = {results: [...], total_results: N}

    Flat ``results[groupId].results = [...]`` with store.subGroupBy set makes
    ``getIssueIds(group, sub)`` return ``undefined`` → empty /issues/ tray while
    module boards (no sub_group_by) still paint cards.
    """
    seen_ids: set = set()
    if sub_group_by:
        # Nested: results[gk] = { results: { sgk: {results, total_results} }, total_results }
        nested: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            issue = _normalize_issue_item(raw)
            gks = _issue_group_keys(issue, group_by)
            sgks = _issue_group_keys(issue, sub_group_by)
            for gk in gks:
                for sgk in sgks:
                    nested.setdefault(gk, {}).setdefault(sgk, []).append(issue)
        results: Dict[str, Any] = {}
        for gk, sub_map in nested.items():
            sub_results: Dict[str, Any] = {}
            group_total = 0
            group_seen: set = set()
            for sgk, iss in sub_map.items():
                sub_results[sgk] = {"results": iss, "total_results": len(iss)}
                for it in iss:
                    iid = it.get("id")
                    if iid is not None and iid not in group_seen:
                        group_seen.add(iid)
                        group_total += 1
                    if iid is not None:
                        seen_ids.add(iid)
            results[gk] = {"results": sub_results, "total_results": group_total}
        total = len(seen_ids)
        return {
            "results": results,
            "total_count": total,
            "total_results": total,
            "count": total,
            "next_cursor": None,
            "prev_cursor": None,
            "next_page_results": False,
            "prev_page_results": False,
            "grouped_by": group_by,
            "sub_grouped_by": sub_group_by,
            "extra_stats": None,
            "referenced_resources": {},
            "total_groups": len(results),
            "next_group_offset": None,
            "sub_total_groups": sum(
                len(v.get("results") or {})
                for v in results.values()
                if isinstance(v, dict) and isinstance(v.get("results"), dict)
            ),
            "sub_next_group_offset": None,
        }

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        issue = _normalize_issue_item(raw)
        for gk in _issue_group_keys(issue, group_by):
            buckets.setdefault(gk, []).append(issue)
    results: Dict[str, Any] = {}
    for gk, iss in buckets.items():
        results[gk] = {"results": iss, "total_results": len(iss)}
        for it in iss:
            iid = it.get("id")
            if iid is not None:
                seen_ids.add(iid)
    total = len(seen_ids)
    return {
        "results": results,
        "total_count": total,
        "total_results": total,
        "count": total,
        "next_cursor": None,
        "prev_cursor": None,
        "next_page_results": False,
        "prev_page_results": False,
        "grouped_by": group_by,
        "sub_grouped_by": None,
        "extra_stats": None,
        "referenced_resources": {},
        "total_groups": len(results),
        "next_group_offset": None,
    }


def order_state_group_results(
    results: Dict[str, Any],
    states: List[Dict[str, Any]],
    *,
    include_empty: bool = True,
) -> Dict[str, Any]:
    """Order state_id buckets by project state sequence; optionally include empty columns.

    Kanban columns follow Object.keys(groupedIssueIds). Without this, order is
    first-seen issue order (Backlog, In Progress, Todo…) and empty statuses
    like Cancelled/Done never appear as columns.
    """
    if not isinstance(results, dict):
        return results
    ordered: Dict[str, Any] = {}
    seen: set = set()
    # Stable sort: sequence, then name
    def _seq(s: Dict[str, Any]) -> float:
        try:
            return float(s.get("sequence") if s.get("sequence") is not None else 1e12)
        except Exception:
            return 1e12

    for st in sorted(
        [s for s in states if isinstance(s, dict) and s.get("id")],
        key=lambda s: (_seq(s), str(s.get("name") or "")),
    ):
        sid = str(st["id"])
        seen.add(sid)
        if sid in results:
            ordered[sid] = results[sid]
        elif include_empty:
            ordered[sid] = {"results": [], "total_results": 0}
    for k, v in results.items():
        if str(k) not in seen:
            ordered[str(k)] = v
    return ordered


def grouped_response_has_empty_cards(body: Any) -> bool:
    """True when any group advertises total_results>0 but has no issue rows."""
    if not isinstance(body, dict):
        return False
    results = body.get("results")
    if not isinstance(results, dict) or not results:
        # Empty grouped dict while total_count>0 → cards missing entirely
        try:
            tc = int(body.get("total_count") or body.get("total_results") or 0)
        except Exception:
            tc = 0
        return tc > 0 and (results == {} or results is None)
    saw_count = False
    saw_rows = False
    empty_with_count = False
    total_rows = 0
    for bucket in results.values():
        if isinstance(bucket, list):
            if bucket:
                saw_rows = True
                total_rows += len(bucket)
            continue
        if not isinstance(bucket, dict):
            continue
        rows = bucket.get("results")
        n_rows = len(rows) if isinstance(rows, list) else 0
        total_rows += n_rows
        try:
            total = int(bucket.get("total_results") or bucket.get("total_count") or n_rows or 0)
        except Exception:
            total = n_rows
        if total > 0:
            saw_count = True
        if n_rows > 0:
            saw_rows = True
        if total > 0 and n_rows == 0:
            empty_with_count = True
    # classic bug: headers with counts, zero cards anywhere
    if empty_with_count and not saw_rows:
        return True
    # or mixed: some columns empty with counts (still broken for those columns)
    if empty_with_count and saw_count:
        return True
    # totals say work items exist but every bucket is empty
    try:
        tc = int(body.get("total_count") or body.get("total_results") or 0)
    except Exception:
        tc = 0
    if tc > 0 and total_rows == 0:
        return True
    return False


def _extract_issue_items(body: Any) -> List[Dict[str, Any]]:
    """Flatten issue rows from a CE/PI list or grouped response body."""
    items: List[Dict[str, Any]] = []
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return items
    r = body.get("results")
    if isinstance(r, list):
        return [x for x in r if isinstance(x, dict)]
    if isinstance(r, dict):
        for bucket in r.values():
            if isinstance(bucket, dict) and isinstance(bucket.get("results"), list):
                items.extend([x for x in bucket["results"] if isinstance(x, dict)])
            elif isinstance(bucket, list):
                items.extend([x for x in bucket if isinstance(x, dict)])
    return items


async def fetch_flat_issues_for_regroup(
    slug: str,
    project_id: str,
    request: Request,
    base_params: Dict[str, Any],
    *,
    max_pages: int = 10,
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    """Page CE flat issues (no group_by) so board regroup has every card."""
    flat_q = dict(base_params)
    flat_q.pop("group_by", None)
    flat_q.pop("sub_group_by", None)
    flat_q.pop("group_offset", None)
    flat_q.pop("group_per_page", None)
    flat_q.pop("sub_group_offset", None)
    flat_q.pop("sub_group_per_page", None)
    flat_q["per_page"] = str(per_page)
    all_items: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for page in range(max_pages):
        flat_q["cursor"] = f"{per_page}:{page}:0"
        st, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params=flat_q,
        )
        if st != 200:
            # If filters 400, retry once without filters so cards still paint
            if st == 400 and "filters" in flat_q:
                flat_q.pop("filters", None)
                st, body, _ = await ce_get(
                    f"/api/workspaces/{slug}/projects/{project_id}/issues/",
                    request,
                    params=flat_q,
                )
            if st != 200:
                break
        page_items = _extract_issue_items(body)
        if not page_items:
            break
        for it in page_items:
            iid = it.get("id")
            if iid is not None and iid in seen_ids:
                continue
            if iid is not None:
                seen_ids.add(iid)
            all_items.append(it)
        # Stop when CE says no next page or short page
        if isinstance(body, dict):
            if body.get("next_page_results") is False:
                break
            try:
                if int(body.get("total_count") or 0) <= len(all_items):
                    break
            except Exception:
                pass
        if len(page_items) < per_page:
            break
    return all_items

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
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        return None, [p for p in body["results"] if isinstance(p, dict)], None
    if not isinstance(body, list):
        return 500, [], {"error": "unexpected projects payload"}
    return None, [p for p in body if isinstance(p, dict)], None


def normalize_projects_list_response(body: Any) -> Dict[str, Any]:
    """Commercial project list (loadFlatPage) expects a page, not a bare CE array.

    SPA does ``const items = response.results`` then hydrates cards. A bare CE
    list leaves ``results`` undefined → infinite Projects grid skeleton.
    """
    if isinstance(body, list):
        items = [p for p in body if isinstance(p, dict)]
        return as_page(items)
    if isinstance(body, dict):
        out = dict(body)
        results = out.get("results")
        if results is None and isinstance(out.get("data"), list):
            results = out["data"]
            out["results"] = results
        if isinstance(results, list):
            if out.get("total_count") is None:
                out["total_count"] = out.get("count") or out.get("total_results") or len(results)
            if out.get("count") is None:
                out["count"] = len(results)
            if out.get("next_page_results") is None:
                out["next_page_results"] = bool(out.get("next_cursor"))
            if out.get("prev_page_results") is None:
                out["prev_page_results"] = bool(out.get("prev_cursor"))
            if "next_cursor" not in out:
                out["next_cursor"] = None
            if "prev_cursor" not in out:
                out["prev_cursor"] = None
            return out
        # dict without results → empty page
        return as_page([])
    return as_page([])



def _ensure_state_groups(rows: List[Dict[str, Any]], project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """SPA kanban sections: backlog, unstarted, started, completed, cancelled.
    If a group is missing, inject a placeholder state so the column still renders.
    """
    groups_needed = [
        ("backlog", "Backlog", 0),
        ("unstarted", "Todo", 1),
        ("started", "In Progress", 2),
        ("completed", "Done", 3),
        ("cancelled", "Cancelled", 4),
    ]
    present = set()
    for r in rows:
        g = (r.get("group") or r.get("group_key") or "").lower()
        if g:
            present.add(g)
    # alias mapping
    aliases = {"todo": "unstarted", "in_progress": "started", "in-progress": "started", "done": "completed", "canceled": "cancelled"}
    for r in rows:
        g = (r.get("group") or "").lower()
        if g in aliases:
            present.add(aliases[g])
    out = list(rows)
    for group, name, seq in groups_needed:
        if group not in present:
            out.append(
                {
                    "id": f"synthetic-{project_id or 'ws'}-{group}",
                    "name": name,
                    "group": group,
                    "color": "#94a3b8",
                    "sequence": seq,
                    "default": group == "backlog",
                    "project_id": project_id,
                    "project": project_id,
                    "description": "",
                    "is_triage": False,
                }
            )
    return out

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
        values.update(
            {
                "APP_RAIL": True,
                "AI_CHAT": True,
                "AI_CONVERSE": True,
                "AI_AUTOPILOT": True,
                "PI_CHAT": True,
                "PI_CHAT_MOBILE": True,
                "PI_DEDUPE": True,
                "PI_DEDUPE_MOBILE": True,
                "WORKSPACE_PAGES": True,
                "NESTED_PAGES": True,
                "EDITOR_AI_OPS": True,
            }
        )
        return {"values": values}

    @app.get("/api/workspaces/{slug}/features/")
    async def workspace_features_get(slug: str, request: Request):
        # Selfhost: always expose PI/Wiki. Membership is best-effort for workspace id only.
        # Never 404/403 the commercial SPA feature gate (blank Upgrade / grey AI wall).
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status == 401:
            return JSONResponse(
                err_body if isinstance(err_body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        workspace_id = None
        try:
            status, body, _ = await ce_get("/api/users/me/workspaces/", request)
            if status == 200 and isinstance(body, list):
                match = next((w for w in body if isinstance(w, dict) and w.get("slug") == slug), None)
                if match:
                    workspace_id = match.get("id")
        except Exception:
            pass
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

    @app.get("/api/workspaces/{slug}/projects/")
    @app.get("/api/workspaces/{slug}/projects")
    async def workspace_projects_list(slug: str, request: Request):
        """Proxy workspace projects LIST for commercial loadFlatPage.

        CE returns a bare array; SPA needs ``{results, total_count, next_cursor}``.
        Only the collection path is handled here — project detail stays on CE.
        """
        # Pass query params through (per_page, cursor, search, archived, …)
        q = dict(request.query_params) if request.query_params else None
        # When SPA asks for group_by, CE ignores it — still return flat page.
        if q:
            q.pop("group_by", None)
            q.pop("sub_group_by", None)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/projects/", request, params=q or None)
        if status != 200:
            # Fall back to membership-gated list helper
            st2, projects, err = await fetch_ce_projects(slug, request)
            if st2 is not None:
                return JSONResponse(
                    body if isinstance(body, (dict, list)) else {"error": str(body)},
                    status_code=status,
                )
            return normalize_projects_list_response(projects)
        return normalize_projects_list_response(body)

    @app.get("/api/workspaces/{slug}/projects/archived/")
    @app.get("/api/workspaces/{slug}/projects/archived")
    async def workspace_projects_archived(slug: str, request: Request):
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/projects/archived/", request)
        if status != 200:
            return normalize_projects_list_response([])
        return normalize_projects_list_response(body)

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
    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues/total-count")
    async def issues_total_count(slug: str, project_id: str, request: Request):
        """Commercial kanban getWorkItemTotalCount — synthesize from CE issues list.

        Do NOT gate on resolve_membership: CE already enforces auth. A flaky
        membership probe was blanking the board while project meta still showed 21.
        """
        q = clean_ce_issue_params(dict(request.query_params))
        # Prefer a tiny page just for totals
        q.setdefault("per_page", "1")
        q.setdefault("cursor", "1:0:0")
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params=q or None,
        )
        if status == 200:
            return total_count_from_issues_body(normalize_issues_list_response(body))
        if status in (401, 403):
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
        return {"total_count": 0, "grouped_count": {}, "counts": {}}

    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues")
    async def project_issues_list(slug: str, project_id: str, request: Request):
        """Proxy commercial kanban/list board load through PI.

        Cleans commercial-only query params, maps group_by aliases to CE allowlist,
        maps commercial filter field names, and normalizes for processIssueResponse.

        Auth is delegated to CE (cookie/session). We intentionally skip PI
        resolve_membership so a membership-endpoint mismatch cannot blank the board.

        **Always** materialize cards when group_by is set: CE GroupedOffsetPaginator
        (and bad commercial filters) produce headers with counts and empty
        ``results:[]`` — Simon · 21 with zero cards in the DOM. Flat-page +
        regroup fills every non-empty group with real issue rows.
        """
        q = clean_ce_issue_params(dict(request.query_params))
        group_by = q.get("group_by")
        sub_group_by = q.get("sub_group_by")
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params=q or None,
        )
        # CE 400 on unknown commercial filter fields → drop filters and retry
        if status == 400 and "filters" in q:
            q_retry = dict(q)
            q_retry.pop("filters", None)
            status, body, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{project_id}/issues/",
                request,
                params=q_retry or None,
            )
            if status == 200:
                q = q_retry
        if status != 200:
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"error": str(body)},
                status_code=status,
            )
        out = normalize_issues_list_response(body)

        # When SPA asks for groups: always rebuild buckets from a flat page so
        # cards exist under every header (do not rely on sparse detection alone).
        # With sub_group_by the commercial SPA requires nested buckets — always
        # regroup so /issues/ matches modules (which omit sub_group_by).
        if group_by:
            need_regroup = bool(sub_group_by) or (
                grouped_response_has_empty_cards(out)
                or isinstance(out.get("results"), list)
                or (
                    isinstance(out.get("results"), dict)
                    and not any(
                        (
                            isinstance(b, dict)
                            and isinstance(b.get("results"), list)
                            and len(b["results"]) > 0
                        )
                        or (isinstance(b, list) and len(b) > 0)
                        for b in (out.get("results") or {}).values()
                    )
                    and int(out.get("total_count") or out.get("total_results") or 0) > 0
                )
            )
            # Prefer always-regroup for self-host boards (small). If CE already
            # returned full rows for every non-zero bucket, skip the extra trip.
            if not need_regroup and isinstance(out.get("results"), dict):
                for b in out["results"].values():
                    if not isinstance(b, dict):
                        continue
                    try:
                        tr = int(b.get("total_results") or 0)
                    except Exception:
                        tr = 0
                    n = len(b.get("results") or []) if isinstance(b.get("results"), list) else 0
                    # Partial page under a large group → still regroup fully
                    if tr > n and tr > 0:
                        need_regroup = True
                        break
                    # Flat rows while SPA will request sub-groups → re-nest
                    if sub_group_by and isinstance(b.get("results"), list) and n > 0:
                        need_regroup = True
                        break
            if need_regroup:
                flat_items = await fetch_flat_issues_for_regroup(
                    slug, project_id, request, q, max_pages=10, per_page=100
                )
                if flat_items:
                    out = regroup_issues_by_ce_field(
                        flat_items,
                        str(group_by),
                        str(sub_group_by) if sub_group_by else None,
                    )
                    out = normalize_issues_list_response(out)
            elif isinstance(out.get("results"), list) and out["results"]:
                out = regroup_issues_by_ce_field(
                    [x for x in out["results"] if isinstance(x, dict)],
                    str(group_by),
                    str(sub_group_by) if sub_group_by else None,
                )
                out = normalize_issues_list_response(out)

            # State columns: order by sequence + keep empty statuses (Done/Cancelled)
            gb = str(group_by or "")
            if gb in ("state_id", "state") and isinstance(out.get("results"), dict) and not sub_group_by:
                try:
                    st, states_body, _ = await ce_get(
                        f"/api/workspaces/{slug}/projects/{project_id}/states/",
                        request,
                    )
                    states_rows: List[Dict[str, Any]] = []
                    if st == 200:
                        if isinstance(states_body, list):
                            states_rows = [x for x in states_body if isinstance(x, dict)]
                        elif isinstance(states_body, dict):
                            maybe = states_body.get("results") or []
                            if isinstance(maybe, list):
                                states_rows = [x for x in maybe if isinstance(x, dict)]
                    if states_rows:
                        out["results"] = order_state_group_results(
                            out["results"], states_rows, include_empty=True
                        )
                        out["total_groups"] = len(out["results"])
                except Exception:
                    pass

        # Enrich module names so board cards don't flash UUIDs
        try:
            mod_map = await _module_name_map(slug, project_id, request)
            if mod_map:
                results = out.get("results")
                if isinstance(results, list):
                    out["results"] = [
                        _enrich_issue_modules(x, mod_map) if isinstance(x, dict) else x for x in results
                    ]
                elif isinstance(results, dict):
                    for k, bucket in list(results.items()):
                        if isinstance(bucket, dict) and isinstance(bucket.get("results"), list):
                            bucket["results"] = [
                                _enrich_issue_modules(x, mod_map) if isinstance(x, dict) else x
                                for x in bucket["results"]
                            ]
                        elif isinstance(bucket, dict) and isinstance(bucket.get("results"), dict):
                            # Nested sub_group_by buckets
                            for sk, sub in list(bucket["results"].items()):
                                if isinstance(sub, dict) and isinstance(sub.get("results"), list):
                                    sub["results"] = [
                                        _enrich_issue_modules(x, mod_map)
                                        if isinstance(x, dict)
                                        else x
                                        for x in sub["results"]
                                    ]
                        elif isinstance(bucket, list):
                            results[k] = [
                                _enrich_issue_modules(x, mod_map) if isinstance(x, dict) else x for x in bucket
                            ]
        except Exception:
            pass
        # Marker so we can confirm this code path is live
        if isinstance(out, dict):
            out.setdefault("extra_stats", None)
            try:
                es = out.get("extra_stats")
                if not isinstance(es, dict):
                    es = {}
                es["cosmic_board_fix"] = "v42-always-regroup"
                out["extra_stats"] = es
            except Exception:
                pass
        return out

    @app.get("/api/workspaces/{slug}/user-work-items/{user_id}/total-count/")
    @app.get("/api/workspaces/{slug}/user-work-items/{user_id}/total-count")
    async def user_work_items_total_count(slug: str, user_id: str, request: Request):
        """Commercial My Work: getUserProfileWorkItemTotalCount.

        SPA calls user-work-items/{id}/total-count/ but CE only has user-issues/{id}/.
        """
        q = clean_ce_issue_params(dict(request.query_params))
        q.setdefault("per_page", "1")
        q.setdefault("cursor", "1:0:0")
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/user-issues/{user_id}/",
            request,
            params=q or None,
        )
        if status == 200:
            return total_count_from_issues_body(normalize_issues_list_response(body))
        if status in (401, 403):
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
        # Soft-fail so My Work doesn't spin forever
        return {"total_count": 0, "grouped_count": {}, "counts": {}}

    @app.get("/api/workspaces/{slug}/user-work-items/{user_id}/")
    @app.get("/api/workspaces/{slug}/user-work-items/{user_id}")
    async def user_work_items_list(slug: str, user_id: str, request: Request):
        """Alias commercial user-work-items list → CE user-issues (normalized)."""
        q = clean_ce_issue_params(dict(request.query_params))
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/user-issues/{user_id}/",
            request,
            params=q or None,
        )
        if status != 200:
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"error": str(body)},
                status_code=status,
            )
        return normalize_issues_list_response(body)

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

        # SPA does results.map(e => e.member) — must nest lite under `.member`.
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
            member_lite = _member_lite_from_user(
                profile,
                workspace_id=ws_id,
                role=row.get("role"),
                membership_id=row.get("id"),
                is_active=row.get("is_active", True),
            )
            # filter=assignable (default SPA scope): hide bots
            filt = (request.query_params.get("filter") or "assignable").lower()
            if filt in ("assignable", "mentionable") and member_lite.get("is_bot"):
                continue
            lite.append(
                {
                    "id": row.get("id") or user_id,
                    "role": row.get("role"),
                    "role_slug": member_lite.get("role_slug"),
                    "member": member_lite,
                    "is_active": member_lite.get("is_active", True),
                    "joined_at": row.get("created_at") or row.get("joined_at"),
                }
            )

        def _member_search_blob(row: Dict[str, Any]) -> str:
            m = row.get("member") if isinstance(row.get("member"), dict) else row
            parts = [
                m.get("display_name") or "",
                m.get("first_name") or "",
                m.get("last_name") or "",
                m.get("email") or "",
            ]
            return " ".join(parts).lower()

        search = (request.query_params.get("search") or "").strip().lower()
        if search:
            lite = [m for m in lite if search in _member_search_blob(m)]
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
            member_lite = _member_lite_from_user(
                member,
                workspace_id=ws_id,
                role=row.get("role"),
                membership_id=row.get("id"),
                is_active=row.get("is_active", True),
            )
            filt = (request.query_params.get("filter") or "assignable").lower()
            if filt in ("assignable", "mentionable") and member_lite.get("is_bot"):
                continue
            lite.append(
                {
                    "id": row.get("id") or member_lite.get("id"),
                    "role": row.get("role"),
                    "role_slug": member_lite.get("role_slug"),
                    "member": member_lite,
                    "is_active": member_lite.get("is_active", True),
                    "joined_at": row.get("created_at") or row.get("joined_at"),
                }
            )
        raw_ids = request.query_params.get("ids") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        if wanted:
            return [
                m
                for m in lite
                if str(m.get("id")) in wanted
                or str((m.get("member") or {}).get("id")) in wanted
            ]
        search = (request.query_params.get("search") or "").strip().lower()
        if search:
            def _blob(row: Dict[str, Any]) -> str:
                m = row.get("member") if isinstance(row.get("member"), dict) else {}
                return " ".join(
                    [
                        m.get("display_name") or "",
                        m.get("first_name") or "",
                        m.get("last_name") or "",
                        m.get("email") or "",
                    ]
                ).lower()

            lite = [m for m in lite if search in _blob(m)]
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
        """Spoof instance version/edition so mobile unlocks Pilot AI.

        Official Plane Cloud returns current_version=\"latest\" (latest_version=null).
        That string is what the commercial mobile client treats as full SaaS product
        surface (Wiki + Plane AI). Semver-only spoofs (e.g. 3.0.0) load the app and
        can enable Wiki via feature flags, but still hide the AI tile.
        """
        status, body, _ = await ce_get("/api/instances/", request)
        if status != 200 or not isinstance(body, dict):
            return JSONResponse(
                body if isinstance(body, dict) else {"error": "instances unavailable"},
                status_code=status if status else 502,
            )
        out = dict(body)
        inst = dict(out.get("instance") or {})
        # Default matches api.plane.so cloud instances (unlocks mobile Plane AI).
        spoof = (os.environ.get("PLANE_SPOOF_VERSION") or "latest").strip() or "latest"
        edition = (os.environ.get("PLANE_SPOOF_EDITION") or "PLANE_CLOUD").strip() or "PLANE_CLOUD"
        inst["current_version"] = spoof
        # Cloud sets latest_version to null when current_version is "latest".
        if spoof == "latest":
            inst["latest_version"] = None
        else:
            inst["latest_version"] = spoof
        inst["edition"] = edition
        inst["is_current_version_deprecated"] = False
        out["instance"] = inst
        cfg = dict(out.get("config") or {})
        cfg["has_llm_configured"] = True
        cfg.setdefault("is_email_password_enabled", True)
        # Keep magic off unless SMTP works — avoid empty "continue" into magic code
        cfg.setdefault("is_magic_login_enabled", False)
        cfg.setdefault("enable_turnstile", False)
        # Official mobile hides Pilot when is_self_managed=true (cloud clients expect SaaS surface).
        # Override with PLANE_SPOOF_SELF_MANAGED=1 only if you need self-host admin banners.
        cfg["is_self_managed"] = os.environ.get("PLANE_SPOOF_SELF_MANAGED", "0").strip() == "1"
        domain = os.environ.get("APP_DOMAIN", "plane.cosmicboosts.store")
        base = f"https://{domain}"
        cfg["app_base_url"] = cfg.get("app_base_url") or base
        cfg["space_base_url"] = cfg.get("space_base_url") or cfg["app_base_url"]
        # Point product servers at ourselves (disco.plane.so equivalents).
        cfg["payment_server_base_url"] = base
        cfg["feature_flag_server_base_url"] = base
        # Cloud uses false (disabled) for prime — avoid clients probing a 404 prime path.
        cfg["prime_server_base_url"] = False
        cfg.setdefault("silo_base_url", base)
        # Extra cloud config keys some clients probe (safe defaults).
        cfg.setdefault("are_access_tokens_disabled", False)
        cfg.setdefault("is_airgapped", False)
        cfg.setdefault("min_desktop_version", "3.0.0")
        cfg.setdefault("desktop_link_handoff_available", True)
        out["config"] = cfg
        return out

    @app.api_route("/api/feature-flags/", methods=["GET", "POST"])
    @app.api_route("/api/feature-flags", methods=["GET", "POST"])
    async def feature_flags_disco_compat(request: Request):
        """Disco-compatible feature-flag endpoint used by GraphQL FeatureFlagQuery
        and commercial clients (POST {workspace_slug, user_id} → {default: {FLAGS}}).
        """
        values = dict((BUSINESS_FLAGS or {}).get("values") or BUSINESS_FLAGS or {})
        for k in list(values.keys()):
            values[k] = True
        values.update(
            {
                "APP_RAIL": True,
                "AI_CHAT": True,
                "AI_CONVERSE": True,
                "AI_AUTOPILOT": True,
                "AI_DEDUPE": True,
                "AI_FILE_UPLOADS": True,
                "AI_PAGES_BLOCKS": True,
                "AI_PAGES_SUMMARY": True,
                "AI_LABEL_PREDICTION": True,
                "AI_MCP_CONNECTORS": True,
                "AI_TEXT_TO_PQL": True,
                "AI_PAGES_EDIT": True,
                "AI_SKILLS": True,
                "PI_CHAT": True,
                "PI_CHAT_MOBILE": True,
                "PI_DEDUPE": True,
                "PI_DEDUPE_MOBILE": True,
                "PI_CONVERSE": True,
                "PI_ACTIONS": True,
                "WORKSPACE_PAGES": True,
                "NESTED_PAGES": True,
                "EDITOR_AI_OPS": True,
                "INITIATIVES": True,
                "TEAMSPACES": True,
                "TIMELINE_DEPENDENCY": True,
                "INBOX_STACKING": True,
                "EPICS": True,
                "ADVANCED_SEARCH": True,
            }
        )
        # Shape expected by plane.graphql.queries.feature_flag.fetch_feature_flags:
        # response.json().values() → iterable of flag maps.
        return {"default": values}

    @app.get("/api/workspaces/{slug}/cycles-lite/")
    async def cycles_lite(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        return []

    def _default_preferences() -> Dict[str, Any]:
        """Mark onboarding/product tours as already dismissed so SPA stops re-showing them."""
        return {
            # Common commercial tour / onboarding keys (SPA ignores unknown keys safely)
            "is_onboarded": True,
            "is_workspace_onboarded": True,
            "has_dismissed_product_tour": True,
            "has_dismissed_sidebar_tour": True,
            "has_dismissed_ai_tour": True,
            "has_dismissed_wiki_tour": True,
            "has_dismissed_project_tour": True,
            "has_dismissed_work_item_tour": True,
            # EpicMigrationModal: if explored_features.epic_migration !== true it opens
            # a blocking walkthrough (and can leave raw "Step {current} of {total}" if ICU fails).
            "explored_features": {
                "epic_migration": True,
            },
            "dismissed_tours": [
                "product",
                "sidebar",
                "ai",
                "wiki",
                "project",
                "work_item",
                "home",
                "app_rail",
                "my_work",
                "epic_migration",
            ],
            "product_tours": {
                "dismissed": True,
                "completed": True,
                "skipped": True,
            },
            "tours": {
                "product": {"dismissed": True, "completed": True},
                "sidebar": {"dismissed": True, "completed": True},
                "ai": {"dismissed": True, "completed": True},
                "wiki": {"dismissed": True, "completed": True},
            },
        }

    @app.get("/api/workspaces/{slug}/preferences/")
    async def workspace_preferences_get(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        cur = dict(_default_preferences())
        cur.update(PREF_STORE.get(slug, {}) or {})
        # Never re-open the blocking Epics migration walkthrough once dismissed.
        explored = cur.get("explored_features")
        if not isinstance(explored, dict):
            explored = {}
        else:
            explored = dict(explored)
        explored["epic_migration"] = True
        cur["explored_features"] = explored
        return cur

    @app.api_route("/api/workspaces/{slug}/preferences/", methods=["PATCH", "PUT", "POST"])
    async def workspace_preferences_write(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        try:
            patch = await request.json()
        except Exception:
            patch = {}
        cur = dict(_default_preferences())
        cur.update(PREF_STORE.get(slug, {}) or {})
        if isinstance(patch, dict):
            # Deep-merge nested tour maps so a partial patch can't re-open tours.
            for k, v in patch.items():
                if isinstance(v, dict) and isinstance(cur.get(k), dict):
                    nested = dict(cur[k])
                    nested.update(v)
                    cur[k] = nested
                else:
                    cur[k] = v
        # Keep epic migration explored after any write (including partial patches).
        explored = cur.get("explored_features")
        if not isinstance(explored, dict):
            explored = {}
        else:
            explored = dict(explored)
        explored["epic_migration"] = True
        cur["explored_features"] = explored
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
    @app.get("/api/workspaces/{slug}/projects/{project_id}/issues/meta")
    async def issues_meta(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        # Prefer real counts from CE issues list so commercial board isn't empty
        q = clean_ce_issue_params(dict(request.query_params))
        q["per_page"] = "1"
        q.setdefault("cursor", "1:0:0")
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/",
            request,
            params=q or None,
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
        Auth delegated to CE — no PI membership hard-gate (blanked kanban columns).
        """
        raw_ids = request.query_params.get("ids") or request.query_params.get("id") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        raw_pids = request.query_params.get("project_ids") or ""
        wanted_projects = {x.strip() for x in raw_pids.split(",") if x.strip()}

        # CE: workspace-level states list (all projects)
        status, body, _ = await ce_get(f"/api/workspaces/{slug}/states/", request)
        if status in (401, 403):
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
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

        normalized = [_normalize_state_lite(r) for r in rows]
        # When no id filter, ensure group coverage per project
        if not wanted:
            by_proj: Dict[str, List[Dict[str, Any]]] = {}
            for r in normalized:
                pid = str(r.get("project_id") or r.get("project") or "")
                by_proj.setdefault(pid, []).append(r)
            merged: List[Dict[str, Any]] = []
            for pid, rs in by_proj.items():
                merged.extend(_ensure_state_groups(rs, pid or None))
            if merged:
                return merged
            return _ensure_state_groups(normalized, None)
        return normalized

    @app.get("/api/workspaces/{slug}/projects/{project_id}/states-lite/")
    async def project_states_lite(slug: str, project_id: str, request: Request):
        """SPA getStatesLite expects data.results; listStatesLite expects paginated body."""
        raw_ids = request.query_params.get("ids") or ""
        wanted = {x.strip() for x in raw_ids.split(",") if x.strip()}
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/states/", request
        )
        if status in (401, 403):
            return JSONResponse(
                body if isinstance(body, (dict, list)) else {"detail": str(body)},
                status_code=status,
            )
        rows: List[Dict[str, Any]] = []
        if status == 200 and isinstance(body, list):
            rows = [x for x in body if isinstance(x, dict)]
        elif status == 200 and isinstance(body, dict):
            maybe = body.get("results") or body.get("data") or []
            if isinstance(maybe, list):
                rows = [x for x in maybe if isinstance(x, dict)]
        if wanted:
            rows = [r for r in rows if str(r.get("id")) in wanted]
        out = [_normalize_state_lite(r, project_id) for r in rows]
        out = _ensure_state_groups(out, project_id)
        return _paginate_results(out)

    async def _module_name_map(slug: str, project_id: str, request: Request) -> Dict[str, str]:
        """id → name for project modules (cached per request via local dict)."""
        out: Dict[str, str] = {}
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/modules/", request
        )
        rows: List[Dict[str, Any]] = []
        if status == 200:
            if isinstance(body, list):
                rows = [x for x in body if isinstance(x, dict)]
            elif isinstance(body, dict):
                maybe = body.get("results") or []
                if isinstance(maybe, list):
                    rows = [x for x in maybe if isinstance(x, dict)]
        for r in rows:
            mid = r.get("id")
            if mid:
                out[str(mid)] = r.get("name") or r.get("title") or str(mid)
        return out

    def _enrich_issue_modules(issue: Dict[str, Any], mod_map: Dict[str, str]) -> Dict[str, Any]:
        """Ensure module fields show names, not bare UUIDs."""
        if not isinstance(issue, dict):
            return issue
        # module_ids: list of uuid strings
        mids = issue.get("module_ids") or issue.get("module_id")
        if isinstance(mids, str):
            mids = [mids]
        if isinstance(mids, list) and mids:
            issue["module_ids"] = [str(x) for x in mids if x]
            modules = []
            for mid in issue["module_ids"]:
                modules.append({"id": mid, "name": mod_map.get(str(mid)) or mid})
            issue["modules"] = modules
            # some SPA paths read singular module
            if len(modules) == 1:
                issue["module"] = modules[0]
                issue["module_detail"] = modules[0]
        # modules already present but missing names
        mods_list = issue.get("modules")
        if isinstance(mods_list, list):
            enriched = []
            for m in mods_list:
                if isinstance(m, dict):
                    mid = str(m.get("id") or "")
                    name = m.get("name") or mod_map.get(mid) or mid
                    enriched.append({**m, "id": mid or m.get("id"), "name": name})
                elif isinstance(m, str):
                    enriched.append({"id": m, "name": mod_map.get(m) or m})
                else:
                    enriched.append(m)
            issue["modules"] = enriched
        return issue

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items")
    async def work_items_alias(slug: str, project_id: str, request: Request):
        """Alias commercial work-items list to CE issues (same normalizer as issues list)."""
        # Reuse the board list proxy so spreadsheet/layout paths stay in sync
        return await project_issues_list(slug, project_id, request)


    # ---- Commercial SPA work-item path aliases → CE issues API ----
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/",
        methods=["GET", "PATCH", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}",
        methods=["GET", "PATCH", "DELETE"],
    )
    async def work_item_detail(slug: str, project_id: str, issue_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        path = f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"
        if request.method == "GET":
            status, body, _ = await ce_get(path, request)
        elif request.method == "PATCH":
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            # Map commercial field aliases → CE issue fields for assign/unassign
            if isinstance(payload, dict):
                if "assignees" in payload and "assignees_list" not in payload:
                    payload["assignees_list"] = payload.get("assignees")
                if "assignee_ids" in payload and "assignees_list" not in payload:
                    payload["assignees_list"] = payload.get("assignee_ids")
            status, body, _ = await ce_patch(path, request, json_body=payload)
        else:
            status, body, _ = await ce_delete(path, request)
        if status >= 400:
            return JSONResponse(body if isinstance(body, (dict, list)) else {"error": str(body)}, status_code=status)
        # Enrich module field with name when only id present
        if isinstance(body, dict) and request.method in ("GET", "PATCH"):
            mod_map = await _module_name_map(slug, project_id, request)
            body = _enrich_issue_modules(body, mod_map)
            # Also pull issue-module relation if CE stores modules separately
            if not body.get("modules") and not body.get("module_ids"):
                st3, rel, _ = await ce_get(
                    f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/modules/",
                    request,
                )
                if st3 == 200:
                    rows = rel if isinstance(rel, list) else (rel.get("results") if isinstance(rel, dict) else [])
                    if isinstance(rows, list) and rows:
                        mods = []
                        for r in rows:
                            if isinstance(r, dict):
                                mid = str(r.get("id") or r.get("module") or r.get("module_id") or "")
                                name = r.get("name") or mod_map.get(mid) or mid
                                if mid:
                                    mods.append({"id": mid, "name": name})
                        if mods:
                            body["modules"] = mods
                            body["module_ids"] = [m["id"] for m in mods]
                            if len(mods) == 1:
                                body["module"] = mods[0]
        return body

    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/subscribers/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/subscribers",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/subscribers/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/subscribers",
        methods=["GET", "POST"],
    )
    async def issue_subscribers_alias(slug: str, project_id: str, issue_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        if request.method == "GET":
            status, body, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/issue-subscribers/",
                request,
            )
            if status == 404 or status >= 400:
                return []
            # SPA: subscribers.find(e => e === currentUserId) — wants list of user id strings
            rows = body if isinstance(body, list) else (body.get("results") if isinstance(body, dict) else [])
            if not isinstance(rows, list):
                return []
            ids = []
            for r in rows:
                if isinstance(r, str):
                    ids.append(r)
                elif isinstance(r, dict):
                    sid = r.get("subscriber") or r.get("subscriber_id") or r.get("id") or r.get("member")
                    if isinstance(sid, dict):
                        sid = sid.get("id")
                    if sid:
                        ids.append(str(sid))
            return ids
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        status, body, _ = await ce_post(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/issue-subscribers/",
            request,
            json_body=payload,
        )
        return JSONResponse(body if isinstance(body, (dict, list)) else {"ok": True}, status_code=status if status else 200)

    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/subscribers/me/",
        methods=["GET", "POST", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/subscribers/me",
        methods=["GET", "POST", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/subscribers/me/",
        methods=["GET", "POST", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/subscribers/me",
        methods=["GET", "POST", "DELETE"],
    )
    async def issue_subscribe_me(slug: str, project_id: str, issue_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        path = f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/subscribe/"
        if request.method == "GET":
            status, body, _ = await ce_get(path, request)
        elif request.method == "POST":
            status, body, _ = await ce_post(path, request, json_body={})
        else:
            status, body, _ = await ce_delete(path, request)
        # SPA status() checks data.subscribed; list path uses user ids separately.
        if request.method == "GET":
            if status < 400 and isinstance(body, dict):
                sub = bool(body.get("subscribed") if "subscribed" in body else body.get("is_subscribed"))
                return {"subscribed": sub, "is_subscribed": sub}
            # fallback: check subscriber list
            st2, lst, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/issue-subscribers/",
                request,
            )
            st_me, me, _ = await ce_get("/api/users/me/", request)
            uid = str((me or {}).get("id") or "") if isinstance(me, dict) else ""
            ids = []
            if st2 == 200:
                rows = lst if isinstance(lst, list) else (lst.get("results") if isinstance(lst, dict) else [])
                for r in rows or []:
                    if isinstance(r, str):
                        ids.append(r)
                    elif isinstance(r, dict):
                        sid = r.get("subscriber") or r.get("id")
                        if isinstance(sid, dict):
                            sid = sid.get("id")
                        if sid:
                            ids.append(str(sid))
            sub = uid in ids
            return {"subscribed": sub, "is_subscribed": sub}
        if status >= 400:
            return {"subscribed": request.method != "DELETE", "is_subscribed": request.method != "DELETE"}
        return {"subscribed": request.method != "DELETE", "is_subscribed": request.method != "DELETE"}

    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/votes/",
        methods=["GET", "POST", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/votes",
        methods=["GET", "POST", "DELETE"],
    )
    async def work_item_votes(slug: str, project_id: str, issue_id: str, request: Request):
        """Commercial SPA expects a LIST of {vote: 1|-1, actor, actor_detail} (see issue-votes)."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)

        key = f"{project_id}:{issue_id}"
        votes = list(VOTE_STORE.get(key) or [])

        # Resolve current user for actor fields
        st_me, me, _ = await ce_get("/api/users/me/", request)
        me = me if isinstance(me, dict) else {}
        uid = str(me.get("id") or "")
        actor_detail = {
            "id": uid,
            "display_name": me.get("display_name") or me.get("first_name") or me.get("email") or "User",
            "first_name": me.get("first_name") or "",
            "last_name": me.get("last_name") or "",
            "avatar": me.get("avatar") or "",
            "avatar_url": me.get("avatar_url"),
        }

        if request.method == "GET":
            # Must be a bare array — SPA does s.filter(e => e.vote === 1)
            return votes

        if request.method == "DELETE":
            VOTE_STORE[key] = [v for v in votes if str(v.get("actor") or "") != uid]
            return {"ok": True}

        # POST add/toggle vote
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        raw = payload.get("vote")
        try:
            vote_val = int(raw)
        except Exception:
            vote_val = 1 if str(raw).lower() in ("1", "up", "upvote", "true") else -1
        if vote_val not in (1, -1):
            vote_val = 1 if vote_val > 0 else -1

        # Replace existing vote from this actor
        votes = [v for v in votes if str(v.get("actor") or "") != uid]
        votes.append(
            {
                "id": str(uuid.uuid4()),
                "issue": issue_id,
                "project": project_id,
                "workspace": slug,
                "vote": vote_val,
                "actor": uid,
                "actor_detail": actor_detail,
            }
        )
        VOTE_STORE[key] = votes
        return votes[-1]

    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/updates/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/updates",
        methods=["GET", "POST"],
    )
    async def work_item_updates(slug: str, project_id: str, issue_id: str, request: Request):
        """SPA store does updates.map(e => e.id) — MUST return a bare array of objects with id."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)

        key = f"{project_id}:{issue_id}"
        stored = list(UPDATE_STORE.get(key) or [])

        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            st_me, me, _ = await ce_get("/api/users/me/", request)
            me = me if isinstance(me, dict) else {}
            row = {
                "id": str(uuid.uuid4()),
                "issue": issue_id,
                "project": project_id,
                "workspace": slug,
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "created_by": me.get("id"),
                "created_by_detail": {
                    "id": me.get("id"),
                    "display_name": me.get("display_name") or me.get("first_name") or "",
                },
                "description_html": payload.get("description_html") or payload.get("description") or "",
                "description_stripped": payload.get("description_stripped") or "",
                "status": payload.get("status") or "done",
                **{k: v for k, v in payload.items() if k not in ("id",)},
            }
            stored.insert(0, row)
            UPDATE_STORE[key] = stored
            return row

        # GET: merge stored status-updates + CE activity history mapped to update shape
        out = list(stored)
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/history/",
            request,
        )
        hist_rows: List[Dict[str, Any]] = []
        if status == 200:
            if isinstance(body, list):
                hist_rows = [x for x in body if isinstance(x, dict)]
            elif isinstance(body, dict):
                maybe = body.get("results") or body.get("data") or []
                if isinstance(maybe, list):
                    hist_rows = [x for x in maybe if isinstance(x, dict)]
        for h in hist_rows:
            hid = h.get("id") or str(uuid.uuid4())
            out.append(
                {
                    "id": str(hid),
                    "issue": issue_id,
                    "project": project_id,
                    "workspace": slug,
                    "created_at": h.get("created_at") or h.get("timestamp"),
                    "updated_at": h.get("created_at") or h.get("timestamp"),
                    "created_by": (h.get("actor_detail") or {}).get("id") if isinstance(h.get("actor_detail"), dict) else h.get("actor"),
                    "created_by_detail": h.get("actor_detail") or {},
                    "description_html": h.get("comment_html")
                    or h.get("description_html")
                    or f"<p>{h.get('field') or 'updated'} → {h.get('new_value') or h.get('verb') or ''}</p>",
                    "description_stripped": str(h.get("new_value") or h.get("verb") or h.get("field") or "Update"),
                    "status": "history",
                    "source": "history",
                }
            )
        return out

    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/updates/{update_id}/",
        methods=["PATCH", "DELETE"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/updates/{update_id}",
        methods=["PATCH", "DELETE"],
    )
    async def work_item_update_one(slug: str, project_id: str, issue_id: str, update_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        key = f"{project_id}:{issue_id}"
        stored = list(UPDATE_STORE.get(key) or [])
        if request.method == "DELETE":
            UPDATE_STORE[key] = [u for u in stored if str(u.get("id")) != str(update_id)]
            return {"ok": True}
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        for i, u in enumerate(stored):
            if str(u.get("id")) == str(update_id):
                if isinstance(payload, dict):
                    stored[i] = {**u, **payload, "id": u.get("id")}
                UPDATE_STORE[key] = stored
                return stored[i]
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/pages/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/pages")
    async def work_item_pages_stub(slug: str, project_id: str, issue_id: str, request: Request):
        return []

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/state-duration/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/state-duration")
    async def work_item_state_duration_stub(slug: str, project_id: str, issue_id: str, request: Request):
        return {"results": [], "total_duration": 0}

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/relations/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/relations")
    async def work_item_relations(slug: str, project_id: str, issue_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/issue-relation/",
            request,
        )
        if status != 200:
            return []
        return body if body is not None else []

    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/relation-dependencies/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/work-items/{issue_id}/relation-dependencies")
    async def work_item_relation_deps(slug: str, project_id: str, issue_id: str, request: Request):
        return []

    @app.get("/api/workspaces/{slug}/enhanced-search/")
    @app.get("/api/workspaces/{slug}/enhanced-search")
    async def enhanced_search_alias(slug: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        q = str(request.url.query or "")
        # Prefer entity-search, fall back to search
        for base in (
            f"/api/workspaces/{slug}/entity-search/",
            f"/api/workspaces/{slug}/search/",
        ):
            path = f"{base}?{q}" if q else base
            status, body, _ = await ce_get(path, request)
            if status == 200:
                return body if body is not None else {"results": []}
        return {"results": [], "count": 0}

    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/project-stats/")
    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/project-stats")
    async def user_profile_project_stats(slug: str, user_id: str, request: Request):
        """My Work sidebar — per-project counts for the user."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, projects, body = await fetch_ce_projects(slug, request)
        if status is not None:
            return as_page([])
        rows: List[Dict[str, Any]] = []
        for p in projects[:40]:
            pid = p.get("id")
            if not pid:
                continue
            # Best-effort count of issues assigned to user in this project
            st, ib, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{pid}/issues/",
                request,
                params={
                    "assignees": user_id,
                    "per_page": "1",
                    "cursor": "1:0:0",
                },
            )
            total = 0
            if st == 200 and isinstance(ib, dict):
                total = int(ib.get("total_count") or ib.get("count") or ib.get("total_results") or 0)
            rows.append(
                {
                    "project_id": pid,
                    "project": pid,
                    "id": pid,
                    "name": p.get("name"),
                    "identifier": p.get("identifier"),
                    "total_issues": total,
                    "completed_issues": 0,
                    "pending_issues": total,
                    "created_issues": 0,
                    "subscribed_issues": 0,
                }
            )
        return as_page(rows)

    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/user-work-items/")
    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/user-work-items")
    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/issues/")
    @app.get("/api/workspaces/{slug}/user-profile/{user_id}/issues")
    async def user_profile_work_items(slug: str, user_id: str, request: Request):
        """My Work list — aggregate assigned issues across projects."""
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, projects, _ = await fetch_ce_projects(slug, request)
        if status is not None:
            return as_page([])
        q = dict(request.query_params)
        q.setdefault("assignees", user_id)
        all_items: List[Dict[str, Any]] = []
        for p in projects[:20]:
            pid = p.get("id")
            if not pid:
                continue
            st, body, _ = await ce_get(
                f"/api/workspaces/{slug}/projects/{pid}/issues/",
                request,
                params=q or None,
            )
            if st != 200:
                continue
            if isinstance(body, dict):
                results = body.get("results")
                if isinstance(results, list):
                    for it in results:
                        if isinstance(it, dict):
                            it.setdefault("project_id", pid)
                            all_items.append(it)
                elif isinstance(results, dict):
                    for bucket in results.values():
                        if isinstance(bucket, dict):
                            for it in bucket.get("results") or []:
                                if isinstance(it, dict):
                                    it.setdefault("project_id", pid)
                                    all_items.append(it)
                        elif isinstance(bucket, list):
                            for it in bucket:
                                if isinstance(it, dict):
                                    it.setdefault("project_id", pid)
                                    all_items.append(it)
            elif isinstance(body, list):
                for it in body:
                    if isinstance(it, dict):
                        it.setdefault("project_id", pid)
                        all_items.append(it)
        return as_page(all_items)

    @app.get("/api/workspaces/{slug}/projects/{project_id}/issue-labels-lite/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/issue-labels-lite")
    async def issue_labels_lite(slug: str, project_id: str, request: Request):
        err_status, role, err_body = await resolve_membership(slug, request)
        if err_status is not None:
            return JSONResponse(err_body or {"error": "Workspace not found"}, status_code=err_status)
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/issue-labels/", request
        )
        if status != 200:
            status, body, _ = await ce_get(f"/api/workspaces/{slug}/labels/", request)
        if status != 200:
            return []
        if isinstance(body, dict) and "results" in body:
            return body["results"]
        return body if isinstance(body, list) else []

    @app.get("/api/workspaces/{slug}/runnerctl/scripts/")
    @app.get("/api/workspaces/{slug}/runnerctl/scripts")
    async def runnerctl_scripts_stub(slug: str, request: Request):
        return []

    @app.get("/api/workspaces/{slug}/runnerctl/health/")
    @app.get("/api/workspaces/{slug}/runnerctl/health")
    async def runnerctl_health_stub(slug: str, request: Request):
        """Settings → Runner probes this; CE has no runnerctl."""
        return {
            "status": "ok",
            "healthy": True,
            "available": False,
            "message": "Runner not configured on this self-hosted instance",
        }

    @app.get("/api/workspaces/{slug}/pages/templates/")
    @app.get("/api/workspaces/{slug}/pages/templates")
    async def pages_templates_stub(slug: str, request: Request):
        return []

    @app.get("/api/workspaces/{slug}/projects/{project_id}/pages/public/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/pages/public")
    async def project_pages_public_stub(slug: str, project_id: str, request: Request):
        """Commercial pages list requests public pages collection (CE missing)."""
        return as_page([])

    @app.get("/api/workspaces/{slug}/projects/{project_id}/views-lite/")
    @app.get("/api/workspaces/{slug}/projects/{project_id}/views-lite")
    async def project_views_lite(slug: str, project_id: str, request: Request):
        """Alias commercial views-lite → CE project views list."""
        status, body, _ = await ce_get(
            f"/api/workspaces/{slug}/projects/{project_id}/views/", request
        )
        if status != 200:
            return []
        if isinstance(body, dict) and isinstance(body.get("results"), list):
            return body["results"]
        return body if isinstance(body, list) else []

    # ---- Export / download stubs (SPA expects 200 + file-ish payload, not 404) ----
    @app.api_route(
        "/api/workspaces/{slug}/export-issues/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/export-issues",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/export-issues/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/export-issues",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issue-exports/",
        methods=["GET", "POST"],
    )
    @app.api_route(
        "/api/workspaces/{slug}/projects/{project_id}/issue-exports",
        methods=["GET", "POST"],
    )
    async def export_issues_stub(slug: str, request: Request, project_id: Optional[str] = None):
        # Return an empty CSV so download buttons complete instead of spinning forever.
        csv_body = "id,name,state,priority,assignees\n"
        return Response(
            content=csv_body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="export.csv"'},
        )

    @app.get("/api/workspaces/{slug}/exporters/")
    @app.get("/api/workspaces/{slug}/exporters")
    @app.post("/api/workspaces/{slug}/exporters/")
    @app.post("/api/workspaces/{slug}/exporters")
    async def exporters_stub(slug: str, request: Request):
        if request.method == "GET":
            return []
        return {"id": str(uuid.uuid4()), "status": "completed", "url": None, "ok": True}



    # ---- User profile tours: force dismissed so SPA stops re-showing onboarding/tours ----
    @app.get("/api/users/me/profile/")
    @app.get("/api/users/me/profile")
    async def users_me_profile_get(request: Request):
        status, body, _ = await ce_get("/api/users/me/profile/", request)
        if status == 401:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=401,
            )
        if status != 200 or not isinstance(body, dict):
            # synthesize minimal profile
            st2, me, _ = await ce_get("/api/users/me/", request)
            me = me if isinstance(me, dict) else {}
            body = {"id": me.get("id"), "user": me.get("id")}
        body = dict(body)
        body["is_tour_completed"] = True
        body["is_navigation_tour_completed"] = True
        body["is_onboarded"] = True
        body["is_mobile_onboarded"] = True
        body["onboarding_step"] = {
            "profile_complete": True,
            "workspace_create": True,
            "workspace_invite": True,
            "workspace_join": True,
        }
        body["mobile_onboarding_step"] = {
            "profile_complete": True,
            "workspace_create": True,
            "workspace_join": True,
        }
        # All product tour surfaces completed
        body["product_tour"] = {
            "work_items": True,
            "cycles": True,
            "modules": True,
            "intake": True,
            "pages": True,
            "wiki": True,
            "ai": True,
            "projects": True,
            "home": True,
            "dismissed": True,
            "completed": True,
        }
        return body

    @app.api_route("/api/users/me/profile/", methods=["PATCH", "PUT", "POST"])
    @app.api_route("/api/users/me/profile", methods=["PATCH", "PUT", "POST"])
    async def users_me_profile_write(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        # Force tour completion flags into CE as well
        payload = {
            **payload,
            "is_tour_completed": True,
            "is_navigation_tour_completed": True,
            "is_onboarded": True,
        }
        status, body, _ = await ce_patch("/api/users/me/profile/", request, json_body=payload)
        if status >= 400:
            # still return success shape so SPA dismiss works offline-of-CE
            return await users_me_profile_get(request)
        if isinstance(body, dict):
            body = dict(body)
            body["is_tour_completed"] = True
            body["is_navigation_tour_completed"] = True
            body["is_onboarded"] = True
            return body
        return await users_me_profile_get(request)

    @app.post("/api/users/me/tour-completed/")
    @app.post("/api/users/me/tour-completed")
    async def users_me_tour_completed(request: Request):
        status, body, _ = await ce_post("/api/users/me/tour-completed/", request, json_body={})
        # Also patch profile
        await ce_patch(
            "/api/users/me/profile/",
            request,
            json_body={"is_tour_completed": True, "is_navigation_tour_completed": True},
        )
        return {"ok": True, "is_tour_completed": True}

    @app.get("/api/users/me/")
    @app.get("/api/users/me")
    async def users_me_get(request: Request):
        status, body, _ = await ce_get("/api/users/me/", request)
        if status != 200:
            return JSONResponse(
                body if isinstance(body, dict) else {"detail": "Authentication credentials were not provided."},
                status_code=status if status else 401,
            )
        if isinstance(body, dict):
            body = dict(body)
            # Some clients nest profile under user
            if isinstance(body.get("profile"), dict):
                p = dict(body["profile"])
                p["is_tour_completed"] = True
                p["is_navigation_tour_completed"] = True
                p["is_onboarded"] = True
                body["profile"] = p
            body.setdefault("is_email_verified", True)
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
        if path.endswith("license-refresh/") or path.endswith("license-refresh"):
            # SPA refreshWorkspaceCurrentPlan expects plan-shaped body, not {}
            return dict(SELFHOST_PLAN)
        if path.endswith("flags/") or path.endswith("flags"):
            values = dict((BUSINESS_FLAGS or {}).get("values") or {})
            for k in list(values.keys()):
                values[k] = True
            return {"values": values}
        if request.method == "GET":
            return {}
        return dict(SELFHOST_PLAN) if "plan" in path or "license" in path else {"ok": True, "status": "selfhost_stub"}
