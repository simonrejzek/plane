/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TWorklog,
  TWorklogDownload,
  TWorklogDownloadFormat,
  TWorklogDownloadPaginatedInfo,
  TWorklogIssueTotalCount,
  TWorklogPaginatedInfo,
} from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export class WorklogService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async fetchWorkspaceWorklogs(
    workspaceSlug: string,
    params?: Record<string, string | number | undefined>
  ): Promise<TWorklogPaginatedInfo | undefined> {
    const { data } = await this.get(`/api/workspaces/${workspaceSlug}/worklogs/`, { params });
    return data || undefined;
  }

  async exportWorkspaceWorklogs(
    workspaceSlug: string,
    provider: TWorklogDownloadFormat,
    filters?: Record<string, string[] | string | undefined>
  ): Promise<TWorklogDownload | undefined> {
    const { data } = await this.post(`/api/workspaces/${workspaceSlug}/export-worklogs/`, {
      provider,
      filters: filters || {},
    });
    return data || undefined;
  }

  async fetchWorkspaceWorklogDownloads(
    workspaceSlug: string,
    params?: Record<string, string | number | undefined>
  ): Promise<TWorklogDownloadPaginatedInfo | undefined> {
    const { data } = await this.get(`/api/workspaces/${workspaceSlug}/export-worklogs/`, { params });
    return data || undefined;
  }

  async fetchWorklogsByIssueId(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<TWorklog[] | undefined> {
    const { data } = await this.get(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/`
    );
    return data || undefined;
  }

  async fetchWorklogCountByIssueId(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<TWorklogIssueTotalCount | undefined> {
    const { data } = await this.get(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/total-worklogs/`
    );
    return data || undefined;
  }

  async createWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    payload: Partial<TWorklog>
  ): Promise<TWorklog | undefined> {
    const { data } = await this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/`,
      payload
    );
    return data || undefined;
  }

  async updateWorklogById(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    payload: Partial<TWorklog>
  ): Promise<TWorklog | undefined> {
    const { data } = await this.patch(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/${worklogId}/`,
      payload
    );
    return data || undefined;
  }

  async deleteWorklogById(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string
  ): Promise<void> {
    await this.delete(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/${worklogId}/`
    );
  }
}

const worklogService = new WorklogService();
export default worklogService;
