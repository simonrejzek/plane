# python imports
from typing import Optional
from datetime import date, datetime

# Third-party library imports
from asgiref.sync import sync_to_async

# Strawberry imports
import strawberry
import strawberry_django
from strawberry.scalars import JSON
from strawberry.types import Info


# Module Imports
from plane.db.models import (
    Issue,
    IssueLabel,
    IssueAssignee,
    ProjectUserProperty,
    IssueActivity,
    IssueComment,
    CycleIssue,
    ModuleIssue,
    IssueType,
)
from plane.graphql.types.users import UserType


@strawberry.type
class IssuesInformationObjectType:
    totalIssues: int
    groupInfo: Optional[JSON]


@strawberry.type
class IssuesInformationType:
    all: Optional[IssuesInformationObjectType]
    active: Optional[IssuesInformationObjectType]
    backlog: Optional[IssuesInformationObjectType]


@strawberry_django.type(Issue)
class IssuesType:
    id: strawberry.ID
    workspace: strawberry.ID
    # Official mobile WorkspaceIssuesQuery uses bare ID scalars for project/state
    project: strawberry.ID
    parent: Optional[strawberry.ID]
    # Must be optional: some issues have null state_id
    state: Optional[strawberry.ID]
    point: Optional[int]
    estimate_point: Optional[strawberry.ID]
    name: str
    # CE model field is description_json (not description) — resolved below
    description_html: Optional[str]
    description_stripped: Optional[str]
    priority: str
    start_date: Optional[date]
    target_date: Optional[date]
    sequence_id: int
    sort_order: float
    completed_at: Optional[date]
    archived_at: Optional[date]
    is_draft: bool
    external_source: Optional[str]
    external_id: Optional[str]
    created_by: Optional[strawberry.ID]
    updated_by: Optional[strawberry.ID]
    created_at: datetime
    updated_at: datetime
    cycle: Optional[strawberry.ID]
    modules: Optional[list[strawberry.ID]]
    type: Optional[strawberry.ID]
    project_identifier: Optional[str]

    @strawberry.field
    def state(self) -> Optional[strawberry.ID]:
        return str(self.state_id) if getattr(self, "state_id", None) else None

    @strawberry.field
    def parent(self) -> Optional[strawberry.ID]:
        return str(self.parent_id) if getattr(self, "parent_id", None) else None

    @strawberry.field
    def project(self) -> Optional[strawberry.ID]:
        return str(self.project_id) if getattr(self, "project_id", None) else None

    @strawberry.field
    def workspace(self) -> Optional[strawberry.ID]:
        return str(self.workspace_id) if getattr(self, "workspace_id", None) else None

    @strawberry.field
    def estimate_point(self) -> Optional[strawberry.ID]:
        return (
            str(self.estimate_point_id)
            if getattr(self, "estimate_point_id", None)
            else None
        )

    @strawberry.field
    def type(self) -> Optional[strawberry.ID]:
        return str(self.type_id) if getattr(self, "type_id", None) else None

    # CE Issue uses description_json, not description
    @strawberry.field
    def description(self) -> Optional[JSON]:
        value = getattr(self, "description_json", None)
        if value is None:
            value = getattr(self, "description", None)
        return value if value is not None else {}

    @strawberry.field(name="descriptionHtml")
    def description_html_field(self) -> Optional[str]:
        return getattr(self, "description_html", None) or "<p></p>"

    @strawberry.field(name="descriptionBinary")
    def description_binary_field(self) -> Optional[str]:
        # BinaryField is not useful to mobile GraphQL clients
        return None

    @strawberry.field
    async def assignees(self) -> Optional[list[strawberry.ID]]:
        assignee_ids = await sync_to_async(
            lambda: list(
                IssueAssignee.objects.filter(issue_id=self.id, deleted_at=None)
                .order_by("created_at")
                .values_list("assignee_id", flat=True)
            )
        )()
        return [str(assignee_id) for assignee_id in assignee_ids]

    @strawberry.field
    async def labels(self) -> Optional[list[strawberry.ID]]:
        label_ids = await sync_to_async(
            lambda: list(
                IssueLabel.objects.filter(issue_id=self.id, deleted_at=None)
                .order_by("created_at")
                .values_list("label_id", flat=True)
            )
        )()
        return [str(label_id) for label_id in label_ids]

    @strawberry.field
    async def cycle(self, info: Info) -> Optional[strawberry.ID]:
        cycle_issue = await sync_to_async(
            CycleIssue.objects.filter(issue_id=self.id).first
        )()
        if cycle_issue:
            return str(cycle_issue.cycle_id)
        return None

    @strawberry.field
    async def modules(self, info: Info) -> list[strawberry.ID]:
        # Fetch related module IDs in a synchronous context
        module_issues = await sync_to_async(
            lambda: list(
                ModuleIssue.objects.filter(issue_id=self.id).values_list(
                    "module_id", flat=True
                )
            )
        )()

        # Return the module IDs as strings
        return [str(module_id) for module_id in module_issues]

    @strawberry.field
    async def project_identifier(self) -> Optional[str]:
        project = self._state.fields_cache.get("project")
        if project is not None:
            return project.identifier
        project_id = getattr(self, "project_id", None)
        if not project_id:
            return None
        from plane.db.models import Project

        return await sync_to_async(
            lambda: Project.objects.filter(pk=project_id).values_list(
                "identifier", flat=True
            ).first()
        )()

    @strawberry.field
    async def parent_project_id(self) -> Optional[str]:
        parent = self._state.fields_cache.get("parent")
        if parent is not None and parent.project_id:
            return str(parent.project_id)
        parent_id = getattr(self, "parent_id", None)
        if not parent_id:
            return None
        project_id = await sync_to_async(
            lambda: Issue.issue_objects.filter(pk=parent_id).values_list(
                "project_id", flat=True
            ).first()
        )()
        return str(project_id) if project_id else None

    @strawberry.field
    async def parent_project_identifier(self) -> Optional[str]:
        parent = self._state.fields_cache.get("parent")
        if parent is not None:
            project = parent._state.fields_cache.get("project")
            if project is not None:
                return project.identifier
        parent_id = getattr(self, "parent_id", None)
        if not parent_id:
            return None
        return await sync_to_async(
            lambda: Issue.issue_objects.filter(pk=parent_id).values_list(
                "project__identifier", flat=True
            ).first()
        )()

    # Official mobile IssuesQuery / workspaceIssues — epics not in CE
    @strawberry.field(name="parentIsEpic")
    def parent_is_epic(self) -> bool:
        return False

    @strawberry.field(name="isEpic")
    def is_epic(self) -> bool:
        return False

    # Official mobile issueRelation nested analytics counters
    @strawberry.field
    def analytics(self) -> Optional["IssueAnalyticsType"]:
        return IssueAnalyticsType(
            backlog=0,
            unstarted=0,
            started=0,
            completed=0,
            cancelled=0,
        )


