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
    # one-shot blank-board recovery may call reload once; no importmap remaps
    assert "importmap" not in text
    assert "__cosmicInjectVersion = 39" in text
    assert "cosmicStateIdsByProject" in text or "__cosmicStateIdsByProject" in text
    assert "blankBoardRecovery" in text or "blank_board" in text
    assert "cosmic-force-projects-sidebar" in text
    assert "main-sidebar" in text
    # Board blank fix: commercial type/parent_type group_by must be coerced
    assert "parent_type" in text
    assert "issue_local_filters" in text
    assert "user-properties" in text or "userprops" in text
    assert 'df.group_by = "state"' in text


def test_index_early_prefs_and_inject_version() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "cosmic-dual-sidebar-prefs" in html
    assert 'app_sidebar_collapsed", "false"' in html
    assert "sidebarWidth" in html
    assert re.search(r"inject\.js\?v=39", html)
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
          readyState: "complete",
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
        const timeouts = [];
        global.window = {
          localStorage: ls,
          sessionStorage: ls,
          document,
          documentElement,
          location: { pathname: "/agenttestws/projects/abc/issues/", reload() {} },
          addEventListener() {},
          dispatchEvent() { return true; },
          __cosmicShellInjected: false,
        };
        global.location = global.window.location;
        global.document = document;
        global.fetch = () => Promise.resolve({ ok: false, json: async () => null });
        global.history = {
          pushState() {},
          replaceState() {},
        };
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
        // inject defers CSS force via setTimeout after hydrate
        global.setTimeout = (fn) => { timeouts.push(fn); return timeouts.length; };
        global.console = { warn() {}, log() {}, error() {} };
        // Pre-poison: commercial type grouping blanks CosmicBoosts board
        store.issue_local_filters = JSON.stringify([{
          key: 'project',
          workspaceSlug: 'cosmicboosts',
          viewId: 'proj1',
          userId: 'u1',
          filters: { display_filters: { group_by: 'type', layout: 'list' } },
        }]);
        const code = fs.readFileSync(process.argv[1], 'utf8');
        eval(code);
        // flush deferred afterHydrateShell timeouts
        while (timeouts.length) {
          const fn = timeouts.shift();
          try { if (typeof fn === 'function') fn(); } catch (e) {}
        }
        // setItem(true) must be forced back to false
        ls.setItem('app_sidebar_collapsed', 'true');
        // SPA write of parent_type must be coerced
        ls.setItem('issue_local_filters', JSON.stringify([{
          filters: { display_filters: { group_by: 'parent_type', sub_group_by: 'type' } },
        }]));
        let parsedFilters = null;
        try { parsedFilters = JSON.parse(ls.getItem('issue_local_filters')); } catch (e) {}
        const out = {
          collapsed: ls.getItem('app_sidebar_collapsed'),
          width: ls.getItem('sidebarWidth'),
          hasRailKey: Object.keys(store).some((k) => k.startsWith('APP_RAIL_')),
          version: global.window.__cosmicInjectVersion,
          forceCss: !!global.document.getElementById('cosmic-force-projects-sidebar'),
          groupBy: parsedFilters && parsedFilters[0] && parsedFilters[0].filters
            && parsedFilters[0].filters.display_filters
            && parsedFilters[0].filters.display_filters.group_by,
          subGroupBy: parsedFilters && parsedFilters[0] && parsedFilters[0].filters
            && parsedFilters[0].filters.display_filters
            && parsedFilters[0].filters.display_filters.sub_group_by,
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
    assert out["version"] == 39, out
    assert out["forceCss"] is True, out
    assert out["groupBy"] == "state", out
    assert out["subGroupBy"] is None, out

if __name__ == "__main__":
    test_inject_source_forces_dual_sidebars()
    test_index_early_prefs_and_inject_version()
    test_execute_inject_sets_localstorage_keys()
    print("OK all inject sidebar tests passed")
