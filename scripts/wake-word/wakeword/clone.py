"""Natural voices of the phrase and its near misses, by VoxCPM2 on a GPU (ADR-329).

Piper's voices are few per language and synthetic in their timbre; a model
taught on them alone learns what Piper sounds like. VoxCPM2 (Apache-2.0 code
and weights) says any text in thirty languages in a voice either DESIGNED from
a description — age, gender, timbre, pace, mood, accent — or CLONED from a real
recording: here the speech of the language's own corpora, so the phrase is
said in the timbres the negatives are spoken in. Measured 2026-10-01 on an RTX
4090: 2.4 times real time, a short phrase at its natural duration (no babble,
unlike Piper on two words). ONE process holds the model, for every bank of the
language — measured 2026-10-02 on an RTX 4090: it alone keeps the GPU busy,
0.48 s a clip, and a second process only time-slices it (no MPS under Windows
or WSL): 0.66 s a clip for the two together. A process takes 6 GB of GPU
memory and 2.6 GB of RAM once loaded, 11 GB of RAM while it loads — the
library builds the model in full precision in RAM; three loading at once froze
the WSL machine (2026-10-01).

Banks: ``vox-<lang>-{positive,near_miss}-{train,test}``. Training voices are
cloned from the TRAIN split of FLEURS and MLS and designed from one half of the
descriptions; test voices are cloned from the TEST split (MLS speakers are
disjoint across splits) and designed from the other half. A bank records the
recipe of its plan, the recordings it cloned included (``recipe``): drawn from
another plan — a near miss added, a budget changed, the training speakers
chosen anew — it is generated again.
"""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import time
import wave
from dataclasses import dataclass
from itertools import product
from multiprocessing import get_context
from multiprocessing.pool import Pool
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from huggingface_hub import snapshot_download
from voxcpm import VoxCPM

from wakeword.audio import faded, peak_int16, to_16k, trim
from wakeword.banks import (
    SAMPLE_RATE,
    Bank,
    BankWriter,
    bank_exists,
    bank_fingerprint,
    bank_recipe,
    drop_bank,
    open_bank,
)
from wakeword.corpora import language_bank_names
from wakeword.languages import LanguageSpec
from wakeword.paths import CORPORA
from wakeword.sources import VOXCPM_REPOSITORY, VOXCPM_REVISION

Kind = Literal["positive", "near_miss"]
Split = Literal["train", "test"]
_KINDS: tuple[Kind, ...] = ("positive", "near_miss")
_SPLITS: tuple[Split, ...] = ("train", "test")

_OUTPUT_RATE = 48_000
#: Clips per bank: ``(designed, cloned)``.
_PLAN: dict[tuple[Kind, Split], tuple[int, int]] = {
    ("positive", "train"): (3_000, 3_000),
    ("positive", "test"): (300, 300),
    ("near_miss", "train"): (1_500, 1_500),
    ("near_miss", "test"): (200, 200),
}
#: Processes decoding at once on the one GPU (see above): one.
_GPU_WORKERS = 1
#: A long bank says how far it is every so many clips.
_PROGRESS_EVERY = 500
_CFG = (1.6, 2.6)
_INFERENCE_TIMESTEPS = 10
#: A reference recording long enough to carry a timbre, short enough to be one voice.
_REFERENCE_SECONDS = (3.0, 10.0)
#: A positive is kept within this band of the phrase's natural duration: « Stop ! »
#: lasts a third of a second where « Dis, Lia ! » lasts a second.
_POSITIVE_BAND = (0.55, 3.2)
_NEAR_MISS_SECONDS = (0.25, 3.5)

_AGES = ("teenage", "young", "middle-aged", "elderly")
_GENDERS = ("man", "woman")
_TIMBRES = ("deep", "bright", "husky", "soft", "warm", "nasal", "thin", "resonant")
_PACES = ("slowly", "at an ordinary pace", "quickly")
_MOODS = ("calmly", "cheerfully", "tiredly", "with curiosity", "in a hurry", "softly")


