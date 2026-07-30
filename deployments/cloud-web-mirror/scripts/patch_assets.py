#!/usr/bin/env python3
"""
Patch mirrored app.plane.so SPA assets for self-host:

- Point API / PI / Live / Admin / Space bases at same-origin (empty string)
  so the commercial UI talks to our Caddy routes:
    /api/*      → Plane CE API
    /api/v1/*   → self-host PI (DeepSeek / OpenRouter — NOT pi.plane.so)
    /live/*     → live service when present
    /god-mode/* → admin

Cloud cookies are only used offline to *download* these assets once.
Runtime inference never hits Plane cloud PI.
"""

from __future__ import annotations

import re
import os
import shutil
import sys
from pathlib import Path

PUBLIC = Path(os.environ.get("CLOUD_MIRROR_PUBLIC", Path(__file__).resolve().parents[1] / "public"))
ROOT = PUBLIC / "assets"
RELEASE = os.environ.get("CLOUD_MIRROR_RELEASE", "dev")
RELEASE_ROOT = ROOT / "releases" / RELEASE

# Replace cloud service bases with same-origin.
# Empty string turns https://pi.plane.so/api/v1/... into /api/v1/...
REPLACEMENTS = [
    # Primary product backends
    ("https://pi.plane.so", ""),
    ("https://api.plane.so", ""),
    ("https://live.plane.so", ""),
    ("https://admin.plane.so", ""),
    ("https://sites.plane.so", ""),
    ("https://silo.plane.so", ""),
    ("https://flux.plane.so", ""),
    # Backtick form already covered by full URL replace
]

# Disable phone-home analytics in the commercial build (optional, quieter self-host)
ANALYTICS_BLANK = [
    (r"VITE_POSTHOG_KEY:`[^`]*`", "VITE_POSTHOG_KEY:``"),
    (r"VITE_SENTRY_DSN:`[^`]*`", "VITE_SENTRY_DSN:``"),
    (r"VITE_GOOGLE_ANALYTICS_ID:`[^`]*`", "VITE_GOOGLE_ANALYTICS_ID:``"),
    (r"VITE_ENABLE_SESSION_RECORDER:`[^`]*`", "VITE_ENABLE_SESSION_RECORDER:`0`"),
    (r"VITE_SESSION_RECORDER_KEY:`[^`]*`", "VITE_SESSION_RECORDER_KEY:``"),
]


def patch_text(text: str) -> tuple[str, int]:
    n = 0
    for old, new in REPLACEMENTS:
        c = text.count(old)
        if c:
            text = text.replace(old, new)
            n += c
    for pat, repl in ANALYTICS_BLANK:
        text2, c = re.subn(pat, repl, text)
        if c:
            text = text2
            n += c
    return text, n




