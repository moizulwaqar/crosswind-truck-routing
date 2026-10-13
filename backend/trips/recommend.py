"""Route ranking — the spec's preference order, applied lexicographically.

    1. Fewest Severe miles
    2. Fewest High miles
    3. Lowest average risk
    4. Shortest travel time

No Travel is stricter than Severe, so No Travel miles are compared *before*
Severe miles (a route with any No Travel stretch can never beat one without).
Values are rounded before comparing so float noise (e.g. 0.000001 miles)
never decides a recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass

from .risk import RiskLevel


@dataclass
class RouteScore:
    route_id: str
    name: str
    duration_seconds: float
    miles_by_level: list[float]  # index = RiskLevel

    @property
    def total_miles(self) -> float:
        return sum(self.miles_by_level)

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[RiskLevel.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH]

    @property
    def average_risk(self) -> float:
        """Distance-weighted mean risk level on a 0 (Low) – 4 (No Travel) scale."""
        total = self.total_miles
        if not total:
            return 0.0
        return sum(level * miles for level, miles in enumerate(self.miles_by_level)) / total

    def sort_key(self) -> tuple:
        return (
            round(self.no_travel_miles, 1),
            round(self.severe_miles, 1),
            round(self.high_miles, 1),
            round(self.average_risk, 3),
            round(self.duration_seconds / 60),  # whole minutes
        )


def _mi(miles: float) -> str:
    return f"{miles:.1f}".rstrip("0").rstrip(".") + " mi"


CRITERIA = (
    ("No Travel miles", lambda s: _mi(s.no_travel_miles)),
    ("Severe miles", lambda s: _mi(s.severe_miles)),
    ("High miles", lambda s: _mi(s.high_miles)),
    ("average risk", lambda s: f"{s.average_risk:.2f}"),
    ("travel time", lambda s: _fmt_duration(s.duration_seconds)),
)


def _fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    return f"{minutes // 60}h {minutes % 60:02d}m"


def rank(scores: list[RouteScore]) -> tuple[list[RouteScore], str]:
    """Return scores best-first and a one-sentence reason for the winner."""
    ordered = sorted(scores, key=lambda s: s.sort_key())
    if not ordered:
        return ordered, ""
    best = ordered[0]
    if len(ordered) == 1:
        reason = "Only one drivable route was found."
    else:
        runner = ordered[1]
        bk, rk = best.sort_key(), runner.sort_key()
        idx = next((i for i, (a, b) in enumerate(zip(bk, rk)) if a != b), None)
        if idx is None:
            reason = f"{best.name} and {runner.name} are tied on every criterion; {best.name} is listed first."
        else:
            _, fmt = CRITERIA[idx]
            compare = f"({fmt(best)} vs {fmt(runner)} for {runner.name})"
            reason = {
                0: f"{best.name} has the fewest No Travel miles {compare}.",
                1: f"{best.name} has the fewest Severe miles {compare}.",
                2: f"Severe miles are tied; {best.name} has the fewest High miles {compare}.",
                3: f"Severe and High miles are tied; {best.name} has the lowest average risk {compare}.",
                4: f"Weather risk is equal across options, so the fastest wins: {best.name} {compare}.",
            }[idx]
    if best.no_travel_miles > 0:
        reason += " Warning: even the best route crosses No Travel conditions — consider delaying departure."
    elif best.severe_miles > 0:
        reason += " Caution: the best route still includes Severe conditions."
    return ordered, reason
