# Capability Truth, Observation and Dead Code (ADR-244 Lot 0b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every capability LIA *declares* be one it also *enforces* or *reads*, persist the four facts a later policy needs to judge a model, and delete the slots nothing calls.

**Architecture:** Five independent corrections on the same subsystem, all enabled by Lot 0a's corrected catalogue: the five undeclared `required_capabilities`, a `supports_strict_mode` reader arbitrated by provenance, four observation columns on `token_usage_logs` written from data already in memory, a boot assertion on the failover chain, and the removal of two dead slots plus an orphan seed row and a silent fallback.

**Tech Stack:** Python 3.14, SQLAlchemy 2 + Alembic, Pydantic 2, pytest, LangChain callbacks, Task (Taskfile.yml).

**Spec:** `docs/superpowers/specs/2026-08-23-llm-model-policy-design.md` — §2.7 (declared-but-unenforced), §5.2 (capability gate), §5.3 (observation columns), §5.4 (verified failover), §5.5 (dead code), plus the install-contract measurement at §3.

**Predecessor:** `docs/superpowers/plans/2026-08-23-llm-catalogue-truth.md` (Lot 0a, delivered). Its 16 amendments are the measured context for everything below.

## Global Constraints

- **A gate over incomplete declarations is worse than none.** The five missing `required_capabilities` land BEFORE anything enforces them.
- **Never override a human decision silently.** A model that comes from `LLM_DEFAULTS` or an admin override is never rejected by the gate — the discrepancy is counted and logged. Only a *policy candidate* (Lot 1, not yet existing) is hard-filtered.
- **Reuse the existing error taxonomy.** `MetricsCallbackHandler._classify_llm_error` already classifies LLM API failures into nine documented kinds. `failure_kind` uses that vocabulary verbatim; a second one would drift.
- **The observation columns are nullable, with no backfill.** They describe calls made after the migration; inventing history is worse than admitting its absence.
- **Assert, not crash.** A broken failover list logs loudly and disables the middleware. It must never prevent a boot.
- **Python:** Black line-length 100, Ruff, MyPy strict (`platform = linux`). Google-style docstrings, module docstring on every file. English only in code, comments and docs.
- **Logging:** `structlog.get_logger(__name__)`. No `print()`. Counters and ids at INFO; never prompt content. Migrations report through `logging.getLogger("alembic.runtime.migration")`, ASCII only (audit F047).
- **Datetimes:** timezone-aware UTC (`datetime.now(UTC)`).
- **File size:** every touched file stays under 600 logical SLOC; the CC ratchet (337 functions at CC >= 15) is shrink-only.
- **Commits:** Conventional Commits. Do not push.

## Plan Amendments (pre-execution review)

**B1 — the `LLMType` Literal is compared through the alias map, and the gap is
shrink-only.** The draft guard asserted `set(get_args(LLMType)) ==
set(LLM_TYPES_REGISTRY)`; measured, the two differ by design. The Literal
carries seven **singular** names (`contact_agent`, `email_agent`,
`event_agent`, `file_agent`, `place_agent`, `route_agent`, `task_agent`) that
`llm_config_helper._ALIAS_MAP` resolves to the registry's plural forms, and it
is missing six slots that were never added to it (`health_agent`, `hue_agent`,
`image_generation`, `vision_analysis`, `voice_transcription`, `voice_tts`).

The invariant that actually holds — and the one worth guarding — is that
**every Literal name resolves to a real slot**: measured, zero phantoms. That
is exactly what catches Task 7 removing a slot without updating the Literal.
The six missing names become a shrink-only allowlist with their reason, rather
than a strict equality that would red for a pre-existing, documented and
non-load-bearing gap (`pyproject.toml` disables `arg-type` for
`src.domains.agents.nodes.*`, so the Literal never was a type guard).

Task 7's guard therefore reads:

```python
def test_the_literal_names_only_real_slots() -> None:
    """Zero phantoms — this is what catches a removal the Literal forgot."""
    from typing import get_args

    from src.core.llm_config_helper import _resolve_canonical_type
    from src.infrastructure.llm.factory import LLMType

    phantom = sorted(
        {_resolve_canonical_type(name) for name in get_args(LLMType)} - set(LLM_TYPES_REGISTRY)
    )
    assert phantom == [], f"the LLMType Literal names slots that do not exist: {phantom}"


#: Slots the Literal was never given. Shrink-only: entries come out as the
#: Literal is completed, and none may be added.
LITERAL_GAP: frozenset[str] = frozenset(
    {
        "health_agent",
        "hue_agent",
        "image_generation",
        "vision_analysis",
        "voice_transcription",
        "voice_tts",
    }
)


def test_the_literal_gap_is_shrink_only() -> None:
    from typing import get_args

    from src.core.llm_config_helper import _resolve_canonical_type
    from src.infrastructure.llm.factory import LLMType

    reachable = {_resolve_canonical_type(name) for name in get_args(LLMType)}
    missing = set(LLM_TYPES_REGISTRY) - reachable
    assert missing <= LITERAL_GAP, f"a new slot skipped the LLMType Literal: {sorted(missing - LITERAL_GAP)}"
    assert len(LITERAL_GAP) <= 6, "LITERAL_GAP is shrink-only"
```

**B2 — provenance is row-level, its evidence is field-level, and the strict-mode
reader must require `verified`.** The draft followed the spec: `declared` keeps
the provider heuristic, `imported`/`verified` narrows. Measured against the
post-Lot-0a catalogue, that would have been a 41-model regression.

Lot 0a promotes a row to `imported` when the registries corroborate *the fields
they publish* — `CORRECTABLE_FIELDS`, five columns. The promotion is row-level,
so it now sits on rows whose `supports_strict_mode` is still the unfilled column
default, and no public registry publishes that field at all. Measured
2026-08-24: **41 active OpenAI rows** are `imported` with
`supports_strict_mode=false`, including `gpt-4.1`, `gpt-5.2`, `gpt-5.4-mini` and
`gpt-5-mini`. A reader that treated `imported` as evidence about that column
would have switched all 41 off the strict path in one commit — the exact
regression the spec's rule was written to prevent, arriving through the door the
rule left open.

The corrected rule: a reader of a column **inside** `CORRECTABLE_FIELDS` may
trust `imported` (this is what `get_effective_context_window` does, correctly,
on `max_input_tokens`). A reader of any column **outside** it must require
`verified` — only a human edit is evidence there. Measured effect today: **0
rows are `verified`**, so the reader is inert and no model changes behaviour
until someone curates one, which is precisely the intent.

The scope is now written on `LLMCapabilityProvenanceEnum` itself and pinned by
`test_the_documented_scope_names_the_real_field_set`, so the next column
arbitrated on provenance cannot repeat this.

**B3 — every figure in this plan describes the DEV instance, and dev is not
prod.** The real per-agent configuration lives in `llm_config_overrides`, in the
database, and the two deployments run different models. "0 problems", "0
mismatches", "14 deactivated", "0 kept_because_referenced" are dev
measurements; none of them is a statement about production.

The design is already per-instance safe, and that is not an accident:

- the initial-correction migration reads `llm_config_overrides` **from the
  database it runs on**, so a model prod references is kept active on prod even
  when dev deactivated it;
