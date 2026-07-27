# Django imports
from django.urls import path
from django.conf import settings

# Module imports
from plane.graphql.views import CustomGraphQLView
from plane.graphql.schema import schema

urlpatterns = [
    path(
        "",
        # strawberry-django AsyncGraphQLView does not accept graphiql= as as_view() kwarg
        CustomGraphQLView.as_view(schema=schema),
    )
]
