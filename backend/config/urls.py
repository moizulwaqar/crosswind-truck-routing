from django.urls import include, path, re_path

from trips.views import spa

urlpatterns = [
    path("api/", include("trips.urls")),
    re_path(r"^(?!api/).*$", spa),
]
