# Python imports
from typing import Optional

# Strawberry imports
import strawberry
from strawberry.types import Info
from strawberry.permission import PermissionExtension
from strawberry.scalars import JSON

# Third-party imports
from asgiref.sync import sync_to_async

# Module imports
from plane.db.models import Profile, WorkspaceMember
from plane.graphql.permissions.workspace import IsAuthenticated
from plane.graphql.types.users import ProfileType, UserType


@strawberry.type
class ProfileMutation:
    @strawberry.mutation(
        extensions=[PermissionExtension(permissions=[IsAuthenticated()])]
    )
    async def update_last_workspace(
        self, info: Info, workspace: strawberry.ID
    ) -> bool:
        profile = await sync_to_async(Profile.objects.get)(
            user=info.context.user
        )

        # Wrap the synchronous call to `exists()` with `sync_to_async`
        workspace_member_exists = await sync_to_async(
            WorkspaceMember.objects.filter(
                workspace=workspace, member=info.context.user
            ).exists
        )()

        if not workspace_member_exists:
            return False

        profile.last_workspace_id = workspace
        await sync_to_async(profile.save)()
        return True

    # Official mobile settings / first-run timezone
    @strawberry.mutation(
        name="updateProfile",
        extensions=[PermissionExtension(permissions=[IsAuthenticated()])],
    )
    async def update_profile(
        self,
        info: Info,
        mobileTimezoneAutoSet: Optional[bool] = None,
        mobile_timezone_auto_set: Optional[bool] = None,
        language: Optional[str] = None,
        theme: Optional[JSON] = None,
        lastWorkspaceId: Optional[strawberry.ID] = None,
        last_workspace_id: Optional[strawberry.ID] = None,
        isOnboarded: Optional[bool] = None,
        is_onboarded: Optional[bool] = None,
        isMobileOnboarded: Optional[bool] = None,
        is_mobile_onboarded: Optional[bool] = None,
        userTimezone: Optional[str] = None,
        user_timezone: Optional[str] = None,
        firstName: Optional[str] = None,
        first_name: Optional[str] = None,
        lastName: Optional[str] = None,
        last_name: Optional[str] = None,
        displayName: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> ProfileType:
        profile = await sync_to_async(Profile.objects.get)(
            user=info.context.user
        )
        user = info.context.user
        profile_fields = []
        user_fields = []

        auto_set = (
            mobileTimezoneAutoSet
            if mobileTimezoneAutoSet is not None
            else mobile_timezone_auto_set
        )
        if auto_set is not None:
            profile.mobile_timezone_auto_set = auto_set
            profile_fields.append("mobile_timezone_auto_set")

        if language is not None:
            profile.language = language
            profile_fields.append("language")

        if theme is not None:
            profile.theme = theme
            profile_fields.append("theme")

        lw = (
            lastWorkspaceId
            if lastWorkspaceId is not None
            else last_workspace_id
        )
        if lw is not None:
            profile.last_workspace_id = lw
            profile_fields.append("last_workspace_id")

        onboarded = isOnboarded if isOnboarded is not None else is_onboarded
        if onboarded is not None:
            profile.is_onboarded = onboarded
            profile_fields.append("is_onboarded")

        mobile_onboarded = (
            isMobileOnboarded
            if isMobileOnboarded is not None
            else is_mobile_onboarded
        )
        if mobile_onboarded is not None:
            profile.is_mobile_onboarded = mobile_onboarded
            profile_fields.append("is_mobile_onboarded")

        tz = userTimezone if userTimezone is not None else user_timezone
        if tz is not None:
            user.user_timezone = tz
            user_fields.append("user_timezone")

        fn = firstName if firstName is not None else first_name
        if fn is not None:
            user.first_name = fn
            user_fields.append("first_name")

        ln = lastName if lastName is not None else last_name
        if ln is not None:
            user.last_name = ln
            user_fields.append("last_name")

        dn = displayName if displayName is not None else display_name
        if dn is not None:
            user.display_name = dn
            user_fields.append("display_name")

        if user_fields:
            await sync_to_async(user.save)(update_fields=user_fields)
        if profile_fields:
            await sync_to_async(profile.save)(update_fields=profile_fields)

        return await sync_to_async(Profile.objects.select_related("user").get)(
            id=profile.id
        )

    # Official mobile profile user fields
    @strawberry.mutation(
        name="updateUser",
        extensions=[PermissionExtension(permissions=[IsAuthenticated()])],
    )
    async def update_user(
        self,
        info: Info,
        firstName: Optional[str] = None,
        first_name: Optional[str] = None,
        lastName: Optional[str] = None,
        last_name: Optional[str] = None,
        displayName: Optional[str] = None,
        display_name: Optional[str] = None,
        userTimezone: Optional[str] = None,
        user_timezone: Optional[str] = None,
        avatar: Optional[str] = None,
        coverImage: Optional[str] = None,
        cover_image: Optional[str] = None,
    ) -> UserType:
        user = info.context.user
        fields = []
        fn = firstName if firstName is not None else first_name
        if fn is not None:
            user.first_name = fn
            fields.append("first_name")
        ln = lastName if lastName is not None else last_name
        if ln is not None:
            user.last_name = ln
            fields.append("last_name")
        dn = displayName if displayName is not None else display_name
        if dn is not None:
            user.display_name = dn
            fields.append("display_name")
        tz = userTimezone if userTimezone is not None else user_timezone
        if tz is not None:
            user.user_timezone = tz
            fields.append("user_timezone")
        if avatar is not None:
            user.avatar = avatar
            fields.append("avatar")
        cover = coverImage if coverImage is not None else cover_image
        if cover is not None:
            user.cover_image = cover
            fields.append("cover_image")
        if fields:
            await sync_to_async(user.save)(update_fields=fields)
        return user
