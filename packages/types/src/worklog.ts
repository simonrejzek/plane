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

export type TWorklog = {
  id: string | undefined;
  description: string | undefined;
  logged_by: string | undefined;
  /** Duration in minutes */
  duration: number | undefined;
  workspace_id: string | undefined;
  project_id: string | undefined;
  issue_detail: TWorklogIssue | undefined;
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
