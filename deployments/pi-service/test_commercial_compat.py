"""
Local loop tests for commercial SPA ↔ CE compatibility.

No DB, no Docker required. Mocks CE membership HTTP and exercises the
permission / plan / features / workspace enrichment paths the Business
mirror needs to leave "Workspace not found".
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commercial_compat import (
    GRANTS_BY_RELATION,
    enrich_workspace,
    features_payload,
    permissions_payload,
    register_commercial_compat,
    relation_for_ce_role,
)


def make_app() -> FastAPI:
    app = FastAPI()
    register_commercial_compat(app)
    return app


@pytest.mark.parametrize(
    "role,expected",
    [(20, "owner"), (15, "member"), (5, "guest"), (None, "guest"), (25, "owner")],
)
def test_relation_for_ce_role(role, expected):
    assert relation_for_ce_role(role) == expected


def test_owner_permissions_have_core_edit_grants():
    p = permissions_payload("owner")
    grants = set(p["permission_grants"])
    for need in (
        "workitem:create",
        "workitem:edit",
        "workitem:view",
        "module:create",
        "module:edit",
        "label:create",
        "label:edit",
        "workitem_worklog:create",
        "workitem_worklog:edit",
        "project:view",
        "workspace:view",
    ):
        assert need in grants, f"missing {need}"
    assert p["relation"] == "owner"
    assert len(grants) >= 100


def test_member_permissions_can_edit_work_items():
    p = permissions_payload("member")
    grants = set(p["permission_grants"])
    assert len(grants) >= 20
    assert p["relation"] == "member"


def test_features_enable_pi_and_wiki():
    f = features_payload("ws-1")
    assert f["is_pi_enabled"] is True
    assert f["is_wiki_enabled"] is True
    assert f["workspace"] == "ws-1"


def test_enrich_workspace_adds_plan_and_slug():
    out = enrich_workspace({"id": "1", "slug": "cosmicboosts", "name": "Cosmic", "role": 20})
    assert out["current_plan"] == "BUSINESS"
    assert out["role_slug"] == "owner"
    assert out["is_on_trial"] is False


async def _mock_ce(path: str, request) -> Tuple[int, Any, Dict[str, str]]:
    if path.endswith("/workspace-members/me/"):
        if "/nope/" in path:
            return 404, {"error": "Workspace not found"}, {}
        return 200, {"id": "m1", "role": 20, "is_active": True}, {}
    if path == "/api/users/me/":
        return 200, {"id": "u1", "email": "test@example.com"}, {}
    if path == "/api/users/me/workspaces/":
        return (
            200,
            [{"id": "w1", "slug": "cosmicboosts", "name": "CosmicBoosts", "role": 20}],
            {},
        )
    return 404, {"error": "not mocked"}, {}


def test_permissions_success():
    app = make_app()
    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=_mock_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/cosmicboosts/permissions/", cookies={"session-id": "x"})
    assert r.status_code == 200
    data = r.json()
    assert data["relation"] == "owner"
    for need in ("workitem:edit", "module:edit", "label:edit", "workitem_worklog:create"):
        assert need in data["permission_grants"]


def test_permissions_unauth():
    app = make_app()

    async def unauth_ce(path, request):
        return 401, {"detail": "Authentication credentials were not provided."}, {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=unauth_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/cosmicboosts/permissions/")
    assert r.status_code == 401


def test_permissions_not_member_is_404():
    app = make_app()

    async def missing_ce(path, request):
        if "workspace-members/me" in path:
            return 404, {"error": "Workspace not found"}, {}
        return 200, [], {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=missing_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/nope/permissions/")
    assert r.status_code == 404


def test_current_plan_business_selfhost():
    app = make_app()
    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=_mock_ce)):
        c = TestClient(app)
        r = c.get("/api/payments/workspaces/cosmicboosts/current-plan/")
    assert r.status_code == 200
    data = r.json()
    assert data["product"] == "BUSINESS"
    # Cloud-shaped plan: not self-managed so official mobile shows Plane AI
    assert data["is_self_managed"] is False
    assert data["is_free_member_count_exceeded"] is False
    assert data["show_payment_button"] is False


def test_flags_all_enabled():
    app = make_app()
    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=_mock_ce)):
        c = TestClient(app)
        r = c.get("/api/payments/workspaces/cosmicboosts/flags/")
    assert r.status_code == 200
    values = r.json()["values"]
    assert values.get("AI_CHAT") is True
    assert values.get("APP_RAIL") is True
    assert all(v is True for v in values.values())


def test_features_and_workspaces_enrichment():
    app = make_app()
    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=_mock_ce)):
        c = TestClient(app)
        f = c.get("/api/workspaces/cosmicboosts/features/")
        w = c.get("/api/users/me/workspaces/")
    assert f.status_code == 200
    assert f.json()["is_pi_enabled"] is True
    assert f.json()["is_wiki_enabled"] is True
    assert w.status_code == 200
    ws = w.json()[0]
    assert ws["current_plan"] == "BUSINESS"
    assert ws["role_slug"] == "owner"


def test_project_features_time_tracking_modules():
    app = make_app()
    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=_mock_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/cosmicboosts/projects/proj1/features/")
    assert r.status_code == 200
    data = r.json()
    assert data["is_module_enabled"] is True
    assert data["is_time_tracking_enabled"] is True
    assert data["is_cycle_enabled"] is True


def test_grants_data_loaded():
    assert "owner" in GRANTS_BY_RELATION
    assert len(GRANTS_BY_RELATION["owner"]["permission_grants"]) >= 300


def test_clean_and_normalize_issue_helpers():
    from commercial_compat import (
        clean_ce_issue_params,
        normalize_issues_list_response,
        sanitize_issue_filters,
        total_count_from_issues_body,
    )

    q = clean_ce_issue_params(
        {
            "group_by": "state",
            "layout": "kanban",
            "sidecar": "1",
            "skip_total_count": "1",
            "filters": "{}",
            "per_page": "30",
        }
    )
    assert q["group_by"] == "state_id"
    assert "layout" not in q and "sidecar" not in q and "filters" not in q

    # Empty filter arrays (SPA clear-filter race) must not reach CE
    assert sanitize_issue_filters('{"state":[]}') is None
    assert sanitize_issue_filters({"priority": [], "labels": []}) is None
    kept = sanitize_issue_filters('{"state":[],"priority":["high","none"]}')
    assert kept is not None
    assert json.loads(kept) == {"priority": ["high", "none"]}

    q2 = clean_ce_issue_params(
        {
            "group_by": "state",
            "filters": '{"state":[],"assignees":[]}',
            "layout": "list",
        }
    )
    assert "filters" not in q2
    assert q2["group_by"] == "state_id"

    q3 = clean_ce_issue_params(
        {"filters": '{"state":[],"priority":["urgent"]}', "group_by": "priority"}
    )
    assert json.loads(q3["filters"]) == {"priority": ["urgent"]}
    assert q3["group_by"] == "priority"

    body = {
        "results": {
            "s1": {"results": [{"id": "i1", "state_id": "s1"}], "total_results": 2},
        },
        "total_count": 2,
    }
    n = normalize_issues_list_response(body)
    assert n["referenced_resources"] == {}
    assert n["results"]["s1"]["results"][0]["id"] == "i1"
    tc = total_count_from_issues_body(n)
    assert tc["total_count"] == 2
    assert tc["counts"]["s1"] == 2


def test_project_issues_list_normalizes_grouped_response():
    app = make_app()

    async def mock_ce(path, request, params=None):
        if "workspace-members/me" in path:
            return 200, {"id": "m1", "role": 20, "is_active": True}, {}
        if path == "/api/users/me/":
            return 200, {"id": "u1"}, {}
        if path == "/api/users/me/workspaces/":
            return 200, [{"id": "w1", "slug": "cosmicboosts", "role": 20}], {}
        if path.endswith("/issues/") and "total-count" not in path:
            # ensure commercial params were stripped before CE
            assert params is None or "layout" not in (params or {})
            assert params is None or (params or {}).get("group_by") in (None, "state_id")
            return (
                200,
                {
                    "results": {
                        "state-1": {
                            "results": [{"id": "issue-1", "name": "A", "state_id": "state-1"}],
                            "total_results": 1,
                        }
                    },
                    "total_count": 1,
                    "total_results": 1,
                },
                {},
            )
        if path.endswith("/modules/"):
            return 200, [], {}
        return 404, {"error": "not mocked"}, {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=mock_ce)):
        c = TestClient(app)
        r = c.get(
            "/api/workspaces/cosmicboosts/projects/proj1/issues/",
            params={"group_by": "state", "layout": "kanban", "sidecar": "1"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["total_count"] == 1
    assert "referenced_resources" in data
    assert data["results"]["state-1"]["results"][0]["id"] == "issue-1"


def test_project_issues_list_strips_empty_filter_arrays():
    """SPA clear-filter races send filters={"state":[]} which CE 400s — board blanks."""
    app = make_app()
    seen: Dict[str, Any] = {}

    async def mock_ce(path, request, params=None):
        if path.endswith("/issues/") and "total-count" not in path:
            seen["params"] = dict(params or {})
            return (
                200,
                {
                    "results": [{"id": "issue-1", "name": "A", "state_id": "s1"}],
                    "total_count": 1,
                    "total_results": 1,
                },
                {},
            )
        if path.endswith("/modules/"):
            return 200, [], {}
        return 404, {"error": "not mocked"}, {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=mock_ce)):
        c = TestClient(app)
        r = c.get(
            "/api/workspaces/cosmicboosts/projects/proj1/issues/",
            params={
                "group_by": "state",
                "layout": "list",
                "filters": json.dumps({"state": [], "priority": [], "labels": []}),
            },
        )
    assert r.status_code == 200
    assert r.json()["total_count"] == 1
    assert "filters" not in seen["params"]
    assert seen["params"].get("group_by") == "state_id"


def test_user_work_items_total_count_aliases_user_issues():
    app = make_app()

    async def mock_ce(path, request, params=None):
        if "workspace-members/me" in path:
            return 200, {"id": "m1", "role": 20, "is_active": True}, {}
        if path == "/api/users/me/":
            return 200, {"id": "u1"}, {}
        if path == "/api/users/me/workspaces/":
            return 200, [{"id": "w1", "slug": "cosmicboosts", "role": 20}], {}
        if "/user-issues/" in path:
            return 200, {"results": [{"id": "i1"}], "total_count": 7, "total_results": 7}, {}
        return 404, {"error": "not mocked"}, {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=mock_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/cosmicboosts/user-work-items/user-1/total-count/")
    assert r.status_code == 200
    assert r.json()["total_count"] == 7
