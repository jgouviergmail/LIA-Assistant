# ADR-064: Journal Analyst Persona Replaces Personality Addon

## Status

Accepted

## Date

2026-03-25

## Context

The Personal Journals (Carnets de Bord) feature extracts observations from conversations and injects them into planner/response prompts to help the assistant build personality and improve reasoning.

Analysis of 64 dev entries and 21 prod entries revealed critical quality issues:
- **Personality contamination**: The conversational personality (e.g., "cynic") was injected into journal writing via `journal_introspection_personality_addon.txt`, causing the LLM to produce literary/sarcastic prose instead of actionable directives.
- **Zero `learnings` in prod**: The most operationally useful theme was completely absent.
- **Massive redundancy**: 5 entries for the same "ça va" insight, consolidation created MORE entries instead of merging.
- **<10% injection rate**: Most entries were never semantically matched to user queries.
- **Verbose entries**: Without personality, entries reached 954-1541 chars of narrative prose.

## Decision

1. **Replace the personality addon with a fixed "analyst persona"** (`journal_analyst_persona.txt`) that is always injected regardless of the active conversational personality. The persona instructs the LLM to write as a clinical behavioral observer producing actionable directives.

2. **Introduce a preferred directive format**: `WHEN [context] → DO [action] (BECAUSE [observation])`, with alternative formats for user preferences and relationship dynamics.

3. **Restructure consolidation** with mandatory dedup as the first step and progressive reformatting of legacy prose entries.

4. **Reduce max entry size** from 2000 to 800 characters to force density.

5. **Purge existing entries** via migration — the old prose format is incompatible with the new directive approach, and progressive reformatting would be too slow/expensive.

## Rationale

The conversational personality serves a different purpose (coloring user-facing responses) than journal writing (producing operational directives for future prompts). Decoupling them allows each to be optimized independently:
- The personality continues to color conversations
- The journal persona is optimized for producing entries that actually get injected and improve behavior

The `personality_code` field remains on `JournalEntry` as traceability metadata (which personality was active when the entry was created) but no longer influences the writing style.

## Consequences

- Journal entries will be denser, more actionable, and in directive format
- The `learnings` theme should see increased representation
- Consolidation will aggressively merge duplicates
- Existing entries (85 total across dev+prod) are purged — journal rebuilds naturally in 2-3 days
- `personality_instruction` parameter kept in service signatures for backward compatibility but unused for prompt building
