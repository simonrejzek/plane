/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

"use client";

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Timer } from "lucide-react";
import { convertMinutesToHoursMinutesString } from "@plane/utils";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import worklogService from "@/services/worklog.service";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
};

export const IssueWorklogSidebarProperty = observer(function IssueWorklogSidebarProperty(props: Props) {
  const { workspaceSlug, projectId, issueId } = props;
  const { getProjectById } = useProject();
  const project = getProjectById(projectId);
  const [totalMinutes, setTotalMinutes] = useState(0);

  useEffect(() => {
    if (!project?.is_time_tracking_enabled || !workspaceSlug || !projectId || !issueId) return;
    void worklogService
      .fetchWorklogCountByIssueId(workspaceSlug, projectId, issueId)
      .then((res) => setTotalMinutes(res?.total_worklog || 0))
      .catch(() => setTotalMinutes(0));
  }, [project?.is_time_tracking_enabled, workspaceSlug, projectId, issueId]);

  if (!project?.is_time_tracking_enabled) return null;

  return (
    <SidebarPropertyListItem icon={Timer} label="Tracked time">
      <div className="flex h-7.5 w-full items-center text-body-xs-regular text-primary">
        {convertMinutesToHoursMinutesString(totalMinutes).trim() || "0m"}
      </div>
    </SidebarPropertyListItem>
  );
});
