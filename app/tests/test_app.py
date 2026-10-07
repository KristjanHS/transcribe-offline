import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

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


@dataclass
class Device:
    device: str


@dataclass
class FakeModel:
    model: Device


class FakeEngine:
    """load_model / transcribe_file stand-ins: the GPU fails at load or at inference."""

    def __init__(self, gpu_fails_at: str) -> None:
        self.gpu_fails_at = gpu_fails_at
        self.devices: list[str] = []  # one entry per transcribe attempt

    def load(self, models_root: Path, language: str, gpu: bool = True) -> FakeModel:
        if gpu and self.gpu_fails_at == "load":
            raise RuntimeError("CUDA driver version is insufficient")
        return FakeModel(Device("cuda" if gpu else "cpu"))

    def transcribe(self, model: FakeModel, audio: Path, language: str, **_kw: Any) -> Path:
        self.devices.append(model.model.device)
        if model.model.device == "cuda" and self.gpu_fails_at == "inference":
            raise RuntimeError("Library cublas64_12.dll is not found")
        return audio.with_suffix(".txt")


@pytest.mark.parametrize(
    ("gpu_fails_at", "devices"),
    [
        ("load", ["cpu", "cpu"]),
        ("inference", ["cuda", "cpu", "cpu"]),  # first file retried once, then CPU for the job
        ("never", ["cuda", "cuda"]),
    ],
)
def test_run_job_falls_back_to_cpu_when_the_gpu_fails(
    tmp_path: Path, gpu_fails_at: str, devices: list[str]
) -> None:
    fake = FakeEngine(gpu_fails_at)
    events: queue.Queue[app.Event] = queue.Queue()
    files = [tmp_path / "a.wav", tmp_path / "b.wav"]
    app.run_job(files, "et", True, events, threading.Event(), tmp_path, fake.load, fake.transcribe)
    got = [events.get_nowait() for _ in range(events.qsize())]
    assert [e.kind for e in got] == ["started", "done", "started", "done", "finished"]
    assert fake.devices == devices


def test_run_job_after_a_gpu_success_reports_failures_without_fallback(tmp_path: Path) -> None:
    fake = FakeEngine("never")

    def transcribe(model: FakeModel, audio: Path, language: str, **kw: Any) -> Path:
        if audio.name == "b.wav" and model.model.device == "cuda":
            raise RuntimeError("CUDA out of memory")  # a CPU retry would succeed
        return fake.transcribe(model, audio, language, **kw)

    events: queue.Queue[app.Event] = queue.Queue()
    files = [tmp_path / "a.wav", tmp_path / "b.wav"]
    app.run_job(files, "et", True, events, threading.Event(), tmp_path, fake.load, transcribe)
    got = [events.get_nowait() for _ in range(events.qsize())]
    assert [e.kind for e in got] == ["started", "done", "started", "failed", "finished"]
    assert fake.devices == ["cuda"]


def test_seconds_left_waits_for_a_meaningful_rate() -> None:
    assert app.seconds_left(0.5, 1.0) is None
    assert app.seconds_left(0.0, 60.0) is None
    assert app.seconds_left(0.25, 60.0) == 180.0


def test_format_eta() -> None:
    assert app.format_eta(20) == "<1 min left"
    assert app.format_eta(300) == "~5 min left"
    assert app.format_eta(3900) == "~1 h 5 min left"
