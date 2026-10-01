---
name: Installer hash discipline
description: Edits under installer/ rebuild Transcribe-Setup.exe and reset its SmartScreen reputation
paths:
  - "installer/**"
---

Any edit here rebuilds `Transcribe-Setup.exe` at the next release (`.github/scripts/setup-exe-reuse.sh`) and the new hash restarts SmartScreen reputation from zero.
Batch installer changes into one release; never touch `installer/` for cosmetics.
