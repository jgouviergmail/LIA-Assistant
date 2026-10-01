# Training a wake word

How LIA's spoken keywords are built, judged and shipped: the wake phrase of each interface
language (« Dis LIA », « Hey LIA »…) and its stop word (« Stop », « Stopp », « 停下 »…). The
decision is [ADR-329](../architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md); the
toolbox is [`scripts/wake-word/`](../../scripts/wake-word/README.md); the browser side is
described in [VOICE_MODE.md](VOICE_MODE.md). This page explains the procedure end to end, and
the measurements that shaped it.

Nothing here runs on the server: a model is trained once, offline, on a workstation, measured,
and committed to the repository as a few megabytes the browser downloads.

## 1. What a model is

A keyword model is the last stage of [openWakeWord](https://github.com/dscripka/openWakeWord)'s
pipeline. The first two stages are shared by every language and every keyword:

```mermaid
flowchart LR
    A[16 kHz audio<br/>80 ms chunks] --> B[melspectrogram.onnx<br/>32 mel bins / 10 ms]
    B --> C[embedding_model.onnx<br/>96 values / 80 ms<br/>Google speech embedding]
    C --> D[last 16 embeddings<br/>1.28 s]
    D --> E[phrase classifier<br/>one per language]
    D --> F[stop classifier<br/>one per language]
    E --> G[detection policy]
    F --> H[detection policy]
```

- The **melspectrogram** and the **embedding** are frozen, pre-trained models (Apache-2.0). The
  embedding was trained by Google on a large speech corpus; it turns any 760 ms of sound into 96
  numbers, every 80 ms.
- The **classifier** is ours: a small dense network (openWakeWord's head) reading the last 16
  embeddings, so 1.28 s of context, and answering a score between 0 and 1. It is the only thing a
  training produces — under a megabyte.
- The **detection policy** turns scores into detections: a threshold, a patience (how many
  consecutive chunks above it), a 2-second warm-up and a 2-second refractory period. The bench
  measures a model UNDER its policy, and the browser applies exactly that policy.

A stop word is one more classifier over the same embeddings: the expensive stages run once per
chunk whatever the number of keywords.

## 2. The data

A classifier learns from three families of clips. All of them are SYNTHESISED or taken from
open corpora: no recording of a real user ever enters the toolbox.

### Positives — the keyword, said every way a person says it

Two synthesisers, because one alone teaches the model what that synthesiser sounds like:

- **Piper** (CPU): fast VITS voices, a few per language, some with hundreds of speakers. Asked
  for two words, a VITS voice babbles, so every clip is said INSIDE a sentence — a lead-in and its
  pause, the keyword, a long continuation (« Bon, dis Lia, quel temps va-t-il faire… ») — and cut
  out on the per-phoneme sample counts the voice reports. Each speaker's speed is first calibrated
  on the keyword's natural duration, then varied around it.
- **VoxCPM2** (GPU): natural voices, either DESIGNED from a description (age, gender, timbre,
  pace, mood, accent) or CLONED from a recording of the language's own corpora. It says a short
  phrase at its natural duration.

Every keyword is written in several FORMS, because nobody controls how a person says it: plainly
(« Dis Lia »), fused (« Dilia »), and with a pause (« Dis, Lia »); a stop word alone, twice, and
twice with a pause. The spellings live in `wakeword/languages.py`.

### Near misses — what must NOT trigger

Phrases a person actually says that sound like the keyword: « Dis-lui », « Dis Léa », « Lydia »
for the phrase; « Top », « Stock », « Shop » for « Stop ». A homophone of the keyword itself is
never listed — it is a positive.

### Negatives — everything else a microphone hears

- **Speech in the language**: FLEURS and Multilingual LibriSpeech (CC-BY 4.0) — hundreds of hours
  for the languages MLS covers.
- **Music, noise and English speech**: MUSAN (CC-BY 4.0).
- **Silence and room tone**, at every level: an idle microphone is the commonest input of all.

### Licences and splits

Every input that shapes a shipped model carries a permissive licence (CC0, CC-BY, Apache-2.0); a
voice under a share-alike or non-commercial licence serves the held-out TEST set only. Every
download is pinned to an immutable address and a SHA-256 in `sources.lock.json`.

Data is split three ways and never mixed:

| Split | Used for | Never used for |
|---|---|---|
| train | learning | judging |
| dev | choosing the checkpoint and its threshold | learning |
| test | the final measurement only | anything else |

Test voices are held-out Piper voices and speakers, VoxCPM2 voices from the other half of the
descriptions and from the corpora's TEST speakers.

## 3. Augmentation

A clip is never seen twice the same way (`wakeword/augment.py`): a resampled speed, a tilted
equaliser, a simulated room, a background of noise, music or speech mixed at a random
signal-to-noise ratio (down to below 0 dB), a telephone band, a random level. Positives are
augmented three times and near misses four, each placed in a 2-second window that ENDS with the
keyword — exactly the 16 embeddings the browser scores when the keyword has just been said.

## 4. Training

`train` (GPU or CPU, the same recipe; `wakeword/train.py`):

1. Every clip window and every negative stream is turned into embeddings once, and cached.
2. Each batch is a quarter positives, a quarter near misses and half negatives — a fifth of those
   drawn from a pool of HARD negatives: the windows the current model likes most, rescanned from
   the streams every few thousand steps.
3. The weight of the negatives rises over the first half of the run, to openWakeWord's reference
   value: early on the model learns the keyword, later it learns to be quiet.
4. Every thousand steps the checkpoint is JUDGED on the dev split: the lowest threshold that keeps
   the dev false accepts under the keyword's target is found, and the score is the recall there
   of held-out training clips played as 6-second STREAMS, clean and at 10 dB. The best checkpoint
   is kept and exported to ONNX.

## 5. Measurement

`measure` reads the TEST split only, listened to continuously under the browser's policy
(`wakeword/measure.py`, shared stream logic in `wakeword/trials.py`):

- **Recall**: every test clip is placed 3 s into a 6 s stream, through a room and a phone half the
  time, clean or at 20, 10 and 5 dB; a detection counts between the start of the keyword and one
  second after its end. Reported overall, per voice and per written form.
- **False accepts per hour**: on hours of continuous test speech in the language and in English,
  on music and on noise.
- **Near-miss accepts** and the **latency** after the keyword.

The verdict compares these with an acceptance grid PUBLISHED before training and never lowered to
pass (`ACCEPTANCE` in `wakeword/measure.py`). A stop word allows more false accepts than the
phrase: a false « stop » only cuts a reading aloud, where a false wake opens the microphone. A
model that fails is not shipped.

## 6. Export and shipping

`export` writes into `apps/web/public/models/wake/v1/`: the two shared stages, the classifier of
each language and keyword, every file named after its SHA-256 (a retrained model is a new URL, so
no cache ever serves a stale one), and one `manifest.json` per language — its files with their
size and hash, the policy, the measured figures, the verdict and the provenance of every input
with its licence. A stop word is exported INTO its language's manifest, under `commands`.

Three guards hold what ships:

- `shipped-models.test.ts`: every language has its phrase and its stop word, each file is the one
  its manifest names, each model was accepted by the bench, and no unnamed file ships.
- `parity.test.ts`: the browser's engine, on the real models through ONNX Runtime Web, scores a
  golden audio file as the toolbox did (`task wake:golden -- <lang>`).
- The browser itself refuses any file whose size or SHA-256 differs from its manifest.

## 7. Running it

The toolbox has its own pinned requirements and two Docker images: a CPU one (Piper,
measurement) and a GPU one (VoxCPM2, CUDA training). See the
[toolbox README](../../scripts/wake-word/README.md) for every command; one language and keyword:

```bash
task wake:run -- prepare --lang fr                 # corpora (once per language)
task wake:run -- synth --lang fr                   # Piper clips
task wake:clone -- fr                              # VoxCPM2 clips (GPU)
task wake:run:gpu -- train --lang fr               # train on CUDA
task wake:run -- measure --lang fr                 # bench on the CPU
task wake:run -- export --lang fr                  # write the model and manifest
task wake:run -- synth --lang fr --keyword stop    # the same steps for the stop word
```

Measured on one workstation (16 cores, RTX 4090, 2026-10-01), for one French keyword:

| Step | Duration |
|---|---|
| Piper clips (four banks, CPU) | about 45 min |
| VoxCPM2 clips (10 000, one process) | about 80 min — 0.48 s a clip |
| Training (40 000 steps) | 7 min on the GPU, about 2 h 30 on the CPU |
| Measurement (CPU) | about 25 min |

The synthesis, not the training, is the long part. VoxCPM2 runs ONE process by default: a
process peaks at 11.3 GB of RAM while it loads and commits about 8.6 GB on a Windows host under
WSL — three at once froze the WSL machine.

## 8. What the measurements taught

Every rule above was paid for by a measurement (French phrase, 2026-10-01):

| Finding | Measured | What changed |
|---|---|---|
| Too little negative speech makes a jumpy model | 49 h of MLS: 14 false accepts/h on dev; 220 h: 2.7/h | 120 MLS training shards |
| A light negative weight never learns silence | weight 30: stuck at 2.7/h; openWakeWord's 1 000: 0.18/h | the reference ramp |
| One window at a fixed offset misjudges a checkpoint | 27 % recall in one window = 75 % in a stream | selection on stream recall, the bench's own logic |
| A bigger network buys nothing | 512 hidden units ≈ 128 | 128 |
| Patience costs more recall than it saves | patience 2-4 lost more recall than false accepts | patience 1 by default |
| Slow training voices miss a quick « dilia » | natural voices said the phrase in 0.85 s, a third with a pause; « dis … Lia » woke LIA, « dilia » did not | fused and paused forms in every language, faster rates, recall per form ≥ 85 % — on the test set, recall clean 73 % → 88 %, « Dilia » 87 % like « Dis Lia », at 10 dB 43 % → 50 % |
| The browser runtime needs its loader | ONNX Runtime Web loads a `.mjs` beside its `.wasm`; only the binary was served | both copied by `apps/web/scripts/copy-ort-runtime.mjs` |
| A two-word request makes a VITS voice babble | Piper on « Dis Lia » alone | the keyword said inside a sentence, cut on its phonemes |

## 9. Adding a keyword or a language

- **A language**: declare its `LanguageSpec` in `wakeword/languages.py` (phrase, forms, near
  misses, voices with their licences, FLEURS and MLS configurations) and its stop word in
  `STOP_WORDS`, pin its remotes (`task wake:run -- lock --lang <code>`), review the diff of
  `sources.lock.json`, run the steps above for both keywords, and add the words to
  `apps/web/src/lib/audio/wake-word/phrases.ts`.
- **A keyword**: it is a retraining, never a setting — the words are a contract between the
  toolbox, the manifest and the screens, held equal by `shipped-models.test.ts`.
- **A new spoken command** beside « stop »: extend `Keyword` in the toolbox and `WAKE_COMMANDS`
  in `apps/web/src/lib/audio/wake-word/commands.ts`; the manifest, the engine and the worker
  already carry any number of commands.
