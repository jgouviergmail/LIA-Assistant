"""Per-user adaptive threshold controller (lot 7, audit 2026-08-19).

A fixed global similarity threshold is structurally wrong when the score
distribution depends on each user's stock and vocabulary: prod journal
injection ran at 10% with scores massed at 0.53–0.61 under the global 0.63.
This controller learns a per-user threshold, under four non-negotiable
safety rails:

- **hard bounds** — the value lives in ``[floor, ceiling]``, never beyond;
- **hysteresis** — one ``step`` per ``adjust_interval``, whatever the error;
- **observability** — every adjustment is counted and logged; the effective
  value flows through the existing debug surfaces (a constraint the system
  applies is a constraint it publishes, ADR-184);
- **kill-switch** — ``ADAPTIVE_THRESHOLDS_ENABLED=false`` freezes everything
  to the static defaults.

Generic by design: a perimeter is a registry entry (name, bounds, target
rate band, static default), so memories/interests thresholds can join later
without new machinery. State is advisory Redis (recurrence-ledger family): a
flush costs a relearn, never a wrong value — reads fail open to the static
default.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "adaptive:thr"


@dataclass(frozen=True)
class ThresholdPerimeter:
    """One adaptive perimeter: what is tuned, inside which hard bounds.

    Attributes:
        name: Registry key and Redis key segment.
        floor: Hard lower bound — the controller can never go below.
        ceiling: Hard upper bound.
        target_rate_low: Lower edge of the acceptable pass-rate band.
        target_rate_high: Upper edge of the acceptable pass-rate band.
        default_getter: Lazy static default (reads settings at call time so
            env overrides and tests see the live value).
    """

    name: str
    floor: float
    ceiling: float
    target_rate_low: float
    target_rate_high: float
    default_getter: Callable[[], float]


#: Registered perimeters — extend HERE (bounds are a design decision: replay
#: the perimeter's calibration evidence before widening them).
PERIMETERS: dict[str, ThresholdPerimeter] = {
    "journal_injection": ThresholdPerimeter(
        name="journal_injection",
        floor=0.55,
        ceiling=0.70,
        target_rate_low=0.10,
        target_rate_high=0.35,
        default_getter=lambda: settings.journal_context_min_score,
    ),
}


def assert_perimeters_valid() -> None:
    """Boot-time completeness/validity assert (ADR-085 family).

    Raises:
        ValueError: On any inconsistent perimeter spec — the app must refuse
            to boot rather than adjust inside a broken frame.
    """
    for name, spec in PERIMETERS.items():
        if name != spec.name:
            raise ValueError(f"Adaptive perimeter key '{name}' != spec.name '{spec.name}'")
        if not (0.0 <= spec.floor < spec.ceiling <= 1.0):
            raise ValueError(f"Adaptive perimeter '{name}': invalid bounds")
        if not (0.0 < spec.target_rate_low < spec.target_rate_high < 1.0):
            raise ValueError(f"Adaptive perimeter '{name}': invalid target band")


# Import-time validation: a broken registry must never reach runtime.
assert_perimeters_valid()


def decide_adjustment(
    threshold: float,
    samples: list[float],
    now: datetime,
    adjusted_at: datetime | None,
    spec: ThresholdPerimeter,
    cfg: dict[str, Any],
) -> float | None:
    """Pure adjustment decision — the whole control law, testable offline.

    Args:
        threshold: Current effective threshold.
        samples: Rolling window of observed top scores (one per search).
        now: Current time (injected — never read inside).
        adjusted_at: Last adjustment time, None when never adjusted.
        spec: Perimeter bounds and target band.
        cfg: Controller settings (window_size, min_samples, step,
            adjust_interval_hours).

    Returns:
        The new threshold (one bounded step), or None when nothing changes.
    """
    if len(samples) < int(cfg["min_samples"]):
        return None
    if adjusted_at is not None:
        elapsed_hours = (now - adjusted_at).total_seconds() / 3600.0
        if elapsed_hours < float(cfg["adjust_interval_hours"]):
            return None

    rate = sum(1 for s in samples if s >= threshold) / len(samples)
    step = float(cfg["step"])
    if rate < spec.target_rate_low:
        candidate = max(spec.floor, threshold - step)
    elif rate > spec.target_rate_high:
        candidate = min(spec.ceiling, threshold + step)
    else:
        return None
    return None if candidate == threshold else round(candidate, 4)


async def _get_redis() -> Any:
    """Seam for tests — resolves the shared Redis cache client."""
    from src.infrastructure.cache.redis import get_redis_cache

    return await get_redis_cache()


def _redis_key(perimeter: str, user_id: UUID) -> str:
    return f"{_KEY_PREFIX}:{perimeter}:{user_id}"


def _controller_cfg() -> dict[str, Any]:
    return {
        "window_size": settings.adaptive_threshold_window_size,
        "min_samples": settings.adaptive_threshold_min_samples,
        "step": settings.adaptive_threshold_step,
        "adjust_interval_hours": settings.adaptive_threshold_adjust_interval_hours,
    }


def _load_state(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        state = json.loads(raw)
        if not isinstance(state, dict) or not isinstance(state.get("s"), list):
            return None
        return state
    except ValueError, TypeError:
        return None


async def effective_threshold(user_id: UUID, perimeter: str) -> float:
    """The threshold to APPLY for this user and perimeter.

    Fail-open by contract for RUNTIME conditions: disabled flag, Redis down
    or corrupt state all resolve to the static default, and a stored value
    is clamped into the hard bounds (defense in depth against stale state
    written under older bounds). An UNKNOWN perimeter is a programming
    error and raises instead — a typo must never silently apply some
    threshold to the wrong perimeter.

    Args:
        user_id: Owner.
        perimeter: Registered perimeter name.

    Returns:
        The effective threshold.

    Raises:
        ValueError: On an unregistered perimeter name.
    """
    spec = PERIMETERS.get(perimeter)
    if spec is None:
        # A typo must fail loudly: returning a default here would silently
        # apply SOME threshold to the wrong perimeter. Callers sit inside
        # their flow's degradation boundary, so this surfaces as a logged
        # skip, never a broken turn.
        raise ValueError(f"unknown adaptive perimeter: {perimeter!r}")
    default = spec.default_getter()
    if not getattr(settings, "adaptive_thresholds_enabled", False):
        return default
    try:
        redis = await _get_redis()
        if redis is None:
            return default
        state = _load_state(await redis.get(_redis_key(perimeter, user_id)))
        if state is None or not isinstance(state.get("t"), int | float):
            return default
        return min(spec.ceiling, max(spec.floor, float(state["t"])))
    except Exception as exc:  # noqa: BLE001 — advisory state, never blocks a turn
        logger.debug("adaptive_threshold_read_failed", perimeter=perimeter, error=str(exc))
        return default


async def observe_score(user_id: UUID, perimeter: str, top_score: float) -> None:
    """Record one search's top score and maybe apply one bounded adjustment.

    Called after each semantic search that had at least one candidate (no
    candidates = no information about the threshold). Best-effort: any
    failure is logged at debug and swallowed — the turn must never pay for
    its own optimization.

    Args:
        user_id: Owner.
        perimeter: Registered perimeter name.
        top_score: Highest candidate similarity observed by this search.
    """
    spec = PERIMETERS.get(perimeter)
    if spec is None:
        raise ValueError(f"unknown adaptive perimeter: {perimeter!r}")
    if not getattr(settings, "adaptive_thresholds_enabled", False):
        return
    # Accepted race: two concurrent turns read-modify-write the same key —
    # worst case ONE sample is lost, and a same-instant double adjustment
    # writes the SAME stepped value twice (both start from the same base, so
    # steps never compound). Advisory learning state, recurrence-ledger
    # doctrine: a lock here would cost more than the data it protects.
    try:
        redis = await _get_redis()
        if redis is None:
            return
        key = _redis_key(perimeter, user_id)
        cfg = _controller_cfg()
        state = _load_state(await redis.get(key)) or {
            "t": spec.default_getter(),
            "s": [],
            "at": None,
        }
        samples = [float(s) for s in state["s"]][-(int(cfg["window_size"]) - 1) :]
        samples.append(round(float(top_score), 4))

        threshold = min(spec.ceiling, max(spec.floor, float(state.get("t") or 0.0)))
        adjusted_at_raw = state.get("at")
        adjusted_at = datetime.fromisoformat(adjusted_at_raw) if adjusted_at_raw else None
        now = datetime.now(UTC)

        new_threshold = decide_adjustment(threshold, samples, now, adjusted_at, spec, cfg)
        if new_threshold is not None:
            direction = "down" if new_threshold < threshold else "up"
            # Metrics are best-effort — never break the observation path.
            with suppress(Exception):
                from src.infrastructure.observability.metrics_registry import (
                    adaptive_threshold_adjustments_total,
                )

                adaptive_threshold_adjustments_total.labels(
                    perimeter=perimeter, direction=direction
                ).inc()
            logger.info(
                "adaptive_threshold_adjusted",
                perimeter=perimeter,
                user_id=str(user_id),
                previous=threshold,
                new=new_threshold,
                direction=direction,
                samples=len(samples),
            )
            threshold = new_threshold
            adjusted_at = now

        # Sliding TTL (refreshed on every write): advisory state must expire —
        # deleted or abandoned accounts must not leave orphan keys forever.
        await redis.set(
            key,
            json.dumps(
                {
                    "t": threshold,
                    "s": samples,
                    "at": adjusted_at.isoformat() if adjusted_at else None,
                }
            ),
            ex=settings.adaptive_threshold_state_ttl_days * 86_400,
        )
    except Exception as exc:  # noqa: BLE001 — advisory state, never blocks a turn
        logger.debug("adaptive_threshold_observe_failed", perimeter=perimeter, error=str(exc))


def record_candidate_score(perimeter: str, top_score: float) -> None:
    """Aggregate calibration evidence for a CANDIDATE perimeter (Lot 7-B4).

    No per-user state, no threshold effect: registering a perimeter stays
    an owner arbitration — this histogram is what that arbitration reads.
    Best-effort by doctrine: a turn never pays for its own optimization.
    """
    with suppress(Exception):
        if not perimeter or not (0.0 <= top_score <= 1.0):
            return
        from src.infrastructure.observability.metrics_registry import (
            adaptive_candidate_top_score,
        )

        adaptive_candidate_top_score.labels(perimeter=perimeter).observe(top_score)
