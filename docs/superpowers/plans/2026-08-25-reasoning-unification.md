# Reasoning Unification (ADR-245, Lot 0c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four stored reasoning shapes, seven provider builders and three frontend renderers with one intent, one derived profile and one translator — without changing a single provider call.

**Architecture:** A `ReasoningIntent` (an ordinal level, an optional budget, an orthogonal exclude flag) replaces the discriminated union. The *shape* of the translation is **derived** from `(provider, model prefix)` through ordered rules and is never stored; the *ladder* of accepted levels stays an optional per-model narrowing the catalogue may supply. One `translate()` with one branch per family replaces the seven builders, and coercion is a safety contract: ties break upward and `none` is never a coercion target.

**Tech Stack:** Python 3.14, Pydantic 2, SQLAlchemy 2 + Alembic, pytest, React 19 + TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-08-23-reasoning-model-unification-design.md` (ADR-245). Read §3.2 and §3.3 before Task 3 — the first draft of both was refuted by the validation harness, and the corrections are the whole point.

**Predecessors:** `2026-08-23-llm-catalogue-truth.md` (Lot 0a) and `2026-08-24-llm-capability-truth.md` (Lot 0b), both delivered. This lot ships **before Lot 1**: Layer 1's `effort_intent` mapper *is* this model, so building Layer 1 first would mean building it twice.

## Global Constraints

- **Behaviour-preserving on 37 slots.** The golden harness is captured FIRST, from the current code, and becomes a permanent test. Nothing merges while a single slot's provider kwargs differ.
- **Ties break upward, and `none` is never a coercion target.** Measured: breaking ties downward makes `deepseek-v4-flash` + `low` coerce to `none` and `claude-opus-4-6` + `minimal` coerce to `none` — reasoning silently disabled, which is the exact failure mode this lot exists to remove, arriving through another door. Doctrine already in the codebase: *"an uninformed guess must never under-budget a hard query"* (`utils/react_budget.py`).
- **The family is derived, the ladder is refined.** The family must never be wrong (measured: 0 gaps over 87 chat models). The ladder is genuinely per-model (OpenAI documents *"supported values are model-dependent"*; `o1` accepts `low/medium/high` but not `minimal`), so a catalogue value may only **narrow** the family ladder — never widen it.
- **The catalogue becomes an optimisation, not a prerequisite.** An unknown model must work through the family ladder plus coercion, never raise.
- **A `can_disable=False` model never produces a disabling config.** `gemini-3.5-flash` is `reasoning.mandatory=true`; a policy that believed it had a cheap mode would be wrong about cost.
- **Python:** Black line-length 100, Ruff, MyPy strict. Google-style docstrings, module docstring on every file. English only in code, comments and docs.
- **Frontend:** the admin widget derives from the same profile the backend uses, served by `/llm-config/metadata`. A contract test pins the two ladders together.
- **i18n:** any new user-visible string lands in all six locales (`en, fr, de, es, it, zh`); zh has no plural form, duplicate the value to `_one` so parity passes.
- **File size:** every new file under 600 logical SLOC; the CC ratchet (337 functions at CC >= 15) and the file-size baseline are shrink-only.
- **Commits:** Conventional Commits. Do not push.

---

## What the prototype already established

A prototype was built and run **inside `lia-api-dev`, against the production code**, before this plan. Do not re-derive these:

| Test | Result |
|---|---|
| T1 golden equivalence over the live configuration | **56/56 identical, 0 divergent** |
| T2 family coverage over 87 chat models | **0 gaps**; 6 widenings, each corroborated as a catalogue error |
| T3 coercion over every currently valid value | **139 values, 0 coerced** |
| T4 exhaustive cross product | **3 480 combinations, 0 crashes** |
| T5 `can_disable` invariant | **0 violations** |
| T6 migration over every stored value + code default | **101 values, 0 failures** (46 values collapse to 7 targets) |
| T7 a new model of a known family | **0 lines to write** |
| T8 a new orthogonal mode (`context` / `mode`) | **~6 lines** |
| T9 a new provider with an unseen shape | **~8 lines** |
| T10 coercion direction | the decisive case above; ties break **up** |

The prototype lives in the session scratchpad (`proto_v2.py`, `proto_validate.py`, `proto_extend.py`). It is throwaway: this lot turns its model into production code and its tests into permanent ones.

---

## The defect being removed, measured

```
 31 SLOC  core/reasoning_types.py               4 shapes in a discriminated union
223 SLOC  llm_config/reasoning_validation.py    cross-validation shape x widget
 99 SLOC  providers/reasoning_builders.py       7 builders + intra-family branching
353 SLOC  backend
+ 261 / 64 / 50 lines of frontend (ReasoningWidget.tsx, reasoningHelpers.ts, reasoningDocText.ts)
+ 6 columns on llm_models across 114 rows
```

**"No reasoning" has four encodings** and 40 of the system's 46 stored values say the same thing three different ways:

```
{"effort": "off"}              21   DeepSeek / Anthropic-adaptive sentinel
{"effort": "none"}              8   OpenAI
ToggleBudget(enabled=False)    11   Qwen / Anthropic-manual
budget: 0                       0   declared sentinel, never used
```

**Three authorities must agree** — the catalogue's `reasoning_widget`, the shape of the stored JSONB, and the builder's `isinstance` check — and a disagreement raises `RuntimeError` at LLM instantiation.

**Two channels produce the same output**: `LLMAgentConfig.reasoning_effort` reaches the Anthropic `effort` kwarg through `build_anthropic_reasoning`, **and** `LLMAgentConfig.effort` reaches it through `factory.py:365`; `additional_kwargs.update()` means the builder silently wins.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/src/core/reasoning_intent.py` | **new** — `ReasoningIntent`, `LEVELS`, the ordinal helper |
| `apps/api/src/infrastructure/llm/reasoning/__init__.py` | **new** — package marker |
| `apps/api/src/infrastructure/llm/reasoning/profiles.py` | **new** — `ReasoningProfile`, the ordered rules, `resolve_reasoning_profile` |
| `apps/api/src/infrastructure/llm/reasoning/coerce.py` | **new** — the safety contract |
| `apps/api/src/infrastructure/llm/reasoning/translate.py` | **new** — one branch per family |
| `apps/api/src/infrastructure/llm/providers/reasoning_builders.py` | **deleted** (7 builders) |
| `apps/api/src/core/reasoning_types.py` | **deleted** (4 shapes) |
| `apps/api/src/domains/llm_config/reasoning_validation.py` | shape × widget cross-validation removed; what survives is level membership |
| `apps/api/src/core/llm_agent_config.py` | `effort` removed; `reasoning_effort` becomes a `ReasoningIntent` |
| `apps/api/src/infrastructure/llm/providers/adapter.py` | one call to `translate()` |
| `apps/api/alembic/versions/2026_08_26_0900-<rev>_reasoning_intent.py` | migrate 37 rows + drop `effort_values` |
| `apps/web/src/components/settings/llm-config/ReasoningWidget.tsx` | one component; three renderers deleted |
| `apps/web/src/components/settings/llm-config/reasoningHelpers.ts` | shape validation deleted; ladder membership survives |
| `apps/api/tests/unit/infrastructure/llm/reasoning/test_golden_equivalence.py` | **T1, permanent** |
| `apps/api/tests/unit/infrastructure/llm/reasoning/test_family_coverage.py` | **T2, permanent** |
| `apps/api/tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py` | **T3, T5, T10, permanent** |
| `apps/api/tests/unit/infrastructure/llm/reasoning/test_translate_matrix.py` | **T4, permanent** |
| `apps/api/tests/unit/infrastructure/llm/reasoning/golden_kwargs.json` | the frozen fixture |

