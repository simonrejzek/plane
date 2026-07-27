# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.issue.worklog import IssueTotalWorkLogEndpoint, IssueWorkLogsEndpoint
from plane.app.views.workspace.worklog import WorkspaceExportWorkLogsEndpoint, WorkspaceWorkLogsEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/worklogs/",
        IssueWorkLogsEndpoint.as_view(),
        name="issue-worklogs",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/worklogs/<uuid:pk>/",
        IssueWorkLogsEndpoint.as_view(),
        name="issue-worklog-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/total-worklogs/",
        IssueTotalWorkLogEndpoint.as_view(),
        name="issue-total-worklogs",
    ),
    path(
        "workspaces/<str:slug>/worklogs/",
        WorkspaceWorkLogsEndpoint.as_view(),
        name="workspace-worklogs",
    ),
    path(
        "workspaces/<str:slug>/export-worklogs/",
        WorkspaceExportWorkLogsEndpoint.as_view(),
        name="workspace-export-worklogs",
    ),
]
