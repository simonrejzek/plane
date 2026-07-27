/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Ellipsis, Timer } from "lucide-react";
// plane imports
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { CustomMenu, Popover } from "@plane/ui";
import {
  calculateTimeAgo,
  convertMinutesToHoursAndMinutes,
  convertMinutesToHoursMinutesString,
  getFileURL,
  renderFormattedDate,
  renderFormattedTime,
} from "@plane/utils";
import type { TWorklog } from "@plane/types";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { usePlatformOS } from "@/hooks/use-platform-os";
import { useWorklogStore } from "@/hooks/store/use-worklog";
// local
import { WorklogForm } from "./worklog-form";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  worklogId: string;
  ends: "top" | "bottom" | undefined;
  disabled?: boolean;
};

export const IssueActivityWorklogItem = observer(function IssueActivityWorklogItem(props: Props) {
  const { workspaceSlug, projectId, issueId, worklogId, ends, disabled = false } = props;
  const { getUserDetails } = useMember();
  const worklogStore = useWorklogStore();
  const worklog = worklogStore.getWorklogById(issueId, worklogId);
  const { isMobile } = usePlatformOS();
  const popoverButtonRef = useRef<HTMLButtonElement | null>(null);
  const [saving, setSaving] = useState(false);

  if (!worklog) return null;

  const user = worklog.logged_by ? getUserDetails(worklog.logged_by) : undefined;
  const displayName = user?.display_name || user?.first_name || "Someone";
  const avatarUrl = user?.avatar_url;
  const durationLabel = convertMinutesToHoursMinutesString(worklog.duration || 0).trim() || "0m";
  const { hours, minutes } = convertMinutesToHoursAndMinutes(worklog.duration || 0);

  const handleClose = () => {
    popoverButtonRef.current?.click();
  };

  const handleUpdate = async (payload: Partial<TWorklog>) => {
    setSaving(true);
    try {
      await worklogStore.updateWorklog(workspaceSlug, projectId, issueId, worklogId, payload);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Worklog updated." });
      handleClose();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: "Could not update worklog." });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      await worklogStore.deleteWorklog(workspaceSlug, projectId, issueId, worklogId);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success!", message: "Worklog deleted." });
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: "Could not delete worklog." });
    }
  };

  return (
    <div
      className={`relative flex gap-3 text-caption-sm-regular ${
        ends === "top" ? "pb-2" : ends === "bottom" ? "pt-2" : "py-2"
      } ${!worklog.description ? "items-center" : ""}`}
    >
      <div className="absolute top-0 bottom-0 left-[13px] w-px bg-layer-3" aria-hidden />

      {/* Avatar with timer badge — commercial Plane worklog style, 1.3 tokens */}
      <div className="relative z-[4] flex h-7 w-7 flex-shrink-0 items-center justify-center overflow-visible">
        <div className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-full border border-subtle bg-layer-2 text-caption-sm-medium text-secondary uppercase">
          {avatarUrl && getFileURL(avatarUrl) ? (
            <img
              src={getFileURL(avatarUrl)}
              alt={displayName}
              className="h-7 w-7 rounded-full object-cover"
              height={28}
              width={28}
            />
          ) : (
            <span>{displayName.charAt(0)}</span>
          )}
        </div>
        <div className="absolute -right-1 -bottom-0.5 flex h-4 w-4 items-center justify-center overflow-hidden rounded-full border border-subtle bg-layer-2 text-secondary">
          <Timer className="h-2.5 w-2.5" />
        </div>
      </div>

      <div className="min-w-0 w-full space-y-1.5">
        <div className="relative flex w-full items-center">
          <div className="flex w-full truncate gap-1 text-secondary">
            <div className="truncate">
              <Link
                href={`/${workspaceSlug}/profile/${user?.id || ""}`}
                className="font-medium text-primary capitalize hover:underline"
              >
                {displayName}
              </Link>
              <span>{` logged `}</span>
              <span className="font-medium text-primary">{`${durationLabel}.`}</span>
            </div>
            {worklog.created_at && (
              <Tooltip
                isMobile={isMobile}
                tooltipContent={`${renderFormattedDate(worklog.created_at)}, ${renderFormattedTime(worklog.created_at)}`}
              >
                <span className="whitespace-nowrap text-tertiary">{calculateTimeAgo(worklog.created_at)}</span>
              </Tooltip>
            )}
          </div>

          {!disabled && (
            <div className="relative flex-shrink-0">
              <div className="absolute right-0 bottom-0">
                <Popover
                  button={<></>}
                  popoverButtonRef={popoverButtonRef}
                  buttonClassName="h-0 w-0"
                  buttonRefClassName="w-auto"
                  popoverClassName="relative"
                  panelClassName="z-20 my-1 w-72 rounded-lg border border-subtle bg-surface-1 p-3 text-caption-sm-regular shadow-raised-200 focus:outline-none"
                >
                  <WorklogForm
                    data={{
                      hours: hours ? String(hours) : "",
                      minutes: minutes ? String(minutes) : "",
                      description: worklog.description || "",
                    }}
                    onSubmit={handleUpdate}
                    onCancel={handleClose}
                    buttonDisabled={saving}
                    buttonTitle={saving ? "Updating" : "Update"}
                  />
                </Popover>
              </div>
              <CustomMenu
                maxHeight="md"
                placement="bottom-start"
                customButton={
                  <div className="flex size-5 items-center justify-center rounded text-tertiary transition-colors hover:bg-layer-transparent-hover">
                    <Ellipsis className="size-3.5" />
                  </div>
                }
                customButtonClassName="flex"
                closeOnSelect
              >
                <CustomMenu.MenuItem onClick={() => popoverButtonRef.current?.click()}>
                  <span className="text-secondary">Edit</span>
                </CustomMenu.MenuItem>
                <CustomMenu.MenuItem onClick={() => void handleDelete()}>
                  <span className="text-secondary">Delete</span>
                </CustomMenu.MenuItem>
              </CustomMenu>
            </div>
          )}
        </div>

        {worklog.description ? (
          <div className="whitespace-pre-line rounded-md border border-subtle p-2 text-secondary">
            {worklog.description}
          </div>
        ) : null}
      </div>
    </div>
  );
});
