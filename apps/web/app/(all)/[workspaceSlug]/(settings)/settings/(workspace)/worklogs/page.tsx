/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { WorkspaceWorklogsRoot } from "@/components/worklogs/workspace-worklogs-root";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
import { useParams } from "react-router";

function WorklogsPage() {
  const { workspaceSlug } = useParams();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  const { t } = useTranslation();

  const canPerformAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name
    ? `${currentWorkspace.name} - ${t("workspace_settings.settings.worklogs.title")}`
    : undefined;

  if (workspaceUserInfo && !canPerformAdminActions) {
    return <NotAuthorizedView section="settings" className="h-auto" />;
  }

  if (!workspaceSlug) return null;

  return (
    <SettingsContentWrapper hugging>
      <PageHead title={pageTitle} />
      <div
        className={cn("flex w-full flex-col gap-y-6", {
          "opacity-60": !canPerformAdminActions,
        })}
      >
        <SettingsHeading
          title={t("workspace_settings.settings.worklogs.heading")}
          description={t("workspace_settings.settings.worklogs.description")}
        />
        <WorkspaceWorklogsRoot workspaceSlug={workspaceSlug.toString()} />
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(WorklogsPage);
