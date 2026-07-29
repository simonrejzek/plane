# Commercial mobile WorkspaceFeatureQuery — product surface gates (wiki / PI / initiatives)
from typing import Optional
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

from plane.graphql.permissions.workspace import WorkspaceBasePermission


@strawberry.type
class WorkspaceFeaturesType:
    """Mirrors commercial workspace features used by official mobile home rail."""

    is_initiative_enabled: bool = False
    is_teams_enabled: bool = False
    is_customer_enabled: bool = False
    is_wiki_enabled: bool = True
    is_pi_enabled: bool = True
    is_release_enabled: bool = False
    is_project_grouping_enabled: bool = False
    is_milestones_enabled: bool = False
    is_work_item_types_enabled: bool = False
    is_workitem_hierarchy_enabled: bool = False
    is_state_duration_enabled: bool = False


@strawberry.type
class WorkspaceFeaturesQuery:
    @strawberry.field(
        name="workspaceFeatures",
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ],
    )
    async def workspace_features(
        self, info: Info, slug: str
    ) -> Optional[WorkspaceFeaturesType]:
        # Contract self-host: expose Wiki + Pilot AI product surface to mobile.
        return WorkspaceFeaturesType(
            is_initiative_enabled=False,
            is_teams_enabled=False,
            is_customer_enabled=False,
            is_wiki_enabled=True,
            is_pi_enabled=True,
            is_release_enabled=False,
            is_project_grouping_enabled=False,
            is_milestones_enabled=False,
            is_work_item_types_enabled=False,
            is_workitem_hierarchy_enabled=False,
            is_state_duration_enabled=False,
        )
