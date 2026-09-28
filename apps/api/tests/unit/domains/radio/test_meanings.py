"""Two headlines of one event, read by meaning — and the vectors every listener shares."""

from __future__ import annotations

import base64
import math
import struct

import numpy as np
import pytest

from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.meanings import (
    HeadlineMeanings,
    RedisHeadlineVectors,
    Vector,
    headline_key,
)
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit


def at(degrees: float) -> tuple[float, float]:
    """A unit vector of the plane: two of them are as close as the cosine of their gap."""
    return (math.cos(math.radians(degrees)), math.sin(math.radians(degrees)))


class TestHeadlineMeanings:
    VECTORS = {"match": at(0), "match again": at(20), "another match": at(45)}

    def test_two_headlines_close_enough_in_meaning_tell_one_event(self) -> None:
        meanings = HeadlineMeanings.of(self.VECTORS, threshold=0.9)  # cos 20° = 0.94
        assert meanings.same_event("match", "match again")
        assert meanings.same_event("match again", "match")

    def test_two_neighbouring_events_are_two(self) -> None:
        meanings = HeadlineMeanings.of(self.VECTORS, threshold=0.9)  # cos 45° = 0.71
        assert not meanings.same_event("match", "another match")

    def test_the_threshold_decides(self) -> None:
        assert HeadlineMeanings.of(self.VECTORS, threshold=0.7).same_event("match", "another match")

    def test_a_headline_whose_meaning_is_unknown_is_never_the_same_event(self) -> None:
        meanings = HeadlineMeanings.of(self.VECTORS, threshold=0.5)
        assert not meanings.same_event("match", "a headline never read")

    def test_the_length_of_a_vector_does_not_count(self) -> None:
        meanings = HeadlineMeanings.of(
            {
                "short": (0.3, 0.0),
                "short too": (0.3, 0.01),
                "long": (3.0, 0.0),
                "aside": (2.0, 3.0),
            },
            threshold=0.9,
        )
        assert meanings.same_event("short", "short too")  # cosine 0.999, product 0.09
        assert not meanings.same_event("long", "aside")  # cosine 0.55, product 6

    def test_an_empty_vector_matches_nothing(self) -> None:
        meanings = HeadlineMeanings.of({"a": (0.0, 0.0), "b": (0.0, 0.0)}, threshold=0.1)
        assert not meanings.same_event("a", "b")

    def test_a_headline_is_read_whatever_its_spacing(self) -> None:
        meanings = HeadlineMeanings.of(
            {"  Spain  beat England ": at(0), "Spain won": at(10)}, threshold=0.9
        )
        assert meanings.same_event("Spain beat\nEngland", "Spain won")
        assert headline_key("  Spain  beat England ") == "Spain beat England"

    def test_no_headline_read_is_no_event(self) -> None:
        assert not HeadlineMeanings.of({}, threshold=0.9).same_event("a", "b")

    def test_the_headlines_telling_one_already_told_are_read_at_once(self) -> None:
        meanings = HeadlineMeanings.of(
            {**self.VECTORS, "rain": at(90), "rain again": at(95)}, threshold=0.9
        )
        told = meanings.told_among(
            ["match again", "another match", "rain again", "never read"], ["match", "rain"]
        )
        # The titles come back as they were given; one never read tells nothing.
        assert told == frozenset({"match again", "rain again"})

    def test_nothing_told_or_nothing_read_tells_nothing(self) -> None:
        meanings = HeadlineMeanings.of(self.VECTORS, threshold=0.9)
        assert meanings.told_among(["match again"], []) == frozenset()
        assert meanings.told_among([], ["match"]) == frozenset()
        assert meanings.told_among(["match again"], ["never read"]) == frozenset()
        assert HeadlineMeanings.of({}, threshold=0.9).told_among(["a"], ["b"]) == frozenset()

    def test_a_headline_is_told_whatever_its_spacing(self) -> None:
        meanings = HeadlineMeanings.of({"Spain beat England": at(0)}, threshold=0.9)
        assert meanings.told_among([" Spain  beat England"], ["Spain beat\nEngland"]) == {
            " Spain  beat England"
        }


