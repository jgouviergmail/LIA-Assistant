# ADR-245: one reasoning intent, one translator, one authority per question

**Status**: Accepted (2026-08-26)
**Deciders**: LIA core team
**Technical story**: reasoning-unification design (`docs/superpowers/specs/2026-08-25-reasoning-unification.md`), Lot 0c. Companion to [ADR-244](ADR-244-LLM-Catalogue-Truth.md), which made the catalogue's *capabilities* trustworthy; this one does the same for what an operator *asks* of a model.

## Context

Asking a model to think harder went through **four stored shapes**, dispatched on a
catalogue column, and read by **seven builders**:

```
{"effort": "<str>"}                     widget = enum
{"budget": <int>}                       widget = budget_int
{"enabled": <bool>, "budget": <int?>}   widget = toggle_budget
null                                    widget = none
```

Three authorities had to agree for a call to work: the `llm_models.reasoning_widget`
column, the *shape* of the stored JSONB, and the builder's own `isinstance` check.
When they disagreed the LLM failed to instantiate — a `RuntimeError` on the hot path,
for a configuration the admin UI had accepted.

The disagreements were not hypothetical.

**The same instruction was stored two ways, and both were live.** Measured over the 54
configured slots before the change: **21 stored `{"effort": "off"}`** and **6 stored
`{"effort": "none"}`**, meaning exactly the same thing. Any code reasoning about "is
reasoning disabled here" had to know both, and the guard that decided whether thinking
would eat the completion budget knew one of them.

**The admin UI offered a level the API refuses.** `gpt-5.2` was published to the
frontend with the catalogue's `reasoning_enum_values`, while the write path validated
against something else — so `minimal` was selectable, savable, and rejected by OpenAI
at call time.

**A second channel wrote the same provider kwarg.** `llm_config_overrides.effort` and
`llm_models.effort_values` fed Anthropic's `output_config.effort`, which
`reasoning_effort` also produced; `additional_kwargs.update()` decided which one won,
by dict order. Measured at removal: no configured slot set it.

**A stale value became an error rather than a degradation.** Changing a slot's model
left its `reasoning_effort` in the previous model's shape. The frontend had a coercion
chokepoint for it (prod 2026-08-14: a model absent from the dialog's metadata left the
section unrendered and the previous shape travelled into the PUT — 422 on every save);
the *runtime* had none.

## Decision

**One intent, one profile, one translator — and each question has exactly one owner.**

```python
@dataclass(frozen=True)
class ReasoningIntent:            # what the CALLER wants
    level: Level = "provider_default"
    budget_tokens: int | None = None
    exclude_from_output: bool = False

@dataclass(frozen=True)
class ReasoningProfile:           # what the MODEL can do
    family: str
    levels: tuple[str, ...]
    supports_budget: bool
    budget_range: tuple[int, int] | None
    can_disable: bool
    default_enabled: bool | None
    source: str = "family"
```

- **The ladder is ordinal and provider-independent**: `provider_default < none <
  minimal < low < medium < high < xhigh < max`. `provider_default` sits at the bottom
  because it is the identity — it asks for nothing and produces no kwarg on any family
  — never a depth, and never a coercion target.
- **The family is derived from `(provider, model)`** by an ordered rule table
  (`reasoning/profiles.py`), narrowed by the one catalogue value still consulted:
  `reasoning_enum_values`.
- **`translate(intent, profile)` renders the provider kwargs**, one small function per
  family, selected from a table. A new provider is one entry and one function; no
  existing family changes.
- **`kwargs_for(provider, model, stored)` is the single adapter seam.** It replaced six
  per-provider call sites scattered across `adapter.py`, and it never raises: an
  unknown model resolves to no family and produces no kwarg, where the builders raised
  on a shape mismatch.

**Coercion, not rejection, at runtime.** A level the model does not offer moves to the
nearest one it does. Three rules make that safe:

1. **Ties break upward.** A tie means the ladder has a gap on both sides; the cheaper
   choice silently under-delivers what the operator asked for, and the more expensive
   one is visible in the cost figures.
2. **`none` is never a coercion target.** Moving *to* `none` would disable reasoning
   on a model chosen for it — the one outcome no operator ever means by "use the
   nearest available depth".
