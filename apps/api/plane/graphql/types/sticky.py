# Python imports
from typing import Optional
from datetime import datetime

# Strawberry imports
import strawberry
import strawberry_django
from strawberry.scalars import JSON

# Module imports
from plane.db.models import Sticky


@strawberry_django.type(Sticky)
class StickyType:
    id: strawberry.ID
    name: Optional[str]
    description: Optional[JSON]
    description_html: Optional[str]
    description_stripped: Optional[str]
    logo_props: Optional[JSON]
    color: Optional[str]
    background_color: Optional[str]
    sort_order: float
    workspace: strawberry.ID
    owner: strawberry.ID
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    def workspace(self) -> strawberry.ID:
        return self.workspace_id

    @strawberry.field
    def owner(self) -> strawberry.ID:
        return self.owner_id

    @strawberry.field(name="descriptionBinary")
    def description_binary_field(self) -> Optional[str]:
        # BinaryField breaks GraphQL serialization for stickies list
        return None


@strawberry.input
class StickyCreateUpdateInputType:
    name: Optional[str] = None
    description: Optional[JSON] = None
    descriptionHtml: Optional[str] = None
    description_html: Optional[str] = None
    logoProps: Optional[JSON] = None
    logo_props: Optional[JSON] = None
    color: Optional[str] = None
    backgroundColor: Optional[str] = None
    background_color: Optional[str] = None
    sortOrder: Optional[float] = None
    sort_order: Optional[float] = None
