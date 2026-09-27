"""Load a Whisper model from a local folder and transcribe one audio file to a .txt beside it."""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from transcribe_offline.models import REQUIRED_FILES

if TYPE_CHECKING:
    import av.container
    import numpy as np
    from av.audio.frame import AudioFrame
    from faster_whisper import WhisperModel
    from numpy.typing import NDArray

AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".wma", ".aac", ".mp4", ".mkv")

# FFmpeg picks a demuxer by probing the content, not by the extension; only these may open a file.
FORMATS = "wav,mp3,mov,flac,ogg,asf,aac,matroska"
CODECS = ("aac", "alac", "flac", "mp3", "opus", "vorbis", "wmav1", "wmav2", "wmapro")  # + pcm_*
# Decoders FFmpeg may open while probing the file, before the CODECS check in decode_audio runs.
DECODERS = (
    "mp3float,mp3,aac,alac,flac,opus,vorbis,wmav1,wmav2,wmapro,pcm_u8,pcm_s16le,pcm_s16be,"
    "pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_f64le,pcm_alaw,pcm_mulaw"
)
OPTIONS = {"protocol_whitelist": "file", "format_whitelist": FORMATS, "codec_whitelist": DECODERS}
SAMPLE_RATE = 16000

LANGUAGES = {"Estonian": "et", "English": "en"}  # name -> language code = folder under models/


class Cancelled(Exception):
    """The user pressed Cancel; the partial output has been removed."""


class ModelMissingError(Exception):
    """A required model file is absent; faster-whisper would otherwise try the network."""


class UnsupportedAudioError(Exception):
    """The file's container or audio codec is not in FORMATS / CODECS."""


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def missing_files(model_path: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (model_path / name).is_file()]


def load_model(models_root: Path, language: str) -> WhisperModel:
    path = models_root / language
    missing = missing_files(path)
    if missing:
        raise ModelMissingError(f"Missing in {path}: {', '.join(missing)}. Run install.bat.")
    from faster_whisper import WhisperModel  # deferred: heavy import, only needed once a job starts

    return WhisperModel(str(path), device="cpu", compute_type="int8")


def _frames(container: av.container.InputContainer) -> Iterator[AudioFrame]:
    """First audio stream's frames, skipping corrupt ones (as faster-whisper's own decoder does)."""
    import av.error

    frames = container.decode(audio=0)
    while True:
        try:
            yield next(frames)
        except StopIteration:
            return
        except av.error.InvalidDataError:
            continue


def decode_audio(path: Path) -> NDArray[np.float32]:
    """16 kHz mono float32 samples, decoded by FFmpeg restricted to local files and FORMATS/CODECS.

    Replaces faster-whisper's decode_audio, which lets FFmpeg open any format and follow any URL.
    """
    import av  # deferred like faster_whisper
    import av.error
    import numpy as np

    try:
        container = av.open(str(path), options=OPTIONS, metadata_errors="ignore")
    except av.error.ArgumentError as exc:  # EINVAL: no allowed demuxer recognises the content
        raise UnsupportedAudioError(f"not a supported audio format ({exc})") from exc
    with container:
        if not container.streams.audio:
            raise UnsupportedAudioError("no audio stream")
        codec = container.streams.audio[0].codec_context.codec.canonical_name
        if codec not in CODECS and not codec.startswith("pcm_"):
            raise UnsupportedAudioError(f"unsupported audio codec: {codec}")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        chunks = [
            out.to_ndarray().reshape(-1)
            for frame in itertools.chain(_frames(container), [None])
            for out in resampler.resample(frame)
        ]
    samples = np.concatenate(chunks) if chunks else np.zeros(0, np.int16)
    return samples.astype(np.float32) / 32768.0


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


def partial_of(dest: Path) -> Path:
    return dest.with_name(dest.name + ".partial")


def unique_destination(audio: Path) -> Path:
    candidate = audio.with_suffix(".txt")
    n = 2
    while candidate.exists() or partial_of(candidate).exists():
        candidate = audio.with_name(f"{audio.stem} ({n}).txt")
        n += 1
    return candidate


def transcribe_file(
    model: WhisperModel,
    audio: Path,
    language: str,
    *,
    timestamps: bool,
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
    decode: Callable[[Path], NDArray[np.float32]] = decode_audio,
) -> Path:
    segments, info = model.transcribe(
        decode(audio), language=language, beam_size=7, patience=1.2, repetition_penalty=1.05
    )
    dest = unique_destination(audio)
    partial = partial_of(dest)
    # "x": fails rather than truncate an existing file or follow a link planted at that name.
    out = open(partial, "x", encoding="utf-8")  # closed by the with below
    try:
        with out:  # platform newline (CRLF on Windows)
            for seg in segments:
                out.write(format_line(seg.start, seg.end, seg.text, timestamps) + "\n")
                if cancelled():
                    raise Cancelled
                if info.duration > 0:
                    on_progress(min(1.0, seg.end / info.duration))
        if dest.exists():  # taken while transcribing: keep both, never overwrite
            dest = unique_destination(audio)
        partial.rename(dest)  # on Windows rename fails rather than overwrite
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest
