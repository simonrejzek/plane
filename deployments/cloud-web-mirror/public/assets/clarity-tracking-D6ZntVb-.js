/**
 * SPDX-FileCopyrightText: 2023-present Plane Software, Inc.
 * SPDX-License-Identifier: LicenseRef-Plane-Commercial
 *
 * Licensed under the Plane Commercial License (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * https://plane.so/legals/eula
 *
 * DO NOT remove or modify this notice.
 * NOTICE: Proprietary and confidential. Unauthorized use or distribution is prohibited.
 */

(function initClarity() {
  try {
    const doc = globalThis.document;

    if (!doc) return;

    const script = doc.currentScript;
    const clarityKey = script?.getAttribute("data-clarity-key");

    if (!clarityKey) return;

    (function injectClarity(c, l, a, r, i) {
      c[a] =
        c[a] ||
        function clarity() {
          (c[a].q = c[a].q || []).push(arguments);
        };
      // Inject after load+idle: a script inserted into <head> during React's
      // hydration walk is a hydration mismatch that discards the whole document.
      const inject = () => {
        const t = l.createElement(r);
        t.async = 1;
        t.src = `https://www.clarity.ms/tag/${i}`;
        l.body.appendChild(t);
      };
      const scheduleInject = () =>
        typeof c.requestIdleCallback === "function" ? c.requestIdleCallback(inject, { timeout: 5000 }) : inject();
      if (l.readyState === "complete") scheduleInject();
      else c.addEventListener("load", scheduleInject, { once: true });
    })(globalThis, doc, "clarity", "script", clarityKey);
  } catch (_error) {
    // no-op
  }
})();
