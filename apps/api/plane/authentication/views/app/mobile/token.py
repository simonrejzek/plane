# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
import logging

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

# Module imports
from plane.authentication.utils.mobile.login import ValidateAuthToken, mobile_user_login
from plane.db.models import User

log = logging.getLogger("plane.api.request")


class MobileSessionTokenCheckEndpoint(APIView):
    """Exchange the short-lived WebView token for JWT access/refresh tokens."""

    permission_classes = [AllowAny]
    authentication_classes = []
    # Never throttle token exchange — mobile logs in then immediately uses tokens
    throttle_classes = []

    def get_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "refresh_token": str(refresh),
            "access_token": str(refresh.access_token),
        }

    def post(self, request):
        try:
            token = request.data.get("token", False)
            if not token or token == "":
                return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

            session_token = ValidateAuthToken(token)
            if not session_token.token_exists():
                return Response({"error": "Invalid token"}, status=status.HTTP_403_FORBIDDEN)

            session_details = session_token.get_value()
            if not session_details:
                return Response({"error": "Invalid token"}, status=status.HTTP_403_FORBIDDEN)

            session_token.remove_token()
            user_id = session_details.get("session_id")
            user = User.objects.filter(id=user_id).first()
            if not user:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            tokens = self.get_tokens_for_user(user)
            log.info("MOBILE_TOKEN_CHECK ok user=%s", user.id)
            return Response(tokens, status=status.HTTP_200_OK)
        except Exception as e:
            log.warning("MOBILE_TOKEN_CHECK fail: %s", e)
            return Response({"error": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


class MobileTokenEndpoint(APIView):
    """Issue JWT tokens for an already-authenticated session user."""

    throttle_classes = []

    def get_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "refresh_token": str(refresh),
            "access_token": str(refresh.access_token),
        }

    def get(self, request):
        try:
            return Response(self.get_tokens_for_user(user=request.user), status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


class MobileSessionTokenEndpoint(APIView):
    """Create a Django session from a JWT-authenticated mobile user."""

    authentication_classes = [JWTAuthentication]
    throttle_classes = []

    def post(self, request):
        try:
            session = mobile_user_login(request=request, user=request.user)
            return Response(
                {
                    "session_name": settings.SESSION_COOKIE_NAME,
                    "session_id": session.session_key,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log.warning("MOBILE_SESSION_TOKEN fail user=%s: %s", getattr(request.user, "id", None), e)
            return Response({"error": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


class MobileRefreshTokenEndpoint(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Critical: official mobile refreshes on almost every resume/request.
    # Default AnonRateThrottle (was 30/min) returns 429 and the app logs the user out.
    throttle_classes = []

    def post(self, request):
        # Accept refresh_token / refresh from body or JSON
        refresh_token = (
            request.data.get("refresh_token")
            or request.data.get("refresh")
            or request.POST.get("refresh_token")
            or request.POST.get("refresh")
            or False
        )
        if not refresh_token:
            log.warning("MOBILE_REFRESH missing token")
            return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_token)
            # Do NOT mint a new refresh on every call — official mobile refreshes
            # in a tight loop; rotating churns tokens and looks like a logout.
            # Just issue a fresh access token from the existing refresh.
            return Response(
                {
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                },
                status=status.HTTP_200_OK,
            )
        except (TokenError, InvalidToken) as e:
            log.warning("MOBILE_REFRESH invalid: %s", e)
            return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            log.warning("MOBILE_REFRESH error: %s", e)
            return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)
