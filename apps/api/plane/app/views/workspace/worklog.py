# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.views.decorators.gzip import gzip_page
from django.utils.decorators import method_decorator

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import WorkSpaceBasePermission
from plane.app.serializers.worklog import IssueWorkLogSerializer
from plane.app.views.base import BaseAPIView
from plane.db.models import IssueWorkLog


class WorkspaceWorkLogsEndpoint(BaseAPIView):
    permission_classes = [WorkSpaceBasePermission]

    @method_decorator(gzip_page)
    def get(self, request, slug):
        issue_worklogs = (
            IssueWorkLog.objects.filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
                workspace__slug=slug,
            )
            .order_by("-created_at")
            .select_related("logged_by", "issue", "project", "workspace")
        )

        # Optional filters (contract worklog list)
        project_ids = request.GET.get("project")
        if project_ids:
            issue_worklogs = issue_worklogs.filter(project_id__in=project_ids.split(","))

        logged_by_ids = request.GET.get("logged_by")
        if logged_by_ids:
            issue_worklogs = issue_worklogs.filter(logged_by_id__in=logged_by_ids.split(","))

        return self.paginate(
            order_by=request.GET.get("order_by", "-created_at"),
            request=request,
            queryset=issue_worklogs,
            on_results=lambda rows: IssueWorkLogSerializer(rows, many=True).data,
        )
