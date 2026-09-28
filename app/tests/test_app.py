import queue
import threading
from pathlib import Path

from transcribe_offline import app, engine


def test_run_job_reports_missing_model_and_finishes(tmp_path: Path) -> None:
    events: queue.Queue[app.Event] = queue.Queue()
    audio = tmp_path / "talk.wav"
    app.run_job(
        [audio], engine.LANGUAGES["Estonian"], True, events, threading.Event(), models_root=tmp_path
    )
    got = [events.get_nowait() for _ in range(events.qsize())]
    assert [e.kind for e in got] == ["failed", "finished"]
    assert "Transcribe-Setup.exe" in got[0].text


def test_seconds_left_waits_for_a_meaningful_rate() -> None:
    assert app.seconds_left(0.5, 1.0) is None
    assert app.seconds_left(0.0, 60.0) is None
    assert app.seconds_left(0.25, 60.0) == 180.0


def test_format_eta() -> None:
    assert app.format_eta(20) == "<1 min left"
    assert app.format_eta(300) == "~5 min left"
    assert app.format_eta(3900) == "~1 h 5 min left"
