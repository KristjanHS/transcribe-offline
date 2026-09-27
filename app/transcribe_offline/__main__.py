"""Entry point: `python -m transcribe_offline`, run with the install folder as working directory."""

from transcribe_offline import guard

guard.install()  # first: every later import and call runs under the audit hook

from transcribe_offline.app import main  # noqa: E402

main()
