# How it was built

Claude Code wrote most of the code from the plans in [`docs/plans/archive/`](plans/archive). I settled
each plan's open questions, reviewed every stage and ran the Windows checks myself. The agent setup and
workflow are in [claudeconf](https://github.com/KristjanHS/claudeconf).

## 1. A unit test that proved less than it claimed

Plan: [Security critique](plans/archive/2026-09-27-security-critique-todo.md), item S4.1. Tkinter's Tcl
interpreter has its own `exec` and `socket` commands, so `root.tk.call("exec", ...)` gets past the
Python import ban. The proposed fix was to hide both commands right after `tk.Tk()`.

The agent wrote `hide_tcl_commands()`, plus a test asserting that a plain call to `exec` or `socket`
now fails with "invalid command name". The SECURITY.md threat model then listed Tcl as covered by a
unit test.

The review stage found three one-line ways around the hiding: `interp invokehidden`, `interp expose`
and `open "|cmd"`. The test only tried the plain call, so it passed with the bypass still open. I had
the hiding and its test removed. The import test now rejects any `.call` or `.eval` attribute in the
runtime modules, which means our code never hands Tcl a string to run.

```diff
--- a/app/tests/test_imports.py
+++ b/app/tests/test_imports.py
-DYNAMIC = {"__import__", "importlib", "eval", "exec"}
-TCL = {"exec", "socket", "open", "load", "expose"}  # Tcl commands our code must never .call()
+DYNAMIC = {"__import__", "importlib", "eval", "exec", "call"}  # .call/.eval also run Tcl
--- a/app/transcribe_offline/app.py
+++ b/app/transcribe_offline/app.py
-def hide_tcl_commands(interp: tk.Tk) -> None:
-    """Hide Tcl's own exec and socket commands: tkinter would otherwise bypass the import ban."""
-    for cmd in ("exec", "socket"):
-        interp.tk.call("interp", "hide", "", cmd)
```

Outcome: 4 lines added, 25 removed (`git show --stat`). SECURITY.md now says Tcl is native code the
runtime audit hook cannot see and names `test_imports.py` as the check. A planted
`root.tk.call("exec", "calc")` in `app.py` fails that test.

## 2. Two gaps found in a finished security stage

Items S2.1 and S4.2 of the same critique asked for two things: decode audio in our own code behind
FFmpeg format and codec allow-lists, and add a runtime audit hook that refuses network access and child
processes.

The agent opened files with `protocol_whitelist` and `format_whitelist`, then checked the codec name
once the file was open. The audit hook blocked `socket.connect`, `socket.bind`, `socket.sendto` and
`socket.getaddrinfo`.

The final review found that `av.open()` probes the file by starting each stream's decoder, and that
happens before our codec check runs. A crafted file could still reach any decoder FFmpeg ships. The fix
passes FFmpeg's own `codec_whitelist` to `av.open()`. The hook had also missed `sendmsg` and DNS
lookups, so it now blocks socket creation and the four lookup functions. A later review caught a
smaller error in SECURITY.md, which said importing `faster_whisper` loads `http`. On Linux,
`sys.modules` showed `ssl` in that list and `http` absent. The doc was corrected, and a new test
asserts that none of the excluded packages load on that import.

```diff
--- a/app/transcribe_offline/engine.py
+++ b/app/transcribe_offline/engine.py
+# Decoders FFmpeg may open while probing the file, before the CODECS check in decode_audio runs.
+DECODERS = (
+    "mp3float,mp3,aac,alac,flac,opus,vorbis,wmav1,wmav2,wmapro,pcm_u8,pcm_s16le,pcm_s16be,"
+    "pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_f64le,pcm_alaw,pcm_mulaw"
+)
+OPTIONS = {"protocol_whitelist": "file", "format_whitelist": FORMATS, "codec_whitelist": DECODERS}
--- a/app/transcribe_offline/guard.py
+++ b/app/transcribe_offline/guard.py
-    "socket.connect",
-    "socket.bind",
-    "socket.sendto",
+    "socket.__new__",
     "socket.getaddrinfo",
+    "socket.gethostbyname",
+    "socket.gethostbyaddr",
+    "socket.getnameinfo",
```

Both fixes have a test that fails without them. The new engine test builds an `.mkv` with AC3 audio
and MPEG-4 video; without the decoder whitelist, opening it starts both decoders and the test fails with
`(<AudioFormat fltp>, yuv420p) != (None, None)`. Dropping the new hook entries fails 2 guard tests.

## 3. Windows App Control and an antivirus

Plans: [App Control](plans/archive/smart-app-control.md), then
[Exe installer](plans/archive/2026-09-28-exe-installer.md) and
[Trust without a certificate](plans/archive/2026-10-01-trust-without-certificate.md).

Release v0.1.1 locked the newest native wheels, PyAV 18.1.0 among them. On a managed Windows 11 PC the
app failed at start with `DLL load failed while importing _core: An Application Control policy has
blocked this file`. The exe installer that came next fetched uv with `curl.exe` and unpacked it with
`tar.exe`.

I set two limits before any fix: no paid certificate, and no allow rules from an administrator. The
plan listed checks to run on that PC before changing code. The same PC already ran
[stt-faster](https://github.com/KristjanHS/stt-faster), another app of mine, on older builds of the
same four native wheels, and PyAV had an upstream report of 18.1.0 being blocked (PyAV#2418). So the
four wheels are pinned to the versions stt-faster ships. PyAV 16 raises a different error class, and
its `with` block can swallow exceptions, so `decode_audio` now closes the file in `try/finally`.

Then Bitdefender quarantined the v0.2.4 setup exe. What it scores is a small unsigned exe
starting `curl.exe` and `tar.exe`, writing an exe to disk, and driving `WScript.Shell` through COM.
`Setup.cs` now downloads with `WebClient`, unzips with `ZipFile` and starts only uv and Python.

```diff
--- a/app/pyproject.toml
+++ b/app/pyproject.toml
+# Native wheels Windows App Control (Smart App Control / ISG) already trusts by reputation;
+# av 18.1.0 was blocked. Bump only to versions proven on an enforcing PC.
+constraint-dependencies = ["av==16.0.1", "ctranslate2==4.6.2", "numpy==2.3.5", "tokenizers==0.22.1"]
--- a/installer/Setup.cs
+++ b/installer/Setup.cs
-            Run(Path.Combine(sys, "curl.exe"), @"-fL -o .uv\uv.zip " + Quote(url), app);
+            Download("https://github.com/astral-sh/uv/releases/download/" + pins["UV_VERSION"]
+                + "/uv-x86_64-pc-windows-msvc.zip", zip);
@@
-            Run(Path.Combine(sys, "tar.exe"), @"-xf .uv\uv.zip -C .uv", app);
+            Unzip(zip, uvDir);
```

Where that leaves things: the pinned set matches one that already runs on that PC. The exe is rebuilt only when
`installer/` changes, so its hash, and the reputation Windows ties to it, carries over between
releases. The repo holds no record yet of how Bitdefender scores the managed-code exe, and SECURITY.md
lists App Control's view of the NVIDIA GPU DLLs as not verified.

## 4. Agent-built machinery I deleted

Plan: [Reviewer-trust simplification](plans/archive/2026-09-27-reviewer-trust-simplification.md). Its
goal was to shrink what a security reviewer has to read or take on trust.

Earlier stages had left these in place:

- a byte-exact parity test against four golden transcripts from stt-faster, with a rule to regenerate
  them whenever ctranslate2, av, tokenizers or numpy changed version
- a runtime set of 24 packages, including huggingface_hub's HTTP client and its Xet downloader
- a Desktop shortcut made through PowerShell and COM, and an `uninstall.bat`
- an "Open folder" button, the app's only process launch
- a rotating log that also wrote `app.log.1` and `app.log.2`, which SECURITY.md did not list

I dropped stt-faster parity as a requirement, since a reviewer cannot check another repo's output. The
parity test became a real-model smoke test that looks for one known word per language. Excluding the
Hub's network packages took the runtime set from 24 to 12 (`uv export --no-dev`). The shortcut, the
button and the rotating log went too.

```diff
--- a/tests/test_golden.py
+++ /dev/null
-    golden = FIXTURES / "golden" / f"{lang.code}-{'ts' if timestamps else 'plain'}.txt"
-    # Byte-exact except CRLF (Windows output) is normalised to the LF goldens.
-    assert out.read_bytes().replace(b"\r\n", b"\n") == golden.read_bytes().replace(b"\r\n", b"\n")
--- /dev/null
+++ b/tests/test_models.py
+    assert word in out.read_text(encoding="utf-8")
--- a/transcribe_offline/app.py
+++ b/transcribe_offline/app.py
-    def open_folder(self) -> None:
-        if self.last_saved is not None and sys.platform == "win32":
-            # The only OS launch in the app (SECURITY.md, "Does").
-            os.startfile(self.last_saved.parent)  # noqa: S606, TID251  # nosec B606
```

Outcome, from `git show --stat`: the smoke-test swap added 32 lines and removed 70 across 12 files. The
shortcut removal was +7/-17, the button +4/-22, the log change +2/-4. SECURITY.md now says "no child
processes at runtime" with no exception, and the app writes exactly one log file, `logs\app.log`.
Changing the expected English word to "Vicksburg" fails the smoke test.

## 5. A CI check that caught a real write

This one is item A2 of the simplification plan. Release CI installs the app as a standard Windows user
and then checks that nothing was written outside the app folder. The agent's version of that check
tested four paths: `python*.exe` under `.local\bin`, uv's HKCU registry key,
`%LOCALAPPDATA%\uv` and `%APPDATA%\uv`.

A list of paths only catches the writes someone already predicted. I had it replaced with a timestamp
diff: touch a marker file before `install.bat`, then fail on any file under the user profile that is
newer than the marker. There was no PowerShell to test it on, so it shipped unvalidated and waited for
the first Windows release run.

```diff
--- a/.github/workflows/release.yml
+++ b/.github/workflows/release.yml
-          $paths = "$env:USERPROFILE\.local\bin\python*.exe", "HKCU:\Software\Python\Astral",
-            "$env:LOCALAPPDATA\uv", "$env:APPDATA\uv"
+          $t0 = (Get-Item "$env:RUNNER_TEMP\install-t0").LastWriteTimeUtc
+          $new = @(Get-ChildItem $env:USERPROFILE -Recurse -File -Force -ErrorAction SilentlyContinue |
+            Where-Object { $_.LastWriteTimeUtc -gt $t0 } | ForEach-Object FullName)
--- a/install.bat
+++ b/install.bat
+rem uv takes a lock file in %TEMP%; keep that (and any other temp file) in this folder.
+set "TMP=%~dp0.uv\tmp"
+set "TEMP=%~dp0.uv\tmp"
```

That first run failed. uv had written `Temp\uv-<hash>.lock` during `uv sync`, a file none of
the four listed paths covered. `install.bat` now points `TMP` and `TEMP` at `.uv\tmp` inside the app
folder.
