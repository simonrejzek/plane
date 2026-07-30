#!/usr/bin/env python3
"""Build the self-host SPA index from the captured cloud shell."""
from __future__ import annotations

import os
import re
from pathlib import Path

PUBLIC = Path(os.environ.get("CLOUD_MIRROR_PUBLIC", Path(__file__).resolve().parents[1] / "public"))
SOURCE = PUBLIC / "index.source.html"
OUT = PUBLIC / "index.html"

SIDEBAR_MIGRATION = """<script id="full-projects-sidebar-migration">
(function(){
  try {
    var key = "cosmic_full_projects_sidebar_v1";
    if (!localStorage.getItem(key)) {
      localStorage.setItem("app_sidebar_collapsed", "false");
      localStorage.setItem(key, "1");
    }
  } catch (error) {}
})();
</script>"""


def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    # ONLY strip the dpl token, never beyond it (old [^\"']+ destroyed CSS/HTML)
    html = re.sub(r"\?dpl=[A-Za-z0-9_]+", "", html)
    # og:url only when exact cloud app origin (attribute value)
    html = html.replace('content="https://app.plane.so/"', 'content="/"')
    html = re.sub(r"<title>[^<]*</title>", "<title>Plane</title>", html, count=1)
    if "full-projects-sidebar-migration" not in html:
        html = html.replace("</head>", f"{SIDEBAR_MIGRATION}</head>", 1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")
    # sanity: critical style must still contain both gif urls closed
    assert "logo-spinner-light" in html and "logo-spinner-dark" in html
    assert "critical-theme" in html
    assert "full-projects-sidebar-migration" in html
    assert html.count("<script") == html.count("</script>")
    # must not have the broken pattern we saw
    assert 'gif"dark"' not in html
    print("sanity ok")

if __name__ == "__main__":
    main()
