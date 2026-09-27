# Golden-parity fixtures

| File | Source | License |
|------|--------|---------|
| `et.wav` | `demo/etteütlus2024.wav` from [TalTechNLP/whisper-large-v3-turbo-et-verbatim](https://huggingface.co/TalTechNLP/whisper-large-v3-turbo-et-verbatim/tree/3b546a06dad3f549044ae3eb49cf82a6a87609e8/demo) at `3b546a06`, first 23.42 s, 16 kHz mono | repo declares MIT; rights to the recording itself not separately stated |
| `en.wav` | [LibriVox "The Gettysburg Address"](https://archive.org/details/gettysburg_address_librivox), `gettysburg_address_lincoln.mp3` (SHA-1 `99797e7d…`), read by Mark Smith, first 25.66 s, 16 kHz mono | public domain |

Cut with `ffmpeg -t <secs> -ac 1 -ar 16000 -c:a pcm_s16le -map_metadata -1 -fflags +bitexact`.

`golden/*.txt` were generated once by stt-faster at `3cfbae7` (same ctranslate2/av/tokenizers/numpy as
this repo's `uv.lock`), with HF cache `refs/main` at the commits pinned in `transcribe_offline/models.py`
(et `1ae5a487`, en `c3058b47`):

```
STT_DEVICE=cpu HF_HUB_OFFLINE=1 python -m backend.cli.main transcribe process <dir> \
  --preset {et-large|turbo} --variant 61 --language {et|en} --output-format txt --no-diarize \
  --timestamps|--no-timestamps
```

Regenerate them whenever `uv.lock` changes ctranslate2, av, tokenizers or numpy: at stt-faster's
previous pins the English output differed by one token.