- the capability gate is warning-only for a configured model, so a prod slot
  whose model fails a newly declared capability is counted and logged, never
  rejected;
- `assert_failover_chain` reads the instance's own catalogue at its own boot;
- every unit test reads `LLM_DEFAULTS` — the code declaration — and never a
  database, which is why they can be trusted on any deployment. Two of them
  hard-coded `gpt-5-mini` / `5000` until this lot; they now compare against the
  declaration, so a retarget no longer trips them.

What remains genuinely instance-specific is checked before deploying, by
`task llm:catalogue:preflight` — read-only, run against whatever `DATABASE_URL`
points at. It answers exactly the three questions the figures above cannot:
which models *this* instance would deactivate and which it keeps because it
references them, which configured models fail their slot's declarations, and
whether any `verified` row would lose strict structured output. On dev it
reports `0 item(s) need attention`; **run it against prod before deploying.**

---

## What Lot 0a already settled

Three premises of the spec were measured on the *pre-correction* catalogue and no longer hold. Do not re-derive them:

| Spec claim | Measured after Lot 0a |
|---|---|
| "only 12 of 87 chat models declare `supports_vision`" | **52 of 73 active chat models** do |
| "`vision_analysis`'s own default `gpt-5-mini` declares `supports_vision=false`" | it declares **true** (`imported`) — the example that motivated the warning-only rule no longer fires. The rule stands on its own doctrine, not on that example |
| "83 models whose `supports_strict_mode` column is an unfilled `false`" | still true: the registries publish nothing about strict mode, so those rows stay `declared` on that field and the provenance rule below is what protects them |

And two facts make Task 1 safe: **70 of 73** active chat models declare `supports_structured_output`, and the current model of each of the five slots to declare qualifies.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/src/domains/llm_config/constants.py` | the five declarations; the two dead slots leave |
| `apps/api/src/domains/llm_config/service.py` | `_model_has_capability` stops answering `True` to an unknown capability |
| `apps/api/src/infrastructure/llm/capability_gate.py` | **new** — the one place that decides whether a model satisfies a slot, and what happens when it does not |
| `apps/api/src/infrastructure/llm/structured_output.py` | `supports_strict_mode` gains its reader |
| `apps/api/src/domains/chat/models.py` | four nullable columns + the controller index |
| `apps/api/src/domains/chat/service.py` | `TokenUsageRecord` carries them |
| `apps/api/src/domains/chat/repository.py` | they reach the row |
| `apps/api/src/infrastructure/observability/callbacks.py` | `llm_type` from the metadata already there; a new `on_llm_error` |
| `apps/api/src/infrastructure/observability/error_taxonomy.py` | **new** — the nine failure kinds, shared by the metric label and the column |
| `apps/api/src/infrastructure/startup/agents.py` | the failover boot assert |
| `apps/api/src/core/bootstrap.py` | `router` leaves the critical-types list |
| `apps/api/src/domains/llm_config/install_contract.py` | `router` and `context_resolver` leave `CURRENT_CORE_LLM_TYPES` |
| `apps/api/src/domains/agents/graphs/base_agent_builder.py` | the silent `.get(..., "contact_agent")` fallback |
| `infrastructure/database/seeds/llm_config_seed.sql` | the `mcp_excalidraw` orphan row leaves |
| `apps/api/alembic/versions/2026_08_25_0900-<rev>_token_usage_observation.py` | schema |
| `apps/api/tests/unit/infrastructure/llm/test_capability_gate.py` | gate tests |
| `apps/api/tests/unit/test_llm_slot_vocabulary_guard.py` | **new** guard: registry, seed and install contract name the same slots |

---

### Task 1: The five missing declarations, and no silent pass on an unknown capability

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py` (five `LLMTypeMetadata` entries)
- Modify: `apps/api/src/domains/llm_config/service.py:101-113` (`_model_has_capability`)
- Test: `apps/api/tests/unit/domains/llm_config/test_capability_checks.py` (existing file)

**Interfaces:**
- Produces: `KNOWN_MODEL_CAPABILITIES` becomes load-bearing — `_model_has_capability` raises on anything outside it.

**Why:** `required_capabilities` is declared on all 58 slots and enforced nowhere; five slots use structured output without declaring it. And `_model_has_capability` returns `True` for any capability string it does not know, so a typo in a declaration silently disables the constraint — the exact "silent fallback on an unknown key" ADR-085 forbids.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/unit/domains/llm_config/test_capability_checks.py`:

```python
def test_the_five_structured_output_slots_declare_it() -> None:
    """Verified at each call site: these five ask the model for a schema.

    ``heartbeat_message`` and ``contacts_agent`` matched the same heuristic and
    were checked and discarded as false positives — do not add them.
    """
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

    for slot in (
        "query_analyzer",
        "semantic_validator",
        "document_generation",
        "memory_reference_extraction",
        "open_loop_extraction",
    ):
        assert "structured_output" in LLM_TYPES_REGISTRY[slot].required_capabilities, slot


def test_every_declared_capability_is_a_known_one() -> None:
    """A typo in a declaration must not silently disable the constraint."""
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
    from src.domains.llm_config.service import KNOWN_MODEL_CAPABILITIES

    unknown = sorted(
        {
            capability
            for metadata in LLM_TYPES_REGISTRY.values()
            for capability in metadata.required_capabilities
            if capability not in KNOWN_MODEL_CAPABILITIES
        }
    )
    assert unknown == [], f"undeclared capability names: {unknown}"


def test_unknown_capability_raises_instead_of_passing() -> None:
    """``_model_has_capability`` used to answer True to anything it did not know."""
    import pytest

    from src.domains.llm_config.service import _model_has_capability
    from src.infrastructure.llm.model_profiles import ModelProfile

    with pytest.raises(ValueError, match="unknown capability"):
        _model_has_capability(ModelProfile(), "telepathy")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_capability_checks.py -v --no-cov`
Expected: FAIL on all three — the declarations are empty and the helper returns `True`.

- [ ] **Step 3: Declare the five**

In `apps/api/src/domains/llm_config/constants.py`, for each of `query_analyzer`, `semantic_validator`, `document_generation`, `memory_reference_extraction` and `open_loop_extraction`, replace:

```python
        required_capabilities=[],
```

with:

```python
        # Verified at the call site: this slot asks the model for a schema.
        required_capabilities=["structured_output"],
