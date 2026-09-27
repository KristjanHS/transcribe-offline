"""Install-time model download (`python -m transcribe_offline.setup`). The only module with network.

Fetches every pinned file into models/<lang>/, verifies its SHA-256, skips files already verified.
"""

from __future__ import annotations

import hashlib
import logging
import ssl
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO

from transcribe_offline.models import MODELS, ModelPin

log = logging.getLogger(__name__)

MODELS_ROOT = Path("models")
CHUNK = 1 << 20
LOG_EVERY = 100 << 20

Fetch = Callable[[str], IO[bytes]]


class ChecksumError(Exception):
    pass


def open_url(url: str) -> IO[bytes]:
    # Windows cert store via the default context; urllib honours HTTPS_PROXY.
    context = ssl.create_default_context()
    return urllib.request.urlopen(url, context=context, timeout=60)  # noqa: S310 — https pins only


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected: str, fetch: Fetch = open_url) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    digest = hashlib.sha256()
    done = 0
    try:
        with fetch(url) as resp, open(partial, "wb") as out:
            total_mb = (getattr(resp, "length", None) or 0) >> 20
            while chunk := resp.read(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done % LOG_EVERY < len(chunk):
                    log.info("  %s: %d / %d MB", dest.name, done >> 20, total_mb)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    actual = digest.hexdigest()
    if actual != expected:
        partial.unlink()
        raise ChecksumError(f"{dest}: expected SHA-256 {expected}, got {actual}")
    partial.replace(dest)


def ensure_model(pin: ModelPin, folder: Path, fetch: Fetch = open_url) -> None:
    for name, expected in pin.files.items():
        dest = folder / name
        if dest.is_file() and sha256_of(dest) == expected:
            log.info("OK       %s", dest)
            continue
        log.info("Download %s", pin.url(name))
        download(pin.url(name), dest, expected, fetch)


def main(root: Path = MODELS_ROOT, fetch: Fetch = open_url) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    try:
        for model_dir, pin in MODELS.items():
            ensure_model(pin, root / model_dir, fetch)
    except ChecksumError as exc:
        log.error("Checksum mismatch, file deleted: %s", exc)
        return 1
    except OSError as exc:
        log.error("Download failed: %s", exc)
        return 1
    log.info("Models ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
