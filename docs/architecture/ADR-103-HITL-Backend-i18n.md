# ADR-103: HITL Backend Internationalization (no hardcoded French)

**Status**: ✅ IMPLEMENTED (2026-07-05)
**Related**: [ADR-085](ADR_INDEX.md) (Draft Display Registry — the parity-guard model), [ADR-102](ADR-102-Domain-Vocabulary-Single-Source.md) (Domain vocabulary single source)

## Context

The backend HITL (Human-in-the-Loop) layer remained structurally French for the
five non-French languages: several code paths hardcoded French strings that a
German, Spanish, Italian, Chinese or English user would hit — either emitted
into their conversation, or fed to an LLM in a way that biased its output. The
Chinese normalization was already done (wave 2), but the generation/reformulation
paths were not.

Two distinct categories of string were conflated, whereas `core/i18n.py` already
draws the line ("*LLM prompts are NOT translated — LLMs understand all
languages*"):

- **LLM-facing scaffolding** — prompt fragments, context labels, few-shot
  examples. Never shown to the user; the output language is controlled by the
  prompt's ``Respond in {user_language}`` instruction. These should be **English**
  (the convention of the versioned prompts), not French.
- **Emitted / user-visible messages** — text injected into the conversation
  (reformulated intent replacing the user's turn, refusal steering) or surfaced
  to the response node. These must be **localized to all six languages**.

## Decision

Apply the two-category rule across the HITL layer, plus a permanent parity guard.

### 1. LLM-facing scaffolding → English

- `draft_modifier`: the modification instruction, the preserved-field context
  labels and the expected-JSON example are English (the versioned
  `draft_modifier_prompt.txt` is already English and drives the output language).
- `hitl_classifier`: the few-shot examples are **externalized** to a versioned
  prompt `hitl_classifier_examples.txt` (English, one ``=== <action_type> ===``
  section each, parsed by a cached loader), removing the French-only bias that
  skewed classification for non-FR users. The action-description context
  (`_format_*_context`) is English too. The user's response may still be in any
  language — it is classified by intent structure, not by matching words.

### 2. Emitted messages → six languages via `HitlMessages`

- Reformulated EDIT intents and the REJECT enriched HumanMessage are localized
  through new `HitlMessages` tables/methods (`get_reformulation`,
  `get_reject_enriched_message`), keyed by a `ReformulationKind` StrEnum (no
  magic strings; an exhaustiveness test forbids a silent empty message).
- The `agent_results` user-rejection fallback is localized
  (`get_user_refused_action`).
- The user language is read from the **checkpointed graph state**
  (`MessagesState.user_language`) at resume time via `resolve_user_language`, and
  threaded as a parameter — never stored on `self` (concurrency-safe).

### 3. Backend i18n parity guard

`tests/unit/core/test_i18n_parity.py` (ADR-085 model) recursively scans the
`core.i18n_*` modules and fails when a language-keyed table is missing a language
(revealed and fixed a real `zh-CN` gap in `_DISPLAY_OPEN_NOW`) or, for
`dict[lang, dict[key, …]]` translation tables, when the inner keys diverge across
languages. `i18n_patterns` is excluded from the *key-parity* check because its
keyword/ordinal maps intentionally key on each language's own words.

## Consequences

- A full HITL turn (EDIT + REJECT) for a German or Chinese user emits no French
  (covered by an end-to-end guard test).
- Classification is no longer biased by French-only few-shot examples.
- Any new backend i18n table missing a language (or an inconsistent key set)
  fails CI.
- Out of scope (documented, not touched): generic non-HITL agent-status
  fallbacks in `agent_results` (`"Erreur inconnue"`, `"Statut inconnu"`, `"Service
  non activé"`).

Non-regression: full fast unit suite green, Black / Ruff / MyPy (strict) clean,
app boots healthy with all changes. No migration.