```

- [ ] **Step 4: Make the helper refuse an unknown capability**

In `apps/api/src/domains/llm_config/service.py`, replace `_model_has_capability`:

```python
def _model_has_capability(caps: ModelCapabilities, capability: str) -> bool:
    """Check whether a ``ModelCapabilities`` declares the given capability.

    Args:
        caps: The model's capability profile.
        capability: One of :data:`KNOWN_MODEL_CAPABILITIES`.

    Returns:
        Whether the model declares it.

    Raises:
        ValueError: when ``capability`` is outside the known vocabulary. The
            previous behaviour — answer ``True`` and move on — turned a typo in
            a slot declaration into a silently disabled constraint, the failure
            mode ADR-085 exists to forbid.
    """
    check = _CAPABILITY_CHECKS.get(capability)
    if check is None:
        raise ValueError(
            f"unknown capability {capability!r}; known: {sorted(KNOWN_MODEL_CAPABILITIES)}"
        )
    return check(caps)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/ -q --no-cov`
Expected: all passed.

- [ ] **Step 6: Verify no dropdown empties**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
import asyncio
from sqlalchemy import select
from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.llm.models import LLMModel
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
async def main():
    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)
        await LLMConfigOverrideCache.load_from_db(db)
        rows = list((await db.execute(select(LLMModel).where(LLMModel.is_active))).scalars().all())
    checks = {'vision': lambda r: r.supports_vision, 'tools': lambda r: r.supports_tools,
              'structured_output': lambda r: r.supports_structured_output}
    for slot, meta in sorted(LLM_TYPES_REGISTRY.items()):
        if not meta.required_capabilities:
            continue
        eligible = [r for r in rows if r.kind is meta.required_kind
                    and all(checks[c](r) for c in meta.required_capabilities)]
        cfg = get_llm_config_for_agent(settings, slot)
        ok = cfg.model in {r.model_name for r in eligible}
        print(f'{slot:30s} eligible={len(eligible):3d} current={cfg.model:22s} qualifies={ok}')
asyncio.run(main())"
```
Expected: no slot has `eligible=0`, and every `qualifies=True`. **If any is False, stop** — a declaration is wrong or the model is.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/domains/llm_config/constants.py apps/api/src/domains/llm_config/service.py apps/api/tests/unit/domains/llm_config/test_capability_checks.py
git commit -m "feat(llm): declare the five structured-output slots and refuse unknown capabilities (ADR-244)"
```

---

### Task 2: The capability gate — one decision, two behaviours

**Files:**
- Create: `apps/api/src/infrastructure/llm/capability_gate.py`
- Create: `apps/api/tests/unit/infrastructure/llm/test_capability_gate.py`
- Modify: `apps/api/src/core/llm_config_helper.py` (call it from `get_llm_config_for_agent`'s result path)

**Interfaces:**
- Consumes: `LLM_TYPES_REGISTRY`, `ModelCapabilitiesCache`.
- Produces:
  `GateVerdict` (frozen dataclass: `satisfied: bool`, `missing: tuple[str, ...]`, `wrong_kind: bool`),
  `evaluate_slot_fit(slot: str, model: str) -> GateVerdict | None` (None when the model is unknown to the cache),
  `report_configured_model(slot: str, model: str) -> None` (warning-only path).

**Why:** the gate must exist and be exercised *before* Lot 1 gives it candidates to filter, so that Lot 1 adds a caller rather than a mechanism. The two behaviours are load-bearing and the spec's v2 got them backwards: an explicit human choice is never rejected, only reported.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/test_capability_gate.py`:

```python
"""One decision about model fit, two behaviours depending on where it came from."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.infrastructure.llm.capability_gate import (
    GateVerdict,
    evaluate_slot_fit,
    report_configured_model,
)
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile


@pytest.fixture(autouse=True)
def _restore_cache() -> Generator[None]:
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


def _install(model: str, **caps: object) -> None:
    ModelCapabilitiesCache._cache[model] = ModelProfile(model_id=model, **caps)  # type: ignore[arg-type]


def test_a_fitting_model_satisfies_the_slot() -> None:
    _install("fits", supports_structured_output=True, kind="chat")
    verdict = evaluate_slot_fit("query_analyzer", "fits")
    assert verdict == GateVerdict(satisfied=True, missing=(), wrong_kind=False)


def test_a_missing_capability_is_named() -> None:
    _install("blind", supports_vision=False, kind="chat")
    verdict = evaluate_slot_fit("vision_analysis", "blind")
    assert verdict is not None
    assert verdict.satisfied is False
    assert verdict.missing == ("vision",)


def test_a_wrong_kind_is_reported_separately() -> None:
    """``required_kind`` and ``required_capabilities`` are different failures."""
    _install("a-chat-model", supports_vision=True, kind="chat")
    verdict = evaluate_slot_fit("image_generation", "a-chat-model")
    assert verdict is not None
    assert verdict.wrong_kind is True


def test_an_unknown_model_yields_no_verdict() -> None:
    """No profile means no evidence — never a rejection."""
    ModelCapabilitiesCache._cache.pop("ghost", None)
    assert evaluate_slot_fit("query_analyzer", "ghost") is None


def test_an_unknown_slot_yields_no_verdict() -> None:
    _install("fits", supports_structured_output=True, kind="chat")
    assert evaluate_slot_fit("not-a-slot", "fits") is None


def test_reporting_a_configured_model_never_raises() -> None:
    """A human decision is counted and logged, never overridden."""
    _install("blind", supports_vision=False, kind="chat")
    report_configured_model("vision_analysis", "blind")  # must not raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_capability_gate.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... capability_gate`.

- [ ] **Step 3: Write the gate**

Create `apps/api/src/infrastructure/llm/capability_gate.py`:

```python
"""Does this model satisfy what the slot declares, and what follows from that.

The verdict is one computation; what happens next depends entirely on where the
model came from, and that distinction is load-bearing:

- a **policy candidate** (a model the system proposed to itself) is hard
  filtered — skip it and try the next;
- a model that came from ``LLM_DEFAULTS`` or from an admin override is a
  **human decision**. It is never rejected: the discrepancy is counted and
  logged so it is visible, and the call proceeds.

Getting that backwards breaks working features. It nearly did: before the
catalogue correction, ``vision_analysis``'s own default ``gpt-5-mini`` was
recorded as ``supports_vision=false``, and a gate applied to explicit
configuration would have disabled image analysis over a column default.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: capability name -> the ``ModelProfile`` attribute that answers it. Mirrors
#: ``llm_config.service._CAPABILITY_CHECKS``, over the runtime profile rather
#: than the API schema; the vocabulary guard pins the two together.
_CAPABILITY_ATTRS: dict[str, str] = {
    "vision": "supports_vision",
    "tools": "supports_tool_calling",
    "structured_output": "supports_structured_output",
}


@dataclass(frozen=True)
class GateVerdict:
    """Whether a model fits a slot, and precisely how it does not."""

    satisfied: bool
    missing: tuple[str, ...]
    wrong_kind: bool


def _verdict(slot_capabilities: list[str], required_kind: str, caps: ModelProfile) -> GateVerdict:
    missing = tuple(
        capability
        for capability in slot_capabilities
        if not getattr(caps, _CAPABILITY_ATTRS[capability])
    )
    wrong_kind = caps.kind != required_kind
    return GateVerdict(satisfied=not missing and not wrong_kind, missing=missing, wrong_kind=wrong_kind)


def evaluate_slot_fit(slot: str, model: str) -> GateVerdict | None:
    """Return how ``model`` fits ``slot``, or ``None`` when there is no evidence.

    Args:
        slot: An ``LLM_TYPES_REGISTRY`` key.
        model: A model name.

    Returns:
        The verdict, or ``None`` when the slot is unknown or the model has no
        profile. Absence of evidence is never a rejection — a model outside the
        catalogue (a live Ollama pull, for instance) must stay usable.
    """
    metadata = LLM_TYPES_REGISTRY.get(slot)
    caps = ModelCapabilitiesCache.get(model)
    if metadata is None or caps is None:
        return None
    return _verdict(metadata.required_capabilities, metadata.required_kind.value, caps)


def report_configured_model(slot: str, model: str) -> None:
    """Count and log a configured model that does not satisfy its slot.

    Never raises and never substitutes: the model was chosen by a human, and
    silently overriding that is the failure this function exists to avoid. The
    counter is what makes the discrepancy visible on the slot's admin card.
    """
    verdict = evaluate_slot_fit(slot, model)
    if verdict is None or verdict.satisfied:
        return
    logger.warning(
        "llm_configured_model_capability_mismatch",
        llm_type=slot,
        model=model,
        missing=list(verdict.missing),
        wrong_kind=verdict.wrong_kind,
    )
    from src.infrastructure.observability.metrics import llm_capability_mismatch_total

    llm_capability_mismatch_total.labels(llm_type=slot).inc()
```

