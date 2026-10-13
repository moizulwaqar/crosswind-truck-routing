"""Place search via Photon (OpenStreetMap data, free, typo-tolerant, no key)."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from .http import get_json


def _label(props: dict) -> str:
    parts: list[str] = []
    for key in ("name", "city", "county", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    if props.get("housenumber") and props.get("street"):
        parts.insert(0, f"{props['housenumber']} {props['street']}")
    return ", ".join(parts[:4])


def search_places(query: str, limit: int = 6) -> list[dict]:
    query = query.strip()
    if len(query) < 2:
        return []
    key = f"geo:{query.lower()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = get_json(
        settings.PHOTON_URL,
        params={"q": query, "limit": limit, "lang": "en"},
        service="Geocoding service (Photon)",
    )
    results, seen = [], set()
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        label = _label(feature.get("properties", {}))
        if not label or label in seen:
            continue
        seen.add(label)
        results.append({"label": label, "lat": round(lat, 6), "lon": round(lon, 6)})
    cache.set(key, results, 24 * 60 * 60)
    return results
