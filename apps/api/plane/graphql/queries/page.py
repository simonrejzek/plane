# Python imports
from typing import Optional

# Third-Party Imports
import strawberry
from asgiref.sync import sync_to_async

# Strawberry Imports
from strawberry.types import Info
from strawberry.permission import PermissionExtension
from strawberry.exceptions import GraphQLError

# Django Imports
from django.db.models import Exists, OuterRef, Q

# Module Imports
from plane.graphql.types.page import PageType
from plane.db.models import UserFavorite, Page
from plane.graphql.permissions.workspace import WorkspaceBasePermission
from plane.graphql.types.paginator import PaginatorResponse
from plane.graphql.utils.paginator import paginate
from plane.graphql.bgtasks.recent_visited_task import recent_visited_task


# workspace level queries
@strawberry.type
class WorkspacePageQuery:
    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def workspacePage(
        self,
        info: Info,
        slug: str,
        page: strawberry.ID,
    ) -> PageType:
        user = info.context.user

        # Build subquery for UserFavorite
        subquery = UserFavorite.objects.filter(
            user=user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=slug,
        )

        # Build the query
        query = (
            Page.objects.filter(workspace__slug=slug, pk=page)
            .filter(parent__isnull=True)
            .filter(Q(owned_by=user) | Q(access=0))
            .select_related("workspace", "owned_by")
            .prefetch_related("projects")
            .annotate(is_favorite=Exists(subquery))
        )

        # Fetch the page asynchronously
        try:
            page_result = await sync_to_async(
                query.get, thread_sensitive=True
            )()
        except Exception:
            message = "Page not found."
            error_extensions = {
                "code": "PAGE_NOT_FOUND",
                "statusCode": 404,
            }
            raise GraphQLError(message, extensions=error_extensions)

        # Background task to update recent visited project
        # user_id = info.context.user.id
        # recent_visited_task.delay(
        #     slug=slug,
        #     project_id=None,
        #     user_id=user_id,
        #     entity_name="page",
        #     entity_identifier=page,
        # )

        return page_result

    # Official mobile workspace pages list (plural)
    @strawberry.field(
        name="workspacePages",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def workspace_pages(
        self,
        info: Info,
        slug: str,
        cursor: Optional[str] = None,
        type: Optional[str] = None,
    ) -> PaginatorResponse[PageType]:
        user = info.context.user
        subquery = UserFavorite.objects.filter(
            user=user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=slug,
        )
        query = (
            Page.objects.filter(workspace__slug=slug)
            .filter(parent__isnull=True)
            .filter(Q(owned_by=user) | Q(access=0))
            .select_related("workspace", "owned_by")
            .prefetch_related("projects")
            .annotate(is_favorite=Exists(subquery))
            .order_by("-updated_at")
        )

        if type == "archived":
            query = query.filter(archived_at__isnull=False)
        else:
            query = query.filter(archived_at__isnull=True)
            if type == "private":
                query = query.filter(owned_by=user, access=Page.PRIVATE_ACCESS)
            elif type == "public":
                query = query.filter(access=Page.PUBLIC_ACCESS)
            elif type == "shared":
                # CE has no workspace-page sharing relation. Returning an
                # empty category is safer than exposing public pages as shared.
                query = query.none()

        pages = await sync_to_async(list)(query)
        return paginate(results_object=pages, cursor=cursor)


# project level queries
@strawberry.type
class UserPageQuery:
    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def userPages(
        self,
        info: Info,
        slug: str,
        cursor: Optional[str] = None,
    ) -> PaginatorResponse[PageType]:
        subquery = UserFavorite.objects.filter(
            user=info.context.user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=slug,
        )
        pages = await sync_to_async(list)(
            Page.objects.filter(workspace__slug=slug)
            .filter(
                projects__project_projectmember__member=info.context.user,
                projects__project_projectmember__is_active=True,
                projects__archived_at__isnull=True,
            )
            .filter(projects__isnull=False)
            .filter(parent__isnull=True)
            .filter(Q(owned_by=info.context.user))
            .select_related("workspace", "owned_by")
            .prefetch_related("projects")
            .annotate(is_favorite=Exists(subquery))
        )

        return paginate(results_object=pages, cursor=cursor)


@strawberry.type
class PageQuery:
    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def pages(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        cursor: Optional[str] = None,
    ) -> PaginatorResponse[PageType]:
        subquery = UserFavorite.objects.filter(
            user=info.context.user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=slug,
        )
        pages = await sync_to_async(list)(
            Page.objects.filter(workspace__slug=slug, projects__id=project)
            .filter(
                projects__project_projectmember__member=info.context.user,
                projects__project_projectmember__is_active=True,
                projects__archived_at__isnull=True,
            )
            .filter(parent__isnull=True)
            .filter(Q(owned_by=info.context.user) | Q(access=0))
            .select_related("workspace", "owned_by")
            .prefetch_related("projects")
            .annotate(is_favorite=Exists(subquery))
        )

        return paginate(results_object=pages, cursor=cursor)

    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def page(
        self,
        info: Info,
        slug: str,
        project: strawberry.ID,
        page: strawberry.ID,
    ) -> PageType:
        user = info.context.user

        # Build subquery for UserFavorite
        subquery = UserFavorite.objects.filter(
            user=user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=slug,
        )

        # Build the query
        query = (
            Page.objects.filter(
                workspace__slug=slug, projects__id=project, pk=page
            )
            .filter(
                projects__project_projectmember__member=user,
                projects__project_projectmember__is_active=True,
                projects__archived_at__isnull=True,
            )
            .filter(parent__isnull=True)
            .filter(Q(owned_by=user) | Q(access=0))
            .select_related("workspace", "owned_by")
            .prefetch_related("projects")
            .annotate(is_favorite=Exists(subquery))
        )

        # Fetch the page asynchronously
        try:
            page_result = await sync_to_async(
                query.get, thread_sensitive=True
            )()
        except Exception:
            message = "Page not found."
            error_extensions = {
                "code": "PAGE_NOT_FOUND",
                "statusCode": 404,
            }
            raise GraphQLError(message, extensions=error_extensions)

        # Background task to update recent visited project
        user_id = info.context.user.id
        recent_visited_task.delay(
            slug=slug,
            project_id=project,
            user_id=user_id,
            entity_name="page",
            entity_identifier=page,
        )

        return page_result