3. **`can_disable`, not ladder membership, governs turning reasoning off.** A catalogue
   row narrows the ladder to the DEPTHS a model offers (`claude-opus-4-6` declares
   `["low","medium","high","max"]`) without meaning "and it can no longer be turned
   off". Reading the ladder here would have silently ENABLED reasoning on an explicit
   `none` — the failure mode inverted.

**Every coercion is counted and logged** (`llm_reasoning_coerced_total{model,
from_level,to_level}` + `llm_reasoning_coerced`). A coercion is not an error, but it
does mean the model is not doing what the admin asked, and that must be visible
somewhere other than a reading of the code.

**Rejection stays on the write path**, where a human is present to fix it, and it
answers exactly one question — *is this level on this model's ladder?* — using
`resolve_reasoning_profile`, the same function the translator uses. The validator and
the translator therefore cannot disagree, which is what made the three-authority
arrangement fail.

**What the UI is offered is what the API accepts.** `GET /llm-config/metadata` now
publishes the RESOLVED profile (`reasoning_family`, `reasoning_levels`,
`reasoning_can_disable`, `reasoning_supports_budget`, `reasoning_supports_exclude`,
`reasoning_budget_range`) instead of the catalogue columns — ADR-184's rule applied to
reasoning: whatever a validator can reject, its producer must be able to read. The
budget range published is the family's own, the one the validator enforces; a second
range typed into the catalogue could only disagree with the one actually applied.
`reasoning_supports_exclude` is **derived from the renderers themselves** (render the
same level twice, with and without the flag, and compare) so the switch cannot outlive
the kwarg.

**The catalogue's shape columns are dropped.** `reasoning_widget` and
`reasoning_budget_range` were demoted first — kept as descriptive metadata, out of the
reasoning identity and out of the ADR-228 workbook — and removed one release later
(v1.32.0, migration `f5a6b7c8d9e0`), because the admin form went on offering them for
editing with nothing saying they decided anything. The cohesion rule that guarded them
went with them: its last clause — *`widget='none'` must NOT carry
`reasoning_enum_values`* — had come to forbid the most useful row an operator can
write, "this model reasons, and these are the depths it accepts", on the strength of a
column nothing consults. What survives is what the resolution reads:
`reasoning_enum_values`, the ladder narrowing, plus `reasoning_doc_i18n_key` for the
help text.

## Consequences

**Migration `d3e4f5a6b7c8` is not a flag day.** `LLMAgentConfig` and
`LLMTypeConfigUpdate` both read the legacy shapes through `intent_from_legacy`, so an
instance that takes the code before running the migration keeps working, and one that
runs the migration before deploying the code keeps working too. The mapper is shared by
the migration, the reference seeds and the golden-equivalence test, so the three cannot
disagree about what a stored value MEANT. It is also total on its own output: replaying
a seed, or an older instance reading a row a newer one wrote, cannot re-encode it.

**The rewrite was simulated against real data before it was written.** Against the dev
database: 36 stored override rows, 29 code defaults, **1 290 (model × stored shape)
combinations, 0 divergences** in the provider kwargs produced. The rewrite collapses
21 × `{"effort": "off"}` and 8 × `{"effort": "none"}` into a single `{"level": "none"}`.

**Equivalence is a permanent test, not a one-off check.** `golden_kwargs.json` freezes
the kwargs the pre-change builders produced for every (model, stored value) pair and
replays them against the translator: **54/54 identical**. It is the artefact that lets
a future family be added without re-deriving what the old code did.

**Down-migration does not reconstruct the legacy shapes.** An intent does not record
which of the four encodings it came from — `{"effort": "off"}`, `{"effort": "none"}`
and `{"enabled": false}` all said `level="none"` — so guessing one would write a shape
the old builders might reject. The stored intents are left in place: the pre-ADR-245
code refuses them at read time, which is a loud, immediate failure rather than a silent
wrong reasoning mode.

**dev and prod are configured differently, and nothing here assumes otherwise.** The
migration reads the target instance's own rows; the unit tests read `LLM_DEFAULTS`,
never a database; `task llm:catalogue:preflight` gives a read-only, per-instance
pre-deployment check.

