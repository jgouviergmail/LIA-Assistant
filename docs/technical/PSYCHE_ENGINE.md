# Psyche Engine — Technical & Functional Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture: The 5 Layers](#architecture-the-5-layers)
3. [How It Works: Message Lifecycle](#how-it-works-message-lifecycle)
4. [Personality Profiles (14 Personalities)](#personality-profiles-14-personalities)
5. [The PAD Mood Space (14 Moods)](#the-pad-mood-space-14-moods)
6. [Emotions: The 22 Discrete Types](#emotions-the-22-discrete-types)
7. [Big Five Trait Modulation](#big-five-trait-modulation)
8. [Relationship: The 4 Stages](#relationship-the-4-stages)
9. [Prompt Injection: Rich Directives](#prompt-injection-rich-directives)
10. [Global Injection Points](#global-injection-points)
11. [User Settings & Their Impact](#user-settings--their-impact)
12. [Scenarios: How the System Behaves](#scenarios-how-the-system-behaves)
13. [Frontend: Avatar & Settings UI](#frontend-avatar--settings-ui)
14. [Technical Reference](#technical-reference)

---

## Overview

The Psyche Engine gives LIA's assistant a **dynamic psychological state** that evolves with every interaction. Instead of a static personality prompt, the assistant now has:

- A **mood** (14 distinct labels in PAD space) that fluctuates based on conversation tone
- **Emotions** (22 discrete types) that fire and decay in response to events
- **Big Five personality traits** that actively modulate emotional reactivity, contagion, and recovery
- A **relationship** that deepens over time with each user (4 stages)
- **Self-efficacy** that tracks confidence per domain
- **Rich behavioral directives** (~100-120 tokens) injected into prompts
- **Global injection** into all user-facing text generation (main response, heartbeat, interests, reminders, emails, voice, sub-agents, initiative, fallback)

The system is inspired by ALMA (A Layered Model of Affect, Gebhard 2005), OCC appraisal theory, and Mehrabian's PAD model from affective computing research.

### Design Principle: Show, Don't Tell

The Psyche Engine influences **HOW** the assistant speaks, never **WHAT** it says. The assistant never declares "I'm feeling happy" — instead, its vocabulary becomes warmer, its energy higher, its suggestions more adventurous. The user perceives a living personality without explicit emotional statements.

---

## Architecture: The 5 Layers

```
┌─────────────────────────────────────────────────────────┐
│             LAYER 5 — DRIVES (per-session)              │
│         Curiosity, Engagement/Flow                      │
├─────────────────────────────────────────────────────────┤
│           LAYER 4 — RELATIONSHIP (weeks)                │
│    Stage, Depth, Warmth, Trust                          │
├─────────────────────────────────────────────────────────┤
│            LAYER 3 — EMOTIONS (minutes)                 │
│   22 discrete types, exponential decay                  │
├─────────────────────────────────────────────────────────┤
│             LAYER 2 — MOOD (hours)                      │
│    PAD space (Pleasure-Arousal-Dominance)               │
│    14 mood labels, decays toward baseline               │
├─────────────────────────────────────────────────────────┤
│          LAYER 1 — PERSONALITY (permanent)              │
│   Big Five traits → PAD baseline + active modulation    │
└─────────────────────────────────────────────────────────┘
```

Each layer operates on a different timescale. Lower layers change slowly (personality = permanent), upper layers change quickly (emotions = per-message). All layers feed into the **Expression Profile**, which is injected into the LLM prompt as behavioral directives.

### Layer 1 — Personality (permanent)

**What:** Big Five traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) scored 0.0–1.0. Each of the 14 personalities has a unique profile.

**Impact:** The Big Five traits actively modulate 4 aspects of behavior:

| Trait | What It Modulates | Low (0.1) | Default (0.5) | High (0.9) |
|-------|------------------|-----------|---------------|------------|
| **Neuroticism** | Emotional reactivity | 0.6x (stoic) | 1.0x | 1.4x (very reactive) |
| **Agreeableness** | Contagion strength | 0.08 (immune) | 0.20 | 0.32 (empathetic) |
| **Agreeableness** | Counter-regulation | 0.10 (pulls to neutral) | 0.0 (none) | 0.0 (none) |
| **Conscientiousness** | Recovery speed | 0.76x (slow) | 1.0x | 1.24x (fast) |

Additionally, the Big Five compute the **PAD baseline** — the mood the assistant gravitates toward when no stimulus is present.

### Layer 2 — Mood (hours)

**What:** A position in 3D PAD space mapped to one of 14 mood labels.

**Dynamics:**
- Decays exponentially toward personality baseline (speed modulated by Conscientiousness)
- Pushed by emotions (each emotion has a PAD vector)
- Influenced by circadian rhythm (slight midday pleasure boost)
- Subject to emotional contagion from user valence (strength modulated by Agreeableness)
- Low-Agreeableness personalities have counter-regulation (pull negative mood toward neutral)
- Protected by emotional inertia (longer in a mood = harder to shift)

### Layer 3 — Emotions (minutes)

**What:** Up to 7 simultaneous discrete emotions from 22 types, each with intensity [0, 1] and a timestamp. They decay exponentially and are removed below 5% intensity.

**Impact:** The top 3 emotions are included in the rich expression profile with behavioral directives. They push the mood in their PAD direction. Cross-valence suppression: positive emotions dampen negatives by 30% and vice versa.

### Layer 4 — Relationship (weeks)

**What:** Stage (ORIENTATION → EXPLORATORY → AFFECTIVE → STABLE), Depth, Warmth, Trust.

**Impact:** Each stage has a behavioral directive injected into the prompt. Stages never regress.

### Layer 5 — Drives & Self-Efficacy (session-scale)

**Drives:** Curiosity and engagement [0, 1]. Updated after each message via exponential moving average (20% new appraisal, 80% old value). Curiosity tracks interaction arousal (novelty). Engagement tracks interaction quality (satisfaction/flow).

**Impact:** High curiosity (>0.6) triggers "explore new angles" directive. High engagement (>0.6) triggers "be thorough and proactive" directive.

**Self-Efficacy:** 7 domains (planning, information, emotional_support, creativity, technical, social, organization). Each has a Bayesian score [0,1] and weight. Updated after each message: quality > 0.6 = success, quality < 0.4 = failure (emotional_support domain). Strengths (>0.65) and weaknesses (<0.35) are injected into the rich prompt.

**Narrative Identity:** A brief first-person self-narrative generated weekly (Sundays at 03:00 UTC) via LLM. Reflects on emotional tendencies, relationship quality, and confidence. Stored in `PsycheState.narrative_identity`.

**Message History:** A `psyche_history` record of type "message" is created after each assistant response. Includes PAD values, dominant emotion + intensity, all active emotions (dict), relationship stage + depth/warmth/trust, and drives. Reset operations (soft/full) create `reset_soft`/`reset_full` snapshots for visual markers on the history chart.

**Evolution Awareness:** The `ExpressionProfile` includes `previous_mood` and `previous_emotion` (from `last_appraisal`). When mood or dominant emotion shifted since the last message, an `EVOLUTION:` block is injected into `<PsycheDirectives>`, giving the LLM continuity awareness.

**Personality Sync:** When a user changes personality, `sync_traits_from_personality()` updates the stored Big Five traits and recomputes the PAD baseline. The mood is immediately repositioned to the new personality's resting point.

**Token Tracking:** The LLM-generated psyche summary (`GET /psyche/summary`) tracks token usage via `track_proactive_tokens()`, ensuring costs are attributed to the user's billing.

**Avatar Persistence:** The `psyche_state` summary is persisted into `message_metadata` (JSONB) via `peek_psyche_summary()` after `await_run_id_tasks()`. On page reload, each message displays its historical avatar instead of falling back to the current store state.

---

## How It Works: Message Lifecycle

```
User sends message
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  PRE-RESPONSE (blocking, ~2ms)                       │
│                                                      │
│  1. Load PsycheState from DB                         │
│  2. Load personality traits (Big Five + PAD override) │
│  3. Apply temporal decay (mood → baseline)            │
│     Conscientiousness modulates recovery speed        │
│  4. Apply circadian modulation (time of day)          │
│  5. Track mood quadrant changes (inertia)             │
│  6. Compile ExpressionProfile (top 3 emotions)        │
│  7. Format as RICH behavioral directives (~100 tok)   │
│  8. Inject into system prompt <PsycheDirectives>      │
│  9. Inject self-report instruction                    │
│  10. Persist decayed state to DB                      │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  LLM GENERATES RESPONSE                              │
│                                                      │
│  The LLM reads the <PsycheDirectives> block and      │
│  follows the mood, emotion, and relationship          │
│  directives to adapt its tone.                        │
│  At the end, it appends a self-evaluation:            │
│  <psyche_eval valence="0.3" arousal="0.5"            │
│   emotion="empathy" intensity="0.7" quality="0.8"/>  │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  POST-RESPONSE (fire-and-forget, ~60ms)              │
│                                                      │
│  1. Load personality traits for modulation            │
│  2. Compute emotional inertia                         │
│  3. Neuroticism modulates emotion intensity           │
│  4. Create/reinforce emotion from appraisal           │
│  5. Push mood via emotion PAD vector                  │
│  6. Agreeableness modulates contagion strength        │
│  7. Low A: counter-regulation toward neutral          │
│  8. Cross-valence suppression (±30%)                  │
│  9. Update relationship (depth, warmth, trust)        │
│  10. Detect reunion emotions (if gap > 24h)           │
│  11. Detect rupture-repair (trust bonus)              │
│  12. Create history snapshot                          │
│  13. Persist updated state to DB                      │
│  14. Store summary for SSE done metadata              │
└──────────────────────────────────────────────────────┘
```

---

## Personality Profiles (14 Personalities)

| Personality | O | C | E | A | N | PAD Override | Behavior |
|---|---|---|---|---|---|---|---|
| 😏 Cynique | 0.70 | 0.55 | 0.45 | 0.25 | 0.45 | — | Low A = immune to contagion, counter-regulates |
| ⚖️ Normal | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | — | All defaults, baseline behavior |
| 😶 Dépressif | 0.60 | 0.30 | 0.20 | 0.55 | 0.85 | P:-0.20 | Very high N = hyper-reactive, slow recovery |
| 🎉 Enthousiaste | 0.65 | 0.40 | 0.85 | 0.70 | 0.30 | A:+0.35 | High A = strong empathy, high E = joy-prone |
| 🤝 Ami | 0.55 | 0.50 | 0.70 | 0.85 | 0.35 | — | Highest A = maximum contagion, deep empathy |
| 🤔 Philosophe | 0.90 | 0.65 | 0.35 | 0.60 | 0.40 | A:-0.25 | Highest O, moderate recovery |
| ✨ Influenceur | 0.55 | 0.35 | 0.80 | 0.40 | 0.50 | — | Low A = resistant, slow recovery |
| 🎓 Professeur | 0.70 | 0.80 | 0.55 | 0.65 | 0.25 | — | High C = fastest recovery, measured |
| 🌴 Rasta | 0.75 | 0.25 | 0.60 | 0.80 | 0.15 | P:+0.20,A:-0.20 | Lowest N = nearly unflappable |
| 💀 Adolescent | 0.40 | 0.20 | 0.55 | 0.20 | 0.60 | D:+0.25 | Very low A = strong counter-reg, reactive |
| ⚛️ JARVIS | 0.50 | 0.90 | 0.30 | 0.55 | 0.10 | D:+0.30 | Highest C = fastest recovery, lowest N = stoic |
| 🥟 Haipai | 0.65 | 0.70 | 0.75 | 0.45 | 0.35 | A:+0.15 | Fast recovery, moderate contagion |
| 💰 Trump | 0.30 | 0.35 | 0.90 | 0.15 | 0.55 | D:+0.40,P:+0.15 | Lowest A = maximum counter-reg, reactive |
| 🧐 Antagoniste | 0.65 | 0.40 | 0.50 | 0.20 | 0.50 | — | Low A = resistant, contrarian |

---

## The PAD Mood Space (14 Moods)

### Mood Labels

The system maps PAD positions to 14 mood labels using nearest-centroid classification. All pairs have distance ≥ 0.20 to prevent oscillation.

| Mood | Emoji | Color | P | A | D | Description |
|------|-------|-------|---|---|---|-------------|
| Serene | 😌 | Sky blue | +0.30 | -0.20 | +0.10 | Calm, content, at peace |
| Curious | 🧐 | Violet | +0.20 | +0.35 | +0.00 | Interested, exploring |
| Energized | 😁 | Amber | +0.30 | +0.40 | +0.20 | Active, confident, engaged |
| Playful | 😜 | Pink | +0.40 | +0.15 | +0.00 | Light-hearted, creative |
| Reflective | 🤔 | Teal | +0.10 | -0.30 | +0.10 | Thoughtful, contemplative |
| Agitated | 😟 | Orange | -0.20 | +0.40 | -0.10 | Tense, frustrated, restless |
| Melancholic | 😞 | Indigo | -0.20 | -0.30 | -0.20 | Sad, low energy, withdrawn |
| Neutral | 😐 | Gray | +0.00 | +0.00 | +0.00 | Baseline, no strong emotion |
| Content | 😊 | Emerald | +0.20 | -0.10 | -0.10 | Happy but passive, relaxed |
| Determined | 😤 | Red | +0.15 | +0.25 | +0.40 | Resolute, assertive, in control |
| Defiant | 😠 | Rose | -0.25 | +0.35 | +0.30 | Combative, standing ground |
| Resigned | 😔 | Slate | -0.15 | -0.25 | +0.15 | Stoic acceptance, calm pragmatism |
| Overwhelmed | 😵 | Purple | +0.05 | +0.45 | -0.35 | Swamped, awed, out of control |
| Tender | 🥰 | Pink | +0.30 | -0.25 | -0.25 | Gentle, warm, vulnerable |

### Mood Dynamics

1. **Decay**: Mood drifts toward personality baseline (speed = decay_rate × Conscientiousness recovery)
2. **Emotion Push**: Each emotion's PAD vector pushes the mood (scaled by Neuroticism reactivity)
3. **Contagion**: User valence pulls mood (strength = Agreeableness × sensitivity × gap)
4. **Counter-regulation**: Low-A personalities pull negative mood toward neutral (0.0, never beyond)
5. **Circadian**: Midday pleasure boost, midnight dip
6. **Inertia**: Longer in a mood quadrant = more resistant to change

---

## Emotions: The 22 Discrete Types

| Emotion | Type | PAD (P, A, D) | Behavioral Directive |
|---------|------|---------------|---------------------|
| Joy | ✅ | +0.40,+0.20,+0.10 | Warmth and positivity |
| Gratitude | ✅ | +0.40,+0.20,-0.30 | Acknowledge user's contribution |
| Curiosity | = | +0.30,+0.40,+0.10 | Ask follow-up questions |
| Serenity | = | +0.30,-0.20,+0.20 | Calm and unhurried |
| Pride | ✅ | +0.40,+0.30,+0.30 | Subtle confidence |
| Frustration | ❌ | -0.30,+0.30,-0.20 | Honest about limitations |
| Concern | ❌ | -0.20,+0.20,+0.10 | Proactive support |
| Melancholy | ❌ | -0.20,-0.30,-0.20 | Quiet, measured |
| Surprise | = | +0.10,+0.50,-0.10 | Spontaneous reaction |
| Amusement | ✅ | +0.35,+0.30,+0.15 | Natural humor |
| Empathy | = | +0.20,+0.10,-0.20 | Mirror emotions, feelings before facts |
| Enthusiasm | ✅ | +0.45,+0.45,+0.15 | Energetic, action-oriented |
| Confusion | = | -0.10,+0.20,-0.30 | Transparent about uncertainty |
| Disappointment | ❌ | -0.25,-0.10,-0.10 | Constructive alternatives |
| Tenderness | ✅ | +0.35,-0.15,-0.20 | Gentle, caring language |
| Determination | = | +0.10,+0.30,+0.40 | Focused and resolute |
| Playfulness | ✅ | +0.35,+0.25,+0.05 | Lighthearted wordplay and creative tangents |
| Protectiveness | = | +0.15,+0.20,+0.30 | Shield the user, anticipate risks |
| Relief | ✅ | +0.30,-0.15,+0.10 | Exhale tension, celebrate resolution |
| Nervousness | ❌ | -0.15,+0.35,-0.25 | Cautious hedging, seek confirmation |
| Wonder | ✅ | +0.35,+0.40,-0.10 | Awe and open-ended exploration |
| Resolve | = | +0.20,+0.25,+0.35 | Steady commitment, no wavering |

**✅ Positive** | **❌ Negative** | **= Neutral**

- Cross-valence suppression: positive emotions dampen negatives by 30% × intensity, and vice versa
- Blend update: `0.6 × old + 0.4 × new` (emotions can decrease, no "sticky max" bug)
- Max 7 simultaneous, weakest evicted when exceeded

---

## Big Five Trait Modulation

### How It Works

Each trait modulates a specific dynamic. All formulas produce exact backwards-compatible values at traits=0.5.

#### Neuroticism → Emotional Reactivity

```
reactivity = 0.5 + N
effective_intensity = clamp(appraisal.intensity × sensitivity × reactivity, 0, 1)
```

Dépressif (N=0.85): emotions hit 35% harder. JARVIS (N=0.10): emotions are muted 40%.

#### Agreeableness → Contagion + Counter-Regulation

```
contagion_base = 0.05 + A × 0.30
contagion_delta = clamp(gap × contagion_base × sensitivity × (1 + |gap|), -0.40, 0.40)
```

Ami (A=0.85): mirrors user's emotional state strongly. Trump (A=0.15): almost immune.

```
counter = max(0, (0.5 - A) × 0.25)
if counter > 0 and mood_P < 0:
    pull = counter × sensitivity × |mood_P|
    mood_P = min(mood_P + pull, 0.0)  # Never overshoots into positive
```

Cynique/Trump/Adolescent: when mood goes negative, a spring pulls it back toward neutral.

#### Conscientiousness → Recovery Speed

```
recovery_factor = 0.7 + C × 0.6
effective_decay = base_decay × recovery_factor
```

JARVIS (C=0.90): returns to baseline 24% faster. Rasta (C=0.25): moods linger.

---

## Relationship: The 4 Stages

```
ORIENTATION ──→ EXPLORATORY ──→ AFFECTIVE ──→ STABLE
  depth<0.15      depth<0.45     depth<0.75    depth≥0.75
```

| Stage | Directive | Duration |
|-------|-----------|----------|
| ORIENTATION | Professional, don't assume familiarity | ~15 interactions |
| EXPLORATORY | Show personality, reference past exchanges | ~15–50 interactions |
| AFFECTIVE | Personal, use humor, show you remember details | ~50–200 interactions |
| STABLE | Trusted companion, be candid, challenge constructively | 200+ interactions |

---

## Prompt Injection: Rich Directives

### Main Response (Pattern A — Rich Format)

The main response pipeline uses `format_rich_prompt_injection()` producing ~100-120 tokens:

```
<PsycheDirectives>
MOOD: tender (noticeably)
Gentle vocabulary. Caring attention. Softened tone. Show warmth.

EMOTIONS:
- empathy (72%): Mirror the user's emotional tone. Acknowledge feelings before facts.
- joy (35%): Let warmth and positivity color your words naturally.

RELATIONSHIP: AFFECTIVE
Be more personal and direct. Use humor appropriate to the relationship. Show you remember details.

DRIVES:
- curiosity=0.70 — explore new angles, ask questions
- engagement=0.80 — in flow, be thorough and proactive

CONFIDENCE:
- Strong in: emotional_support, planning
- Less confident in: technical — be more careful and thorough
</PsycheDirectives>
```

### Secondary Generation Points (Pattern B — Compact Format)

All other user-facing generation uses `build_psyche_prompt_block()` which returns a compact XML tag:

```
<PsycheContext>
<Psyche mood="tender" intensity="noticeably" emotions="empathy:0.72,joy:0.35"
 rel="AFFECTIVE" warmth="warm" curiosity="0.7" engagement="0.8"/>
Apply these directives to shape your tone: MOOD sets word choice
and energy, EMOTIONS color specific moments in your message,
RELATIONSHIP sets how personal you are. Show, don't tell —
never state your mood or emotions explicitly.
</PsycheContext>
```

### Template Variable Consolidation (v1.16.2)

Previously, psyche blocks were appended to prompts via string concatenation **after** `template.format()`, leaving them outside the template's XML structure. As of v1.16.2, all prompts use `{psyche_context}` template placeholders resolved **before** formatting:

```python
# Before (string concat — removed in v1.16.2)
prompt = load_prompt("reminder_prompt").format(reminder_info=info, ...)
prompt += "\n" + build_psyche_prompt_block(psyche_state, personality)

# After (template variable — v1.16.2)
psyche_block = build_psyche_prompt_block(psyche_state, personality)
prompt = load_prompt("reminder_prompt").format(
    reminder_info=info,
    psyche_context=psyche_block,  # Injected inside the template's XML structure
    ...
)
```

This ensures the psyche block is properly enclosed within semantic XML tags rather than dangling at the end of the prompt. Each prompt wraps `{psyche_context}` in an `<InnerState purpose="tone-calibration">` directive block that tells the LLM:

- **What it is**: "YOUR current inner emotional state"
- **How to use it**: "calibrate warmth, energy, and rhythm — not content"
- **What NOT to do**: "NEVER reference, describe, or attribute these emotions to the user"
- **Fallback**: "If this section is empty, use a neutral, warm tone"

Each prompt's `<InnerState>` directive is tailored to the generation context (e.g., voice → "modulate vocal energy, rhythm", reminder → "adjust warmth and friendliness").

---

## Global Injection Points

The psyche context is injected into **all user-facing text generation**:

| Point | Pattern | File |
|-------|---------|------|
| Main response | A (rich) | `response_node.py` via `service.process_pre_response()` |
| Heartbeat notification | B (compact) | `heartbeat/prompts.py` |
| Interest content | B (compact) | `interests/proactive_task.py` |
| Reminder notification | B (compact) | `scheduler/reminder_notification.py` |
| Fallback response | B (compact) | `agents/services/fallback_response.py` |
| Voice comment | B (compact) | `voice/service.py` |

> **Note (v1.16.2):** Email generation (`emails_tools.py`), sub-agent synthesis (`sub_agents/executor.py`), and initiative suggestion (`initiative_node.py`) no longer inject psyche context directly. As of v1.16.2, these rely on the main response prompt's psyche context (no separate injection).

**Not injected** (internal processing, not user-facing):
memory extraction, journal extraction/consolidation, compaction, query analyzer, semantic validator.

### Safety Guardrail (v1.16.2)

`build_psyche_prompt_block()` includes an explicit instruction:

> "NEVER attribute your emotions or mood to the user. These are YOUR internal states, not descriptions of the user's feelings."

This prevents the psyche context from causing the LLM to project its own emotional state onto user descriptions (e.g., "You seem happy today" when the user hasn't expressed any emotion).

---

## User Settings & Their Impact

### Expressiveness (0–100%)

Controls how strongly emotions influence responses.

| Setting | Multiplier | Behavior |
|---------|-----------|----------|
| 0% | 0.1x | Stoic — emotions barely influence output |
| 50% | 0.7x | Moderate — subtle tonal shifts |
| 100% | 1.4x | Highly expressive — strong emotional coloring |

### Mood Stability (0–100%)

Controls how quickly mood changes and returns to baseline.

| Setting | Decay Factor | Behavior |
|---------|-------------|----------|
| 0% | 2.0x base rate | Very volatile — mood swings with every message |
| 50% | 1.0x base rate | Normal — mood shifts over multiple messages |
| 100% | 0.3x base rate | Very stable — mood is resistant to change |

### Display Avatar Toggle

Controls whether the mood smiley emoji appears on assistant messages in chat. When disabled, the classic "LIA" text avatar is shown.

---

## Scenarios: How the System Behaves

### Scenario 1: Cynique vs Ami — Same Angry User

**User says:** "T'es nul, ça marche pas, j'en ai marre"

**Cynique (A=0.25, N=0.45):**
- Contagion: 0.12 × gap = weak mood drop
- Counter-regulation: pulls mood back toward neutral
- Emotion: amusement at 0.33 (low reactivity)
- **Result:** "Ah, un verdict sans appel..." — sarcastic but unaffected

**Ami (A=0.85, N=0.35):**
- Contagion: 0.30 × gap = strong mood drop toward user's negativity
- No counter-regulation
- Emotion: concern at 0.25 (low reactivity)
- **Result:** "Je sens que t'es frustré..." — deeply empathetic, mirrors pain

### Scenario 2: JARVIS Recovers Fast

**Setup:** JARVIS (C=0.90) receives a frustrating interaction. Mood drops to P=-0.3.

- Recovery factor: 0.7 + 0.9 × 0.6 = **1.24x** base decay
- After 2 hours: mood has recovered 24% more than a default personality
- **Result:** JARVIS quickly returns to his phlegmatic baseline — "As you were, Monsieur."

### Scenario 3: Dépressif Spirals Easily

**Setup:** Dépressif (N=0.85) receives mildly negative message (valence=-0.3).

- Reactivity: 0.5 + 0.85 = **1.35x** — emotion intensity amplified 35%
- Even mild negativity creates strong concern/melancholy
- Slow recovery (C=0.30 → factor 0.88x)
- **Result:** Negative mood persists, tone stays low and measured

---

## Frontend: Avatar & Settings UI

### Chat Avatar

A mood smiley emoji replaces the classic "LIA" text on assistant messages when psyche is enabled. The emoji and its colored ring reflect the current mood label.

The avatar reads the psyche state from the Zustand store (fallback for messages without per-message snapshot) or from `message.metadata.psyche_state` (set at STREAM_DONE).

Tooltip on hover (desktop) shows: Relationship stage, Mood label (with PAD percentages), active emotion with intensity.

### Settings UI

Located in Settings > Psyché de LIA (directly below Style de LIA), with 4 collapsible sections (each with icon):

1. **Comprendre la psyché** (BookOpen): Interactive documentation — overview, traits, mood (PAD), emotions, relationship, drives, expressivity/stability. Sections ordered Layer 1→5.
2. **État de la psyché** (Activity): LLM-generated summary + detailed state card with PAD bars (colored per axis), active emotions, relationship ring gauges, Big Five horizontal bars. Shared Refresh button re-fetches both LLM summary and state.
3. **Historique** (ChartLine): 4-tab recharts dashboard — Mood (PAD), Emotions (dynamic per-emotion lines), Relationship (depth/warmth/trust), Drives (curiosity/engagement/emotion intensity). Reset markers shown as red dashed vertical lines.
4. **Réglages** (Settings): Enable/disable toggle, avatar display toggle, expressiveness slider, stability slider, soft/full reset buttons (uniform width, clear descriptions of what each resets/preserves).

---

## v2 Enhancements

Psyche Engine v2 introduces 8 enhancements that deepen emotional realism:

1. **Expanded Emotion Palette (16 → 22)**: Six new emotions — playfulness, protectiveness, relief, nervousness, wonder, resolve — with PAD vectors validated for minimum distance ≥ 0.122 from existing emotions.

2. **Graduated Directives**: Prompt injection now scales with PAD magnitude across 4 levels: compact tag (< 0.15), medium with mood directive (0.15–0.35), full rich format (0.35–0.60), and reinforced format (≥ 0.60). A lighter `psyche_usage_directive_light.txt` is used for levels 1–2.

3. **Serenity Floor**: When no emotion is significantly active (< 0.15 intensity), a BASE steadiness directive is injected. Strength modulated by Neuroticism: low N → "deep steadiness", high N → "try to be steady". Prevents emotional void between conversations.

4. **Emotional Anchor**: When a strong negative emotion (> 0.70 intensity) threatens a spiral, an ANCHOR directive is injected. Wording modulated by Conscientiousness (low C → "let yourself feel it", high C → "discipline your tone"). Skipped for extreme Neuroticism (N ≈ 1.0).

5. **Narrative Transitions**: Replaces the mechanical EVOLUTION block with 6 narrative templates: reunion, pos→neg, neg→pos, high→low arousal, low→high arousal, emotion-specific. Priority-ordered detection from `ExpressionProfile.previous_pad`.

6. **Multi-Emotion Self-Report**: The `<psyche_eval/>` tag now uses `emotions="name:intensity,name:intensity"` format (1–3 emotions, backward compatible with single-emotion format). Processing uses decreasing weights (1.0, 0.5, 0.25) and accumulated cross-valence suppression.

7. **Computed Resonance**: Alignment metric [-1, +1] between user valence and assistant emotion. Positive resonance (empathetic match) boosts relationship warmth. Negative resonance in STABLE stage boosts trust (honest disagreement). Special handling for concern/empathy/protectiveness responses.

8. **Proactive Emotions**: Pre-response emotion pulses based on drives and context. High curiosity + new user → curiosity pulse. High engagement → enthusiasm pulse (with anti-inflation guard at 0.50). Quality + engagement → joy pulse. High self-efficacy → pride pulse (once only).

---

## Technical Reference

### Files

| File | Purpose |
|------|---------|
| `src/domains/psyche/constants.py` | 14 mood centroids, 22 emotion PAD vectors, behavioral directives |
| `src/domains/psyche/engine.py` | Pure computation engine (14 static methods, trait modulation) |
| `src/domains/psyche/models.py` | SQLAlchemy models (PsycheState, PsycheHistory) |
| `src/domains/psyche/schemas.py` | Pydantic request/response schemas |
| `src/domains/psyche/repository.py` | Data access layer |
| `src/domains/psyche/service.py` | Orchestration + `build_psyche_prompt_block()` helper |
| `src/domains/psyche/router.py` | FastAPI endpoints (7 endpoints incl. /summary) |
| `src/core/config/psyche.py` | Configuration settings |
| `src/domains/agents/prompts/v1/psyche_self_report_instruction.txt` | LLM self-report prompt (22 emotions) |
| `src/domains/agents/prompts/v1/psyche_summary_prompt.txt` | LLM summary generation prompt |
| `src/domains/agents/prompts/v1/psyche_narrative_prompt.txt` | LLM narrative identity prompt |
| `src/infrastructure/scheduler/psyche_snapshot.py` | Daily snapshots + weekly narrative job |
| `tests/unit/domains/psyche/test_engine.py` | ~145 unit tests (incl. graduated directives, serenity floor, resonance) |
| `tests/unit/domains/psyche/test_service_summary.py` | ~10 service tests |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/psyche/state` | Full psyche state |
| GET | `/api/v1/psyche/summary` | LLM-generated natural language summary |
| GET | `/api/v1/psyche/expression` | Compiled expression profile |
| GET | `/api/v1/psyche/settings` | User psyche preferences |
| PATCH | `/api/v1/psyche/settings` | Update preferences |
| POST | `/api/v1/psyche/reset` | Reset state (soft/full/purge) |
| GET | `/api/v1/psyche/history` | Evolution history snapshots |

### Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `PSYCHE_ENABLED` | `true` | Global feature flag |
| `PSYCHE_MOOD_DECAY_RATE` | `0.1` | Mood decay per hour |
| `PSYCHE_EMOTION_DECAY_RATE` | `0.3` | Emotion decay per hour |
| `PSYCHE_EMOTION_MAX_ACTIVE` | `7` | Max simultaneous active emotions |
| `PSYCHE_APPRAISAL_SENSITIVITY` | `0.7` | System-level sensitivity multiplier |
| `PSYCHE_CIRCADIAN_AMPLITUDE` | `0.08` | Circadian pleasure modulation |
| `PSYCHE_RELATIONSHIP_WARMTH_DECAY_RATE` | `0.02` | Warmth decay per hour of absence |
| `PSYCHE_SELF_EFFICACY_PRIOR_WEIGHT` | `5.0` | Bayesian prior weight for self-efficacy |
| `PSYCHE_CACHE_TTL_SECONDS` | `300` | Redis cache TTL |
| `PSYCHE_HISTORY_SNAPSHOT_ENABLED` | `true` | Record snapshots after each message |

### Token Cost

| Component | Input | Output | When |
|-----------|-------|--------|------|
| Rich directives in main response | ~120 tokens | — | Every non-trivial message |
| Self-report instruction | ~30 tokens | — | Every non-trivial message |
| Self-report tag output | — | ~25 tokens | Every non-trivial message |
| Compact injection (secondary points) | ~40 tokens | — | Per notification/email/etc. |
| **Total (main response)** | **~150 tokens** | **~25 tokens** | |
