from typing import Any, Dict, Optional, Tuple
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

# Third-Party Imports
from asgiref.sync import sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

# Strawberry imports
from strawberry.django.views import AsyncGraphQLView
from strawberry.types import ExecutionResult
from strawberry.types.execution import ExecutionContext

log = logging.getLogger("plane.api.request")


def _extract_bearer_token(request) -> Optional[str]:
    """Pull a JWT from any header/cookie the official mobile app might send."""
    candidates = []
    headers = getattr(request, "headers", None)
    if headers is not None:
        for key in (
            "Authorization",
            "authorization",
            "X-Access-Token",
            "x-access-token",
            "X-Auth-Token",
            "x-auth-token",
        ):
            try:
                val = headers.get(key)
            except Exception:
                val = None
            if val:
                candidates.append(str(val))

    meta = getattr(request, "META", {}) or {}
    for key in (
        "HTTP_AUTHORIZATION",
        "HTTP_X_ACCESS_TOKEN",
        "HTTP_X_AUTH_TOKEN",
    ):
        val = meta.get(key)
        if val:
            if isinstance(val, (bytes, bytearray)):
                val = val.decode("latin-1", "ignore")
            candidates.append(str(val))

    cookies = getattr(request, "COOKIES", {}) or {}
    for key in ("access_token", "accessToken", "jwt", "token"):
        val = cookies.get(key)
        if val:
            candidates.append(str(val))

    for auth_header in candidates:
        parts = auth_header.split()
        if len(parts) >= 2 and parts[0].lower() == "bearer":
            token = parts[1].strip().strip('"').strip("'")
        else:
            token = parts[-1].strip().strip('"').strip("'") if parts else ""
        if token and token.lower() not in ("null", "undefined", "none", "bearer", ""):
            return token
    return None


def _normalize_auth_meta(request) -> Optional[str]:
    """Ensure META HTTP_AUTHORIZATION is set for DRF JWTAuthentication."""
    token = _extract_bearer_token(request)
    if token:
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return token


@sync_to_async
def resolve_user_from_token(raw_token: str):
    """
    Accept access OR refresh tokens. Mobile GraphQL sometimes sends the
    refresh JWT as Authorization Bearer after a refresh cycle.

    Runs fully in a worker thread (DB + JWT crypto are sync).
    """
    from plane.db.models import User

    last_err = None
    for TokenCls, label in ((AccessToken, "access"), (RefreshToken, "refresh")):
        try:
            token = TokenCls(raw_token)
            user_id = token.payload.get("user_id")
            if not user_id:
                last_err = f"{label}: no user_id claim"
                continue
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user is None:
                last_err = f"{label}: user {user_id} not found/active"
                continue
            return user, label, None
        except Exception as e:
            last_err = f"{label}: {type(e).__name__}: {e}"
            continue

    try:
        validated = JWTAuthentication().get_validated_token(raw_token)
        user = JWTAuthentication().get_user(validated)
        return user, "jwt_auth", None
    except Exception as e:
        last_err = f"jwt_auth: {type(e).__name__}: {e}"

    return None, None, last_err


@sync_to_async
def resolve_session_user(request):
    """
    Safely resolve Django session user in a sync thread.

    MUST NOT be done inline in async get_context — accessing LazyObject
    request.user triggers SessionStore.load() → SynchronousOnlyOperation,
    which previously aborted the whole get_context and wiped JWT auth.
    """
    try:
        user = getattr(request, "user", None)
        if user is None:
            return None
        # Force evaluation of SimpleLazyObject inside this sync thread
        if getattr(user, "is_authenticated", False):
            _ = user.pk
            return user
    except Exception:
        return None
    return None


