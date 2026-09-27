import hashlib
import io
from pathlib import Path
from typing import IO

import pytest

from transcribe_offline import setup
from transcribe_offline.models import MODELS, REQUIRED_FILES, ModelPin

DATA = b"model bytes" * 1000
GOOD = hashlib.sha256(DATA).hexdigest()


def serve(url: str) -> IO[bytes]:
    return io.BytesIO(DATA)


def refuse(url: str) -> IO[bytes]:
    raise AssertionError(f"unexpected fetch: {url}")


def test_every_pin_covers_the_required_files() -> None:
    for pin in MODELS.values():
        assert sorted(pin.files) == sorted(REQUIRED_FILES)
        assert pin.url("model.bin").startswith("https://huggingface.co/")
        assert pin.commit in pin.url("model.bin")


def test_download_good_hash(tmp_path: Path) -> None:
    dest = tmp_path / "et" / "model.bin"
    setup.download("https://x/model.bin", dest, GOOD, fetch=serve)
    assert dest.read_bytes() == DATA
    assert not dest.with_name("model.bin.partial").exists()


def test_download_bad_hash_deletes_file(tmp_path: Path) -> None:
    dest = tmp_path / "model.bin"
    with pytest.raises(setup.ChecksumError, match="model.bin"):
        setup.download("https://x/model.bin", dest, "0" * 64, fetch=serve)
    assert list(tmp_path.iterdir()) == []


def test_leftover_partial_is_replaced(tmp_path: Path) -> None:
    dest = tmp_path / "model.bin"
    dest.with_name("model.bin.partial").write_bytes(b"truncated")
    setup.download("https://x/model.bin", dest, GOOD, fetch=serve)
    assert dest.read_bytes() == DATA
    assert list(tmp_path.iterdir()) == [dest]


def test_ensure_model_skips_verified_and_refetches_corrupt(tmp_path: Path) -> None:
    pin = ModelPin(repo="r/m", commit="c0ffee", subfolder="", files={"model.bin": GOOD})
    (tmp_path / "model.bin").write_bytes(DATA)
    setup.ensure_model(pin, tmp_path, fetch=refuse)
    (tmp_path / "model.bin").write_bytes(b"corrupt")
    setup.ensure_model(pin, tmp_path, fetch=serve)
    assert (tmp_path / "model.bin").read_bytes() == DATA
