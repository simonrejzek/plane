# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from urllib.parse import urlencode, urljoin

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseRedirect
from django.views import View

# Module imports
from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.provider.credentials.email import EmailProvider
from plane.authentication.utils.host import base_host
from plane.authentication.utils.mobile.login import ValidateAuthToken, mobile_validate_user_onboarding
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.db.models import User
from plane.license.models import Instance
from plane.utils.exception_logger import log_exception


class MobileSignInAuthEndpoint(View):
    """Email/password sign-in for the official mobile WebView at /m/auth."""

    def post(self, request):
        instance = Instance.objects.first()
        if instance is None or not instance.is_setup_done:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"],
                error_message="INSTANCE_NOT_CONFIGURED",
            )
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)

        email = request.POST.get("email", False)
        password = request.POST.get("password", False)

        if not email or not password:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["REQUIRED_EMAIL_PASSWORD_SIGN_IN"],
                error_message="REQUIRED_EMAIL_PASSWORD_SIGN_IN",
                payload={"email": str(email)},
            )
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)

        email = email.strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INVALID_EMAIL_SIGN_IN"],
                error_message="INVALID_EMAIL_SIGN_IN",
                payload={"email": str(email)},
            )
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)

        existing_user = User.objects.filter(email=email).first()
        if not existing_user:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["USER_DOES_NOT_EXIST"],
                error_message="USER_DOES_NOT_EXIST",
                payload={"email": str(email)},
            )
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)

        try:
            provider = EmailProvider(
                request=request,
                key=email,
                code=password,
                is_signup=False,
                callback=post_user_auth_workflow,
            )
            user = provider.authenticate()

            is_onboarded = mobile_validate_user_onboarding(user=user)
            if not is_onboarded:
                exc = AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["USER_NOT_ONBOARDED"],
                    error_message="USER_NOT_ONBOARDED",
                    payload={"email": str(email)},
                )
                url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
                return HttpResponseRedirect(url)

            session_token = ValidateAuthToken()
            session_token.set_value(str(user.id))

            url = urljoin(
                base_host(request=request, is_app=True),
                "m/auth/?" + urlencode({"token": session_token.token}),
            )
            return HttpResponseRedirect(url)
        except AuthenticationException as e:
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(e.get_error_dict()))
            return HttpResponseRedirect(url)
        except ValueError as e:
            log_exception(e)
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["AUTHENTICATION_FAILED"],
                error_message="AUTHENTICATION_FAILED",
                payload={"email": str(email)},
            )
            url = urljoin(base_host(request=request, is_app=True), "m/auth/?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)
