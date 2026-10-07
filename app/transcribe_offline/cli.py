"""Command line: transcribe audio files, write a .txt beside each, print each transcript's path."""

from __future__ import annotations

import argparse
import logging
import queue
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from transcribe_offline import engine, guard
from transcribe_offline.job import Event, run_job

log = logging.getLogger(__name__)


def parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="transcribe", description="Transcribe audio offline; each .txt goes beside its audio."
    )
    parser.add_argument("-l", "--language", required=True, choices=engine.LANGUAGES.values())
    parser.add_argument("--no-timestamps", action="store_true", help="no [start --> end] times")
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    job: Callable[..., Any] = run_job,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    allow_dir: Callable[[Path], None] = guard.GUARD.allow_dir,
) -> int:
    """0 when every file was transcribed, 1 on any failure, 130 when interrupted."""
    args = parse(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=err)
    files = [p.absolute() for p in args.files if engine.is_audio(p)]
    failures = [f"{p}: not an audio file" for p in args.files if not engine.is_audio(p)]
    for p in files:
        allow_dir(p.parent)  # the transcripts go beside the audio
    events: queue.Queue[Event] = queue.Queue()
    cancel = threading.Event()
    timestamps = not args.no_timestamps
    worker = threading.Thread(target=job, args=(files, args.language, timestamps, events, cancel))
    # Ctrl+C only cancels: the worker removes the .partial and frees the model before we exit.
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        if files:  # no model load when nothing is audio
            worker.start()
            while (ev := events.get()).kind != "finished":
                if ev.kind == "started":
                    log.info("File %d of %d: %s", ev.index + 1, len(files), ev.text)
                elif ev.kind == "done":
                    out.write(ev.text + "\n")
                elif ev.kind == "failed":
                    failures.append(ev.text)
            worker.join()  # the model is freed on the worker; exiting first aborts in CTranslate2
    finally:
        signal.signal(signal.SIGINT, previous)
    for failure in failures:
        log.error("Failed: %s", failure)
    if cancel.is_set():
        return 130
    return 1 if failures else 0
