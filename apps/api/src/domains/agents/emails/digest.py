"""One digest per e-mail, computed once, cached — never invented (ADR-287).

« Résume mes non lus », « synthèse des newsletters de la semaine », a morning
routine: the assistant reasons over MANY messages, and doing that on N full
bodies is neither affordable nor good. A message never changes, so its digest
— gist, key points, actions, category, importance — is produced once by a
small model (slot ``email_digest``, a short schema-bound answer with no
reasoning, ADR-285) and served from Redis from then on.

What this module promises, and what the tests pin:

- a cache hit costs no model call; a miss costs exactly one, written with a
  TTL (a value with no TTL is never written — ADR-271's lesson);
- two callers condensing the same message in flight share ONE call
  (:func:`run_single_flight`);
- a ceiling refusal (:func:`spend_blocked`, both ceilings — ADR-272) skips
  the digest and KEEPS the body, and reads ``skipped_quota`` — a quota
  refusal is not a generation failure;
- a model failure or a truncated output is a REFUSAL (ADR-275): the body
  stays, nothing is invented, nothing is cached;
- the key carries the language and the schema version, so a prompt change
  (a version bump) or a language switch never serves a stale digest;
- the closed vocabularies are enforced HERE, never by a schema bound that
  would fail the whole output (a ``max_length`` on a list is a refusal, not
  a trim).

The spend is the turn's (``LLM_SPEND_ROADS``: TURN) — the tool runs inside a
turn whose ambient tracker records it, and the structured door is handed the
account so both ceilings see it.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, field_validator

from src.core.config import settings
from src.core.constants import (
    EMAIL_DIGEST_GIST_MAX_CHARS,
    EMAIL_DIGEST_MAX_ACTIONS,
    EMAIL_DIGEST_MAX_KEY_POINTS,
    EMAIL_DIGEST_SCHEMA_VERSION,
    REDIS_KEY_EMAIL_DIGEST_PREFIX,
)
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.field_names import FIELD_BODY
from src.core.i18n import get_language_name, normalize_language
from src.core.llm_config_helper import get_llm_config_for_agent, short_answer_config
from src.domains.agents.emails.detail_levels import paginate_body
from src.domains.agents.prompts import load_prompt
from src.domains.usage_limits.enforcement import spend_blocked
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.metrics_extractions import email_digest_cache_total
from src.infrastructure.utils.single_flight import run_single_flight

logger = structlog.get_logger(__name__)

LLM_TYPE: Final = "email_digest"
DIGEST_STATUS_FIELD = "digest_status"
CATEGORIES: frozenset[str] = frozenset(
    {"personal", "work", "newsletter", "notification", "transactional", "other"}
)
IMPORTANCES: frozenset[str] = frozenset({"high", "normal", "low"})


class EmailDigest(BaseModel):
    """What the model says about one message. Sizes are TRIMMED, never refused."""

    gist: str = Field(
        default="", description="One or two sentences: what it is about, what it asks."
    )
    key_points: list[str] = Field(default_factory=list, description="Facts, figures, dates, names.")
    actions: list[str] = Field(
        default_factory=list, description="What the reader is expected to do."
    )
    category: str = Field(
        default="other",
        description="personal | work | newsletter | notification | transactional | other",
    )
    importance: str = Field(default="normal", description="high | normal | low")

    @field_validator("gist", mode="after")
    @classmethod
    def _trim_gist(cls, value: str) -> str:
        return value.strip()[:EMAIL_DIGEST_GIST_MAX_CHARS]

    @field_validator("key_points", mode="after")
    @classmethod
    def _trim_key_points(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()][
            :EMAIL_DIGEST_MAX_KEY_POINTS
        ]

    @field_validator("actions", mode="after")
    @classmethod
    def _trim_actions(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()][:EMAIL_DIGEST_MAX_ACTIONS]

    @field_validator("category", mode="after")
    @classmethod
    def _closed_category(cls, value: str) -> str:
        normalised = value.strip().lower()
        return normalised if normalised in CATEGORIES else "other"

    @field_validator("importance", mode="after")
    @classmethod
    def _closed_importance(cls, value: str) -> str:
        normalised = value.strip().lower()
        return normalised if normalised in IMPORTANCES else "normal"


#: The keys a digest flattens INTO the message dict. Named so that the response
#: node's serializer shows them: ``payload_to_text`` skips a short field named
#: ``summary`` (it reads it as a display name), it never skips ``gist``.
DIGEST_FIELDS: tuple[str, ...] = tuple(EmailDigest.model_fields)


def digest_cache_key(user_id: str, provider: str, message_id: str, language: str) -> str:
    """The Redis key of one digest: account, provider, message, language, schema version.

    Family ``email:digest`` (``USER_CACHE``, ADR-260): purged by a conversation
    reset like every per-user cache, never by pattern.
    """
    lang = normalize_language(language)
    return (
        f"{REDIS_KEY_EMAIL_DIGEST_PREFIX}{user_id}:{provider}:{message_id}:{lang}:"
        f"{EMAIL_DIGEST_SCHEMA_VERSION}"
    )


def _stamp(email: dict[str, Any], status: str, digest: EmailDigest | None = None) -> None:
    email[DIGEST_STATUS_FIELD] = status
    if digest is not None:
        email.update(digest.model_dump())
    email_digest_cache_total.labels(result=status).inc()


async def _open_cache() -> Any | None:
    """The Redis client, or ``None`` when the cache cannot be reached."""
    try:
        return await get_redis_cache()
    except Exception as exc:
        logger.warning("email_digest_cache_unavailable", error_type=type(exc).__name__)
        return None


async def _read_many(redis: Any | None, keys: list[str]) -> list[str | None]:
    """One round trip for every key; a failed read is a miss on every key."""
    if redis is None or not keys:
        return [None] * len(keys)
    try:
        values: list[str | None] = await redis.mget(keys)
    except Exception as exc:
        logger.warning("email_digest_cache_read_failed", error_type=type(exc).__name__)
        return [None] * len(keys)
    return values


class EmailDigestService:
    """Condense messages IN PLACE, reading the cache before any model call."""

    async def digest_many(
        self,
        *,
        user_id: str,
        emails: list[dict[str, Any]],
        language: str,
        config: RunnableConfig | None = None,
    ) -> None:
        """Flatten a digest into each message dict and stamp ``digest_status``.

        Statuses: ``cached`` | ``computed`` | ``failed`` | ``skipped_quota`` |
        ``skipped_disabled`` | ``skipped_empty``. A message without a digest
        keeps its body — the level reads the status to decide what to shed.

        Args:
            user_id: The account, for the cache key and the ceilings.
            emails: The messages, as the client normalised them (mutated).
            language: The user's language or locale; the digest is written in it.
            config: The turn's RunnableConfig — it carries the token-tracking
                callback, and a model call handed no config is a euro no ledger
                sees (measured on Docker dev 2026-09-15: six digests,
                ``callbacks_before_filter: 0``, no ``token_usage_recorded`` row).
        """
        if not emails:
            return
        if not settings.emails_digest_enabled:
            for email in emails:
                _stamp(email, "skipped_disabled")
            return

        candidates: list[tuple[dict[str, Any], str]] = []
        for email in emails:
            if not str(email.get(FIELD_BODY) or "").strip():
                _stamp(email, "skipped_empty")
                continue
            key = digest_cache_key(
                user_id, str(email.get("_provider") or "unknown"), str(email.get("id")), language
            )
            candidates.append((email, key))
        if not candidates:
            return

        # The cache is an accelerator, never a gate: unreachable, every message
        # is condensed and nothing is written — a slower turn, not a failed one.
        redis = await _open_cache()
        misses: list[tuple[dict[str, Any], str]] = []
        for (email, key), cached in zip(
            candidates, await _read_many(redis, [key for _, key in candidates]), strict=True
        ):
            if cached:
                try:
                    _stamp(email, "cached", EmailDigest.model_validate_json(cached))
                    continue
                except ValueError:
                    logger.debug("email_digest_cache_unreadable", key_suffix=key[-24:])
            misses.append((email, key))

        if not misses:
            return
        if await spend_blocked(user_id):
            for email, _key in misses:
                _stamp(email, "skipped_quota")
            return

        semaphore = asyncio.Semaphore(settings.emails_digest_concurrency)

        async def _one(email: dict[str, Any], key: str) -> None:
            async with semaphore:
                try:
                    flight = await run_single_flight(
                        key,
                        lambda: self._compute_and_cache(
                            email, key, language, user_id, redis, config
                        ),
                    )
                except UsageLimitExceededError:
                    # The ceiling closed between the batch gate and this call:
                    # a refusal is not a generation failure (ADR-272).
                    logger.info("email_digest_skipped_quota", message_id=str(email.get("id")))
                    _stamp(email, "skipped_quota")
                    return
                except Exception as exc:
                    # A refusal, never an invention: the body stays (ADR-275).
                    logger.warning(
                        "email_digest_failed",
                        error_type=type(exc).__name__,
                        message_id=str(email.get("id")),
                    )
                    _stamp(email, "failed")
                    return
            _stamp(email, "computed", flight.value)

        await asyncio.gather(*(_one(email, key) for email, key in misses))
        logger.info(
            "email_digest_batch",
            total=len(emails),
            computed=sum(1 for e in emails if e.get(DIGEST_STATUS_FIELD) == "computed"),
            cached=sum(1 for e in emails if e.get(DIGEST_STATUS_FIELD) == "cached"),
            failed=sum(1 for e in emails if e.get(DIGEST_STATUS_FIELD) == "failed"),
        )

    async def _compute_and_cache(
        self,
        email: dict[str, Any],
        key: str,
        language: str,
        user_id: str,
        redis: Any,
        config: RunnableConfig | None,
    ) -> EmailDigest:
        digest = await self._compute(email, language, user_id, config)
        if redis is None:
            return digest
        try:
            # ``ex=``: a digest with no TTL is never written (ADR-271).
            await redis.set(
                key, digest.model_dump_json(), ex=settings.emails_digest_cache_ttl_seconds
            )
        except Exception as exc:
            # The digest is served this turn either way; the next turn pays again.
            logger.warning("email_digest_cache_write_failed", error_type=type(exc).__name__)
        return digest

    async def _compute(
        self, email: dict[str, Any], language: str, user_id: str, config: RunnableConfig | None
    ) -> EmailDigest:
        """One short structured call. The body is cut at a paragraph under the
        input budget; when it continues, the model is told so."""
        body_text, parts = paginate_body(
            str(email.get(FIELD_BODY) or ""),
            part=1,
            part_tokens=settings.emails_digest_input_max_tokens,
        )
        if parts > 1:
            body_text = body_text.rsplit("\n[continued:", 1)[0] + "\n[the message continues]"
        template = load_prompt("email_digest_prompt")
        prompt = template.format(
            language_name=get_language_name(language),
            subject=str(email.get("subject") or ""),
            sender=str(email.get("from") or ""),
            date=str(email.get("date_formatted") or email.get("date") or ""),
            body=body_text,
        )
        # No reasoning, and the SLOT's own output cap: the administrator edits
        # it on the slot (ADR-244); the constant only seeds its default.
        llm = get_llm(LLM_TYPE, config_override=short_answer_config(LLM_TYPE))
        provider = get_llm_config_for_agent(settings, LLM_TYPE).provider
        return await get_structured_output(
            llm,
            [HumanMessage(content=prompt)],
            EmailDigest,
            provider,
            node_name=LLM_TYPE,
            user_id=user_id,
            config=config,
        )


__all__ = [
    "DIGEST_FIELDS",
    "DIGEST_STATUS_FIELD",
    "EmailDigest",
    "EmailDigestService",
    "digest_cache_key",
]
