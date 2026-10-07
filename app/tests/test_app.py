from transcribe_offline import app


def test_seconds_left_waits_for_a_meaningful_rate() -> None:
    assert app.seconds_left(0.5, 1.0) is None
    assert app.seconds_left(0.0, 60.0) is None
    assert app.seconds_left(0.25, 60.0) == 180.0


def test_format_eta() -> None:
    assert app.format_eta(20) == "<1 min left"
    assert app.format_eta(300) == "~5 min left"
    assert app.format_eta(3900) == "~1 h 5 min left"
