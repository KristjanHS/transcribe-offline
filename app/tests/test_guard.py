import os
import tkinter as tk
from pathlib import Path

import pytest

from transcribe_offline.app import hide_tcl_commands
from transcribe_offline.guard import Guard


@pytest.fixture
def guard(tmp_path: Path) -> Guard:
    g = Guard(root=tmp_path / "app")
    g.allow_dir(tmp_path / "audio")
    return g


@pytest.mark.parametrize("event", ["socket.connect", "socket.getaddrinfo", "subprocess.Popen"])
def test_network_and_processes_are_blocked(guard: Guard, event: str) -> None:
    with pytest.raises(PermissionError, match=event):
        guard(event, ())


def test_writes_only_inside_the_app_or_beside_chosen_audio(guard: Guard, tmp_path: Path) -> None:
    guard("open", (tmp_path / "app" / "logs" / "app.log", "w", 0))
    guard("open", (tmp_path / "audio" / "talk.txt.partial", "x", 0))
    guard("open", (tmp_path / "elsewhere.txt", "r", 0))  # reading is not restricted
    for path in (tmp_path / "elsewhere.txt", tmp_path / "audio" / "sub" / "talk.txt"):
        with pytest.raises(PermissionError):
            guard("open", (path, "w", 0))
    with pytest.raises(PermissionError):
        guard("open", (str(tmp_path / "x"), None, os.O_WRONLY | os.O_CREAT))  # os.open


def test_rename_and_remove_outside_are_blocked(guard: Guard, tmp_path: Path) -> None:
    partial = tmp_path / "audio" / "talk.txt.partial"
    guard("os.rename", (partial, tmp_path / "audio" / "talk.txt", -1, -1))
    with pytest.raises(PermissionError):
        guard("os.rename", (partial, tmp_path / "talk.txt", -1, -1))
    with pytest.raises(PermissionError):
        guard("os.remove", (tmp_path / "talk.txt", -1))


def test_tcl_exec_and_socket_are_hidden() -> None:
    interp = tk.Tcl()
    hide_tcl_commands(interp)
    for cmd in ("exec", "socket"):
        with pytest.raises(tk.TclError, match="invalid command name"):
            interp.call(cmd)
