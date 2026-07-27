# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import IssueWorkLog


class IssueWorkLogSerializer(BaseSerializer):
    issue_detail = serializers.SerializerMethodField()
    project_detail = serializers.SerializerMethodField()

    class Meta:
        model = IssueWorkLog
        fields = [
            "id",
            "created_at",
            "updated_at",
            "description",
            "duration",
            "created_by",
            "updated_by",
            "project_id",
            "workspace_id",
            "logged_by",
            "issue_detail",
            "project_detail",
        ]
        read_only_fields = [
            "logged_by",
            "issue",
            "workspace",
            "project",
        ]

    def get_issue_detail(self, obj):
        issue = obj.issue
        return {
            "id": str(issue.id),
            "sequence_id": issue.sequence_id,
            "name": issue.name,
        }

    def get_project_detail(self, obj):
        project = obj.project
        return {
            "id": str(project.id),
            "name": project.name,
            "identifier": project.identifier,
        }
