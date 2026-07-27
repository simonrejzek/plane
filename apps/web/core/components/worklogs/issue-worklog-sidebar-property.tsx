/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { Timer } from "lucide-react";
import { convertMinutesToHoursMinutesString } from "@plane/utils";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useWorklogStore } from "@/hooks/store/use-worklog";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
};

/**
 * Properties panel: total tracked time only (matches commercial Plane).
 * Individual log entries appear in the activity timeline.
 */
export const IssueWorklogSidebarProperty = observer(function IssueWorklogSidebarProperty(props: Props) {
  const { workspaceSlug, projectId, issueId } = props;
  const { getProjectById } = useProject();
  const worklogStore = useWorklogStore();
  const project = getProjectById(projectId);
  const totalMinutes = worklogStore.getTotalMinutesByIssueId(issueId);

  useEffect(() => {
    if (!project?.is_time_tracking_enabled || !workspaceSlug || !projectId || !issueId) return;
    void worklogStore.fetchIssueWorklogs(workspaceSlug, projectId, issueId);
  }, [project?.is_time_tracking_enabled, workspaceSlug, projectId, issueId, worklogStore]);

  if (!project?.is_time_tracking_enabled) return null;

  const label = convertMinutesToHoursMinutesString(totalMinutes).trim() || "0h 0m";

  return (
    <SidebarPropertyListItem icon={Timer} label="Tracked time">
      <div className="flex h-7.5 w-full items-center text-body-xs-regular text-primary">{label}</div>
    </SidebarPropertyListItem>
  );
});
