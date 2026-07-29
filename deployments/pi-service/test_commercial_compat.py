"""
Local loop tests for commercial SPA ↔ CE compatibility.

No DB, no Docker required. Mocks CE membership HTTP and exercises the
permission / plan / features / workspace enrichment paths the Business
mirror needs to leave "Workspace not found".
"""

from __future__ import annotations

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
