# Third-Party Imports
from typing import Optional

import strawberry
from asgiref.sync import sync_to_async
from django.conf import settings
from strawberry.types import Info

# Module Imports
from plane.graphql.types.version_check import VersionCheckType


@sync_to_async
def get_version_check(platform: str, is_internal: Optional[bool] = False):
    """
    Mobile version gate. Without a feature-flag server we allow any version.
    """
    base = getattr(settings, "FEATURE_FLAG_SERVER_BASE_URL", "") or ""
    token = getattr(settings, "FEATURE_FLAG_SERVER_AUTH_TOKEN", "") or ""
    if base and token:
        try:
            import requests

            url = f"{base}/api/mobile-version/"
            headers = {
                "content-type": "application/json",
                "x-api-key": token,
            }
            response = requests.post(
                url,
                json={"platform": platform, "is_internal": is_internal},
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            pass

    return {
        "version": "999.0.0",
        "min_supported_version": "0.0.0",
        "url": "",
        "force_update": False,
    }


@strawberry.type
class VersionCheckQuery:
    @strawberry.field
    async def version_check(
        self, info: Info, platform: str, is_internal: Optional[bool] = False
    ) -> VersionCheckType:
        version_details = await get_version_check(platform, is_internal)
        return VersionCheckType(
            version=version_details["version"],
            min_supported_version=version_details["min_supported_version"],
            url=version_details["url"],
            force_update=version_details["force_update"],
        )
