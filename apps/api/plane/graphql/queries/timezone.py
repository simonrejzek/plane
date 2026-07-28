# Third-Party Imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension

# Module Imports
from plane.graphql.types.timezone import TimezoneListItemType
from plane.graphql.permissions.workspace import IsAuthenticated

# Prefer pytz common zones (already a Plane dependency via User model)
try:
    import pytz

    _TIMEZONES = list(pytz.common_timezones)
except Exception:  # pragma: no cover
    _TIMEZONES = ["UTC", "America/New_York", "Europe/London", "Europe/Berlin"]


@strawberry.type
class TimezoneListQuery:
    @strawberry.field(
        extensions=[PermissionExtension(permissions=[IsAuthenticated()])]
    )
    async def timezoneList(self, info: Info) -> list[TimezoneListItemType]:
        items = []
        for tz in _TIMEZONES:
            items.append(
                TimezoneListItemType(
                    value=tz,
                    query=tz.lower().replace("_", " ").replace("/", " "),
                    label=tz.replace("_", " "),
                )
            )
        return items
