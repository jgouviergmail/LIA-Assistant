# Psyche Engine — Emotional Intelligence

## What is the Psyche Engine?

The Psyche Engine gives LIA a dynamic psychological state that evolves with every interaction. Instead of a fixed personality, LIA now has moods that fluctuate, emotions that fire and decay, a relationship that deepens with time, and personality traits that shape how it reacts emotionally.

**Design principle**: LIA never says "I'm feeling happy" — instead, its vocabulary becomes warmer, its energy higher, its suggestions more adventurous. You perceive a living personality without explicit emotional statements.

## The 5 Layers

1. **Personality (permanent)** — Big Five traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) inherited from the chosen personality. They modulate emotional reactivity, empathy, and recovery speed.
2. **Mood (hours)** — A position in 3D PAD space (Pleasure, Arousal, Dominance) mapped to one of 14 distinct moods. Decays toward the personality baseline over time.
3. **Emotions (minutes)** — Up to 7 simultaneous emotions from 22 types (joy, gratitude, curiosity, serenity, pride, frustration, concern, melancholy, surprise, amusement, empathy, enthusiasm, confusion, disappointment, tenderness, determination, playfulness, protectiveness, relief, nervousness, wonder, resolve). Each has an intensity that decays and pushes the mood in a specific direction.
4. **Relationship (weeks/months)** — 4 stages (Orientation → Exploratory → Affective → Stable) with tracked depth, warmth, and trust. Progress is one-way.
5. **Drives (per session)** — Curiosity and engagement that evolve with each exchange. High curiosity makes LIA explore new angles; high engagement makes it more thorough.

## Emotional Avatar

A mood emoji replaces the classic LIA logo on assistant messages. The emoji and colored ring reflect the current emotional state. Hover for a tooltip showing mood, active emotion, and relationship stage. Each message preserves its historical avatar — on page reload, you see the mood LIA had when it wrote that message.

## Settings

Located in Settings > Psyche de LIA:

- **Enable/Disable** — Toggle the entire Psyche Engine on or off
- **Avatar Display** — Show or hide the mood emoji on messages
- **Expressiveness** (0-100%) — How strongly emotions influence responses. 0% = stoic, 100% = highly expressive
- **Stability** (0-100%) — How quickly mood returns to baseline. 0% = volatile, 100% = very stable
- **Refresh Mood** — Resets mood and emotions but preserves the relationship and personality traits
- **Reset Everything** — Resets mood, emotions, relationship, and domain confidence. Memories and journals are not affected

## History Dashboard

4 interactive charts showing evolution over time (24h to 90 days):
- **Mood (PAD)** — Pleasure, Arousal, and Dominance curves
- **Emotions** — Per-emotion intensity lines (dynamic, only emotions that appeared)
- **Relationship** — Depth, warmth, and trust progression
- **Drives** — Curiosity, engagement, and emotion intensity

Reset events are marked as red dashed vertical lines on all charts.

## How It Works

Before each response, LIA loads its psychological state, applies natural decay toward its personality baseline, checks what time of day it is (slight mood boost at midday), and compiles behavioral directives that shape the tone of its reply.

After each response, LIA self-evaluates: what emotion did this exchange trigger? How positive was the user? This hidden evaluation feeds the next cycle — creating a continuous emotional loop that makes conversations feel natural and alive.

## FAQ

**Does the Psyche Engine cost extra tokens?** Very little — about 150 input tokens and 25 output tokens per message. The self-evaluation uses a hidden XML tag, not an extra LLM call.

**Can I ask LIA about its mood?** Yes. While LIA normally doesn't announce its emotions, if you ask directly, it can share what it's feeling.

**Does changing personality affect the Psyche?** Yes. When you switch personality, Big Five traits and mood baseline are automatically updated. The mood is repositioned to the new personality's resting point.

**What's the difference between Refresh Mood and Reset Everything?** Refresh Mood clears mood and emotions but keeps the relationship intact. Reset Everything also resets the relationship stage, trust, depth, and domain confidence — like a first meeting.
