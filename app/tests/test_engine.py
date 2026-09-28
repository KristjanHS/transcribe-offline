import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np
import pytest
from numpy.typing import NDArray

from transcribe_offline import engine
from transcribe_offline.models import REQUIRED_FILES

FIXTURES = Path(__file__).parent / "fixtures"


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


def silence(path: Path) -> NDArray[np.float32]:
    return np.zeros(engine.SAMPLE_RATE, np.float32)


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
        decode=silence,
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
            decode=silence,
        )
    assert list(tmp_path.iterdir()) == []


def transcribe(audio: Path, on_progress: Callable[[float], None] = lambda f: None) -> Path:
    return engine.transcribe_file(
        FakeModel(SEGMENTS),  # pyright: ignore[reportArgumentType]
        audio,
        "et",
        timestamps=False,
        on_progress=on_progress,
        cancelled=lambda: False,
        decode=silence,
    )


def test_transcribe_file_never_overwrites_a_file_that_appears_meanwhile(tmp_path: Path) -> None:
    taken = tmp_path / "talk.txt"

    def take(fraction: float) -> None:
        taken.write_text("mine")

    out = transcribe(tmp_path / "talk.wav", on_progress=take)
    assert out == tmp_path / "talk (2).txt"
    assert taken.read_text() == "mine"


def test_transcribe_file_leaves_a_stale_partial_alone(tmp_path: Path) -> None:
    stale = tmp_path / "talk.txt.partial"
    stale.write_text("stale")
    assert transcribe(tmp_path / "talk.wav") == tmp_path / "talk (2).txt"
    assert stale.read_text() == "stale"


def test_decode_audio_gives_16k_mono_float() -> None:
    samples = engine.decode_audio(FIXTURES / "en.wav")
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert len(samples) > engine.SAMPLE_RATE and 0 < np.abs(samples).max() <= 1


def ac3_and_video_mkv(path: Path) -> Path:
    with av.open(str(path), "w") as out:
        audio = out.add_stream("ac3", rate=48000)
        video = out.add_stream("mpeg4", rate=1)
        assert isinstance(audio, av.AudioStream) and isinstance(video, av.VideoStream)
        video.width = video.height = 16
        frame = av.AudioFrame.from_ndarray(np.zeros((1, 48000), np.float32), "fltp", "mono")
        frame.rate = 48000
        picture = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), np.uint8), "rgb24")
        for packet in [*audio.encode(frame), *audio.encode(None), *video.encode(picture)]:
            out.mux(packet)
        for packet in video.encode(None):
            out.mux(packet)
    return path


def test_decode_audio_rejects_a_codec_outside_the_allow_list(tmp_path: Path) -> None:
    with pytest.raises(engine.UnsupportedAudioError, match="codec: ac3"):
        engine.decode_audio(ac3_and_video_mkv(tmp_path / "talk.mkv"))


def test_opening_never_starts_a_decoder_outside_the_allow_list(tmp_path: Path) -> None:
    # av.open probes every stream with its decoder; a started decoder would have set the format.
    path = ac3_and_video_mkv(tmp_path / "talk.mkv")
    with av.open(str(path), options=engine.OPTIONS) as container:
        streams = container.streams
        assert (streams.audio[0].format, streams.video[0].format) == (None, None)


def test_decode_audio_rejects_content_that_probes_as_another_format(tmp_path: Path) -> None:
    # An ffconcat playlist named .wav: FFmpeg would probe it as "concat" and open the listed file.
    path = tmp_path / "talk.wav"
    path.write_text(f"ffconcat version 1.0\nfile '{FIXTURES / 'en.wav'}'\n")
    with pytest.raises(engine.UnsupportedAudioError, match="format"):
        engine.decode_audio(path)
