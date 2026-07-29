# Mobile home GraphQL schema-compat for official Flutter app
from typing import Optional, List
from asgiref.sync import sync_to_async

import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

from plane.db.models import Notification, Workspace
from plane.graphql.permissions.workspace import (
    IsAuthenticated,
    WorkspaceBasePermission,
)


@strawberry.type
class NotificationWorkspaceCountType:
    id: strawberry.ID
    slug: str
    unread: int


@strawberry.type
class NotificationCountType:
    unread: int
    workspaces: List[NotificationWorkspaceCountType]


@strawberry.type
class CatchUpWorkItemType:
    id: strawberry.ID
    name: str
    projectIdentifier: Optional[str] = None
    sequenceId: Optional[int] = None
    intakeId: Optional[strawberry.ID] = None


@strawberry.type
class CatchUpUnreadType:
    id: strawberry.ID
    type: Optional[str] = None


@strawberry.type
class CatchUpType:
    projectId: Optional[strawberry.ID] = None
    id: strawberry.ID
    type: Optional[str] = None
    count: int = 0
    workItem: Optional[CatchUpWorkItemType] = None
    firstUnread: Optional[CatchUpUnreadType] = None
    lastUnread: Optional[CatchUpUnreadType] = None


@strawberry.type
class MobileHomeQuery:
    """Fields the App Store client requests on home load that CE does not implement."""

    @strawberry.field(
        name="notificationCount",
        extensions=[PermissionExtension(permissions=[IsAuthenticated()])],
    )
    async def notification_count(self, info: Info) -> NotificationCountType:
        user = info.context.user
        if user is None:
            return NotificationCountType(unread=0, workspaces=[])

        def _run():
            base = Notification.objects.filter(
                receiver_id=user.id,
                read_at__isnull=True,
                archived_at__isnull=True,
            )
            total = base.count()
            # Per-workspace unread for workspaces the user belongs to
            ws_rows = []
            for ws in Workspace.objects.filter(
                workspace_member__member_id=user.id,
                workspace_member__is_active=True,
            ).distinct():
                unread = base.filter(workspace_id=ws.id).count()
                ws_rows.append(
                    NotificationWorkspaceCountType(
                        id=ws.id, slug=ws.slug, unread=unread
                    )
                )
            return NotificationCountType(unread=total, workspaces=ws_rows)

        return await sync_to_async(_run, thread_sensitive=True)()

    @strawberry.field(
        name="catchUps",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def catch_ups(self, info: Info, slug: str) -> List[CatchUpType]:
        # CE has no Catch-Up product; return empty so mobile home can paint.
        return []
