"""Install time (`python -m transcribe_offline.setup`); the only module with network or processes.

On a capable NVIDIA GPU, adds the locked `gpu` dependency group (uv sync). Then fetches every pinned
model file into models/<lang>/, verifies its SHA-256, skips files already verified.
"""

from __future__ import annotations

import hashlib
import http.client
import logging
import os
import ssl
import subprocess  # nosec B404  # nvidia-smi and uv only, list args
import sys
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from transcribe_offline import APP_ROOT
from transcribe_offline.models import MODELS, MODELS_ROOT, ModelPin

log = logging.getLogger(__name__)

CHUNK = 1 << 20
LOG_EVERY = 100 << 20

MIN_GPU_DRIVER = {"win32": (528, 33), "linux": (525, 60, 13)}  # CUDA 12.0
MIN_GPU_VRAM_MIB = 4000
MIN_GPU_COMPUTE = (7, 0)  # ctranslate2 runs float16 on CUDA only from Volta on

Fetch = Callable[[str], IO[bytes]]
Run = Callable[..., Any]


class ChecksumError(Exception):
    pass


@dataclass(frozen=True)
class GpuInfo:
    name: str
    vram_mib: int
    driver: tuple[int, ...]
    compute: tuple[int, ...]

    def __str__(self) -> str:
        driver = ".".join(map(str, self.driver))
        return f"{self.name} ({self.vram_mib / 1024:.0f} GB, driver {driver})"


def detect_gpu(
    env: Mapping[str, str] = os.environ, run: Run = subprocess.run, platform: str = sys.platform
) -> GpuInfo | None:
    """First GPU from nvidia-smi (ships with every NVIDIA driver); None on any doubt."""
    if platform == "win32":
        smi = str(Path(env.get("SystemRoot", "C:\\Windows"), "System32", "nvidia-smi.exe"))
    else:  # on WSL the Windows driver provides it
        smi = "/usr/lib/wsl/lib/nvidia-smi" if "WSL_DISTRO_NAME" in env else "/usr/bin/nvidia-smi"
    cmd = [
        smi,
        "--query-gpu=name,memory.total,driver_version,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = run(cmd, capture_output=True, text=True, timeout=15, check=False)
        line = result.stdout.splitlines()[0]
        name, vram, driver, compute = (part.strip() for part in line.rsplit(",", 3))
        info = GpuInfo(name, int(float(vram)), version(driver), version(compute))
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
    return info if result.returncode == 0 else None


def version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in text.split("."))


def gpu_capable(
    info: GpuInfo | None, platform: str = sys.platform, env: Mapping[str, str] = os.environ
) -> bool:
    floor = MIN_GPU_DRIVER["win32" if "WSL_DISTRO_NAME" in env else platform]  # WSL: Windows driver
    return (
        info is not None
        and info.vram_mib >= MIN_GPU_VRAM_MIB
        and info.driver >= floor
        and info.compute >= MIN_GPU_COMPUTE
    )


def sync_gpu_group(
    root: Path = APP_ROOT, run: Run = subprocess.run, platform: str = sys.platform
) -> bool:
    # The installer's environment (UV_* settings, cleared variables) is inherited unchanged.
    python = "{}.{}.{}".format(
        *sys.version_info[:3]
    )  # as the installer's sync, so UV_PYTHON can't recreate .venv
    cmd = [
        str(root / ".uv" / "uv.exe") if platform == "win32" else "uv",  # Linux: the user's own uv
        "sync",
        "--frozen",
        "--no-dev",
        "--group",
        "gpu",
        "--python",
        python,
    ]
    return run(cmd, cwd=root, check=False).returncode == 0


def open_url(url: str) -> IO[bytes]:
    # Only https URLs built from models.py pins. Windows cert store via the default context;
    # urllib honours HTTPS_PROXY.
    context = ssl.create_default_context()
    return urllib.request.urlopen(url, context=context, timeout=60)  # noqa: S310  # nosec B310


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


def main(
    root: Path = MODELS_ROOT,
    fetch: Fetch = open_url,
    detect: Callable[[], GpuInfo | None] = detect_gpu,
    sync: Callable[[], bool] = sync_gpu_group,
) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    info = detect()
    if not gpu_capable(info):
        log.info("%s: CPU only", info or "No NVIDIA GPU found")
    else:
        log.info("%s: installing GPU libraries (~1.3 GB)", info)
        if not sync():
            log.error("Installing the GPU libraries failed; run setup again.")
            return 1
    try:
        for model_dir, pin in MODELS.items():
            ensure_model(pin, root / model_dir, fetch)
    except ChecksumError as exc:
        log.error("Checksum mismatch, file deleted: %s", exc)
        return 1
    except (OSError, http.client.HTTPException) as exc:
        log.error("Download failed: %s", exc)
        return 1
    log.info("Models ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
