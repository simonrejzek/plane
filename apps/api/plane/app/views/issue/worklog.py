# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db.models import Sum
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ProjectEntityPermission
from plane.app.serializers.worklog import IssueWorkLogSerializer
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, IssueWorkLog, Project


class IssueWorkLogsEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def _ensure_time_tracking_enabled(self, project_id):
        project = Project.objects.filter(pk=project_id).first()
        if not project or not project.is_time_tracking_enabled:
            return Response(
                {"error": "Time tracking is not enabled for this project."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def post(self, request, slug, project_id, issue_id):
        disabled = self._ensure_time_tracking_enabled(project_id)
        if disabled:
            return disabled

        serializer = IssueWorkLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                issue_id=issue_id,
                logged_by=request.user,
            )
            Issue.objects.filter(pk=issue_id).update(updated_at=timezone.now())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, slug, project_id, issue_id):
        worklogs = IssueWorkLog.objects.filter(
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
            project__project_projectmember__member=request.user,
            project__project_projectmember__is_active=True,
        ).select_related("issue", "logged_by", "project", "workspace")
        serializer = IssueWorkLogSerializer(worklogs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, slug, project_id, issue_id, pk):
        disabled = self._ensure_time_tracking_enabled(project_id)
        if disabled:
            return disabled

        worklog = IssueWorkLog.objects.get(
            pk=pk,
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
        )
        serializer = IssueWorkLogSerializer(worklog, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            Issue.objects.filter(pk=issue_id).update(updated_at=timezone.now())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, project_id, issue_id, pk):
        worklog = IssueWorkLog.objects.get(
            pk=pk,
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
        )
        worklog.delete()
        Issue.objects.filter(pk=issue_id).update(updated_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueTotalWorkLogEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_id):
        total_worklog = IssueWorkLog.objects.filter(
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
            project__project_projectmember__member=request.user,
            project__project_projectmember__is_active=True,
        ).aggregate(total_worklog=Sum("duration"))["total_worklog"]
        return Response({"total_worklog": total_worklog or 0}, status=status.HTTP_200_OK)