---

### Task 1: Freeze the golden — before touching anything

**Files:**
- Create: `apps/api/scripts/llm_catalogue/capture_reasoning_golden.py`
- Create: `apps/api/tests/unit/infrastructure/llm/reasoning/golden_kwargs.json`
- Create: `apps/api/tests/unit/infrastructure/llm/reasoning/__init__.py`

**Interfaces:**
- Produces: `golden_kwargs.json`, a list of `{slot, provider, model, stored, kwargs}` records captured from the CURRENT code.

**Why:** this lot changes the hot path of 37 configured slots. The only honest way to claim it changes no behaviour is to compare against what the code produced *before* — captured from the current builders, not reconstructed afterwards. Capture it first, or the claim is unfalsifiable.

- [ ] **Step 1: Write the capture script**

Create `apps/api/scripts/llm_catalogue/capture_reasoning_golden.py`:

```python
#!/usr/bin/env python
"""Freeze what the CURRENT reasoning builders produce, slot by slot.

Run this BEFORE the unification, against the unmodified code. The output is a
fixture, not a report: ``test_golden_equivalence`` replays it and fails on any
divergence, which is what makes "no behaviour change" a checkable claim rather
than an assertion.

The capture is deliberately over-wide: every configured slot AND every value
the catalogue declares for its model, so a slot whose stored value changes
later is still covered.

Usage:
    cd apps/api
    python scripts/llm_catalogue/capture_reasoning_golden.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "unit"
    / "infrastructure"
    / "llm"
    / "reasoning"
    / "golden_kwargs.json"
)


async def _capture() -> list[dict[str, object]]:
    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_DEFAULTS
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
    from src.infrastructure.llm.providers.reasoning_builders import (
        build_anthropic_reasoning,
        build_deepseek_v4_reasoning,
        build_gemini_reasoning,
        build_ollama_reasoning,
        build_openai_reasoning,
        build_perplexity_reasoning,
        build_qwen_reasoning,
    )

    builders = {
        "openai": build_openai_reasoning,
        "anthropic": build_anthropic_reasoning,
        "deepseek": build_deepseek_v4_reasoning,
        "gemini": build_gemini_reasoning,
        "qwen": build_qwen_reasoning,
        "perplexity": build_perplexity_reasoning,
        "ollama": build_ollama_reasoning,
    }

    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)
        await LLMConfigOverrideCache.load_from_db(db)

    records: list[dict[str, object]] = []
    for slot in sorted(LLM_DEFAULTS):
        config = get_llm_config_for_agent(settings, slot)
        builder = builders.get(config.provider)
        if builder is None or not config.model:
            continue
        stored = config.reasoning_effort
        records.append(
            {
                "slot": slot,
                "provider": config.provider,
                "model": config.model,
                "stored": None if stored is None else stored.model_dump(),
                "effort_field": config.effort,
                "kwargs": builder(stored, config.model),
            }
        )
    return records


def main() -> None:
    """Capture and write the fixture."""
    records = asyncio.run(_capture())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(records, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} - {len(records)} slots captured")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Capture against the unmodified code**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python scripts/llm_catalogue/capture_reasoning_golden.py
```
Expected: `wrote ... - 56 slots captured` (the prototype measured 56 slots with a builder). **If the count differs from 56, record the number and why before continuing** — the fixture is the reference, not the expectation.

- [ ] **Step 3: Sanity-read the fixture**

Run: `python -c "import json,collections; d=json.load(open('apps/api/tests/unit/infrastructure/llm/reasoning/golden_kwargs.json',encoding='utf-8')); print(len(d)); print(collections.Counter(json.dumps(r['kwargs'],sort_keys=True) for r in d).most_common(8))"`
Expected: a handful of distinct kwargs shapes over the whole fleet — that concentration is the defect this lot removes, and seeing it now is the point.

- [ ] **Step 4: Commit the fixture**

```bash
git add apps/api/scripts/llm_catalogue/capture_reasoning_golden.py apps/api/tests/unit/infrastructure/llm/reasoning/
git commit -m "test(llm): freeze the reasoning golden before unification (ADR-245)"
```

---

### Task 2: The intent

**Files:**
- Create: `apps/api/src/core/reasoning_intent.py`
- Test: `apps/api/tests/unit/core/test_reasoning_intent.py`

**Interfaces:**
- Produces: `LEVELS: tuple[str, ...]`, `Level` (a `Literal`), `level_ordinal(level) -> int`, `ReasoningIntent` (frozen dataclass: `level: Level = "provider_default"`, `budget_tokens: int | None = None`, `exclude_from_output: bool = False`).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/test_reasoning_intent.py`:

```python
"""One value replaces four shapes, and its ladder is ordered."""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent, level_ordinal


def test_the_ladder_is_ordered_from_off_to_max() -> None:
    assert LEVELS == (
        "provider_default",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )


def test_ordinals_are_strictly_increasing() -> None:
    """Coercion measures distance on this ladder; a tie must be a real tie."""
    ordinals = [level_ordinal(level) for level in LEVELS]
    assert ordinals == sorted(ordinals)
    assert len(set(ordinals)) == len(LEVELS)


def test_the_default_intent_asks_for_nothing() -> None:
    """``provider_default`` is the identity: no kwarg, whatever the model."""
    intent = ReasoningIntent()
    assert intent.level == "provider_default"
    assert intent.budget_tokens is None
    assert intent.exclude_from_output is False


def test_the_intent_is_frozen() -> None:
    intent = ReasoningIntent(level="high")
    with pytest.raises(Exception):
        intent.level = "low"  # type: ignore[misc]


def test_an_unknown_level_has_no_ordinal() -> None:
    with pytest.raises(KeyError):
        level_ordinal("telepathic")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/test_reasoning_intent.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... reasoning_intent`.

- [ ] **Step 3: Write the intent**

Create `apps/api/src/core/reasoning_intent.py`:

```python
"""What the caller WANTS from a reasoning model, in one shape.

Replaces a four-member discriminated union whose shape was dispatched on a
catalogue column. Measured before the change: 40 of the system's 46 stored
values said "no reasoning" in three different ways
(``{"effort": "off"}`` x21, ``{"effort": "none"}`` x8,
``ToggleBudget(enabled=False)`` x11), and three authorities -- the column, the
stored JSONB and the builder's ``isinstance`` -- had to agree or the LLM failed
to instantiate.

An intent says what is wanted; a :class:`ReasoningProfile` says what the model
can do; ``translate`` reconciles the two. Nothing is stored about *shape*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: The ordinal ladder, from "let the provider decide" up to the deepest mode.
#: ``provider_default`` sits at the bottom deliberately: it is the identity, not
#: a level, and coercion never targets it.
LEVELS: tuple[str, ...] = (
    "provider_default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

Level = Literal[
    "provider_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"
]

_ORDINALS: dict[str, int] = {level: index for index, level in enumerate(LEVELS)}


def level_ordinal(level: str) -> int:
    """Return a level's rank on the ladder.

    Args:
        level: A :data:`LEVELS` member.

    Returns:
        Its index, used by coercion to measure distance.

    Raises:
        KeyError: on any value outside the ladder. Never guess a rank -- a
            silent default would make coercion pick an arbitrary neighbour.
    """
    return _ORDINALS[level]


@dataclass(frozen=True)
class ReasoningIntent:
    """A request for reasoning depth, independent of any provider.

    Attributes:
        level: How much thinking is wanted. ``provider_default`` asks for
            nothing and produces no kwarg on any family.
        budget_tokens: An explicit token budget, for the families that accept
            one. Mutually exclusive with a level in practice: when both are
            given, the family's translator decides which it can express.
        exclude_from_output: Orthogonal to depth -- keep the reasoning out of
            the response. Families that cannot express it ignore it rather than
            failing, so a caller never has to know which can.
    """

    level: Level = "provider_default"
    budget_tokens: int | None = None
    exclude_from_output: bool = False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/test_reasoning_intent.py -q --no-cov`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/core/reasoning_intent.py apps/api/tests/unit/core/test_reasoning_intent.py
git commit -m "feat(llm): one reasoning intent replaces four stored shapes (ADR-245)"
```

---

### Task 3: The derived profile, and the ladder the catalogue may narrow

**Files:**
- Create: `apps/api/src/infrastructure/llm/reasoning/__init__.py`
- Create: `apps/api/src/infrastructure/llm/reasoning/profiles.py`
- Test: `apps/api/tests/unit/infrastructure/llm/reasoning/test_family_coverage.py`

**Interfaces:**
- Consumes: `LEVELS` from Task 2.
- Produces: `ReasoningProfile` (frozen: `family`, `levels`, `supports_budget`, `budget_range`, `can_disable`, `default_enabled`, `source`), `resolve_reasoning_profile(provider, model, *, model_levels=None, model_can_disable=None) -> ReasoningProfile`, `FAMILIES: frozenset[str]`.

**Read first:** spec §3.2. The first draft derived the ladder from the family too; the harness refuted it with **29 divergences**, because OpenAI documents that supported values are model-dependent.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/reasoning/test_family_coverage.py`:

```python
"""The family must never be wrong; the ladder may only narrow.

