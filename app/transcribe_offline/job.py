"""One transcription job, shared by the GUI and the CLI: no tkinter here."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcribe_offline import engine
from transcribe_offline.models import MODELS_ROOT

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    kind: str  # started | progress | done | failed | finished
    index: int = -1
    text: str = ""
    fraction: float = 0.0


def run_job(
    files: list[Path],
    language: str,
    timestamps: bool,
    events: queue.Queue[Event],
    cancel: threading.Event,
    models_root: Path = MODELS_ROOT,
    load: Callable[..., Any] = engine.load_model,
    transcribe: Callable[..., Path] = engine.transcribe_file,
) -> None:
    """Worker-thread body: load the model once, transcribe files in order, report via events.

    A GPU failure (CUDA DLLs load lazily, so often at the first inference) falls back to the CPU
    for the rest of the job and retries that file once. Nothing is persisted.
    """
    try:
        try:
            model = load(models_root, language)
        except engine.ModelMissingError:
            raise
        except Exception:
            log.exception("Model load failed; retrying on the CPU")
            model = load(models_root, language, gpu=False)
    except Exception as exc:
        log.exception("Model load failed")
        events.put(Event("failed", text=str(exc)))
        events.put(Event("finished"))
        return

    def run(model: Any, audio: Path) -> Path:
        return transcribe(
            model,
            audio,
            language,
            timestamps=timestamps,
            on_progress=lambda f: events.put(Event("progress", fraction=f)),
            cancelled=cancel.is_set,
        )

    gpu_unproven = engine.on_gpu(model)  # until one file has transcribed on it
    for i, audio in enumerate(files):
        if cancel.is_set():
            break
        events.put(Event("started", i, audio.name))
        try:
            try:
                txt = run(model, audio)
            except RuntimeError:  # how ctranslate2 reports CUDA/cuBLAS/out-of-memory errors
                if not gpu_unproven:
                    raise
                log.exception("Transcription on the GPU failed; retrying on the CPU")
                gpu_unproven = False
                model = load(models_root, language, gpu=False)
                txt = run(model, audio)
            gpu_unproven = False
        except engine.Cancelled:
            break
        except Exception as exc:
            log.exception("Transcription failed: %s", audio.name)  # name only: paths are personal
            events.put(Event("failed", i, f"{audio.name}: {exc}"))
        else:
            events.put(Event("done", i, str(txt)))
    events.put(Event("finished"))
