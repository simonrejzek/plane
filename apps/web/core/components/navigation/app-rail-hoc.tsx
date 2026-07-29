/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// hoc/withDockItems.tsx
import React from "react";
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { PiChatLogo, PlaneNewIcon, WikiIcon } from "@plane/propel/icons";
import type { AppSidebarItemData } from "@/components/sidebar/sidebar-item";
import { useWorkspacePaths } from "@/hooks/use-workspace-paths";

type WithDockItemsProps = {
  dockItems: (AppSidebarItemData & { shouldRender: boolean })[];
};

export function withDockItems<P extends WithDockItemsProps>(WrappedComponent: React.ComponentType<P>) {
  const ComponentWithDockItems = observer(function ComponentWithDockItems(props: Omit<P, keyof WithDockItemsProps>) {
    const { workspaceSlug } = useParams();
    const pathname = usePathname();
    const { isProjectsPath, isNotificationsPath, isWikiPath, isAiPath } = useWorkspacePaths();
    const slug = workspaceSlug?.toString() ?? "";

    // App rail dock — matches app.plane.so Business shell: Projects, Wiki, AI (no Dashboards product).
    const dockItems: (AppSidebarItemData & { shouldRender: boolean })[] = [
      {
        label: "Projects",
        icon: <PlaneNewIcon className="size-5" />,
        href: `/${slug}/`,
        isActive: Boolean(isProjectsPath && !isNotificationsPath && !isWikiPath && !isAiPath),
        shouldRender: true,
      },
      {
        label: "Wiki",
        icon: <WikiIcon className="size-5" />,
        href: `/${slug}/wiki/`,
        isActive: Boolean(isWikiPath),
        shouldRender: true,
      },
      {
        label: "AI",
        icon: <PiChatLogo className="size-5" />,
        href: `/${slug}/pi-chat/`,
        isActive: Boolean(isAiPath),
        shouldRender: true,
      },
    ];

    return <WrappedComponent {...(props as P)} dockItems={dockItems} />;
  });

  return ComponentWithDockItems;
}