T2 of the validation harness, made permanent. A catalogue model whose widget
says it reasons but whose family resolves to ``none`` is a gap that would send
no reasoning kwarg at all; the reverse is a widening, and the six known ones are
allowlisted with their evidence.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.reasoning.profiles import (
    FAMILIES,
    ReasoningProfile,
    resolve_reasoning_profile,
)

pytestmark = pytest.mark.unit

#: Models the family rules say reason while the catalogue's widget says they do
#: not. Each was checked against the provider's documentation and found to be a
#: CATALOGUE error, not a rule error — the rules are right and the rows are
#: stale. Shrink-only: an entry leaves when its row is corrected.
KNOWN_WIDENINGS: frozenset[str] = frozenset()


def test_every_family_is_declared() -> None:
    """A rule producing an unknown family would silently translate to nothing."""
    from src.infrastructure.llm.reasoning.profiles import _RULES

    for _provider, _prefixes, profile in _RULES:
        assert profile.family in FAMILIES, profile.family


def test_a_known_model_resolves_to_its_family() -> None:
    assert resolve_reasoning_profile("openai", "gpt-5.2").family == "openai"
    assert resolve_reasoning_profile("anthropic", "claude-opus-4-6").family == "anthropic_adaptive"
    assert resolve_reasoning_profile("deepseek", "deepseek-v4-flash").family == "deepseek_toggle"


def test_a_negative_rule_wins_over_a_broad_one() -> None:
    """``gpt-4.1`` must not inherit the ``gpt-5``-era OpenAI family."""
    assert resolve_reasoning_profile("openai", "gpt-4.1").family == "none"
    assert resolve_reasoning_profile("openai", "gpt-5-chat-latest").family == "none"
    assert resolve_reasoning_profile("anthropic", "claude-3-5-haiku-20241022").family == "none"


def test_an_unknown_model_never_raises() -> None:
    """The catalogue is an optimisation, not a prerequisite."""
    profile = resolve_reasoning_profile("openai", "gpt-5.9-nova-unreleased")
    assert isinstance(profile, ReasoningProfile)
    assert profile.family == "openai"
    assert profile.source == "family"


def test_a_catalogue_ladder_narrows_but_never_widens() -> None:
    base = resolve_reasoning_profile("openai", "gpt-5.2")
    narrowed = resolve_reasoning_profile("openai", "gpt-5.2", model_levels=("low", "high"))
    assert set(narrowed.levels) < set(base.levels)
    assert narrowed.source == "model_refined"

    widened = resolve_reasoning_profile(
        "openai", "gpt-5.2", model_levels=("low", "high", "telepathic")
    )
    assert "telepathic" not in widened.levels


def test_an_empty_narrowing_is_ignored() -> None:
    """A catalogue row that intersects to nothing must not disarm the family."""
    profile = resolve_reasoning_profile("openai", "gpt-5.2", model_levels=("telepathic",))
    assert profile.levels == resolve_reasoning_profile("openai", "gpt-5.2").levels
    assert profile.source == "family"


