/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TWorklogIssue = {
  id: string | undefined;
  sequence_id: number | undefined;
  name: string | undefined;
};

export type TWorklogProject = {
  id: string | undefined;
  name: string | undefined;
  identifier: string | undefined;
};

export type TWorklog = {
  id: string | undefined;
  description: string | undefined;
  logged_by: string | undefined;
  /** Duration in minutes */
  duration: number | undefined;
  workspace_id: string | undefined;
  project_id: string | undefined;
  issue_detail: TWorklogIssue | undefined;
  project_detail?: TWorklogProject | undefined;
  created_by: string | undefined;
  updated_by: string | undefined;
  created_at: string | undefined;
  updated_at: string | undefined;
};

export type TWorklogIssueTotalCount = {
  total_worklog: number | undefined;
};

export type TWorklogPaginatedInfo = {
  next_cursor: string | undefined;
  prev_cursor: string | undefined;
  next_page_results: boolean | undefined;
  prev_page_results: boolean | undefined;
  total_pages: number | undefined;
  count: number | undefined;
  total_count: number | undefined;
  results: TWorklog[] | undefined;
};

export type TWorklogFilterKeys = "logged_by" | "project" | "created_at";

export type TWorklogFilters = {
  logged_by: string[];
  project: string[];
  created_at: string[];
};

export type TWorklogDownloadFormat = "csv" | "xlsx";

export type TWorklogDownloadStatus = "queued" | "processing" | "completed" | "failed" | "expired";

export type TWorklogDownload = {
  id: string | undefined;
  provider: TWorklogDownloadFormat | undefined;
  status: TWorklogDownloadStatus | undefined;
  url: string | undefined;
  filters: Partial<TWorklogFilters> | undefined;
  type: string | undefined;
  initiated_by: string | undefined;
  initiated_by_detail?: {
    id?: string;
    display_name?: string;
    first_name?: string;
    last_name?: string;
  };
  created_at: string | undefined;
  updated_at: string | undefined;
};

export type TWorklogDownloadPaginatedInfo = {
  next_cursor: string | undefined;
  prev_cursor: string | undefined;
  next_page_results: boolean | undefined;
  prev_page_results: boolean | undefined;
  total_pages: number | undefined;
  count: number | undefined;
  total_count: number | undefined;
  results: TWorklogDownload[] | undefined;
};
