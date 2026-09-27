import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from transcribe_offline import engine
from transcribe_offline.models import REQUIRED_FILES


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00.00"),
        (1.234, "00:00:01.23"),
        (59.996, "00:01:00.00"),
        (3723.5, "01:02:03.50"),
        (-2.0, "00:00:00.00"),
        (math.nan, "??:??:??.??"),
        (math.inf, "??:??:??.??"),
    ],
)
def test_fmt_time(seconds: float, expected: str) -> None:
    assert engine.fmt_time(seconds) == expected


def test_format_line_both_modes() -> None:
    assert engine.format_line(1.0, 2.5, "  Tere  ", True) == "[00:00:01.00 --> 00:00:02.50] Tere"
    assert engine.format_line(1.0, 2.5, "  Tere  ", False) == "Tere"


def test_unique_destination_collisions(tmp_path: Path) -> None:
    audio = tmp_path / "talk.mp3"
    assert engine.unique_destination(audio) == tmp_path / "talk.txt"
    (tmp_path / "talk.txt").touch()
    assert engine.unique_destination(audio) == tmp_path / "talk (2).txt"
    (tmp_path / "talk (2).txt").touch()
    assert engine.unique_destination(audio) == tmp_path / "talk (3).txt"


def test_is_audio_case_insensitive() -> None:
    assert engine.is_audio(Path("a.MP3"))
    assert engine.is_audio(Path("b.M4a"))
    assert not engine.is_audio(Path("notes.docx"))


def test_missing_files_and_load_refusal(tmp_path: Path) -> None:
    model_dir = tmp_path / "et"
    model_dir.mkdir()
    for name in REQUIRED_FILES[:-1]:
        (model_dir / name).touch()
    assert engine.missing_files(model_dir) == [REQUIRED_FILES[-1]]
    with pytest.raises(engine.ModelMissingError, match="preprocessor_config.json"):
        engine.load_model(tmp_path, engine.LANGUAGES["Estonian"])


@dataclass
class Seg:
    start: float
    end: float
    text: str


@dataclass
class Info:
    duration: float


class FakeModel:
    def __init__(self, segments: list[Seg], duration: float = 10.0) -> None:
        self.segments = segments
        self.duration = duration
        self.kwargs: dict[str, object] = {}

    def transcribe(self, audio: str, **kwargs: object) -> tuple[list[Seg], Info]:
        self.kwargs = kwargs
        return self.segments, Info(self.duration)


SEGMENTS = [Seg(0.0, 5.0, " Tere."), Seg(5.0, 10.0, " Head aega.")]


def test_transcribe_file_writes_txt_and_reports_progress(tmp_path: Path) -> None:
    audio = tmp_path / "talk.wav"
    progress: list[float] = []
    model = FakeModel(SEGMENTS)
    out = engine.transcribe_file(
        model,  # pyright: ignore[reportArgumentType]
        audio,
        engine.LANGUAGES["Estonian"],
        timestamps=False,
        on_progress=progress.append,
        cancelled=lambda: False,
    )
    assert out == tmp_path / "talk.txt"
    assert out.read_text(encoding="utf-8").splitlines() == ["Tere.", "Head aega."]
    assert progress == [0.5, 1.0]
    assert model.kwargs == {
        "language": "et",
        "beam_size": 7,
        "patience": 1.2,
        "repetition_penalty": 1.05,
    }
    assert not list(tmp_path.glob("*.partial"))


def test_transcribe_file_cancel_removes_partial(tmp_path: Path) -> None:
    with pytest.raises(engine.Cancelled):
        engine.transcribe_file(
            FakeModel(SEGMENTS),  # pyright: ignore[reportArgumentType]
            tmp_path / "talk.wav",
            engine.LANGUAGES["English"],
            timestamps=True,
            on_progress=lambda f: None,
            cancelled=lambda: True,
        )
    assert list(tmp_path.iterdir()) == []
