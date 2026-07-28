# Strawberry imports
import strawberry


@strawberry.type
class WorkspaceLicenseType:
    """Minimal license payload for official mobile WorkspaceLicenseQuery."""

    is_free_member_count_exceeded: bool
