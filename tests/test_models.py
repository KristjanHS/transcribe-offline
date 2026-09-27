import shutil
from pathlib import Path

import pytest

from transcribe_offline import engine

FIXTURES = Path(__file__).parent / "fixtures"
MODELS_ROOT = Path(__file__).parents[1] / "models"


@pytest.mark.slow
@pytest.mark.parametrize(
    ("name", "wav", "word"), [("Estonian", "et.wav", "Tartus"), ("English", "en.wav", "Gettysburg")]
)
def test_real_model_transcribes(tmp_path: Path, name: str, wav: str, word: str) -> None:
    lang = engine.LANGUAGES[name]
    audio = tmp_path / wav
    shutil.copy(FIXTURES / wav, audio)
    model = engine.load_model(MODELS_ROOT, lang)
    out = engine.transcribe_file(
        model, audio, lang, timestamps=False, on_progress=lambda f: None, cancelled=lambda: False
    )
    assert word in out.read_text(encoding="utf-8")
