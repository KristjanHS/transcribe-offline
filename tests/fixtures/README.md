# Test audio

| File | Source | License |
|------|--------|---------|
| `et.wav` | `demo/etteütlus2024.wav` from [TalTechNLP/whisper-large-v3-turbo-et-verbatim](https://huggingface.co/TalTechNLP/whisper-large-v3-turbo-et-verbatim/tree/3b546a06dad3f549044ae3eb49cf82a6a87609e8/demo) at `3b546a06`, first 23.42 s, 16 kHz mono | repo declares MIT; rights to the recording itself not separately stated |
| `en.wav` | [LibriVox "The Gettysburg Address"](https://archive.org/details/gettysburg_address_librivox), `gettysburg_address_lincoln.mp3` (SHA-1 `99797e7d…`), read by Mark Smith, first 25.66 s, 16 kHz mono | public domain |

Cut with `ffmpeg -t <secs> -ac 1 -ar 16000 -c:a pcm_s16le -map_metadata -1 -fflags +bitexact`.
