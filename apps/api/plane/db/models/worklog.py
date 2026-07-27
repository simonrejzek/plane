# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
from django.db import models

# Module imports
from plane.db.models.issue import Issue
from plane.db.models.project import ProjectBaseModel


class IssueWorkLog(ProjectBaseModel):
    """Issue-level time tracking entries (contract / Business feature)."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="worklogs")
    description = models.TextField(blank=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worklogs",
    )
    # duration is stored in minutes
    duration = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Issue Work Log"
        verbose_name_plural = "Issue Work Logs"
        db_table = "issue_worklogs"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.issue.name} {self.logged_by.email}"
