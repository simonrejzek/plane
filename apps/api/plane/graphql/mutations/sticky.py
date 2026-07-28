# Python imports
from typing import Optional
import logging

# Strawberry imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension
from strawberry.exceptions import GraphQLError

# Third-party imports
from asgiref.sync import sync_to_async
from django.db import transaction

# Module imports
from plane.db.models import Sticky, Workspace
from plane.graphql.types.sticky import StickyType, StickyCreateUpdateInputType
from plane.graphql.permissions.workspace import WorkspaceBasePermission

log = logging.getLogger("plane.api.request")


def _apply_sticky_input(sticky: Sticky, data: StickyCreateUpdateInputType) -> None:
    if data.name is not None:
        sticky.name = data.name

    description_html = data.descriptionHtml if data.descriptionHtml is not None else data.description_html
    if description_html is not None:
        sticky.description_html = description_html

    if data.description is not None:
        sticky.description = data.description

    logo_props = data.logoProps if data.logoProps is not None else data.logo_props
    if logo_props is not None:
        sticky.logo_props = logo_props

    if data.color is not None:
        sticky.color = data.color

    background_color = (
        data.backgroundColor
        if data.backgroundColor is not None
        else data.background_color
    )
    if background_color is not None:
        sticky.background_color = background_color

    sort_order = data.sortOrder if data.sortOrder is not None else data.sort_order
    if sort_order is not None:
        sticky.sort_order = sort_order


@strawberry.type
class StickyMutation:
    @strawberry.mutation(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def createSticky(
        self,
        info: Info,
        slug: str,
        # Official mobile uses stickyData (not data)
        stickyData: Optional[StickyCreateUpdateInputType] = None,
        data: Optional[StickyCreateUpdateInputType] = None,
        name: Optional[str] = None,
        descriptionHtml: Optional[str] = None,
        description_html: Optional[str] = None,
        color: Optional[str] = None,
        backgroundColor: Optional[str] = None,
    ) -> StickyType:
        def _run():
            workspace = Workspace.objects.get(slug=slug)
            sticky = Sticky(
                workspace=workspace,
                owner=info.context.user,
                name=name or "",
                description_html=(
                    descriptionHtml
                    if descriptionHtml is not None
                    else (description_html if description_html is not None else "<p></p>")
                ),
                color=color or "",
                background_color=backgroundColor or "",
            )
            payload = stickyData if stickyData is not None else data
            if payload is not None:
                _apply_sticky_input(sticky, payload)
            with transaction.atomic():
                sticky.save()
            # Re-read to prove durability
            saved = Sticky.objects.filter(pk=sticky.id).first()
            log.info(
                "GQL_MUTATION createSticky ok id=%s owner=%s bg=%s",
                sticky.id,
                info.context.user.id,
                getattr(saved, "background_color", None),
            )
            return saved or sticky

        return await sync_to_async(_run, thread_sensitive=True)()

    @strawberry.mutation(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def updateSticky(
        self,
        info: Info,
        slug: str,
        sticky: strawberry.ID,
        stickyData: Optional[StickyCreateUpdateInputType] = None,
        data: Optional[StickyCreateUpdateInputType] = None,
        name: Optional[str] = None,
        descriptionHtml: Optional[str] = None,
        description_html: Optional[str] = None,
        color: Optional[str] = None,
        backgroundColor: Optional[str] = None,
    ) -> StickyType:
        def _run():
            try:
                sticky_obj = Sticky.objects.get(
                    pk=sticky,
                    workspace__slug=slug,
                    owner_id=info.context.user.id,
                )
            except Sticky.DoesNotExist:
                raise GraphQLError(
                    "Sticky not found",
                    extensions={"code": "NOT_FOUND", "statusCode": 404},
                )

            if name is not None:
                sticky_obj.name = name
            if descriptionHtml is not None:
                sticky_obj.description_html = descriptionHtml
            elif description_html is not None:
                sticky_obj.description_html = description_html
            if color is not None:
                sticky_obj.color = color
            if backgroundColor is not None:
                sticky_obj.background_color = backgroundColor
            payload = stickyData if stickyData is not None else data
            if payload is not None:
                _apply_sticky_input(sticky_obj, payload)

            with transaction.atomic():
                sticky_obj.save()
            sticky_obj.refresh_from_db()
            log.info(
                "GQL_MUTATION updateSticky ok id=%s name=%s html_len=%s",
                sticky_obj.id,
                sticky_obj.name,
                len(sticky_obj.description_html or ""),
            )
            return sticky_obj

        return await sync_to_async(_run, thread_sensitive=True)()

    @strawberry.mutation(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def deleteSticky(
        self,
        info: Info,
        slug: str,
        sticky: strawberry.ID,
    ) -> bool:
        def _run():
            deleted, _ = Sticky.objects.filter(
                pk=sticky,
                workspace__slug=slug,
                owner_id=info.context.user.id,
            ).delete()
            log.info(
                "GQL_MUTATION deleteSticky ok id=%s deleted=%s",
                sticky,
                deleted > 0,
            )
            return deleted > 0

        return await sync_to_async(_run, thread_sensitive=True)()
