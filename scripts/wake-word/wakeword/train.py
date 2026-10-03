"""Train one language's classifier on openWakeWord's features (ADR-329).

The data, all computed once and cached under the language's work directory
with the fingerprints of the banks it came from — a bank rebuilt since (other
shards, other clips) makes a cache stale, and it is computed again:

- **positives** — every training clip of the phrase, augmented three times,
  in a 2-second window it ENDS in (0-200 ms before the end): exactly the 16
  embeddings the browser scores when the phrase has just been said;
- **near misses** — the same for the phrases that must not wake LIA, four times;
- **backgrounds** — windows of music, noise and room tone alone, at any level,
  and digital silence: an idle microphone is the commonest input of all;
- **speech streams** — every embedding of the language's training speech
  (FLEURS, MLS) and of MUSAN's music, noise and English speech, from which
  16-embedding windows are drawn at random at every step.

The model is openWakeWord's DNN head. Each batch is one quarter positives, one
quarter near misses, half negatives — a fifth of those drawn from a pool of
HARD negatives refreshed from the streams as training goes. The negative weight
rises over the first half: early on the model learns the phrase, later it
learns to be quiet. Every ``_VALIDATE_EVERY`` steps the checkpoint is judged on
the DEV split: the lowest threshold that holds the dev false accepts under
``FA_TARGET_PER_HOUR`` of the keyword is found, and the score is the recall there of the
held-out training clips PLAYED AS STREAMS (``trials``: clean and at 10 dB), the
very number the measurement certifies on the test clips — a single window at a
fixed offset under-read it by a factor of three (measured 2026-10-01: 27 % for
75 % in a stream) — together with the recall of the WEAKEST written form, since
the acceptance holds every form (measured 2026-10-02: « Stop » said once at 58 %
behind 96 % doubled, while the average looked fine). The best checkpoint is
kept. The test split is never read here.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from collections.abc import Sequence
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from torch import nn

from wakeword import augment as aug
from wakeword.banks import Bank, Int16Array, bank_exists, bank_fingerprint, open_bank
from wakeword.corpora import MUSAN_DEV_BANKS, language_bank_names, musan_bank_names
from wakeword.features import (
    CHUNK,
    EMBEDDING_DIM,
    EMBEDDINGS,
    WARMUP_CHUNKS,
    FeatureExtractor,
    Policy,
)
from wakeword.languages import Keyword, LanguageSpec
from wakeword.paths import CORPORA, language_dir
from wakeword.sources import feature_models, fetch, read_lock
from wakeword.trials import Trial, form_of, recall, stream

TOTAL_SAMPLES = 32_000
_COPIES = {"positive": 3, "near_miss": 4}
_BACKGROUND_WINDOWS = 30_000
_VALIDATION_EVERY_NTH_CLIP = 20
_HIDDEN = 128
_STEPS = 40_000
_BATCH = 2048
_LEARNING_RATE = 1e-3
_WARMUP_STEPS = 1_000
#: openWakeWord's reference recipe ramps the negative weight to 1 000 (and doubles
#: it while the false accepts miss the target). Measured 2026-10-01 on French: at
#: 30 the dev false accepts stalled at 2.7/h with 55 % recall at 0.999.
_NEGATIVE_WEIGHT_MAX = 1000.0
_HARD_SHARE = 0.2
_HARD_POOL = 50_000
_HARD_SCAN = 1_000_000
_HARD_EVERY = 2_000
_VALIDATE_EVERY = 1_000
#: The conditions a checkpoint is selected on: the clean phrase and the phrase at
#: 10 dB, the two recalls the acceptance names.
_VALIDATION_SNRS: dict[str, float | None] = {"clean": None, "10 dB": 10.0}
#: The dev false-accept rate the checkpoint is judged at, per keyword. The phrase
#: is judged at the published speech limit itself (``measure.ACCEPTANCE``): a
#: missed « Dis LIA » costs more than a rare false wake (owner decision 2026-10-02,
#: the « Dis Siri » habit — in use, the shipped model woke on nothing and missed a
#: quick « dilia », while judged at half the limit a model chose 0.9999 and heard
#: 74 % of the test clips). The stop command keeps half its limit.
FA_TARGET_PER_HOUR: dict[Keyword, float] = {"wake": 0.5, "stop": 1.0}
#: The thresholds a checkpoint is judged at, finer toward the strict end: late
#: in training the scores saturate, and a checkpoint recalling 93 % of the clips
#: clean at 0.999 was thrown away for its 1.2 false accepts per dev hour there —
#: no stricter step existed (measured 2026-10-02, French phrase, step 36 000).
THRESHOLDS = (
    *(0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99, 0.995, 0.998, 0.999),
    *(0.9995, 0.9998, 0.9999),
)
_SECONDS_PER_EMBEDDING = CHUNK / 16_000
_WORKERS = 12

F16 = npt.NDArray[np.float16]
F32 = npt.NDArray[np.float32]


# -- features ---------------------------------------------------------------------


def extractor() -> FeatureExtractor:
    """The shared stages, verified against the lock."""
    lock = read_lock()
    mel, embedding = (fetch(remote, lock) for remote in feature_models())
    return FeatureExtractor(mel, embedding, threads=8)


_WORKER_BACKGROUNDS: list[Bank] = []
_WORKER_BANKS: dict[str, Bank] = {}


def _init_worker(names: list[str]) -> None:
    _WORKER_BACKGROUNDS.extend(open_bank(CORPORA, name) for name in names)


def _augmented(payload: tuple[str, list[int], int, int]) -> Int16Array:
    bank_name, indices, copies, seed = payload
    if bank_name not in _WORKER_BANKS:
        _WORKER_BANKS[bank_name] = open_bank(CORPORA, bank_name)
    bank = _WORKER_BANKS[bank_name]
    rng = np.random.default_rng(seed)
    windows = [
        aug.augment(bank.segment(index), TOTAL_SAMPLES, _WORKER_BACKGROUNDS, rng)
        for index in indices
        for _ in range(copies)
    ]
    return np.stack(windows)


def _background(payload: tuple[int, int]) -> Int16Array:
    count, seed = payload
    rng = np.random.default_rng(seed)
    windows = []
    for _ in range(count):
        roll = rng.random()
        if roll < 0.1:
            window = np.zeros(TOTAL_SAMPLES, dtype=np.float32)
        elif roll < 0.25:
            window = aug.coloured_noise(TOTAL_SAMPLES, rng)
        else:
            window = aug.background_from(_WORKER_BACKGROUNDS, TOTAL_SAMPLES, rng)
            if rng.random() < 0.5:
                window = aug.reverberate(window, rng)
            if rng.random() < 0.4:
                window = aug.phone_band(window, rng)
        peak = float(np.max(np.abs(window))) or 1.0
        windows.append(aug.to_int16(window * (10 ** (rng.uniform(-60, -3) / 20) / peak)))
    return np.stack(windows)


def _embed_batches(fx: FeatureExtractor, batches: Any) -> F16:
    out = [fx.embed(batch).astype(np.float16) for batch in batches]
    return np.concatenate(out) if out else np.zeros((0, EMBEDDINGS, EMBEDDING_DIM), np.float16)


def _stamp_of(path: Path) -> Path:
    return path.with_name(path.name + ".inputs.json")


def _inputs(banks: Sequence[str]) -> dict[str, str]:
    return {name: bank_fingerprint(CORPORA, name) for name in banks}


def _current(path: Path, banks: Sequence[str]) -> bool:
    """A cache is current when it exists and its banks are the ones it was computed from."""
    stamp = _stamp_of(path)
    if not (path.exists() and stamp.exists()):
        return False
    recorded: dict[str, str] = json.loads(stamp.read_text(encoding="utf-8"))
    return recorded == _inputs(banks)


def _stamp(path: Path, banks: Sequence[str]) -> None:
    _stamp_of(path).write_text(json.dumps(_inputs(banks), sort_keys=True), encoding="utf-8")


def _cached(path: Path, build: Any, banks: Sequence[str]) -> Any:
    """``build()``'s array, kept in ``path`` while the ``banks`` it reads are unchanged."""
    if not _current(path, banks):
        np.save(path, build())
        _stamp(path, banks)
    return np.load(path, mmap_mode="r")


