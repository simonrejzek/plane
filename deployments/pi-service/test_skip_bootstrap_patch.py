"""Structural proof: self-host store-context must not skip issue bootstrap.

Commercial SPA ships skipBootstrap:()=>!0 which leaves Work items blank
(no /issues/ fetch). patch_assets.enable_selfhost_issue_bootstrap flips it.
"""
from __future__ import annotations

from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / "cloud-web-mirror" / "public" / "assets"


def test_store_context_skip_bootstrap_is_disabled() -> None:
    paths = list(PUBLIC.rglob("store-context*.js"))
    assert paths, "store-context*.js missing under cloud-web-mirror public assets"
    saw_false = False
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "skipBootstrap" not in text:
            continue
        assert "skipBootstrap:()=>!0" not in text, f"{path} still skips bootstrap"
        if "skipBootstrap:()=>!1" in text:
            saw_false = True
    assert saw_false, "no store-context with skipBootstrap:()=>!1"


def test_enable_selfhost_patch_function_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "cloud-web-mirror" / "scripts" / "patch_assets.py"
    src = script.read_text(encoding="utf-8")
    assert "def enable_selfhost_issue_bootstrap" in src
    assert "skipBootstrap:()=>!0" in src
    assert "skipBootstrap:()=>!1" in src
