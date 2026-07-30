#!/usr/bin/env python3
"""Build SPA index.html from cloud shell. Safe dpl strip + dual-sidebar prefs."""
from __future__ import annotations

import os
import re
from pathlib import Path

PUBLIC = Path(
    os.environ.get(
        "CLOUD_MIRROR_PUBLIC", Path(__file__).resolve().parents[1] / "public"
    )
)
SOURCE = PUBLIC / "index.source.html"
OUT = PUBLIC / "index.html"

EARLY_SIDEBAR = """<script id="cosmic-dual-sidebar-prefs">
(function(){
  try {
    Object.keys(localStorage).forEach(function(k){
      if (k.indexOf("APP_RAIL_") === 0) localStorage.removeItem(k);
    });
    localStorage.setItem("app_sidebar_collapsed", "false");
    localStorage.setItem("sidebarWidth", JSON.stringify(250));
  } catch (e) {}
})();
</script>
"""

INJECT = (
    '<script id="cosmic-shell-inject" '
    'src="/cosmic-pilot/inject.js?v=41" defer></script>'
)


def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    # ONLY strip the dpl token, never beyond it
    html = re.sub(r"\?dpl=[A-Za-z0-9_]+", "", html)
    html = html.replace('content="https://app.plane.so/"', 'content="/"')
    html = re.sub(r"<title>[^<]*</title>", "<title>Plane</title>", html, count=1)

    if "cosmic-dual-sidebar-prefs" not in html:
        if "<head>" in html:
            html = html.replace("<head>", "<head>" + EARLY_SIDEBAR, 1)
        else:
            html = re.sub(r"(<head[^>]*>)", r"\1" + EARLY_SIDEBAR, html, count=1)

    html = re.sub(
        r'<script id="cosmic-shell-inject"[^>]*></script>\s*',
        "",
        html,
    )
    if "cosmic-shell-inject" not in html:
        if "</body>" in html:
            html = html.replace("</body>", INJECT + "</body>", 1)
        else:
            html += INJECT

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")
    assert "logo-spinner-light" in html and "logo-spinner-dark" in html
    assert "critical-theme" in html
    assert "cosmic-dual-sidebar-prefs" in html
    assert "inject.js?v=41" in html
    assert html.count("<script") == html.count("</script>")
    assert 'gif"dark"' not in html
    print("sanity ok")


if __name__ == "__main__":
    main()
