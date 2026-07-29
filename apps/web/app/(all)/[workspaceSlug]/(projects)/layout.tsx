/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Outlet } from "react-router";
import { ProjectsAppPowerKProvider } from "@/components/power-k/projects-app-provider";
// plane web components
import { ProjectAppSidebar } from "./_sidebar";
import { ExtendedProjectSidebar } from "./extended-project-sidebar";

function WorkspaceLayout() {
  return (
    <>
      <ProjectsAppPowerKProvider />
      {/* min-h-0 keeps nested project views (issues/modules) scrollable under App Rail + top nav */}
      <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-subtle">
        {/* Portal host must not intercept clicks when empty; children re-enable pointer events. */}
        <div
          id="full-screen-portal"
          className="pointer-events-none absolute inset-0 z-30 w-full [&>*]:pointer-events-auto"
        />
        <div className="relative flex min-h-0 size-full overflow-hidden">
          <ProjectAppSidebar />
          <ExtendedProjectSidebar />
          <main className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface-1">
            <Outlet />
          </main>
        </div>
      </div>
    </>
  );
}

export default observer(WorkspaceLayout);