@method_decorator(csrf_exempt, name="dispatch")
class CustomGraphQLView(AsyncGraphQLView):
    async def dispatch(self, request, *args, **kwargs):
        try:
            raw = request.body
            if isinstance(raw, (bytes, bytearray)):
                request._gql_debug_body = raw.decode("utf-8", "ignore")
            else:
                request._gql_debug_body = str(raw or "")
        except Exception as e:
            request._gql_debug_body = f"<body-error {e}>"

        token = _normalize_auth_meta(request)
        request._gql_has_auth_header = bool(token)
        request._gql_token_prefix = (
            (token[:12] + "…") if token and len(token) > 12 else (token or "")
        )
        return await super().dispatch(request, *args, **kwargs)

    async def get_context(self, request, response):
        context = await super().get_context(request, response)
        user = None
        auth_src = None
        auth_err = None
        try:
            token = _normalize_auth_meta(request)

            # 1) JWT first (primary for official mobile GraphQL).
            #    Do this BEFORE touching request.user — session lazy load
            #    was crashing the whole method in async context.
            if token:
                user, label, auth_err = await resolve_user_from_token(token)
                if user is not None:
                    auth_src = f"jwt_{label}"

            # 2) Optional session user (web) — only if JWT not present
            if user is None:
                session_user = await resolve_session_user(request)
                if session_user is not None:
                    user = session_user
                    auth_src = "session"

            context.user = user
            # Assign concrete user object (not LazyObject) so later async
            # code does not re-trigger session DB loads.
            request.user = user
            request._gql_auth_src = auth_src
            request._gql_auth_err = auth_err
        except Exception as e:
            log.warning("GQL_GET_CONTEXT_FAIL: %s", e, exc_info=True)
            context.user = None
            request.user = None
            request._gql_auth_err = str(e)
        return context

    async def process_result(
        self,
        request: Any,
        result: ExecutionResult,
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, Any]:
        import re

        processed_result = {"data": result.data}

        body = getattr(request, "_gql_debug_body", "") or ""
        op_match = re.search(
            r'"(?:operationName)"\s*:\s*"([^"]+)"', body
        ) or re.search(r"\b(query|mutation)\s+([A-Za-z0-9_]+)", body)
        op_name = ""
        if op_match:
            op_name = (
                op_match.group(1)
                if op_match.lastindex == 1
                and "operationName" in (op_match.group(0) or "")
                else (
                    op_match.group(2)
                    if op_match.lastindex and op_match.lastindex >= 2
                    else op_match.group(1)
                )
            )
        is_mutation = '"mutation' in body or "mutation " in body or (
            body.lstrip().startswith("mutation")
        )

        user_id = getattr(getattr(request, "user", None), "id", None)
        has_auth = getattr(request, "_gql_has_auth_header", False)
        auth_src = getattr(request, "_gql_auth_src", None)
        auth_err = getattr(request, "_gql_auth_err", None)
        token_prefix = getattr(request, "_gql_token_prefix", "")

        if result.errors:
            processed_result["errors"] = [
                {
                    "message": error.message,
                    "extensions": error.extensions or {},
                }
                for error in result.errors
            ]
            is_auth_miss = user_id is None and any(
                "not authenticated" in (e.message or "").lower()
                or (e.extensions or {}).get("code") == "UNAUTHENTICATED"
                for e in result.errors
            )
            if is_auth_miss:
                log.warning(
                    "GQL_AUTH_MISS op=%s has_auth=%s src=%s err=%s token=%s path=%s",
                    op_name,
                    has_auth,
                    auth_src,
                    auth_err,
                    token_prefix,
                    getattr(request, "path", ""),
                )
            else:
                log.error(
                    "GQL_DEBUG_QUERY user=%s op=%s path=%s body=%s errors=%s",
                    user_id,
                    op_name,
                    getattr(request, "path", ""),
                    body[:4000],
                    [
                        {
                            "message": e.message,
                            "path": getattr(e, "path", None),
                            "code": (e.extensions or {}).get("code")
                            if e.extensions
                            else None,
                        }
                        for e in result.errors
                    ],
                )
        else:
            if is_mutation:
                keys = (
                    list((result.data or {}).keys())
                    if isinstance(result.data, dict)
                    else []
                )
                log.info(
                    "GQL_MUTATION_OK user=%s op=%s keys=%s",
                    user_id,
                    op_name,
                    keys,
                )
            elif user_id and op_name in (
                "userInformationAndWorkspacesQuery",
                "UserFavoritesQuery",
                "stickies",
            ):
                log.info(
                    "GQL_OK user=%s op=%s src=%s",
                    user_id,
                    op_name,
                    auth_src,
                )

        return processed_result