def test_the_family_covers_every_reasoning_model_in_the_catalogue() -> None:
    """T2, against the shipped snapshot rather than a live database.

    Uses the vendored catalogue seed as the model list so the test is
    deterministic and needs no DB — the same reason Lot 0a's seed guards parse
    the SQL.
    """
    import re
    from pathlib import Path

    seed = (
        Path(__file__).resolve().parents[6].parent
        / "infrastructure"
        / "database"
        / "seeds"
        / "llm_pricing_seed.sql"
    )
    rows = re.findall(
        r"^\s*\('([a-z]+)',\s*'([^']+)',.*?'(chat|image|audio|realtime|tts|embedding)',\s*'(none|enum|budget_int|toggle_budget)'",
        seed.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert len(rows) >= 100, f"only {len(rows)} catalogue rows parsed"

    gaps, widenings = [], []
    for provider, model, kind, widget in rows:
        if kind != "chat":
            continue
        family = resolve_reasoning_profile(provider, model).family
        if widget != "none" and family == "none":
            gaps.append(f"{provider}/{model}")
        elif widget == "none" and family != "none" and model not in KNOWN_WIDENINGS:
            widenings.append(f"{provider}/{model}")
    assert gaps == [], f"catalogue says these reason, the rules say they do not: {gaps}"
    assert widenings == [], (
        f"the rules say these reason, the catalogue says they do not: {widenings}. "
        "Check the provider's documentation: if the rules are right, the CATALOGUE "
        "row is stale and belongs in KNOWN_WIDENINGS with its evidence."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_family_coverage.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... reasoning.profiles`.

- [ ] **Step 3: Write the profile and the rules**

Create `apps/api/src/infrastructure/llm/reasoning/__init__.py`:

```python
"""One reasoning model: an intent, a derived profile, one translator."""
```

Create `apps/api/src/infrastructure/llm/reasoning/profiles.py`:

```python
"""The SHAPE of a model's reasoning, derived — never stored.

Two things the first draft of this design conflated, and the validation harness
separated:

- the **family** is the shape of the translation. It must never be wrong, so it
  is derived from ``(provider, model prefix)`` through ordered rules. Measured
  over 87 chat models: **0 gaps**.
- the **ladder** is the set of accepted levels. It is genuinely per-model --
  OpenAI documents that supported values are model-dependent, ``o1`` accepts
  ``low/medium/high`` but not ``minimal``, ``gpt-5.6`` adds ``max`` -- so the
  catalogue may supply one, and it may only **narrow** the family's. Deriving it
  from the family produced **29 divergences**.

The consequence is the point: the catalogue becomes an optimisation rather than
a prerequisite. An unknown model resolves to its family's ladder and coercion
handles the rest, instead of raising ``RuntimeError`` at instantiation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

FAMILIES: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic_adaptive",
        "anthropic_budget",
        "gemini_level",
        "gemini_budget",
        "deepseek_toggle",
        "qwen_toggle_budget",
        "perplexity",
        "none",
    }
)


@dataclass(frozen=True)
class ReasoningProfile:
    """What a model can express about reasoning.

    Attributes:
        family: Which translator branch applies.
        levels: The accepted ladder, in ascending order.
        supports_budget: Whether an explicit token budget is expressible.
        budget_range: ``(min, max)`` when it is, else ``None``.
        can_disable: Whether reasoning can be turned off at all. Neither
            OpenRouter nor Vercel models this; LIA needs it because
            ``gemini-3.5-flash`` is ``reasoning.mandatory=true``, and a policy
            that believed it had a cheap mode would be wrong about cost.
        default_enabled: What the provider does absent any instruction, when
            that is known.
        source: ``family`` when the ladder is the family's, ``model_refined``
            when the catalogue narrowed it.
    """

    family: str
    levels: tuple[str, ...]
    supports_budget: bool
    budget_range: tuple[int, int] | None
    can_disable: bool
    default_enabled: bool | None
    source: str = "family"


_NO_REASONING = ReasoningProfile("none", (), False, None, True, False)

#: ORDERED rules. A negative entry (``family="none"``) placed before a broad one
#: wins — that ordering is what keeps ``gpt-4.1`` and ``gpt-5-chat-latest`` out
#: of the OpenAI reasoning family.
_RULES: list[tuple[str, tuple[str, ...], ReasoningProfile]] = [
    (
        "openai",
        (
            "o1-mini",
            "gpt-5-chat-latest",
            "gpt-5.1-chat-latest",
            "gpt-5.2-chat-latest",
            "gpt-5.3-chat-latest",
            "gpt-5-search-api",
            "gpt-4o",
            "gpt-4.1",
            "computer-use-preview",
            "text-embedding",
            "tts-",
        ),
        _NO_REASONING,
    ),
    ("qwen", ("qwen2.5",), _NO_REASONING),
    (
        "gemini",
        (
            "gemini-3.1-flash-preview-tts",
            "gemini-2.0",
            "gemini-1.5",
            "embedding-",
            "text-embedding",
        ),
        _NO_REASONING,
    ),
    ("anthropic", ("claude-3-5",), _NO_REASONING),
    (
        "anthropic",
        ("claude-opus-4-6", "claude-sonnet-4-6"),
        ReasoningProfile(
            "anthropic_adaptive", ("none", "low", "medium", "high", "max"), False, None, True, True
        ),
    ),
    (
        "anthropic",
        ("claude-opus-4-5", "claude-haiku-4-5", "claude-opus-4", "claude-sonnet-4"),
        ReasoningProfile(
            "anthropic_budget",
            ("none", "minimal", "low", "medium", "high", "xhigh"),
            True,
            (1024, 128000),
            True,
            True,
        ),
    ),
    (
        "openai",
        ("gpt-5.6",),
        ReasoningProfile(
            "openai", ("none", "low", "medium", "high", "xhigh", "max"), False, None, True, None
        ),
    ),
    (
        "openai",
        ("gpt-5", "o1", "o3", "o4"),
        ReasoningProfile(
            "openai",
            ("none", "minimal", "low", "medium", "high", "xhigh"),
            False,
            None,
            True,
            None,
        ),
    ),
    (
        "deepseek",
        ("deepseek-v4",),
        ReasoningProfile("deepseek_toggle", ("none", "high", "max"), False, None, True, True),
    ),
    (
        "gemini",
        ("gemini-3",),
        ReasoningProfile(
            "gemini_level", ("minimal", "low", "medium", "high"), False, None, False, True
        ),
    ),
    (
        "gemini",
        ("gemini-2.5",),
        ReasoningProfile(
            "gemini_budget",
            ("none", "minimal", "low", "medium", "high"),
            True,
            (0, 24576),
            True,
            True,
        ),
    ),
    (
        "qwen",
        ("qwen",),
        ReasoningProfile(
            "qwen_toggle_budget",
            ("none", "minimal", "low", "medium", "high"),
            True,
            (0, 32768),
            True,
            False,
        ),
    ),
    (
        "perplexity",
        ("sonar-deep-research", "sonar-reasoning"),
        ReasoningProfile("perplexity", ("low", "medium", "high"), False, None, True, True),
    ),
]


def resolve_reasoning_profile(
    provider: str,
    model: str,
    *,
    model_levels: tuple[str, ...] | None = None,
    model_can_disable: bool | None = None,
) -> ReasoningProfile:
    """Derive the family, then apply the catalogue's optional narrowing.

    Args:
        provider: LIA provider id.
        model: LIA model name.
        model_levels: The ladder the catalogue declares, when it declares one.
            It may only narrow: a level the family cannot translate is dropped,
            and a narrowing that intersects to nothing is ignored entirely
            rather than disarming the model.
        model_can_disable: An explicit override of the family's answer.

    Returns:
        The profile. Never raises: an unrecognised model resolves to
        ``family="none"`` and simply produces no reasoning kwarg.
    """
    base = _NO_REASONING
    for rule_provider, prefixes, profile in _RULES:
        if rule_provider == provider and model.startswith(prefixes):
            base = profile
            break
    if base.family == "none":
        return base

    resolved = base
    if model_levels:
        declared = set(model_levels)
        narrowed = tuple(level for level in base.levels if level in declared)
        if narrowed:
            resolved = replace(resolved, levels=narrowed, source="model_refined")
    if model_can_disable is not None:
        resolved = replace(resolved, can_disable=model_can_disable)
    return resolved
```

- [ ] **Step 4: Run the tests and record the widenings**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_family_coverage.py -v --no-cov`
Expected: `test_the_family_covers_every_reasoning_model_in_the_catalogue` FAILS listing the widenings. **Check each against the provider's documentation**, then put the confirmed catalogue errors in `KNOWN_WIDENINGS` with a one-line reason each. The prototype measured 6; if the count differs, the catalogue moved and the difference is the finding.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/infrastructure/llm/reasoning apps/api/tests/unit/infrastructure/llm/reasoning/test_family_coverage.py
git commit -m "feat(llm): derive the reasoning family, refine the ladder from the catalogue (ADR-245)"
```

---

### Task 4: Coercion — the safety contract

**Files:**
- Create: `apps/api/src/infrastructure/llm/reasoning/coerce.py`
- Test: `apps/api/tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py`

**Interfaces:**
- Consumes: `ReasoningProfile`, `level_ordinal`.
- Produces: `coerce(level: str, profile: ReasoningProfile) -> tuple[str, bool]` returning `(effective_level, was_coerced)`.

**Read first:** spec §3.3. This is where a plausible-looking choice silently disables reasoning.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py`:

```python
"""Coercion is a safety contract, not a convenience.

T3, T5 and T10 of the validation harness, made permanent.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.reasoning.coerce import coerce
from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

pytestmark = pytest.mark.unit


def test_a_supported_level_is_never_coerced() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-5.2")
    for level in profile.levels:
        assert coerce(level, profile) == (level, False)


def test_provider_default_is_always_the_identity() -> None:
    for provider, model in (("openai", "gpt-5.2"), ("gemini", "gemini-3.5-flash")):
        profile = resolve_reasoning_profile(provider, model)
        assert coerce("provider_default", profile) == ("provider_default", False)


def test_ties_break_upward() -> None:
    """The decisive measured case: downward re-creates the failure being removed.

    ``deepseek-v4-flash`` accepts ("none", "high", "max"). A request for "low"
    is equidistant from "none" and "high". Breaking down disables reasoning
    silently — the exact defect this model exists to remove, arriving through
    another door. Doctrine: ``utils/react_budget.py`` — "an uninformed guess
    must never under-budget a hard query".
    """
    profile = resolve_reasoning_profile("deepseek", "deepseek-v4-flash")
    assert coerce("low", profile) == ("high", True)

    adaptive = resolve_reasoning_profile("anthropic", "claude-opus-4-6")
    assert coerce("minimal", adaptive) == ("low", True)


def test_none_is_never_a_coercion_target() -> None:
    """Only an EXPLICIT level="none" may disable reasoning."""
    for provider, model in (
        ("deepseek", "deepseek-v4-flash"),
        ("anthropic", "claude-opus-4-6"),
        ("openai", "gpt-5.2"),
    ):
        profile = resolve_reasoning_profile(provider, model)
        for level in ("minimal", "low", "medium", "high", "xhigh", "max"):
            coerced, _ = coerce(level, profile)
            assert coerced != "none", f"{model}: {level} coerced to none"


def test_an_explicit_none_is_honoured_when_the_model_can_disable() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-5.2")
    assert coerce("none", profile) == ("none", False)


def test_a_mandatory_model_never_gets_a_disabling_level() -> None:
    """T5: ``gemini-3.5-flash`` is reasoning.mandatory — it has no cheap mode."""
    profile = resolve_reasoning_profile("gemini", "gemini-3.5-flash")
    assert profile.can_disable is False
    coerced, was_coerced = coerce("none", profile)
    assert coerced != "none"
    assert was_coerced is True


def test_a_family_with_no_ladder_falls_back_to_the_identity() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-4.1")
    assert coerce("high", profile) == ("provider_default", True)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-5.2"),
        ("anthropic", "claude-opus-4-6"),
        ("anthropic", "claude-opus-4-5"),
        ("deepseek", "deepseek-v4-flash"),
        ("gemini", "gemini-3.5-flash"),
        ("gemini", "gemini-2.5-flash"),
        ("qwen", "qwen3.5-plus"),
        ("perplexity", "sonar-reasoning"),
    ],
)
def test_every_coercion_lands_inside_the_ladder(provider: str, model: str) -> None:
    """T4's invariant: coercion never invents a level."""
    from src.core.reasoning_intent import LEVELS

    profile = resolve_reasoning_profile(provider, model)
    for level in LEVELS:
        coerced, _ = coerce(level, profile)
        assert coerced in profile.levels or coerced == "provider_default"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... reasoning.coerce`.

- [ ] **Step 3: Write the coercion**

Create `apps/api/src/infrastructure/llm/reasoning/coerce.py`:

```python
"""Map a requested level onto what a model actually accepts, safely.

Two rules, both measured rather than chosen, and both enforced by tests.

**Ties break upward.** With ties broken downward, ``deepseek-v4-flash`` asked
for ``low`` -- equidistant from ``none`` and ``high`` on its ("none", "high",
"max") ladder -- coerces to ``none``: reasoning silently disabled. So does
``claude-opus-4-6`` asked for ``minimal``. That is the exact failure this whole
model exists to remove, re-created through another door. The codebase already
carries the doctrine: *"an uninformed guess must never under-budget a hard
query"* (``utils/react_budget.py``).

**``none`` is never a coercion target.** Only an explicit ``level="none"``
disables reasoning, and only on a model that can be disabled at all.
"""

