"""Two headlines of one event, read by meaning (ADR-324 decision 34).

The newsroom tells a story once per STORY — a fingerprint across outlets, a
near-identical headline (``editorial.same_headline``) — but an event reported by
one outlet under ten headlines shares too few WORDS for either: « L'Espagne
renverse l'Angleterre à Wembley » and « L'Espagne continue sur sa lancée en
renversant l'Angleterre à Londres » have two in common. Their meanings are close.

Measured 2026-09-27 on the dev newsroom (80 stories of two outlets, 101 pairs
labelled by hand), comparing the platform's embeddings of the HEADLINES alone:
outside the one story twenty articles covered (a papal visit), every pair telling
one event stood at 0.906 or more (a match, a storm, a crash told by two outlets,
a demonstration, an election day) and two distinct events at 0.871 at most;
inside it, one event and two overlapped between 0.874 and 0.898 (two masses, on
two days, at 0.898). At 0.9 nothing distinct is joined, and a big story's other
angles stay the writer's to judge, shown what was heard. Headline and summary
together separated worse: one match told twice fell to 0.823.

The vectors are the ANTENNA's, never the newsroom's (decision 1: the newsroom
costs no model): a headline is embedded the first time a session's desk reads
it, on that listener's run, and kept in Redis for every other listener as long
as its story may air. A blind reading is never an obstacle: the word rules
still judge.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from src.domains.radio.editorial import NEWS_MAX_AGE_S

#: A headline's vector, kept as the provider's float32: 6 KB at 1 536 dimensions,
#: where a tuple of Python floats weighs 49 KB — held by every live session.
Vector = npt.NDArray[np.float32]


def headline_key(title: str) -> str:
    """A headline as it is read: its words, single-spaced."""
    return " ".join(title.split())


@dataclass(frozen=True, slots=True, eq=False)
class HeadlineMeanings:
    """Which headlines tell one event: the similarity of every pair, decided once.

    Build it with :meth:`of`; the cosine of two unit vectors is their dot
    product, so the whole relation is one matrix product.
    """

    index: Mapping[str, int]
    same: np.ndarray

    @classmethod
    def of(cls, vectors: Mapping[str, npt.ArrayLike], threshold: float) -> HeadlineMeanings:
        """The relation over the headlines read.

        Args:
            vectors: A vector per headline (any length; an empty one matches nothing).
            threshold: The cosine at and above which two headlines tell one event.

        Returns:
            The relation, keyed by :func:`headline_key`.
        """
        titles = list(vectors)
        if not titles:
            return cls(index={}, same=np.zeros((0, 0), dtype=bool))
        matrix = np.asarray([vectors[title] for title in titles], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        unit = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)
        return cls(
            index={headline_key(title): row for row, title in enumerate(titles)},
            same=(unit @ unit.T) >= threshold,
        )

    def same_event(self, first: str, second: str) -> bool:
        """Whether two headlines tell one event; a headline never read tells none."""
        row = self.index.get(headline_key(first))
        column = self.index.get(headline_key(second))
        return row is not None and column is not None and bool(self.same[row, column])

    def told_among(self, titles: Sequence[str], told: Sequence[str]) -> frozenset[str]:
        """The headlines of ``titles`` that tell the event of one of ``told``, read at once.

        One slice of the relation, never a pair at a time: a desk holds hundreds of
        stories and two days of headlines heard. A headline never read tells none.

        Args:
            titles: The headlines to read.
            told: The headlines already told.

        Returns:
            The headlines of ``titles`` concerned, as they were given.
        """
        columns = [column for column in map(self._row, told) if column is not None]
        rows = [(title, row) for title in titles if (row := self._row(title)) is not None]
        if not columns or not rows:
            return frozenset()
        block = self.same[np.ix_([row for _, row in rows], columns)]
        hits = np.asarray(block.any(axis=1), dtype=bool)
        return frozenset(title for (title, _), hit in zip(rows, hits, strict=True) if hit)

    def _row(self, title: str) -> int | None:
        return self.index.get(headline_key(title))


Embed = Callable[[list[str]], Awaitable[list[list[float]]]]


class RedisHeadlineVectors:
    """The headlines' vectors, shared by every listener (family ``radio:headline``, global).

    A vector is keyed by the model and the size that made it, so a changed
    embedding configuration never compares two spaces.
    """

    def __init__(self, redis: Any, *, embed: Embed, model: str, dimensions: int) -> None:
        """Bind the cache to its client and to the embedding door.

        Args:
            redis: A ``decode_responses`` Redis client.
            embed: The platform's embedding of documents (it bills the active run).
            model: The embedding model's name.
            dimensions: The size of its vectors.
        """
        self._redis = redis
        self._embed = embed
        self._model = model
        self._dimensions = dimensions

    def _key(self, title: str) -> str:
        digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
        return f"radio:headline:{self._model}:{self._dimensions}:{digest}"

    async def vectors(self, titles: Sequence[str]) -> dict[str, Vector]:
        """A vector for each headline: kept ones read, the others embedded in one call.

        Args:
            titles: The headlines, as :func:`headline_key` reads them.

        Returns:
            Every headline's vector.

        Raises:
            ValueError: When the provider answers for another number of headlines, or
                with vectors of another size — then nothing is kept: which vector is
                whose cannot be told, and one space must never meet another.
            Exception: Whatever the embedding door or Redis raises.
        """
        if not titles:
            return {}
        stored = await self._redis.mget([self._key(title) for title in titles])
        found = {
            title: kept
            for title, raw in zip(titles, stored, strict=True)
            if (kept := self._decoded(raw)) is not None
        }
        missing = [title for title in titles if title not in found]
        if missing:
            made = await self._embed(missing)
            if len(made) != len(missing) or any(len(v) != self._dimensions for v in made):
                raise ValueError("the embedding answered another shape than it was asked")
            for title, values in zip(missing, made, strict=True):
                vector = np.asarray(values, dtype=np.float32)
                found[title] = vector
                await self._redis.set(self._key(title), _encoded(vector), ex=NEWS_MAX_AGE_S)
        return found

    def _decoded(self, raw: str | None) -> Vector | None:
        """A kept vector, or None when it is absent or unreadable."""
        if raw is None:
            return None
        try:
            values = np.frombuffer(base64.b64decode(raw, validate=True), dtype=np.float32)
        except ValueError:  # binascii.Error included: not base64, or not whole floats
            return None
        return values if len(values) == self._dimensions else None


def _encoded(vector: Vector) -> str:
    return base64.b64encode(vector.tobytes()).decode("ascii")


__all__ = ["HeadlineMeanings", "RedisHeadlineVectors", "Vector", "headline_key"]
