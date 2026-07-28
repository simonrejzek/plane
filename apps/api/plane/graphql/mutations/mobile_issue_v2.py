# Python imports
from datetime import datetime, date
from typing import Optional, List, Any
import json
import logging

# Strawberry
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension
from strawberry.exceptions import GraphQLError
from strawberry.scalars import JSON

# Third-party
from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.graphql.permissions.project import ProjectMemberPermission
from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueLabel,
    Workspace,
    ModuleIssue,
    CycleIssue,
    State,
)
from plane.graphql.types.issue import IssuesType
from plane.graphql.bgtasks.issue_activity_task import issue_activity
from plane.graphql.utils.issue_activity import convert_issue_properties_to_activity_dict

log = logging.getLogger("plane.api.request")


@strawberry.input
class IssueCreateInputType:
    name: Optional[str] = None
    state: Optional[str] = None
    priority: Optional[str] = "none"
    descriptionHtml: Optional[str] = None
    # Official mobile may also send ProseMirror JSON
    description: Optional[JSON] = None
    parent: Optional[str] = None
    startDate: Optional[date] = None
    targetDate: Optional[date] = None
    assignees: Optional[List[strawberry.ID]] = None
    labels: Optional[List[strawberry.ID]] = None
    cycleId: Optional[str] = None
    moduleIds: Optional[List[strawberry.ID]] = None
    estimatePoint: Optional[str] = None


@strawberry.input
class IssueUpdateInputType:
    name: Optional[str] = None
    state: Optional[str] = None
    priority: Optional[str] = None
    descriptionHtml: Optional[str] = None
    description: Optional[JSON] = None
    parent: Optional[str] = None
    startDate: Optional[date] = None
    targetDate: Optional[date] = None
    assignees: Optional[List[strawberry.ID]] = None
    labels: Optional[List[strawberry.ID]] = None
    cycleId: Optional[str] = None
    moduleIds: Optional[List[strawberry.ID]] = None
    estimatePoint: Optional[str] = None