from __future__ import annotations

from src.core.reasoning_intent import level_ordinal
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def coerce(level: str, profile: ReasoningProfile) -> tuple[str, bool]:
    """Return the nearest level this model accepts, and whether it moved.

    Args:
        level: The requested level.
        profile: The model's derived profile.

    Returns:
        ``(effective_level, was_coerced)``. ``provider_default`` is returned
        unchanged, and is also the answer for a family with no ladder -- asking
        a non-reasoning model for ``high`` produces no kwarg rather than an
        error.
    """
    if level == "provider_default" or level in profile.levels:
        return level, False
    if not profile.levels:
        return "provider_default", True
    if level == "none" and not profile.can_disable:
        # A mandatory-reasoning model has no cheap mode. Give it the cheapest
        # it HAS rather than pretending it can be switched off.
        return profile.levels[0], True

    target = level_ordinal(level)
    # ``none`` is excluded as a target: coercion may lower depth, never remove
    # reasoning. The fallback keeps a ladder that is only ("none",) usable.
    candidates = [candidate for candidate in profile.levels if candidate != "none"]
    if not candidates:
        candidates = list(profile.levels)
    nearest = min(
        candidates, key=lambda candidate: (abs(level_ordinal(candidate) - target), -level_ordinal(candidate))
    )
    return nearest, True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py -q --no-cov`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/infrastructure/llm/reasoning/coerce.py apps/api/tests/unit/infrastructure/llm/reasoning/test_coercion_contract.py
git commit -m "feat(llm): reasoning coercion breaks ties upward and never targets none (ADR-245)"
```

---

### Task 5: One translator, and the golden it must reproduce

**Files:**
- Create: `apps/api/src/infrastructure/llm/reasoning/translate.py`
- Create: `apps/api/tests/unit/infrastructure/llm/reasoning/test_golden_equivalence.py`
- Create: `apps/api/tests/unit/infrastructure/llm/reasoning/test_translate_matrix.py`

**Interfaces:**
- Consumes: `ReasoningIntent`, `ReasoningProfile`, `coerce`.
- Produces: `translate(intent, profile, model, max_output_tokens) -> dict[str, Any]`, and `intent_from_legacy(value) -> ReasoningIntent` (the migration mapper, used by Task 6 and by the golden test).

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/infrastructure/llm/reasoning/test_golden_equivalence.py`:

```python
"""T1, permanent: the new translator reproduces the old builders exactly.

The fixture was captured from the UNMODIFIED code before this lot began. Any
divergence is a behaviour change on the hot path of every configured slot, and
this test is what makes "no behaviour change" a checkable claim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
from src.infrastructure.llm.reasoning.translate import intent_from_legacy, translate

pytestmark = pytest.mark.unit

GOLDEN = json.loads((Path(__file__).with_name("golden_kwargs.json")).read_text(encoding="utf-8"))


def test_the_golden_is_not_empty() -> None:
    """A fixture that captured nothing would make this test vacuous."""
    assert len(GOLDEN) >= 50


@pytest.mark.parametrize("record", GOLDEN, ids=[r["slot"] for r in GOLDEN])
def test_the_translator_reproduces_the_builder(record: dict) -> None:
    caps = ModelCapabilitiesCache.get(record["model"])
    profile = resolve_reasoning_profile(
        record["provider"],
        record["model"],
        model_levels=tuple(caps.reasoning_enum_values) if caps and caps.reasoning_enum_values else None,
    )
    produced = translate(
        intent_from_legacy(record["stored"]),
        profile,
        record["model"],
        caps.max_output_tokens if caps else 4096,
    )
    assert produced == record["kwargs"], (
        f"{record['slot']} ({record['provider']}/{record['model']}) diverges: "
        f"was {record['kwargs']}, now {produced}"
    )
```

Create `apps/api/tests/unit/infrastructure/llm/reasoning/test_translate_matrix.py`:

```python
"""T4, permanent: the whole cross product translates without crashing."""

from __future__ import annotations

import json

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
from src.infrastructure.llm.reasoning.translate import translate

pytestmark = pytest.mark.unit

MODELS = [
    ("openai", "gpt-5.2"),
    ("openai", "gpt-5.6-luna"),
    ("openai", "gpt-4.1"),
    ("anthropic", "claude-opus-4-6"),
    ("anthropic", "claude-opus-4-5"),
    ("deepseek", "deepseek-v4-flash"),
    ("gemini", "gemini-3.5-flash"),
    ("gemini", "gemini-2.5-flash"),
    ("qwen", "qwen3.5-plus"),
    ("perplexity", "sonar-reasoning"),
    ("ollama", "llama3.2"),
]
BUDGETS = (None, 0, 1024, 32768, 999999)


@pytest.mark.parametrize(("provider", "model"), MODELS)
def test_every_combination_translates_to_serialisable_kwargs(provider: str, model: str) -> None:
    profile = resolve_reasoning_profile(provider, model)
    for level in LEVELS:
        for budget in BUDGETS:
            produced = translate(
                ReasoningIntent(level=level, budget_tokens=budget), profile, model, 128_000
            )
            json.dumps(produced)  # must be a plain, serialisable kwargs dict


def test_a_non_reasoning_model_produces_no_kwarg_whatever_is_asked() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-4.1")
    for level in LEVELS:
        assert translate(ReasoningIntent(level=level), profile, "gpt-4.1", 32_768) == {}


def test_provider_default_produces_no_kwarg_on_any_family() -> None:
    for provider, model in MODELS:
        profile = resolve_reasoning_profile(provider, model)
        assert translate(ReasoningIntent(), profile, model, 128_000) == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/ -v --no-cov`
Expected: the two new files FAIL on `ModuleNotFoundError: ... reasoning.translate`.

- [ ] **Step 3: Write the translator**

Create `apps/api/src/infrastructure/llm/reasoning/translate.py`:

```python
"""One function, one branch per family, replacing seven builders.

