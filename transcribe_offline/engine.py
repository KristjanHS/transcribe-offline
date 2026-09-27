"""Load a Whisper model from a local folder and transcribe one audio file to a .txt beside it."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from transcribe_offline.models import REQUIRED_FILES

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".wma", ".aac", ".mp4", ".mkv")


@dataclass(frozen=True)
class Lang:
    code: str
    model_dir: str


LANGUAGES = {
    "Estonian": Lang(code="et", model_dir="et"),
    "English": Lang(code="en", model_dir="en"),
}


class Cancelled(Exception):
    """The user pressed Cancel; the partial output has been removed."""


class ModelMissingError(Exception):
    """A required model file is absent; faster-whisper would otherwise try the network."""


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def missing_files(model_path: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (model_path / name).is_file()]


def load_model(models_root: Path, lang: Lang) -> WhisperModel:
    path = models_root / lang.model_dir
    missing = missing_files(path)
    if missing:
        raise ModelMissingError(f"Missing in {path}: {', '.join(missing)}. Run install.bat.")
    os.environ["HF_HUB_OFFLINE"] = "1"  # before faster_whisper loads huggingface_hub
    from faster_whisper import WhisperModel  # deferred: heavy import, only needed once a job starts

    return WhisperModel(str(path), device="cpu", compute_type="int8")


def fmt_time(seconds: float) -> str:
    if not math.isfinite(seconds):
        return "??:??:??.??"
    centis = round(max(0.0, seconds) * 100)
    minutes, centis = divmod(centis, 6000)
    hours, minutes = divmod(minutes, 60)
    secs, centis = divmod(centis, 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def format_line(start: float, end: float, text: str, timestamps: bool) -> str:
    text = text.strip()
    return f"[{fmt_time(start)} --> {fmt_time(end)}] {text}" if timestamps else text


def unique_destination(audio: Path) -> Path:
    candidate = audio.with_suffix(".txt")
    n = 2
    while candidate.exists():
        candidate = audio.with_name(f"{audio.stem} ({n}).txt")
        n += 1
    return candidate


def transcribe_file(
    model: WhisperModel,
    audio: Path,
    lang: Lang,
    *,
    timestamps: bool,
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
) -> Path:
    dest = unique_destination(audio)
    partial = dest.with_name(dest.name + ".partial")
    segments, info = model.transcribe(
        str(audio), language=lang.code, beam_size=7, patience=1.2, repetition_penalty=1.05
    )
    try:
        # Platform newline (CRLF on Windows).
        with open(partial, "w", encoding="utf-8") as out:
            for seg in segments:
                out.write(format_line(seg.start, seg.end, seg.text, timestamps) + "\n")
                if cancelled():
                    raise Cancelled
                if info.duration > 0:
                    on_progress(min(1.0, seg.end / info.duration))
        partial.replace(dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest
