"""Drive shipped inject.js dual-sidebar preference path (real file, not reimplemented)."""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INJECT = ROOT / "static" / "inject.js"
INDEX = ROOT.parent / "cloud-web-mirror" / "public" / "index.html"


def test_inject_source_forces_dual_sidebars() -> None:
    text = INJECT.read_text(encoding="utf-8")
    assert "APP_RAIL = true" in text
    assert "APP_RAIL = false" not in text
    assert 'app_sidebar_collapsed", "false"' in text
    assert "sidebarWidth" in text
    assert "JSON.stringify(250)" in text
    assert "location.reload" not in text
    assert "importmap" not in text
    assert "__cosmicInjectVersion = 34" in text
    assert "cosmic-force-projects-sidebar" in text
    assert "main-sidebar" in text


def test_index_early_prefs_and_inject_version() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "cosmic-dual-sidebar-prefs" in html
    assert 'app_sidebar_collapsed", "false"' in html
    assert "sidebarWidth" in html
    assert re.search(r"inject\.js\?v=34", html)
    assert html.find("cosmic-dual-sidebar-prefs") < html.find("entry.client")


def test_execute_inject_sets_localstorage_keys() -> None:
    """Execute the real inject.js under Node with a localStorage shim."""
    runner = textwrap.dedent(
        r"""
        const fs = require('fs');
        const store = {
          app_sidebar_collapsed: 'true',
          APP_RAIL_cosmicboosts: 'true',
          sidebarWidth: JSON.stringify(0),
        };
        function makeLS() {
          return {
            getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
            setItem(k, v) { store[k] = String(v); },
            removeItem(k) { delete store[k]; },
            key(i) { return Object.keys(store)[i]; },
            get length() { return Object.keys(store).length; },
          };
        }
        // Object.keys(localStorage) used by inject to wipe APP_RAIL_*
        const ls = new Proxy(makeLS(), {
          ownKeys() { return Reflect.ownKeys(store); },
          getOwnPropertyDescriptor(_t, prop) {
            if (prop in store) {
              return { configurable: true, enumerable: true, value: store[prop] };
            }
            return undefined;
          },
          has(_t, prop) { return prop in store || prop in makeLS(); },
          get(t, prop) {
            if (prop in t) return t[prop];
            if (prop in store) return store[prop];
            return undefined;
          },
        });
        global.localStorage = ls;
        global.sessionStorage = ls;
        const nodes = {};
        const documentElement = {
          removeAttribute() {},
        };
        const head = {
          appendChild(el) {
            if (el && el.id) nodes[el.id] = el;
            return el;
          },
        };
        const document = {
          head,
          documentElement,
          getElementById(id) {
            return nodes[id] || null;
          },
          createElement(tag) {
            return {
              tagName: String(tag).toUpperCase(),
              id: "",
              textContent: "",
            };
          },
          addEventListener() {},
          querySelectorAll() { return []; },
        };
        global.window = {
          localStorage: ls,
          sessionStorage: ls,
          document,
          documentElement,
          addEventListener() {},
          dispatchEvent() { return true; },
          __cosmicShellInjected: false,
        };
        global.document = document;
        global.CustomEvent = function CustomEvent() {};
        global.Event = function Event() {};
        global.MutationObserver = function () { this.observe = () => {}; this.disconnect = () => {}; };
        global.XMLHttpRequest = function XMLHttpRequest() {};
        global.XMLHttpRequest.prototype = {
          open() {},
          send() {},
          addEventListener() {},
        };
        global.setInterval = () => 0;
        global.clearInterval = () => {};
        global.setTimeout = () => 0;
        global.console = { warn() {}, log() {}, error() {} };
        const code = fs.readFileSync(process.argv[1], 'utf8');
        eval(code);
        // setItem(true) must be forced back to false
        ls.setItem('app_sidebar_collapsed', 'true');
        const out = {
          collapsed: ls.getItem('app_sidebar_collapsed'),
          width: ls.getItem('sidebarWidth'),
          hasRailKey: Object.keys(store).some((k) => k.startsWith('APP_RAIL_')),
          version: global.window.__cosmicInjectVersion,
          forceCss: !!global.document.getElementById('cosmic-force-projects-sidebar'),
        };
        process.stdout.write(JSON.stringify(out));
        """
    )
    r = subprocess.run(
        ["node", "-e", runner, str(INJECT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, f"stderr={r.stderr!r} stdout={r.stdout!r}"
    out = json.loads(r.stdout.strip())
    assert out["collapsed"] == "false", out
    assert json.loads(out["width"]) == 250, out
    assert out["hasRailKey"] is False, out
    assert out["version"] == 34, out
    assert out["forceCss"] is True, out


if __name__ == "__main__":
    test_inject_source_forces_dual_sidebars()
    test_index_early_prefs_and_inject_version()
    test_execute_inject_sets_localstorage_keys()
    print("OK all inject sidebar tests passed")
