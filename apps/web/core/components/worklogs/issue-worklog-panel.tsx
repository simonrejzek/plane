/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { Timer, Plus, Trash2, Pencil } from "lucide-react";
import type { TWorklog } from "@plane/types";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { convertHoursMinutesToMinutes, convertMinutesToHoursMinutesString } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useMember } from "@/hooks/store/use-member";
// services
import worklogService from "@/services/worklog.service";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

type FormState = {
  hours: string;
  minutes: string;
  description: string;
};

const emptyForm: FormState = { hours: "", minutes: "", description: "" };

export const IssueWorklogPanel = observer(function IssueWorklogPanel(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled = false } = props;
  const { getProjectById } = useProject();
  const { getUserDetails } = useMember();

  const project = getProjectById(projectId);
  const enabled = Boolean(project?.is_time_tracking_enabled);

  const [worklogs, setWorklogs] = useState<TWorklog[]>([]);
  const [totalMinutes, setTotalMinutes] = useState(0);
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!enabled || !workspaceSlug || !projectId || !issueId) return;
    setLoading(true);
    try {
      const [list, total] = await Promise.all([
        worklogService.fetchWorklogsByIssueId(workspaceSlug, projectId, issueId),
        worklogService.fetchWorklogCountByIssueId(workspaceSlug, projectId, issueId),
      ]);
      setWorklogs(list || []);
      setTotalMinutes(total?.total_worklog || 0);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error", message: "Failed to load worklogs." });
    } finally {
      setLoading(false);
    }
  }, [enabled, workspaceSlug, projectId, issueId]);

  useEffect(() => {
    void load();
  }, [load]);

  const sortedWorklogs = useMemo(
    () =>
      [...worklogs].sort((a, b) => {
        const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
        return bTime - aTime;
      }),
    [worklogs]
  );

  if (!enabled) return null;

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setFormOpen(true);
  };

  const openEdit = (log: TWorklog) => {
    const duration = log.duration || 0;
    const hours = Math.floor(duration / 60);
    const minutes = duration % 60;
    setEditingId(log.id || null);
    setForm({
      hours: hours ? String(hours) : "",
      minutes: minutes ? String(minutes) : "",
      description: log.description || "",
    });
    setFormOpen(true);
  };

  const handleSave = async () => {
    const hours = Number(form.hours) || 0;
    const minutes = Number(form.minutes) || 0;
    if (!hours && !minutes) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error", message: "Enter hours or minutes." });
      return;
    }
    const payload: Partial<TWorklog> = {
      duration: Math.round(convertHoursMinutesToMinutes(hours, minutes)),
      description: form.description || "",
    };
    setSaving(true);
    try {
      if (editingId) {
        await worklogService.updateWorklogById(workspaceSlug, projectId, issueId, editingId, payload);
        setToast({ type: TOAST_TYPE.SUCCESS, title: "Success", message: "Worklog updated." });
      } else {
        await worklogService.createWorklog(workspaceSlug, projectId, issueId, payload);
        setToast({ type: TOAST_TYPE.SUCCESS, title: "Success", message: "Worklog created." });
      }
      setFormOpen(false);
      setEditingId(null);
      setForm(emptyForm);
      await load();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error", message: "Could not save worklog." });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (worklogId: string) => {
    try {
      await worklogService.deleteWorklogById(workspaceSlug, projectId, issueId, worklogId);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success", message: "Worklog deleted." });
      await load();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error", message: "Could not delete worklog." });
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-custom-border-200 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm text-custom-text-200">
          <Timer className="h-4 w-4" />
          <span className="font-medium text-custom-text-100">Time tracking</span>
          <span className="text-custom-text-300">
            {loading ? "…" : convertMinutesToHoursMinutesString(totalMinutes).trim() || "0m"}
          </span>
        </div>
        {!disabled && (
          <Button variant="secondary" size="sm" onClick={openCreate} className="flex items-center gap-1">
            <Plus className="h-3.5 w-3.5" />
            Log time
          </Button>
        )}
      </div>

      {formOpen && !disabled && (
        <div className="space-y-2 rounded border border-custom-border-200 bg-custom-background-90 p-3">
          <div className="flex gap-2">
            <input
              type="number"
              min={0}
              placeholder="Hours"
              value={form.hours}
              onChange={(e) => setForm((f) => ({ ...f, hours: e.target.value }))}
              className="w-full rounded border border-custom-border-200 bg-custom-background-100 px-2 py-1.5 text-sm"
            />
            <input
              type="number"
              min={0}
              placeholder="Minutes"
              value={form.minutes}
              onChange={(e) => setForm((f) => ({ ...f, minutes: e.target.value }))}
              className="w-full rounded border border-custom-border-200 bg-custom-background-100 px-2 py-1.5 text-sm"
            />
          </div>
          <textarea
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            className="min-h-16 w-full resize-none rounded border border-custom-border-200 bg-custom-background-100 px-2 py-1.5 text-sm"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setFormOpen(false);
                setEditingId(null);
              }}
            >
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={() => void handleSave()} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {sortedWorklogs.length === 0 && !loading && (
          <p className="text-xs text-custom-text-300">No time logged yet.</p>
        )}
        {sortedWorklogs.map((log) => {
          const user = log.logged_by ? getUserDetails(log.logged_by) : undefined;
          const name = user?.display_name || user?.first_name || user?.email || "Someone";
          return (
            <div
              key={log.id}
              className="flex items-start justify-between gap-2 rounded border border-custom-border-100 px-2 py-1.5 text-xs"
            >
              <div className="min-w-0 space-y-0.5">
                <div className="text-custom-text-100">
                  <span className="font-medium">{name}</span>
                  {" logged "}
                  <span className="font-medium">
                    {convertMinutesToHoursMinutesString(log.duration || 0).trim()}
                  </span>
                </div>
                {log.description ? (
                  <p className="whitespace-pre-wrap text-custom-text-300">{log.description}</p>
                ) : null}
              </div>
              {!disabled && log.id && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    className="rounded p-1 text-custom-text-300 hover:bg-custom-background-80"
                    onClick={() => openEdit(log)}
                    aria-label="Edit worklog"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 text-custom-text-300 hover:bg-custom-background-80"
                    onClick={() => void handleDelete(log.id as string)}
                    aria-label="Delete worklog"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
});
