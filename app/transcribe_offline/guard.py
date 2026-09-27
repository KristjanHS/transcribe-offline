"""Runtime guard: a Python audit hook (PEP 578) that refuses network, child processes, and writes
outside the app folder or beside the chosen audio files. `__main__` installs it before anything
else; once installed it cannot be removed. It sees Python-level calls only, not native code
(FFmpeg, CTranslate2) — see SECURITY.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from transcribe_offline import APP_ROOT

BLOCKED = {
    "socket.connect",
    "socket.bind",
    "socket.sendto",
    "socket.getaddrinfo",
    "subprocess.Popen",
    "os.system",
    "os.startfile",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.fork",
    "os.forkpty",
}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
PATH_ARGS = {"os.remove": 1, "os.rename": 2, "os.mkdir": 1, "os.rmdir": 1}  # event -> path args


def _norm(path: object) -> str:
    # String operations only: a syscall inside the hook could raise events of its own.
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))  # pyright: ignore[reportArgumentType]


class Guard:
    def __init__(self, root: Path = APP_ROOT) -> None:
        self.root = _norm(root)
        self.audio_dirs: set[str] = set()

    def allow_dir(self, folder: Path) -> None:
        """Allow writes directly inside `folder` (where the transcripts of its audio go)."""
        self.audio_dirs.add(_norm(folder))

    def writable(self, path: object) -> bool:
        if isinstance(path, int):  # a descriptor that is already open
            return True
        p = _norm(path)
        return p.startswith(self.root + os.sep) or os.path.dirname(p) in self.audio_dirs

    def __call__(self, event: str, args: tuple[object, ...]) -> None:
        if event in BLOCKED:
            raise PermissionError(f"Blocked at runtime: {event}")
        if event == "open":
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & WRITE_FLAGS
            )
            paths = [path] if writing else []
        else:
            paths = args[: PATH_ARGS.get(event, 0)]
        for path in paths:
            if not self.writable(path):
                raise PermissionError(f"Blocked at runtime: {event} {path}")


GUARD = Guard()


def install() -> None:
    sys.addaudithook(GUARD)
