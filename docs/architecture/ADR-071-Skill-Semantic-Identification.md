# ADR-071: Skill Semantic Identification

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-15 |
| **Related** | ADR-019 (Agent Manifest Catalogue System), ADR-048 (Semantic Tool Router) |

## Context

Skill identification in the planner pipeline originally combined two heterogeneous mechanisms:

1. **`SkillBypassStrategy`** (deterministic skills only) — matched skills by computing the **overlap of domains** between `QueryIntelligence.domains` and the `agent_name` fields of the skill's `plan_template.steps`. A per-skill threshold `max_missing_domains` (default: 1) controlled how strict the overlap had to be.
2. **`QueryAnalyzer`** (non-deterministic skills only) — exposed non-deterministic skills to the LLM through an XML catalogue containing name + description, and let the LLM set `skill_name` in its output by reading the descriptions.

Deterministic skills were **explicitly hidden** from the `QueryAnalyzer`'s catalogue (filter `not deterministic` in `query_analyzer_service.py`), making the two mechanisms mutually exclusive at the planning step.

### Production incident (2026-04-15)

On a real user request *"Je veux mon briefing quotidien"*, `QueryAnalyzer` classified the query domains as `{web_search, weather, event}` (introducing `web_search` as a proxy for "information retrieval"). The deterministic `briefing-quotidien` skill declares five domains `{event, task, weather, email, reminder}`. The overlap calculation produced `overlap=2, missing=3`, exceeding the skill's `max_missing_domains=2` threshold. The bypass refused to trigger.

The LLM planner then generated a two-step plan (events + weather) without emails, tasks or reminders. The `SkillActivator` in the response node identified the skill by description (semantic match) and activated the briefing format — but the underlying tool data for emails / tasks / reminders had never been collected.

### Root cause

The domain-overlap heuristic is a **lagging proxy for user intent**. Two queries covering identical domains can have completely different intents:

- *"Give me my daily briefing"* — aggregation, matches the `briefing-quotidien` description
- *"Send the weather by email to my wife and plan us a meeting this afternoon"* — action composition on `{weather, email, event}`, unrelated to the briefing skill

Relying on domain overlap at the planner level meant skills could be triggered structurally even when the user's intent did not match, and conversely skills could be missed when the `QueryAnalyzer` introduced parasitic domains. Multiplying thresholds (`max_missing_domains`) per skill amplified the configuration surface without fixing the underlying signal.

## Decision

### Single source of truth: semantic identification

Skill identification is **unified** around a single signal: `QueryIntelligence.detected_skill_name`, produced by the `QueryAnalyzer` LLM from semantic alignment between the user's request and each skill's description.

- The `QueryAnalyzer` now exposes **all active skills** (deterministic and non-deterministic) to the LLM. The deterministic-vs-dynamic distinction is resolved downstream.
- `SkillBypassStrategy` consumes `detected_skill_name` directly: `can_handle` is a presence check, `plan` does the user-scoped lookup, verifies the skill is deterministic and active, and builds the plan from the template.
- `_has_potential_skill_match` (the early-insufficient-content guard in `planner_node_v3.py`) is simplified to a presence check on `detected_skill_name`.
- `max_missing_domains` and the global constant `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` are removed. Leftover occurrences in user YAMLs are silently ignored by the lenient loader.

### User isolation

