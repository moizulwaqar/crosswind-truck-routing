"""End-to-end API tests against the deterministic fake providers."""
from datetime import timedelta

import pytest

pytestmark = pytest.mark.django_db
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def fake_providers(settings):
    settings.FAKE_PROVIDERS = True
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


def plan_payload(**overrides):
    body = {
        "origin": {"lat": 32.7767, "lon": -96.7970, "label": "Dallas"},
        "destination": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago"},
        "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_lb": 42_000,
        "interval_miles": 25,
    }
    body.update(overrides)
    return body


def test_plan_returns_three_ranked_routes(client):
    res = client.post("/api/plan", plan_payload(), format="json")
    assert res.status_code == 200, res.json()
    data = res.json()
    routes = data["routes"]
    assert len(routes) == 3
    assert sorted(r["rank"] for r in routes) == [1, 2, 3]
    assert sum(r["recommended"] for r in routes) == 1
    assert data["recommended_route_id"] == next(r["id"] for r in routes if r["recommended"])
    assert data["recommendation_reason"]

    for r in routes:
        cps = r["checkpoints"]
        assert cps[0]["mile"] == 0
        assert cps[-1]["mile"] == pytest.approx(r["distance_miles"], abs=0.1)
        assert sum(r["stats"]["miles_by_level"]) == pytest.approx(r["distance_miles"], abs=0.5)
        assert all(a["eta"] <= b["eta"] for a, b in zip(cps, cps[1:]))
        assert len(r["timeline"]) == 49
        assert r["risk_segments"][0]["from_mile"] == 0


def test_recommended_route_follows_spec_order(client):
    data = client.post("/api/plan", plan_payload(), format="json").json()
    key = lambda r: (  # noqa: E731
        round(r["stats"]["miles_by_level"][4], 1),
        round(r["stats"]["miles_by_level"][3], 1),
        round(r["stats"]["miles_by_level"][2], 1),
        round(r["stats"]["average_risk"], 3),
        round(r["duration_seconds"] / 60),
    )
    best = min(data["routes"], key=key)
    assert best["recommended"]


def test_interval_changes_checkpoint_density(client):
    n10 = client.post("/api/plan", plan_payload(interval_miles=10), format="json").json()
    n50 = client.post("/api/plan", plan_payload(interval_miles=50), format="json").json()
    assert len(n10["routes"][0]["checkpoints"]) > 4 * len(n50["routes"][0]["checkpoints"]) - 5


def test_heavier_load_never_lowers_risk(client):
    light = client.post("/api/plan", plan_payload(load_lb=5_000), format="json").json()
    heavy = client.post("/api/plan", plan_payload(load_lb=79_000), format="json").json()
    for rl, rh in zip(light["routes"], heavy["routes"]):
        for a, b in zip(rl["checkpoints"], rh["checkpoints"]):
            assert b["level"] >= a["level"]


def test_heatmap_frames(client):
    plan = client.post("/api/plan", plan_payload(), format="json").json()
    cells = plan["corridor"]["cells"]
    assert 0 < len(cells) <= 120
    res = client.post(
        "/api/heatmap",
        {"start": plan["departure"], "load_lb": 42_000, "cells": cells},
        format="json",
    )
    assert res.status_code == 200
    hm = res.json()
    assert hm["hours"] == 48
    assert len(hm["risk"]) == len(cells)
    assert all(len(row) == 49 for row in hm["risk"])
    assert max(max(row) for row in hm["risk"]) >= 3  # the fake storm shows up


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({"interval_miles": 15}, "Interval miles"),
        ({"load_lb": -1}, "Load lb"),
        ({"departure": "2020-01-01T00:00:00Z"}, "past"),
        ({"destination": {"lat": 32.7767, "lon": -96.7970}}, "same place"),
    ],
)
def test_plan_validation(client, override, fragment):
    res = client.post("/api/plan", plan_payload(**override), format="json")
    assert res.status_code == 400
    assert fragment in res.json()["error"]


def test_plan_is_saved_and_listed(client):
    from trips.models import Trip

    res = client.post("/api/plan", plan_payload(), format="json")
    assert res.status_code == 200
    trip_id = res.json()["trip_id"]
    assert Trip.objects.filter(pk=trip_id).exists()

    listed = client.get("/api/trips")
    assert listed.status_code == 200
    assert listed.json()["trips"][0]["id"] == trip_id
    assert listed.json()["trips"][0]["origin_label"] == "Dallas"

    again = client.get(f"/api/trips/{trip_id}")
    assert again.status_code == 200
    assert again.json()["trip_id"] == trip_id
    assert len(again.json()["routes"]) == 3

    missing = client.get("/api/trips/999999")
    assert missing.status_code == 404


def test_invalid_plan_is_not_saved(client):
    from trips.models import Trip

    res = client.post("/api/plan", plan_payload(interval_miles=15), format="json")
    assert res.status_code == 400
    assert Trip.objects.count() == 0


def test_geocode(client):
    res = client.get("/api/geocode", {"q": "dal"})
    assert res.status_code == 200
    assert res.json()["results"][0]["label"].startswith("Dallas")
