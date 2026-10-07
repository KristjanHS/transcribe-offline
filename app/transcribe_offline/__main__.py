"""Entry point: `python -m transcribe_offline` opens the GUI; with arguments it is the CLI."""

import sys

from transcribe_offline import guard

guard.install()  # first: every later import and call runs under the audit hook

if len(sys.argv) > 1:
    from transcribe_offline.cli import main
else:
    from transcribe_offline.app import main

sys.exit(main())