- [ ] **Step 4: Declare the counter**

In `apps/api/src/infrastructure/observability/metrics.py`, next to the other `llm_*` counters, add:

```python
llm_capability_mismatch_total = Counter(
    "llm_capability_mismatch_total",
    "Configured model does not satisfy its slot's declared capabilities",
    ["llm_type"],
)
```

`llm_type` is bounded by `LLM_TYPES_REGISTRY`; never label this with `node_name`, whose cardinality is unbounded (101 distinct values measured, some carrying prompt fragments).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_capability_gate.py -q --no-cov`
Expected: 6 passed.

- [ ] **Step 6: Wire the warning-only path**

In `apps/api/src/core/llm_config_helper.py`, at the end of `get_llm_config_for_agent`, before returning:

```python
    # Report only — never reject. See capability_gate's module docstring.
    from src.infrastructure.llm.capability_gate import report_configured_model

    if effective.model:
        report_configured_model(agent_type, effective.model)
```

- [ ] **Step 7: Verify the live configuration is silent**

Run: `docker exec -e PYTHONPATH=/app -w /app lia-api-dev python /tmp/probe9.py` (the Task 1 Step 6 probe)
Expected: `0 slot(s) already violate their own declaration` — so the counter stays at zero on the reference configuration. Record the number in the commit body.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/infrastructure/llm/capability_gate.py apps/api/src/infrastructure/observability/metrics.py apps/api/src/core/llm_config_helper.py apps/api/tests/unit/infrastructure/llm/test_capability_gate.py
git commit -m "feat(llm): capability gate — hard for candidates, reported for human choices (ADR-244)"
```

---

### Task 3: `supports_strict_mode` gets a reader, arbitrated by provenance

**Files:**
- Modify: `apps/api/src/infrastructure/llm/structured_output.py:600-602`
- Test: `apps/api/tests/unit/infrastructure/llm/test_structured_output_strict_mode.py` (create)

**Interfaces:**
- Consumes: `ModelProfile.capability_provenance`, `ModelProfile.supports_strict_mode` (both from Lot 0a).

**Why:** the column exists, travels through the import sheet and has six translations, and **no runtime reader**. The runtime decides on `provider == "openai"` alone. Turning the column on naively would regress every one of the 83 rows whose `false` is an unfilled default — the registries publish nothing about strict mode, so those rows stay `declared` on that field. The provenance is what distinguishes an unfilled default from a decision.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/test_structured_output_strict_mode.py`:

```python
"""Strict mode reads the column only when someone actually filled it."""

from __future__ import annotations

from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.structured_output import resolve_strict_mode


def test_declared_row_keeps_the_provider_heuristic() -> None:
    """83 rows carry an unfilled ``false``; believing it would regress them all."""
    caps = ModelProfile(supports_strict_mode=False, capability_provenance="declared")
    assert resolve_strict_mode(True, "openai", caps) is True


def test_a_filled_false_narrows() -> None:
    caps = ModelProfile(supports_strict_mode=False, capability_provenance="verified")
    assert resolve_strict_mode(True, "openai", caps) is False


def test_a_filled_true_is_honoured() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="imported")
    assert resolve_strict_mode(True, "openai", caps) is True


def test_a_non_openai_provider_never_uses_strict_mode() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="verified")
    assert resolve_strict_mode(True, "anthropic", caps) is False


def test_an_incompatible_schema_never_uses_strict_mode() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="verified")
    assert resolve_strict_mode(False, "openai", caps) is False


def test_no_profile_keeps_the_provider_heuristic() -> None:
    assert resolve_strict_mode(True, "openai", None) is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_structured_output_strict_mode.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'resolve_strict_mode'`.

- [ ] **Step 3: Write the reader**

In `apps/api/src/infrastructure/llm/structured_output.py`, above the call site, add:

```python
def resolve_strict_mode(
    is_strict_compatible: bool,
    provider: str,
    caps: ModelProfile | None,
) -> bool:
    """Decide whether to ask OpenAI for strict structured output.

    Three conditions, in order of authority. The schema must be compatible and
    the provider must be OpenAI — strict mode is an OpenAI feature and no other
    provider accepts the flag. Then, and only then, the catalogue may *narrow*
    the answer.

    It may narrow it only when someone filled the column. Measured 2026-08-23:
    83 catalogue rows carry ``supports_strict_mode=false``, which is the column
    default, and no public registry publishes the field — so those rows stay
    ``declared`` on it forever. Believing an unfilled default would switch every
    one of them off the strict path in one commit. ``declared`` therefore keeps
    today's provider heuristic exactly, and only ``imported``/``verified``
    narrows.

    Args:
        is_strict_compatible: Whether the schema itself can be strict.
        provider: The resolved provider id.
        caps: The model's profile, or ``None`` when it is outside the catalogue.

    Returns:
        Whether to pass ``strict=True``.
    """
    if not is_strict_compatible or provider != "openai":
        return False
    if caps is None or caps.capability_provenance == CAPABILITY_PROVENANCE_DECLARED:
        return True
    return caps.supports_strict_mode
```

Add `from src.core.constants import CAPABILITY_PROVENANCE_DECLARED` and `from src.infrastructure.llm.model_profiles import ModelProfile` to the imports if absent.

- [ ] **Step 4: Use it at the call site**

Replace:

```python
    is_strict_compatible, strict_reason = _analyze_schema_strict_compatibility(schema)
    use_strict_mode = is_strict_compatible and provider == "openai"
```

with:

```python
    is_strict_compatible, strict_reason = _analyze_schema_strict_compatibility(schema)
    use_strict_mode = resolve_strict_mode(is_strict_compatible, provider, get_model_profile(llm, provider, model))