@dataclass(frozen=True, slots=True)
class Job:
    """One clip: a text, and either a description or a reference recording."""

    text: str
    description: str | None
    reference: tuple[str, int] | None
    cfg: float
    seed: int


def descriptions(spec: LanguageSpec, split: Split) -> list[str]:
    """Every designed voice of a split: the description space halved by a stable hash."""
    voices = []
    for age, gender, timbre, pace, mood, accent in product(
        _AGES, _GENDERS, _TIMBRES, _PACES, _MOODS, spec.accents
    ):
        text = (
            f"(A {age} {gender} with a {timbre} voice and a {accent} accent, "
            f"speaking {pace} and {mood})"
        )
        digest = hashlib.sha1(text.encode(), usedforsecurity=False).digest()[0]
        if (digest % 2 == 0) == (split == "train"):
            voices.append(text)
    return voices


def reference_banks(spec: LanguageSpec, split: Split) -> list[str]:
    """The corpora a split's voices are cloned from: train for training, test for the measure."""
    return language_bank_names(spec)["train" if split == "train" else "test"]


def plan(
    spec: LanguageSpec, kind: Kind, split: Split, banks: dict[str, Bank], seed: int = 0
) -> list[Job]:
    """The clips of one bank, drawn reproducibly from ``seed``."""
    rng = random.Random(f"vox:{spec.slug}:{kind}:{split}:{seed}")
    texts = spec.spoken if kind == "positive" else spec.near_misses
    designed, cloned = _PLAN[(kind, split)]
    voices = descriptions(spec, split)
    references = [
        (name, index)
        for name, bank in banks.items()
        for index in range(len(bank))
        if _REFERENCE_SECONDS[0] * SAMPLE_RATE
        <= bank.offsets[index + 1] - bank.offsets[index]
        <= _REFERENCE_SECONDS[1] * SAMPLE_RATE
    ]
    jobs = [
        Job(
            texts[i % len(texts)],
            rng.choice(voices),
            None,
            rng.uniform(*_CFG),
            rng.randrange(2**31),
        )
        for i in range(designed)
    ]
    jobs += [
        Job(
            texts[i % len(texts)],
            None,
            rng.choice(references),
            rng.uniform(*_CFG),
            rng.randrange(2**31),
        )
        for i in range(cloned)
    ]
    rng.shuffle(jobs)
    return jobs


def recipe(jobs: list[Job], references: dict[str, str]) -> str:
    """A plan's digest: its clips, the fingerprints of the banks it clones, the model."""
    payload = {
        "voxcpm": VOXCPM_REVISION,
        "timesteps": _INFERENCE_TIMESTEPS,
        "bands": [_POSITIVE_BAND, _NEAR_MISS_SECONDS],
        "references": references,
        "clips": [[job.text, job.description, job.reference, job.cfg, job.seed] for job in jobs],
    }
    return hashlib.sha1(json.dumps(payload).encode(), usedforsecurity=False).hexdigest()


Plans = dict[tuple[Kind, Split], tuple[list[Job], str]]


def plans(spec: LanguageSpec) -> Plans:
    """Every bank's plan and recipe (the reference banks read once per split)."""
    out: Plans = {}
    for split in _SPLITS:
        names = reference_banks(spec, split)
        banks = {name: open_bank(CORPORA, name) for name in names}
        fingerprints = {name: bank_fingerprint(CORPORA, name) for name in names}
        for kind in _KINDS:
            jobs = plan(spec, kind, split, banks)
            out[(kind, split)] = (jobs, recipe(jobs, fingerprints))
    return out


def _model() -> VoxCPM:
    """The pinned model, WITHOUT its denoiser: a reference's room and microphone are part
    of the voice a cloned clip should carry (the augmentation adds the rest)."""
    path = snapshot_download(VOXCPM_REPOSITORY, revision=VOXCPM_REVISION)
    return VoxCPM.from_pretrained(path, load_denoiser=False)


