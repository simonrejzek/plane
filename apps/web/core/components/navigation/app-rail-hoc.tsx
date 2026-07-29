/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// hoc/withDockItems.tsx
import React from "react";
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { DashboardIcon, PlaneNewIcon } from "@plane/propel/icons";
import type { AppSidebarItemData } from "@/components/sidebar/sidebar-item";
import { useWorkspacePaths } from "@/hooks/use-workspace-paths";

type WithDockItemsProps = {
  dockItems: (AppSidebarItemData & { shouldRender: boolean })[];
};

export function withDockItems<P extends WithDockItemsProps>(WrappedComponent: React.ComponentType<P>) {
  const ComponentWithDockItems = observer(function ComponentWithDockItems(props: Omit<P, keyof WithDockItemsProps>) {
    const { workspaceSlug } = useParams();
    const pathname = usePathname();
    const { isProjectsPath, isNotificationsPath } = useWorkspacePaths();
    const slug = workspaceSlug?.toString() ?? "";
    const isDashboardsPath = pathname?.includes(`/${slug}/dashboards`) ?? false;

    // App rail dock — aligned with app.plane.so shell (no Pilot/AI entry here).
    const dockItems: (AppSidebarItemData & { shouldRender: boolean })[] = [
      {
        label: "Projects",
        icon: <PlaneNewIcon className="size-5" />,
        href: `/${slug}/`,
        isActive: Boolean(isProjectsPath && !isNotificationsPath && !isDashboardsPath),
        shouldRender: true,
      },
      {
        label: "Dashboards",
        icon: <DashboardIcon className="size-5" />,
        href: `/${slug}/dashboards/`,
        isActive: isDashboardsPath,
        shouldRender: true,
      },
    ];

    return <WrappedComponent {...(props as P)} dockItems={dockItems} />;
  });

  return ComponentWithDockItems;
}
