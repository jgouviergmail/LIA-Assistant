"""A story the station told, read whole on the radio page, in the listener's language (ADR-324).

The programme says a story in a few sentences; the page offers the article itself
under the transcript. The article is the newsroom's — its full text when the
outlet allows it and the newsroom could read it, else the feed's summary, said
as such — and it is TRANSLATED when its feed's language is not the listener's:
on demand, when the listener opens it (owner decision 2026-09-26), by the
radio's own translator slot.

- A translation is made ONCE per story and language: kept in a shared cache for
  as long as the story may air (``NEWS_MAX_AGE_S``). A public article in a
  language is nobody's personal data, so the next listener who opens it pays
  nothing — and a reading that arrives while it is being made (a panel folded
  and reopened, a second listener, another worker) waits for it rather than
  paying for the same text twice (``shared_flight``, ADR-271).
- It is billed to the listener who opened it, under a run of its own (ADR-272):
  what it cost comes back with the article, and a reading from the cache costs
  nothing. The call is also an act of its own in the transparency register
  (``register.file_article``, ADR-324 decision 31); a reading from the cache
  called no model and files nothing.
- The text is the one the newsroom kept (``newsroom.fulltext``): an article it
  cut ends on its last whole sentence here, and the cut is stated — the rest
  is at the outlet. A translation that fails — a ceiling, a truncated answer,
  a provider error — shows the original, said as such: never nothing.

The core (what to show, what to translate, where to cut) is pure; the model, the
cache and the claim are ports, and :func:`radio_article` binds the real ones.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.config import settings
from src.core.i18n import get_language_name, normalize_language
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.core.prompt_store import read_prompt_file
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.chat.service import TrackingContext
from src.domains.radio.adapters import LedgerCostReader, bound_call
from src.domains.radio.budget import BudgetReader, listener_budget
from src.domains.radio.constants import RADIO_RUN_ID_PREFIX
from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.newsroom.fulltext import was_cut
from src.domains.radio.register import file_article
from src.domains.radio.repository import NewsStory, read_story
from src.domains.radio.schemas import RadioArticleResponse
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm.factory import LLMType
from src.infrastructure.observability.callbacks import TokenTrackingCallback
from src.infrastructure.utils.shared_flight import (
    CLAIM_PREFIX,
    CLAIM_TTL_SECONDS,
    run_shared_flight,
)

logger = structlog.get_logger(__name__)

TRANSLATOR_PROMPT: Final[str] = "radio_translator_prompt"
RADIO_TRANSLATOR_SLOT: Final[LLMType] = "radio_translator"

#: Where a sentence ends: a stop followed by a space, or a full-width stop.
_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"[.!?…](?=\s)|[。！？]")


class ArticleTranslation(BaseModel):
    """What the translator returns: the article in the listener's language."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="The headline, in the listener's language.")
    text: str = Field(
        description="The whole text, in the listener's language, one blank line between paragraphs."
    )


@dataclass(frozen=True, slots=True)
class Translated:
    """What one translation gave.

    Attributes:
        translation: The article translated; ``None`` when none could be made.
        cost_eur: What it cost the listener (``None`` when unknown).
        budget_reached: No model was asked: the listener's radio spent its
            rolling day's budget (ADR-324 decision 37).
    """

    translation: ArticleTranslation | None
    cost_eur: float | None
    budget_reached: bool = False


class Translator(Protocol):
    """Translates one article into a language (the radio's translator slot)."""

    async def translate(self, *, title: str, text: str, url: str, language: str) -> Translated:
        """The article in ``language``, and what that cost."""
        ...


class ArticleBooks(Protocol):
    """Files one translation the model was asked for in the transparency register — never raises."""

    async def __call__(
        self, *, user_id: UUID, run_id: str, started_at: datetime, translated: bool
    ) -> None:
        """File the call made under ``run_id``, and whether it gave a translation."""
        ...


class ArticleFlights(Protocol):
    """One translation per story and language at a time."""

    async def once(
        self,
        story_id: UUID,
        language: str,
        *,
        make: Callable[[], Awaitable[Translated]],
        made_elsewhere: Callable[[], Awaitable[Translated | None]],
    ) -> Translated:
        """What ``make()`` gave, or the translation another reading made meanwhile."""
        ...


class ArticleCache(Protocol):
    """The shared cache of translations, per story and language."""

    async def get(self, story_id: UUID, language: str) -> ArticleTranslation | None:
        """A translation already made, if any."""
        ...

    async def put(self, story_id: UUID, language: str, translation: ArticleTranslation) -> None:
        """Keep a translation for the next reader."""
        ...


def _paragraphs(text: str) -> str:
    """One blank line between two paragraphs — the newsroom files one per line."""
    return "\n\n".join(line.strip() for line in text.splitlines() if line.strip())


