/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { startTransition, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { HydratedRouter } from "react-router/dom";

import polyfills from "@/lib/polyfills";

void polyfills;

// Cosmic shell: Wiki / Pilot full-page takeovers + dock polish (Dashboard → Wiki + AI)
(function loadCosmicShellInject() {
  if (typeof document === "undefined") return;
  if ((window as unknown as { __cosmicShellLoader?: boolean }).__cosmicShellLoader) return;
  (window as unknown as { __cosmicShellLoader?: boolean }).__cosmicShellLoader = true;
  const s = document.createElement("script");
  s.src = "/cosmic-pilot/static/inject.js";
  s.async = true;
  document.head.appendChild(s);
})();

startTransition(() => {
  hydrateRoot(
    document,
    <StrictMode>
      <HydratedRouter />
    </StrictMode>
  );
});