def _write_reference(path: Path, bank: Bank, index: int) -> Path:
    """A reference recording as the WAV file the model reads (one file per worker, rewritten)."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(np.asarray(bank.segment(index)).tobytes())
    return path


#: One worker's model, reference banks and reference file (set by ``_init_worker``).
_WORKER: dict[str, Any] = {}


def _init_worker(bank_names: list[str], loading: Lock) -> None:
    # One worker loads at a time: a load peaks at four times what the loaded model holds.
    with loading:
        _WORKER["model"] = _model()
    _WORKER["banks"] = {name: open_bank(CORPORA, name) for name in bank_names}
    _WORKER["reference"] = Path(tempfile.mkdtemp(prefix="vox-")) / "reference.wav"


def _generate(job: Job) -> tuple[Job, Any]:
    """One clip, 16 kHz float, trimmed (in a worker)."""
    model: VoxCPM = _WORKER["model"]
    torch.manual_seed(job.seed)
    if job.reference is not None:
        name, index = job.reference
        reference = _write_reference(_WORKER["reference"], _WORKER["banks"][name], index)
        wav = model.generate(
            text=job.text,
            reference_wav_path=str(reference),
            cfg_value=job.cfg,
            inference_timesteps=_INFERENCE_TIMESTEPS,
        )
    else:
        wav = model.generate(
            text=f"{job.description}{job.text}",
            cfg_value=job.cfg,
            inference_timesteps=_INFERENCE_TIMESTEPS,
        )
    return job, trim(to_16k(np.asarray(wav, dtype=np.float32).reshape(-1), _OUTPUT_RATE))


def _bank_name(spec: LanguageSpec, kind: Kind, split: Split) -> str:
    return f"vox-{spec.slug}-{kind}-{split}"


def _current(name: str, digest: str) -> bool:
    return bank_exists(CORPORA, name) and bank_recipe(CORPORA, name) == digest


def clone_bank(
    spec: LanguageSpec, kind: Kind, split: Split, jobs: list[Job], digest: str, pool: Pool
) -> str:
    """Write one natural-voice bank from its plan; returns its name (kept when current)."""
    name = _bank_name(spec, kind, split)
    if _current(name, digest):
        return name
    if bank_exists(CORPORA, name):
        print(f"bank {name}: drawn from another plan, generated again")
        drop_bank(CORPORA, name)
    low, high = (
        tuple(factor * spec.phrase_seconds for factor in _POSITIVE_BAND)
        if kind == "positive"
        else _NEAR_MISS_SECONDS
    )
    kept = dropped = 0
    began = time.monotonic()
    with BankWriter(CORPORA, name, recipe=digest) as bank:
        for job, audio in pool.imap(_generate, jobs):
            if (kept + dropped) % _PROGRESS_EVERY == 0:
                print(
                    f"{name}: {kept + dropped} clips, {time.monotonic() - began:.0f} s", flush=True
                )
            if not low <= audio.size / SAMPLE_RATE <= high:
                dropped += 1
                continue
            voice = f"cloned:{job.reference[0]}" if job.reference else "designed"
            bank.add(peak_int16(faded(audio)), {"voice": voice, "text": job.text})
            kept += 1
    print(f"bank {name}: {kept} kept, {dropped} dropped on duration")
    return name


def clone_language(spec: LanguageSpec) -> None:
    """Every natural-voice bank of a language that is missing or stale, on one pool."""
    every = plans(spec)
    due = [
        key for key, (_, digest) in every.items() if not _current(_bank_name(spec, *key), digest)
    ]
    if not due:
        return
    names = sorted({name for split in _SPLITS for name in reference_banks(spec, split)})
    # CUDA survives no fork: the worker starts afresh and loads its own model.
    context = get_context("spawn")
    with context.Pool(_GPU_WORKERS, _init_worker, (names, context.Lock())) as pool:
        for kind, split in due:
            jobs, digest = every[(kind, split)]
            clone_bank(spec, kind, split, jobs, digest, pool)
