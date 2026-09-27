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
    assert "install.bat" in got[0].text
