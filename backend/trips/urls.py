from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("geocode", views.geocode),
    path("plan", views.plan),
    path("trips", views.trips),
    path("trips/<int:trip_id>", views.trip_detail),
    path("heatmap", views.heatmap),
]
