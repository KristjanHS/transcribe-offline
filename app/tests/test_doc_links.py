import re
from pathlib import Path

REPO = Path(__file__).parents[2]
LINK = re.compile(r"\]\(<?([^)\s>]+)")


def test_every_relative_markdown_link_resolves() -> None:
    docs = REPO / "docs"
    pages = [REPO / "README.md", REPO / "SECURITY.md"]
    pages += [p for p in docs.rglob("*.md") if not p.is_relative_to(docs / "plans")]
    checked, broken = 0, []
    for page in pages:
        for target in LINK.findall(page.read_text(encoding="utf-8")):
            path = target.split("#", 1)[0]
            if not path or re.match(r"(https?|mailto):", target):
                continue
            checked += 1
            if not (page.parent / path).exists():
                broken.append(f"{page.relative_to(REPO).as_posix()}: {target}")
    assert checked, "no relative links found; the scan pattern is broken"
    assert not broken, f"Markdown link target does not exist: {broken}"