```

and add `provenance=...` to the existing debug log so the decision is explainable:

```python
    logger.debug(
        "using_native_structured_output",
        provider=provider,
        schema=schema_name,
        strict_compatible=is_strict_compatible,
        strict_reason=strict_reason,
        use_strict_mode=use_strict_mode,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/ -q --no-cov`
Expected: all passed, including the existing structured-output suites.

- [ ] **Step 6: Verify no live model changes behaviour**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
import asyncio
from sqlalchemy import select
from src.domains.llm.models import LLMModel
from src.infrastructure.database.session import get_db_context
async def main():
    async with get_db_context() as db:
        rows = list((await db.execute(select(LLMModel).where(LLMModel.is_active))).scalars().all())
    openai = [r for r in rows if r.provider.value == 'openai']
    narrowing = [r.model_name for r in openai
                 if r.capability_provenance.value != 'declared' and not r.supports_strict_mode]
    print(f'openai rows={len(openai)} that now LOSE strict mode: {len(narrowing)}')
    for n in narrowing[:10]: print('  ', n)
asyncio.run(main())"
```
Expected: a list. **Every name on it is a behaviour change** — read it before continuing, and if a configured slot's model appears, record why the narrowing is right in the commit body.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/infrastructure/llm/structured_output.py apps/api/tests/unit/infrastructure/llm/test_structured_output_strict_mode.py
git commit -m "feat(llm): supports_strict_mode gets a reader, arbitrated by provenance (ADR-244)"
```

---

### Task 4: Four observation columns

**Files:**
- Modify: `apps/api/src/domains/chat/models.py` (`TokenUsageLog`)
- Create: `apps/api/alembic/versions/2026_08_25_0900-c2d3e4f5a6b7_token_usage_observation.py`
- Test: `apps/api/tests/unit/domains/chat/test_token_usage_observation_columns.py`

**Interfaces:**
- Produces: `TokenUsageLog.latency_ms`, `.status`, `.failure_kind`, `.llm_type`, and the index `ix_token_usage_logs_controller_window`.

**Why:** they are the objective failure signal §2.6 asked for, they cost nothing (every value already exists in memory), and `llm_type` is what lets an aggregate group by *slot*. `node_name` cannot: it carries 101 distinct unbounded values, some containing French prompt fragments.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/domains/chat/test_token_usage_observation_columns.py`:

```python
"""The four facts a model policy needs to judge a model, and their index."""

from __future__ import annotations

from src.domains.chat.models import TokenUsageLog


def test_the_columns_exist_and_are_nullable() -> None:
    """Nullable with no backfill: history is admitted absent, never invented."""
    columns = TokenUsageLog.__table__.columns
    for name in ("latency_ms", "status", "failure_kind", "llm_type"):
        assert name in columns, name
        assert columns[name].nullable is True, name


def test_the_controller_window_index_is_declared() -> None:
    """The aggregate groups by SLOT — never by node_name (unbounded)."""
    names = {index.name for index in TokenUsageLog.__table__.indexes}
    assert "ix_token_usage_logs_controller_window" in names


def test_the_lifetime_index_is_untouched() -> None:
    names = {index.name for index in TokenUsageLog.__table__.indexes}
    assert "ix_token_usage_logs_lifetime_aggregation" in names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/chat/test_token_usage_observation_columns.py -v --no-cov`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Add the columns and the index**

In `apps/api/src/domains/chat/models.py`, after `usd_to_eur_rate`, add:

```python
    # Observation columns (ADR-244). Nullable, no backfill: they describe calls
    # made after the migration, and inventing history would be worse than
    # admitting its absence.
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Wall time of the LLM call in milliseconds"
    )
    status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="success / error"
    )
    failure_kind: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="LLM_FAILURE_KINDS member when status='error', NULL otherwise",
    )
    llm_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "The configured slot from LLM_TYPES_REGISTRY. Aggregates group by "
            "this, never by node_name, whose values are unbounded free text"
        ),
    )
```

and to `__table_args__`:

```python
        # Controller window: the most recent calls of one (slot, model) pair.
        # node_name is deliberately absent — 101 distinct values were measured,
        # 28 of them carrying free text, so an index on it would neither be
        # selective nor safe to expose.
        Index(
            "ix_token_usage_logs_controller_window",
            "llm_type",
            "model_name",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
```

Update the class docstring's `Attributes:` block with the four new fields.

- [ ] **Step 4: Create the migration**

Create `apps/api/alembic/versions/2026_08_25_0900-c2d3e4f5a6b7_token_usage_observation.py`:

```python
"""Observation columns on token_usage_logs (ADR-244, Lot 0b).

Four nullable columns and one index. No backfill: they describe calls made
after this migration. ``llm_type`` is the configured slot, from the closed
LLM_TYPES_REGISTRY vocabulary — aggregates group by it and never by
``node_name``, which carries 101 distinct unbounded values.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-25 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the four observation columns and the controller-window index."""
    op.add_column(
        "token_usage_logs",
        sa.Column("latency_ms", sa.Integer(), nullable=True, comment="Wall time of the LLM call in milliseconds"),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column("status", sa.String(length=16), nullable=True, comment="success / error"),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "failure_kind",
            sa.String(length=32),
            nullable=True,
            comment="LLM_FAILURE_KINDS member when status='error', NULL otherwise",
        ),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "llm_type",
            sa.String(length=64),
            nullable=True,
            comment="The configured slot from LLM_TYPES_REGISTRY",
        ),
    )
    op.create_index(
        "ix_token_usage_logs_controller_window",
        "token_usage_logs",
        ["llm_type", "model_name", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """Drop the index and the four columns."""
    op.drop_index("ix_token_usage_logs_controller_window", table_name="token_usage_logs")
    for column in ("llm_type", "failure_kind", "status", "latency_ms"):
        op.drop_column("token_usage_logs", column)
```

- [ ] **Step 5: Apply and verify a single head**

Run: `docker exec -w /app lia-api-dev alembic upgrade head`
Then: `docker exec -w /app lia-api-dev alembic heads`
Expected: exactly one head, `c2d3e4f5a6b7`.

- [ ] **Step 6: Run the tests and the replay**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/chat/test_token_usage_observation_columns.py -q --no-cov`
Then: `task db:migrate:replay-check`
Expected: 3 passed; replay OK.

Note: the DESC-ordered index must be added to the `schema_drift` exclusion list beside `ix_token_usage_logs_lifetime_aggregation` — reflection cannot match `postgresql_ops`. If `task db:migrate:replay-check` reports drift on it, that exclusion is the fix, not a change to the index.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/domains/chat/models.py apps/api/alembic/versions/2026_08_25_0900-c2d3e4f5a6b7_token_usage_observation.py apps/api/tests/unit/domains/chat/test_token_usage_observation_columns.py
git commit -m "feat(chat): observation columns on token_usage_logs (ADR-244)"
```

---

### Task 5: Fill them — the slot is already in the metadata

**Files:**
- Create: `apps/api/src/infrastructure/observability/error_taxonomy.py`
- Modify: `apps/api/src/infrastructure/observability/callbacks.py` (`_classify_llm_error` moves; `TokenTrackingCallback` gains `llm_type`, `status` and `on_llm_error`)
- Modify: `apps/api/src/domains/chat/service.py` (`TokenUsageRecord`, `record_node_tokens`)
- Modify: `apps/api/src/domains/chat/repository.py` (`bulk_create_token_logs`)
- Test: `apps/api/tests/unit/infrastructure/observability/test_token_tracking_observation.py`

**Interfaces:**
- Consumes: the columns from Task 4.
- Produces: `LLM_FAILURE_KINDS: frozenset[str]`, `classify_llm_error(error) -> str` in `error_taxonomy`.

**Why:** every value already exists at the point of the call. `create_instrumented_config` puts `llm_type` in the run metadata at **every** instrumented call site (`instrumentation.py`, `enriched_metadata["llm_type"]`), `duration_ms` is already computed for the debug panel, and `MetricsCallbackHandler._classify_llm_error` already produces the failure vocabulary. Nothing needs to be invented; it needs to be persisted.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/observability/test_token_tracking_observation.py`:

```python
"""The slot, the latency and the outcome reach the ledger."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.infrastructure.observability.error_taxonomy import LLM_FAILURE_KINDS, classify_llm_error


class _Tracker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_node_tokens(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _callback(tracker: _Tracker):  # type: ignore[no-untyped-def]
    from src.infrastructure.observability.callbacks import TokenTrackingCallback

    return TokenTrackingCallback(tracker, "run-1")  # type: ignore[arg-type]


async def test_the_slot_travels_from_the_run_metadata() -> None:
    """``create_instrumented_config`` already puts ``llm_type`` there."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [[]], run_id=run_id, metadata={"langgraph_node": "response", "llm_type": "response"}
    )
    assert callback._call_context[str(run_id)]["llm_type"] == "response"


