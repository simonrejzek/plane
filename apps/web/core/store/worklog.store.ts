/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
import type { TWorklog } from "@plane/types";
import worklogService from "@/services/worklog.service";

export class WorklogStore {
  worklogsByIssueId: Record<string, TWorklog[]> = {};
  totalMinutesByIssueId: Record<string, number> = {};

  constructor() {
    makeObservable(this, {
      worklogsByIssueId: observable,
      totalMinutesByIssueId: observable,
      fetchIssueWorklogs: action,
      createWorklog: action,
      updateWorklog: action,
      deleteWorklog: action,
    });
  }

  getWorklogsByIssueId = computedFn((issueId: string): TWorklog[] => this.worklogsByIssueId[issueId] || []);

  getTotalMinutesByIssueId = computedFn((issueId: string): number => this.totalMinutesByIssueId[issueId] || 0);

  getWorklogById = computedFn((issueId: string, worklogId: string): TWorklog | undefined =>
    (this.worklogsByIssueId[issueId] || []).find((w) => w.id === worklogId)
  );

  private recomputeTotal(issueId: string) {
    const total = (this.worklogsByIssueId[issueId] || []).reduce((sum, w) => sum + (w.duration || 0), 0);
    this.totalMinutesByIssueId[issueId] = total;
  }

  async fetchIssueWorklogs(workspaceSlug: string, projectId: string, issueId: string) {
    const [list, total] = await Promise.all([
      worklogService.fetchWorklogsByIssueId(workspaceSlug, projectId, issueId),
      worklogService.fetchWorklogCountByIssueId(workspaceSlug, projectId, issueId),
    ]);
    runInAction(() => {
      this.worklogsByIssueId[issueId] = list || [];
      this.totalMinutesByIssueId[issueId] = total?.total_worklog || 0;
    });
    return list || [];
  }

  async createWorklog(workspaceSlug: string, projectId: string, issueId: string, payload: Partial<TWorklog>) {
    const created = await worklogService.createWorklog(workspaceSlug, projectId, issueId, payload);
    if (!created?.id) return created;
    runInAction(() => {
      const current = this.worklogsByIssueId[issueId] || [];
      this.worklogsByIssueId[issueId] = [created, ...current];
      this.recomputeTotal(issueId);
    });
    return created;
  }

  async updateWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    payload: Partial<TWorklog>
  ) {
    const updated = await worklogService.updateWorklogById(workspaceSlug, projectId, issueId, worklogId, payload);
    if (!updated?.id) return updated;
    runInAction(() => {
      this.worklogsByIssueId[issueId] = (this.worklogsByIssueId[issueId] || []).map((w) =>
        w.id === worklogId ? updated : w
      );
      this.recomputeTotal(issueId);
    });
    return updated;
  }

  async deleteWorklog(workspaceSlug: string, projectId: string, issueId: string, worklogId: string) {
    await worklogService.deleteWorklogById(workspaceSlug, projectId, issueId, worklogId);
    runInAction(() => {
      this.worklogsByIssueId[issueId] = (this.worklogsByIssueId[issueId] || []).filter((w) => w.id !== worklogId);
      this.recomputeTotal(issueId);
    });
  }
}
