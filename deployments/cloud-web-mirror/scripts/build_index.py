#!/usr/bin/env python3
"""Build SPA index.html from cloud shell + self-host bootstrap shim."""

from __future__ import annotations

import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / "public"
SOURCE = PUBLIC / "index.source.html"
OUT = PUBLIC / "index.html"

# Injected before the SPA boots: force PI/wiki feature flags + block cloud PI host.
BOOTSTRAP = r"""
<script>
(function () {
  // Self-host bootstrap — commercial UI assets, local API + PI only.
  window.__PLANE_SELFHOST__ = {
    piBase: "",
    apiBase: "",
    note: "UI mirrored from app.plane.so; inference via local /api/v1 (DeepSeek)."
  };

  function patchJson(url, data) {
    try {
      if (!data || typeof data !== "object") return data;
      // Workspace feature flags (Plane Intelligence / Wiki)
      if (/\/api\/workspaces\/[^/]+\/features\/?/.test(url) || /\/features\/?$/.test(url)) {
        data.is_pi_enabled = true;
        data.is_wiki_enabled = true;
        if (data.is_project_grouping_enabled === undefined) data.is_project_grouping_enabled = false;
      }
      // Instance / config soft-enable AI surfaces
      if (data.config && typeof data.config === "object") {
        // leave auth config as returned by CE
      }
      // Subscription / plan detail — treat as Business so AI chrome is not paywalled
      if (data.product === "FREE" || data.product === "free") {
        data.product = "BUSINESS";
      }
      if (data.current_plan === "FREE") data.current_plan = "BUSINESS";
      if (Array.isArray(data) && url.includes("workspaces")) {
        data.forEach(function (w) {
          if (w && (w.current_plan === "FREE" || !w.current_plan)) w.current_plan = "BUSINESS";
        });
      }
      if (data.values && typeof data.values === "object" && url.includes("/api/v1/flags")) {
        Object.keys(data.values).forEach(function (k) {
          if (k.indexOf("AI_") === 0) data.values[k] = true;
        });
      }
    } catch (e) {}
    return data;
  }

  // Block any accidental call to cloud PI / cloud API after asset patch misses
  var blockedHosts = ["pi.plane.so", "api.plane.so", "silo.plane.so", "flux.plane.so"];
  function rewriteUrl(input) {
    try {
      var u = typeof input === "string" ? input : (input && input.url) || "";
      if (!u) return input;
      for (var i = 0; i < blockedHosts.length; i++) {
        var h = blockedHosts[i];
        if (u.indexOf("https://" + h) === 0) {
          return u.split("https://" + h).join("");
        }
        if (u.indexOf("http://" + h) === 0) {
          return u.split("http://" + h).join("");
        }
      }
      return typeof input === "string" ? u : input;
    } catch (e) {
      return input;
    }
  }

  var _fetch = window.fetch;
  window.fetch = function (input, init) {
    var rewritten = rewriteUrl(input);
    var urlStr = typeof rewritten === "string" ? rewritten : (rewritten && rewritten.url) || String(input);
    return _fetch.call(this, rewritten, init).then(function (res) {
      var ct = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
      if (ct.indexOf("application/json") === -1) return res;
      return res
        .clone()
        .json()
        .then(function (data) {
          var patched = patchJson(urlStr, data);
          return new Response(JSON.stringify(patched), {
            status: res.status,
            statusText: res.statusText,
            headers: res.headers,
          });
        })
        .catch(function () {
          return res;
        });
    });
  };

  // EventSource used by Pilot streaming — rewrite cloud PI host if present
  var _ES = window.EventSource;
  if (_ES) {
    window.EventSource = function (url, conf) {
      return new _ES(rewriteUrl(url), conf);
    };
    window.EventSource.prototype = _ES.prototype;
  }
})();
</script>
"""


def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    # Drop deployment query cache-busters for cleaner self-host URLs
    html = re.sub(r"\?dpl=[^\"']+", "", html)
    # Remove splash-only cloud absolute og:url
    html = html.replace("https://app.plane.so/", "/")
    # Insert bootstrap immediately after <head>
    if "<head>" in html:
        html = html.replace("<head>", "<head>" + BOOTSTRAP, 1)
    else:
        html = BOOTSTRAP + html
    # Ensure SPA title
    html = re.sub(r"<title>[^<]*</title>", "<title>Plane</title>", html, count=1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
