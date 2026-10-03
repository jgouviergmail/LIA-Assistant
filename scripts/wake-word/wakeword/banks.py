"""An audio bank: many 16 kHz mono int16 segments in one memory-mapped file.

``<name>.pcm`` holds the samples end to end and ``<name>.json`` their offsets,
names and per-segment metadata. A bank is written once, through a writer that
streams to disk (MUSAN's music alone is forty hours: never held in memory), and
read through ``numpy.memmap`` by every later step.

A synthesised bank also records its RECIPE — a digest of the plan it was drawn
from — so a spec that changed (another near miss, another plan size) finds the
bank stale instead of training on the old clips; and anything computed from a
bank records the bank's FINGERPRINT, so a bank rebuilt since is never read
through a cache of the old one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 16_000

Int16Array = npt.NDArray[np.int16]


@dataclass(slots=True)
class Bank:
    """A read-only bank.

    Attributes:
        name: Its file stem.
        samples: Every sample, memory-mapped.
        offsets: ``offsets[i]:offsets[i+1]`` is segment ``i``.
        meta: One dict per segment (its source name, and whatever its writer kept).
    """

    name: str
    samples: Int16Array
    offsets: npt.NDArray[np.int64]
    meta: list[dict[str, Any]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.offsets) - 1

    def segment(self, index: int) -> Int16Array:
        """One segment, as a view."""
        return self.samples[int(self.offsets[index]) : int(self.offsets[index + 1])]


def bank_paths(directory: Path, name: str) -> tuple[Path, Path]:
    """The two files of a bank."""
    return directory / f"{name}.pcm", directory / f"{name}.json"


def bank_exists(directory: Path, name: str) -> bool:
    """A bank is complete only once its index was written (it is written last)."""
    return bank_paths(directory, name)[1].exists()


def bank_recipe(directory: Path, name: str) -> str | None:
    """The recipe a complete bank was written under, or None (a corpus, or written before)."""
    info = json.loads(bank_paths(directory, name)[1].read_text(encoding="utf-8"))
    recipe = info.get("recipe")
    return str(recipe) if recipe is not None else None


def bank_fingerprint(directory: Path, name: str) -> str:
    """What a complete bank holds, in one word: the SHA-1 of its index.

    The index lists every segment's length and metadata (and the recipe): two
    builds of a bank from other audio never share it.
    """
    index = bank_paths(directory, name)[1].read_bytes()
    return hashlib.sha1(index, usedforsecurity=False).hexdigest()


def drop_bank(directory: Path, name: str) -> None:
    """Delete a bank's two files (a stale bank, before it is written again)."""
    for path in bank_paths(directory, name):
        path.unlink(missing_ok=True)


def open_bank(directory: Path, name: str) -> Bank:
    """Read a complete bank."""
    pcm, index = bank_paths(directory, name)
    info = json.loads(index.read_text(encoding="utf-8"))
    offsets = np.asarray(info["offsets"], dtype=np.int64)
    total = int(offsets[-1])
    samples: Int16Array = (
        np.memmap(pcm, dtype=np.int16, mode="r", shape=(total,))
        if total
        else np.zeros(0, dtype=np.int16)
    )
    return Bank(name, samples, offsets, list(info["meta"]))


class BankWriter:
    """Append segments to a new bank; the index is written on a clean exit only.

    ``recipe`` is recorded in the index (see ``bank_recipe``).
    """

    def __init__(self, directory: Path, name: str, recipe: str | None = None) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._pcm, self._index = bank_paths(directory, name)
        self._index.unlink(missing_ok=True)
        self._handle = self._pcm.open("wb")
        self._offsets = [0]
        self._meta: list[dict[str, Any]] = []
        self._recipe = recipe

    def add(self, samples: Int16Array, meta: dict[str, Any]) -> None:
        """Append one segment (an empty one is skipped)."""
        if samples.size == 0:
            return
        self._handle.write(np.ascontiguousarray(samples, dtype=np.int16).tobytes())
        self._offsets.append(self._offsets[-1] + int(samples.size))
        self._meta.append(meta)

    def __enter__(self) -> BankWriter:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._handle.close()
        if kind is not None:
            # A half-written bank must never pass for a complete one.
            self._pcm.unlink(missing_ok=True)
            return
        payload: dict[str, Any] = {"offsets": self._offsets, "meta": self._meta}
        if self._recipe is not None:
            payload["recipe"] = self._recipe
        self._index.write_text(json.dumps(payload), encoding="utf-8")


def to_int16(audio: npt.NDArray[np.floating[Any]] | Int16Array) -> Int16Array:
    """Mono int16 from whatever a decoder returned (float in [-1, 1] or int16)."""
    if audio.dtype == np.int16:
        integers = np.asarray(audio, dtype=np.int16)
        if integers.ndim == 2:
            return integers.astype(np.int32).mean(axis=1).astype(np.int16)
        return integers
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)
    return (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