def _whole_head(text: str) -> str:
    """The longest head of a cut text that ends on a whole paragraph or sentence, else word."""
    ends = [text.rfind("\n")] + [match.end() for match in _SENTENCE_END.finditer(text)][-1:]
    at = max(ends)
    if at <= 0:
        at = text.rfind(" ")
    return text[:at].rstrip() if at > 0 else text


def article_text(story: NewsStory) -> tuple[str, bool, bool]:
    """The text the page shows: the article the newsroom kept, else the feed's summary.

    Args:
        story: The story.

    Returns:
        The text (one blank line between two paragraphs), whether it is the
        article rather than the summary, and whether the newsroom cut it — then
        ending on its last whole sentence, never inside a word.
    """
    if not (story.full_text and story.full_text.strip()):
        return _paragraphs(story.summary or ""), False, False
    if not was_cut(story.full_text):
        return _paragraphs(story.full_text), True, False
    return _paragraphs(_whole_head(story.full_text)), True, True


def needs_translation(story_language: str | None, listener_language: str) -> bool:
    """Whether the article must be translated: its language is another, or unknown."""
    if story_language is None:
        return True
    return normalize_language(story_language) != normalize_language(listener_language)


async def open_article(
    story: NewsStory,
    *,
    language: str,
    translator: Translator,
    cache: ArticleCache,
    flights: ArticleFlights,
) -> RadioArticleResponse:
    """The article as the page shows it — translated when it must be, once per language.

    Args:
        story: The story the listener opened.
        language: The listener's language.
        translator: The translator slot, bound to the listener.
        cache: The shared translations.
        flights: Makes one translation of a story and language at a time.

    Returns:
        The article; its original when no translation could be made (said so).
    """
    text, complete, cut = article_text(story)
    target = normalize_language(language)

    def answer(
        title: str,
        body: str,
        *,
        translated: bool,
        failed: bool = False,
        budget_reached: bool = False,
        cost_eur: float | None = 0.0,
    ) -> RadioArticleResponse:
        return RadioArticleResponse(
            id=story.id,
            outlet=story.outlet,
            url=story.url,
            published_at=story.published_at,
            title=title,
            text=body,
            complete=complete,
            cut=cut,
            translated=translated,
            source_language=story.language,
            translation_failed=failed,
            budget_reached=budget_reached,
            cost_eur=cost_eur,
        )

    if not text or not needs_translation(story.language, target):
        return answer(story.title, text, translated=False)
    kept = await cache.get(story.id, target)
    if kept is not None:
        return answer(kept.title, kept.text, translated=True)

    async def make() -> Translated:
        made = await translator.translate(
            title=story.title, text=text, url=story.url, language=target
        )
        if made.translation is not None and made.translation.text.strip():
            await cache.put(story.id, target, made.translation)
            logger.info("radio_article_translated", chars=len(text), cut=cut)
        return made

    async def made_elsewhere() -> Translated | None:
        found = await cache.get(story.id, target)
        return None if found is None else Translated(found, 0.0)

    try:
        made = await flights.once(story.id, target, make=make, made_elsewhere=made_elsewhere)
    except Exception as exc:  # noqa: BLE001 — a failed translation shows the original, said so
        logger.warning("radio_article_translation_failed", error_type=type(exc).__name__)
        return answer(story.title, text, translated=False, failed=True, cost_eur=None)
    if made.budget_reached:
        return answer(story.title, text, translated=False, budget_reached=True)
    translation = made.translation
    if translation is None or not translation.text.strip():
        return answer(story.title, text, translated=False, failed=True, cost_eur=made.cost_eur)
    return answer(translation.title, translation.text, translated=True, cost_eur=made.cost_eur)


# --- The real ports ---------------------------------------------------------------------


def render_translator_prompt(
    template: str, *, title: str, text: str, url: str, language: str
) -> str:
    """The translator's prompt: the task above the marker, the article below it, fenced."""
    return template.format(
        language_name=get_language_name(language),
        article=wrap_external_content(f"{title}\n\n{text}", source_url=url),
    )


