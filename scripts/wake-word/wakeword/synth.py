"""Synthetic speech of the phrase and of its near misses, with Piper (ADR-329).

Measured on 2026-10-01 before this design was written: a Piper VITS voice
asked for a two-word utterance often babbles (« Dis Lia » alone lasted 7.5 s
on one voice; the 125-speaker MLS voice answered « Avis aussi, avis aussi… »),
and the MLS voice swallows the first plosive of an utterance. So every clip is
spoken INSIDE a sentence — a short lead-in and the pause after it, the phrase,
a long continuation — and the phrase is CUT out on the per-phoneme-id sample
counts the voice itself reports (the model is patched in memory to expose
them, as Piper does). The id layout of a token prefix is a prefix of the
layout of the whole, so the cut is exact on any phoneme type.

Each voice and speaker is first CALIBRATED: its median phrase duration at the
default rate sets the length scale that brings it to the language's natural
duration, then every clip draws a rate around it — a speaker who drawls is not
what the model learns the phrase sounds like. A cut outside the plausible
duration band is dropped and counted.

Diversity is the point of a synthetic set: every clip draws its voice and
speaker, its spelling, its lead-in and continuation, its rate and its noise
scales from a seeded generator. The VITS sampling noise itself is drawn inside
the voice model, so two runs are alike in distribution, not byte for byte.

Four banks per language: ``clips-<lang>-{positive,near_miss}-{train,test}``.
The TEST banks are synthesised from voices and speakers the model never hears
in training, so the measurement is of generalisation, not of memory. A bank
records the recipe of its plan (``recipe``): drawn from another plan — a near
miss added, a budget changed — it is synthesised again, never trained on as it
was.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from functools import cache
from multiprocessing import Pool
from typing import Any, Literal

import numpy as np
import onnx
import onnxruntime as ort
from piper import PiperConfig, PiperVoice, SynthesisConfig
from piper.config import PhonemeType
from piper.const import EOS
from piper.patch_voice_with_alignment import add_alignment_output
from piper.phonemize_espeak import EspeakPhonemizer

from wakeword.audio import FloatArray, faded, peak_int16, to_16k
from wakeword.banks import BankWriter, Int16Array, bank_exists, bank_recipe, drop_bank
from wakeword.languages import PIPER_REVISION, LanguageSpec, Voice
from wakeword.paths import CORPORA
from wakeword.sources import fetch, voice_remotes

Kind = Literal["positive", "near_miss"]
Split = Literal["train", "test"]

#: Clips per VOICE: ``(multi-speaker budget, single-speaker budget)``. A
#: multi-speaker voice spreads its budget over its speakers, at most
#: ``_PER_SPEAKER_CAP`` each (a 10-speaker voice must not outweigh a
#: 700-speaker one); a single-speaker voice spends it on prosody alone.
_PLAN: dict[tuple[Kind, Split], tuple[int, int]] = {
    ("positive", "train"): (10_000, 1_000),
    ("positive", "test"): (1_000, 200),
    ("near_miss", "train"): (4_000, 400),
    ("near_miss", "test"): (500, 100),
}
_PER_SPEAKER_CAP = {"train": 100, "test": 40}
#: Around the calibrated rate: from brisk to a little slow. Widened toward fast
#: on a measurement (2026-10-01, French, owner on dev): « dis … Lia » woke LIA,
#: « dilia » said at a natural pace did not — the phrase is said quickly.
_RATE_JITTER = (0.7, 1.3)
_NOISE_SCALE = (0.4, 0.8)
_NOISE_W_SCALE = (0.5, 0.9)
#: The calibrated length scale is clamped: beyond it the voice is not speaking.
_LENGTH_SCALE_BOUNDS = (0.25, 2.5)
_CALIBRATION_TAKES = 3
#: A positive cut must last within this band of the language's natural phrase
#: duration; a near miss within an absolute band.
_POSITIVE_BAND = (0.55, 1.9)
_NEAR_MISS_SECONDS = (0.2, 3.0)
_WORKERS = 14


@dataclass(frozen=True, slots=True)
class Job:
    """One clip to synthesise."""

    voice: Voice
    speaker: int
    text: str
    lead: str
    carrier: str
    rate: float
    noise_scale: float
    noise_w_scale: float
    target_seconds: float
    kind: Kind
    #: ``(phrase, lead-in, continuation)`` the speaker's rate is calibrated on:
    #: the same for every clip of the speaker, near misses included.
    calibration: tuple[str, str, str]


# -- the voice --------------------------------------------------------------------

_WORKER_LOCK: dict[str, Any] = {}


def _init_worker(lock: dict[str, Any]) -> None:
    _WORKER_LOCK.update(lock)


@cache
def _voice(voice: Voice) -> PiperVoice:
    """A Piper voice exposing its alignments, on a ONE-thread session (the pool is the parallelism)."""
    model_path, config_path = (fetch(remote, _WORKER_LOCK) for remote in voice_remotes(voice))
    model = onnx.load(str(model_path))
    add_alignment_output(model)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    # Measured 2026-10-01: with the arena, every new input length grew it and
    # fourteen workers held 22 GB; a sentence's buffers are cheap to allocate.
    options.enable_cpu_mem_arena = False
    session = ort.InferenceSession(
        model.SerializeToString(), options, providers=["CPUExecutionProvider"]
    )
    with config_path.open(encoding="utf-8") as handle:
        config = PiperConfig.from_dict(json.load(handle))
    return PiperVoice(session=session, config=config)


# -- phonemes ---------------------------------------------------------------------

_INLINE = re.compile(r"(\[\[.*?\]\])")
#: espeak writes a Mandarin tone as a digit after its syllable; a voice of
#: another language never learnt one, so the tones are dropped for it.
_TONAL = frozenset({"cmn"})
_TONE = re.compile(r"[1-5]")


@cache
def _phonemizer() -> EspeakPhonemizer:
    return EspeakPhonemizer()


def espeak_phonemes(text: str, language: str, foreign: bool = False) -> str:
    """The text phonemised in ``language``, inline ``[[ … ]]`` phonemes kept as written."""
    parts = []
    for part in _INLINE.split(text):
        if part.startswith("[["):
            parts.append(part[2:-2].strip())
        elif part.strip():
            sentences = _phonemizer().phonemize(language, part)
            phonemes = " ".join("".join(sentence) for sentence in sentences)
            parts.append(_TONE.sub("", phonemes) if foreign and language in _TONAL else phonemes)
    return " ".join(parts)


def _pinyin_tokens(voice: PiperVoice, text: str) -> list[str]:
    return [token for sentence in voice.phonemize(text) for token in sentence]


def _layout(
    voice: PiperVoice, job: Job, text: str, lead: str, carrier: str
) -> tuple[list[int], int, int] | None:
    """The ids of the whole sentence and the id span of the phrase, or None when it cannot be cut.

    A token list's ids are BOS, PAD, every token's ids each followed by PAD,
    then EOS: a prefix's ids, EOS removed, are a prefix of the whole's. The
    pause after the lead-in and before the continuation is the comma the
    voice itself reads. A phrase token the voice cannot say makes the clip
    unusable (Piper would drop it in silence).
    """
    if voice.config.phoneme_type == PhonemeType.PINYIN:
        lead_tokens = _pinyin_tokens(voice, lead)
        head = _pinyin_tokens(voice, lead + text)
        whole = _pinyin_tokens(voice, lead + text + "，" + carrier)
    else:
        # A voice of the language reads with its own espeak voice (en-gb for a
        # British one); a voice of another language reads the spec's.
        language = job.voice.reads_as or voice.config.espeak_voice
        foreign = job.voice.reads_as is not None
        said = [espeak_phonemes(part, language, foreign) for part in (lead, text, carrier)]
        lead_tokens = list(said[0] + " ")
        head = list(said[0] + " " + said[1])
        whole = list(said[0] + " " + said[1] + ", " + said[2])
    if whole[: len(head)] != head or len(head) <= len(lead_tokens):
        return None
    if any(token not in voice.config.phoneme_id_map for token in head[len(lead_tokens) :]):
        return None
    eos = len(voice.config.phoneme_id_map[EOS])
    start = len(voice.phonemes_to_ids(lead_tokens)) - eos
    end = len(voice.phonemes_to_ids(head)) - eos
    return voice.phonemes_to_ids(whole), start, end


def _speak(
    voice: PiperVoice, job: Job, text: str, lead: str, carrier: str, length_scale: float
) -> FloatArray | None:
    """``text`` said between ``lead`` and ``carrier``, cut out of the sentence, or None."""
    layout = _layout(voice, job, text, lead, carrier)
    if layout is None:
        return None
    ids, start, end = layout
    config = SynthesisConfig(
        speaker_id=job.speaker if voice.config.num_speakers > 1 else None,
        length_scale=length_scale,
        noise_scale=job.noise_scale,
        noise_w_scale=job.noise_w_scale,
    )
    result = voice.phoneme_ids_to_audio(ids, config, include_alignments=True)
    if not isinstance(result, tuple):
        return None
    audio, samples = result
    if samples is None:
        return None
    first = int(np.sum(samples[:start]))
    last = int(np.sum(samples[:end]))
    return np.asarray(np.squeeze(audio)[first:last], dtype=np.float32)


@cache
def _calibrate(
    voice: Voice, speaker: int, calibration: tuple[str, str, str], target: float
) -> float:
    """The length scale bringing this speaker's phrase to ``target`` seconds (median of takes).

    Cached per speaker: every clip of a speaker, near misses included, shares
    the base its own rate is drawn around.
    """
    piper = _voice(voice)
    phrase, lead, carrier = calibration
    probe = Job(
        voice, speaker, phrase, lead, carrier, 1.0, 0.6, 0.7, target, "positive", calibration
    )
    durations = []
    for _ in range(_CALIBRATION_TAKES):
        audio = _speak(piper, probe, phrase, lead, carrier, 1.0)
        if audio is not None and audio.size:
            durations.append(audio.size / piper.config.sample_rate)
    if not durations:
        return 1.0
    low, high = _LENGTH_SCALE_BOUNDS
    return float(np.clip(target / float(np.median(durations)), low, high))


# -- one clip ---------------------------------------------------------------------


def synthesise(job: Job) -> Int16Array | None:
    """One clip, 16 kHz int16, peak-normalised; None when it is not usable."""
    voice = _voice(job.voice)
    base = _calibrate(job.voice, job.speaker, job.calibration, job.target_seconds)
    audio = _speak(voice, job, job.text, job.lead, job.carrier, base * job.rate)
    if audio is None or audio.size == 0:
        return None
    seconds = audio.size / voice.config.sample_rate
    if job.kind == "positive":
        low, high = (factor * job.target_seconds for factor in _POSITIVE_BAND)
    else:
        low, high = _NEAR_MISS_SECONDS
    if not low <= seconds <= high:
        return None
    return peak_int16(faded(to_16k(audio, voice.config.sample_rate)))


def _run(job: Job) -> tuple[Job, Int16Array | None]:
    return job, synthesise(job)


# -- a bank -----------------------------------------------------------------------


def plan(spec: LanguageSpec, kind: Kind, split: Split, seed: int) -> list[Job]:
    """The clips of one bank, drawn reproducibly from ``seed``."""
    rng = random.Random(f"{spec.slug}:{kind}:{split}:{seed}")
    texts = spec.positives if kind == "positive" else spec.near_misses
    multi_budget, single_budget = _PLAN[(kind, split)]
    voices = spec.train_voices if split == "train" else spec.test_voices
    jobs = []
    for voice in voices:
        if len(voice.speakers) > 1:
            count = min(_PER_SPEAKER_CAP[split], multi_budget // len(voice.speakers))
        else:
            count = single_budget
        count = max(1, round(count * voice.share))
        for speaker in voice.speakers:
            # Each speaker cycles through every text from its own starting
            # point before any repeats; lead-in, continuation and rate vary.
            offset = rng.randrange(len(texts))
            for index in range(count):
                jobs.append(
                    Job(
                        voice,
                        speaker,
                        texts[(index + offset) % len(texts)],
                        rng.choice(spec.leads),
                        rng.choice(spec.carriers),
                        rng.uniform(*_RATE_JITTER),
                        rng.uniform(*_NOISE_SCALE),
                        rng.uniform(*_NOISE_W_SCALE),
                        spec.phrase_seconds,
                        kind,
                        (spec.positives[0], spec.leads[0], spec.carriers[0]),
                    )
                )
    jobs.sort(key=lambda job: (job.voice.key, job.voice.reads_as or "", job.speaker))
    return jobs


def recipe(jobs: list[Job]) -> str:
    """A plan's digest: every clip it draws, the bands a cut is kept in, the voices' revision."""
    clips = [
        [
            job.voice.key,
            job.voice.reads_as,
            job.speaker,
            job.text,
            job.lead,
            job.carrier,
            job.rate,
            job.noise_scale,
            job.noise_w_scale,
            job.target_seconds,
            job.kind,
            list(job.calibration),
        ]
        for job in jobs
    ]
    payload = {
        "piper": PIPER_REVISION,
        "bands": [_POSITIVE_BAND, _NEAR_MISS_SECONDS],
        "clips": clips,
    }
    return hashlib.sha1(json.dumps(payload).encode(), usedforsecurity=False).hexdigest()


def synthesise_bank(
    spec: LanguageSpec, kind: Kind, split: Split, lock: dict[str, Any], seed: int = 0
) -> str:
    """Write one clip bank; returns its name (kept when complete under the same plan)."""
    name = f"clips-{spec.slug}-{kind}-{split}"
    jobs = plan(spec, kind, split, seed)
    digest = recipe(jobs)
    if bank_exists(CORPORA, name):
        if bank_recipe(CORPORA, name) == digest:
            return name
        print(f"bank {name}: drawn from another plan, synthesised again")
        drop_bank(CORPORA, name)
    for voice in {job.voice for job in jobs}:
        for remote in voice_remotes(voice):
            fetch(remote, lock)
    dropped: dict[str, int] = {}
    with (
        BankWriter(CORPORA, name, recipe=digest) as bank,
        Pool(_WORKERS, initializer=_init_worker, initargs=(lock,)) as pool,
    ):
        for job, audio in pool.imap(_run, jobs, chunksize=16):
            if audio is None:
                key = job.voice.key + (f" as {job.voice.reads_as}" if job.voice.reads_as else "")
                dropped[key] = dropped.get(key, 0) + 1
                continue
            meta: dict[str, Any] = {
                "voice": job.voice.key,
                "speaker": job.speaker,
                "text": job.text,
            }
            if job.voice.reads_as:
                meta["reads_as"] = job.voice.reads_as
            bank.add(audio, meta)
    kept = len(jobs) - sum(dropped.values())
    print(f"bank {name}: {kept}/{len(jobs)} clips; dropped by voice: {dropped}")
    return name
