# Python imports
from typing import Optional
import logging
import time

# Third-Party Imports
import strawberry
from asgiref.sync import sync_to_async

# Strawberry Imports
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Module Imports
from plane.db.models import Sticky
from plane.graphql.types.sticky import StickyType
from plane.graphql.permissions.workspace import WorkspaceBasePermission
from plane.graphql.types.paginator import PaginatorResponse
from plane.graphql.utils.paginator import Cursor, PAGINATOR_MAX_LIMIT

log = logging.getLogger("plane.api.request")


@strawberry.type
class StickyQuery:
    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def stickies(
        self,
        info: Info,
        slug: str,
        cursor: Optional[str] = None,
        query: Optional[str] = None,
    ) -> PaginatorResponse[StickyType]:
        """Workspace stickies for the current user — DB-sliced for fast first paint."""

        def _run():
            t0 = time.monotonic()
            user_id = info.context.user.id
            qs = Sticky.objects.filter(
                workspace__slug=slug,
                owner_id=user_id,
            ).order_by("-sort_order", "-created_at")

            if query:
                qs = qs.filter(description_stripped__icontains=query)

            # Count without loading binary/html blobs
            total_results = qs.count()
            cursor_object = Cursor.from_string(cursor)
            page_size = min(cursor_object.page_size, PAGINATOR_MAX_LIMIT)
            start_index = 0
            if cursor_object.current_page > 0:
                start_index = cursor_object.current_page * page_size

            # Only fetch the page we need; defer heavy binary field
            page_qs = (
                qs.defer("description_binary")
                .only(
                    "id",
                    "name",
                    "description",
                    "description_html",
                    "description_stripped",
                    "logo_props",
                    "color",
                    "background_color",
                    "sort_order",
                    "workspace_id",
                    "owner_id",
                    "created_at",
                    "updated_at",
                )[start_index : start_index + page_size]
            )
            paginated_data = list(page_qs)

            prev_cursor = f"{page_size}:{cursor_object.current_page - 1}:0"
            cur = f"{page_size}:{cursor_object.current_page}:0"
            end_index = start_index + len(paginated_data)
            next_cursor = None
            if end_index < total_results:
                next_cursor = f"{page_size}:{cursor_object.current_page + 1}:0"

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log.info(
                "GQL_STICKIES user=%s slug=%s count=%s total=%s ms=%s",
                user_id,
                slug,
                len(paginated_data),
                total_results,
                elapsed_ms,
            )

            return PaginatorResponse(
                prev_cursor=prev_cursor,
                cursor=cur,
                next_cursor=next_cursor,
                prev_page_results=cursor_object.current_page > 0,
                next_page_results=bool(next_cursor),
                count=len(paginated_data),
                total_count=total_results,
                results=paginated_data,
            )

        return await sync_to_async(_run, thread_sensitive=True)()

    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def sticky(
        self,
        info: Info,
        slug: str,
        sticky: strawberry.ID,
    ) -> Optional[StickyType]:
        return await sync_to_async(
            Sticky.objects.filter(
                workspace__slug=slug,
                owner_id=info.context.user.id,
                pk=sticky,
            )
            .defer("description_binary")
            .first
        )()