class Embedder:
    """The platform's embedding door, standing in: one vector per text, calls counted."""

    def __init__(self, dimensions: int = 3) -> None:
        self.calls: list[list[str]] = []
        self.dimensions = dimensions

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), 1.0, 0.5][: self.dimensions] for text in texts]


def plain(read: dict[str, Vector]) -> dict[str, list[float]]:
    return {title: vector.tolist() for title, vector in read.items()}


def vectors(redis: FakeRedis, embed: Embedder) -> RedisHeadlineVectors:
    return RedisHeadlineVectors(redis, embed=embed, model="embedder-1", dimensions=3)


class TestRedisHeadlineVectors:
    async def test_a_headline_read_once_is_shared_by_every_listener(self) -> None:
        redis, embed = FakeRedis(), Embedder()
        first = await vectors(redis, embed).vectors(["Spain beat England"])
        again = await vectors(redis, embed).vectors(["Spain beat England"])
        assert plain(first) == plain(again) == {"Spain beat England": [18.0, 1.0, 0.5]}
        assert embed.calls == [["Spain beat England"]]
        # Kept as the provider's float32, made or read: a live session holds them all.
        assert first["Spain beat England"].dtype == again["Spain beat England"].dtype
        assert first["Spain beat England"].dtype == np.float32

    async def test_only_the_headlines_never_read_are_embedded_in_one_call(self) -> None:
        redis, embed = FakeRedis(), Embedder()
        await vectors(redis, embed).vectors(["a storm"])
        read = await vectors(redis, embed).vectors(["a storm", "a crash", "a vote"])
        assert set(read) == {"a storm", "a crash", "a vote"}
        assert embed.calls == [["a storm"], ["a crash", "a vote"]]

    async def test_a_vector_is_kept_as_long_as_its_story_may_air(self) -> None:
        redis = FakeRedis()
        await vectors(redis, Embedder()).vectors(["a storm"])
        [key] = redis.strings
        assert key.startswith("radio:headline:embedder-1:3:")
        assert redis.ttls[key] == NEWS_MAX_AGE_S

    async def test_another_model_or_size_never_reads_a_vector_it_did_not_make(self) -> None:
        redis, embed = FakeRedis(), Embedder()
        await vectors(redis, embed).vectors(["a storm"])
        other = RedisHeadlineVectors(redis, embed=embed, model="embedder-2", dimensions=3)
        await other.vectors(["a storm"])
        assert len(embed.calls) == 2

    @pytest.mark.parametrize(
        "stored",
        [
            "not base64 !",
            "AAAA",  # three bytes: no whole float
            base64.b64encode(struct.pack("<2f", 1.0, 2.0)).decode(),  # two floats of three
        ],
    )
    async def test_a_vector_that_cannot_be_read_is_made_again(self, stored: str) -> None:
        redis, embed = FakeRedis(), Embedder()
        store = vectors(redis, embed)
        await store.vectors(["a storm"])
        [key] = redis.strings
        redis.strings[key] = stored
        assert plain(await store.vectors(["a storm"])) == {"a storm": [7.0, 1.0, 0.5]}
        assert len(embed.calls) == 2

    async def test_an_answer_for_fewer_headlines_keeps_nothing(self) -> None:
        """Which vector is whose cannot be told: none is kept for the others to read."""

        class Short(Embedder):
            async def __call__(self, texts: list[str]) -> list[list[float]]:
                return (await super().__call__(texts))[:-1]

        redis = FakeRedis()
        with pytest.raises(ValueError):
            await vectors(redis, Short()).vectors(["a storm", "a crash"])
        assert redis.strings == {}

    async def test_vectors_of_another_size_keep_nothing(self) -> None:
        """Two spaces must never meet in one relation: the reading goes blind instead."""
        redis = FakeRedis()
        with pytest.raises(ValueError):
            await vectors(redis, Embedder(dimensions=2)).vectors(["a storm"])
        assert redis.strings == {}

    async def test_nothing_asked_calls_nothing(self) -> None:
        redis, embed = FakeRedis(), Embedder()
        assert await vectors(redis, embed).vectors([]) == {}
        assert embed.calls == [] and redis.ops["mget"] == 0