def _date_to_str(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d")


def _default_state_id(project_id):
    """Prefer non-triage default state so issue_objects manager can see the issue."""
    st = (
        State.objects.filter(project_id=project_id, default=True)
        .exclude(is_triage=True)
        .first()
    )
    if st:
        return st.id
    st = State.objects.filter(project_id=project_id).exclude(is_triage=True).first()
    return st.id if st else None


def _coerce_state_id(project_id, state_id):
    """Never persist triage states — they are invisible to Issue.issue_objects lists."""
    if not state_id:
        return _default_state_id(project_id)
    # State.objects excludes triage; use all_state_objects for lookup
    manager = getattr(State, "all_state_objects", State.objects)
    st = manager.filter(id=state_id, project_id=project_id).first()
    if st is None:
        return _default_state_id(project_id)
    if getattr(st, "is_triage", False) or getattr(st, "group", None) == "triage":
        log.info(
            "GQL_MUTATION coerced triage state %s -> default for project %s",
            state_id,
            project_id,
        )
        return _default_state_id(project_id)
    return st.id


def _refetch_issue(issue_id):
    return (
        Issue.objects.select_related("project", "state", "workspace", "parent")
        .prefetch_related("assignees", "labels")
        .filter(pk=issue_id)
        .first()
    )


def _create_issue_sync(info, slug, project, issueInput):
    workspace = Workspace.objects.get(slug=slug)
    name = (issueInput.name or "Untitled").strip() or "Untitled"
    state_id = _coerce_state_id(project, issueInput.state)
    priority = issueInput.priority or "none"
    description_html = issueInput.descriptionHtml or "<p></p>"
    description_json = issueInput.description if issueInput.description is not None else {}
    parent_id = issueInput.parent or None
    if parent_id == "":
        parent_id = None

    with transaction.atomic():
        issue = Issue(
            name=name,
            project_id=project,
            priority=priority,
            state_id=state_id,
            description_html=description_html,
            description_json=description_json if isinstance(description_json, dict) else {},
            parent_id=parent_id,
            estimate_point_id=issueInput.estimatePoint or None,
            start_date=issueInput.startDate,
            target_date=issueInput.targetDate,
            workspace=workspace,
            created_by=info.context.user,
            updated_by=info.context.user,
            is_draft=False,
        )
        issue.save()

        assignees = issueInput.assignees or []
        if assignees:
            IssueAssignee.objects.bulk_create(
                [
                    IssueAssignee(
                        assignee_id=user,
                        issue=issue,
                        workspace=workspace,
                        project_id=project,
                        created_by_id=info.context.user.id,
                        updated_by_id=info.context.user.id,
                    )
                    for user in assignees
                ],
                batch_size=10,
                ignore_conflicts=True,
            )

        labels = issueInput.labels or []
        if labels:
            IssueLabel.objects.bulk_create(
                [
                    IssueLabel(
                        label_id=label,
                        issue=issue,
                        project_id=project,
                        workspace=workspace,
                        created_by_id=info.context.user.id,
                        updated_by_id=info.context.user.id,
                    )
                    for label in labels
                ],
                batch_size=10,
                ignore_conflicts=True,
            )

        if issueInput.cycleId:
            CycleIssue.objects.get_or_create(
                cycle_id=issueInput.cycleId,
                issue=issue,
                defaults={
                    "project_id": project,
                    "workspace": workspace,
                    "created_by_id": info.context.user.id,
                    "updated_by_id": info.context.user.id,
                },
            )

        for module_id in issueInput.moduleIds or []:
            ModuleIssue.objects.get_or_create(
                module_id=module_id,
                issue=issue,
                defaults={
                    "project_id": project,
                    "workspace": workspace,
                    "created_by_id": info.context.user.id,
                    "updated_by_id": info.context.user.id,
                },
            )

        issue_id = issue.id

    # Confirm row is visible via default list manager
    visible = Issue.issue_objects.filter(pk=issue_id).exists()
    if not visible:
        # Last-resort: force non-triage state so mobile lists can see it
        fixed = _default_state_id(project)
        if fixed:
            Issue.objects.filter(pk=issue_id).update(state_id=fixed, is_draft=False)
            visible = Issue.issue_objects.filter(pk=issue_id).exists()
        log.warning(
            "GQL_MUTATION createIssueV2 not_listable id=%s forced_state=%s visible=%s",
            issue_id,
            fixed,
            visible,
        )

    # activity outside transaction so a broker blip can't roll back the issue
    try:
        issue_activity.delay(
            type="issue.activity.created",
            origin=getattr(info.context.request, "META", {}).get("HTTP_ORIGIN"),
            epoch=int(timezone.now().timestamp()),
            notification=True,
            project_id=str(project),
            issue_id=str(issue_id),
            actor_id=str(info.context.user.id),
            current_instance=None,
            requested_data=json.dumps(
                {
                    "name": name,
                    "description_html": description_html,
                    "priority": priority,
                    "state_id": str(state_id) if state_id else None,
                    "label_ids": labels,
                    "assignee_ids": assignees,
                },
                default=str,
            ),
        )
    except Exception as e:
        log.warning("createIssueV2 activity failed: %s", e)

    refreshed = _refetch_issue(issue_id)
    # Verify persistence by re-reading name from DB
    db_name = Issue.objects.filter(pk=issue_id).values_list("name", flat=True).first()
    log.info(
        "GQL_MUTATION createIssueV2 ok id=%s project=%s name=%s db_name=%s visible=%s",
        issue_id,
        project,
        name,
        db_name,
        visible,
    )
    return refreshed


def _update_issue_sync(info, id, project, slug, issueInput):
    try:
        # Use base manager so we can still update issues that somehow got triage/archived
        issue = Issue.objects.select_related("project", "state").get(
            id=id, project_id=project, workspace__slug=slug
        )
    except Issue.DoesNotExist:
        raise GraphQLError(
            "Issue not found",
            extensions={"code": "NOT_FOUND", "statusCode": 404},
        )

    try:
        current_issue_activity = convert_issue_properties_to_activity_dict(issue)
    except Exception:
        current_issue_activity = {}

    activity_payload = {}
    workspace = Workspace.objects.get(slug=slug)

    with transaction.atomic():
        if issueInput.name is not None:
            issue.name = issueInput.name
            activity_payload["name"] = issueInput.name
        if issueInput.priority is not None:
            issue.priority = issueInput.priority
            activity_payload["priority"] = issueInput.priority
        if issueInput.state is not None:
            coerced = _coerce_state_id(project, issueInput.state or None)
            issue.state_id = coerced
            activity_payload["state_id"] = str(coerced) if coerced else None
        if issueInput.descriptionHtml is not None:
            issue.description_html = issueInput.descriptionHtml
            activity_payload["description_html"] = issueInput.descriptionHtml
        if issueInput.description is not None:
            # Keep description_json in sync for editors that read JSON not HTML
            if isinstance(issueInput.description, dict):
                issue.description_json = issueInput.description
            activity_payload["description"] = issueInput.description
        if issueInput.parent is not None:
            issue.parent_id = issueInput.parent or None
            activity_payload["parent_id"] = issueInput.parent
        if issueInput.estimatePoint is not None:
            issue.estimate_point_id = issueInput.estimatePoint or None
            activity_payload["estimate_point"] = issueInput.estimatePoint
        if issueInput.startDate is not None:
            issue.start_date = issueInput.startDate
            activity_payload["start_date"] = _date_to_str(issueInput.startDate)
        if issueInput.targetDate is not None:
            issue.target_date = issueInput.targetDate
            activity_payload["target_date"] = _date_to_str(issueInput.targetDate)

        # Never leave issues as draft after a mobile update
        issue.is_draft = False
        issue.updated_by = info.context.user
        issue.save()

        if issueInput.assignees is not None:
            activity_payload["assignee_ids"] = issueInput.assignees
            IssueAssignee.objects.filter(issue=issue).delete()
            if issueInput.assignees:
                IssueAssignee.objects.bulk_create(
                    [
                        IssueAssignee(
                            assignee_id=user,
                            issue=issue,
                            workspace=workspace,
                            project_id=project,
                            created_by_id=info.context.user.id,
                            updated_by_id=info.context.user.id,
                        )
                        for user in issueInput.assignees
                    ],
                    batch_size=10,
                    ignore_conflicts=True,
                )

        if issueInput.labels is not None:
            activity_payload["label_ids"] = issueInput.labels
            IssueLabel.objects.filter(issue=issue).delete()
            if issueInput.labels:
                IssueLabel.objects.bulk_create(
                    [
                        IssueLabel(
                            label_id=label,
                            issue=issue,
                            project_id=project,
                            workspace=workspace,
                            created_by_id=info.context.user.id,
                            updated_by_id=info.context.user.id,
                        )
                        for label in issueInput.labels
                    ],
                    batch_size=10,
                    ignore_conflicts=True,
                )

        if issueInput.cycleId is not None:
            CycleIssue.objects.filter(issue=issue).delete()
            if issueInput.cycleId:
                CycleIssue.objects.create(
                    cycle_id=issueInput.cycleId,
                    issue=issue,
                    project_id=project,
                    workspace=workspace,
                    created_by_id=info.context.user.id,
                    updated_by_id=info.context.user.id,
                )

        if issueInput.moduleIds is not None:
            ModuleIssue.objects.filter(issue=issue).delete()
            for module_id in issueInput.moduleIds:
                ModuleIssue.objects.create(
                    module_id=module_id,
                    issue=issue,
                    project_id=project,
                    workspace=workspace,
                    created_by_id=info.context.user.id,
                    updated_by_id=info.context.user.id,
                )

        issue_id = issue.id

    # Ensure still listable after update
    if not Issue.issue_objects.filter(pk=issue_id).exists():
        fixed = _default_state_id(project)
        if fixed:
            Issue.objects.filter(pk=issue_id).update(state_id=fixed, is_draft=False, archived_at=None)
            log.warning(
                "GQL_MUTATION updateIssueV2 re-listable id=%s state=%s",
                issue_id,
                fixed,
            )

    try:
        issue_activity.delay(
            type="issue.activity.updated",
            origin=getattr(info.context.request, "META", {}).get("HTTP_ORIGIN"),
            epoch=int(timezone.now().timestamp()),
            notification=True,
            project_id=str(project),
            issue_id=str(issue_id),
            actor_id=str(info.context.user.id),
            current_instance=json.dumps(current_issue_activity, default=str),
            requested_data=json.dumps(activity_payload, default=str),
        )
    except Exception as e:
        log.warning("updateIssueV2 activity failed: %s", e)

    refreshed = _refetch_issue(issue_id)
    # Prove DB write for logs
    db_vals = (
        Issue.objects.filter(pk=issue_id)
        .values("name", "priority", "state_id", "description_html")
        .first()
    )
    log.info(
        "GQL_MUTATION updateIssueV2 ok id=%s project=%s fields=%s db=%s",
        issue_id,
        project,
        list(activity_payload.keys()),
        {
            "name": (db_vals or {}).get("name"),
            "priority": (db_vals or {}).get("priority"),
            "state_id": str((db_vals or {}).get("state_id") or ""),
            "html_len": len((db_vals or {}).get("description_html") or ""),
        },
    )
    return refreshed


@strawberry.type
class MobileIssueV2Mutation:
    @strawberry.mutation(
        name="createIssueV2",
        extensions=[
            PermissionExtension(permissions=[ProjectMemberPermission()])
        ],
    )
    async def create_issue_v2(
        self,
        info: Info,
        slug: str,
        project: str,
        issueInput: IssueCreateInputType,
    ) -> IssuesType:
        return await sync_to_async(_create_issue_sync, thread_sensitive=True)(
            info, slug, project, issueInput
        )

    @strawberry.mutation(
        name="updateIssueV2",
        extensions=[
            PermissionExtension(permissions=[ProjectMemberPermission()])
        ],
    )
    async def update_issue_v2(
        self,
        info: Info,
        # Official mobile: mutation IssueMutationV2($id: String!, ...)
        id: str,
        project: str,
        slug: str,
        issueInput: IssueUpdateInputType,
    ) -> IssuesType:
        return await sync_to_async(_update_issue_sync, thread_sensitive=True)(
            info, id, project, slug, issueInput
        )

    # Official mobile: replace issue module memberships
    @strawberry.mutation(
        name="issueModules",
        extensions=[
            PermissionExtension(permissions=[ProjectMemberPermission()])
        ],
    )
    async def issue_modules(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        issue: strawberry.ID,
        modules: List[strawberry.ID],
    ) -> bool:
        def _run():
            workspace = Workspace.objects.get(slug=slug)
            with transaction.atomic():
                ModuleIssue.objects.filter(
                    issue_id=issue, project_id=project
                ).delete()
                for module_id in modules:
                    ModuleIssue.objects.create(
                        module_id=module_id,
                        issue_id=issue,
                        project_id=project,
                        workspace=workspace,
                        created_by_id=info.context.user.id,
                        updated_by_id=info.context.user.id,
                    )
            count = ModuleIssue.objects.filter(
                issue_id=issue, project_id=project
            ).count()
            log.info(
                "GQL_MUTATION issueModules ok issue=%s modules=%s db_count=%s",
                issue,
                len(modules),
                count,
            )
            return True

        return await sync_to_async(_run, thread_sensitive=True)()
