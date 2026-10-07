import hashlib
import io
import sys
from pathlib import Path
from typing import IO, Any

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


class FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout, self.returncode = stdout, returncode
        self.cmd: list[str] = []
        self.kwargs: dict[str, Any] = {}

    def __call__(self, cmd: list[str], **kwargs: Any) -> Any:
        self.cmd, self.kwargs = cmd, kwargs
        return self


def test_detect_gpu_reads_first_gpu_from_system32_nvidia_smi() -> None:
    run = FakeRun(
        "NVIDIA GeForce RTX 3060, Laptop, 12288, 560.94, 8.6\nTesla T4, 15360, 560.94, 7.5\n"
    )
    info = setup.detect_gpu({"SystemRoot": "D:\\Win"}, run=run, platform="win32")
    assert info == setup.GpuInfo("NVIDIA GeForce RTX 3060, Laptop", 12288, (560, 94), (8, 6))
    assert run.cmd[0].startswith("D:\\Win") and run.cmd[0].endswith("nvidia-smi.exe")
    assert str(info) == "NVIDIA GeForce RTX 3060, Laptop (12 GB, driver 560.94)"


@pytest.mark.parametrize(
    ("env", "smi"),
    [({"WSL_DISTRO_NAME": "Ubuntu"}, "/usr/lib/wsl/lib/nvidia-smi"), ({}, "/usr/bin/nvidia-smi")],
)
def test_detect_gpu_on_linux_runs_the_drivers_nvidia_smi(env: dict[str, str], smi: str) -> None:
    run = FakeRun("NVIDIA GeForce RTX 3070 Laptop GPU, 8192, 610.88, 8.6\n")
    info = setup.detect_gpu(env, run=run, platform="linux")
    assert info is not None and info.driver == (610, 88)
    assert run.cmd[0] == smi


@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [
        ("", 0),
        ("RTX 3060, [N/A], 560.94, 8.6\n", 0),
        ("RTX 3060, 12288, 560.94\n", 0),  # a driver without the compute_cap field
        ("RTX 3060, 12288, 560.94, 8.6\n", 9),
    ],
    ids=["no-output", "unparsable", "no-compute-cap", "exit-code"],
)
def test_detect_gpu_any_doubt_is_none(stdout: str, returncode: int) -> None:
    assert setup.detect_gpu({}, run=FakeRun(stdout, returncode)) is None


def test_detect_gpu_missing_tool_is_none() -> None:
    def run(*_a: Any, **_kw: Any) -> Any:
        raise FileNotFoundError("nvidia-smi")

    assert setup.detect_gpu({}, run=run) is None


@pytest.mark.parametrize(
    ("info", "platform", "capable"),
    [
        (setup.GpuInfo("RTX 3050", 4096, (528, 33), (8, 6)), "win32", True),
        (setup.GpuInfo("RTX 3050", 4096, (528, 24), (8, 6)), "win32", False),  # below CUDA 12
        (
            setup.GpuInfo("RTX 3050", 4096, (528, 24), (8, 6)),
            "linux",
            True,
        ),  # Linux floor 525.60.13
        (setup.GpuInfo("RTX 3050", 4096, (525, 53), (8, 6)), "linux", False),
        (setup.GpuInfo("RTX 3050", 4096, (528, 24), (8, 6)), "wsl", False),  # Windows' driver
        (setup.GpuInfo("GTX 1050", 3072, (560, 94), (6, 1)), "win32", False),  # too little VRAM
        (setup.GpuInfo("GTX 1070", 8192, (560, 94), (6, 1)), "win32", False),  # Pascal: no float16
        (None, "win32", False),
    ],
)
def test_gpu_capable_needs_driver_and_vram(
    info: setup.GpuInfo | None, platform: str, capable: bool
) -> None:
    env = {"WSL_DISTRO_NAME": "Ubuntu"} if platform == "wsl" else {}
    assert setup.gpu_capable(info, "linux" if platform == "wsl" else platform, env) is capable


def test_sync_gpu_group_runs_bundled_uv_frozen(tmp_path: Path) -> None:
    run = FakeRun(returncode=1)
    assert setup.sync_gpu_group(tmp_path, run=run, platform="win32") is False
    assert run.cmd == [
        str(tmp_path / ".uv" / "uv.exe"),
        "sync",
        "--frozen",
        "--no-dev",
        "--group",
        "gpu",
        "--python",
        "{}.{}.{}".format(*sys.version_info[:3]),
    ]
    assert run.kwargs["cwd"] == tmp_path
    setup.sync_gpu_group(tmp_path, run=run, platform="linux")
    assert run.cmd[0] == "uv"  # the user's own uv, on PATH


def fail_fetch(url: str) -> IO[bytes]:
    raise OSError("offline")


def test_main_capable_gpu_syncs_before_models_and_stops_if_sync_fails(tmp_path: Path) -> None:
    def gpu() -> setup.GpuInfo:
        return setup.GpuInfo("RTX 3060", 12288, (560, 94), (8, 6))

    assert setup.main(tmp_path, refuse, detect=gpu, sync=lambda: False) == 1


def test_main_without_gpu_skips_sync(tmp_path: Path) -> None:
    def no_sync() -> bool:
        raise AssertionError("gpu group synced without a capable GPU")

    assert setup.main(tmp_path, fail_fetch, detect=lambda: None, sync=no_sync) == 1
