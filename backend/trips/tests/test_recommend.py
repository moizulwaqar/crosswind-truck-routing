from trips.recommend import RouteScore, rank


def score(rid, hours, low=0, mod=0, high=0, severe=0, no_travel=0):
    return RouteScore(rid, f"Route {rid.upper()}", hours * 3600, [low, mod, high, severe, no_travel])


def winner(*scores):
    ordered, reason = rank(list(scores))
    return ordered[0].route_id, reason


def test_fewest_severe_miles_beats_faster_route():
    fast = score("a", 10, low=500, severe=20)
    slow = score("b", 13, low=400, high=150)
    rid, reason = winner(fast, slow)
    assert rid == "b"
    assert "fewest Severe miles" in reason


def test_high_miles_break_severe_tie():
    rid, reason = winner(score("a", 10, low=480, high=40), score("b", 11, low=500, high=10, mod=10))
    assert rid == "b" and "High miles" in reason


def test_average_risk_breaks_high_tie():
    # equal Severe/High; B has more Low miles relative to Moderate
    rid, reason = winner(score("a", 10, low=100, mod=100), score("b", 11, low=180, mod=20))
    assert rid == "b" and "average risk" in reason


def test_travel_time_is_last_tiebreaker():
    rid, reason = winner(score("a", 12, low=500), score("b", 10, low=520))
    assert rid == "b" and "fastest" in reason


def test_no_travel_is_worse_than_severe():
    rid, _ = winner(score("a", 9, low=480, no_travel=5), score("b", 12, low=400, severe=60))
    assert rid == "b"


def test_float_noise_does_not_decide():
    a = score("a", 10, low=500, severe=0.00001)
    b = score("b", 11, low=500)
    rid, _ = winner(a, b)
    assert rid == "a"  # 0.00001 severe miles rounds to 0 → falls through to travel time


def test_warns_when_best_route_is_unsafe():
    _, reason = winner(score("a", 10, low=400, no_travel=3), score("b", 11, low=400, no_travel=9))
    assert "consider delaying departure" in reason
