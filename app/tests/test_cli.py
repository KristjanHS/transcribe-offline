import io
import queue
import threading
from pathlib import Path

import pytest

from transcribe_offline import cli
from transcribe_offline.job import Event


def fake_job(fail: frozenset[str]):
    def job(
        files: list[Path], language: str, timestamps: bool, events: queue.Queue[Event], _c: object
    ) -> None:
        for i, audio in enumerate(files):
            events.put(Event("started", i, audio.name))
            if audio.name in fail:
                events.put(Event("failed", i, f"{audio.name}: broken"))
            else:
                events.put(Event("done", i, str(audio.with_suffix(".txt"))))
        events.put(Event("finished"))

    return job


def run(argv: list[str], fail: frozenset[str] = frozenset()) -> tuple[int, str, list[Path]]:
    out = io.StringIO()
    allowed: list[Path] = []
    code = cli.main(argv, fake_job(fail), out, io.StringIO(), allowed.append)
    return code, out.getvalue(), allowed


def test_prints_each_transcript_and_allows_writes_beside_the_audio(tmp_path: Path) -> None:
    a, b = tmp_path / "a.wav", tmp_path / "sub" / "b.mp3"
    code, out, allowed = run(["-l", "et", str(a), str(b)])
    assert code == 0
    assert out.splitlines() == [str(a.with_suffix(".txt")), str(b.with_suffix(".txt"))]
    assert allowed == [a.parent, b.parent]


def test_any_failure_or_non_audio_file_exits_1(tmp_path: Path) -> None:
    assert run(["-l", "en", str(tmp_path / "a.wav")], frozenset({"a.wav"}))[0] == 1
    code, out, allowed = run(["-l", "en", str(tmp_path / "notes.docx")])
    assert (code, out, allowed) == (1, "", [])


def test_language_is_required_and_checked() -> None:
    for argv in (["a.wav"], ["-l", "de", "a.wav"]):
        with pytest.raises(SystemExit):
            cli.parse(argv)


def test_passes_language_and_timestamps_to_the_job(tmp_path: Path) -> None:
    seen: list[tuple[str, bool]] = []

    def job(
        files: list[Path],
        language: str,
        timestamps: bool,
        events: queue.Queue[Event],
        _c: threading.Event,
    ) -> None:
        seen.append((language, timestamps))
        events.put(Event("finished"))

    cli.main(
        ["-l", "en", "--no-timestamps", str(tmp_path / "a.wav")],
        job,
        io.StringIO(),
        io.StringIO(),
        lambda _p: None,
    )
    assert seen == [("en", False)]
