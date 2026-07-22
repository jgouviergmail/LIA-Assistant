"""Psyche production measurement instrument (ADR-104 / ADR-142).

Replays the ADR-104 baseline battery against the live ``psyche_history`` /
``psyche_states`` / ``personalities`` tables, read-only. This is the missing
artifact behind ADR-104's "production re-measurement after >= 1 month"
acceptance criterion — run it BEFORE activating ``PSYCHE_DOMINANCE_CENTER``
or flipping ``PSYCHE_PROACTIVE_JOY_PULSE``, then again after, and compare.

Per-user metrics (message snapshots in the window): distinct moods visited
(labels recomputed from PAD via ``classify_mood`` — history stores no label),
top-mood share, PAD octant coverage, dominance/arousal-negative shares,
dominant-emotion distribution (joy/pride flagged), intensity >= 0.60 share,
dominant-emotion stickiness, mean co-active emotions, and the
post-first-message magnitude after >= 12 h idle (snapshots are post-appraisal,
so this is NOT a resting magnitude — named accordingly).

Catalogue metrics: resting PAD + mood per personality at the CURRENT settings
(damping, dominance_center), D-spread, and how many personalities rest D < 0.

No PII: output contains user UUIDs, counters, and emotion/mood names only.

Usage:
    DEV:  cd apps/api && python scripts/measure_psyche.py
    PROD: docker exec lia-api-prod python scripts/measure_psyche.py

Options:
    --window-days N     Measurement window (default: 30)
    --min-snapshots N   Skip users with fewer message snapshots (default: 20)
    --json-out PATH     Also write the full report as diffable JSON
    --database-url URL  Override the settings database URL (asyncpg form)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# Add project root to path for imports (idempotent; harmless under pytest)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domains.psyche.engine import PADOverride, PersonalityTraits, PsycheEngine

# =============================================================================
# Pure data structures and aggregation (unit-tested, no DB)
# =============================================================================


@dataclass(frozen=True)
class SnapshotRow:
    """One ``psyche_history`` message snapshot, flattened for aggregation."""

    created_at: datetime
    mood_pleasure: float
    mood_arousal: float
    mood_dominance: float
    dominant_emotion: str | None
    emotion_intensity: float
    active_emotion_count: int


@dataclass(frozen=True)
class UserMetrics:
    """ADR-104 baseline battery for one user."""

    snapshot_count: int
    distinct_moods: int
    mood_distribution: dict[str, int]
    top_mood: str | None
    top_mood_share: float | None
    octants_visited: int
    octant_distribution: dict[str, int]
    share_dominance_negative: float | None
    share_arousal_negative: float | None
    dominant_emotion_distribution: dict[str, int]
    top_dominant_emotion: str | None
    joy_dominant_share: float | None
    pride_dominant_share: float | None
    intensity_ge_060_share: float | None
    dominant_stickiness: float | None
    mean_co_active_emotions: float | None
    post_idle_magnitude_mean: float | None
    post_idle_sample_count: int


@dataclass(frozen=True)
class PersonalityRow:
    """One ``personalities`` row, flattened for resting-point classification."""

    code: str
    openness: float | None
    conscientiousness: float | None
    extraversion: float | None
    agreeableness: float | None
    neuroticism: float | None
    pad_pleasure_override: float | None
    pad_arousal_override: float | None
    pad_dominance_override: float | None


@dataclass(frozen=True)
class RestingRow:
    """Resting PAD + mood classification for one personality."""

    code: str
    pleasure: float
    arousal: float
    dominance: float
    resting_mood: str


def aggregate_user_metrics(
    rows: list[SnapshotRow],
    idle_gap_hours: float = 12.0,
) -> UserMetrics:
    """Compute the ADR-104 battery over one user's ordered message snapshots.

    Args:
        rows: Message snapshots (any order — sorted defensively by created_at).
        idle_gap_hours: Minimum pause before a snapshot counts as post-idle.

    Returns:
        UserMetrics with None for ratios that need data the rows cannot provide.
    """
    rows = sorted(rows, key=lambda r: r.created_at)
    n = len(rows)
    if n == 0:
        return UserMetrics(
            snapshot_count=0,
            distinct_moods=0,
            mood_distribution={},
            top_mood=None,
            top_mood_share=None,
            octants_visited=0,
            octant_distribution={},
            share_dominance_negative=None,
            share_arousal_negative=None,
            dominant_emotion_distribution={},
            top_dominant_emotion=None,
            joy_dominant_share=None,
            pride_dominant_share=None,
            intensity_ge_060_share=None,
            dominant_stickiness=None,
            mean_co_active_emotions=None,
            post_idle_magnitude_mean=None,
            post_idle_sample_count=0,
        )

    moods = Counter(
        PsycheEngine.classify_mood(r.mood_pleasure, r.mood_arousal, r.mood_dominance) for r in rows
    )
    top_mood, top_mood_count = moods.most_common(1)[0]

    octants = Counter(
        ("P+" if r.mood_pleasure >= 0 else "P-")
        + ("A+" if r.mood_arousal >= 0 else "A-")
        + ("D+" if r.mood_dominance >= 0 else "D-")
        for r in rows
    )

    dominants = Counter(r.dominant_emotion for r in rows if r.dominant_emotion)
    top_dominant = dominants.most_common(1)[0][0] if dominants else None

    transitions = [
        (rows[i - 1].dominant_emotion, rows[i].dominant_emotion)
        for i in range(1, n)
        if rows[i - 1].dominant_emotion and rows[i].dominant_emotion
    ]
    stickiness = (
        sum(1 for prev, curr in transitions if prev == curr) / len(transitions)
        if transitions
        else None
    )

    post_idle_magnitudes = [
        math.sqrt(
            rows[i].mood_pleasure ** 2 + rows[i].mood_arousal ** 2 + rows[i].mood_dominance ** 2
        )
        for i in range(1, n)
        if (rows[i].created_at - rows[i - 1].created_at) >= timedelta(hours=idle_gap_hours)
    ]

    return UserMetrics(
        snapshot_count=n,
        distinct_moods=len(moods),
        mood_distribution=dict(moods.most_common()),
        top_mood=top_mood,
        top_mood_share=top_mood_count / n,
        octants_visited=len(octants),
        octant_distribution=dict(octants.most_common()),
        share_dominance_negative=sum(1 for r in rows if r.mood_dominance < 0) / n,
        share_arousal_negative=sum(1 for r in rows if r.mood_arousal < 0) / n,
        dominant_emotion_distribution=dict(dominants.most_common()),
        top_dominant_emotion=top_dominant,
        joy_dominant_share=(dominants.get("joy", 0) / n) if n else None,
        pride_dominant_share=(dominants.get("pride", 0) / n) if n else None,
        intensity_ge_060_share=sum(1 for r in rows if r.emotion_intensity >= 0.60) / n,
        dominant_stickiness=stickiness,
        mean_co_active_emotions=sum(r.active_emotion_count for r in rows) / n,
        post_idle_magnitude_mean=(
            sum(post_idle_magnitudes) / len(post_idle_magnitudes) if post_idle_magnitudes else None
        ),
        post_idle_sample_count=len(post_idle_magnitudes),
    )


def classify_catalogue(
    rows: list[PersonalityRow],
    damping: float,
    dominance_center: float,
) -> list[RestingRow]:
    """Classify each personality's resting PAD + mood at the given settings.

    Args:
        rows: Personality rows (None traits fall back to balanced 0.5 defaults,
            mirroring PsycheService._load_personality_traits_and_override).
        damping: Baseline damping to apply.
        dominance_center: Dominance translation to apply.

    Returns:
        One RestingRow per input row, in input order.
    """
    out: list[RestingRow] = []
    for row in rows:
        traits = PersonalityTraits(
            openness=row.openness if row.openness is not None else 0.5,
            conscientiousness=(row.conscientiousness if row.conscientiousness is not None else 0.5),
            extraversion=row.extraversion if row.extraversion is not None else 0.5,
            agreeableness=row.agreeableness if row.agreeableness is not None else 0.5,
            neuroticism=row.neuroticism if row.neuroticism is not None else 0.5,
        )
        override = (
            PADOverride(
                pleasure=row.pad_pleasure_override,
                arousal=row.pad_arousal_override,
                dominance=row.pad_dominance_override,
            )
            if any(
                x is not None
                for x in (
                    row.pad_pleasure_override,
                    row.pad_arousal_override,
                    row.pad_dominance_override,
                )
            )
            else None
        )
        pad = PsycheEngine.compute_pad_baseline(
            traits, override, damping=damping, dominance_center=dominance_center
        )
        out.append(
            RestingRow(
                code=row.code,
                pleasure=pad.pleasure,
                arousal=pad.arousal,
                dominance=pad.dominance,
                resting_mood=PsycheEngine.classify_mood(pad.pleasure, pad.arousal, pad.dominance),
            )
        )
    return out


# =============================================================================
# Async I/O shell (thin: fetch rows, delegate to pure functions, render)
# =============================================================================


async def _fetch_report(window_days: int, min_snapshots: int) -> dict[str, Any]:
    """Fetch snapshots + catalogue and build the full report dict."""
    from sqlalchemy import select

    from src.core.config import settings
    from src.domains.personalities.models import Personality
    from src.domains.psyche.constants import SNAPSHOT_TYPE_MESSAGE
    from src.domains.psyche.models import PsycheHistory
    from src.infrastructure.database.session import get_db_context

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": window_days,
        "min_snapshots": min_snapshots,
        "settings": {
            "psyche_baseline_damping": settings.psyche_baseline_damping,
            "psyche_dominance_center": settings.psyche_dominance_center,
            "psyche_proactive_joy_pulse": settings.psyche_proactive_joy_pulse,
        },
        "users": {},
        "skipped_users": {},
        "catalogue": [],
    }

    async with get_db_context() as db:
        result = await db.execute(
            select(
                PsycheHistory.user_id,
                PsycheHistory.created_at,
                PsycheHistory.mood_pleasure,
                PsycheHistory.mood_arousal,
                PsycheHistory.mood_dominance,
                PsycheHistory.dominant_emotion,
                PsycheHistory.trait_snapshot,
            )
            .where(
                PsycheHistory.snapshot_type == SNAPSHOT_TYPE_MESSAGE,
                PsycheHistory.created_at >= cutoff,
            )
            .order_by(PsycheHistory.user_id, PsycheHistory.created_at)
        )

        by_user: dict[str, list[SnapshotRow]] = {}
        for user_id, created_at, p, a, d, dominant, snap in result.all():
            snap = snap or {}
            by_user.setdefault(str(user_id), []).append(
                SnapshotRow(
                    created_at=created_at,
                    mood_pleasure=p,
                    mood_arousal=a,
                    mood_dominance=d,
                    dominant_emotion=dominant,
                    emotion_intensity=float(snap.get("emotion_intensity", 0.0)),
                    active_emotion_count=len(snap.get("active_emotions", {}) or {}),
                )
            )

        for user_id, rows in by_user.items():
            if len(rows) < min_snapshots:
                report["skipped_users"][
                    user_id
                ] = f"insufficient data: {len(rows)} < {min_snapshots} snapshots"
                continue
            report["users"][user_id] = asdict(aggregate_user_metrics(rows))

        personalities = (
            await db.execute(
                select(
                    Personality.code,
                    Personality.trait_openness,
                    Personality.trait_conscientiousness,
                    Personality.trait_extraversion,
                    Personality.trait_agreeableness,
                    Personality.trait_neuroticism,
                    Personality.pad_pleasure_override,
                    Personality.pad_arousal_override,
                    Personality.pad_dominance_override,
                ).order_by(Personality.code)
            )
        ).all()
        catalogue_rows = [
            PersonalityRow(
                code=str(code),
                openness=o,
                conscientiousness=c,
                extraversion=e,
                agreeableness=a,
                neuroticism=n,
                pad_pleasure_override=pp,
                pad_arousal_override=pa,
                pad_dominance_override=pd,
            )
            for code, o, c, e, a, n, pp, pa, pd in personalities
        ]
        resting = classify_catalogue(
            catalogue_rows,
            damping=settings.psyche_baseline_damping,
            dominance_center=settings.psyche_dominance_center,
        )
        report["catalogue"] = [asdict(r) for r in resting]
        d_values = [r.dominance for r in resting]
        report["catalogue_summary"] = {
            "personalities": len(resting),
            "resting_d_min": min(d_values) if d_values else None,
            "resting_d_max": max(d_values) if d_values else None,
            "resting_d_mean": (sum(d_values) / len(d_values)) if d_values else None,
            "resting_d_negative_count": sum(1 for d in d_values if d < 0),
            "distinct_resting_moods": len({r.resting_mood for r in resting}),
        }

    return report


def _render(report: dict[str, Any]) -> None:
    """Print the human-readable report to stdout."""
    print("=" * 78)
    print("PSYCHE PRODUCTION MEASUREMENT (ADR-104 baseline battery)")
    print("=" * 78)
    print(f"generated: {report['generated_at']}  window: {report['window_days']}d")
    s = report["settings"]
    print(
        f"settings: damping={s['psyche_baseline_damping']}"
        f" center={s['psyche_dominance_center']}"
        f" joy_pulse={s['psyche_proactive_joy_pulse']}"
    )

    for user_id, m in report["users"].items():
        print(f"\n--- user {user_id} ({m['snapshot_count']} snapshots) ---")
        print(f"  moods visited     : {m['distinct_moods']}/14 -> {m['mood_distribution']}")
        print(
            f"  top mood          : {m['top_mood']} ({m['top_mood_share']:.0%})"
            if m["top_mood"]
            else "  top mood          : -"
        )
        print(f"  octants           : {m['octants_visited']}/8 -> {m['octant_distribution']}")
        print(
            f"  D<0 share         : {m['share_dominance_negative']:.1%}"
            f"   A<0 share: {m['share_arousal_negative']:.1%}"
        )
        print(f"  dominant emotions : {m['dominant_emotion_distribution']}")
        print(
            f"  joy dominant      : {m['joy_dominant_share']:.1%}"
            f"   pride dominant: {m['pride_dominant_share']:.1%}"
        )
        print(f"  intensity >=0.60  : {m['intensity_ge_060_share']:.1%}")
        stickiness = m["dominant_stickiness"]
        print(
            f"  stickiness        : {stickiness:.1%}"
            if stickiness is not None
            else "  stickiness        : - (not enough transitions)"
        )
        print(f"  co-active mean    : {m['mean_co_active_emotions']:.2f}")
        pim = m["post_idle_magnitude_mean"]
        print(
            f"  post-idle |PAD|   : {pim:.3f} (n={m['post_idle_sample_count']})"
            if pim is not None
            else "  post-idle |PAD|   : - (no >=12h gap in window)"
        )

    for user_id, reason in report["skipped_users"].items():
        print(f"\n--- user {user_id}: SKIPPED ({reason}) ---")

    print("\n--- personality catalogue at current settings ---")
    for r in report["catalogue"]:
        print(
            f"  {r['code']:<16} P={r['pleasure']:+.3f} A={r['arousal']:+.3f}"
            f" D={r['dominance']:+.3f}  rest={r['resting_mood']}"
        )
    cs = report.get("catalogue_summary", {})
    if cs:
        print(
            f"  => D spread [{cs['resting_d_min']:+.3f}, {cs['resting_d_max']:+.3f}]"
            f" mean {cs['resting_d_mean']:+.3f};"
            f" {cs['resting_d_negative_count']}/{cs['personalities']} rest D<0;"
            f" {cs['distinct_resting_moods']} distinct resting moods"
        )


async def _amain(args: argparse.Namespace) -> int:
    """Async entry point: env overrides, model imports, fetch, render."""
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from dotenv import load_dotenv

    load_dotenv()

    from src.infrastructure.database.registry import import_all_models

    import_all_models()

    report = await _fetch_report(args.window_days, args.min_snapshots)
    _render(report)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nJSON report written to {args.json_out}")
    return 0


def main() -> int:
    """Parse CLI arguments and run the measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--min-snapshots", type=int, default=20)
    parser.add_argument("--json-out", type=str, default=None)
    parser.add_argument("--database-url", type=str, default=None)
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
