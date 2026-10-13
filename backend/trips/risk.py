"""Weather risk classification — a direct encoding of the assessment's rules.

Pure functions only (no I/O) so every threshold is unit-testable.

Boundary interpretation (the spec's ranges share endpoints, e.g. "0.10–0.25"
then "0.25–0.50"): a value that sits exactly on a shared endpoint belongs to
the *higher* band, matching the explicit "≥55 mph" wording for wind. The one
exception is the top of the Severe band for rain/snow, where the spec says
No Travel is ">1.00" / ">3.0", so exactly 1.00 in/hr rain is still Severe.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]


# Upper bounds (exclusive) for Low, Moderate, High. Severe/No Travel split is
# handled per condition because the spec words it differently.
WIND_MPH_BANDS = (25.0, 35.0, 45.0, 55.0)  # >=55 -> No Travel
RAIN_IN_HR_BANDS = (0.10, 0.25, 0.50)  # Severe up to and including 1.00
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_IN_HR_BANDS = (0.5, 1.0, 2.0)  # Severe up to and including 3.0
SNOW_NO_TRAVEL_ABOVE = 3.0

# Load rules
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # 45–54 mph + >30,000 lb -> No Travel
HEAVY_LOAD_SEVERE_LB = 40_000  # 35–44 mph + >40,000 lb -> Severe


def classify_wind(mph: float) -> RiskLevel:
    low, moderate, high, severe = WIND_MPH_BANDS
    if mph < low:
        return RiskLevel.LOW
    if mph < moderate:
        return RiskLevel.MODERATE
    if mph < high:
        return RiskLevel.HIGH
    if mph < severe:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def _classify_precip(rate: float, bands: tuple[float, float, float], no_travel_above: float) -> RiskLevel:
    low, moderate, high = bands
    if rate < low:
        return RiskLevel.LOW
    if rate < moderate:
        return RiskLevel.MODERATE
    if rate < high:
        return RiskLevel.HIGH
    if rate <= no_travel_above:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def classify_rain(in_per_hr: float) -> RiskLevel:
    return _classify_precip(in_per_hr, RAIN_IN_HR_BANDS, RAIN_NO_TRAVEL_ABOVE)


def classify_snow(in_per_hr: float) -> RiskLevel:
    return _classify_precip(in_per_hr, SNOW_IN_HR_BANDS, SNOW_NO_TRAVEL_ABOVE)


def apply_load_rules(wind_mph: float, wind_level: RiskLevel, load_lb: float) -> RiskLevel:
    """Escalate the wind level for heavy loads (high-profile tip-over risk).

    * ≥55 mph            -> No Travel for any load (already true of the base level)
    * 45–54 mph, >30k lb -> No Travel
    * 35–44 mph, >40k lb -> Severe
    """
    if wind_mph >= WIND_MPH_BANDS[3]:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= WIND_MPH_BANDS[2] and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= WIND_MPH_BANDS[1] and load_lb > HEAVY_LOAD_SEVERE_LB:
        return max(wind_level, RiskLevel.SEVERE)
    return wind_level


@dataclass(frozen=True)
class Assessment:
    level: RiskLevel
    wind_level: RiskLevel
    rain_level: RiskLevel
    snow_level: RiskLevel
    load_escalated: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "wind_level": int(self.wind_level),
            "rain_level": int(self.rain_level),
            "snow_level": int(self.snow_level),
            "load_escalated": self.load_escalated,
            "reasons": list(self.reasons),
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall checkpoint risk = worst of (load-adjusted wind, rain, snow)."""
    base_wind = classify_wind(wind_mph)
    wind = apply_load_rules(wind_mph, base_wind, load_lb)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    overall = max(wind, rain, snow)

    reasons: list[str] = []
    if overall > RiskLevel.LOW:
        if wind == overall:
            msg = f"Wind {wind_mph:.0f} mph"
            if wind > base_wind:
                msg += f" with {load_lb:,.0f} lb load (escalated from {base_wind.label})"
            reasons.append(msg)
        if rain == overall:
            reasons.append(f"Rain {rain_in_hr:.2f} in/hr")
        if snow == overall:
            reasons.append(f"Snow {snow_in_hr:.2f} in/hr")

    return Assessment(
        level=overall,
        wind_level=wind,
        rain_level=rain,
        snow_level=snow,
        load_escalated=wind > base_wind,
        reasons=tuple(reasons),
    )