async def test_a_failed_call_records_status_and_kind() -> None:
    """A failure produces a zero-token row: the ledger must show it happened."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [[]], run_id=run_id, metadata={"langgraph_node": "response", "llm_type": "response"}
    )
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)

    assert len(tracker.calls) == 1
    recorded = tracker.calls[0]
    assert recorded["status"] == "error"
    assert recorded["failure_kind"] == "timeout"
    assert recorded["prompt_tokens"] == 0
    assert recorded["llm_type"] == "response"


async def test_an_error_is_recorded_once() -> None:
    """The same idempotency guard as ``on_llm_end`` — handlers can double-attach."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start({}, [[]], run_id=run_id, metadata={})
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)
    assert len(tracker.calls) == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("x"), "timeout"),
        (ValueError("rate_limit exceeded"), "rate_limit"),
        (RuntimeError("something else"), "unknown"),
    ],
)
def test_the_taxonomy_is_the_one_the_metrics_already_use(
    error: BaseException, expected: str
) -> None:
    assert classify_llm_error(error) == expected
    assert expected in LLM_FAILURE_KINDS


def test_every_kind_fits_the_column() -> None:
    """``failure_kind`` is ``String(32)``."""
    assert all(len(kind) <= 32 for kind in LLM_FAILURE_KINDS)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/observability/test_token_tracking_observation.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... error_taxonomy`.

- [ ] **Step 3: Extract the taxonomy**

Create `apps/api/src/infrastructure/observability/error_taxonomy.py` holding the body of the current `MetricsCallbackHandler._classify_llm_error` as a module-level `classify_llm_error(error: BaseException) -> str`, plus:

```python
#: The closed vocabulary. One declaration, so the Prometheus label and the
#: ``token_usage_logs.failure_kind`` column can never disagree — and so a new
#: kind cannot silently exceed the column's ``String(32)``.
LLM_FAILURE_KINDS: frozenset[str] = frozenset(
    {
        "rate_limit",
        "timeout",
        "invalid_request",
        "context_length_exceeded",
        "authentication",
        "content_filter",
        "model_not_found",
        "api_error",
        "unknown",
    }
)
```

In `callbacks.py`, replace the static method body with a delegation so there is exactly one implementation:

```python
    @staticmethod
    def _classify_llm_error(error: BaseException) -> str:
        """Delegate to the shared taxonomy (see ``error_taxonomy``)."""
        return classify_llm_error(error)
```

- [ ] **Step 4: Carry the slot and the outcome**

In `TokenTrackingCallback._store_call_context`, add the slot:

```python
        self._call_context[str(run_id)] = {
            "node_name": node_name,
            # The slot, put there by create_instrumented_config at every
            # instrumented call site. node_name cannot substitute for it: it is
            # the graph node, not the configured slot, and its values are
            # unbounded.
            "llm_type": md.get("llm_type"),
            "start_time": time.time(),
        }
```

In `on_llm_end`, read it and pass the three new values:

```python
            await self.tracker.record_node_tokens(
                node_name=node_name,
                model_name=usage_data.model_name,
                prompt_tokens=usage_data.input_tokens,
                completion_tokens=usage_data.output_tokens,
                cached_tokens=usage_data.cached_tokens,
                duration_ms=duration_ms,
                started_at=start_time if start_time > 0 else None,
                llm_type=call_ctx.get("llm_type"),
                status="success",
            )
```

Add the error handler beside it:

```python
    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Record a failed call as a zero-token row.

        A failure produces no usage metadata, so without this the ledger simply
        has no trace that the call happened — and a policy that only ever sees
        successes cannot tell a model that works from one that never answers.
        The row carries zero tokens and zero cost: it is an observation, not a
        charge.
        """
        run_id_str = str(run_id)
        if run_id_str in self._recorded_llm_run_ids:
            return
        self._recorded_llm_run_ids.add(run_id_str)

        call_ctx = self._call_context.pop(run_id_str, {})
        start_time = call_ctx.get("start_time", 0.0)
        duration_ms = (time.time() - start_time) * 1000 if start_time > 0 else 0.0
        failure_kind = classify_llm_error(error)

        logger.warning(
            "token_tracking_llm_error",
            run_id=self.run_id,
            llm_run_id=run_id_str,
            node_name=call_ctx.get("node_name", "unknown"),
            llm_type=call_ctx.get("llm_type"),
            failure_kind=failure_kind,
        )
        with suppress(Exception):
            await self.tracker.record_node_tokens(
                node_name=call_ctx.get("node_name", "unknown"),
                model_name="unknown",
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=0,
                duration_ms=duration_ms,
                started_at=start_time if start_time > 0 else None,
                llm_type=call_ctx.get("llm_type"),
                status="error",
                failure_kind=failure_kind,
            )
```

The `suppress` is deliberate and matches the existing `on_llm_end` guard: token tracking must never turn a provider failure into a second, different failure. Put the justification comment above the block, per the empty-except doctrine.

- [ ] **Step 5: Widen the record and the row**

In `apps/api/src/domains/chat/service.py`, add to `TokenUsageRecord`:

```python
    # Observation fields (ADR-244) — persisted to token_usage_logs.
    llm_type: str | None = None
    status: str | None = None
    failure_kind: str | None = None
```

and the matching keyword-only parameters on `record_node_tokens`, defaulting to `None`, forwarded into the record. In the `logs_data` comprehension feeding `bulk_create_token_logs`, add:

```python
                "latency_ms": int(record.duration_ms) if record.duration_ms else None,
                "llm_type": record.llm_type,
                "status": record.status,
                "failure_kind": record.failure_kind,
```

In `apps/api/src/domains/chat/repository.py`, add the four to the `TokenUsageLog(...)` construction with `log_data.get(...)`, and to the docstring's key list.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/observability/ tests/unit/domains/chat/ -q --no-cov`
Expected: all passed.

- [ ] **Step 7: Measure the real coverage of `llm_type`**

Restart the API, exercise one chat turn, then:
```bash
docker exec lia-postgres-dev psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select coalesce(llm_type,'(null)') as slot, status, count(*), round(avg(latency_ms)) as avg_ms
from token_usage_logs where created_at > now() - interval '10 minutes'
group by 1,2 order by 3 desc;"
```
Expected: most rows carry a non-null `llm_type`. **Record the null fraction in the commit body** — it is the honest measure of how many call sites go through `create_instrumented_config`, and Lot 1's aggregates inherit exactly that blind spot. Do not paper over it.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/infrastructure/observability/error_taxonomy.py apps/api/src/infrastructure/observability/callbacks.py apps/api/src/domains/chat/service.py apps/api/src/domains/chat/repository.py apps/api/tests/unit/infrastructure/observability/test_token_tracking_observation.py
git commit -m "feat(observability): persist slot, latency and outcome per LLM call (ADR-244)"
```

---

### Task 6: The failover chain is asserted at boot

**Files:**
- Modify: `apps/api/src/infrastructure/startup/agents.py`
- Modify: `apps/api/src/domains/agents/graphs/base_agent_builder.py` (consume the verdict)
- Test: `apps/api/tests/unit/infrastructure/startup/test_failover_assert.py`

**Interfaces:**
- Produces: `assert_failover_chain(settings) -> list[str]` — the usable subset, empty when nothing is usable.

**Why:** `FALLBACK_MODELS_DEFAULT` named a model absent from the catalogue and one that was deactivated, so the chain had no reachable target and nothing said so. Lot 0a retargeted the constant; this makes the property permanent, and at the only moment it can be checked against the real catalogue.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/startup/test_failover_assert.py`:

```python
"""A failover chain that cannot fail over must say so, not pretend."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.startup.agents import assert_failover_chain


