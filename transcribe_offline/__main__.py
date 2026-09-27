"""Entry point: `python -m transcribe_offline`, run with the install folder as working directory."""

import os

# Before faster_whisper is imported: never contact the Hugging Face Hub at runtime.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from transcribe_offline.app import main  # noqa: E402

main()
