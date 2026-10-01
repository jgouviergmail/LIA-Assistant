"""Natural voices of the phrase and its near misses, by VoxCPM2 on a GPU (ADR-329).

Piper's voices are few per language and synthetic in their timbre; a model
taught on them alone learns what Piper sounds like. VoxCPM2 (Apache-2.0 code
and weights) says any text in thirty languages in a voice either DESIGNED from
a description — age, gender, timbre, pace, mood, accent — or CLONED from a real
recording: here the speech of the language's own corpora, so the phrase is
said in the timbres the negatives are spoken in. Measured 2026-10-01 on an RTX
4090: 2.4 times real time, a short phrase at its natural duration (no babble,
unlike Piper on two words). ``_GPU_WORKERS`` processes each hold the model,
for every bank of the language. Measured 2026-10-01 for one process: 0.4 s a
short clip, 5.6 GB of GPU memory, 2.6 GB of RAM once loaded but 11.3 GB while it
loads — so workers load ONE AT A TIME (three at once froze the WSL machine) —
and about 8.6 GB committed on a Windows host under WSL, which three workers took
to the host's commit limit beside the dev stack: one worker is the default.

Banks: ``vox-<lang>-{positive,near_miss}-{train,test}``. Training voices are
cloned from the TRAIN split of FLEURS and MLS and designed from one half of the
descriptions; test voices are cloned from the TEST split (MLS speakers are
disjoint across splits) and designed from the other half.
"""

from __future__ import annotations

import hashlib
import random
import tempfile
import time
import wave
from collections.abc import Iterator
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
from wakeword.banks import SAMPLE_RATE, Bank, BankWriter, bank_exists, open_bank
from wakeword.corpora import language_bank_names
from wakeword.languages import LanguageSpec
from wakeword.paths import CORPORA
from wakeword.sources import VOXCPM_REPOSITORY, VOXCPM_REVISION

Kind = Literal["positive", "near_miss"]
Split = Literal["train", "test"]

_OUTPUT_RATE = 48_000
#: Clips per bank: ``(designed, cloned)``.
_PLAN: dict[tuple[Kind, Split], tuple[int, int]] = {
    ("positive", "train"): (3_000, 3_000),
    ("positive", "test"): (300, 300),
    ("near_miss", "train"): (1_500, 1_500),
    ("near_miss", "test"): (200, 200),
}
#: Processes decoding at once on the one GPU, each holding the model (see above).
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


def _clips(spec: LanguageSpec, kind: Kind, split: Split, pool: Pool) -> Iterator[tuple[Job, Any]]:
    """Every clip of a bank, in plan order, decoded by the pool's workers."""
    names = reference_banks(spec, split)
    jobs = plan(spec, kind, split, {name: open_bank(CORPORA, name) for name in names})
    yield from pool.imap(_generate, jobs)


def clone_bank(spec: LanguageSpec, kind: Kind, split: Split, pool: Pool) -> str:
    """Write one natural-voice bank; returns its name (kept when already complete)."""
    name = f"vox-{spec.slug}-{kind}-{split}"
    if bank_exists(CORPORA, name):
        return name
    low, high = (
        tuple(factor * spec.phrase_seconds for factor in _POSITIVE_BAND)
        if kind == "positive"
        else _NEAR_MISS_SECONDS
    )
    kept = dropped = 0
    began = time.monotonic()
    with BankWriter(CORPORA, name) as bank:
        for job, audio in _clips(spec, kind, split, pool):
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
    """Every natural-voice bank of a language, on one pool of workers."""
    kinds: tuple[Kind, ...] = ("positive", "near_miss")
    splits: tuple[Split, ...] = ("train", "test")
    missing = [
        (kind, split)
        for kind in kinds
        for split in splits
        if not bank_exists(CORPORA, f"vox-{spec.slug}-{kind}-{split}")
    ]
    if not missing:
        return
    names = sorted({name for split in splits for name in reference_banks(spec, split)})
    # CUDA survives no fork: every worker starts afresh and loads its own model.
    context = get_context("spawn")
    with context.Pool(_GPU_WORKERS, _init_worker, (names, context.Lock())) as pool:
        for kind, split in missing:
            clone_bank(spec, kind, split, pool)
