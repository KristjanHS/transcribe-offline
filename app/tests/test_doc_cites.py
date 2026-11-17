import re
import subprocess  # noqa: TID251  # test-only: lists tracked files; never imported by the app
from pathlib import Path

REPO = Path(__file__).parents[2]
CITE = re.compile(r"\d{4}-\d{2}-\d{2}-[\w.-]+\.md")
KNOWN_DANGLING: set[str] = set()  # baseline of cites allowed to stay unresolved; keep it empty


def test_every_cited_dated_doc_is_tracked() -> None:
    listing = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout.decode()
    tracked = [REPO / name for name in listing.split("\0") if name and (REPO / name).is_file()]
    names = {path.name for path in tracked}
    dangling = set()
    for path in tracked:
        data = path.read_bytes()
        if b"\0" not in data:
            text = data.decode(errors="replace")
            dangling |= {f"{path.relative_to(REPO).as_posix()}: {c}" for c in CITE.findall(text)}
    unresolved = {d for d in dangling if d.split(": ")[-1] not in names | KNOWN_DANGLING}
    assert not unresolved, f"cited doc is not a tracked file: {sorted(unresolved)}"
