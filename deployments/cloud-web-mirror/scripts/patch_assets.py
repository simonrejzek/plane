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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "public" / "assets"

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
    targets = list(ROOT.glob("epic-migration-*.js"))
    if not targets:
        print("warn: no epic-migration-*.js found")
        return
    needle = "Epics is now a work item type"
    for path in targets:
        raw = path.read_text(encoding="utf-8")
        if needle in raw and "||F[e].title" in raw:
            print(f"ok epic fallbacks: {path.name}")
            # cache-bust tour media (stale SPA HTML cache from pre-media deploys)
            if "/epic-migration/step-${e}.${n}`" in raw and "?v=" not in raw:
                raw = raw.replace(
                    "src:`/epic-migration/step-${e}.${n}`",
                    "src:`/epic-migration/step-${e}.${n}?v=6`",
                )
                path.write_text(raw, encoding="utf-8")
                print(f"  cache-busted media urls in {path.name}")
            continue
        print(f"ERROR: {path.name} missing English fallbacks for epic tour — refusing build")
        raise SystemExit(2)


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing assets dir: {ROOT}", file=sys.stderr)
        return 1
    files = 0
    changes = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
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
    ensure_epic_migration_fallbacks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