@pytest.fixture(autouse=True)
def _restore_cache() -> Generator[None]:
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


class _Settings:
    def __init__(self, chain: str) -> None:
        self.fallback_models = chain


def test_a_reachable_chain_survives_intact() -> None:
    ModelCapabilitiesCache._cache["alive"] = ModelProfile(model_id="alive")
    assert assert_failover_chain(_Settings("alive")) == ["alive"]


def test_an_unreachable_entry_is_dropped_not_kept() -> None:
    ModelCapabilitiesCache._cache["alive"] = ModelProfile(model_id="alive")
    ModelCapabilitiesCache._cache.pop("ghost", None)
    assert assert_failover_chain(_Settings("ghost,alive")) == ["alive"]


def test_an_entirely_unreachable_chain_returns_empty() -> None:
    """Empty disables the middleware — it never raises, a boot must not fail."""
    ModelCapabilitiesCache._cache.clear()
    assert assert_failover_chain(_Settings("ghost,phantom")) == []


def test_an_empty_setting_is_not_an_error() -> None:
    assert assert_failover_chain(_Settings("")) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/startup/test_failover_assert.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'assert_failover_chain'`.

- [ ] **Step 3: Write the assertion**

In `apps/api/src/infrastructure/startup/agents.py`:

```python
def assert_failover_chain(settings: Settings) -> list[str]:
    """Return the failover entries the catalogue can actually serve.

    Assert, not crash. A broken failover list is a configuration defect worth
    shouting about, but it must never prevent a boot: the primary model works,
    and refusing to start would turn a degraded fallback into a total outage.

    Measured 2026-08-23 before ADR-244 retargeted it: the shipped chain named
    ``claude-sonnet-4-5``, absent from the catalogue entirely, and
    ``deepseek-chat``, deactivated — so the chain had no reachable target at
    all, and nothing anywhere said so.

    Args:
        settings: The resolved settings (reads ``fallback_models``).

    Returns:
        The usable subset, in the configured order. Empty means the caller
        must disable the failover middleware rather than mount a chain that
        cannot fire.
    """
    configured = [part.strip() for part in settings.fallback_models.split(",") if part.strip()]
    usable = [name for name in configured if ModelCapabilitiesCache.get(name) is not None]
    unreachable = [name for name in configured if name not in usable]
    if unreachable:
        logger.error(
            "llm_failover_chain_unreachable",
            unreachable=unreachable,
            usable=usable,
            msg="these fallback models are absent from the active catalogue",
        )
    if configured and not usable:
        logger.error(
            "llm_failover_chain_empty",
            configured=configured,
            msg="failover disabled: no configured fallback model is reachable",
        )
    return usable
```

Call it in the lifespan step that builds the agent registry, after `ModelCapabilitiesCache.load_from_db`, and store the result where `base_agent_builder` reads the chain.

- [ ] **Step 4: Consume the verdict**

In `apps/api/src/domains/agents/graphs/base_agent_builder.py`, where the fallback middleware is mounted, mount it only when the asserted chain is non-empty, and log `llm_failover_disabled` otherwise.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/startup/test_failover_assert.py -q --no-cov`
Expected: 4 passed.

- [ ] **Step 6: Verify at runtime**

Restart the API and run:
```bash
docker logs --since 3m lia-api-dev 2>&1 | grep -E 'llm_failover_chain|llm_failover_disabled'
```
Expected: **no line** — the retargeted chain is fully reachable. Then temporarily set `FALLBACK_MODELS=ghost` in the container environment, restart, confirm `llm_failover_chain_empty` appears **and the API still becomes healthy**, and restore.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/infrastructure/startup/agents.py apps/api/src/domains/agents/graphs/base_agent_builder.py apps/api/tests/unit/infrastructure/startup/test_failover_assert.py
git commit -m "feat(llm): assert the failover chain at boot instead of pretending (ADR-244)"
```

---

### Task 7: Delete what nothing calls

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py` (remove the `router` and `context_resolver` entries from `LLM_TYPES_REGISTRY` and `LLM_DEFAULTS`)
- Modify: `apps/api/src/infrastructure/llm/factory.py` (`LLMType` Literal)
- Modify: `apps/api/src/domains/llm_config/install_contract.py` (`CURRENT_CORE_LLM_TYPES`)
- Modify: `apps/api/src/core/bootstrap.py` (`required_llm_types`)
- Modify: `apps/api/src/domains/agents/graphs/base_agent_builder.py:250` (the silent fallback)
- Modify: `infrastructure/database/seeds/llm_config_seed.sql` (the two rows and the `mcp_excalidraw` orphan)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (the six keys ×2 slots)
- Create: `apps/api/tests/unit/test_llm_slot_vocabulary_guard.py`

**Why:** `router` and `context_resolver` have no `get_llm()` caller — all six occurrences of `get_llm("router")` are docstrings — yet both are listed in `CURRENT_CORE_LLM_TYPES`, which drives the installer questionnaire. An unwired subsystem with settings, i18n and seed rows attached costs maintenance on every change and fakes coverage.

**Measured safe:** both resolve to `openai`, which four surviving core slots also resolve to, so the derived provider set is unchanged (`['deepseek', 'openai']` before and after) and the questionnaire is untouched.

- [ ] **Step 1: Write the guard first**

Create `apps/api/tests/unit/test_llm_slot_vocabulary_guard.py`:

