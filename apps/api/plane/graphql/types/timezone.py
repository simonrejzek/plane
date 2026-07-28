# Strawberry imports
import strawberry


@strawberry.type
class TimezoneListItemType:
    value: str
    query: str
    label: str
