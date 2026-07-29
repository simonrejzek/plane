#!/usr/bin/env python3
"""Build SPA index.html from cloud shell. Safe dpl strip only; no head injection."""
from __future__ import annotations
import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / "public"
SOURCE = PUBLIC / "index.source.html"
OUT = PUBLIC / "index.html"

def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    # ONLY strip the dpl token, never beyond it (old [^\"']+ destroyed CSS/HTML)
    html = re.sub(r"\?dpl=[A-Za-z0-9_]+", "", html)
    # og:url only when exact cloud app origin (attribute value)
    html = html.replace('content="https://app.plane.so/"', 'content="/"')
    html = re.sub(r"<title>[^<]*</title>", "<title>Plane</title>", html, count=1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")
    # sanity: critical style must still contain both gif urls closed
    assert "logo-spinner-light" in html and "logo-spinner-dark" in html
    assert "critical-theme" in html
    assert html.count("<script") == html.count("</script>")
    # must not have the broken pattern we saw
    assert 'gif"dark"' not in html
    print("sanity ok")

if __name__ == "__main__":
    main()