```python
"""One slot vocabulary, named identically everywhere it is named.

Four places declare slots — ``LLM_TYPES_REGISTRY``, ``LLM_DEFAULTS``, the
``LLMType`` Literal and ``llm_config_seed.sql`` — and nothing forced them to
agree. They did not: ``mcp_excalidraw`` had a seed row and no registry entry,
and ``router``/``context_resolver`` had registry entries, defaults, seed rows,
six translations each and no caller at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.install_contract import CURRENT_CORE_LLM_TYPES

pytestmark = pytest.mark.unit

_SEED = (
    Path(__file__).resolve().parents[3].parent
    / "infrastructure"
    / "database"
    / "seeds"
    / "llm_config_seed.sql"
)
_CONFIG_ROW = re.compile(r"^\s*\(gen_random_uuid\(\),\s*'([^']+)',", re.MULTILINE)


def _seed_slots() -> set[str]:
    return set(_CONFIG_ROW.findall(_SEED.read_text(encoding="utf-8")))


def test_the_parser_finds_rows() -> None:
    assert len(_seed_slots()) >= 30


def test_registry_and_defaults_declare_the_same_slots() -> None:
    assert set(LLM_TYPES_REGISTRY) == set(LLM_DEFAULTS)


def test_no_seed_row_is_an_orphan() -> None:
    orphans = sorted(_seed_slots() - set(LLM_TYPES_REGISTRY))
    assert orphans == [], f"seed rows for slots that do not exist: {orphans}"


def test_the_install_contract_names_real_slots() -> None:
    unknown = sorted(set(CURRENT_CORE_LLM_TYPES) - set(LLM_TYPES_REGISTRY))
    assert unknown == [], f"CURRENT_CORE_LLM_TYPES names removed slots: {unknown}"


def test_the_literal_matches_the_registry() -> None:
    from typing import get_args

    from src.infrastructure.llm.factory import LLMType

    assert set(get_args(LLMType)) == set(LLM_TYPES_REGISTRY)
```

- [ ] **Step 2: Run it to see the drift it already catches**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_llm_slot_vocabulary_guard.py -v --no-cov`
Expected: FAIL on `test_no_seed_row_is_an_orphan` (`mcp_excalidraw`). **This failure is the point.**

- [ ] **Step 3: Remove the two slots**

Delete the `"router"` and `"context_resolver"` entries from `LLM_TYPES_REGISTRY` and from `LLM_DEFAULTS`; remove them from the `LLMType` Literal; remove them from `CURRENT_CORE_LLM_TYPES`; remove `"router"` from `bootstrap.py`'s `required_llm_types` and the `router_model=` field from its log call; delete the legacy `context_resolver_llm_*` settings from `src/core/config/`; delete their rows from `llm_config_seed.sql`; delete the six `settings.admin.llmConfig.types.router` and `…context_resolver` keys from each of the six locale files.

- [ ] **Step 4: Remove the orphan seed row**

Delete the `mcp_excalidraw` row from `llm_config_seed.sql`.

- [ ] **Step 5: Close the silent fallback**

In `apps/api/src/domains/agents/graphs/base_agent_builder.py`, replace:

```python
    llm_type = llm_type_map.get(agent_name, "contact_agent")
```

with:

```python
    llm_type = llm_type_map.get(agent_name)
    if llm_type is None:
        # A silent default here sent an unmapped agent's calls to the contacts
        # slot's configuration — wrong model, wrong budget, wrong cost line, and
        # nothing said so. Naming the agent is the whole remediation.
        raise KeyError(
            f"agent {agent_name!r} has no llm_type mapping; add it to llm_type_map"
        )
```

- [ ] **Step 6: Verify the install contract is unchanged**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
from src.domains.llm_config.install_contract import CURRENT_CORE_LLM_TYPES, CURRENT_CORE_PROVIDER_IDS, provider_for_llm_type
derived = sorted({provider_for_llm_type(t) for t in CURRENT_CORE_LLM_TYPES})
print('derived  :', derived)
print('declared :', sorted(CURRENT_CORE_PROVIDER_IDS))
assert derived == sorted(CURRENT_CORE_PROVIDER_IDS), 'the questionnaire would change'"
```
Expected: `['deepseek', 'openai']` on both lines. **If they differ, stop** — the installer questionnaire changes and that is a separate decision.

- [ ] **Step 7: Run the guard, the suite and i18n parity**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_llm_slot_vocabulary_guard.py -q --no-cov`
Then: `task test:backend:unit:fast`
Then: `task lint:i18n`
Expected: all green. The slot count drops from 58 to 56; any test asserting 58 is updated in this commit with the reason.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src apps/web/locales infrastructure/database/seeds/llm_config_seed.sql apps/api/tests/unit/test_llm_slot_vocabulary_guard.py
git commit -m "refactor(llm): delete the two dead slots, the orphan seed row and the silent fallback (ADR-244)"
```

---

### Task 8: Lot acceptance

**Files:** none — verification only.

- [ ] **Step 1: Every gate that needs no service**

Run: `task ci:fast`
Expected: green.

- [ ] **Step 2: The migration replays**

Run: `task db:migrate:replay-check`
Expected: OK.

- [ ] **Step 3: The app boots and the graph builds**

Run: `docker compose -f docker-compose.dev.yml up -d lia-api-dev` (not `docker restart` — it does not re-read `env_file`), then poll health from inside the container and check the logs.
Expected: `{"status":"healthy"}`, `graph_built_successfully`, `agents_registered` at its new count, zero `"level": "error"` lines.

- [ ] **Step 4: A guard actually reds on a reverted fix**

Re-add the `mcp_excalidraw` row to `llm_config_seed.sql`, confirm `test_llm_slot_vocabulary_guard.py` FAILS, then restore. Do the same by re-emptying one of the five `required_capabilities` declarations against `test_capability_checks.py`.

- [ ] **Step 5: The observation columns actually fill**

Exercise one chat turn, then run the Task 5 Step 7 query. Record the `llm_type` null fraction and the p95 latency per slot.

- [ ] **Step 6: Commit the acceptance record**

```bash
git commit --allow-empty -m "chore(llm): Lot 0b acceptance — declared is enforced, observed and reachable (ADR-244)

task ci:fast green; migration replay OK; API healthy with the graph built.
Capability gate silent on the reference configuration (0 mismatches).
llm_type coverage: <n>% of rows over the acceptance window."
```

---

## Self-Review

**Spec coverage.** §2.7's five undeclared slots → Task 1. §5.2's gate, both behaviours → Task 2 (the hard-filter half has no caller until Lot 1, by design). §5.2's `supports_strict_mode` reader → Task 3. §5.3's four columns and the controller index → Tasks 4 and 5. §5.4's failover assert → Task 6. §5.5's dead code, plus the orphan seed row and the silent fallback from §2.7 → Task 7.

**Deliberately out of this plan.** `failure_kind` values `structured_output` and `json_recovered`: they originate in `structured_output.py` and `json_recovery.py`, neither of which holds the LLM call's `run_id`, so persisting them means threading call context through the structured-output path. Their only consumer is Lot 2's controller, which is suspended. The nine API-failure kinds cover every failure the provider reports.

Also out: `SLOT_POLICIES` and the candidate hard-filter path (Lot 1), the continuous catalogue sync (Lot 3), the reasoning unification (ADR-245, Lot 0c).

**Placeholder scan.** No TBD, no "handle errors appropriately". Every code step carries the code. Task 6 Step 3's call-site wiring and Task 7 Step 3's deletions name every file and symbol.

**Type consistency.** `GateVerdict` fields match between Task 2's implementation and its tests. `classify_llm_error` / `LLM_FAILURE_KINDS` keep the same names in Task 5's taxonomy module, the callback delegation and the tests. `assert_failover_chain(settings) -> list[str]` keeps one signature in Task 6. The four column names — `latency_ms`, `status`, `failure_kind`, `llm_type` — are identical in the model (Task 4), the migration (Task 4), the record and repository (Task 5) and every query.

**One risk worth naming.** Task 5 Step 7 measures how many rows actually carry `llm_type`. That number is not knowable before the change, and it bounds everything Lot 1 can aggregate. The plan requires recording it rather than assuming full coverage.
