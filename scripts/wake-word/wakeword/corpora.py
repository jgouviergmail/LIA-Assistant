"""The negative and background corpora, decoded once into banks (ADR-329).

- **FLEURS** (CC-BY 4.0): read speech in the language — negatives and babble;
  ``dev`` chooses the checkpoint and the threshold, ``test`` is held out for
  the false-accept measurement.
- **Multilingual LibriSpeech** (CC-BY 4.0): audiobook speech in the language —
  a spread subset of the training shards for negatives, ``dev`` and ``test``
  in the same two roles.
- **MUSAN** (CC-BY 4.0): music, noise, and (English) speech — backgrounds and
  negatives for every language; one file in five, chosen by a stable hash of
  its name, is held out for measurement.

Every archive is verified against the lock before it is opened, and a large
one is deleted once its bank is complete.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from typing import Any

import numpy as np
import soundfile

from wakeword.banks import (
    SAMPLE_RATE,
    BankWriter,
    Int16Array,
    bank_exists,
    bank_paths,
    open_bank,
    to_int16,
)
from wakeword.languages import LanguageSpec
from wakeword.paths import CORPORA
from wakeword.sources import Remote, discard, fetch, fleurs_remotes, mls_split, musan_remote

_AUDIO_SUFFIXES = (".wav", ".flac")
#: -70 dBFS: below it a segment holds no speech, music or noise worth the name.
_SILENCE_RMS = 10 ** (-70 / 20)
#: One MUSAN file in this many is held out for the measurement.
_MUSAN_TEST_EVERY = 5
#: Of the remaining English speech, one file in this many is kept for training:
#: a foreign language matters as a negative, not as twenty hours of it.
_MUSAN_SPEECH_TRAIN_EVERY = 3


def _stable_bucket(name: str, modulo: int) -> int:
    digest = hashlib.sha1(name.encode(), usedforsecurity=False).hexdigest()
    return int(digest, 16) % modulo


def _decoded(
    archive: tarfile.TarFile, keep: Callable[[str], bool] = lambda _name: True
) -> Iterator[tuple[str, Int16Array]]:
    """Every kept audio member of an archive as 16 kHz mono int16, refusing another rate."""
    for member in archive:
        if not member.isfile() or not member.name.endswith(_AUDIO_SUFFIXES):
            continue
        if not keep(member.name):
            continue
        handle = archive.extractfile(member)
        if handle is None:
            continue
        # Read as FLOAT, whatever the file holds: libsndfile scales integer PCM
        # to [-1, 1] but does NOT scale a float file read as int16 — every
        # FLEURS WAV is float32 and came out as zeros (measured 2026-10-01).
        data, rate = soundfile.read(io.BytesIO(handle.read()), dtype="float32", always_2d=False)
        if rate != SAMPLE_RATE:
            raise SystemExit(f"{member.name}: {rate} Hz where {SAMPLE_RATE} Hz was expected")
        yield member.name, to_int16(data)


def _bank_from_archives(name: str, archives: list[Remote], lock: dict[str, Any]) -> None:
    if bank_exists(CORPORA, name):
        return
    with BankWriter(CORPORA, name) as bank:
        for remote in archives:
            with tarfile.open(fetch(remote, lock), mode="r:gz") as archive:
                for member, audio in _decoded(archive):
                    bank.add(audio, {"source": remote.name, "file": member})
    assert_audible(name)
    print(f"bank {name}: {len(archives)} archive(s)")


def assert_audible(name: str, sample: int = 50) -> None:
    """Refuse a bank whose sampled segments are silence: a decoder failed in silence.

    Raises:
        SystemExit: Most of the sampled segments are below -70 dBFS; the bank
            is deleted so a rerun rebuilds it.
    """
    bank = open_bank(CORPORA, name)
    rng = np.random.default_rng(0)
    picked = rng.choice(len(bank), size=min(sample, len(bank)), replace=False)
    silent = 0
    for index in picked:
        segment = np.asarray(bank.segment(int(index)), dtype=np.float64)
        rms = np.sqrt(np.mean(segment**2)) / 32768.0 if segment.size else 0.0
        silent += int(rms < _SILENCE_RMS)
    if silent * 2 > len(picked):
        for path in bank_paths(CORPORA, name):
            path.unlink(missing_ok=True)
        raise SystemExit(f"bank {name}: {silent}/{len(picked)} sampled segments are silent")


def language_bank_names(spec: LanguageSpec) -> dict[str, list[str]]:
    """The language's banks by role: training negatives, validation, measurement."""
    names = {
        "train": [f"fleurs-{spec.fleurs}-train"],
        "dev": [f"fleurs-{spec.fleurs}-dev"],
        "test": [f"fleurs-{spec.fleurs}-test"],
    }
    if spec.mls:
        for role in names:
            names[role].append(f"mls-{spec.mls}-{role}")
    return names


def prepare_language(spec: LanguageSpec, lock: dict[str, Any]) -> None:
    """The language's FLEURS and MLS banks, one per split.

    ``train`` feeds the negatives, ``dev`` chooses the checkpoint and the
    threshold, ``test`` is touched by the final measurement only.
    """
    fleurs = fleurs_remotes(spec.fleurs)
    for split, remote in fleurs.items():
        _bank_from_archives(f"fleurs-{spec.fleurs}-{split}", [remote], lock)
    if spec.mls:
        for split in ("train", "dev", "test"):
            shards = mls_split(spec, lock, split)
            _bank_from_archives(f"mls-{spec.mls}-{split}", shards, lock)
            for remote in shards:
                discard(remote)
    for remote in fleurs.values():
        discard(remote)


MUSAN_KINDS = ("music", "noise", "speech")


def musan_bank_names() -> list[str]:
    """Every MUSAN bank, train and test, per kind."""
    return [f"musan-{kind}-{split}" for kind in MUSAN_KINDS for split in ("train", "test")]


def _musan_bank(member: str) -> str | None:
    """The bank a MUSAN file belongs to, or None when it is not kept."""
    parts = member.split("/")
    kind = parts[1] if len(parts) > 2 else ""
    if kind not in MUSAN_KINDS:
        return None
    held_out = _stable_bucket(member, _MUSAN_TEST_EVERY) == 0
    if kind == "speech" and not held_out:
        if _stable_bucket(member + "#train", _MUSAN_SPEECH_TRAIN_EVERY) != 0:
            return None
    return f"musan-{kind}-{'test' if held_out else 'train'}"


def prepare_musan(lock: dict[str, Any]) -> None:
    """Split MUSAN into six banks in ONE pass over its 11 GB archive."""
    if all(bank_exists(CORPORA, name) for name in musan_bank_names()):
        return
    remote = musan_remote()
    with ExitStack() as stack:
        writers = {
            name: stack.enter_context(BankWriter(CORPORA, name)) for name in musan_bank_names()
        }
        with tarfile.open(fetch(remote, lock), mode="r:gz") as archive:
            for member, audio in _decoded(archive, keep=lambda name: _musan_bank(name) is not None):
                bank = _musan_bank(member)
                assert bank is not None
                writers[bank].add(audio, {"source": remote.name, "file": member})
    for name in musan_bank_names():
        assert_audible(name)
    discard(remote)
    print("musan banks written")
