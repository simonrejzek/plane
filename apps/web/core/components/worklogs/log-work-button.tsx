/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { Plus } from "lucide-react";
// plane imports
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Popover } from "@plane/ui";
import { cn } from "@plane/utils";
import type { TWorklog } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useWorklogStore } from "@/hooks/store/use-worklog";
// local
import { WorklogForm } from "./worklog-form";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

export const IssueActivityWorklogCreateButton = observer(function IssueActivityWorklogCreateButton(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled = false } = props;
  const { getProjectById } = useProject();
  const worklogStore = useWorklogStore();
  const project = getProjectById(projectId);
  const popoverButtonRef = useRef<HTMLButtonElement | null>(null);
  const [saving, setSaving] = useState(false);

  if (!project?.is_time_tracking_enabled) return null;

  const handleClose = () => {
    popoverButtonRef.current?.click();
  };

  const handleSubmit = async (payload: Partial<TWorklog>) => {
    setSaving(true);
    try {
      await worklogStore.createWorklog(workspaceSlug, projectId, issueId, payload);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Worklog created successfully." });
      handleClose();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: "Something went wrong. please try again." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover
      popoverButtonRef={popoverButtonRef}
      disabled={disabled}
      popoverClassName="relative"
      buttonRefClassName="w-auto"
      buttonClassName={cn("outline-none", { "cursor-not-allowed": disabled })}
      button={
        <Button size="sm" variant="ghost" prependIcon={<Plus className="size-3.5" />} disabled={disabled}>
          Log work
        </Button>
      }
      popperPosition="bottom-end"
      panelClassName="z-20 my-1 w-72 rounded-lg border border-subtle bg-surface-1 p-3 text-caption-sm-regular shadow-raised-200 focus:outline-none"
    >
      <WorklogForm
        data={{ hours: "", minutes: "", description: "" }}
        onSubmit={handleSubmit}
        onCancel={handleClose}
        buttonDisabled={saving}
        buttonTitle={saving ? "Saving" : "Save"}
      />
    </Popover>
  );
});
