# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""plane URL Configuration"""

from django.conf import settings
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

handler404 = "plane.app.views.error_404.custom_404_view"

urlpatterns = [
    path("api/", include("plane.app.urls")),
    path("api/public/", include("plane.space.urls")),
    path("api/instances/", include("plane.license.urls")),
    path("api/v1/", include("plane.api.urls")),
    path("auth/", include("plane.authentication.urls")),
    path("", include("plane.web.urls")),
]

try:
    import strawberry  # noqa: F401

    # Mobile app expects /graphql/; also expose under /api/graphql/ as fallback
    # Import eagerly so ImportErrors are logged instead of silent 404s.
    import plane.graphql.urls  # noqa: F401

    # Register both with and without trailing slash so mobile POST /graphql
    # does not 301-redirect and drop the request body.
    urlpatterns = [
        path("graphql/", include("plane.graphql.urls")),
        path("graphql", include("plane.graphql.urls")),
        path("api/graphql/", include("plane.graphql.urls")),
        path("api/graphql", include("plane.graphql.urls")),
    ] + urlpatterns
except Exception as graphql_exc:  # noqa: BLE001 — never block API boot if mobile GraphQL fails
    import logging

    logging.getLogger(__name__).exception("Mobile GraphQL disabled: %s", graphql_exc)

if settings.ENABLE_DRF_SPECTACULAR:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/schema/swagger-ui/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/schema/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [re_path(r"^__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
