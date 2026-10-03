# Wake-word toolbox (ADR-329)

Trains and measures the per-language wake-phrase models the browser runs to
wake a Live session from standby, and to start the classic voice mode's
transcription. Offline, in its own image: nothing here runs on the API's
interpreter nor on the Raspberry Pi. The only output is a handful of files
under `apps/web/public/models/wake/`, committed with their manifest.

The whole procedure — data, training, measurement, shipping — and the measurements
that shaped it are explained in
[docs/technical/WAKE_WORD_TRAINING.md](../../docs/technical/WAKE_WORD_TRAINING.md).

## The model

openWakeWord's pipeline (Apache-2.0), re-trained per language:

1. `melspectrogram.onnx` — 32 mel bins every 10 ms (512-sample window);
2. `embedding_model.onnx` — Google's `speech_embedding`, 96 dimensions every 80 ms;
3. `classifier.onnx` — the language's own head: the last 16 embeddings (1.28 s)
   to a score.

The first two are shared by every language. `python -m wakeword selfcheck`
holds this package's batch and streaming features to the `openwakeword` 0.6.0
package itself, and proves that a score computed in batch on the streaming
grid IS the score the browser computes chunk by chunk.

## Data, and the licence every input is used under

| Input | Role | Licence |
|---|---|---|
| Piper voices listed as `train_voices` in `wakeword/languages.py` | synthetic positives and near misses | CC0, CC-BY 4.0, public domain, Apache-2.0 |
| Piper voices listed as `test_voices` | the held-out TEST set only, never shipped | as published (some share-alike) |
| Piper (`piper-tts`, pinned in `requirements.in`) | the CPU synthesiser | GPL-3.0-or-later: run as a tool, never shipped; the audio it writes carries its VOICE's licence |
| VoxCPM2 (`openbmb/VoxCPM2`, pinned revision) | natural voices: designed from a description, or cloned from the corpora below | Apache-2.0 (code and weights) |
| FLEURS (Google) | speech in the language: negatives, babble, dev and test | CC-BY 4.0 |
| Multilingual LibriSpeech (Meta) | audiobook speech: negatives, dev and test | CC-BY 4.0 |
| MUSAN (OpenSLR 17) | music, noise, English speech: backgrounds and negatives | CC-BY 4.0 |
| openWakeWord v0.5.1 feature models | the two shared stages | Apache-2.0 |

Rooms are SYNTHETIC impulse responses (`augment.synthetic_room`): no
impulse-response corpus, so none to license. Every remote is fetched from an
immutable address and verified against `sources.lock.json`.

## Two synthesisers

- **Piper** (CPU, `synth`): a VITS voice asked for two words often babbles,
  and some swallow the first plosive of an utterance (measured 2026-10-01), so
  every clip is said INSIDE a sentence — a lead-in and its pause, the phrase, a
  long continuation — and cut out on the per-phoneme sample counts the voice
  reports. Each speaker's rate is first calibrated on the language's natural
  phrase duration.
- **VoxCPM2** (GPU, `clone`, `Dockerfile.gpu`): natural voices, designed from a
  description (age, gender, timbre, pace, mood, accent) or cloned from a
  recording of FLEURS or MLS. Training voices come from the TRAIN splits and one
  half of the descriptions; test voices from the TEST splits and the other half.
  It runs as ONE process: alone it keeps the GPU busy (0.48 s a clip on an RTX
  4090), and a second process only time-slices it — measured, 0.66 s a clip for
  the two together. A process needs 11 GB of RAM while it loads, then 2.6 GB,
  and 6 GB of GPU memory.

Each language trains its phrase plainly, fused and once with a pause (« Dis
Lia », « Dilia », « Dis, Lia »): a person says it quickly as often as slowly.

Training uses every clip bank that exists; the measurement reports recall per
voice, so a weak synthesiser shows.

## Commands

```bash
task wake:image                     # build the CPU image (pinned base, hashed lock)
task wake:image:gpu                 # build the GPU image (VoxCPM2, CUDA training)
task wake:run -- lock --lang fr     # pin every remote the language needs
task wake:run -- prepare --lang fr  # download and decode the corpora
task wake:clone -- fr               # natural voices on the GPU (after prepare)
task wake:train -- fr               # prepare, synth, train, measure, export
task wake:run:gpu -- train --lang fr  # the same training on CUDA (an NVIDIA GPU)
task wake:run -- synth --lang fr --keyword stop    # the stop command: every step takes --keyword
task wake:selfcheck                 # features vs openWakeWord, batch vs streaming
task wake:deps:lock                 # recompile both hashed locks
```

Training runs the same recipe on either image; on the GPU one the feature
stages use ONNX Runtime's CUDA provider and the classifier trains on CUDA. The
measurement and the golden fixture run in the CPU image, whose arithmetic is
the browser's.

A language also ships its STOP COMMAND — LIA's name, then the word (« LIA, stop »;
`--keyword stop`: the language's voices and corpora, its own words in `STOP_WORDS`,
banks and work directory named `<lang>-stop`).
Its `export` writes the classifier into the language's manifest under `commands`,
so the phrase is exported first. Measured on an RTX 4090 for one language: Piper
30-45 min on the CPU, VoxCPM2 0.5-0.65 s a clip on one process, training about
30 min on the GPU, the measurement 4 min on the GPU and 25 min on the CPU (which
certifies what ships). `measure --threshold` certifies an operating point other
than the dev's; the export ships the measured row.

Corpora, voices and features live in the Docker volume `lia-wake-data`
(several tens of GB for a language with MLS: the training speech alone is a
PCM bank of about 115 MB per hour); `docker volume rm lia-wake-data` reclaims
it.

## How a model is judged

`train` keeps the checkpoint with the best recall on held-out training clips,
played as streams — clean, at 10 dB, and for the weakest written form — at the
threshold that holds the DEV false accepts under the keyword's target (0.25 per
hour for the phrase, 1 for the stop command). The dev is 74 hours for French:
FLEURS and MLS dev, one MLS training speaker in four (by volume, at most two
hours each — the others are the negatives, at most fifteen hours each), MUSAN
music and the English speech no training uses.
`measure` then reads only TEST data, listened to continuously under the
browser's policy (threshold, patience, a 2-second refractory period, a 2-second
warm-up): recall at four signal-to-noise ratios and per written form, latency,
near-miss accepts, false accepts per hour on speech, music and noise. The
acceptance thresholds (for the phrase: recall ≥ 90 % clean and ≥ 80 % at 10 dB,
no written form under 85 % clean, ≤ 0.5 false accept per hour of speech, ≤ 0.2
per hour of music, median latency ≤ 300 ms; the stop command allows 2 and 1) are
written in `wakeword/measure.py` and are never lowered to pass.

## Adding a language

Add a `LanguageSpec` to `wakeword/languages.py` (the phrase, its spellings and
inline phonemes, near misses, train and test voices with their licences, the
FLEURS and MLS configurations), run `task wake:run -- lock --lang <code>`,
review the diff of `sources.lock.json`, then `task wake:train -- <code>`.
