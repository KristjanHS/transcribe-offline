import functools
import shutil
from pathlib import Path

import pytest

from transcribe_offline import engine

FIXTURES = Path(__file__).parent / "fixtures"
MODELS_ROOT = Path(__file__).parents[1] / "models"


@functools.cache
def model_for(name: str) -> object:
    return engine.load_model(MODELS_ROOT, engine.LANGUAGES[name])


@pytest.mark.slow
@pytest.mark.parametrize("timestamps", [True, False], ids=["ts", "plain"])
@pytest.mark.parametrize("name", ["Estonian", "English"])
def test_matches_stt_faster(tmp_path: Path, name: str, timestamps: bool) -> None:
    lang = engine.LANGUAGES[name]
    audio = tmp_path / f"{lang.code}.wav"
    shutil.copy(FIXTURES / audio.name, audio)
    out = engine.transcribe_file(
        model_for(name),  # pyright: ignore[reportArgumentType]
        audio,
        lang,
        timestamps=timestamps,
        on_progress=lambda f: None,
        cancelled=lambda: False,
    )
    golden = FIXTURES / "golden" / f"{lang.code}-{'ts' if timestamps else 'plain'}.txt"
    # splitlines() normalises CRLF (Windows output) against LF goldens.
    assert out.read_text(encoding="utf-8").splitlines() == golden.read_text("utf-8").splitlines()
