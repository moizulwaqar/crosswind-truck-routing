"""HTTP API.

    GET  /api/health              liveness
    GET  /api/geocode?q=Dallas    place autocomplete
    POST /api/plan                3 routes + checkpoints + risk + recommendation
    GET  /api/trips               recently saved plans
    GET  /api/trips/<id>          one saved plan
    POST /api/heatmap             0–48 h corridor forecast frames
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Trip
from .providers.geocoding import search_places
from .providers.http import ProviderError
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services.corridor import corridor_heatmap
from .services.planner import plan_trip

log = logging.getLogger(__name__)


def _error(message: str, code: int, details=None) -> Response:
    body = {"error": message}
    if details:
        body["details"] = details
    return Response(body, status=code)


def _first_error(errors) -> str:
    """Flatten DRF's nested error structure into one readable sentence."""
    if isinstance(errors, dict):
        for field, value in errors.items():
            msg = _first_error(value)
            return msg if field == "non_field_errors" else f"{field.replace('_', ' ').capitalize()}: {msg}"
    if isinstance(errors, list) and errors:
        return _first_error(errors[0])
    return str(errors)


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    try:
        return Response({"results": search_places(request.query_params.get("q", ""))})
    except ProviderError as exc:
        return _error(str(exc), exc.status)


@api_view(["POST"])
def plan(request):
    ser = PlanRequestSerializer(data=request.data)
    if not ser.is_valid():
        return _error(_first_error(ser.errors), status.HTTP_400_BAD_REQUEST, ser.errors)
    d = ser.validated_data
    started = time.perf_counter()
    try:
        result = plan_trip(
            origin=(d["origin"]["lat"], d["origin"]["lon"]),
            destination=(d["destination"]["lat"], d["destination"]["lon"]),
            departure=d["departure"],
            load_lb=d["load_lb"],
            interval_miles=int(d["interval_miles"]),
        )
    except ProviderError as exc:
        return _error(str(exc), exc.status)
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    _save_trip(d, result)
    log.info("plan: %d routes in %d ms", len(result["routes"]), result["elapsed_ms"])
    return Response(result)


def _save_trip(data, result) -> None:
    """Persist the plan. Labels come from the request; the planner only has coordinates."""
    origin, dest = data["origin"], data["destination"]
    result["origin"]["label"] = origin.get("label") or ""
    result["destination"]["label"] = dest.get("label") or ""
    trip = Trip.objects.create(
        origin_label=result["origin"]["label"],
        destination_label=result["destination"]["label"],
        origin_lat=origin["lat"],
        origin_lon=origin["lon"],
        destination_lat=dest["lat"],
        destination_lon=dest["lon"],
        departure=data["departure"],
        load_lb=data["load_lb"],
        interval_miles=int(data["interval_miles"]),
        recommended_route_id=result["recommended_route_id"],
        plan={},
    )
    result["trip_id"] = trip.id
    trip.plan = result
    trip.save(update_fields=["plan"])


def _trip_summary(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "origin_label": trip.origin_label,
        "destination_label": trip.destination_label,
        "departure": trip.departure.isoformat(),
        "load_lb": trip.load_lb,
        "interval_miles": trip.interval_miles,
        "recommended_route_id": trip.recommended_route_id,
        "created_at": trip.created_at.isoformat(),
    }


@api_view(["GET"])
def trips(_request):
    rows = Trip.objects.all()[:12]
    return Response({"trips": [_trip_summary(t) for t in rows]})


@api_view(["GET"])
def trip_detail(_request, trip_id: int):
    trip = Trip.objects.filter(pk=trip_id).first()
    if trip is None:
        return _error("This search could not be found.", status.HTTP_404_NOT_FOUND)
    return Response(trip.plan)


@api_view(["POST"])
def heatmap(request):
    ser = HeatmapRequestSerializer(data=request.data)
    if not ser.is_valid():
        return _error(_first_error(ser.errors), status.HTTP_400_BAD_REQUEST, ser.errors)
    d = ser.validated_data
    try:
        data = corridor_heatmap([tuple(c) for c in d["cells"]], d["start"], d["load_lb"])
    except ProviderError as exc:
        return _error(str(exc), exc.status)
    return Response(data)


def spa(_request, path: str = ""):
    """Serve the React app's index.html for any non-API route."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend not built. Run `npm run build` in frontend/ (or use the Vite dev server).")
    return FileResponse(open(index, "rb"), content_type="text/html")
