# Python imports
from typing import Optional

# Strawberry
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Third-party
from asgiref.sync import sync_to_async
from django.db.models import Q, Exists, OuterRef

# Module imports
from plane.db.models import Page, UserFavorite
from plane.graphql.types.page import PageType
from plane.graphql.permissions.workspace import WorkspaceBasePermission
from plane.graphql.permissions.project import ProjectBasePermission


def _page_qs(slug: str, user):
    subquery = UserFavorite.objects.filter(
        user=user,
        entity_type="page",
        entity_identifier=OuterRef("pk"),
        workspace__slug=slug,
    )
    return (
        Page.objects.filter(workspace__slug=slug)
        .filter(Q(owned_by=user) | Q(access=0))
        .select_related("workspace", "owned_by")
        .prefetch_related("projects")
        .annotate(is_favorite=Exists(subquery))
    )


@strawberry.type
class MobileNestedPagesQuery:
    @strawberry.field(
        name="nestedChildPages",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])],
    )
    async def nested_child_pages(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        page: strawberry.ID,
    ) -> list[PageType]:
        pages = await sync_to_async(list)(
            _page_qs(slug, info.context.user).filter(
                parent_id=page, projects__id=project
            )
        )
        return pages

    @strawberry.field(
        name="nestedParentPages",
        extensions=[PermissionExtension(permissions=[ProjectBasePermission()])],
    )
    async def nested_parent_pages(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        page: strawberry.ID,
    ) -> list[PageType]:
        # Walk parents chain
        result = []
        current = await sync_to_async(
            Page.objects.filter(pk=page, workspace__slug=slug).first
        )()
        while current and current.parent_id:
            parent = await sync_to_async(
                Page.objects.filter(pk=current.parent_id).first
            )()
            if not parent:
                break
            result.append(parent)
            current = parent
        return result

    @strawberry.field(
        name="workspaceNestedChildPages",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def workspace_nested_child_pages(
        self,
        info: Info,
        slug: str,
        page: strawberry.ID,
    ) -> list[PageType]:
        pages = await sync_to_async(list)(
            _page_qs(slug, info.context.user).filter(parent_id=page)
        )
        return pages

    @strawberry.field(
        name="workspaceNestedParentPages",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def workspace_nested_parent_pages(
        self,
        info: Info,
        slug: str,
        page: strawberry.ID,
    ) -> list[PageType]:
        result = []
        current = await sync_to_async(
            Page.objects.filter(pk=page, workspace__slug=slug).first
        )()
        while current and current.parent_id:
            parent = await sync_to_async(
                Page.objects.filter(pk=current.parent_id).first
            )()
            if not parent:
                break
            result.append(parent)
            current = parent
        return result


@strawberry.type
class WorkspaceNestedChildArchivePagesResult:
    """Mobile selects workspaceNestedChildArchivePages { __typename } - must be Object, not Boolean."""

    success: bool = True
    page: Optional[strawberry.ID] = None


@strawberry.type
class MobileNestedPagesMutation:
    @strawberry.mutation(
        name="workspaceNestedChildArchivePages",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def workspace_nested_child_archive_pages(
        self,
        info: Info,
        slug: str,
        page: strawberry.ID,
    ) -> WorkspaceNestedChildArchivePagesResult:
        from django.utils import timezone

        await sync_to_async(
            Page.objects.filter(
                workspace__slug=slug, parent_id=page
            ).update
        )(archived_at=timezone.now().date())
        return WorkspaceNestedChildArchivePagesResult(success=True, page=page)


@strawberry.type
class InitiativesCountType:
    totalCount: int = 0
    totalCountByLead: Optional[int] = 0


@strawberry.type
class InitiativesCountQuery:
    # EE initiatives not in CE - return zeros so mobile does not fail
    @strawberry.field(
        name="initiativesCount",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def initiatives_count(
        self, info: Info, slug: str
    ) -> InitiativesCountType:
        return InitiativesCountType(totalCount=0, totalCountByLead=0)
