import pytest

from trips.risk import RiskLevel as L
from trips.risk import apply_load_rules, assess, classify_rain, classify_snow, classify_wind


@pytest.mark.parametrize(
    "mph,expected",
    [
        (0, L.LOW), (24.9, L.LOW),
        (25, L.MODERATE), (34.9, L.MODERATE),
        (35, L.HIGH), (44.9, L.HIGH),
        (45, L.SEVERE), (54.9, L.SEVERE),
        (55, L.NO_TRAVEL), (80, L.NO_TRAVEL),
    ],
)
def test_wind_bands(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [
        (0, L.LOW), (0.099, L.LOW),
        (0.10, L.MODERATE), (0.249, L.MODERATE),
        (0.25, L.HIGH), (0.499, L.HIGH),
        (0.50, L.SEVERE), (1.00, L.SEVERE),  # spec: No Travel is strictly > 1.00
        (1.01, L.NO_TRAVEL),
    ],
)
def test_rain_bands(rate, expected):
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [
        (0, L.LOW), (0.49, L.LOW),
        (0.5, L.MODERATE), (0.99, L.MODERATE),
        (1.0, L.HIGH), (1.99, L.HIGH),
        (2.0, L.SEVERE), (3.0, L.SEVERE),  # spec: No Travel is strictly > 3.0
        (3.01, L.NO_TRAVEL),
    ],
)
def test_snow_bands(rate, expected):
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    "mph,load,expected",
    [
        # >=55 mph: No Travel for any load
        (55, 0, L.NO_TRAVEL),
        (60, 10_000, L.NO_TRAVEL),
        # 45–54 mph: No Travel only when load > 30,000 lb
        (45, 30_000, L.SEVERE),
        (45, 30_001, L.NO_TRAVEL),
        (54, 45_000, L.NO_TRAVEL),
        # 35–44 mph: Severe only when load > 40,000 lb
        (35, 40_000, L.HIGH),
        (35, 40_001, L.SEVERE),
        (44, 79_000, L.SEVERE),
        # below 35 mph: load never matters
        (34, 80_000, L.MODERATE),
        (10, 80_000, L.LOW),
    ],
)
def test_load_rules(mph, load, expected):
    assert apply_load_rules(mph, classify_wind(mph), load) == expected


def test_overall_is_worst_condition():
    a = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6, load_lb=20_000)
    assert a.level == L.HIGH
    assert a.rain_level == L.HIGH and a.snow_level == L.MODERATE
    assert a.reasons == ("Rain 0.30 in/hr",)


def test_load_escalation_is_reported():
    a = assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=42_000)
    assert a.level == L.SEVERE
    assert a.load_escalated
    assert "escalated from High" in a.reasons[0]


def test_calm_weather_has_no_reasons():
    a = assess(5, 0, 0, 80_000)
    assert a.level == L.LOW and a.reasons == ()
