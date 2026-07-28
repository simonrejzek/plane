# Python imports
from typing import Optional

# Strawberry imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Third-party imports
from asgiref.sync import sync_to_async


# Module imports
from plane.graphql.permissions.project import ProjectBasePermission
from plane.db.models import Workspace, IssueComment


@strawberry.type
class IssueCommentResultType:
    id: strawberry.ID


@strawberry.type
class IssueCommentMutation:
    # adding issue comment
    @strawberry.mutation(
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])]
    )
    async def addIssueComment(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        issue: strawberry.ID,
        comment_html: str = "",
        commentHtml: Optional[str] = None,
    ) -> IssueCommentResultType:
        workspace_details = await sync_to_async(
            Workspace.objects.filter(slug=slug).first
        )()
        if not workspace_details:
            raise Exception("Workspace not found")

        html = commentHtml if commentHtml is not None else comment_html
        comment = await sync_to_async(
            lambda: IssueComment.objects.create(
                workspace_id=workspace_details.id,
                project_id=project,
                issue_id=issue,
                comment_html=html,
                actor=info.context.user,
                created_by=info.context.user,
                updated_by=info.context.user,
            )
        )()

        return IssueCommentResultType(id=comment.id)

    # Official mobile: addIssueCommentV2(...) { id }
    # IMPORTANT: do not call self.addIssueComment — strawberry may bind self as None
    @strawberry.mutation(
        name="addIssueCommentV2",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])]
    )
    async def add_issue_comment_v2(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        issue: strawberry.ID,
        comment_html: str = "",
        commentHtml: Optional[str] = None,
    ) -> IssueCommentResultType:
        workspace_details = await sync_to_async(
            Workspace.objects.filter(slug=slug).first
        )()
        if not workspace_details:
            raise Exception("Workspace not found")

        html = commentHtml if commentHtml is not None else comment_html
        comment = await sync_to_async(
            lambda: IssueComment.objects.create(
                workspace_id=workspace_details.id,
                project_id=project,
                issue_id=issue,
                comment_html=html,
                actor=info.context.user,
                created_by=info.context.user,
                updated_by=info.context.user,
            )
        )()
        return IssueCommentResultType(id=comment.id)
