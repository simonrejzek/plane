/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
import { ProjectsAppPowerKProvider } from "@/components/power-k/projects-app-provider";

/**
 * AI (Plane Intelligence) workspace shell — same chrome as app.plane.so:
 * App Rail + top nav stay from WorkspaceContentWrapper; this panel is the
 * full content area (no Projects sidebar).
 */
export default function AiChatLayout() {
  return (
    <>
      <ProjectsAppPowerKProvider />
      <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-subtle bg-surface-1">
        <main className="relative flex h-full min-h-0 w-full flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </>
  );
}
