# Third-Party Imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Module Imports
from plane.graphql.types.license import WorkspaceLicenseType
from plane.graphql.permissions.workspace import WorkspaceBasePermission


@strawberry.type
class WorkspaceLicenseQuery:
    @strawberry.field(
        extensions=[
            PermissionExtension(permissions=[WorkspaceBasePermission()])
        ]
    )
    async def workspaceLicense(
        self, info: Info, slug: str
    ) -> WorkspaceLicenseType:
        # Contract / self-hosted: never block on free-seat limits
        return WorkspaceLicenseType(is_free_member_count_exceeded=False)
