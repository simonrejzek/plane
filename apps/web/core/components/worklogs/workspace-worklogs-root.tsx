/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { ChevronDown, Download, RefreshCw } from "lucide-react";
// plane imports
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import type { TWorklog, TWorklogDownload, TWorklogDownloadFormat, TWorklogFilters } from "@plane/types";
import { CustomMenu } from "@plane/ui";
import { convertMinutesToHoursMinutesString, renderFormattedDate } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
// services
import worklogService from "@/services/worklog.service";

type Props = {
  workspaceSlug: string;
};

const emptyFilters: TWorklogFilters = {
  logged_by: [],
  project: [],
  created_at: [],
};

export const WorkspaceWorklogsRoot = observer(function WorkspaceWorklogsRoot(props: Props) {
  const { workspaceSlug } = props;
  const {
    getUserDetails,
    workspace: { workspaceMemberIds },
  } = useMember();
  const { workspaceProjectIds, getProjectById } = useProject();

  const [worklogs, setWorklogs] = useState<TWorklog[]>([]);
  const [downloads, setDownloads] = useState<TWorklogDownload[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [prevCursor, setPrevCursor] = useState<string | undefined>(undefined);
  const [nextCursor, setNextCursor] = useState<string | undefined>(undefined);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [count, setCount] = useState(0);

  const [filters, setFilters] = useState<TWorklogFilters>(emptyFilters);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedUser, setSelectedUser] = useState("");

  const projectOptions = useMemo(
    () =>
      (workspaceProjectIds || [])
        .map((id) => getProjectById(id))
        .filter((p): p is NonNullable<typeof p> => !!p)
        .sort((a, b) => (a.name || "").localeCompare(b.name || "")),
    [workspaceProjectIds, getProjectById]
  );

  const buildParams = useCallback(
    (pageCursor?: string) => {
      const params: Record<string, string | number | undefined> = {
        per_page: 20,
        cursor: pageCursor,
      };
      if (filters.project.length) params.project = filters.project.join(",");
      if (filters.logged_by.length) params.logged_by = filters.logged_by.join(",");
      if (filters.created_at.length) params.created_at = filters.created_at.join(",");
      return params;
    },
    [filters]
  );

  const loadWorklogs = useCallback(
    async (pageCursor?: string) => {
      setLoading(true);
      try {
        const data = await worklogService.fetchWorkspaceWorklogs(workspaceSlug, buildParams(pageCursor));
        setWorklogs(data?.results || []);
        setCursor(pageCursor);
        setNextCursor(data?.next_cursor);
        setPrevCursor(data?.prev_cursor);
        setHasNext(!!data?.next_page_results);
        setHasPrev(!!data?.prev_page_results);
        setTotalCount(data?.total_count || 0);
        setCount(data?.count || data?.results?.length || 0);
      } catch {
        setToast({ type: TOAST_TYPE.ERROR, title: "Error", message: "Failed to load worklogs." });
      } finally {
        setLoading(false);
      }
    },
    [workspaceSlug, buildParams]
  );

  const loadDownloads = useCallback(async () => {
    try {
      const data = await worklogService.fetchWorkspaceWorklogDownloads(workspaceSlug, { per_page: 10 });
      setDownloads(data?.results || []);
    } catch {
      // non-blocking
    }
  }, [workspaceSlug]);

  useEffect(() => {
    void loadWorklogs();
    void loadDownloads();
  }, [loadWorklogs, loadDownloads]);

  const applyFilters = () => {
    const created_at: string[] = [];
    if (startDate || endDate) {
      created_at.push(startDate || "");
      created_at.push(endDate || "");
    }
    setFilters({
      project: selectedProject ? [selectedProject] : [],
      logged_by: selectedUser ? [selectedUser] : [],
      created_at,
    });
  };

  // reload when filters change
  useEffect(() => {
    void loadWorklogs(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const handleExport = async (provider: TWorklogDownloadFormat) => {
    setExporting(true);
    try {
      await worklogService.exportWorkspaceWorklogs(workspaceSlug, provider, {
        project: filters.project,
        logged_by: filters.logged_by,
        created_at: filters.created_at,
      });
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Export queued",
        message: "You can download the file from Previous Downloads once ready.",
      });
      // refresh downloads after a short delay
      setTimeout(() => void loadDownloads(), 1500);
      void loadDownloads();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Export failed", message: "Could not start export. Please try again." });
    } finally {
      setExporting(false);
    }
  };

  const loggedByLabel = (worklog: TWorklog) => {
    const user = worklog.logged_by ? getUserDetails(worklog.logged_by) : undefined;
    const name = user?.display_name || user?.first_name || "Unknown";
    const when = worklog.created_at ? renderFormattedDate(worklog.created_at) : "";
    return when ? `${name} on ${when}` : name;
  };

  const issueLabel = (worklog: TWorklog) => {
    const identifier = worklog.project_detail?.identifier;
    const seq = worklog.issue_detail?.sequence_id;
    const name = worklog.issue_detail?.name || "";
    if (identifier != null && seq != null) return `${identifier}-${seq} ${name}`;
    return name || "—";
  };

  const countFilters = (f: TWorklogDownload["filters"] | undefined) => {
    if (!f) return 0;
    let n = 0;
    if (f.project?.length) n += 1;
    if (f.logged_by?.length) n += 1;
    if (f.created_at?.length) n += 1;
    return n;
  };

  return (
    <div className="space-y-6">
      {/* Header row: filters + download */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-8 rounded-md border border-subtle bg-surface-1 px-2 text-body-xs-regular text-primary"
            value={selectedUser}
            onChange={(e) => setSelectedUser(e.target.value)}
          >
            <option value="">Users</option>
            {(workspaceMemberIds || []).map((id) => {
              const u = getUserDetails(id);
              return (
                <option key={id} value={id}>
                  {u?.display_name || u?.first_name || id}
                </option>
              );
            })}
          </select>

          <select
            className="h-8 rounded-md border border-subtle bg-surface-1 px-2 text-body-xs-regular text-primary"
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
          >
            <option value="">Projects</option>
            {projectOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          <div className="flex items-center gap-1 rounded-md border border-subtle bg-surface-1 px-2 py-1">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="h-6 bg-transparent text-body-xs-regular text-primary outline-none"
            />
            <span className="text-tertiary">→</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="h-6 bg-transparent text-body-xs-regular text-primary outline-none"
            />
          </div>

          <Button size="sm" variant="secondary" onClick={applyFilters}>
            Apply
          </Button>
        </div>

        <CustomMenu
          maxHeight="md"
          placement="bottom-end"
          customButton={
            <Button size="sm" variant="primary" prependIcon={<Download className="size-3.5" />} loading={exporting}>
              Download
              <ChevronDown className="ml-1 size-3.5" />
            </Button>
          }
          customButtonClassName="flex"
          closeOnSelect
        >
          <CustomMenu.MenuItem onClick={() => void handleExport("xlsx")}>
            <span>Excel</span>
          </CustomMenu.MenuItem>
          <CustomMenu.MenuItem onClick={() => void handleExport("csv")}>
            <span>CSV</span>
          </CustomMenu.MenuItem>
        </CustomMenu>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-subtle">
        <table className="w-full text-left text-body-xs-regular">
          <thead className="border-b border-subtle bg-layer-1 text-tertiary">
            <tr>
              <th className="px-4 py-2.5 font-medium">Project</th>
              <th className="px-4 py-2.5 font-medium">Issue</th>
              <th className="px-4 py-2.5 font-medium">Logged</th>
              <th className="px-4 py-2.5 text-right font-medium">Duration</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-tertiary">
                  Loading worklogs…
                </td>
              </tr>
            ) : worklogs.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-tertiary">
                  No worklogs found.
                </td>
              </tr>
            ) : (
              worklogs.map((w) => (
                <tr key={w.id} className="border-b border-subtle last:border-0">
                  <td className="px-4 py-3 text-primary">{w.project_detail?.name || "—"}</td>
                  <td className="px-4 py-3 text-primary">{issueLabel(w)}</td>
                  <td className="px-4 py-3 text-secondary">{loggedByLabel(w)}</td>
                  <td className="px-4 py-3 text-right text-primary">
                    {convertMinutesToHoursMinutesString(w.duration || 0).trim() || "0m"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div className="flex items-center justify-between border-t border-subtle px-4 py-2 text-caption-sm-regular text-tertiary">
          <span>
            {totalCount > 0 ? `Showing ${count} of ${totalCount}` : "0 results"}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={!hasPrev || loading} onClick={() => void loadWorklogs(prevCursor)}>
              Prev
            </Button>
            <Button size="sm" variant="secondary" disabled={!hasNext || loading} onClick={() => void loadWorklogs(nextCursor)}>
              Next
            </Button>
          </div>
        </div>
      </div>

      {/* Previous downloads */}
      <div className="rounded-lg border border-subtle">
        <div className="flex items-center justify-between border-b border-subtle px-4 py-3">
          <h4 className="text-body-sm-medium text-primary">Previous Downloads</h4>
          <button
            type="button"
            className="rounded p-1 text-tertiary hover:bg-layer-transparent-hover"
            onClick={() => void loadDownloads()}
            aria-label="Refresh downloads"
          >
            <RefreshCw className="size-3.5" />
          </button>
        </div>
        <div className="divide-y divide-subtle">
          {downloads.length === 0 ? (
            <div className="px-4 py-6 text-center text-body-xs-regular text-tertiary">No previous downloads.</div>
          ) : (
            downloads.map((d) => {
              const by =
                d.initiated_by_detail?.display_name ||
                d.initiated_by_detail?.first_name ||
                "Someone";
              const providerLabel = d.provider === "xlsx" ? "Export to xlsx" : `Export to ${d.provider || "file"}`;
              const ready = d.status === "completed" && d.url;
              return (
                <div key={d.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <div className="flex items-center gap-2 text-body-xs-medium text-primary">
                      {providerLabel}
                      <span className="rounded bg-layer-2 px-1.5 py-0.5 text-caption-sm-regular text-tertiary">
                        {countFilters(d.filters)} filters
                      </span>
                      {d.status && d.status !== "completed" && (
                        <span className="text-caption-sm-regular text-tertiary capitalize">{d.status}</span>
                      )}
                    </div>
                    <div className="mt-0.5 text-caption-sm-regular text-tertiary">
                      {d.created_at ? renderFormattedDate(d.created_at) : ""} · Exported by {by}
                    </div>
                  </div>
                  {ready ? (
                    <a href={d.url} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="secondary">
                        Download
                      </Button>
                    </a>
                  ) : (
                    <Button size="sm" variant="secondary" disabled>
                      Download
                    </Button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
});
