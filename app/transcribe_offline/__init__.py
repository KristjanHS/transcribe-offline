"""Minimal offline speech-to-text GUI."""

import os
from pathlib import Path

# Set on first import of the package, before anything can import huggingface_hub (via
# faster_whisper): never contact the Hub at runtime.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

APP_ROOT = Path(__file__).resolve().parents[1]  # the app folder, whatever the working directory
