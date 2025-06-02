from django.urls import path
from .views import MilkmanViewSet


urlpatterns = [
    # Milkman CRUD
    path("allmilkmans/", MilkmanViewSet.as_view({"get": "list"}), name="milkman-list"),
    path(
        "milkmandetails/<int:pk>/",
        MilkmanViewSet.as_view({"get": "retrieve"}),
        name="milkman-retrieve",
    ),
    path(
        "addmilkman/", MilkmanViewSet.as_view({"post": "create"}), name="milkman-create"
    ),
    path(
        "updatemilkman/<int:pk>/",
        MilkmanViewSet.as_view({"put": "update"}),
        name="milkman-update",
    ),
    path(
        "deletemilkman/<int:pk>/",
        MilkmanViewSet.as_view({"delete": "destroy"}),
        name="milkman-delete",
    ),
]