Also carries ``intent_from_legacy``: the mapper from the four stored shapes to
the single intent. It lives here rather than in the migration because the golden
test needs it too -- the migration and the equivalence proof must agree on what
a stored value MEANT, and two copies could not.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.coerce import coerce
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile

#: Level -> fraction of the model's output cap, for the families that express a
#: budget rather than a level. The ratios are the ones OpenRouter and Vercel
#: publish for the same mapping, so a level means the same depth across
#: providers.
_BUDGET_RATIO: dict[str, float] = {
    "minimal": 0.10,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "xhigh": 0.95,
    "max": 0.95,
}


def intent_from_legacy(value: dict[str, Any] | None) -> ReasoningIntent:
    """Read one of the four stored shapes as an intent.

    The four encodings of "no reasoning" collapse to ``level="none"``:
    ``{"effort": "off"}`` (21 stored values), ``{"effort": "none"}`` (8),
    ``{"enabled": false}`` (11) and the never-used ``{"budget": 0}``.

    Args:
        value: The stored JSONB, or ``None``.

    Returns:
        The equivalent intent. A shape outside the four is read as
        ``provider_default`` rather than raising: the migration must be total.
    """
    if not value:
        return ReasoningIntent()
    if "effort" in value:
        effort = str(value["effort"])
        return ReasoningIntent(level="none" if effort == "off" else effort)  # type: ignore[arg-type]
    if "enabled" in value:
        if not value["enabled"]:
            return ReasoningIntent(level="none")
        budget = value.get("budget")
        return ReasoningIntent(
            budget_tokens=int(budget) if budget is not None else ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
        )
    if "budget" in value:
        budget = int(value["budget"])
        if budget == -1:
            return ReasoningIntent()
        if budget == 0:
            return ReasoningIntent(level="none")
        return ReasoningIntent(budget_tokens=budget)
    return ReasoningIntent()


def _budget_for(level: str, max_output_tokens: int, floor: int) -> int:
    ratio = _BUDGET_RATIO.get(level)
    if ratio is None:
        return floor
    return max(int(max_output_tokens * ratio), floor)


def translate(
    intent: ReasoningIntent,
    profile: ReasoningProfile,
    model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Render an intent as the provider kwargs its family expects.

    Args:
        intent: What the caller wants.
        profile: What the model can express.
        model: The model name, for the families whose kwargs name it.
        max_output_tokens: Used by the budget families to turn a level into a
            token count.

    Returns:
        The kwargs dict, empty when nothing should be sent.
    """
    family = profile.family
    if family == "none":
        return {}
    if intent.level == "provider_default" and intent.budget_tokens is None:
        return {}

    level, _ = coerce(intent.level, profile)

    if family == "openai":
        return {} if level == "provider_default" else {"reasoning_effort": level}
    if family == "anthropic_adaptive":
        return {} if level == "none" else {"thinking": {"type": "adaptive"}, "effort": level}
    if family == "anthropic_budget":
        if level == "none":
            return {}
        budget = intent.budget_tokens
        if budget is None:
            budget = _budget_for(level, max_output_tokens, ANTHROPIC_MIN_THINKING_BUDGET_TOKENS)
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}
    if family == "gemini_level":
        return {"thinking_level": level, "include_thoughts": not intent.exclude_from_output}
    if family == "gemini_budget":
        budget = intent.budget_tokens
        if budget is None:
            budget = 0 if level == "none" else int(max_output_tokens * _BUDGET_RATIO.get(level, 0.5))
        return {"thinking_budget": budget, "include_thoughts": not intent.exclude_from_output}
    if family == "deepseek_toggle":
        if level == "none":
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": level}
    if family == "qwen_toggle_budget":
        if level == "none":
            return {"extra_body": {"enable_thinking": False}}
        extra: dict[str, Any] = {"enable_thinking": True}
        if intent.budget_tokens is not None:
            extra["thinking_budget"] = intent.budget_tokens
        return {"extra_body": extra}
    if family == "perplexity":
        return {"reasoning_effort": level}
    return {}
```

- [ ] **Step 4: Run the tests and read every divergence**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/ -v --no-cov`
Expected: all passed. **Every failure of `test_the_translator_reproduces_the_builder` names a slot whose provider kwargs would change.** The prototype measured 56/56 identical; if a slot diverges here, the cause is a rule or a ratio, not the fixture — fix the translator, never the golden.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/infrastructure/llm/reasoning/translate.py apps/api/tests/unit/infrastructure/llm/reasoning/
git commit -m "feat(llm): one reasoning translator, proven equivalent on every slot (ADR-245)"
```

---

### Task 6: Migrate the stored values and the code defaults

**Files:**
- Modify: `apps/api/src/core/llm_agent_config.py` (`reasoning_effort` becomes a `ReasoningIntent`; `effort` removed)
- Modify: `apps/api/src/domains/llm_config/constants.py` (31 code defaults)
- Create: `apps/api/alembic/versions/2026_08_26_0900-d3e4f5a6b7c8_reasoning_intent.py`
- Test: `apps/api/tests/unit/infrastructure/llm/reasoning/test_legacy_migration.py`

**Interfaces:**
- Consumes: `intent_from_legacy` from Task 5.

**Why:** `LLMAgentConfig.effort` and `reasoning_effort` both reach the Anthropic `effort` kwarg, and `additional_kwargs.update()` means the builder silently wins. One field, one output, no precedence puzzle.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/reasoning/test_legacy_migration.py`:

```python
"""T6, permanent: every stored shape reads as an intent, and the four "off"s collapse."""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.translate import intent_from_legacy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "stored",
    [
        {"effort": "off"},
        {"effort": "none"},
        {"enabled": False},
        {"enabled": False, "budget": None},
        {"budget": 0},
    ],
)
def test_every_encoding_of_off_collapses_to_one(stored: dict) -> None:
    """40 of the 46 stored values said this in three different ways."""
    assert intent_from_legacy(stored) == ReasoningIntent(level="none")


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, ReasoningIntent()),
        ({}, ReasoningIntent()),
        ({"budget": -1}, ReasoningIntent()),
        ({"effort": "medium"}, ReasoningIntent(level="medium")),
        ({"budget": 8192}, ReasoningIntent(budget_tokens=8192)),
        ({"enabled": True, "budget": 4096}, ReasoningIntent(budget_tokens=4096)),
    ],
)
def test_the_other_shapes_read_as_themselves(stored: dict | None, expected: ReasoningIntent) -> None:
    assert intent_from_legacy(stored) == expected


def test_an_unrecognised_shape_reads_as_provider_default() -> None:
    """The migration must be total: a shape nobody planned for cannot abort it."""
    assert intent_from_legacy({"telepathy": True}) == ReasoningIntent()


def test_every_code_default_migrates() -> None:
    """The 31 code defaults, read through the same mapper as the DB rows."""
    from src.domains.llm_config.constants import LLM_DEFAULTS

    migrated = 0
    for config in LLM_DEFAULTS.values():
        stored = config.reasoning_effort
        payload = stored if isinstance(stored, dict) or stored is None else stored.model_dump()
        assert isinstance(intent_from_legacy(payload), ReasoningIntent)
        migrated += 1
    assert migrated == len(LLM_DEFAULTS)


def test_the_duplicate_effort_channel_is_gone() -> None:
    """``LLMAgentConfig.effort`` and ``reasoning_effort`` both produced the
    Anthropic ``effort`` kwarg, and ``additional_kwargs.update()`` decided which
    silently won."""
    import dataclasses

    from src.core.llm_agent_config import LLMAgentConfig

    names = {f.name for f in dataclasses.fields(LLMAgentConfig)} if dataclasses.is_dataclass(
        LLMAgentConfig
    ) else set(LLMAgentConfig.model_fields)
    assert "effort" not in names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_legacy_migration.py -v --no-cov`
Expected: `test_the_duplicate_effort_channel_is_gone` FAILS; the others pass (the mapper already exists).

- [ ] **Step 3: Write the migration**

Create `apps/api/alembic/versions/2026_08_26_0900-d3e4f5a6b7c8_reasoning_intent.py`:

```python
"""Rewrite stored reasoning_effort as a single intent (ADR-245, Lot 0c).

Every stored shape becomes ``{"level": ..., "budget_tokens": ...}``. The four
encodings of "no reasoning" -- ``{"effort": "off"}`` (21 rows),
``{"effort": "none"}`` (8), ``{"enabled": false}`` (11) and the never-used
``{"budget": 0}`` -- collapse to ``{"level": "none"}``.

``llm_config_overrides.effort`` is dropped: it produced the same Anthropic
kwarg as ``reasoning_effort`` and ``additional_kwargs.update()`` decided which
silently won.

The mapper is ``translate.intent_from_legacy``, shared with the golden test, so
the migration and the equivalence proof cannot disagree about what a stored
value meant.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-26 09:00:00.000000
"""

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Rewrite every stored value and drop the duplicate effort channel."""
    from dataclasses import asdict

    from src.infrastructure.llm.reasoning.translate import intent_from_legacy

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, reasoning_effort FROM llm_config_overrides "
            "WHERE reasoning_effort IS NOT NULL"
        )
    ).fetchall()

    rewritten = 0
    for row_id, stored in rows:
        intent = intent_from_legacy(stored if isinstance(stored, dict) else None)
        bind.execute(
            sa.text("UPDATE llm_config_overrides SET reasoning_effort = :value WHERE id = :row_id"),
            {"value": json.dumps(asdict(intent)), "row_id": row_id},
        )
        rewritten += 1

    op.drop_column("llm_config_overrides", "effort")
    op.drop_column("llm_models", "effort_values")
    logger.info("reasoning intent migration: rewritten=%d rows", rewritten)


