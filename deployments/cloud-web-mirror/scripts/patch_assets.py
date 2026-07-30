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




def fix_css_modulepreloads() -> None:
    """Commercial root/manifest modulepreloads *.css as scripts → browser MIME errors.

    Convert ``rel=\"modulepreload\"`` entries that point at .css into stylesheet
    links in HTML, and strip .css entries from JS modulepreload arrays where safe.

    Critical Vite bug (blocks /issues/ ListLayout, modules often already OK):
    the commercial preload helper does ``t.endsWith(\`.css\`)`` but every mapDeps
    CSS URL ships with ``?dpl=…``, so endsWith is false → CSS is injected as
    ``rel=modulepreload as=script`` → browser: "Failed to load module script…
    MIME type of text/css" → vite:preloadError aborts the dynamic import →
    Suspense never resolves → ListLayout / base-list never mount → no
    ``/issues/?group_by=`` fetch and empty card tray under Display/Add.
    Modules can still look fine when their CSS was already linked as a real
    stylesheet from the route manifest (preload skipped) or a prior nav.
    """
    fixed = 0
    for path in PUBLIC.rglob("*.html"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        updated, n = re.subn(
            r'<link\s+rel="modulepreload"\s+([^>]*href="[^"]+\.css[^"]*"[^>]*)/?>',
            r'<link rel="stylesheet" \1/>',
            raw,
            flags=re.I,
        )
        # also href-first order
        updated, n2 = re.subn(
            r'<link\s+([^>]*href="[^"]+\.css[^"]*"[^>]*)\s+rel="modulepreload"([^>]*)/?>',
            r'<link rel="stylesheet" \1\2/>',
            updated,
            flags=re.I,
        )
        if n or n2:
            path.write_text(updated, encoding="utf-8")
            fixed += n + n2
            print(f"css-modulepreload html: {path.name} ({n + n2})")

    # Vite preload: treat ".css?query" / ".css#hash" as stylesheets, not modules.
    # Live commercial chunk uses double-quotes inside the template for rel=.
    old_css_detect = 'let o=t.endsWith(`.css`),s=o?`[rel="stylesheet"]`:``'
    new_css_detect = 'let o=/\\.css(?:[?#]|$)/.test(t),s=o?`[rel="stylesheet"]`:``'
    already_marker = "/\\.css(?:[?#]|$)/.test(t)"
    for path in ROOT.rglob("chunk-IJF3QNGC-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if already_marker in raw:
            print(f"vite css-detect already: {path.name}")
            continue
        original = raw
        if old_css_detect in raw:
            raw = raw.replace(old_css_detect, new_css_detect, 1)
        elif "endsWith(`.css`)" in raw:
            raw = raw.replace(
                "t.endsWith(`.css`)",
                already_marker,
                1,
            )
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            fixed += 1
            print(f"vite css-detect query-safe: {path.name}")
        else:
            print(f"WARN: vite css-detect needle missing in {path.name}")

    # Strip CSS URLs from __vite__mapDeps file lists (belt + suspenders).
    # Styles already load via route manifest / the fixed stylesheet preload.
    mapdeps_css = re.compile(
        r',?"(?:/assets/[^"]+\.css(?:\?[^"]*)?)"'
    )
    for path in list(ROOT.rglob("page-*.js")) + list(ROOT.rglob("lazy-*.js")) + list(
        ROOT.glob("root-*.js")
    ):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "__vite__mapDeps" not in raw or ".css" not in raw:
            continue
        # Only touch the m.f=[...] list near mapDeps, not arbitrary strings.
        def _strip_css_in_mapdeps(src: str) -> tuple[str, int]:
            m = re.search(r"(m\.f\|\|\(m\.f=\[)(.*?)(\]\))", src)
            if not m:
                m = re.search(r"(m\.f=\[)(.*?)(\])", src)
            if not m:
                return src, 0
            body = m.group(2)
            new_body, n = mapdeps_css.subn("", body)
            # clean double commas / leading comma
            new_body = re.sub(r",{2,}", ",", new_body)
            new_body = re.sub(r"^,", "", new_body)
            new_body = re.sub(r",$", "", new_body)
            if n:
                src = src[: m.start()] + m.group(1) + new_body + m.group(3) + src[m.end() :]
            return src, n

        updated, n = _strip_css_in_mapdeps(raw)
        if n:
            path.write_text(updated, encoding="utf-8")
            fixed += n
            print(f"mapDeps strip css: {path.name} ({n})")

    # root-*.js often lists css paths next to js in modulepreload dependency arrays
    for path in ROOT.glob("root-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if ".css" not in raw or "AppProgressBar" not in raw:
            continue
        # Remove quoted css URLs from arrays: ,"/assets/AppProgressBar-xxx.css?dpl=..."
        updated, n = re.subn(
            r',?"/assets/[^"]+\.css(?:\?[^"]*)?"',
            "",
            raw,
        )
        if n:
            path.write_text(updated, encoding="utf-8")
            fixed += n
            print(f"css-modulepreload js: {path.name} ({n})")
    print(f"css-modulepreload total fixes: {fixed}")


def enable_selfhost_issue_bootstrap() -> None:
    """Commercial SPA ships sidecar-mode flags in store-context.

    - skipBootstrap:()=>!0 → project-wrapper nulls SWR keys (no members/states/…)
    - ingest:()=>!0 → every issues request gets sidecar=1 (cloud-only path)
    - skipTotalCount:()=>!0 → skips total-count (badge can stay 0)

    Self-host has no sidecar: force all three off so boards load and cards
    paint under group headers.
    """
    n = 0
    paths = list(ROOT.rglob("store-context*.js"))
    rel = ROOT / "releases"
    if rel.exists():
        paths += list(rel.rglob("store-context*.js"))
    # de-dupe
    seen = set()
    for path in paths:
        try:
            rp = path.resolve()
        except Exception:
            rp = path
        if rp in seen:
            continue
        seen.add(rp)
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        original = raw
        raw = raw.replace("skipBootstrap:()=>!0", "skipBootstrap:()=>!1")
        raw = raw.replace("ingest:()=>!0", "ingest:()=>!1")
        # Keep skipTotalCount as-is unless we still have the full cloud triad;
        # turning it off ensures Work items N badge + board count stay in sync.
        raw = raw.replace(
            "ug={ingest:()=>!1,skipBootstrap:()=>!1,skipTotalCount:()=>!0}",
            "ug={ingest:()=>!1,skipBootstrap:()=>!1,skipTotalCount:()=>!1}",
        )
        raw = raw.replace(
            "ug={ingest:()=>!0,skipBootstrap:()=>!0,skipTotalCount:()=>!0}",
            "ug={ingest:()=>!1,skipBootstrap:()=>!1,skipTotalCount:()=>!1}",
        )
        if raw == original:
            if "skipBootstrap:()=>!1" in original:
                print(f"selfhost bootstrap already applied: {path.name}")
            continue
        path.write_text(raw, encoding="utf-8")
        n += 1
        print(f"selfhost bootstrap patched: {path.name}")
    print(f"selfhost bootstrap patch files: {n}")


def ensure_board_groups_fallback() -> None:
    """Prevent blank work-items board when getGroupByColumns returns undefined.

    Commercial layout: if (!groups) return null — happens when group_by is type
    (no CE work-item types), parent_type (always void 0), or state ids not loaded
    yet. Fall back to All Issues column and inject cosmic state-id cache for
    state grouping so intermittent blank boards (count badge only) stop.
    """
    needle_old = (
        "nr=ot((e,t,n,r)=>{if(!e)return t?[N]:void 0;"
        "let i=tr[e]({isWorkspaceLevel:n,projectId:r});if(i)return L(e,i)})"
    )
    # Prefer state ids from SPA store; else window.__cosmicStateIdsByProject
    # (filled by inject from states-lite). Never return undefined when groupBy set.
    needle_new = (
        "nr=ot((e,t,n,r)=>{"
        "if(!e)return t?[N]:void 0;"
        "let i=tr[e]({isWorkspaceLevel:n,projectId:r});"
        "if((!i||Array.isArray(i)&&i.length===0)&&(e===`state`||e===`state_detail.group`)){"
        "let p=r||(typeof window<`u`?window.__cosmicRouterProjectId:void 0);"
        "let c=typeof window<`u`&&window.__cosmicStateIdsByProject;"
        "if(p&&c&&c[p]&&c[p].length)i=c[p]"
        "}"
        "if(i&&(!Array.isArray(i)||i.length>0))return L(e,i);"
        "return[N]"
        "})"
    )
    nfiles = 0
    for path in list(ROOT.glob("work-item-layout*.js")) + list(
        (ROOT / "releases").glob("**/work-item-layout*.js") if (ROOT / "releases").exists() else []
    ):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if needle_old not in raw:
            # already patched or different minification
            if "cosmicStateIdsByProject" in raw:
                print(f"board groups already patched: {path.name}")
                continue
            print(f"WARN: board groups needle missing in {path.name}")
            continue
        path.write_text(raw.replace(needle_old, needle_new), encoding="utf-8")
        nfiles += 1
        print(f"board groups fallback: {path.name}")
    # base-list / base-kanban: if groups empty array, still paint (don't require null-only)
    # already handled by returning [N] instead of undefined
    print(f"board groups fallback files: {nfiles}")

    # When columns fall back to single "All Issues" but store is still keyed by
    # state/type ids, flatten issue-id arrays into All Issues so rows paint.
    list_old = (
        "j=O?Object.assign(A,{[k[0]]:t[`All Issues`]??[]}):qe(t)?A:Object.assign(A,{...t}),"
    )
    list_new = (
        "j=O?Object.assign(A,{[k[0]]:t[`All Issues`]??[]}):qe(t)?A:Object.assign(A,{...t});"
        "if(k.length===1&&k[0]===`All Issues`&&t&&typeof t==`object`&&!Array.isArray(t)){"
        "let _all=[],_has=t[`All Issues`];"
        "if(!(_has&&_has.length)){for(let _v of Object.values(t)){"
        "if(Array.isArray(_v))_all=_all.concat(_v);"
        "else if(_v&&typeof _v==`object`){for(let _x of Object.values(_v))if(Array.isArray(_x))_all=_all.concat(_x)}"
        "}if(_all.length)j={[`All Issues`]:_all}}"
        "},"
    )
    for path in list(ROOT.glob("base-list-root*.js")) + list(
        (ROOT / "releases").glob("**/base-list-root*.js") if (ROOT / "releases").exists() else []
    ):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if list_old in raw:
            path.write_text(raw.replace(list_old, list_new), encoding="utf-8")
            print(f"list All Issues flatten: {path.name}")
        elif "_all=_all.concat" in raw:
            print(f"list flatten already: {path.name}")
        else:
            print(f"WARN: list flatten needle missing in {path.name}")


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
    # Prior builds (or accidental source pollution) may already embed
    # /assets/releases/<old-id>/… in mapDeps. A naive replace of "/assets/"
    # then produces /assets/releases/<new>/releases/<old>/… which 404s and
    # prevents ListLayout/base-list from loading → blank Work items board.
    prior_release = re.compile(r"/assets/releases/[^/]+/")
    prior_release_rel = re.compile(r"(?<![./A-Za-z0-9_-])assets/releases/[^/]+/")
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
        # Collapse any existing release prefix back to plain /assets/ first.
        # Multi-pass: double-nested .../releases/old/releases/dev/... needs
        # two collapses before we re-apply the current prefix.
        for _ in range(4):
            nxt = prior_release.sub("/assets/", updated)
            nxt = prior_release_rel.sub("assets/", nxt)
            if nxt == updated:
                break
            updated = nxt
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
    double_nested = []
    for path in RELEASE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".css", ".html", ".json", ".map", ".svg"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if re.search(rf"/assets/(?!releases/{re.escape(RELEASE)}/)", raw):
                stale_refs.append(path.relative_to(RELEASE_ROOT))
            # Require a path segment (no quotes) so adjacent mapDeps entries
            # like "/assets/releases/r/a.js","/assets/releases/r/b.js" do not
            # false-positive on a cross-entry .* match.
            if re.search(r"/assets/releases/[^/\"']+/releases/", raw):
                double_nested.append(path.relative_to(RELEASE_ROOT))
        except Exception:
            continue
    if stale_refs:
        sample = ", ".join(map(str, stale_refs[:5]))
        raise SystemExit(f"ERROR: release graph retains unversioned /assets/ refs: {sample}")
    if double_nested:
        sample = ", ".join(map(str, double_nested[:5]))
        raise SystemExit(f"ERROR: double-nested release paths in asset graph: {sample}")
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


def ensure_lazy_module_fallback() -> None:
    """Keep an optional lazy module from taking down the entire SPA.

    The mirrored commercial bundle has a delayed optional component whose
    loader can resolve without a module on self-host. React's production lazy
    initializer assumes every successful promise resolves to
    ``{ default: Component }`` and otherwise throws while reading ``default``.
    Render nothing for that missing optional component so the surrounding
    dashboard, Wiki, and AI routes remain interactive.
    """
    targets = list(ROOT.glob("chunk-IJF3QNGC-*.js"))
    old = "if(e._status===1)return e._result.default;throw e._result"
    new = "if(e._status===1)return e._result?.default||(()=>null);throw e._result"
    patched = 0
    for path in targets:
        raw = path.read_text(encoding="utf-8")
        if new in raw:
            patched += 1
            continue
        if old not in raw:
            continue
        path.write_text(raw.replace(old, new, 1), encoding="utf-8")
        patched += 1
        print(f"lazy-module fallback: {path.name}")
    if patched != 1:
        raise SystemExit(
            f"ERROR: expected one React lazy initializer, patched {patched}"
        )


def ensure_issues_layout_hoc_path_and_loader() -> None:
    """Unblock issue-layout-HOC on /issues/ (modules already OK).

    HOC does ``return workspaceSlug ? … : null``. Leaf-only useParams often
    omits workspaceSlug on project Work items, so the main pane is null while
    Display/Add chrome from the parent still renders. Also
    ``!groupedIssueIds`` kept the skeleton forever when fetch never armed.
    """
    n = 0
    old_ws = (
        "let{layout:t,pendingInitialFetch:n}=e,{workspaceSlug:i}=r(),a=ue(),{issues:o}=_(a);return i?"
    )
    new_ws = (
        "let{layout:t,pendingInitialFetch:n}=e,{workspaceSlug:i}=r();"
        "if(!i){try{let m=(typeof location<`u`&&location.pathname||``).match(/^\\/([^/]+)\\//);"
        "if(m)i=m[1]}catch(x){}}let a=ue(),{issues:o}=_(a);return i?"
    )
    old_load = "o?.getIssueLoader()===`init-loader`||!o?.groupedIssueIds?(0,Q.jsx)(z,{layout:t})"
    new_load = "o?.getIssueLoader()===`init-loader`?(0,Q.jsx)(z,{layout:t})"
    for path in ROOT.rglob("issue-layout-HOC-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        original = raw
        if old_ws in raw:
            raw = raw.replace(old_ws, new_ws, 1)
        if old_load in raw:
            raw = raw.replace(old_load, new_load, 1)
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            n += 1
            print(f"issue-layout-HOC: {path.name}")
        else:
            print(f"issue-layout-HOC already/missing: {path.name}")
    # Extra useEffect arm on base-list so fetch re-runs when O/k appear
    old_arm = (
        "z=Mt(()=>{l!==o.INITIATIVE_WORK_ITEM&&(E===s.LIST||!E)&&p(`init-loader`,"
        "{canGroup:!0,perPageCount:T?10:30,groupPaginationEnabled:!0,groupPerPageCount:10,groupOffset:0},n)},"
        "[l,p,D,E,n]),B=f?.groupedIssueIds"
    )
    new_arm = (
        "z=Mt(()=>{l!==o.INITIATIVE_WORK_ITEM&&(E===s.LIST||!E)&&p(`init-loader`,"
        "{canGroup:!0,perPageCount:T?10:30,groupPaginationEnabled:!0,groupPerPageCount:10,groupOffset:0},n)},"
        "[l,p,D,E,n]),_cosmicArm=(0,Tn.useEffect)(()=>{if(l===o.INITIATIVE_WORK_ITEM)return;"
        "if(!(E===s.LIST||!E))return;try{p(`init-loader`,{canGroup:!0,perPageCount:T?10:30,"
        "groupPaginationEnabled:!0,groupPerPageCount:10,groupOffset:0},n)}catch(x){}},[l,p,D,E,n,O,k]),"
        "B=f?.groupedIssueIds"
    )
    for path in ROOT.rglob("base-list-root-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "_cosmicArm" in raw:
            print(f"base-list arm already: {path.name}")
            continue
        if old_arm in raw:
            path.write_text(raw.replace(old_arm, new_arm, 1), encoding="utf-8")
            n += 1
            print(f"base-list arm: {path.name}")
        else:
            print(f"WARN: base-list arm needle missing in {path.name}")
    print(f"layout HOC/list arm files: {n}")


def ensure_issues_init_fetch_retries() -> None:
    """Re-arm ListLayout init fetch; modules already fetch reliably.

    ``use-initial-issues-fetch`` runs the init callback once via useLayoutEffect.
    On project Work items (``/issues/``) that race is easy to lose: filters are
    not in the MobX map yet, or PROJECT actions closed over empty router params,
    so ``fetchIssues`` never hits the network — empty tray under Display/Add.
    Module detail works because its leaf params include ``moduleId`` and filters
    hydrate on a different path.

    Retries at 300ms / 1.5s / 4s re-call the latest callback after filters land.
    """
    old = (
        "function r(e,t){let[n,r]=(0,i.useState)(!0),a=(0,i.useRef)(e);"
        "return(0,i.useLayoutEffect)(()=>{a.current=e}),"
        "(0,i.useLayoutEffect)(()=>{a.current(),r(!1)},t),n}"
    )
    new = (
        "function r(e,t){let[n,r]=(0,i.useState)(!0),a=(0,i.useRef)(e);"
        "return(0,i.useLayoutEffect)(()=>{a.current=e}),"
        "(0,i.useLayoutEffect)(()=>{let e=()=>{try{a.current&&a.current()}catch(e){}};"
        "e(),r(!1);let t=setTimeout(e,300),n=setTimeout(e,1500),i=setTimeout(e,4e3);"
        "return()=>{clearTimeout(t),clearTimeout(n),clearTimeout(i)}},t),n}"
    )
    n = 0
    for path in ROOT.rglob("use-initial-issues-fetch-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "setTimeout(e,300)" in raw:
            print(f"init-fetch retries already: {path.name}")
            continue
        if old in raw:
            path.write_text(raw.replace(old, new, 1), encoding="utf-8")
            n += 1
            print(f"init-fetch retries: {path.name}")
        else:
            print(f"WARN: init-fetch needle missing in {path.name}")
    # Always derive PROJECT slug/id from pathname (leaf useParams can still lag)
    for path in ROOT.rglob("use-issues-actions-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        cond = (
            "m=()=>{let{workspaceSlug:e,projectId:t}=s();"
            "if(!e||!t){try{let m=(typeof location<`u`&&location.pathname||``)"
            ".match(/^\\/([^/]+)\\/projects\\/([0-9a-fA-F-]{36})/);"
            "if(m){e=e||m[1],t=t||m[2]}}catch(x){}}let n=e?.toString(),i=t?.toString(),"
        )
        always = (
            "m=()=>{let{workspaceSlug:e,projectId:t}=s();"
            "try{let m=(typeof location<`u`&&location.pathname||``)"
            ".match(/^\\/([^/]+)\\/projects\\/([0-9a-fA-F-]{36})/);"
            "if(m){e=m[1],t=m[2]}}catch(x){}let n=e?.toString(),i=t?.toString(),"
        )
        bare = (
            "m=()=>{let{workspaceSlug:e,projectId:t}=s(),n=e?.toString(),i=t?.toString(),"
            "{issues:a,issuesFilter:o}=l(r.PROJECT),"
        )
        bare_new = (
            "m=()=>{let{workspaceSlug:e,projectId:t}=s();"
            "try{let m=(typeof location<`u`&&location.pathname||``)"
            ".match(/^\\/([^/]+)\\/projects\\/([0-9a-fA-F-]{36})/);"
            "if(m){e=m[1],t=m[2]}}catch(x){}let n=e?.toString(),i=t?.toString(),"
            "{issues:a,issuesFilter:o}=l(r.PROJECT),"
        )
        original = raw
        if "if(m){e=m[1],t=m[2]}" not in raw:
            if cond in raw:
                raw = raw.replace(cond, always, 1)
            elif bare in raw:
                raw = raw.replace(bare, bare_new, 1)
        # Re-parse path on every fetchIssues call (closed-over n/i can be empty)
        old_cb = (
            "l(r.PROJECT),c=(0,d.useCallback)(async(e,t)=>{"
            "if(!(!n||!i))return a.fetchIssues(n.toString(),i.toString(),e,t)},[a.fetchIssues,n,i])"
        )
        new_cb = (
            "l(r.PROJECT),c=(0,d.useCallback)(async(e,t)=>{"
            "let w=n,p=i;try{let m=(typeof location<`u`&&location.pathname||``)"
            ".match(/^\\/([^/]+)\\/projects\\/([0-9a-fA-F-]{36})/);if(m){w=m[1],p=m[2]}}catch(x){}"
            "if(!(!w||!p))return a.fetchIssues(String(w),String(p),e,t)},[a.fetchIssues,n,i])"
        )
        if "String(w),String(p)" not in raw and old_cb in raw:
            raw = raw.replace(old_cb, new_cb, 1)
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            n += 1
            print(f"actions path/fetch: {path.name}")
        else:
            print(f"actions path already: {path.name}")
    # Seed default applied filters when project filter map not ready
    gaf_old = (
        "getAppliedFilters=e=>{if(!e)return;let t=this.getIssueFilters(e);if(!t)return;"
        "let n=qi(t.displayFilters?.layout,`my_issues`);if(n)return this.computedFilteredParams(t,n)}"
    )
    gaf_new = (
        "getAppliedFilters=e=>{if(!e)return;let t=this.getIssueFilters(e);"
        "if(!t)t={displayFilters:{layout:`list`,group_by:`state`,order_by:`-created_at`},"
        "displayProperties:{},richFilters:{},pqlFilters:{},kanbanFilters:{group_by:[],sub_group_by:[]}};"
        "let n=qi(t.displayFilters?.layout||`list`,`my_issues`);"
        "if(n)return this.computedFilteredParams(t,n);"
        "return this.computedFilteredParams(t,`list`)}"
    )
    for path in ROOT.rglob("store-context*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "displayFilters:{layout:`list`,group_by:`state`,order_by:`-created_at`}" in raw and "getAppliedFilters=e=>{if(!e)return;let t=this.getIssueFilters(e);if(!t)t=" in raw:
            print(f"getAppliedFilters seed already: {path.name}")
            continue
        if gaf_old in raw:
            path.write_text(raw.replace(gaf_old, gaf_new), encoding="utf-8")
            n += 1
            print(f"getAppliedFilters seed: {path.name}")
    print(f"issues init/fetch harden files: {n}")


def ensure_use_params_merge_matches() -> None:
    """Merge React Router match params so Work items can fetch issues.

    Commercial chunk useParams is implemented as::

        return matches[matches.length-1]?.params ?? {}

    Leaf routes under ``projects/(detail)/[projectId]/issues/(list)`` often
    contribute empty params, so ``workspaceSlug`` / ``projectId`` from parents
    are dropped. ``use-issues-actions`` then no-ops::

        if (!workspaceSlug || !projectId) return

    and ListLayout never hits ``/issues/?group_by=…`` — empty card tray with
    Display / Add work item chrome still visible.
    """
    old = "function Vt(){let{matches:e}=G.useContext($);return e[e.length-1]?.params??{}}"
    new = (
        "function Vt(){let{matches:e}=G.useContext($);"
        "let t={};"
        "if(e)for(let n of e)if(n&&n.params)for(let r in n.params)"
        "if(n.params[r]!=null)t[r]=n.params[r];"
        "return t}"
    )
    # alternate minifier letters seen in older mirrors
    alts = [
        (
            "function Vt(){let{matches:e}=G.useContext($);return e[e.length-1]?.params??{}}",
            new,
        ),
        (
            "function Vt(){let{matches:e}=G.useContext($);return e.at(-1)?.params??{}}",
            new,
        ),
    ]
    nfiles = 0
    for path in ROOT.rglob("chunk-IJF3QNGC-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        original = raw
        if "for(let n of e)if(n&&n.params)" in raw:
            print(f"useParams merge already: {path.name}")
            continue
        for o, n in alts:
            if o in raw:
                raw = raw.replace(o, n, 1)
                break
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            nfiles += 1
            print(f"useParams merge patched: {path.name}")
    # also hard-fallback PROJECT fetchIssues when params still empty
    actions_old = (
        "m=()=>{let{workspaceSlug:e,projectId:t}=s(),n=e?.toString(),i=t?.toString(),"
        "{issues:a,issuesFilter:o}=l(r.PROJECT),c=(0,d.useCallback)(async(e,t)=>{"
        "if(!(!n||!i))return a.fetchIssues(n.toString(),i.toString(),e,t)},[a.fetchIssues,n,i]),"
    )
    actions_new = (
        "m=()=>{let{workspaceSlug:e,projectId:t}=s();"
        "if(!e||!t){try{let m=(typeof location<`u`&&location.pathname||``)"
        ".match(/^\\/([^/]+)\\/projects\\/([0-9a-fA-F-]{36})/);"
        "if(m){e=e||m[1],t=t||m[2]}}catch(x){}}"
        "let n=e?.toString(),i=t?.toString(),"
        "{issues:a,issuesFilter:o}=l(r.PROJECT),c=(0,d.useCallback)(async(e,t)=>{"
        "if(!(!n||!i))return a.fetchIssues(n.toString(),i.toString(),e,t)},[a.fetchIssues,n,i]),"
    )
    for path in ROOT.rglob("use-issues-actions-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "location.pathname||``).match(/^\\/([^/]+)\\/projects\\/" in raw or (
            "location.pathname||``)" in raw and "projects\\/([0-9a-fA-F-]{36})" in raw
        ):
            print(f"issues-actions path fallback already: {path.name}")
            continue
        if actions_old in raw:
            path.write_text(raw.replace(actions_old, actions_new, 1), encoding="utf-8")
            nfiles += 1
            print(f"issues-actions path fallback: {path.name}")
        else:
            print(f"WARN: issues-actions needle missing in {path.name}")
    print(f"useParams/issues-fetch param fixes: {nfiles}")


def ensure_project_issues_board_mount() -> None:
    """Mount project Work items even while filters hydrate; always fetch list.

    Commercial page-CSL8Ir returns ``<Fragment/>`` when
    ``getIssueFilters(projectId)`` is still null (``!n||!r||!o``). That blanks
    the board body forever if fetchFilters is slow/fails once — headers stay
    (parent layout) but ListLayout never mounts so fetchIssues never runs.

    Also default ``displayFilters.layout`` to ``list`` so ListLayout's
    ``E===LIST`` init fetch is not skipped when layout is momentarily unset.

    Hardens PROJECT ``fetchFilters`` so a user-properties glitch still seeds
    default display filters into the MobX store (layout=list, group_by=state).
    """
    nfiles = 0
    # page-*: project work items route
    page_needles = [
        (
            # gate: require workspace+project only (not hydrated filters)
            "!n||!r||!o?(0,B.jsx)(B.Fragment,{})",
            "!n||!r?(0,B.jsx)(B.Fragment,{})",
        ),
        (
            "o=r?a?.getIssueFilters(r):void 0,s=o?.displayFilters?.layout",
            'o=r?a?.getIssueFilters(r):void 0,s=o?.displayFilters?.layout??"list"',
        ),
        # alternate minifier order / binding letters seen in some chunks
        (
            "!n||!r||!o?(0,",
            "!n||!r?(0,",
        ),
    ]
    list_needles = [
        (
            "T=C?.group_by||null,E=C?.layout",
            'T=C?.group_by||null,E=C?.layout??"list"',
        ),
        (
            # init fetch: treat missing layout as list so first paint loads cards
            "l!==o.INITIATIVE_WORK_ITEM&&E===s.LIST&&p(`init-loader`",
            "l!==o.INITIATIVE_WORK_ITEM&&(E===s.LIST||!E)&&p(`init-loader`",
        ),
    ]
    # PROJECT fetchFilters: wrap await user-properties so store still hydrates
    filter_needles = [
        (
            "fetchFilters=async(e,t)=>{let n=await this.rootIssueStore.rootStore.memberViewState.fetchProjectUserProperties(e,t),r=this.computedDisplayFilters(n?.display_filters),i=this.computedDisplayProperties(n?.display_properties),a={group_by:[],sub_group_by:[]},o=this.rootIssueStore.currentUserId;if(o){let n=this.handleIssuesLocalFilters.get(m.PROJECT,e,t,o);a.group_by=n?.kanban_filters?.group_by||[],a.sub_group_by=n?.kanban_filters?.sub_group_by||[]}C(()=>{j(this.filters,[t],{richFilters:n?.rich_filters||{},pqlFilters:n?.pql_filters||qe,lastUsedFilterType:n?.last_used_filter,displayFilters:r,displayProperties:i,kanbanFilters:a})})};",
            "fetchFilters=async(e,t)=>{let n;try{n=await this.rootIssueStore.rootStore.memberViewState.fetchProjectUserProperties(e,t)}catch(err){n=null}if(!n||typeof n!==`object`)n={display_filters:{layout:`list`,group_by:`state`,order_by:`-created_at`},display_properties:{},rich_filters:{},pql_filters:qe};if(!n.display_filters||typeof n.display_filters!==`object`)n.display_filters={};if(!n.display_filters.layout)n.display_filters.layout=`list`;if(n.display_filters.group_by==null||n.display_filters.group_by===``)n.display_filters.group_by=`state`;let r=this.computedDisplayFilters(n?.display_filters),i=this.computedDisplayProperties(n?.display_properties),a={group_by:[],sub_group_by:[]},o=this.rootIssueStore.currentUserId;if(o){let n=this.handleIssuesLocalFilters.get(m.PROJECT,e,t,o);a.group_by=n?.kanban_filters?.group_by||[],a.sub_group_by=n?.kanban_filters?.sub_group_by||[]}C(()=>{j(this.filters,[t],{richFilters:n?.rich_filters||{},pqlFilters:n?.pql_filters||qe,lastUsedFilterType:n?.last_used_filter,displayFilters:r,displayProperties:i,kanbanFilters:a})})}",
        ),
    ]
    targets = (
        list(ROOT.glob("page-*.js"))
        + list(ROOT.glob("base-list-root-*.js"))
        + list(ROOT.glob("store-context*.js"))
        + list((ROOT / "releases").glob("**/page-*.js") if (ROOT / "releases").exists() else [])
        + list(
            (ROOT / "releases").glob("**/base-list-root-*.js")
            if (ROOT / "releases").exists()
            else []
        )
        + list(
            (ROOT / "releases").glob("**/store-context*.js")
            if (ROOT / "releases").exists()
            else []
        )
    )
    seen = set()
    for path in targets:
        try:
            rp = path.resolve()
        except Exception:
            rp = path
        if rp in seen:
            continue
        seen.add(rp)
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        original = raw
        if path.name.startswith("page-"):
            if "PROJECT_ISSUES_" not in raw:
                continue
            needles = page_needles
        elif path.name.startswith("base-list-root"):
            needles = list_needles
        elif path.name.startswith("store-context"):
            needles = filter_needles
        else:
            continue
        for old, new in needles:
            if old in raw and new not in raw:
                raw = raw.replace(old, new)
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            nfiles += 1
            print(f"board-mount patched: {path.name}")
        elif path.name.startswith("page-") and "PROJECT_ISSUES_" in original:
            if "!n||!r?(0,B.jsx)(B.Fragment,{})" in original or 'layout??"list"' in original:
                print(f"board-mount already: {path.name}")

    # Force layout switcher to always mount a layout (default list)
    r_old = "function R(e){if(!e.activeLayout)return null;let t=K[e.activeLayout];return t?(0,B.jsx)(z.Suspense,{children:(0,B.jsx)(t,{workspaceSlug:e.workspaceSlug,projectId:e.projectId})}):null}"
    r_new = "function R(e){let a=e.activeLayout||`list`;let t=K[a]||K.list||K[`list`];if(!t)return null;return(0,B.jsx)(z.Suspense,{children:(0,B.jsx)(t,{workspaceSlug:e.workspaceSlug,projectId:e.projectId})})}"
    prop_old = "(0,B.jsx)(R,{workspaceSlug:n,projectId:r,activeLayout:s})"
    prop_new = "(0,B.jsx)(R,{workspaceSlug:n,projectId:r,activeLayout:s||`list`})"
    for path in ROOT.rglob("page-*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "PROJECT_ISSUES_" not in raw:
            continue
        original = raw
        if r_old in raw:
            raw = raw.replace(r_old, r_new, 1)
        if prop_old in raw:
            raw = raw.replace(prop_old, prop_new, 1)
        if raw != original:
            path.write_text(raw, encoding="utf-8")
            nfiles += 1
            print(f"layout switcher forced: {path.name}")

    print(f"board-mount patch files: {nfiles}")
    # refuse to ship broken store-context
    for path in ROOT.rglob("store-context*.js"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if raw.count("{") != raw.count("}"):
            raise SystemExit(f"ERROR: brace imbalance in {path}")


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
    ensure_lazy_module_fallback()
    ensure_epic_migration_fallbacks()
    enable_selfhost_issue_bootstrap()
    ensure_board_groups_fallback()
    ensure_project_issues_board_mount()
    ensure_use_params_merge_matches()
    ensure_issues_init_fetch_retries()
    ensure_issues_layout_hoc_path_and_loader()
    fix_css_modulepreloads()
    namespace_release_assets()
    # re-apply after namespace so release copies also get board + css fixes
    enable_selfhost_issue_bootstrap()
    ensure_board_groups_fallback()
    ensure_project_issues_board_mount()
    ensure_use_params_merge_matches()
    ensure_issues_init_fetch_retries()
    ensure_issues_layout_hoc_path_and_loader()
    fix_css_modulepreloads()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
