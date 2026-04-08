# ADR-068: Psyche Engine — Dynamic Psychological State for the AI Assistant

## Status

Accepted

## Date

2026-04-01

## Context

LIA's assistant personality was static: a prompt text (`Personality.prompt_instruction`) injected into the system prompt. The emotional awareness was limited to 3 states (COMFORT/DANGER/NEUTRAL) derived from memory `emotional_weight` values. There was no dynamic mood, no evolving relationship, no contextual emotional response.

Users interacting frequently with the assistant experienced a flat, repetitive persona that didn't adapt to the emotional tone of conversations or evolve over time.

## Decision

### Multi-Layered Psyche Architecture (ALMA-inspired)

Implement a 5-layer psychological state engine based on established affective computing models:

```
Layer 1 — Personality (permanent): Big Five traits → PAD baseline
Layer 2 — Mood (hours): PAD space with temporal decay toward baseline
Layer 3 — Emotions (minutes): 22 discrete emotions with exponential decay
Layer 4 — Relationship (weeks): 4-stage depth/warmth tracking
Layer 5 — Drives (session): Curiosity and engagement
```

### Key Design Choices

1. **Big Five traits per personality**: Each of the 14 personalities receives OCEAN scores + optional PAD overrides for caricature personalities where linear Mehrabian mapping produces unrealistic results (e.g., Trump, Teenager, Depressed).

2. **PAD mood space (Pleasure-Arousal-Dominance)**: Continuous 3D representation preferred over discrete states. Enables smooth transitions, mathematical operations (decay, push, contagion), and mood-congruent memory recall.

3. **Self-report appraisal**: The response LLM produces a `<psyche_eval/>` XML tag at the end of each response with its self-assessment (valence, emotion, quality). This tag is stripped before display. No additional LLM call needed — cost: ~25 output tokens.

4. **Independent feature flag**: `PSYCHE_ENABLED` (system) + `user.psyche_enabled` (per-user). Both must be true. Disabled by default. The existing EmotionalState (COMFORT/DANGER/NEUTRAL) coexists unchanged.

5. **Pure computation engine**: All mood/emotion dynamics are mathematical operations in a stateless `PsycheEngine` class (no DB, no LLM, no async). Fully unit-testable. ~155 tests covering all methods.

6. **Relationship never regresses**: Stages (ORIENTATION → EXPLORATORY → AFFECTIVE → STABLE) are one-way. Absence decays `warmth_active` but depth and stage persist.

### Cost Analysis

- **Input**: +65 tokens/message (prompt instruction + compact XML tag)
- **Output**: +25 tokens/message (self-report tag, stripped)
- **Latency**: +2ms blocking (DB read + math), 0ms for fire-and-forget post-response
- **Storage**: 1 row per user in `psyche_states`, snapshots in `psyche_history`

## Consequences

### Positive

- Assistant develops a perceptible, evolving personality that adapts to each user
- Emotional state influences tone, vocabulary, and energy without explicit mention
- Mood-congruent memory recall creates organic behavioral coherence
- Rupture-repair mechanism strengthens trust through resolved conflicts
- Colorblind-safe mood ring provides visual feedback in the UI

### Negative

- Additional complexity in the response pipeline (4 insertion points in response_node)
- ~$0.58/month/active user in token costs
- Redis cache is stub in v1 (DB query on every pre-response)

### Risks

- Uncanny valley: emotions must influence style, never content or guilt-tripping
- Tag visibility: brief flash during streaming mitigated by streaming filter + content_replacement

## References

- ALMA (Gebhard, 2005): A Layered Model of Affect
- OCC (Ortony, Clore & Collins, 1988): Cognitive appraisal theory
- Mehrabian (1996): Big Five → PAD mapping
- WASABI (Becker-Asano, 2008): Mass-spring mood dynamics
- Self-Determination Theory (Deci & Ryan): Autonomy, Competence, Relatedness

## Files

- Domain: `apps/api/src/domains/psyche/`
- Engine: `apps/api/src/domains/psyche/engine.py`
- Migration: `apps/api/alembic/versions/2026_04_01_0001-add_psyche_engine.py`
- Prompt: `apps/api/src/domains/agents/prompts/v1/psyche_self_report_instruction.txt`
- Frontend: `apps/web/src/components/psyche/`, `apps/web/src/stores/psycheStore.ts`
- Tests: `apps/api/tests/unit/domains/psyche/test_engine.py` (~155 unit tests)

## v2 Evolution (2026-04-08)

Eight enhancements were added to the Psyche Engine without changing the core architecture:

1. **Expanded emotion palette** (16 -> 22): Added playfulness, protectiveness, relief, nervousness, wonder, resolve
2. **Graduated directives**: Behavioral directives now scale with emotion intensity instead of binary on/off
3. **Serenity floor**: Minimum serenity baseline prevents prolonged negativity drift
4. **Emotional anchor**: Persistent personality-based emotion provides continuity across sessions
5. **Narrative transitions**: Richer `EVOLUTION:` blocks with direction and tonal adaptation cues
6. **Multi-emotion self-report**: `<psyche_eval/>` now supports up to 3 emotions per message
7. **Computed resonance**: New metric (0-1) quantifying emotional alignment with user valence, dynamically modulating contagion
8. **Proactive emotions**: Engine can generate anticipatory emotions (e.g., before scheduled events) rather than only reacting

Test coverage grew from 51 to ~155 tests.