def downgrade() -> None:
    """Restore the columns; the stored shapes are NOT reconstructed.

    An intent does not carry which of the four legacy encodings it came from,
    and guessing one would write a shape the old builders might reject. The
    columns come back empty so a rollback lands on "no override", which every
    slot tolerates.
    """
    op.add_column("llm_models", sa.Column("effort_values", sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column("llm_config_overrides", sa.Column("effort", sa.String(length=32), nullable=True))
    op.execute(sa.text("UPDATE llm_config_overrides SET reasoning_effort = NULL"))
```

- [ ] **Step 4: Change the field and the 31 defaults**

In `apps/api/src/core/llm_agent_config.py`, remove the `effort` field entirely and retype `reasoning_effort` to `ReasoningIntent | None`. In `apps/api/src/domains/llm_config/constants.py`, rewrite each of the 31 `reasoning_effort=` defaults as a `ReasoningIntent(...)`, mapping mechanically: `{"effort": "off"}` and `ToggleBudget(enabled=False)` become `ReasoningIntent(level="none")`, `{"effort": "X"}` becomes `ReasoningIntent(level="X")`.

- [ ] **Step 5: Apply and verify**

Run: `docker exec -w /app lia-api-dev alembic upgrade head`
Expected: `reasoning intent migration: rewritten=<n> rows` with `n` around 37.
Then: `docker exec -w /app lia-api-dev alembic heads` → one head.
Then: `task db:migrate:replay-check` → OK.

- [ ] **Step 6: Run the tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/ tests/unit/domains/llm_config/ -q --no-cov`
Expected: all passed, **including the golden** — the stored values changed shape but must still translate to the same kwargs.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/core/llm_agent_config.py apps/api/src/domains/llm_config/constants.py apps/api/alembic/versions/2026_08_26_0900-d3e4f5a6b7c8_reasoning_intent.py apps/api/tests/unit/infrastructure/llm/reasoning/test_legacy_migration.py
git commit -m "feat(llm): migrate stored reasoning to one intent, drop the duplicate effort channel (ADR-245)"
```

---

### Task 7: Switch the adapter, delete the builders

**Files:**
- Modify: `apps/api/src/infrastructure/llm/providers/adapter.py` (one call to `translate`)
- Modify: `apps/api/src/infrastructure/llm/factory.py` (the `effort` forwarding at line 365 goes)
- Delete: `apps/api/src/infrastructure/llm/providers/reasoning_builders.py`
- Delete: `apps/api/src/core/reasoning_types.py`
- Modify: `apps/api/src/domains/llm_config/reasoning_validation.py` (shape × widget cross-validation removed)

- [ ] **Step 1: Point the adapter at the translator**

In `adapter.py`, replace the per-provider builder dispatch with:

```python
        from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
        from src.infrastructure.llm.reasoning.translate import translate

        caps = ModelCapabilitiesCache.get(model)
        profile = resolve_reasoning_profile(
            provider,
            model,
            model_levels=(
                tuple(caps.reasoning_enum_values)
                if caps and caps.reasoning_enum_values
                else None
            ),
        )
        reasoning_kwargs = translate(
            reasoning_effort or ReasoningIntent(),
            profile,
            model,
            caps.max_output_tokens if caps else 4096,
        )
        additional_kwargs.update(reasoning_kwargs)
```

- [ ] **Step 2: Delete the dead modules**

```bash
git rm apps/api/src/infrastructure/llm/providers/reasoning_builders.py apps/api/src/core/reasoning_types.py
```

Then remove every import of them; `.venv/Scripts/ruff check src` names each site.

- [ ] **Step 3: Trim the validation**

In `reasoning_validation.py`, delete the shape × widget cross-validation (it validated a shape that no longer varies). What survives is one question: **is this level on the model's ladder?** — answered by `resolve_reasoning_profile(...).levels`, so the validator and the translator cannot disagree.

- [ ] **Step 4: Run everything**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit -q --no-cov` then `task lint`
Expected: green. The golden test is the one that matters: it proves the deletion changed nothing.

- [ ] **Step 5: Runtime proof**

Restart the API (`docker compose -f docker-compose.dev.yml up -d api` — `docker restart` does not re-read `env_file`) and confirm: healthy, `graph_built_successfully`, `agents_registered` unchanged, zero `"level": "error"`.

- [ ] **Step 6: Commit**

```bash
git add -A apps/api/src
git commit -m "refactor(llm): one translator replaces seven reasoning builders (ADR-245)"
```

---

### Task 8: One frontend component

**Files:**
- Modify: `apps/web/src/components/settings/llm-config/ReasoningWidget.tsx` (three renderers → one)
- Modify: `apps/web/src/components/settings/llm-config/reasoningHelpers.ts` (shape validation → ladder membership)
- Modify: `apps/web/src/types/llm-config.ts` (the profile shape)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`
- Test: `apps/web/src/components/settings/llm-config/__tests__/ReasoningWidget.test.tsx`

**Why:** the widget dispatched on `reasoning_widget` because the *shape* varied. It no longer does. `levels` gives the buttons, `supports_budget` the numeric field, `can_disable` greys out "none" — one component, driven by the same profile the backend uses.

- [ ] **Step 1: Extend the metadata contract**

`/llm-config/metadata` serves the resolved profile per model (`family`, `levels`, `supports_budget`, `budget_range`, `can_disable`). Add a backend contract test asserting the served ladder equals `resolve_reasoning_profile(...).levels` — the two must never drift.

- [ ] **Step 2: Write the failing component test**

Replace `ReasoningWidget.test.tsx` with tests that drive the profile rather than the widget type: a model with a five-level ladder renders five options; `can_disable: false` renders "none" disabled with an explanatory title; `supports_budget: true` renders the numeric field within `budget_range`; a level outside the ladder never renders. Include the accessibility assertions the repo's conventions require — a stable translated accessible name, keyboard equivalence and a deterministic focus order.

- [ ] **Step 3: Write the single component**

One component, no `widget ===` dispatch. Delete `ReasoningEnumWidget`, `ReasoningBudgetWidget` and `ReasoningToggleWidget`.

- [ ] **Step 4: Trim the helpers**

`reasoningEffortShape` and `reasoningEffortMatchesModel` were shape-discriminators; they go. What survives is `coerceReasoningLevelForModel(current, profile)` — a level not on the new model's ladder must not travel across a model switch.

- [ ] **Step 5: i18n across six locales**

Any new string lands in all six. `task lint:i18n` enforces parity; zh has no plural form, so duplicate the value to `_one`.

- [ ] **Step 6: Run the frontend gates**

Run: `task test:frontend` then `task test:frontend:coverage` then `task lint:frontend`
Expected: green, including the a11y, react-hooks and complexity ratchets.

- [ ] **Step 7: Commit**

```bash
git add apps/web
git commit -m "refactor(web): one reasoning widget driven by the model profile (ADR-245)"
```

---

### Task 9: Demote the catalogue columns

**Files:**
- Modify: `apps/api/src/domains/llm/models.py` (the six reasoning columns become optional)
- Modify: `apps/api/src/domains/llm/pricing_sheet.py` (exclusions and their reasons)
- Test: the Task 3 coverage guard

**Why:** the columns described a shape that is now derived. What remains is a *narrowing*: a NULL is valid and safe, and a stale row can no longer break instantiation.

- [ ] **Step 1: Make a NULL explicitly valid**

Add a test asserting that a model whose `reasoning_widget` is NULL and whose `reasoning_enum_values` is NULL still resolves to its family's profile and translates correctly. That property is the whole benefit of the change, and it deserves to be pinned.

- [ ] **Step 2: Update the workbook exclusions**

`reasoning_widget` was the shape authority and is now a narrowing hint. Either keep exporting it with an updated comment, or exclude it with a written reason — the existing `test_every_model_column_is_exported_or_explicitly_excluded` guard forces the choice to be explicit.

- [ ] **Step 3: Run the gates**

Run: `task lint` then `task test:backend:unit:fast`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/domains/llm
git commit -m "refactor(llm): the reasoning columns become an optional narrowing (ADR-245)"
```

---

### Task 10: Lot acceptance

- [ ] **Step 1: Every gate**

Run: `task ci:fast` — expected green.
Run: `task db:migrate:replay-check` — expected OK.

- [ ] **Step 2: The golden proves the claim**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/reasoning/test_golden_equivalence.py -v --no-cov`
Expected: every slot passes. **Record the slot count in the commit body** — that number is the scope of the behaviour-preservation claim.

- [ ] **Step 3: The runtime resolves identically**

Restart the API and, for each of the 10 distinct configured models, print the kwargs `translate` produces. Compare against `golden_kwargs.json`. Expected: identical.

- [ ] **Step 4: Measure what was deleted**

Run: `apps/api/.venv/Scripts/python scripts/audit/measure_sloc.py apps/api/src/infrastructure/llm apps/api/src/core apps/api/src/domains/llm_config`
Expected: the reasoning surface is materially smaller than the 353 SLOC + 375 frontend lines measured before. **Record the measured figures**, and run `task ratchet:update` so the file-size caps follow the shrink down.

- [ ] **Step 5: A guard reds on a reverted fix**

Temporarily break one family rule (drop the `gpt-4.1` negative entry), confirm `test_family_coverage` FAILS, then restore. Temporarily break the tie direction in `coerce`, confirm `test_coercion_contract` FAILS, then restore.

- [ ] **Step 6: Commit the acceptance record**

```bash
git commit --allow-empty -m "chore(llm): Lot 0c acceptance — one reasoning model (ADR-245)

task ci:fast green; migration replay OK; API healthy with the graph built.
Golden equivalence: <n>/<n> slots identical.
Reasoning surface: <before> -> <after> SLOC backend, <before> -> <after> frontend."
```

---

## Self-Review

**Spec coverage.** §3.1 the intent → Task 2. §3.2 the derived family and the narrowing ladder → Task 3. §3.3 the coercion contract → Task 4. §3.4 `can_disable` → Tasks 3, 4 and 8; the escape hatch and the shared profile for the UI → Task 8. §3.5 the duplicate `effort` channel → Task 6. §6 what ships and what is deleted → Tasks 5, 7, 8, 9. §7's six risks: the golden harness (Tasks 1 and 5), the total migration (Task 6), the coverage guard (Task 3), the coercion tests (Task 4), the `can_disable` invariant (Task 4), the frontend/backend contract test (Task 8 Step 1). §8's six delivery steps map to Tasks 1–2, 3–5, 6, 7, 8, 9.

**Deliberately out of this plan.** The typed escape hatch per family (§3.4 improvement 2) is declared but not built: nothing needs it until a caller must pass a provider-specific option the families do not model, and building it now would be a speculative layer. `exclude_from_output` IS built — it costs one field and the families that cannot express it ignore it, which is the property that makes the model extensible (T8 measured ~6 lines for a new orthogonal mode).

**Placeholder scan.** Tasks 1–6 and 9–10 carry the actual code. Tasks 7 and 8 describe deletions and a UI rewrite whose exact shape depends on what Task 5's golden proves; each step names the files, the symbols and the gate that must pass. That is the one place this plan describes rather than dictates, and it is deliberate: dictating a component's markup before the contract test exists would be inventing.

**Type consistency.** `ReasoningIntent` and `LEVELS` keep the same names from Task 2 through Task 8. `ReasoningProfile`'s seven fields are identical in Task 3's definition, Task 4's coercion, Task 5's translator and Task 8's frontend contract. `coerce(level, profile) -> (level, bool)` and `translate(intent, profile, model, max_output_tokens) -> dict` keep one signature each. `intent_from_legacy` lives in `translate.py` and is used by both the migration (Task 6) and the golden test (Task 5) — one mapper, so the two cannot disagree about what a stored value meant.

**One risk worth naming.** Task 1's fixture must be captured **before** any other task touches the builders. If a later task is executed first, the golden records the new behaviour and proves nothing. The task order is not a preference here; it is the proof.
