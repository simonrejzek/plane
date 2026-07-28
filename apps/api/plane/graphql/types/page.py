# Python imports
from typing import Optional
from datetime import date, datetime

# Third-party library imports
from asgiref.sync import sync_to_async

# Strawberry imports
import strawberry
import strawberry_django
from strawberry.scalars import JSON

# Module imports
from plane.db.models import Page
from plane.graphql.types.project import ProjectLiteType


@strawberry_django.type(Page)
class PageType:
    id: strawberry.ID
    parent: Optional[strawberry.ID]
    name: str
    description_stripped: Optional[str]
    description_binary: Optional[str]
    workspace: strawberry.ID
    project: strawberry.ID
    owned_by: strawberry.ID
    access: int
    color: Optional[str]
    archived_at: Optional[date]
    is_locked: bool
    view_props: JSON
    logo_props: JSON
    is_global: bool
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
    projects: list[strawberry.ID]
    # teams: list[strawberry.ID]
    # labels: list[strawberry.ID]

    @strawberry.field
    def workspace(self) -> int:
        return self.workspace_id

    # @strawberry.field
    def project(self) -> int:
        return self.project_id

    @strawberry.field
    def owned_by(self) -> int:
        return self.owned_by_id

    @strawberry.field
    def parent(self) -> int:
        return self.parent_id

    @strawberry.field
    async def projects(self) -> list[strawberry.ID]:
        projects = await sync_to_async(list)(self.projects.all())
        return [project.id for project in projects]

    # CE Page model uses description_json (not description)
    @strawberry.field
    def description(self) -> Optional[JSON]:
        value = self.__dict__.get("description_json")
        if value is None:
            value = self.__dict__.get("description")
        return value if value is not None else {}

    @strawberry.field(name="descriptionHtml")
    def description_html_field(self) -> Optional[str]:
        return self.__dict__.get("description_html") or "<p></p>"

    @strawberry.field(name="deletedAt")
    def deleted_at_field(self) -> Optional[datetime]:
        return self.__dict__.get("deleted_at")

    @strawberry.field(name="isDescriptionEmpty")
    def is_description_empty(self) -> bool:
        html = (self.__dict__.get("description_html") or "").strip()
        if not html or html in ("<p></p>", "<p><br></p>", "<p><br/></p>"):
            return True
        # strip simple tags for emptiness check
        text = (
            html.replace("<p>", "")
            .replace("</p>", "")
            .replace("<br>", "")
            .replace("<br/>", "")
            .replace("<br />", "")
            .replace("&nbsp;", "")
            .strip()
        )
        return len(text) == 0

    # @strawberry.field
    # async def labels(self) -> list[strawberry.ID]:
    #     labels = await sync_to_async(list)(self.labels.all())
    #     return [label.id for label in labels]


@strawberry_django.type(Page)
class PageLiteType:
    id: strawberry.ID
    name: str

    @strawberry.field
    def projects(self) -> list[ProjectLiteType]:
        return self.projects.all()
