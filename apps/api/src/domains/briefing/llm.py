"""Briefing LLM helpers — greeting + synthesis.

One LLM slot ("briefing" in LLM_TYPES_REGISTRY), two distinct versioned prompts.
Token usage is reported via ``track_proactive_tokens`` so it surfaces in the
existing ``message_token_summary`` + ``user_statistics`` analytics — no parallel
billing path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog
from langchain_core.messages import HumanMessage

from src.core.config import settings as app_settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.auth.models import User
from src.domains.briefing.constants import (
    BRIEFING_GREETING_PROMPT_NAME,
    BRIEFING_GREETING_TARGET_PREFIX,
    BRIEFING_LLM_TYPE,
    BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA,
    BRIEFING_SYNTHESIS_PROMPT_NAME,
    BRIEFING_SYNTHESIS_TARGET_PREFIX,
    BRIEFING_TASK_TYPE,
    TIME_OF_DAY_AFTERNOON,
    TIME_OF_DAY_EVENING,
    TIME_OF_DAY_MORNING,
    TIME_OF_DAY_NIGHT,
)
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus, LLMUsage
from src.domains.personalities.service import PersonalityService
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.observability.metrics_briefing import (
    briefing_llm_invocations_total,
)
from src.infrastructure.proactive.tracking import track_proactive_tokens

logger = structlog.get_logger(__name__)


# =============================================================================
# Public entry points
# =============================================================================


async def generate_greeting(
    *,
    user: User,
    user_tz: ZoneInfo,
    cards: CardsBundle,
    language: str,
) -> tuple[str, LLMUsage | None]:
    """Generate the top-of-page greeting (single sentence, ~20 words).

    Errors are non-fatal: a fallback greeting is returned so the dashboard
    always renders. The LLM call is tracked via ``track_proactive_tokens``.

    Returns:
        Tuple of (greeting_text, usage). ``usage`` is None when the fallback
        path is taken (no LLM call was made).
    """
    try:
        prompt_text = load_prompt(
            BRIEFING_GREETING_PROMPT_NAME,
            version=app_settings.briefing_greeting_prompt_version,
        )
        rendered = prompt_text.format(
            user_name=_resolve_display_name(user),
            time_of_day=_compute_time_of_day(user_tz),
            day_of_week=datetime.now(user_tz).strftime("%A"),
            language=language,
            personality_brief=await _resolve_personality(user.id),
            active_sections=_summarize_cards_for_llm(cards, verbose=False),
        )
        text, usage = await _invoke_and_track(
            rendered=rendered,
            user=user,
            target_prefix=BRIEFING_GREETING_TARGET_PREFIX,
            kind="greeting",
        )
        if not text:
            return _fallback_greeting(user, user_tz, language), None
        return text, usage
    except Exception as exc:
        logger.warning(
            "briefing_greeting_failed",
            user_id=str(user.id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        briefing_llm_invocations_total.labels(kind="greeting", outcome="error").inc()
        return _fallback_greeting(user, user_tz, language), None


async def generate_synthesis(
    *,
    user: User,
    user_tz: ZoneInfo,
    cards: CardsBundle,
    language: str,
) -> tuple[str | None, LLMUsage | None]:
    """Generate a 2-3 sentence synthesis. Returns (None, None) when too few cards have data.

    The minimum threshold (``BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA``) avoids
    forcing the LLM to write meaningful content from a near-empty dashboard.

    Returns:
        Tuple of (synthesis_text, usage). Both are None when synthesis is
        skipped or on failure.
    """
    cards_with_data = sum(1 for c in _iter_cards(cards) if c.status == CardStatus.OK)
    if cards_with_data < BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA:
        briefing_llm_invocations_total.labels(kind="synthesis", outcome="skipped").inc()
        return None, None

    try:
        prompt_text = load_prompt(
            BRIEFING_SYNTHESIS_PROMPT_NAME,
            version=app_settings.briefing_synthesis_prompt_version,
        )
        rendered = prompt_text.format(
            user_name=_resolve_display_name(user),
            time_of_day=_compute_time_of_day(user_tz),
            day_of_week=datetime.now(user_tz).strftime("%A"),
            language=language,
            personality_brief=await _resolve_personality(user.id),
            active_sections=_summarize_cards_for_llm(cards, verbose=True),
        )
        text, usage = await _invoke_and_track(
            rendered=rendered,
            user=user,
            target_prefix=BRIEFING_SYNTHESIS_TARGET_PREFIX,
            kind="synthesis",
        )
        if not text:
            return None, None
        return text, usage
    except Exception as exc:
        logger.warning(
            "briefing_synthesis_failed",
            user_id=str(user.id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        briefing_llm_invocations_total.labels(kind="synthesis", outcome="error").inc()
        return None, None


# =============================================================================
# Internals
# =============================================================================


async def _invoke_and_track(
    *,
    rendered: str,
    user: User,
    target_prefix: str,
    kind: str,
) -> tuple[str, LLMUsage | None]:
    """Invoke the briefing LLM and persist token usage.

    Args:
        rendered: Fully rendered prompt to send to the LLM.
        user: The authenticated user — used for token tracking attribution.
        target_prefix: Prefix injected into the analytics ``target_id`` so the
            run_id remains tagged with the call kind (greeting vs synthesis).
        kind: Short label (e.g. ``"greeting"``, ``"synthesis"``) used for
            metrics and structured logs.

    Returns:
        Tuple of (trimmed_text, usage). ``usage`` carries the token counts and
        EUR cost computed via the in-memory pricing cache; it is None only when
        no usage metadata was reported by the provider.

    Raises:
        Exception: Network / provider failures from ``llm.ainvoke`` propagate
            to the caller, which wraps them in a non-fatal try/except.
    """
    llm = get_llm(BRIEFING_LLM_TYPE)
    model_name = get_llm_config_for_agent(app_settings, BRIEFING_LLM_TYPE).model

    response = await llm.ainvoke([HumanMessage(content=rendered)])
    # LangChain may return content as either str or list[str | dict]; we only
    # care about plain text for the greeting / synthesis.
    raw_content = response.content
    if isinstance(raw_content, list):
        text = "".join(part for part in raw_content if isinstance(part, str)).strip()
    else:
        text = (raw_content or "").strip()

    # Token usage extraction. LangChain v1 surfaces .usage_metadata as a
    # standard dict on the AIMessage; defensive .get() to tolerate provider
    # variants that omit cache fields. OpenAI's input_tokens already includes
    # cached tokens — subtract to expose the "billable non-cached" count
    # consistently with the rest of the tracking pipeline.
    raw_usage = getattr(response, "usage_metadata", None) or {}
    raw_input = int(raw_usage.get("input_tokens", 0) or 0)
    tokens_out = int(raw_usage.get("output_tokens", 0) or 0)
    tokens_cache = int(
        raw_usage.get("cache_read_input_tokens", 0)
        or raw_usage.get("input_token_details", {}).get("cache_read", 0)
        or 0
    )
    tokens_in = max(raw_input - tokens_cache, 0)

    # EUR cost via the sync in-memory pricing cache (already populated at startup).
    cost_eur = 0.0
    try:
        _, cost_eur = get_cached_cost_usd_eur(
            model=model_name,
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            cached_tokens=tokens_cache,
        )
    except Exception as exc:
        logger.debug(
            "briefing_cost_estimation_failed",
            kind=kind,
            model=model_name,
            error=str(exc),
        )

    # Deterministic-ish target_id for analytics dedup (truncate to keep run_id stable).
    text_signature = hashlib.md5((text[:60] or uuid4().hex).encode("utf-8")).hexdigest()[:8]
    target_id = f"{target_prefix}_{text_signature}"

    try:
        await track_proactive_tokens(
            user_id=user.id,
            task_type=BRIEFING_TASK_TYPE,
            target_id=target_id,
            conversation_id=None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            model_name=model_name,
        )
    except Exception as exc:
        logger.warning(
            "briefing_token_tracking_failed",
            user_id=str(user.id),
            kind=kind,
            error=str(exc),
        )

    briefing_llm_invocations_total.labels(kind=kind, outcome="success").inc()

    usage: LLMUsage | None = None
    if raw_usage:
        usage = LLMUsage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            cost_eur=cost_eur,
            model_name=model_name,
        )
    return text, usage


def _resolve_display_name(user: User) -> str:
    """First name fallback chain: full_name → email local part → 'there'."""
    if user.full_name:
        # If full_name has multiple words, take the first as the friendly first name.
        first = user.full_name.strip().split()[0] if user.full_name.strip() else None
        if first:
            return first
    if user.email:
        return user.email.split("@", 1)[0]
    return "there"


def _compute_time_of_day(user_tz: ZoneInfo) -> str:
    """Bucket the user's local hour into a coarse time-of-day label.

    Aligned with the labels referenced in briefing_*_prompt.txt.
    """
    hour = datetime.now(user_tz).hour
    if hour < 5:
        return TIME_OF_DAY_NIGHT
    if hour < 12:
        return TIME_OF_DAY_MORNING
    if hour < 18:
        return TIME_OF_DAY_AFTERNOON
    if hour < 22:
        return TIME_OF_DAY_EVENING
    return TIME_OF_DAY_NIGHT


async def _resolve_personality(user_id: UUID) -> str:
    """Best-effort fetch of the user's personality instruction. Empty string on failure.

    Acquires its own DB session via ``get_db_context()`` to avoid sharing
    with concurrent fetchers (SQLAlchemy AsyncSession is not safe for
    concurrent operations).
    """
    try:
        async with get_db_context() as db:
            service = PersonalityService(db)
            prompt = await service.get_prompt_instruction_for_user(user_id)
            return prompt or ""
    except Exception as exc:
        logger.warning(
            "briefing_personality_resolution_failed",
            user_id=str(user_id),
            error=str(exc),
        )
        return ""


def _iter_cards(cards: CardsBundle) -> Iterator[CardSection]:
    yield cards.weather
    yield cards.agenda
    yield cards.mails
    yield cards.birthdays
    yield cards.reminders
    yield cards.health


def _summarize_cards_for_llm(cards: CardsBundle, *, verbose: bool) -> str:
    """Compact JSON summary of the cards data for prompt injection.

    Verbose=False (greeting): minimal hints (counts, headline weather).
    Verbose=True (synthesis): includes specific items (event titles, mail subjects).
    """
    summary: dict[str, object] = {}

    if cards.weather.status == CardStatus.OK and cards.weather.data is not None:
        w = cards.weather.data
        summary["weather"] = {
            "temp_c": getattr(w, "temperature_c", None),
            "condition": getattr(w, "condition_code", None),
            "city": getattr(w, "location_city", None),
            "forecast_alert": getattr(w, "forecast_alert", None),
        }

    if cards.agenda.status == CardStatus.OK and cards.agenda.data is not None:
        events = getattr(cards.agenda.data, "events", []) or []
        if verbose:
            summary["agenda"] = [
                {"title": e.title, "start": e.start_local, "loc": e.location} for e in events[:3]
            ]
        else:
            summary["agenda_count"] = len(events)

    if cards.mails.status == CardStatus.OK and cards.mails.data is not None:
        items = getattr(cards.mails.data, "items", []) or []
        total = getattr(cards.mails.data, "total_unread_today", 0)
        summary["mails"] = (
            {
                "unread_today": total,
                "items": [
                    {
                        "from": (m.sender_name or m.sender_email or "(unknown)"),
                        "subject": m.subject,
                    }
                    for m in items[:3]
                ],
            }
            if verbose
            else {"unread_today": total}
        )

    if cards.birthdays.status == CardStatus.OK and cards.birthdays.data is not None:
        items = getattr(cards.birthdays.data, "items", []) or []
        summary["birthdays"] = [
            {"name": b.contact_name, "days_until": b.days_until} for b in items[:3]
        ]

    if cards.reminders.status == CardStatus.OK and cards.reminders.data is not None:
        items = getattr(cards.reminders.data, "items", []) or []
        if verbose:
            summary["reminders"] = [
                {"content": r.content, "trigger": r.trigger_at_local} for r in items[:3]
            ]
        else:
            summary["reminders_count"] = len(items)

    if cards.health.status == CardStatus.OK and cards.health.data is not None:
        items = getattr(cards.health.data, "items", []) or []
        summary["health"] = {
            item.kind: {
                "today": item.value_today,
                "avg_window": item.value_avg_window,
                "window_days": item.window_days,
                "unit": item.unit,
            }
            for item in items
        }

    if not summary:
        return "{}"
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


def _fallback_greeting(user: User, user_tz: ZoneInfo, language: str) -> str:
    """Static fallback when the LLM is unreachable.

    Localized in the 6 supported languages so the page never falls back to
    English when the user is on another locale.
    """
    name = _resolve_display_name(user)
    bucket = _compute_time_of_day(user_tz)

    fallbacks = {
        "fr": {
            TIME_OF_DAY_MORNING: f"Bonjour {name}.",
            TIME_OF_DAY_AFTERNOON: f"Bon après-midi {name}.",
            TIME_OF_DAY_EVENING: f"Bonsoir {name}.",
            TIME_OF_DAY_NIGHT: f"Bonsoir {name}.",
        },
        "en": {
            TIME_OF_DAY_MORNING: f"Good morning, {name}.",
            TIME_OF_DAY_AFTERNOON: f"Good afternoon, {name}.",
            TIME_OF_DAY_EVENING: f"Good evening, {name}.",
            TIME_OF_DAY_NIGHT: f"Good evening, {name}.",
        },
        "es": {
            TIME_OF_DAY_MORNING: f"Buenos días, {name}.",
            TIME_OF_DAY_AFTERNOON: f"Buenas tardes, {name}.",
            TIME_OF_DAY_EVENING: f"Buenas noches, {name}.",
            TIME_OF_DAY_NIGHT: f"Buenas noches, {name}.",
        },
        "de": {
            TIME_OF_DAY_MORNING: f"Guten Morgen, {name}.",
            TIME_OF_DAY_AFTERNOON: f"Guten Tag, {name}.",
            TIME_OF_DAY_EVENING: f"Guten Abend, {name}.",
            TIME_OF_DAY_NIGHT: f"Guten Abend, {name}.",
        },
        "it": {
            TIME_OF_DAY_MORNING: f"Buongiorno, {name}.",
            TIME_OF_DAY_AFTERNOON: f"Buon pomeriggio, {name}.",
            TIME_OF_DAY_EVENING: f"Buonasera, {name}.",
            TIME_OF_DAY_NIGHT: f"Buonasera, {name}.",
        },
        "zh": {
            TIME_OF_DAY_MORNING: f"早上好，{name}。",
            TIME_OF_DAY_AFTERNOON: f"下午好，{name}。",
            TIME_OF_DAY_EVENING: f"晚上好，{name}。",
            TIME_OF_DAY_NIGHT: f"晚上好，{name}。",
        },
    }
    lang = (language or "en").split("-")[0].lower()
    return fallbacks.get(lang, fallbacks["en"]).get(bucket, f"Hello, {name}.")
