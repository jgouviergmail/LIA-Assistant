"""
Psyche Engine service — orchestrates DB, cache, and engine computation.

Responsibilities:
- Lazy initialization of PsycheState for new users
- Pre-response: load state, apply decay, compile expression profile
- Post-response: apply appraisal, update relationship, persist
- Reset: soft/full/purge levels
- Settings: read/update user preferences
- GDPR: delete all psyche data for a user

Error handling: ALL psyche failures are caught and logged as warnings.
The psyche engine NEVER breaks the response pipeline.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import time as _time
import zoneinfo
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import REDIS_KEY_PSYCHE_STATE_PREFIX
from src.domains.psyche.constants import (
    PSYCHE_SCHEMA_VERSION,
    RELATIONSHIP_STAGES,
    RESET_LEVEL_FULL,
    RESET_LEVEL_PURGE,
    RESET_LEVEL_SOFT,
    SELF_EFFICACY_CONVERSATION_DOMAIN,
    SNAPSHOT_TYPE_MESSAGE,
)
from src.domains.psyche.engine import (
    PADOverride,
    PADVector,
    PersonalityTraits,
    PsycheAppraisal,
    PsycheEngine,
)
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.psyche.repository import PsycheStateRepository
from src.domains.psyche.schemas import PsycheStateSummary
from src.infrastructure.observability.logging import get_logger

# Lazy imports for generate_summary (avoid circular at module level)
# from src.infrastructure.llm import get_llm
# from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

logger = get_logger(__name__)

# =============================================================================
# In-process summary registry (for SSE done metadata)
# =============================================================================
# Same pattern as journal extraction debug (extraction_service.py)
# Written by psyche_post_response_background, popped by api/service.py

_SUMMARY_TTL_SECONDS: int = 300  # 5 minutes

_psyche_summary_results: dict[str, tuple[float, dict[str, Any]]] = {}


def store_psyche_summary(run_id: str, summary: dict[str, Any]) -> None:
    """Store psyche summary for a given run_id with timestamp.

    Args:
        run_id: Pipeline run_id to associate the summary with.
        summary: PsycheStateSummary dict.
    """
    _psyche_summary_results[run_id] = (_time.monotonic(), summary)


def peek_psyche_summary(run_id: str) -> dict[str, Any] | None:
    """Return psyche summary for a given run_id without removing it.

    Args:
        run_id: Pipeline run_id whose summary to retrieve.

    Returns:
        Summary dict or None if not found.
    """
    entry = _psyche_summary_results.get(run_id)
    return entry[1] if entry is not None else None


def pop_psyche_summary(run_id: str) -> dict[str, Any] | None:
    """Pop and return psyche summary for a given run_id.

    Also evicts stale entries older than TTL.

    Args:
        run_id: Pipeline run_id whose summary to retrieve.

    Returns:
        Summary dict or None if not found.
    """
    # Evict stale entries
    now = _time.monotonic()
    stale_keys = [
        k for k, (ts, _) in _psyche_summary_results.items() if now - ts > _SUMMARY_TTL_SECONDS
    ]
    for k in stale_keys:
        del _psyche_summary_results[k]

    entry = _psyche_summary_results.pop(run_id, None)
    return entry[1] if entry is not None else None


# =============================================================================
# PsycheService
# =============================================================================


class PsycheService:
    """Orchestrates psyche state management: DB + cache + engine computation."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db
        self.repo = PsycheStateRepository(db)

    # =========================================================================
    # Lazy Initialization
    # =========================================================================

    async def get_or_create_state(self, user_id: UUID) -> PsycheState:
        """Load psyche state from cache/DB, or create default for new users.

        Lazy initialization: creates a default PsycheState on first access
        with Big Five traits copied from the user's current personality.

        Args:
            user_id: User UUID.

        Returns:
            PsycheState (existing or newly created).
        """
        # Try Redis cache first
        cached = await self._load_from_cache(user_id)
        if cached:
            return cached

        # Try DB
        state = await self.repo.get_by_user_id(user_id)
        if state:
            await self._save_to_cache(user_id, state)
            return state

        # Create default — load personality traits
        traits = await self._load_personality_traits(user_id)
        efficacy = PsycheEngine.initialize_self_efficacy()

        state = PsycheState(
            user_id=user_id,
            trait_openness=traits.openness,
            trait_conscientiousness=traits.conscientiousness,
            trait_extraversion=traits.extraversion,
            trait_agreeableness=traits.agreeableness,
            trait_neuroticism=traits.neuroticism,
            self_efficacy=efficacy,
            psyche_version=PSYCHE_SCHEMA_VERSION,
        )

        # Compute initial mood at baseline
        baseline = PsycheEngine.compute_pad_baseline(traits)
        state.mood_pleasure = baseline.pleasure
        state.mood_arousal = baseline.arousal
        state.mood_dominance = baseline.dominance
        state.mood_quadrant_since = datetime.now(UTC)

        state = await self.repo.create(state)
        await self._save_to_cache(user_id, state)

        logger.info(
            "psyche_state_initialized",
            user_id=str(user_id),
            traits=f"O={traits.openness}/C={traits.conscientiousness}/"
            f"E={traits.extraversion}/A={traits.agreeableness}/N={traits.neuroticism}",
        )
        return state

    async def sync_traits_from_personality(self, user_id: UUID) -> None:
        """Sync Big Five traits and mood baseline when personality changes.

        Called when the user switches personality. Updates the stored traits
        and recomputes the PAD baseline so the mood evolves toward the new
        personality's resting point.

        Args:
            user_id: User UUID.
        """
        state = await self.repo.get_by_user_id(user_id)
        if not state:
            return  # No psyche state yet — traits will be set at creation

        traits, pad_override = await self._load_personality_traits_and_override(user_id)

        state.trait_openness = traits.openness
        state.trait_conscientiousness = traits.conscientiousness
        state.trait_extraversion = traits.extraversion
        state.trait_agreeableness = traits.agreeableness
        state.trait_neuroticism = traits.neuroticism

        # Recompute mood baseline — mood will naturally decay toward it
        baseline = PsycheEngine.compute_pad_baseline(traits, pad_override)
        state.mood_pleasure = baseline.pleasure
        state.mood_arousal = baseline.arousal
        state.mood_dominance = baseline.dominance

        await self.repo.update(state)
        await self._invalidate_cache(user_id)

        logger.info(
            "psyche_traits_synced_from_personality",
            user_id=str(user_id),
            traits=f"O={traits.openness}/C={traits.conscientiousness}/"
            f"E={traits.extraversion}/A={traits.agreeableness}/N={traits.neuroticism}",
        )

    # =========================================================================
    # Pre-Response Processing (blocking, ~2ms)
    # =========================================================================

    async def process_pre_response(
        self,
        user_id: UUID,
        user_timezone: str = "Europe/Paris",
    ) -> tuple[str, PsycheStateSummary | None]:
        """Process pre-response: load state, apply decay, compile profile.

        Called BEFORE response generation. Returns the psyche context string
        for prompt injection and a lightweight summary for SSE metadata.

        Args:
            user_id: User UUID.
            user_timezone: IANA timezone for circadian modulation.

        Returns:
            Tuple of (psyche_context_string, PsycheStateSummary or None).
        """
        state = await self.get_or_create_state(user_id)
        now = datetime.now(UTC)

        # Load personality for PAD baseline computation
        traits, pad_override = await self._load_personality_traits_and_override(user_id)
        baseline = PsycheEngine.compute_pad_baseline(traits, pad_override)

        # Compute time elapsed since last update
        hours_elapsed = 0.0
        if state.updated_at:
            hours_elapsed = max(0.0, (now - state.updated_at).total_seconds() / 3600.0)

        # Load user stability preference for dynamic decay rate
        # stability=0% → fastest mood changes (2x base rate)
        # stability=50% → moderate (1x base rate)
        # stability=100% → slowest mood changes (0.3x base rate)
        # Formula: inverted scale with floor to prevent zero decay
        _, user_stability = await self._load_user_psyche_prefs(user_id)
        stability_factor = max(0.3, 2.0 - (user_stability / 50.0))
        effective_decay_rate = settings.psyche_mood_decay_rate * stability_factor

        # Capture mood quadrant BEFORE decay (for inertia tracking)
        pre_decay_quadrant = PADVector(
            state.mood_pleasure, state.mood_arousal, state.mood_dominance
        ).quadrant_key()

        # Apply temporal decay
        (
            state.mood_pleasure,
            state.mood_arousal,
            state.mood_dominance,
            surviving_emotions,
            state.relationship_warmth_active,
        ) = PsycheEngine.apply_temporal_decay(
            mood_p=state.mood_pleasure,
            mood_a=state.mood_arousal,
            mood_d=state.mood_dominance,
            baseline=baseline,
            hours_elapsed=hours_elapsed,
            decay_rate=effective_decay_rate,
            emotions=state.active_emotions or [],
            emotion_decay_rate=settings.psyche_emotion_decay_rate,
            warmth=state.relationship_warmth_active,
            warmth_decay_rate=settings.psyche_relationship_warmth_decay_rate,
            has_interaction=True,
            traits=traits,
        )
        state.active_emotions = surviving_emotions

        # Apply circadian modulation
        local_hour = _compute_local_hour(now, user_timezone)
        state.mood_pleasure = PsycheEngine.apply_circadian(
            state.mood_pleasure, local_hour, settings.psyche_circadian_amplitude
        )

        # Track mood quadrant changes (for emotional inertia calculation)
        # If quadrant changed after decay+circadian, reset the inertia timer
        post_decay_quadrant = PADVector(
            state.mood_pleasure, state.mood_arousal, state.mood_dominance
        ).quadrant_key()

        if post_decay_quadrant != pre_decay_quadrant or state.mood_quadrant_since is None:
            state.mood_quadrant_since = now

        # v2: proactive emotion pulses based on drives and context
        proactive = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=state.drive_curiosity,
            drive_engagement=state.drive_engagement,
            interaction_count=state.relationship_interaction_count,
            last_appraisal=state.last_appraisal,
            self_efficacy=state.self_efficacy,
            existing_emotions=state.active_emotions or [],
            now_iso=now.isoformat(),
        )
        if proactive:
            state.active_emotions = PsycheEngine.merge_proactive_emotions(
                existing_emotions=state.active_emotions or [],
                proactive=proactive,
            )
            logger.debug(
                "psyche_proactive_injected",
                user_id=str(user_id),
                pulse_count=len(proactive),
                pulses=[p["name"] for p in proactive],
            )

        # Compile expression profile (top_n=3 for rich directives)
        profile = PsycheEngine.compile_expression_profile(
            mood_p=state.mood_pleasure,
            mood_a=state.mood_arousal,
            mood_d=state.mood_dominance,
            emotions=state.active_emotions or [],
            stage=state.relationship_stage,
            warmth=state.relationship_warmth_active,
            drive_curiosity=state.drive_curiosity,
            drive_engagement=state.drive_engagement,
            top_n=3,
            self_efficacy=state.self_efficacy,
            traits=traits,
        )

        # Enrich profile with evolution awareness from last appraisal
        profile.gap_hours = hours_elapsed
        if state.last_appraisal:
            prev_emotion = state.last_appraisal.get("emotion")
            if prev_emotion:
                profile.previous_emotion = prev_emotion
            prev_mood = state.last_appraisal.get("mood_label")
            if prev_mood:
                profile.previous_mood = prev_mood
            # v2: previous PAD for transition detection
            prev_p = state.last_appraisal.get("mood_pleasure")
            prev_a = state.last_appraisal.get("mood_arousal")
            prev_d = state.last_appraisal.get("mood_dominance")
            if prev_p is not None and prev_a is not None and prev_d is not None:
                profile.previous_pad = (prev_p, prev_a, prev_d)

        # Persist decayed state
        await self.repo.update(state)
        await self._save_to_cache(user_id, state)

        # Build rich prompt injection with behavioral directives + usage guide
        from src.domains.agents.prompts.prompt_loader import load_prompt

        directives, usage_key = PsycheEngine.format_graduated_prompt_injection(profile)
        usage_guide = str(load_prompt(usage_key))
        psyche_context = f"<PsycheContext>\n{directives}\n\n{usage_guide}\n</PsycheContext>"

        # Build SSE summary
        top_emotion = None
        top_intensity = 0.0
        if state.active_emotions:
            sorted_emos = sorted(
                state.active_emotions, key=lambda e: e.get("intensity", 0), reverse=True
            )
            if sorted_emos:
                top_emotion = sorted_emos[0].get("name")
                top_intensity = sorted_emos[0].get("intensity", 0)

        # Build active_emotions list (top 3 for tooltip)
        top_emotions_list: list[dict] = []
        if state.active_emotions:
            sorted_emos = sorted(
                state.active_emotions, key=lambda e: e.get("intensity", 0), reverse=True
            )
            for emo in sorted_emos[:3]:
                emo_name = emo.get("name")
                emo_int = emo.get("intensity", 0)
                if emo_name and emo_int >= 0.05:
                    top_emotions_list.append({"name": emo_name, "intensity": round(emo_int, 2)})

        summary = PsycheStateSummary(
            mood_label=profile.mood_label,
            mood_color=PsycheEngine.mood_to_color(profile.mood_label),
            mood_pleasure=round(state.mood_pleasure, 3),
            mood_arousal=round(state.mood_arousal, 3),
            mood_dominance=round(state.mood_dominance, 3),
            active_emotion=top_emotion,
            emotion_intensity=round(top_intensity, 2),
            relationship_stage=state.relationship_stage,
            mood_intensity=profile.mood_intensity,
            active_emotions=top_emotions_list,
            drive_curiosity=round(state.drive_curiosity, 2),
            drive_engagement=round(state.drive_engagement, 2),
        )

        return psyche_context, summary

    # =========================================================================
    # Post-Response Processing (fire-and-forget)
    # =========================================================================

    async def process_post_response(
        self,
        user_id: UUID,
        appraisal: PsycheAppraisal | None = None,
    ) -> PsycheStateSummary | None:
        """Apply appraisal, update relationship, persist state.

        Called AFTER response generation in a fire-and-forget background task.

        Args:
            user_id: User UUID.
            appraisal: Parsed self-report from LLM response (None if tag absent).

        Returns:
            Updated PsycheStateSummary or None.
        """
        state = await self.get_or_create_state(user_id)
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        # Compute gap hours for relationship update
        gap_hours = 0.0
        if state.relationship_last_interaction:
            gap_hours = max(
                0.0,
                (now - state.relationship_last_interaction).total_seconds() / 3600.0,
            )

        # Get previous dominant emotion for rupture-repair detection
        prev_dominant = None
        if state.active_emotions:
            sorted_prev = sorted(
                state.active_emotions, key=lambda e: e.get("intensity", 0), reverse=True
            )
            if sorted_prev:
                prev_dominant = sorted_prev[0].get("name")

        if appraisal:
            # Compute inertia
            inertia = PsycheEngine.compute_emotional_inertia(state.mood_quadrant_since, now)

            # Load user expressiveness and compute effective sensitivity
            # 0% → 0.1 (stoic), 50% → 0.7 (base), 100% → 1.4 (extreme)
            # Formula: base * (0.15 + 1.85 * user/100) — linear scale from 0.1 to 1.4
            user_sensitivity, _ = await self._load_user_psyche_prefs(user_id)
            base_sensitivity = settings.psyche_appraisal_sensitivity
            expressiveness_scale = 0.15 + 1.85 * (user_sensitivity / 100.0)
            effective_sensitivity = base_sensitivity * expressiveness_scale

            # Load personality traits for Big Five modulation
            traits, _ = await self._load_personality_traits_and_override(user_id)

            # Apply appraisal (emotion creation + mood push + trait modulation)
            (
                state.mood_pleasure,
                state.mood_arousal,
                state.mood_dominance,
                updated_emotions,
            ) = PsycheEngine.apply_appraisal(
                mood_p=state.mood_pleasure,
                mood_a=state.mood_arousal,
                mood_d=state.mood_dominance,
                emotions=state.active_emotions or [],
                appraisal=appraisal,
                sensitivity=effective_sensitivity,
                inertia=inertia,
                max_active=settings.psyche_emotion_max_active,
                now_iso=now_iso,
                traits=traits,
            )
            state.active_emotions = updated_emotions
            # Store mood_label for evolution awareness in next pre-response
            _best_label = PsycheEngine.classify_mood(
                state.mood_pleasure, state.mood_arousal, state.mood_dominance
            )
            state.last_appraisal = {
                "valence": appraisal.valence,
                "arousal": appraisal.arousal,
                "emotions": list(appraisal.emotions),
                "emotion": appraisal.dominant_emotion,  # backward compat
                "intensity": appraisal.dominant_intensity,  # backward compat
                "quality": appraisal.quality,
                "mood_label": _best_label,
                "mood_pleasure": state.mood_pleasure,
                "mood_arousal": state.mood_arousal,
                "mood_dominance": state.mood_dominance,
                "timestamp": now_iso,
            }

            # v2: computed emotional resonance
            resonance = PsycheEngine.compute_resonance(
                user_valence=appraisal.valence,
                emotions=appraisal.emotions,
            )
            state.last_appraisal["resonance"] = round(resonance, 3)
            if abs(resonance) > 0.1:
                logger.debug(
                    "psyche_resonance_computed",
                    user_id=str(user_id),
                    resonance=round(resonance, 3),
                    user_valence=round(appraisal.valence, 2),
                    dominant_emotion=appraisal.dominant_emotion,
                )

            # Update relationship
            quality = appraisal.quality
            (
                state.relationship_depth,
                state.relationship_warmth_active,
                state.relationship_trust,
                state.relationship_interaction_count,
                state.relationship_stage,
                reunion_emotions,
            ) = PsycheEngine.update_relationship(
                depth=state.relationship_depth,
                warmth=state.relationship_warmth_active,
                trust=state.relationship_trust,
                interaction_count=state.relationship_interaction_count,
                stage=state.relationship_stage,
                quality=quality,
                gap_hours=gap_hours,
                now_iso=now_iso,
            )

            # Add reunion emotions
            if reunion_emotions:
                if state.active_emotions is None:
                    state.active_emotions = []
                state.active_emotions.extend(reunion_emotions)

            # Rupture-repair detection
            curr_dominant = appraisal.dominant_emotion
            repair_bonus = PsycheEngine.detect_rupture_repair(prev_dominant, curr_dominant)
            if repair_bonus > 0:
                state.relationship_trust = min(1.0, state.relationship_trust + repair_bonus)
                logger.info(
                    "psyche_rupture_repair_detected",
                    user_id=str(user_id),
                    prev_emotion=prev_dominant,
                    curr_emotion=curr_dominant,
                    trust_bonus=repair_bonus,
                )

            # v2: resonance → relationship modulation
            if abs(resonance) > 0.1:
                if resonance > 0.3:
                    warmth_boost = 0.02 * resonance
                    state.relationship_warmth_active = min(
                        1.0, state.relationship_warmth_active + warmth_boost
                    )
                elif resonance < -0.3 and state.relationship_stage == "STABLE":
                    trust_boost = 0.01 * abs(resonance)
                    state.relationship_trust = min(1.0, state.relationship_trust + trust_boost)
                elif resonance < -0.3:
                    warmth_penalty = 0.01 * abs(resonance)
                    state.relationship_warmth_active = max(
                        0.0, state.relationship_warmth_active - warmth_penalty
                    )

        # Update drives from appraisal (curiosity ← arousal, engagement ← quality)
        if appraisal:
            state.drive_curiosity, state.drive_engagement = PsycheEngine.update_drives(
                curiosity=state.drive_curiosity,
                engagement=state.drive_engagement,
                appraisal_arousal=appraisal.arousal,
                appraisal_quality=appraisal.quality,
            )

            # Update self-efficacy: quality > 0.6 = success, < 0.4 = failure
            # Uses "emotional_support" domain as proxy for conversational competence
            if appraisal.quality > 0.6 or appraisal.quality < 0.4:
                state.self_efficacy = PsycheEngine.update_self_efficacy(
                    efficacy=state.self_efficacy or PsycheEngine.initialize_self_efficacy(),
                    domain=SELF_EFFICACY_CONVERSATION_DOMAIN,
                    success=appraisal.quality > 0.6,
                    prior_weight=settings.psyche_self_efficacy_prior_weight,
                )

        # Always update last interaction timestamp
        state.relationship_last_interaction = now

        # Persist
        await self.repo.update(state)
        await self._save_to_cache(user_id, state)

        # Create history snapshot for evolution tracking (graphiques)
        if settings.psyche_history_snapshot_enabled:
            top_emo_name = None
            top_emo_intensity = 0.0
            if state.active_emotions:
                sorted_for_snap = sorted(
                    state.active_emotions,
                    key=lambda e: e.get("intensity", 0),
                    reverse=True,
                )
                if sorted_for_snap:
                    top_emo_name = sorted_for_snap[0].get("name")
                    top_emo_intensity = sorted_for_snap[0].get("intensity", 0)

            # Build active_emotions map for history chart (all emotions, not just top)
            emotions_map: dict[str, float] = {}
            for emo in state.active_emotions or []:
                name = emo.get("name")
                intensity = emo.get("intensity", 0)
                if name and intensity >= 0.05:
                    emotions_map[name] = round(intensity, 2)

            snapshot = PsycheHistory(
                user_id=user_id,
                snapshot_type=SNAPSHOT_TYPE_MESSAGE,
                mood_pleasure=state.mood_pleasure,
                mood_arousal=state.mood_arousal,
                mood_dominance=state.mood_dominance,
                dominant_emotion=top_emo_name,
                relationship_stage=state.relationship_stage,
                trait_snapshot={
                    "emotion_intensity": round(top_emo_intensity, 2),
                    "active_emotions": emotions_map,
                    "relationship_depth": round(state.relationship_depth, 3),
                    "relationship_warmth": round(state.relationship_warmth_active, 3),
                    "relationship_trust": round(state.relationship_trust, 3),
                    "drive_curiosity": round(state.drive_curiosity, 3),
                    "drive_engagement": round(state.drive_engagement, 3),
                    "resonance": round(
                        state.last_appraisal.get("resonance", 0.0) if state.last_appraisal else 0.0,
                        3,
                    ),
                },
            )
            await self.repo.create_snapshot(snapshot)

        # Build summary
        profile = PsycheEngine.compile_expression_profile(
            mood_p=state.mood_pleasure,
            mood_a=state.mood_arousal,
            mood_d=state.mood_dominance,
            emotions=state.active_emotions or [],
            stage=state.relationship_stage,
            warmth=state.relationship_warmth_active,
            drive_curiosity=state.drive_curiosity,
            drive_engagement=state.drive_engagement,
        )

        top_emotion = None
        top_intensity = 0.0
        if state.active_emotions:
            sorted_emos = sorted(
                state.active_emotions, key=lambda e: e.get("intensity", 0), reverse=True
            )
            if sorted_emos:
                top_emotion = sorted_emos[0].get("name")
                top_intensity = sorted_emos[0].get("intensity", 0)

        # Build active_emotions list (top 3 for tooltip)
        top_emotions_list: list[dict] = []
        if state.active_emotions:
            for emo in sorted_emos[:3]:
                emo_name = emo.get("name")
                emo_int = emo.get("intensity", 0)
                if emo_name and emo_int >= 0.05:
                    top_emotions_list.append({"name": emo_name, "intensity": round(emo_int, 2)})

        return PsycheStateSummary(
            mood_label=profile.mood_label,
            mood_color=PsycheEngine.mood_to_color(profile.mood_label),
            mood_pleasure=round(state.mood_pleasure, 3),
            mood_arousal=round(state.mood_arousal, 3),
            mood_dominance=round(state.mood_dominance, 3),
            active_emotion=top_emotion,
            emotion_intensity=round(top_intensity, 2),
            relationship_stage=state.relationship_stage,
            mood_intensity=profile.mood_intensity,
            active_emotions=top_emotions_list,
            drive_curiosity=round(state.drive_curiosity, 2),
            drive_engagement=round(state.drive_engagement, 2),
        )

    # =========================================================================
    # LLM Summary
    # =========================================================================

    async def generate_summary(self, user_id: UUID, user_language: str) -> str:
        """Generate a natural language summary of the current psyche state via LLM.

        Calls a lightweight LLM to produce 2-3 sentences describing the mood,
        dominant emotion, and relationship stage in the user's language.

        Args:
            user_id: User UUID.
            user_language: ISO language code (e.g., 'fr', 'en').

        Returns:
            LLM-generated summary string, or template fallback on error.
        """
        from uuid import uuid4

        from langchain_core.messages import HumanMessage, SystemMessage

        from src.core.i18n_types import get_language_name
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.infrastructure.llm import get_llm
        from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

        state = await self.get_or_create_state(user_id)

        # Compile expression profile for mood label
        profile = PsycheEngine.compile_expression_profile(
            mood_p=state.mood_pleasure,
            mood_a=state.mood_arousal,
            mood_d=state.mood_dominance,
            emotions=state.active_emotions or [],
            stage=state.relationship_stage,
            warmth=state.relationship_warmth_active,
            drive_curiosity=state.drive_curiosity,
            drive_engagement=state.drive_engagement,
        )

        # Load personality name
        personality_name = await self._load_personality_name(user_id)

        # Format emotions text
        emotions_text = ", ".join(
            f"{e.get('name', '?')} ({e.get('intensity', 0):.0%})"
            for e in (state.active_emotions or [])
        )

        # Load and format prompt
        prompt_template = load_prompt("psyche_summary_prompt")
        prompt = prompt_template.format(
            user_language=get_language_name(user_language),
            personality_name=personality_name,
            mood_label=profile.mood_label,
            mood_p=f"{state.mood_pleasure:+.2f}",
            mood_a=f"{state.mood_arousal:+.2f}",
            mood_d=f"{state.mood_dominance:+.2f}",
            emotions_text=emotions_text or "none",
            stage=state.relationship_stage,
            depth=f"{state.relationship_depth * 100:.0f}",
            warmth=f"{state.relationship_warmth_active * 100:.0f}",
            trust=f"{state.relationship_trust * 100:.0f}",
            interaction_count=state.relationship_interaction_count,
        )

        llm = get_llm("psyche_summary")
        try:
            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="psyche_summary",
                messages=[
                    SystemMessage(content=prompt),
                    HumanMessage(content="Generate the summary."),
                ],
                session_id=f"psyche_summary_{uuid4().hex[:8]}",
                user_id=str(user_id),
            )
            summary = result.content if isinstance(result.content, str) else str(result.content)

            # Track token usage for user billing
            try:
                tokens_in = 0
                tokens_out = 0
                tokens_cache = 0
                model_name: str | None = None
                usage = getattr(result, "usage_metadata", None)
                if isinstance(usage, dict):
                    tokens_in = int(usage.get("input_tokens", 0))
                    tokens_out = int(usage.get("output_tokens", 0))
                    tokens_cache = int(usage.get("cache_read_input_tokens", 0))
                model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None)

                if tokens_in > 0 or tokens_out > 0:
                    from src.infrastructure.proactive.tracking import (
                        track_proactive_tokens,
                    )

                    await track_proactive_tokens(
                        user_id=user_id,
                        task_type="psyche_summary",
                        target_id=str(user_id),
                        conversation_id=None,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        tokens_cache=tokens_cache,
                        model_name=str(model_name) if model_name else None,
                        db=self.db,
                    )
            except Exception as track_err:
                logger.debug(
                    "psyche_summary_token_tracking_failed",
                    error=str(track_err),
                )

            logger.info(
                "psyche_summary_generated",
                user_id=str(user_id),
                summary_length=len(summary),
            )
            return summary
        except Exception as e:
            logger.warning(
                "psyche_summary_generation_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            # Fallback: template-based summary
            return f"Mood: {profile.mood_label}. Emotions: {emotions_text or 'none'}."

    async def _load_personality_name(self, user_id: UUID) -> str:
        """Load the display name of the user's current personality.

        Args:
            user_id: User UUID.

        Returns:
            Personality title string, or 'Default' if none set.
        """
        from src.domains.auth.models import User
        from src.domains.personalities.models import Personality

        result = await self.db.execute(
            select(Personality.code)
            .join(User, User.personality_id == Personality.id)
            .where(User.id == user_id)
        )
        code = result.scalar_one_or_none()
        return code or "Default"

    # =========================================================================
    # Narrative Identity (weekly self-reflection)
    # =========================================================================

    async def generate_and_save_narrative(self, user_id: UUID) -> str | None:
        """Generate and persist a self-narrative via LLM.

        Called weekly by the psyche scheduler. The narrative is a brief
        first-person introspection reflecting on the relationship and
        emotional tendencies.

        Args:
            user_id: User UUID.

        Returns:
            Generated narrative text, or None on failure.
        """
        from uuid import uuid4

        from langchain_core.messages import HumanMessage, SystemMessage

        from src.core.i18n_types import get_language_name
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.infrastructure.llm import get_llm
        from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

        state = await self.get_or_create_state(user_id)
        personality_name = await self._load_personality_name(user_id)

        # Load user language
        from src.domains.auth.models import User as UserModel

        user_result = await self.db.execute(
            select(UserModel.language).where(UserModel.id == user_id)
        )
        user_language = user_result.scalar_one_or_none() or "fr"

        # Compile profile for mood label
        profile = PsycheEngine.compile_expression_profile(
            mood_p=state.mood_pleasure,
            mood_a=state.mood_arousal,
            mood_d=state.mood_dominance,
            emotions=state.active_emotions or [],
            stage=state.relationship_stage,
            warmth=state.relationship_warmth_active,
            drive_curiosity=state.drive_curiosity,
            drive_engagement=state.drive_engagement,
            self_efficacy=state.self_efficacy,
        )

        strengths = ", ".join(profile.confidence_strengths) or "none yet"
        weaknesses = ", ".join(profile.confidence_weaknesses) or "none"

        prompt_template = load_prompt("psyche_narrative_prompt")
        prompt = prompt_template.format(
            user_language=get_language_name(user_language),
            personality_name=personality_name,
            mood_label=profile.mood_label,
            stage=state.relationship_stage,
            depth=f"{state.relationship_depth * 100:.0f}",
            warmth=f"{state.relationship_warmth_active * 100:.0f}",
            trust=f"{state.relationship_trust * 100:.0f}",
            interaction_count=state.relationship_interaction_count,
            strengths=strengths,
            weaknesses=weaknesses,
        )

        llm = get_llm("psyche_summary")  # Reuse same LLM config
        try:
            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="psyche_summary",
                messages=[
                    SystemMessage(content=prompt),
                    HumanMessage(content="Write the self-narrative."),
                ],
                session_id=f"psyche_narrative_{uuid4().hex[:8]}",
                user_id=str(user_id),
            )
            narrative = result.content if isinstance(result.content, str) else str(result.content)

            state.narrative_identity = narrative
            await self.repo.update(state)

            logger.info(
                "psyche_narrative_generated",
                user_id=str(user_id),
                narrative_length=len(narrative),
            )
            return narrative

        except Exception as e:
            logger.warning(
                "psyche_narrative_generation_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    # =========================================================================
    # Reset
    # =========================================================================

    async def reset_state(self, user_id: UUID, level: str) -> None:
        """Reset psyche state at specified level.

        Args:
            user_id: User UUID.
            level: Reset level (soft/full/purge). Validated by Pydantic Literal
                in PsycheResetRequest — no invalid values reach this method.
        """
        if level == RESET_LEVEL_PURGE:
            await self.repo.delete_for_user(user_id)
            await self._invalidate_cache(user_id)
            logger.info("psyche_state_purged", user_id=str(user_id))
            return

        state = await self.repo.get_by_user_id(user_id)
        if not state:
            logger.info("psyche_reset_skipped_no_state", user_id=str(user_id), level=level)
            return

        # Compute baseline for mood reset
        traits, pad_override = await self._load_personality_traits_and_override(user_id)
        baseline = PsycheEngine.compute_pad_baseline(traits, pad_override)

        if level in (RESET_LEVEL_SOFT, RESET_LEVEL_FULL):
            # Reset mood to baseline
            state.mood_pleasure = baseline.pleasure
            state.mood_arousal = baseline.arousal
            state.mood_dominance = baseline.dominance
            state.mood_quadrant_since = datetime.now(UTC)
            state.active_emotions = []
            state.last_appraisal = None
            state.drive_curiosity = 0.5
            state.drive_engagement = 0.5

        if level == RESET_LEVEL_FULL:
            # Also reset relationship and self-efficacy
            state.relationship_stage = RELATIONSHIP_STAGES[0]
            state.relationship_depth = 0.0
            state.relationship_warmth_active = 0.5
            state.relationship_trust = 0.3
            state.relationship_interaction_count = 0
            state.relationship_total_duration_minutes = 0.0
            state.self_efficacy = PsycheEngine.initialize_self_efficacy()
            state.narrative_identity = None

        await self.repo.update(state)
        await self._save_to_cache(user_id, state)

        # Record a reset snapshot so the history chart can show a visual marker
        from src.domains.psyche.constants import (
            SNAPSHOT_TYPE_RESET_FULL,
            SNAPSHOT_TYPE_RESET_SOFT,
        )

        reset_snapshot_type = (
            SNAPSHOT_TYPE_RESET_FULL if level == RESET_LEVEL_FULL else SNAPSHOT_TYPE_RESET_SOFT
        )
        snapshot = PsycheHistory(
            user_id=user_id,
            snapshot_type=reset_snapshot_type,
            mood_pleasure=state.mood_pleasure,
            mood_arousal=state.mood_arousal,
            mood_dominance=state.mood_dominance,
            dominant_emotion=None,
            relationship_stage=state.relationship_stage,
            trait_snapshot=None,
        )
        await self.repo.create_snapshot(snapshot)

        logger.info("psyche_state_reset", user_id=str(user_id), level=level)

    # =========================================================================
    # History
    # =========================================================================

    async def get_history(
        self,
        user_id: UUID,
        limit: int = 100,
        snapshot_type: str | None = None,
        hours: int | None = None,
    ) -> list[PsycheHistory]:
        """Get psyche history snapshots for a user.

        Args:
            user_id: User UUID.
            limit: Maximum number of snapshots to return.
            snapshot_type: Optional filter by snapshot type.
            hours: Optional time range filter (last N hours).

        Returns:
            List of PsycheHistory, ordered by created_at descending.
        """
        return await self.repo.get_history(
            user_id=user_id,
            limit=limit,
            snapshot_type=snapshot_type,
            hours=hours,
        )

    # =========================================================================
    # GDPR
    # =========================================================================

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete all psyche data for a user (GDPR).

        Args:
            user_id: User UUID.

        Returns:
            Total records deleted.
        """
        count = await self.repo.delete_for_user(user_id)
        await self._invalidate_cache(user_id)
        return count

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _load_personality_traits(self, user_id: UUID) -> PersonalityTraits:
        """Load Big Five traits from user's current personality.

        Args:
            user_id: User UUID.

        Returns:
            PersonalityTraits (defaults to 0.5 if personality has no traits).
        """
        traits, _ = await self._load_personality_traits_and_override(user_id)
        return traits

    async def _load_personality_traits_and_override(
        self, user_id: UUID
    ) -> tuple[PersonalityTraits, PADOverride | None]:
        """Load Big Five traits and PAD override from user's personality.

        Args:
            user_id: User UUID.

        Returns:
            Tuple of (PersonalityTraits, PADOverride or None).
        """
        from src.domains.auth.models import User
        from src.domains.personalities.models import Personality

        result = await self.db.execute(
            select(Personality)
            .join(User, User.personality_id == Personality.id)
            .where(User.id == user_id)
        )
        personality = result.scalar_one_or_none()

        if not personality or personality.trait_openness is None:
            return PersonalityTraits(), None

        traits = PersonalityTraits(
            openness=personality.trait_openness or 0.5,
            conscientiousness=personality.trait_conscientiousness or 0.5,
            extraversion=personality.trait_extraversion or 0.5,
            agreeableness=personality.trait_agreeableness or 0.5,
            neuroticism=personality.trait_neuroticism or 0.5,
        )

        pad_override = None
        if any(
            [
                personality.pad_pleasure_override is not None,
                personality.pad_arousal_override is not None,
                personality.pad_dominance_override is not None,
            ]
        ):
            pad_override = PADOverride(
                pleasure=personality.pad_pleasure_override,
                arousal=personality.pad_arousal_override,
                dominance=personality.pad_dominance_override,
            )

        return traits, pad_override

    async def _load_user_psyche_prefs(self, user_id: UUID) -> tuple[int, int]:
        """Load user psyche sensitivity and stability preferences.

        Args:
            user_id: User UUID.

        Returns:
            Tuple of (sensitivity, stability) integers [0, 100].
        """
        from src.domains.auth.models import User

        result = await self.db.execute(
            select(User.psyche_sensitivity, User.psyche_stability).where(User.id == user_id)
        )
        row = result.one_or_none()
        if row:
            return (row[0] or 70, row[1] or 60)
        return (70, 60)

    async def _load_from_cache(self, user_id: UUID) -> PsycheState | None:
        """Load psyche state from Redis cache.

        Args:
            user_id: User UUID.

        Returns:
            PsycheState or None if cache miss or Redis unavailable.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache as get_redis

            redis = await get_redis()
            if not redis:
                return None

            key = f"{REDIS_KEY_PSYCHE_STATE_PREFIX}{user_id}"
            data = await redis.get(key)
            if not data:
                return None

            # Cache stores the DB record ID, not full object — just use as "exists" check
            # Full object caching would require serialization/deserialization of SQLAlchemy model
            # For v1, cache is a simple existence check that saves the DB query
            # TODO: Implement full JSON serialization for cache in v2
            return None  # v1: always read from DB, cache only for TTL tracking
        except Exception:
            return None

    async def _save_to_cache(self, user_id: UUID, state: PsycheState) -> None:
        """Save psyche state to Redis cache.

        Args:
            user_id: User UUID.
            state: PsycheState to cache.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache as get_redis

            redis = await get_redis()
            if not redis:
                return

            key = f"{REDIS_KEY_PSYCHE_STATE_PREFIX}{user_id}"
            # v1: Store minimal marker (existence + updated_at)
            # Full serialization deferred to v2
            await redis.set(
                key,
                state.updated_at.isoformat() if state.updated_at else "init",
                ex=settings.psyche_cache_ttl_seconds,
            )
        except Exception as e:
            logger.debug("psyche_cache_save_failed", user_id=str(user_id), error=str(e))

    async def _invalidate_cache(self, user_id: UUID) -> None:
        """Invalidate Redis cache for a user's psyche state.

        Args:
            user_id: User UUID.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache as get_redis

            redis = await get_redis()
            if redis:
                key = f"{REDIS_KEY_PSYCHE_STATE_PREFIX}{user_id}"
                await redis.delete(key)
        except Exception as e:
            logger.debug("psyche_cache_invalidate_failed", user_id=str(user_id), error=str(e))


# =============================================================================
# Background Task (fire-and-forget entry point)
# =============================================================================


async def psyche_post_response_background(
    user_id: str,
    appraisal: PsycheAppraisal | None,
    run_id: str,
) -> None:
    """Background task for post-response psyche update.

    Called via safe_fire_and_forget from response_node.
    Stores summary in process-local registry for SSE done metadata.

    Args:
        user_id: User UUID string.
        appraisal: Parsed PsycheAppraisal from response tag (None if absent).
        run_id: Pipeline run_id for summary registry.
    """
    try:
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            service = PsycheService(db)
            summary = await service.process_post_response(
                user_id=UUID(user_id),
                appraisal=appraisal,
            )
            await db.commit()

        # Store summary for pop_psyche_summary(run_id)
        if summary:
            store_psyche_summary(run_id, summary.model_dump())

    except Exception as e:
        logger.warning(
            "psyche_post_response_background_failed",
            user_id=user_id,
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
        )


# =============================================================================
# Utility
# =============================================================================


def _compute_local_hour(utc_now: datetime, timezone_str: str) -> float:
    """Compute local hour from UTC time and timezone string.

    Args:
        utc_now: Current UTC time.
        timezone_str: IANA timezone string.

    Returns:
        Local hour as float [0, 24).
    """
    try:
        tz = zoneinfo.ZoneInfo(timezone_str)
        local_time = utc_now.astimezone(tz)
        return local_time.hour + local_time.minute / 60.0
    except Exception:
        return 12.0  # Default to noon if timezone conversion fails


# =============================================================================
# Centralized Psyche Prompt Block (for secondary generation points)
# =============================================================================


async def build_psyche_prompt_block(
    user_id: str | UUID,
    user_timezone: str | None = None,
) -> str:
    """Build compact psyche context block for secondary generation points.

    Standalone async function with its own DB session. Used by heartbeat,
    interest notifications, reminders, emails, voice, sub-agents, etc.
    The main response pipeline (response_node.py) uses PsycheService.process_pre_response()
    directly instead — do NOT use this helper for the main response.

    Applies decay + circadian READ-ONLY (no persist) to avoid double-decay
    if the user sends a message shortly after.

    Args:
        user_id: User UUID (str or UUID).
        user_timezone: IANA timezone. If None, loaded from User record.
            Falls back to "UTC" (circadian=0 at noon = safe default).

    Returns:
        Formatted psyche context string wrapped in <PsycheContext> tags,
        or "" if psyche is disabled or on any failure.
    """
    if not settings.psyche_enabled:
        return ""

    try:
        from src.infrastructure.database.session import get_db_context

        uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id

        async with get_db_context() as db:
            # Check user preferences
            from src.domains.auth.models import User

            result = await db.execute(
                select(User.psyche_enabled, User.timezone).where(User.id == uid)
            )
            row = result.one_or_none()
            if not row or not row[0]:  # psyche_enabled = False
                return ""

            timezone = user_timezone or row[1] or "UTC"

            # Load psyche state (read-only — do NOT persist)
            service = PsycheService(db)
            state = await service.get_or_create_state(uid)
            traits, pad_override = await service._load_personality_traits_and_override(uid)
            baseline = PsycheEngine.compute_pad_baseline(traits, pad_override)

            # Apply temporal decay in memory (read-only)
            now = datetime.now(UTC)
            hours_elapsed = 0.0
            if state.updated_at:
                hours_elapsed = max(0.0, (now - state.updated_at).total_seconds() / 3600.0)

            _, user_stability = await service._load_user_psyche_prefs(uid)
            stability_factor = max(0.3, 2.0 - (user_stability / 50.0))
            effective_decay_rate = settings.psyche_mood_decay_rate * stability_factor

            mood_p, mood_a, mood_d, emotions, _ = PsycheEngine.apply_temporal_decay(
                mood_p=state.mood_pleasure,
                mood_a=state.mood_arousal,
                mood_d=state.mood_dominance,
                baseline=baseline,
                hours_elapsed=hours_elapsed,
                decay_rate=effective_decay_rate,
                emotions=state.active_emotions or [],
                emotion_decay_rate=settings.psyche_emotion_decay_rate,
                warmth=state.relationship_warmth_active,
                warmth_decay_rate=settings.psyche_relationship_warmth_decay_rate,
                has_interaction=False,
                traits=traits,
            )

            # Apply circadian
            local_hour = _compute_local_hour(now, timezone)
            mood_p = PsycheEngine.apply_circadian(
                mood_p, local_hour, settings.psyche_circadian_amplitude
            )

            # Compile compact profile
            profile = PsycheEngine.compile_expression_profile(
                mood_p=mood_p,
                mood_a=mood_a,
                mood_d=mood_d,
                emotions=emotions,
                stage=state.relationship_stage,
                warmth=state.relationship_warmth_active,
                drive_curiosity=state.drive_curiosity,
                drive_engagement=state.drive_engagement,
            )

            compact = PsycheEngine.format_prompt_injection(profile)

            # Build mood-specific directive for compact context
            from src.domains.psyche.constants import (
                MOOD_BEHAVIORAL_DIRECTIVES,
                RELATIONSHIP_STAGE_DIRECTIVES,
            )

            mood_dir = MOOD_BEHAVIORAL_DIRECTIVES.get(profile.mood_label, "")
            rel_dir = RELATIONSHIP_STAGE_DIRECTIVES.get(profile.relationship_stage, "")
            intensity_hint = (
                "strongly"
                if profile.mood_intensity == "strongly"
                else "noticeably" if profile.mood_intensity == "noticeably" else "subtly"
            )

            return (
                f"<PsycheContext>\n{compact}\n"
                f"You have an inner life. Inhabit this state {intensity_hint}:\n"
                f"- MOOD ({profile.mood_label}): {mood_dir}\n"
                f"- RELATIONSHIP ({profile.relationship_stage}): {rel_dir}\n"
                "- EMOTIONS: let each named emotion color specific moments. "
                "Higher intensity = more visible in tone and word choice.\n"
                "- NEVER say 'I feel X'. Express through word choice, rhythm, energy. "
                "Never guilt-trip or express disappointment about user behavior.\n"
                "- NEVER attribute your emotions or mood to the user. These are YOUR internal "
                "states — express them through your own tone and style, never by describing "
                "the user's feelings or state of mind.\n"
                "</PsycheContext>"
            )

    except Exception as e:
        logger.debug(
            "build_psyche_prompt_block_failed",
            user_id=str(user_id),
            error=str(e),
        )
        return ""
