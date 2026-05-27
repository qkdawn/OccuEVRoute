"""Location search integration for planner start points."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from backend.schemas import LocationSearchResult


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
SHENZHEN_VIEWBOX = "113.75,22.85,114.65,22.38"
USER_AGENT = "OccuEVRoute/1.0 course-demo"


def search_locations(query: str, limit: int = 5) -> list[LocationSearchResult]:
    normalized = query.strip()
    if not normalized:
        return []

    params = urllib.parse.urlencode(
        {
            "q": normalized,
            "format": "jsonv2",
            "limit": max(1, min(limit, 10)),
            "addressdetails": 0,
            "bounded": 1,
            "viewbox": SHENZHEN_VIEWBOX,
        }
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=6) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results: list[LocationSearchResult] = []
    for item in payload:
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(item.get("display_name") or normalized)
        results.append(LocationSearchResult(label=label, lat=lat, lng=lng))
    return results