def ensure_epic_migration_fallbacks() -> None:
    """Commercial SPA expects product_tour.epic_migration.* — self-host may miss that ns.
    Keep English copy fallbacks so users never see raw i18n key strings."""
    # Only the modal bundle uses product_tour.epic_migration keys; ignore docs-url chunks.
    targets = [
        p
        for p in ROOT.glob("epic-migration-*.js")
        if "product_tour.epic_migration" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    if not targets:
        print("ERROR: no epic-migration modal bundle with product_tour keys found")
        raise SystemExit(2)
    needle = "Epics is now a work item type"
    for path in targets:
        raw = path.read_text(encoding="utf-8")
        if needle not in raw or "||F[e].title" not in raw:
            print(f"ERROR: {path.name} missing English fallbacks for epic tour — refusing build")
            raise SystemExit(2)
        print(f"ok epic fallbacks: {path.name}")
        if "src:`/epic-migration/step-${e}.${n}`" in raw:
            raw = raw.replace(
                "src:`/epic-migration/step-${e}.${n}`",
                "src:`/epic-migration/step-${e}.${n}?v=6`",
            )
            path.write_text(raw, encoding="utf-8")
            print(f"  cache-busted media urls in {path.name}")


def namespace_release_assets() -> None:
    """Publish one immutable, self-contained asset graph per mirror build.

    The cloud bundle reuses hashed filenames across deployments.  Mutating those
    filenames in place lets a browser/CDN combine modules from different builds,
    which leaves the SPA mounted with an empty main element.  Copy the patched
    graph under a build-specific prefix and make the document/bootstrap modules
    reference that prefix instead.
    """
    if RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    for source in ROOT.iterdir():
        if source.name == "releases":
            continue
        target = RELEASE_ROOT / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    prefix = f"/assets/releases/{RELEASE}/"
    changed = 0
    for path in PUBLIC.rglob("*"):
        if not path.is_file():
            continue
        # Keep the source asset graph pristine for repeatable reruns. Rewrite
        # public bootstrap documents and the copied release graph that browsers
        # actually load.
        if ROOT in path.parents and RELEASE_ROOT not in path.parents:
            continue
        if path.suffix not in {".js", ".css", ".html", ".json", ".map", ".svg"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        updated = raw
        # Rewrite each path form once.  The negative lookbehind prevents the
        # final relative-path rule from matching the slash in an absolute URL.
        updated = updated.replace("../assets/", f"../assets/releases/{RELEASE}/")
        updated = updated.replace("./assets/", f"./assets/releases/{RELEASE}/")
        updated = updated.replace("/assets/", prefix)
        updated = re.sub(
            r"(?<![./A-Za-z0-9_-])assets/",
            f"assets/releases/{RELEASE}/",
            updated,
        )
        if updated != raw:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    marker = RELEASE_ROOT / "detail-DFXDSk4X.js"
    if not marker.exists():
        raise SystemExit(f"ERROR: release asset graph missing {marker}")
    stale_refs = []
    for path in RELEASE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".css", ".html", ".json", ".map", ".svg"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if re.search(rf"/assets/(?!releases/{re.escape(RELEASE)}/)", raw):
                stale_refs.append(path.relative_to(RELEASE_ROOT))
        except Exception:
            continue
    if stale_refs:
        sample = ", ".join(map(str, stale_refs[:5]))
        raise SystemExit(f"ERROR: release graph retains unversioned /assets/ refs: {sample}")
    print(f"release namespace: {RELEASE} ({changed} documents rewritten)")




# Surgical commercial AI/Wiki self-host gates.
# Without these, Plane AI paints grey/empty when flags race or auth-check fails:
#   Ga requires isAuthorized && isWorkspaceAuthorized
#   layout shows Upgrade when !is_pi_enabled
#   with-ai-feature-flag shows not-found when AI_CHAT ai flags missing
AI_SELFHOST_SURGICAL = [
    # PiChatDetail: always paint commercial chat shell on AI routes
    (
        "children:s&&c?(0,$.jsx)(`div`",
        "children:(s=!0,c=!0,!0)?(0,$.jsx)(`div`",
    ),
    # AI layout: never block on IS_PI_ENABLED upgrade wall
    (
        "i=!r&&!n(t,oe.IS_PI_ENABLED)",
        "i=!1",
    ),
    # AI feature flag default ON when not yet loaded
    (
        "c=(e,t,n=!1)=>{let i=(0,s.useContext)(o);if(i===void 0)throw Error(`useFlag must be used within StoreProvider`);return e?i.aiFeatureFlags.flags[e]?.[r[t]]??n:n}",
        "c=(e,t,n=!0)=>{let i=(0,s.useContext)(o);if(i===void 0)throw Error(`useFlag must be used within StoreProvider`);return e?i.aiFeatureFlags.flags[e]?.[r[t]]??n:n}",
    ),
    # Payments feature flag getter default ON
    (
        "ue=(e,t,n=!1)=>e?s.featureFlags.flags[e]?.[a[t]]??n:n",
        "ue=(e,t,n=!0)=>e?s.featureFlags.flags[e]?.[a[t]]??n:n",
    ),
    # Workspace features: PI + Wiki always enabled
    (
        "isWorkspaceFeatureEnabled=H((e,t)=>{if(t===bo.IS_CROSS_PROJECT_SUB_WORK_ITEMS_ENABLED)return!0;let n=this.featuresByWorkspaceSlug(e);return n?n?.[t]??!1:!1})",
        "isWorkspaceFeatureEnabled=H((e,t)=>{if(t===bo.IS_CROSS_PROJECT_SUB_WORK_ITEMS_ENABLED||t===bo.IS_PI_ENABLED||t===bo.IS_WIKI_ENABLED)return!0;let n=this.featuresByWorkspaceSlug(e);return n?n?.[t]??!1:!1})",
    ),
    # Wiki layout: never show upgrade wall when is_wiki missing
    (
        "c=!a&&!s,d=Se(t,`PAGE_TEMPLATES`)",
        "c=!1,d=Se(t,`PAGE_TEMPLATES`)",
    ),
    # getInstance: never leave isWorkspaceAuthorized false (grey UnauthorizedView)
    (
        "getInstance=async e=>{try{let t=await this.piChatService.getInstance(e);return this.isWorkspaceAuthorized=t.is_authorized,C(()=>{this.hasAnyChats[e]=t.has_chats}),t}catch(e){console.error(`Failed to get instance information:`,e),this.isWorkspaceAuthorized=!1}}",
        "getInstance=async e=>{try{let t=await this.piChatService.getInstance(e);return this.isWorkspaceAuthorized=!0,C(()=>{this.hasAnyChats[e]=!!(t&&t.has_chats)}),t||{is_authorized:!0,has_chats:!1}}catch(e){console.error(`Failed to get instance information:`,e),this.isWorkspaceAuthorized=!0}}",
    ),
]


def apply_ai_selfhost_surgical() -> int:
    """Idempotent targeted fixes for commercial AI/Wiki grey screens."""
    n = 0
    for path in ROOT.rglob("*.js"):
        if "releases" in path.relative_to(ROOT).parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        orig = raw
        for old, new in AI_SELFHOST_SURGICAL:
            if old in raw:
                raw = raw.replace(old, new)
                n += 1
        if raw != orig:
            path.write_text(raw, encoding="utf-8")
            print(f"ai-selfhost: {path.name}")
    # entry.client bootstrap: fix identity bug (p===data always true when patch mutates)
    for path in ROOT.glob("entry.client-*.js"):
        raw = path.read_text(encoding="utf-8")
        orig = raw
        raw = raw.replace(
            "if(p===data) return res;\n          return new Response(JSON.stringify(p)",
            "return new Response(JSON.stringify(p)",
        )
        if raw != orig:
            path.write_text(raw, encoding="utf-8")
            n += 1
            print(f"ai-selfhost bootstrap: {path.name}")
    return n


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing assets dir: {ROOT}", file=sys.stderr)
        return 1
    files = 0
    changes = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if "releases" in path.relative_to(ROOT).parts:
            continue
        if path.suffix not in {".js", ".css", ".html", ".json", ".map"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        patched, n = patch_text(raw)
        if n:
            path.write_text(patched, encoding="utf-8")
            files += 1
            changes += n
            print(f"patched {path.name}: {n}")
    print(f"done: {files} files, {changes} replacements")
    ai_n = apply_ai_selfhost_surgical()
    print(f"ai-selfhost surgical: {ai_n}")
    ensure_epic_migration_fallbacks()
    namespace_release_assets()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