All cache lookups in the bypass path go through `SkillsCache.get_by_name_for_user(name, user_id)`, which respects the agentskills.io override semantics (user's own skill wins over an admin skill of the same name) and **never reaches skills owned by other users**. The previous `SkillsCache.get_all()` iteration, which relied on `active_skills_ctx` as the only isolation filter, is eliminated in the planner hot path.

### Eligibility contract

A skill is eligible for planner-level activation if and only if:

1. The `QueryAnalyzer` sets `detected_skill_name` to its name (semantic description match)
2. The user has the skill active (`active_skills_ctx` contains it, or `active_skills_ctx` is `None`)
3. The skill is returned by `SkillsCache.get_by_name_for_user(name, user_id)`

If the resolved skill is deterministic, `SkillBypassStrategy` builds the plan from the template. Otherwise, the LLM planner handles it using the skill's description and instructions.

## Consequences

### Positive

- **Intent-aligned activation**: a skill is triggered because its description matches the user's whole intent, not because of a coincidental domain overlap.
- **Simpler model**: one mechanism, one signal, one code path. `SkillBypassStrategy` drops ~100 lines of overlap logic. `_has_potential_skill_match` drops ~60 lines.
- **Stronger user isolation**: user-scoped lookups are the only access pattern in the hot path. No implicit cross-user visibility.
- **Deterministic and non-deterministic skills treated uniformly at the identification layer**: the response node activation and the planner bypass consume the same `detected_skill_name`.
- **Skill-authoring contract clarified**: skill descriptions become the primary contract — they must unambiguously capture the skill's purpose so the LLM can identify them.

### Negative

- **Single LLM failure mode**: if the `QueryAnalyzer` fails to identify a skill (prompt issue, skill description too vague, rare hallucination), there is no structural fallback at the planner. This is a conscious trade-off: rather than mask failures with a domain-overlap safety net (which masks description problems and invites false positives), we prefer to fail fast so description quality improves over time.
- **Prompt quality becomes load-bearing**: the `QueryAnalyzer` prompt must guide the LLM to distinguish skill invocations from action compositions. The prompt was reinforced accordingly (*"A skill matches when its description semantically aligns with the user's intent as a whole — not merely because a keyword appears."*).
- **All active skills now visible in the `QueryAnalyzer` catalogue**: a small increase in prompt tokens per request (≈50-100 tokens per skill, bounded by the number of active skills — typically <30).

### Mitigations

- Existing positive-path structlog events (`skill_detected`, `skill_bypass_matched`, `skill_activated`) remain and provide enough signal to diagnose missed detections from production traces. No preventive logging of non-detections (which would be noise).
- Skill description quality governance becomes an explicit concern during skill authoring. The UI guide no longer exposes `max_missing_domains` as a lever.

## Alternatives Considered

### Alternative A: Keep the overlap as a secondary fallback

Promote `detected_skill_name` to primary signal but keep the domain-overlap matching (with `max_missing_domains` tightened) as a secondary filet in case `QueryAnalyzer` misses. **Rejected**: retains the confusion between structural and semantic signals; user example "*send weather to my wife + plan meeting*" still matches briefing on domains, yielding a silent false positive when `QueryAnalyzer` returns null.

### Alternative B: Late-swap in the LLM planner

Let the LLM planner detect the skill from its own catalogue and, if it picks a deterministic skill, swap its generated steps with the template. **Rejected**: duplicates the semantic detection logic in a second LLM stage, adds complexity, and masks the fact that `QueryAnalyzer` failed upstream — preventing iterative improvement of its prompt.

### Alternative C: Embedding-based similarity at the bypass level

Compute a similarity score between the query and each skill's description via embeddings, activate the bypass when the top match crosses a threshold. **Rejected for now**: reintroduces a tunable threshold per skill (same failure mode as `max_missing_domains`), and the `QueryAnalyzer` LLM already performs a richer semantic judgement than embedding similarity alone.

## Implementation Notes

- `SkillBypassStrategy.can_handle` returns `True` even for non-deterministic skills; `plan` gracefully returns `PlanningResult(success=False)` with a human-readable `error` field, and the planner falls through to the next strategy.
- `_filter_steps_by_scopes` is preserved unchanged — the scope-aware partial-execution contract (e.g., briefing without email for a user without Gmail) remains.
- Tests `test_skill_bypass_strategy.py` and `test_planner_v3_skill_guard.py` have been rewritten around the new eligibility contract, with explicit coverage of user-override semantics.
