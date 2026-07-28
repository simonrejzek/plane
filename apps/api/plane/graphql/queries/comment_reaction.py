# Python imports
from typing import Optional

# Strawberry imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Third-party
from asgiref.sync import sync_to_async
from django.db.models import Count

# Module imports
from plane.db.models import CommentReaction, Project
from plane.graphql.permissions.project import ProjectBasePermission


@strawberry.type
class WorkItemCommentReactionType:
    reaction: str
    userIds: list[strawberry.ID]


@strawberry.input
class CommentReactionInput:
    reaction: str


async def _reactions_for_comment(
    slug: str, project: str, work_item: str, comment: str
) -> list[WorkItemCommentReactionType]:
    rows = await sync_to_async(list)(
        CommentReaction.objects.filter(
            workspace__slug=slug,
            project_id=project,
            comment_id=comment,
            comment__issue_id=work_item,
        )
        .values("reaction")
        .annotate(count=Count("id"))
    )
    result = []
    for row in rows:
        reaction = row["reaction"]
        user_ids = await sync_to_async(list)(
            CommentReaction.objects.filter(
                workspace__slug=slug,
                project_id=project,
                comment_id=comment,
                reaction=reaction,
            ).values_list("actor_id", flat=True)
        )
        result.append(
            WorkItemCommentReactionType(
                reaction=reaction,
                userIds=[str(uid) for uid in user_ids],
            )
        )
    return result


@strawberry.type
class WorkItemCommentReactionQuery:
    # Official mobile WorkItemCommentReactionQuery
    @strawberry.field(
        name="workItemCommentReactions",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])],
    )
    async def work_item_comment_reactions(
        self,
        info: Info,
        slug: str,
        project: str,
        workItem: str,
        comment: str,
    ) -> list[WorkItemCommentReactionType]:
        return await _reactions_for_comment(slug, project, workItem, comment)


@strawberry.type
class WorkItemCommentReactionMutation:
    @strawberry.mutation(
        name="addWorkItemCommentReaction",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])],
    )
    async def add_work_item_comment_reaction(
        self,
        info: Info,
        slug: str,
        project: str,
        workItem: str,
        comment: str,
        reactionInput: CommentReactionInput,
    ) -> WorkItemCommentReactionType:
        project_obj = await sync_to_async(Project.objects.get)(pk=project)
        await sync_to_async(CommentReaction.objects.get_or_create)(
            workspace_id=project_obj.workspace_id,
            project_id=project,
            comment_id=comment,
            actor=info.context.user,
            reaction=reactionInput.reaction,
            defaults={
                "created_by": info.context.user,
                "updated_by": info.context.user,
            },
        )
        reactions = await _reactions_for_comment(
            slug, project, workItem, comment
        )
        for r in reactions:
            if r.reaction == reactionInput.reaction:
                return r
        return WorkItemCommentReactionType(
            reaction=reactionInput.reaction,
            userIds=[str(info.context.user.id)],
        )

    @strawberry.mutation(
        name="removeWorkItemCommentReaction",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])],
    )
    async def remove_work_item_comment_reaction(
        self,
        info: Info,
        slug: str,
        project: str,
        workItem: str,
        comment: str,
        reactionInput: CommentReactionInput,
    ) -> WorkItemCommentReactionType:
        await sync_to_async(
            CommentReaction.objects.filter(
                workspace__slug=slug,
                project_id=project,
                comment_id=comment,
                actor=info.context.user,
                reaction=reactionInput.reaction,
            ).delete
        )()
        reactions = await _reactions_for_comment(
            slug, project, workItem, comment
        )
        for r in reactions:
            if r.reaction == reactionInput.reaction:
                return r
        return WorkItemCommentReactionType(
            reaction=reactionInput.reaction, userIds=[]
        )
