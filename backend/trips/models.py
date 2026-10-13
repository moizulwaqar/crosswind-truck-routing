"""Saved trip plans. Routes and forecasts are computed live, then stored here."""
from django.db import models


class Trip(models.Model):
    origin_label = models.CharField(max_length=300, blank=True)
    destination_label = models.CharField(max_length=300, blank=True)
    origin_lat = models.FloatField()
    origin_lon = models.FloatField()
    destination_lat = models.FloatField()
    destination_lon = models.FloatField()
    departure = models.DateTimeField()
    load_lb = models.FloatField()
    interval_miles = models.PositiveSmallIntegerField()
    recommended_route_id = models.CharField(max_length=8)
    plan = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
