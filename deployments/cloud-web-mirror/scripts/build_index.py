#!/usr/bin/env python3
"""Build SPA index.html from cloud shell. Do NOT inject head scripts (breaks hydrateRoot(document))."""
from __future__ import annotations
import re
from pathlib import Path
PUBLIC = Path(__file__).resolve().parents[1] / "public"
SOURCE = PUBLIC / "index.source.html"
OUT = PUBLIC / "index.html"

def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    html = re.sub(r"\?dpl=[^\"']+", "", html)
    html = html.replace("https://app.plane.so/", "/")
    html = re.sub(r"<title>[^<]*</title>", "<title>Plane</title>", html, count=1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")

if __name__ == "__main__":
    main()
