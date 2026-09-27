"""Tkinter GUI: pick audio files, transcribe them in one worker thread, write a .txt beside each."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from transcribe_offline import engine

log = logging.getLogger(__name__)

MODELS_ROOT = Path("models")
LOG_FILE = Path("logs") / "app.log"
POLL_MS = 100


@dataclass(frozen=True)
class Event:
    kind: str  # started | progress | done | failed | finished
    index: int = -1
    text: str = ""
    fraction: float = 0.0


def run_job(
    files: list[Path],
    lang: engine.Lang,
    timestamps: bool,
    events: queue.Queue[Event],
    cancel: threading.Event,
    models_root: Path = MODELS_ROOT,
) -> None:
    """Worker-thread body: load the model once, transcribe files in order, report via events."""
    try:
        model = engine.load_model(models_root, lang)
    except Exception as exc:
        log.exception("Model load failed")
        events.put(Event("failed", text=str(exc)))
        events.put(Event("finished"))
        return
    for i, audio in enumerate(files):
        if cancel.is_set():
            break
        events.put(Event("started", i, audio.name))
        try:
            txt = engine.transcribe_file(
                model,
                audio,
                lang,
                timestamps=timestamps,
                on_progress=lambda f: events.put(Event("progress", fraction=f)),
                cancelled=cancel.is_set,
            )
        except engine.Cancelled:
            break
        except Exception as exc:
            log.exception("Transcription failed: %s", audio)
            events.put(Event("failed", i, f"{audio.name}: {exc}"))
        else:
            events.put(Event("done", i, str(txt)))
    events.put(Event("finished"))


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.files: list[Path] = []
        self.events: queue.Queue[Event] = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.failures: list[str] = []
        self.last_saved: Path | None = None
        self.closing = False
        self.language = tk.StringVar(value="Estonian")
        self.timestamps = tk.BooleanVar(value=True)
        self.status = tk.StringVar()
        self.saved = tk.StringVar()

        root.title("Transcribe (offline)")
        f = ttk.Frame(root, padding=12)
        f.grid(sticky="nsew")
        self.choose_btn = ttk.Button(f, text="Choose audio files…", command=self.choose)
        self.choose_btn.grid(row=0, column=0)
        self.files_label = ttk.Label(f, text="No files selected")
        self.files_label.grid(row=0, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Label(f, text="Language:").grid(row=1, column=0, sticky="w", pady=4)
        for col, name in enumerate(engine.LANGUAGES, start=1):
            ttk.Radiobutton(f, text=name, value=name, variable=self.language).grid(
                row=1, column=col, sticky="w"
            )
        ttk.Checkbutton(f, text="Include timestamps", variable=self.timestamps).grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        self.start_btn = ttk.Button(f, text="Start", command=self.start)
        self.start_btn.grid(row=3, column=0, pady=4, sticky="w")
        self.cancel_btn = ttk.Button(f, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_btn.grid(row=3, column=1, sticky="w")
        ttk.Label(f, textvariable=self.status).grid(row=4, column=0, columnspan=3, sticky="w")
        self.progress = ttk.Progressbar(f, length=320, maximum=1.0)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="we", pady=4)
        ttk.Label(f, textvariable=self.saved).grid(row=6, column=0, columnspan=2, sticky="w")
        self.open_btn = ttk.Button(
            f, text="Open folder", command=self.open_folder, state="disabled"
        )
        self.open_btn.grid(row=6, column=2, sticky="e")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def choose(self) -> None:
        patterns = " ".join(f"*{ext} *{ext.upper()}" for ext in engine.AUDIO_EXTENSIONS)
        chosen = filedialog.askopenfilenames(
            filetypes=[("Audio / video", patterns), ("All files", "*.*")]
        )
        picked = [Path(p) for p in chosen]
        self.files = [p for p in picked if engine.is_audio(p)]
        skipped = [p.name for p in picked if not engine.is_audio(p)]
        self.files_label.config(text=f"{len(self.files)} files selected")
        self.status.set(f"skipped: {', '.join(skipped)} — not an audio file" if skipped else "")

    def start(self) -> None:
        if not self.files or self.worker is not None:
            return
        self.cancel.clear()
        self.failures = []
        self.progress["value"] = 0
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        args = (list(self.files), engine.LANGUAGES[self.language.get()], self.timestamps.get())
        self.status.set("Loading model…")
        self.worker = threading.Thread(target=run_job, args=(*args, self.events, self.cancel))
        self.worker.daemon = True
        self.worker.start()
        self.root.after(POLL_MS, self.poll)

    def poll(self) -> None:
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            if ev.kind == "started":
                self.progress["value"] = 0
                self.status.set(f"File {ev.index + 1} of {len(self.files)}: {ev.text}")
            elif ev.kind == "progress":
                self.progress["value"] = ev.fraction
            elif ev.kind == "done":
                self.last_saved = Path(ev.text)
                self.saved.set(f"Saved: {ev.text}")
                self.open_btn.config(state="normal")
            elif ev.kind == "failed":
                self.failures.append(ev.text)
            elif ev.kind == "finished":
                self.finish()
                return
        self.root.after(POLL_MS, self.poll)

    def finish(self) -> None:
        if self.closing:
            self.root.destroy()
            return
        self.worker = None
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        if self.failures:
            self.status.set(f"Finished with {len(self.failures)} failure(s).")
            messagebox.showerror("Some files failed", "\n".join(self.failures))
        else:
            self.status.set("Cancelled." if self.cancel.is_set() else "Finished.")

    def open_folder(self) -> None:
        if self.last_saved is not None and sys.platform == "win32":
            # The only OS launch in the app (SECURITY.md, "Does").
            os.startfile(self.last_saved.parent)  # noqa: S606, TID251  # nosec B606

    def on_close(self) -> None:
        if self.worker is None:
            self.root.destroy()
        elif not self.closing and messagebox.askyesno("Transcribing", "Cancel and quit?"):
            self.closing = True  # finish() destroys the window once the worker has removed .partial
            self.cancel.set()
            for btn in (self.choose_btn, self.cancel_btn, self.open_btn):
                btn.config(state="disabled")


def main() -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root = tk.Tk()
    App(root)
    root.mainloop()
