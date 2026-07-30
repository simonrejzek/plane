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
        coerce_display_filters_group_by,
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
    assert json.loads(kept) == {"priority__in": ["high", "none"]}

    # Commercial assignees/labels/state → CE assignee_id / label_id / state_id
    mapped = sanitize_issue_filters(
        '{"assignees":["u1","u2"],"labels":["l1"],"state":["s1"]}'
    )
    assert mapped is not None
    assert json.loads(mapped) == {
        "assignee_id__in": ["u1", "u2"],
        "label_id__in": ["l1"],
        "state_id__in": ["s1"],
    }
    # Unknown commercial-only keys dropped (do not 400 CE)
    assert sanitize_issue_filters('{"type":["t1"],"milestone":["m1"]}') is None

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
    assert json.loads(q3["filters"]) == {"priority__in": ["urgent"]}
    assert q3["group_by"] == "priority"

    # Commercial type/parent_type must map to state_id (not drop group_by)
    for bad in ("type", "type_id", "parent_type", "parent_id"):
        qb = clean_ce_issue_params({"group_by": bad, "layout": "kanban"})
        assert qb["group_by"] == "state_id", bad

    prefs = {
        "display_filters": {"group_by": "type", "sub_group_by": "parent_type", "layout": "list"},
        "filters": {},
    }
    coerce_display_filters_group_by(prefs)
    assert prefs["display_filters"]["group_by"] == "state"
    assert prefs["display_filters"]["sub_group_by"] is None

    # Any sub_group_by (e.g. created_by on project /issues/) must be cleared —
    # single-level boards match modules and flat always-regroup.
    prefs2 = {
        "display_filters": {
            "group_by": "state",
            "sub_group_by": "created_by",
            "layout": "kanban",
        }
    }
    coerce_display_filters_group_by(prefs2)
    assert prefs2["display_filters"]["sub_group_by"] is None
    assert prefs2["display_filters"]["group_by"] == "state"

    q_sg = clean_ce_issue_params(
        {
            "group_by": "state_id",
            "sub_group_by": "created_by",
            "layout": "kanban",
        }
    )
    assert "sub_group_by" not in q_sg
    assert q_sg["group_by"] == "state_id"

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

    # Flat list can be wrapped as All Issues for SPA group-aware processIssueResponse
    flat = normalize_issues_list_response(
        [{"id": "a", "name": "A"}], force_flat_as_all_issues=True
    )
    assert "All Issues" in flat["results"]
    assert flat["results"]["All Issues"]["results"][0]["id"] == "a"
    assert flat["total_count"] == 1



def test_regroup_issues_fills_empty_group_cards():
    """CE sparse groups (total_results>0, results=[]) must be rebuildable."""
    from commercial_compat import (
        grouped_response_has_empty_cards,
        regroup_issues_by_ce_field,
    )

    sparse = {
        "results": {
            "user-1": {"results": [], "total_results": 21},
            "None": {"results": [], "total_results": 0},
        },
        "total_count": 21,
    }
    assert grouped_response_has_empty_cards(sparse) is True
    # total_count>0 with empty results dict
    assert grouped_response_has_empty_cards({"results": {}, "total_count": 21}) is True

    flat = [
        {"id": "i1", "name": "A", "assignee_ids": ["user-1"], "state_id": "s1"},
        {"id": "i2", "name": "B", "assignee_ids": ["user-1"], "state_id": "s1"},
        {"id": "i3", "name": "C", "assignee_ids": [], "state_id": "s2"},
    ]
    regrouped = regroup_issues_by_ce_field(flat, "assignees__id")
    assert "user-1" in regrouped["results"]
    assert len(regrouped["results"]["user-1"]["results"]) == 2
    assert regrouped["results"]["user-1"]["total_results"] == 2
    assert grouped_response_has_empty_cards(regrouped) is False

    # Nested assignee objects must become UUID keys (not str(dict))
    nested = regroup_issues_by_ce_field(
        [{"id": "x", "assignees": [{"id": "user-9", "display_name": "Simon"}], "state_id": "s1"}],
        "assignees__id",
    )
    assert "user-9" in nested["results"]
    assert len(nested["results"]["user-9"]["results"]) == 1

    # sub_group_by=created_by (project Work items kanban) → nested buckets
    nested_sg = regroup_issues_by_ce_field(
        [
            {"id": "i1", "name": "A", "state_id": "s1", "created_by": "u1"},
            {"id": "i2", "name": "B", "state_id": "s1", "created_by": "u1"},
            {"id": "i3", "name": "C", "state_id": "s2", "created_by": "u2"},
        ],
        "state_id",
        "created_by",
    )
    assert nested_sg["sub_grouped_by"] == "created_by"
    assert isinstance(nested_sg["results"]["s1"]["results"], dict)
    assert "u1" in nested_sg["results"]["s1"]["results"]
    assert len(nested_sg["results"]["s1"]["results"]["u1"]["results"]) == 2
    assert nested_sg["results"]["s1"]["total_results"] == 2
    assert len(nested_sg["results"]["s2"]["results"]["u2"]["results"]) == 1
    assert nested_sg["total_count"] == 3


def test_normalize_projects_list_wraps_ce_array():
    from commercial_compat import normalize_projects_list_response

    page = normalize_projects_list_response(
        [{"id": "p1", "name": "Demo"}, {"id": "p2", "name": "B"}]
    )
    assert page["results"][0]["id"] == "p1"
    assert page["total_count"] == 2
    assert page["next_page_results"] is False
    # already paged shape is preserved
    paged = normalize_projects_list_response(
        {"results": [{"id": "x"}], "total_count": 9, "next_cursor": "c1", "next_page_results": True}
    )
    assert paged["total_count"] == 9
    assert paged["next_cursor"] == "c1"


def test_workspace_preferences_dismiss_epic_migration():
    """EpicMigrationModal opens unless explored_features.epic_migration is true."""
    app = make_app()

    async def mock_ce(path, request, params=None):
        if "workspace-members/me" in path:
            return 200, {"id": "m1", "role": 20, "is_active": True}, {}
        if path == "/api/users/me/":
            return 200, {"id": "u1"}, {}
        if path == "/api/users/me/workspaces/":
            return 200, [{"id": "w1", "slug": "cosmicboosts", "role": 20}], {}
        return 404, {"error": "not mocked"}, {}

    with patch("commercial_compat.ce_get", new=AsyncMock(side_effect=mock_ce)):
        c = TestClient(app)
        r = c.get("/api/workspaces/cosmicboosts/preferences/")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("explored_features", {}).get("epic_migration") is True


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
    calls: list = []

    async def mock_ce(path, request, params=None):
        if path.endswith("/issues/") and "total-count" not in path:
            calls.append(dict(params or {}))
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
    data = r.json()
    assert data["total_count"] == 1
    # First CE call is the grouped request — empty filter arrays stripped
    assert calls, "expected at least one CE issues call"
    assert "filters" not in calls[0]
    assert calls[0].get("group_by") == "state_id"
    # Cards present under state group after regroup
    assert "s1" in data["results"]
    assert data["results"]["s1"]["results"][0]["id"] == "issue-1"
    assert (data.get("extra_stats") or {}).get("cosmic_board_fix") == "v42-always-regroup"


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
