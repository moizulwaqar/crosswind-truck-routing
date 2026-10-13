"""Request validation for the public API."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_DEPARTURE_DAYS_AHEAD = 7  # Open-Meteo forecasts reach ~16 days; leave room for long trips
MAX_LOAD_LB = 120_000


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(required=False, allow_blank=True, max_length=300)


def validate_departure(value):
    # DRF has already made naive datetimes aware (as UTC, settings.TIME_ZONE);
    # the frontend always sends an explicit UTC ISO string.
    now = timezone.now()
    if value < now - timedelta(hours=1):
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
        raise serializers.ValidationError(
            f"Departure must be within {MAX_DEPARTURE_DAYS_AHEAD} days (forecast horizon)."
        )
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if abs(o["lat"] - d["lat"]) < 1e-4 and abs(o["lon"] - d["lon"]) < 1e-4:
            raise serializers.ValidationError("Origin and destination are the same place.")
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    start = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    cells = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=600,
    )

    def validate_cells(self, cells):
        for lat, lon in cells:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Cell coordinates out of range.")
        return cells
