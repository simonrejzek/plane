# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import WorkSpaceBasePermission
from plane.app.serializers.exporter import ExporterHistorySerializer
from plane.app.serializers.worklog import IssueWorkLogSerializer
from plane.app.views.base import BaseAPIView
from plane.bgtasks.worklogs_export_task import worklogs_export_task
from plane.db.models import ExporterHistory, IssueWorkLog, Workspace


def build_worklog_filters(request):
    """Map query params to IssueWorkLog ORM filters."""
    filters = {}

    project_ids = request.GET.get("project")
    if project_ids:
        ids = [p for p in project_ids.split(",") if p and p != "null"]
        if ids:
            filters["project_id__in"] = ids

    logged_by_ids = request.GET.get("logged_by")
    if logged_by_ids:
        ids = [p for p in logged_by_ids.split(",") if p and p != "null"]
        if ids:
            filters["logged_by_id__in"] = ids

    # created_at can be "YYYY-MM-DD,YYYY-MM-DD" (start,end) like commercial EE
    created_at = request.GET.get("created_at")
    if created_at:
        parts = [p.strip() for p in created_at.split(",") if p.strip()]
        if len(parts) >= 1 and parts[0]:
            filters["created_at__date__gte"] = parts[0]
        if len(parts) >= 2 and parts[1]:
            filters["created_at__date__lte"] = parts[1]

    return filters


class WorkspaceWorkLogsEndpoint(BaseAPIView):
    permission_classes = [WorkSpaceBasePermission]

    @method_decorator(gzip_page)
    def get(self, request, slug):
        filters = build_worklog_filters(request)
        issue_worklogs = (
            IssueWorkLog.objects.filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
                workspace__slug=slug,
            )
            .filter(**filters)
            .order_by("-created_at")
            .select_related("logged_by", "issue", "project", "workspace")
            .distinct()
        )

        return self.paginate(
            order_by=request.GET.get("order_by", "-created_at"),
            request=request,
            queryset=issue_worklogs,
            on_results=lambda rows: IssueWorkLogSerializer(rows, many=True).data,
        )


class WorkspaceExportWorkLogsEndpoint(BaseAPIView):
    permission_classes = [WorkSpaceBasePermission]

    def post(self, request, slug):
        provider = request.data.get("provider")
        body_filters = request.data.get("filters") or {}
        workspace = Workspace.objects.filter(slug=slug).first()
        if not workspace:
            return Response({"error": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND)

        if provider not in ("csv", "xlsx"):
            return Response(
                {"error": f"Provider '{provider}' not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prefer explicit body filters; fall back to query string
        filter_params = {}
        project = body_filters.get("project") or request.GET.get("project")
        logged_by = body_filters.get("logged_by") or request.GET.get("logged_by")
        created_at = body_filters.get("created_at") or request.GET.get("created_at")

        # Normalize list filters to ORM kwargs for the celery task
        if project:
            if isinstance(project, list):
                project = ",".join(project)
            ids = [p for p in str(project).split(",") if p and p != "null"]
            if ids:
                filter_params["project_id__in"] = ids
        if logged_by:
            if isinstance(logged_by, list):
                logged_by = ",".join(logged_by)
            ids = [p for p in str(logged_by).split(",") if p and p != "null"]
            if ids:
                filter_params["logged_by_id__in"] = ids
        if created_at:
            if isinstance(created_at, list):
                parts = created_at
            else:
                parts = [p.strip() for p in str(created_at).split(",") if p.strip()]
            if len(parts) >= 1 and parts[0]:
                filter_params["created_at__date__gte"] = parts[0]
            if len(parts) >= 2 and parts[1]:
                filter_params["created_at__date__lte"] = parts[1]

        stored_filters = {
            "project": body_filters.get("project") or ([] if not project else str(project).split(",")),
            "logged_by": body_filters.get("logged_by") or ([] if not logged_by else str(logged_by).split(",")),
            "created_at": body_filters.get("created_at")
            or ([] if not created_at else (created_at if isinstance(created_at, list) else str(created_at).split(","))),
        }

        exporter = ExporterHistory.objects.create(
            workspace_id=workspace.id,
            initiated_by=request.user,
            provider=provider,
            filters=stored_filters,
            type="issue_worklogs",
        )
        worklogs_export_task.delay(
            provider=exporter.provider,
            workspace_id=str(workspace.id),
            user_id=str(request.user.id),
            token_id=exporter.token,
            slug=slug,
            filters=filter_params,
        )
        serializer = ExporterHistorySerializer(exporter)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request, slug):
        exporter_history = ExporterHistory.objects.filter(
            workspace__slug=slug, type="issue_worklogs"
        ).select_related("workspace", "initiated_by")

        return self.paginate(
            order_by=request.GET.get("order_by", "-created_at"),
            request=request,
            queryset=exporter_history,
            on_results=lambda rows: ExporterHistorySerializer(rows, many=True).data,
        )
