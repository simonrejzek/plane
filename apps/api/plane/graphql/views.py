from typing import Any, Dict, Optional
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

# Third-Party Imports
from asgiref.sync import sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

# Strawberry imports
from strawberry.django.views import AsyncGraphQLView
from strawberry.types import ExecutionResult
from strawberry.types.execution import ExecutionContext


# Sync to async function to get the validated token
@sync_to_async
def get_validated_token(token):
    return JWTAuthentication().get_validated_token(token)


# Sync to async function to get the user
@sync_to_async
def get_jwt_user(validated_token):
    return JWTAuthentication().get_user(validated_token)


@method_decorator(csrf_exempt, name="dispatch")
class CustomGraphQLView(AsyncGraphQLView):
    async def get_context(self, request, response):
        # Get the context from the parent class
        context = await super().get_context(request, response)
        try:
            # ========= JWT token validation =========
            # Get the token from the request headers
            auth_header = request.headers.get("Authorization")

            # If the token is present, validate it and get the user
            if auth_header:
                parts = auth_header.split()
                # Accept "Bearer <token>" (official app) and raw token
                bearer_token = parts[1] if len(parts) >= 2 else parts[0]
                if not bearer_token:
                    context.user = None
                    request.user = None
                    return context

                validated_token = await get_validated_token(bearer_token)
                if validated_token is None:
                    context.user = None
                    request.user = None
                    return context

                # Get the user from the validated token
                user = await get_jwt_user(validated_token)

                # Set the user in the context
                context.user = user
                request.user = user
            else:
                context.user = None
        except (InvalidToken, TokenError, IndexError, Exception):
            context.user = None
            request.user = None
        return context

    async def process_result(
        self,
        request: Any,
        result: ExecutionResult,
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, Any]:
        processed_result = {
            "data": result.data,
        }

        if result.errors:
            processed_result["errors"] = [
                {
                    "message": error.message,
                    "extensions": error.extensions or {},
                }
                for error in result.errors
            ]
            # Surface GraphQL failures in API logs (HTTP is still often 200)
            import logging

            logging.getLogger("plane.graphql").error(
                "GraphQL errors user=%s path=%s errors=%s",
                getattr(getattr(request, "user", None), "id", None),
                getattr(request, "path", ""),
                [
                    {
                        "message": e.message,
                        "path": getattr(e, "path", None),
                        "extensions": e.extensions or {},
                    }
                    for e in result.errors
                ],
            )

        return processed_result