def clip_features(
    fx: FeatureExtractor,
    bank_name: str,
    kind: str,
    indices: list[int],
    backgrounds: list[str],
    seed: int,
) -> F16:
    """Augmented windows of the given clips, embedded."""
    batches = [indices[i : i + 64] for i in range(0, len(indices), 64)]
    payloads = [
        (bank_name, batch, _COPIES[kind], seed * 100_003 + n) for n, batch in enumerate(batches)
    ]
    with Pool(_WORKERS, initializer=_init_worker, initargs=(backgrounds,)) as pool:
        return _embed_batches(fx, pool.imap(_augmented, payloads))


def background_features(fx: FeatureExtractor, backgrounds: list[str], seed: int) -> F16:
    """Background-only windows (music, noise, room tone, silence), embedded."""
    payloads = [(250, seed * 7_919 + n) for n in range(_BACKGROUND_WINDOWS // 250)]
    with Pool(_WORKERS, initializer=_init_worker, initargs=(backgrounds,)) as pool:
        return _embed_batches(fx, pool.imap(_background, payloads))


Forms = npt.NDArray[np.str_]
#: Per condition: the stream embeddings, each clip's span, and its written form.
ValidationTrials = dict[str, tuple[F16, F32, F32, Forms]]


def validation_trials(
    fx: FeatureExtractor, banks: list[str], backgrounds: list[str], work: Path, seed: int
) -> ValidationTrials:
    """The held-out training clips played as streams, embedded once per condition.

    Returns, per condition, the stacked stream embeddings, each clip's span and
    its written form: a checkpoint is then scored on them without touching the
    audio again.
    """
    noise = [open_bank(CORPORA, name) for name in backgrounds]
    out: ValidationTrials = {}
    inputs = [*banks, *backgrounds]
    for condition, snr in _VALIDATION_SNRS.items():
        path = work / f"trials-{condition.replace(' ', '')}.npz"
        if not _current(path, inputs):
            rng = np.random.default_rng(seed + 101)
            frames: list[F16] = []
            starts: list[float] = []
            ends: list[float] = []
            forms: list[str] = []
            for bank_name in banks:
                bank = open_bank(CORPORA, bank_name)
                _, held = _split(bank)
                for first in range(0, len(held), 128):
                    chunk = held[first : first + 128]
                    streams = [stream(bank.segment(i), snr, noise, rng) for i in chunk]
                    embedded = fx.embed(np.stack([audio for audio, _, _ in streams]))
                    frames.extend(embedded.astype(np.float16))
                    starts.extend(start for _, start, _ in streams)
                    ends.extend(end for _, _, end in streams)
                    forms.extend(form_of(str(bank.meta[i]["text"])) for i in chunk)
            np.savez(
                path,
                frames=np.stack(frames),
                starts=np.array(starts),
                ends=np.array(ends),
                forms=np.array(forms),
            )
            _stamp(path, inputs)
        with np.load(path) as stored:
            out[condition] = (stored["frames"], stored["starts"], stored["ends"], stored["forms"])
    return out


def _weakest_form(trials: list[Trial], forms: Forms, policy: Policy) -> tuple[str, float]:
    """The written form the policy finds least often, and its recall."""
    by_form: dict[str, list[Trial]] = {}
    for trial, form in zip(trials, forms, strict=True):
        by_form.setdefault(str(form), []).append(trial)
    found = [(form, float(recall(items, policy)["recall"])) for form, items in by_form.items()]
    return min(found, key=lambda pair: pair[1])


def trial_scores(net: Net, frames: F16, starts: F32, ends: F32) -> list[Trial]:
    """Every validation stream scored by the network, as trials the policy reads."""
    # Every stream's windows of 16 embeddings, as (stream, window, embedding, value).
    windows = np.lib.stride_tricks.sliding_window_view(frames, EMBEDDINGS, axis=1).swapaxes(2, 3)
    per_stream = windows.shape[1]
    scores = scores_of(net, windows.reshape(-1, EMBEDDINGS, EMBEDDING_DIM))
    rows = scores.reshape(frames.shape[0], per_stream)
    return [
        (row, float(start), float(end)) for row, start, end in zip(rows, starts, ends, strict=True)
    ]


def stream_frames(fx: FeatureExtractor, bank_name: str) -> F16:
    """Every embedding of a bank's concatenated audio, cached once per bank."""
    path = CORPORA / f"emb-{bank_name}.npy"

    def build() -> F16:
        started = time.time()
        frames = fx.embed_long(open_bank(CORPORA, bank_name).samples).astype(np.float16)
        print(f"embedded {bank_name}: {frames.shape[0]} frames in {time.time() - started:.0f}s")
        return frames

    frames: F16 = _cached(path, build, [bank_name])
    return frames


# -- the model --------------------------------------------------------------------


class Net(nn.Module):
    """openWakeWord's DNN head, returning a LOGIT (the export adds the sigmoid)."""

    def __init__(self, hidden: int = _HIDDEN) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Flatten(),
            nn.Linear(EMBEDDINGS * EMBEDDING_DIM, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits: torch.Tensor = self.layers(x)
        return logits.squeeze(-1)


class Scored(nn.Module):
    """The exported graph: ``(batch, 16, 96)`` to ``(batch, 1)`` probabilities."""

    def __init__(self, net: Net) -> None:
        super().__init__()
        self.net = net

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.net(x)).unsqueeze(-1)


def _device_of(net: Net) -> torch.device:
    return next(net.parameters()).device


def scores_of(net: Net, windows: npt.NDArray[Any], batch: int = 65_536) -> F32:
    """Probabilities of many windows, in inference mode, on the network's device."""
    net.eval()
    device = _device_of(net)
    out = []
    with torch.inference_mode():
        for i in range(0, windows.shape[0], batch):
            chunk = torch.from_numpy(np.asarray(windows[i : i + batch], dtype=np.float32))
            out.append(torch.sigmoid(net(chunk.to(device))).cpu().numpy())
    net.train()
    return np.concatenate(out) if out else np.zeros(0, np.float32)


def stream_scores(net: Net, frames: npt.NDArray[Any]) -> F32:
    """The score at every embedding of a stream (16 trailing embeddings each)."""
    if frames.shape[0] < EMBEDDINGS:
        return np.zeros(0, np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(frames, (EMBEDDINGS, EMBEDDING_DIM))[:, 0]
    return scores_of(net, windows)


def false_accepts(scores: F32, threshold: float, patience: int = 1) -> tuple[int, float]:
    """Detections, and hours listened, of a stream's scores under the browser's policy."""
    hours = (scores.size + WARMUP_CHUNKS) * _SECONDS_PER_EMBEDDING / 3600
    fired = Policy(threshold, patience).detections(scores, first_chunk=WARMUP_CHUNKS)
    return len(fired), hours


# -- sampling ---------------------------------------------------------------------


class NegativePool:
    """16-embedding windows drawn from several streams, never across two of them."""

    def __init__(self, streams: list[F16], backgrounds: F16) -> None:
        self.frames = np.concatenate([np.asarray(stream) for stream in streams])
        starts, offset = [], 0
        for frames in streams:
            starts.append(np.arange(offset, offset + frames.shape[0] - EMBEDDINGS + 1))
            offset += frames.shape[0]
        self.starts = np.concatenate(starts)
        self.backgrounds = np.asarray(backgrounds)
        self.hard = np.zeros(0, dtype=np.int64)
        self._steps = np.arange(EMBEDDINGS)

    def windows(self, starts: npt.NDArray[np.int64]) -> F16:
        """The windows beginning at ``starts`` (indices into ``frames``)."""
        return np.asarray(self.frames[starts[:, None] + self._steps], dtype=np.float16)

    def draw(self, count: int, rng: np.random.Generator) -> F16:
        """Stream windows, hard ones and background windows, mixed."""
        hard = min(int(count * _HARD_SHARE), self.hard.size)
        background = count // 8
        plain = count - hard - background
        parts = [self.windows(self.starts[rng.integers(0, self.starts.size, plain)])]
        if hard:
            parts.append(self.windows(self.hard[rng.integers(0, self.hard.size, hard)]))
        parts.append(self.backgrounds[rng.integers(0, self.backgrounds.shape[0], background)])
        return np.concatenate(parts)

    def refresh_hard(self, net: Net, rng: np.random.Generator) -> None:
        """Keep the negatives the model currently likes most (scanned in slices)."""
        scan = self.starts[rng.integers(0, self.starts.size, min(_HARD_SCAN, self.starts.size))]
        scores = np.concatenate(
            [
                scores_of(net, self.windows(scan[i : i + 65_536]))
                for i in range(0, scan.size, 65_536)
            ]
        )
        keep = np.argsort(scores)[-_HARD_POOL:]
        self.hard = scan[keep]


# -- training ---------------------------------------------------------------------


def clip_bank_names(spec: LanguageSpec, kind: str, split: str) -> list[str]:
    """The clip banks of a kind and split that exist: Piper's always, VoxCPM2's when generated."""
    names = [f"clips-{spec.slug}-{kind}-{split}"]
    natural = f"vox-{spec.slug}-{kind}-{split}"
    if bank_exists(CORPORA, natural):
        names.append(natural)
    return names


def _split(bank: Bank) -> tuple[list[int], list[int]]:
    """Every Nth clip is held out for validation (by index: reproducible)."""
    indices = list(range(len(bank)))
    validation = indices[::_VALIDATION_EVERY_NTH_CLIP]
    held = set(validation)
    return [i for i in indices if i not in held], validation


def _lr(step: int) -> float:
    if step < _WARMUP_STEPS:
        return _LEARNING_RATE * (step + 1) / _WARMUP_STEPS
    progress = (step - _WARMUP_STEPS) / max(1, _STEPS - _WARMUP_STEPS)
    return float(_LEARNING_RATE * 0.5 * (1 + np.cos(np.pi * progress)))


def _validate(
    fa_target: float,
    net: Net,
    trials: ValidationTrials,
    val_near: F16,
    dev_frames: list[F16],
) -> dict[str, Any]:
    dev_scores = [stream_scores(net, frames) for frames in dev_frames]
    scored = {
        condition: trial_scores(net, frames, starts, ends)
        for condition, (frames, starts, ends, _) in trials.items()
    }
    forms = trials["clean"][3]
    near = scores_of(net, val_near)
    # Where the strictest threshold stands, whatever holds: a run that will fail
    # shows it from its first validations, on both sides of the trade-off.
    strict = Policy(THRESHOLDS[-1])
    counts = [false_accepts(scores, THRESHOLDS[-1]) for scores in dev_scores]
    diagnosis = {
        "dev_fa_per_hour_strictest": round(
            sum(c for c, _ in counts) / max(1e-9, sum(h for _, h in counts)), 3
        ),
        "recall_clean_strictest": round(recall(scored["clean"], strict)["recall"], 4),
    }
    best: dict[str, Any] = {"threshold": None, "score": 0.0}
    for threshold in THRESHOLDS:
        counts = [false_accepts(scores, threshold) for scores in dev_scores]
        detections = sum(count for count, _ in counts)
        hours = sum(hours for _, hours in counts)
        if detections / hours <= fa_target:
            policy = Policy(threshold)
            recalls = {
                condition: round(recall(items, policy)["recall"], 4)
                for condition, items in scored.items()
            }
            weakest, weakest_recall = _weakest_form(scored["clean"], forms, policy)
            best = {
                "threshold": threshold,
                # The recalls the acceptance names, weighed alike: clean, at
                # 10 dB, and the weakest written form clean.
                "score": round((sum(recalls.values()) + weakest_recall) / (len(recalls) + 1), 4),
                **{f"recall {condition}": value for condition, value in recalls.items()},
                "weakest form": weakest,
                "recall weakest form": round(weakest_recall, 4),
                "near_miss_accepts": float(np.mean(near >= threshold)),
                "dev_false_accepts": detections,
                "dev_hours": round(hours, 2),
            }
            break
    return {**best, **diagnosis}


def train(spec: LanguageSpec, seed: int = 0) -> Path:
    """Train, select and save one language's classifier; returns the run directory."""
    torch.manual_seed(seed)
    torch.set_num_threads(16)
    # The same recipe on either device: the GPU image trains on CUDA, the CPU one on the CPU.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    rng = np.random.default_rng(seed)
    work = language_dir(spec.slug)
    fa_target = FA_TARGET_PER_HOUR[spec.keyword]
    fx = extractor()
    banks = language_bank_names(spec)
    background_banks = [
        *(name for name in musan_bank_names() if name.endswith("-train")),
        *banks["train"],
    ]

    def features(kind: str) -> tuple[F16, F16]:
        """Train and validation windows of every clip bank of a kind (Piper, VoxCPM2)."""
        train_parts: list[F16] = []
        val_parts: list[F16] = []
        for tag, bank_name in enumerate(clip_bank_names(spec, kind, "train"), start=1):
            bank = open_bank(CORPORA, bank_name)
            fit, held = _split(bank)
            for part, indices, parts in (("train", fit, train_parts), ("val", held, val_parts)):
                path = work / f"x-{bank_name}-{part}.npy"
                salt = seed + 10 * tag + (1 if part == "val" else 0)
                parts.append(
                    _cached(
                        path,
                        lambda b=bank_name, i=indices, s=salt: clip_features(
                            fx, b, kind, i, background_banks, s
                        ),
                        [bank_name, *background_banks],
                    )
                )
        return np.concatenate(train_parts), np.concatenate(val_parts)

    x_pos, _ = features("positive")
    x_near, x_near_val = features("near_miss")
    trials = validation_trials(
        fx, clip_bank_names(spec, "positive", "train"), background_banks, work, seed
    )
    x_background = _cached(
        work / "x_background.npy",
        lambda: background_features(fx, background_banks, seed + 5),
        background_banks,
    )
    negative_streams = [
        stream_frames(fx, name)
        for name in [*banks["train"], *(n for n in musan_bank_names() if n.endswith("-train"))]
    ]
    # The dev the checkpoint is chosen on: the language's speech, its music and English.
    dev_frames = [stream_frames(fx, name) for name in [*banks["dev"], *MUSAN_DEV_BANKS]]
    pool = NegativePool(negative_streams, x_background)
    hours = pool.frames.shape[0] * _SECONDS_PER_EMBEDDING / 3600
    dev_hours = sum(frames.shape[0] for frames in dev_frames) * _SECONDS_PER_EMBEDDING / 3600
    print(
        f"positives {x_pos.shape[0]} ({trials['clean'][0].shape[0]} validation streams), "
        f"near misses {x_near.shape[0]}, "
        f"backgrounds {x_background.shape[0]}, negative streams {hours:.1f} h, "
        f"dev {dev_hours:.1f} h, on {device}"
    )

    net = Net().to(device)
    optimiser = torch.optim.AdamW(net.parameters(), lr=_LEARNING_RATE, weight_decay=1e-4)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    quarter = _BATCH // 4
    history: list[dict[str, Any]] = []
    best_score, best_state = -1.0, None
    for step in range(_STEPS):
        for group in optimiser.param_groups:
            group["lr"] = _lr(step)
        if step % _HARD_EVERY == 0 and step > 0:
            pool.refresh_hard(net, rng)
        x = np.concatenate(
            [
                x_pos[rng.integers(0, x_pos.shape[0], quarter)],
                x_near[rng.integers(0, x_near.shape[0], quarter)],
                pool.draw(_BATCH - 2 * quarter, rng),
            ]
        ).astype(np.float32)
        labels = np.zeros(_BATCH, dtype=np.float32)
        labels[:quarter] = 1.0
        negative_weight = 1.0 + (_NEGATIVE_WEIGHT_MAX - 1.0) * min(1.0, step / (_STEPS / 2))
        weights = np.full(_BATCH, negative_weight, dtype=np.float32)
        weights[:quarter] = 1.0
        logits = net(torch.from_numpy(x).to(device))
        loss = (
            loss_fn(logits, torch.from_numpy(labels).to(device))
            * torch.from_numpy(weights).to(device)
        ).mean()
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()
        if (step + 1) % _VALIDATE_EVERY == 0:
            result = _validate(fa_target, net, trials, x_near_val, dev_frames)
            result.update(step=step + 1, loss=loss.item(), negative_weight=negative_weight)
            history.append(result)
            print(json.dumps(result))
            if result["threshold"] is not None and result["score"] > best_score:
                best_score = result["score"]
                best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    if best_state is None:
        raise SystemExit("no checkpoint held the dev false-accept target")
    net.load_state_dict(best_state)
    torch.save({"state": best_state, "hidden": _HIDDEN}, work / "classifier.pt")
    final = _validate(fa_target, net, trials, x_near_val, dev_frames)
    # The exporter traces on the CPU, whatever device trained.
    _export_onnx(copy.deepcopy(net).cpu(), work / "classifier.onnx")
    report = {
        "selected": final,
        "history": history,
        "steps": _STEPS,
        "seed": seed,
        # What the model learnt from, read back by the export's provenance.
        "clip_banks": {
            kind: clip_bank_names(spec, kind, "train") for kind in ("positive", "near_miss")
        },
    }
    (work / "train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"selected: {json.dumps(final)}")
    return work


def _export_onnx(net: Net, path: Path) -> None:
    """The scored graph with a dynamic batch, through torch's ``torch.export`` exporter.

    Measured 2026-10-01: opset 20, five operators (Gemm, LayerNormalization,
    Relu, Reshape, Sigmoid), every one served by ONNX Runtime Web's WASM backend.
    """
    # The exporter warns, once per operator it cannot register, that torchvision
    # is absent: nothing here uses it.
    logging.getLogger("torch.onnx").setLevel(logging.ERROR)
    batch = torch.export.Dim("batch", min=1, max=65_536)
    program = torch.onnx.export(
        Scored(net).eval(),
        (torch.zeros(2, EMBEDDINGS, EMBEDDING_DIM),),
        input_names=["input"],
        output_names=["score"],
        dynamic_shapes={"x": {0: batch}},
        dynamo=True,
    )
    assert program is not None
    program.save(str(path))