class ModelTranslator:
    """The translator slot, bound to one listener: every call billed under its own run."""

    def __init__(
        self,
        user_id: UUID,
        *,
        cost_of: Callable[[str], Awaitable[float | None]],
        books: ArticleBooks,
        budget: BudgetReader,
    ) -> None:
        """Bind the translator.

        Args:
            user_id: The listener who opened the article (the ceilings' owner).
            cost_of: Reads what a run cost once its books are closed.
            books: Files each call in the transparency register.
            budget: Reads what the listener's radio spent over the rolling day.
        """
        self._user_id = user_id
        self._cost_of = cost_of
        self._books = books
        self._budget = budget

    async def translate(self, *, title: str, text: str, url: str, language: str) -> Translated:
        """The article translated, and what that cost the listener.

        A call the structured door refuses — a ceiling, a cut answer, a provider
        error — gives no translation, and what it spent is still said: the
        tracker files the spend on exit whatever raised. Every call, answered or
        not, is one act in the register, under the run it was billed to. Past the
        listener's radio budget no model is asked, so nothing is filed either.
        """
        if (await self._budget(self._user_id, now=datetime.now(UTC))).reached:
            logger.info("radio_article_translation_over_budget")
            return Translated(None, 0.0, budget_reached=True)
        run_id = f"{RADIO_RUN_ID_PREFIX}article_{uuid4().hex}"
        started_at = datetime.now(UTC)
        prompt = render_translator_prompt(
            read_prompt_file(TRANSLATOR_PROMPT), title=title, text=text, url=url, language=language
        )
        translation: ArticleTranslation | None = None
        try:
            async with TrackingContext(run_id, self._user_id, run_id, None) as tracker:
                call = bound_call(
                    RADIO_TRANSLATOR_SLOT,
                    user_id=self._user_id,
                    callbacks=[TokenTrackingCallback(tracker, run_id)],
                )
                translation = await call(single_call_messages(prompt), ArticleTranslation)
        except Exception as exc:  # noqa: BLE001 — a refused translation shows the original
            logger.warning("radio_article_translation_refused", error_type=type(exc).__name__)
        try:
            await self._books(
                user_id=self._user_id,
                run_id=run_id,
                started_at=started_at,
                translated=translation is not None and bool(translation.text.strip()),
            )
        except Exception as exc:  # noqa: BLE001 — observing never breaks the observed
            logger.warning("radio_article_unfiled", error_type=type(exc).__name__)
        return Translated(translation, await self._cost_of(run_id))


class SharedArticleFlights:
    """One translation per story and language across the workers (``shared_flight``).

    The claim outlives the longest translation — past it, a second one could
    start — and a reading waits as long as one may take: the translator slot's
    own timeout, which ends the holder's call first.
    """

    def __init__(self, bound_s: float) -> None:
        """Bind the flights to how long one translation may take.

        Args:
            bound_s: The translator slot's timeout, in seconds.
        """
        self._bound_s = bound_s

    async def once(
        self,
        story_id: UUID,
        language: str,
        *,
        make: Callable[[], Awaitable[Translated]],
        made_elsewhere: Callable[[], Awaitable[Translated | None]],
    ) -> Translated:
        """What ``make()`` gave, or the translation another reading published meanwhile."""
        flight = await run_shared_flight(
            f"{CLAIM_PREFIX}:radio_article:{story_id}:{language}",
            build=make,
            read_shared=made_elsewhere,
            wait_budget_s=self._bound_s,
            claim_ttl_s=math.ceil(self._bound_s) + CLAIM_TTL_SECONDS,
        )
        return flight.value


class RedisArticleCache:
    """The shared translations in Redis (family ``radio:article``, global)."""

    def __init__(self, redis: Any) -> None:
        """Bind the cache to its client."""
        self._redis = redis

    @staticmethod
    def _key(story_id: UUID, language: str) -> str:
        return f"radio:article:{story_id}:{language}"

    async def get(self, story_id: UUID, language: str) -> ArticleTranslation | None:
        """A translation already made, if any (an unreadable one is none)."""
        raw = await self._redis.get(self._key(story_id, language))
        if raw is None:
            return None
        try:
            return ArticleTranslation.model_validate(json.loads(raw))
        except ValueError, ValidationError:
            return None

    async def put(self, story_id: UUID, language: str, translation: ArticleTranslation) -> None:
        """Keep a translation for as long as its story may air."""
        await self._redis.set(
            self._key(story_id, language), translation.model_dump_json(), ex=NEWS_MAX_AGE_S
        )


async def radio_article(
    user_id: UUID, story_id: UUID, language: str
) -> RadioArticleResponse | None:
    """The article of a story the listener may read, in their language.

    Args:
        user_id: The listener.
        story_id: The story (a transcript source's ``article_id``).
        language: The listener's stored language.

    Returns:
        The article; ``None`` when the story is unknown or not theirs to read.
    """
    story = await read_story(user_id, story_id)
    if story is None:
        return None
    bound_s = get_llm_config_for_agent(settings, RADIO_TRANSLATOR_SLOT).timeout_seconds
    return await open_article(
        story,
        language=language,
        translator=ModelTranslator(
            user_id, cost_of=LedgerCostReader().cost_eur, books=file_article, budget=listener_budget
        ),
        cache=RedisArticleCache(await get_redis_cache()),
        flights=SharedArticleFlights(bound_s or 0.0),
    )


__all__ = [
    "RADIO_TRANSLATOR_SLOT",
    "TRANSLATOR_PROMPT",
    "ArticleBooks",
    "ArticleCache",
    "ArticleFlights",
    "ArticleTranslation",
    "ModelTranslator",
    "RedisArticleCache",
    "SharedArticleFlights",
    "Translated",
    "Translator",
    "article_text",
    "needs_translation",
    "open_article",
    "radio_article",
    "render_translator_prompt",
]