**What this costs.** A per-provider builder could express a provider quirk directly;
the translator has to express it as a family. That is the intended trade: a quirk that
does not fit a family is a new family (one table entry, one function), not a branch
inside a shared function.

## Alternatives considered

**Keep the four shapes and fix the three authorities.** Rejected: the authorities have
no reason to agree, because nothing derives one from another. Every fix restores the
agreement for the models it touches and leaves the next divergence to be found in
production.

**Validate at runtime instead of coercing.** Rejected: it turns a stale configuration
into an outage on a code path with no human present. The admin write path is where a
human can fix it; the runtime's job is to still make the call, and to say what it did.

**Publish the catalogue columns and validate against them.** Rejected: that is the
`minimal` bug. The catalogue is a declaration; the family rules are what the runtime
applies. Publishing the declaration while enforcing the rules is precisely how the UI
came to offer a level the API refuses.

**Delete the demoted catalogue columns outright.** Deferred at first, then done
(v1.32.0). The argument for keeping them — "they still document what a vendor
publishes, and the admin catalogue displays them" — was refuted by the screen itself:
the create/edit form went on offering `reasoning_widget` and `reasoning_budget_range`
for editing, with nothing saying they no longer decided anything. A field an operator
can curate, that nothing reads, is worse than an absent one, and the repository's own
rule already said so (*"dead code is deleted, not kept for later"*). Migration
`f5a6b7c8d9e0` drops both columns and the enum type that had no other user;
`reasoning_enum_values` — the ladder narrowing the resolution does read — and
`reasoning_doc_i18n_key` survive.

One defect surfaced with them: four rows still declared `off` in that surviving
ladder, a level the ADR-245 vocabulary does not have. The narrowing is an
intersection, so `("none","high","max") ∩ {"off","high","max"}` produced a ladder with
**no off switch**, and only `can_disable` — the rule this ADR establishes — put the
switch back. It worked by rescue, not by design. Migration `e4f5a6b7c8d9` normalises
those ladders through `intent_from_legacy`, and a guard refuses any seed row declaring
a level off the ladder.

## Amendment (2026-09-05) — the seam had two branches left

This ADR said `kwargs_for` replaced six per-provider call sites. It had replaced
five. The Ollama and Perplexity branches of `_prepare_provider_config` never
popped `reasoning_effort`, so the stored `ReasoningIntent` object itself reached
`ChatOpenAI(reasoning_effort=...)` and failed Pydantic validation — for ANY stored
level, `provider_default` included.

Measured in production on 2026-09-05: the `response` slot was moved to
`ollama / qwen3.8:27b` and every turn died at instantiation. The override row had
`reasoning_effort = NULL` (the admin widget hides itself on a model whose ladder is
empty), so the level came from the slot's code DEFAULT through `merge_config` — the
inheritance this ADR deliberately kept, because the runtime coerces. Twenty-nine of
the fifty-eight slot defaults carry a non-null intent; none of those slots could
ever run on Ollama or Perplexity, and the other twenty-nine broke the moment an
intent was stored.

Three decisions:

1. **Both branches now call the seam**, like the five others. For the sonar
   reasoning tier the existing `perplexity` renderer runs for the first time. For
   Ollama the family is `ollama` (ADR-267): its ladder is a vocabulary the discovery
   declares per model from the server's `thinking` capability — full for a thinking
   model, `("none",)` for the others, unknown for a tag nobody discovered
   (`ReasoningProfile.ladder_from_catalogue`). Ollama accepts `think=false` on any
   model and rejects a positive level on a model without the capability
   (`server/routes.go`), which is exactly what that shape guarantees.
2. **A guard drives every member of `ProviderType`** with every storable level
   (`test_reasoning_seam_guard.py`): no constructor may receive the intent object,
   and every kwarg must be JSON-serialisable. A new provider must be added to its
   matrix. Mutation-checked: reinstating the Ollama defect turns thirteen tests red.
3. **`extra_body` is merged, never assigned** (`_merge_extra_body`): three branches
   wrote that one kwarg and a plain assignment dropped whatever the
   `provider_config` escape hatch had put there.
