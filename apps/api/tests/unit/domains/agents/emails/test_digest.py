"""One digest per message, computed once, cached — never invented (ADR-287).

« Résume mes non lus », « synthèse des newsletters de la semaine », a morning
routine: the assistant reasons over MANY messages, and doing that on N full
bodies is neither affordable nor good. A message never changes, so its digest
is produced once by a small model — gist, key points, actions, category,
importance — and served from the cache from then on. The rules pinned here:

- a cache hit costs no model call; a miss costs exactly one, and the result is
  written with a TTL (a value with no TTL is never written, ADR-271's lesson);
- two callers condensing the same message in flight share ONE call;
- a quota refusal skips the digest and KEEPS the body (the model can still
  read the message), and says ``skipped_quota`` — never ``failed``;
- a model failure or a truncated output is a refusal: the body stays, nothing
  is invented, nothing is cached;
- the key carries the language and the schema version, so a prompt change or
  a language switch never serves a stale digest;
- the closed vocabularies are enforced in code, never by a schema bound that
  would fail the whole output (ADR-275 pointing at Pydantic constraints).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.constants import EMAIL_DIGEST_SCHEMA_VERSION, REDIS_KEY_EMAIL_DIGEST_PREFIX
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.reasoning_intent import ReasoningIntent
from src.core.reasoning_profiles import ReasoningProfile
from src.domains.agents.display.llm_serializer import payload_to_text
from src.domains.agents.emails.digest import (
    DIGEST_FIELDS,
    EmailDigest,
    EmailDigestService,
    digest_cache_key,
)
from src.infrastructure.cache.key_families import family_of
from src.infrastructure.llm.structured_output_errors import StructuredOutputError

pytestmark = [pytest.mark.unit]

MODULE = "src.domains.agents.emails.digest"
USER = "35e9301b-86e1-4665-b47a-23363fff33aa"


def _email(index: int, provider: str = "google") -> dict[str, Any]:
    return {
        "id": f"m{index}",
        "subject": f"Subject {index}",
        "from": f"sender{index}@example.com",
        "date_formatted": "mardi 15 septembre 2026 à 21:11",
        "body": "\n\n".join(f"Paragraph {index}.{p} " + "word " * 40 for p in range(3)),
        "_provider": provider,
    }


def _digest(index: int = 1) -> EmailDigest:
    return EmailDigest(
        gist=f"Gist {index}",
        key_points=[f"Point {index}a", f"Point {index}b"],
        actions=[f"Reply to sender {index}"],
        category="newsletter",
        importance="low",
    )


class _FakeRedis:
    def __init__(self, store: dict[str, str] | None = None, *, broken: bool = False) -> None:
        self.store = store or {}
        self.broken = broken
        self.set = AsyncMock(side_effect=self._set)
        self.reads = 0

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.reads += 1
        if self.broken:
            raise ConnectionError("redis is down")
        return [self.store.get(key) for key in keys]

    async def _set(self, key: str, value: str, ex: int | None = None) -> None:
        assert ex, "a digest is never written without a TTL"
        if self.broken:
            raise ConnectionError("redis is down")
        self.store[key] = value


@pytest.fixture
def redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def doors(redis: _FakeRedis):  # type: ignore[no-untyped-def]
    """The four doors the service reaches, all closed for the test."""
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.get_structured_output", AsyncMock(return_value=_digest())) as structured,
        patch(f"{MODULE}.get_llm"),
        patch(f"{MODULE}.spend_blocked", AsyncMock(return_value=False)) as blocked,
    ):
        yield {"structured": structured, "blocked": blocked}


class TestTheCacheKey:
    def test_carries_user_provider_message_language_and_schema_version(self) -> None:
        key = digest_cache_key(USER, "google", "m1", "fr-FR")
        assert key.startswith(REDIS_KEY_EMAIL_DIGEST_PREFIX)
        assert key.endswith(f":m1:fr:{EMAIL_DIGEST_SCHEMA_VERSION}")
        assert digest_cache_key(USER, "google", "m1", "de") != key

    def test_the_family_is_declared_as_a_user_cache(self) -> None:
        """ADR-260: a key named by a user id declares its scope; a reset purges it."""
        assert family_of(digest_cache_key(USER, "google", "m1", "fr")) == "email:digest"


class TestHitAndMiss:
    async def test_a_hit_costs_no_model_call(self, redis: _FakeRedis, doors: dict) -> None:
        email = _email(1)
        redis.store[digest_cache_key(USER, "google", "m1", "fr")] = json.dumps(
            _digest(1).model_dump()
        )

        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")

        doors["structured"].assert_not_awaited()
        assert email["digest_status"] == "cached"
        assert email["gist"] == "Gist 1"
        assert email["key_points"] == ["Point 1a", "Point 1b"]

    async def test_a_miss_costs_one_call_and_is_written_with_a_ttl(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        email = _email(1)

        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")

        doors["structured"].assert_awaited_once()
        assert doors["structured"].await_args.kwargs["user_id"] == USER
        assert email["digest_status"] == "computed"
        assert email["category"] == "newsletter"
        redis.set.assert_awaited_once()
        assert redis.set.await_args.kwargs["ex"] > 0
        cached = json.loads(redis.store[digest_cache_key(USER, "google", "m1", "fr")])
        assert cached["gist"] == "Gist 1"

    async def test_an_unreadable_cache_entry_is_recomputed_not_served(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        """A corrupted value is a miss, never a failure and never a digest."""
        email = _email(1)
        redis.store[digest_cache_key(USER, "google", "m1", "fr")] = "{not json"

        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")

        doors["structured"].assert_awaited_once()
        assert email["digest_status"] == "computed"
        assert email["gist"] == "Gist 1"

    async def test_the_same_message_twice_in_flight_shares_one_call(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        twins = [_email(1), _email(1)]

        await EmailDigestService().digest_many(user_id=USER, emails=twins, language="fr")

        assert doors["structured"].await_count == 1
        assert [e["digest_status"] for e in twins] == ["computed", "computed"]

    async def test_a_quota_refusal_skips_and_keeps_the_body(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        doors["blocked"].return_value = True
        email = _email(1)

        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")

        doors["structured"].assert_not_awaited()
        assert email["digest_status"] == "skipped_quota"
        assert "body" in email and "gist" not in email
        redis.set.assert_not_awaited()

    async def test_a_model_failure_is_a_refusal_never_an_invention(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        doors["structured"].side_effect = StructuredOutputError(
            "cut", provider="x", schema_name="EmailDigest"
        )
        email = _email(1)

        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")

        assert email["digest_status"] == "failed"
        assert "body" in email and "gist" not in email
        redis.set.assert_not_awaited()

    async def test_the_switch_off_skips_every_message(self, redis: _FakeRedis, doors: dict) -> None:
        email = _email(1)
        with patch(f"{MODULE}.settings.emails_digest_enabled", False):
            await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")
        doors["structured"].assert_not_awaited()
        assert email["digest_status"] == "skipped_disabled"

    async def test_a_message_without_a_body_is_not_condensed(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        email = {**_email(1), "body": ""}
        await EmailDigestService().digest_many(user_id=USER, emails=[email], language="fr")
        doors["structured"].assert_not_awaited()
        assert email["digest_status"] == "skipped_empty"


class TestDegradedPaths:
    async def test_the_cache_is_read_in_one_round_trip(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        """N messages, one ``mget`` — never N ``get`` round trips."""
        await EmailDigestService().digest_many(
            user_id=USER, emails=[_email(i) for i in range(1, 6)], language="fr"
        )
        assert redis.reads == 1
        assert doors["structured"].await_count == 5

    async def test_a_quota_refusal_mid_batch_is_skipped_never_failed(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        """The batch gate passed, then the ceiling closed between two calls (a
        refusal is not a generation failure — ADR-272)."""
        from src.core.exceptions_domains import UsageLimitExceededError

        doors["structured"].side_effect = [
            _digest(1),
            UsageLimitExceededError(limit_name="cycle_tokens"),
        ]
        emails = [_email(1), _email(2)]

        await EmailDigestService().digest_many(user_id=USER, emails=emails, language="fr")

        assert [e["digest_status"] for e in emails] == ["computed", "skipped_quota"]
        assert emails[1]["body"], "the body stays where no digest landed"

    async def test_redis_down_degrades_to_compute_without_cache(self, doors: dict) -> None:
        """No cache is a slower path, never a failed tool: every message is
        condensed, nothing is written, and the status says so."""
        broken = _FakeRedis(broken=True)
        with patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=broken)):
            emails = [_email(1), _email(2)]
            await EmailDigestService().digest_many(user_id=USER, emails=emails, language="fr")

        assert [e["digest_status"] for e in emails] == ["computed", "computed"]
        assert doors["structured"].await_count == 2


class TestTheSpendIsAccounted:
    """The digest runs inside a TOOL, and a tool's model call is accounted only
    through the RunnableConfig the runtime carries (its TokenTrackingCallback):
    ``get_structured_output`` builds a fresh config when handed none. Measured
    on Docker dev 2026-09-15: six digests, ``callbacks_before_filter: 0``, no
    ``token_usage_recorded`` row — a euro spent that no ledger saw (ADR-272)."""

    async def test_the_turn_config_reaches_the_structured_door(
        self, redis: _FakeRedis, doors: dict
    ) -> None:
        config = {"callbacks": ["turn-tracker"], "metadata": {"run_id": "r1"}}

        await EmailDigestService().digest_many(
            user_id=USER, emails=[_email(1)], language="fr", config=config
        )

        assert doors["structured"].await_args.kwargs["config"] is config

    async def test_without_a_turn_the_door_is_told_so(self, redis: _FakeRedis, doors: dict) -> None:
        await EmailDigestService().digest_many(user_id=USER, emails=[_email(1)], language="fr")

        assert doors["structured"].await_args.kwargs["config"] is None


class TestTheOutputCapIsTheSlots:
    """The digest has a slot of its own: its ``max_tokens`` — seeded from
    ``EMAIL_DIGEST_MAX_OUTPUT_TOKENS`` and edited by the admin — is the cap.
    The code passes no cap of its own, so what an administrator types is what
    the model gets; a ``.env`` key here would be a third authority."""

    async def test_the_call_keeps_the_slots_budget(self, redis: _FakeRedis, doors: dict) -> None:
        slot = get_llm_config_for_agent(settings, "email_digest").model_copy(
            update={"max_tokens": 4_321}
        )
        with (
            patch(f"{MODULE}.get_llm_config_for_agent", return_value=slot),
            patch("src.core.llm_config_helper.get_llm_config_for_agent", return_value=slot),
            patch(
                "src.core.llm_config_helper.resolve_reasoning_profile",
                return_value=ReasoningProfile(
                    "deepseek_toggle", ("none", "low", "high", "max"), False, None, True, True
                ),
            ),
            patch(f"{MODULE}.get_llm") as get_llm,
        ):
            await EmailDigestService().digest_many(user_id=USER, emails=[_email(1)], language="fr")

        override = get_llm.call_args.kwargs["config_override"]
        assert override.max_tokens == 4_321
        assert override.reasoning_effort == ReasoningIntent(level="none")


class TestTheVocabularyIsEnforcedInCode:
    def test_unknown_category_and_importance_fall_back(self) -> None:
        digest = EmailDigest(
            gist="g", key_points=[], actions=[], category="Spam!", importance="URGENT"
        )
        assert digest.category == "other"
        assert digest.importance == "normal"

    def test_sizes_are_trimmed_never_refused(self) -> None:
        digest = EmailDigest(
            gist="x" * 1_000,
            key_points=[f"p{i}" for i in range(9)],
            actions=[f"a{i}" for i in range(9)],
            category="work",
            importance="high",
        )
        assert len(digest.gist) == 300
        assert len(digest.key_points) == 5
        assert len(digest.actions) == 3


class TestTheResponseNodeReadsIt:
    def test_the_serializer_shows_gist_key_points_and_actions(self) -> None:
        """``payload_to_text`` skips a short field named ``summary`` (it treats it
        as a display name): the digest fields are named so that it shows them."""
        email = {**_email(1)}
        email.pop("body")
        email.update(_digest(1).model_dump())
        text = payload_to_text(email)
        assert "Gist 1" in text
        assert "key points: Point 1a, Point 1b" in text
        assert "actions: Reply to sender 1" in text
        assert set(DIGEST_FIELDS) <= set(_digest(1).model_dump())