@strawberry.type
class IssueAnalyticsType:
    backlog: int = 0
    unstarted: int = 0
    started: int = 0
    completed: int = 0
    cancelled: int = 0


@strawberry.type
class IssueStatsType:
    attachments: int = 0
    relations: int = 0
    sub_work_items: int = 0
    links: int = 0
    pages: int = 0


@strawberry_django.type(ProjectUserProperty)
class IssueUserPropertyType:
    display_filters: JSON
    display_properties: JSON
    filters: JSON
    id: strawberry.ID
    project: strawberry.ID
    user: strawberry.ID
    workspace: strawberry.ID

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id

    @strawberry.field
    def user(self) -> int:
        return self.user_id

    @strawberry.field
    def project(self) -> int:
        return self.project_id


@strawberry_django.type(IssueActivity)
class IssuePropertyActivityType:
    id: strawberry.ID
    issue: strawberry.ID
    verb: str
    field: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    comment: str
    attachments: list[str]
    issue_comment: Optional[strawberry.ID]
    actor: strawberry.ID
    old_identifier: Optional[strawberry.ID]
    new_identifier: Optional[strawberry.ID]
    epoch: float
    workspace: strawberry.ID
    project: strawberry.ID
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    def actor_details(self) -> Optional[UserType]:
        return self._state.fields_cache.get("actor")

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id

    @strawberry.field
    def actor(self) -> int:
        return self.actor_id

    @strawberry.field
    def project(self) -> int:
        return self.project_id

    @strawberry.field
    def issue_comment(self) -> int:
        return self.issue_comment_id

    @strawberry.field
    def issue(self) -> int:
        return self.issue_id


@strawberry_django.type(IssueComment)
class IssueCommentActivityType:
    id: strawberry.ID
    comment_stripped: str
    comment_json: JSON
    comment_html: str
    attachments: list[str]
    issue: strawberry.ID
    actor: strawberry.ID
    access: str
    external_source: Optional[str]
    external_id: Optional[str]
    workspace: strawberry.ID
    project: strawberry.ID
    parent: Optional[strawberry.ID]
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    def actor_details(self) -> Optional[UserType]:
        return self._state.fields_cache.get("actor")

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id

    @strawberry.field
    def actor(self) -> int:
        return self.actor_id

    @strawberry.field
    def project(self) -> int:
        return self.project_id

    @strawberry.field
    def issue(self) -> int:
        return self.issue_id

    @strawberry.field
    def parent(self) -> Optional[strawberry.ID]:
        return str(self.parent_id) if self.parent_id else None


@strawberry_django.type(Issue)
class IssueLiteType:
    id: strawberry.ID
    name: str
    sequence_id: int
    workspace: strawberry.ID
    project: strawberry.ID
    project_identifier: Optional[str]

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id


@strawberry_django.type(IssueType)
class IssueTypesType:
    id: strawberry.ID
    workspace: strawberry.ID
    name: str
    description: str
    logo_props: JSON
    is_default: bool
    level: int
    is_active: bool

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id
