# LLM Catalogue Truth (ADR-244 Lot 0a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LIA's model catalogue tell the truth about model capabilities, so that every later decision — compaction thresholds, capability gates, model policies — reasons on measured data instead of column defaults.

**Architecture:** A filtered snapshot of two public registries (LiteLLM, MIT; models.dev) is vendored in the repository. A canonical-provider-locked matcher plus a per-field precedence mapper turn that snapshot into `RegistryFacts`. A `task llm:catalogue:sync` command emits a reviewable diff; a one-off data migration applies the initial correction. **Capabilities only** — prices, reasoning metadata and streaming are never read (measured decisions, see the spec). Three CI guards keep it honest.

**Tech Stack:** Python 3.14, SQLAlchemy 2 + Alembic, Pydantic 2, pytest, Task (Taskfile.yml).

**Spec:** `docs/superpowers/specs/2026-08-23-llm-model-policy-design.md` — §0 bis, §0 ter, §0 quinquies, §5.1, §5.5. Read §0 ter and §0 quinquies before Task 3: they explain, with measurements, why three field families are excluded.

## Global Constraints

- **Canonical provider lock.** A registry entry is accepted only when its provider matches LIA's provider through the declared mapping. Matching by model id alone is forbidden: models.dev publishes 193 providers and `deepseek-v4-flash` appears under 23 of them with output caps from 32 768 to 1 048 576.
- **Never read from the registries:** any price field, any reasoning field (`reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`, `effort_values`), `supports_streaming`, and the four sampling flags (`supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`).
- **No network on any execution path.** The vendored snapshot is the only source at runtime; fetching is a developer/CI task.
- **Deactivation rule.** A model is deactivated only when nothing references it: no `llm_config_overrides` row on the target instance, no `LLM_DEFAULTS` entry, no seed row, no constant.
- **Python:** Black line-length 100, Ruff, MyPy (`platform = linux`). Google-style docstrings, module docstring on every file. English only in code, comments and docs.
- **Logging:** `structlog.get_logger(__name__)`. No `print()`. Counters and ids at INFO; never model prompt content.
- **Datetimes:** timezone-aware UTC (`datetime.now(UTC)`).
- **File size:** every new file stays under 600 logical SLOC.
- **Commits:** Conventional Commits. Do not push. Do not run git commands other than `git add` / `git commit`.

## Plan Amendments (found during the pre-execution review, 2026-08-24)

Three defects were found reading the plan against the repository. The
amendments below **take precedence** over the task bodies where they conflict.

**A1 — `compute_diff` moves into `src/`, the script becomes a thin CLI.**
Task 5 placed the diff engine in `scripts/llm_catalogue/sync.py` and had the
test reach it through `sys.path.insert(..., parents[6] / "scripts")`. That path
resolves to `apps/scripts`, which does not exist — the test could never have
imported the module. Beyond the bug, the engine has **three** consumers (the
CLI, the test, and the Task 6 migration, which re-declared the field tuple
inline). It therefore lives at
`apps/api/src/infrastructure/llm/catalogue/sync_diff.py`, exporting
`CatalogueRow`, `FieldChange`, `COMPARED_FIELDS` and `compute_diff`.
`scripts/llm_catalogue/sync.py` keeps only the DB load and the printing, and
the Task 6 migration imports `COMPARED_FIELDS` instead of repeating it. The
engine gains MyPy strict, Ruff and Black coverage, which `scripts/` does not
have (`task lint:backend` runs on `src tests` only).

**A2 — a migration reports through the Alembic logger, never `print()`.**
`2025_11_05_1513-add_token_usage_indexes_for_lifetime_metrics.py:77` records
the reason: `print()` raises `UnicodeEncodeError` under a CP1252 Windows
console (audit F047). The convention is
`logging.getLogger("alembic.runtime.migration")` with ASCII-only messages.
Task 6 uses it. Its `op.execute(sa.text("SELECT 1"))` is dropped — it was a
no-op with no purpose.

**A3 — no `# noqa: T201`.** `apps/api/pyproject.toml` enables `E, W, F, I, B,
C4, UP`; `T20` (flake8-print) is not among them, so the suppression names a
rule that does not exist and misleads the next reader. Developer CLIs under
the repository-root `scripts/` print plainly.

Four more amendments come from measuring the generated snapshot (512 LiteLLM
entries, 291 models.dev entries) against LIA's 124 catalogue rows.

**A4 — the allowlist holds two entries, not four.** `ALLOWED_DECLARED_MODELS`
was written with `edge-tts`, `scribe_v2`, `gpt-image-1` and `gpt-image-2`.
Measured: `LLM_DEFAULTS`' 58 slots name only **10 distinct `(provider, model)`
pairs**, and exactly **two** are unknown to both registries — `edge/edge-tts`
and `elevenlabs/scribe_v2`. Both `gpt-image-*` are registry-known. The
allowlist becomes those two and its shrink-only bound becomes `<= 2`.

**A5 — `RegistryFacts` carries no `kind`.** LiteLLM's `mode` describes the API
surface; LIA's `kind` classifies the product for UI filtering. They answer
different questions, and the divergence is not error: over the 103 matched
rows, `mode=chat` maps to `kind=audio` six times (`gpt-4o-audio-preview` and
siblings) and to `kind=tts` once (`gemini-2.5-pro-preview-tts`) — 6.8 % of
matches. A field nothing may correctly consume is dead weight, so it is
excluded like the price, reasoning and streaming families, with its own
exclusion test. `mode` stays in the vendored snapshot: it is what lets a human
reviewing a `task llm:catalogue:fetch` diff tell what an entry is.

**A6 — models.dev `status` is a second, independent deprecation signal.**
LiteLLM publishes `deprecation_date` on 45 of LIA's rows (16 already past).
models.dev flags 8 rows `status="deprecated"`; seven are the same models, and
one is unique: `gemini-3.1-flash-lite-preview`, still active, with no LiteLLM
date — the preview class Google retires without publishing a date. Zero false
positives over the eight. `RegistryFacts` therefore carries
`registry_status: str | None` verbatim, and the *consumers* apply the policy:
a model is retiring when its date is within the notice window **or** its
status is `deprecated`. Facts stay facts.

**A7 — `max_tokens` is a genuine third source for the output cap.** Over the
512 LiteLLM entries, `max_tokens` and `max_output_tokens` **never** contradict
(361 agree, 0 differ), and `max_tokens` is the only one present on 22 entries
(the Gemini embedding and video families). Output precedence becomes
models.dev `limit.output` -> LiteLLM `max_output_tokens` -> LiteLLM
`max_tokens`.

Two of those amendments were themselves refuted by the next measurement.

**A7' — `max_tokens` is not an output source; A7 is withdrawn.** The 22 entries
where `max_tokens` is the only cap present all satisfy
`max_tokens == max_input_tokens` (Gemini embeddings, the `veo` family,
`gemini-1.5-flash`): LiteLLM files the *input* limit there. Over the 512
entries, `max_tokens` duplicates `max_output_tokens` 361 times, duplicates
`max_input_tokens` 22 times, and carries an output cap nothing else does
**zero** times. It is removed from `LITELLM_KEEP` and from the precedence.

**A8 — a non-positive token count is absence, not a value.** Registries publish
`0` for "not applicable": models.dev does it on all five image entries
(`limit: {input: 0, output: 0}`) and LiteLLM on the five moderation entries.
The plan's `_first` accepted `0` because it is not `None`, so the migration
would have written `max_output_tokens = 0` onto LIA's three image rows.
`_positive_int` now gates every token fact.

**A9 — an embedding row takes no output cap from any registry.** models.dev
fills `limit.output` with the **embedding dimension**: 3072 for
`text-embedding-3-large`, 1536 for `-small` and `ada-002`, 1 for
`gemini-embedding-001`. Importing it writes a vector width into a token
column. LiteLLM publishes nothing usable there either. `registry_facts` takes
an optional `kind`, and emits no `max_output_tokens` for `kind="embedding"` —
the caller supplies it because only LIA knows what its own row is, the
registries' `mode` answering a different question (A5).

The last three come from running the diff against the live catalogue.

**A10 — deactivation requires corroboration, and "announced" is not "gone".**
The plan deactivated any model whose `deprecation_date` had passed. Measured
over the snapshot: 71 LiteLLM entries are past their date; models.dev
corroborates 1, does not list 66 (it drops retired models, so silence is weak
corroboration) and **contradicts 4** by still listing them healthy —
`gpt-5.2-chat-latest`, `gpt-5.3-chat-latest` (rolling aliases OpenAI repoints,
where the date expires the snapshot rather than the alias) and two Gemini image
previews. The plan would have deactivated two live models.

Symmetrically, a `status="deprecated"` flag alone never deactivates: the seven
LIA rows carrying it also carry a date two months in the **future**
(2026-10-23) — announced, not gone.

The asymmetry is deliberate and follows `utils/react_budget.py`: deactivating a
live model drops it out of `ModelCapabilitiesCache` and falls back to
`CONSERVATIVE_DEFAULT`, whose `is_reasoning_model=False` makes the adapter send
sampling parameters to a reasoning model and the provider answer 400. Leaving a
dead model listed only leaves a stale dropdown entry, which the guard surfaces.
`is_retiring` (warn) and `is_retired` (may deactivate) are therefore two
predicates, one implementation each, in `field_mapping.py`. Result on LIA's 114
active rows: 23 retiring, of which **14 retired**, 2 disputed, 6 announced, 1
flagged. None of the 14 is referenced by `LLM_DEFAULTS`, by
`llm_config_overrides` or by a constant, so `kept_because_referenced` is 0.

**A11 — the `image_generation` slot points at a model that has no catalogue
row.** `llm_config_seed.sql:25` pins the slot to `gpt-image-2` and
`image_generation_pricing_seed.sql` prices it, but `llm_pricing_seed.sql`
never creates its `llm_models` row: `SELECT ... WHERE model_name='gpt-image-2'`
returns nothing on the dev instance. So `ModelCapabilitiesCache.get` answers
`None` and the runtime falls back to `CONSERVATIVE_DEFAULT`. Task 9 as written
would have moved the **code** default onto that same phantom. The row is added
to the models seed (active — every other image row is inactive, which is also
why the admin dropdown filtered by `required_kind=image` is empty) and the
correction migration inserts it where it is missing, so an existing instance
converges too.

**A12 — the seed postconditions are count-only.** `verify_reference_seeds.sql`
asserts cardinalities and nothing else, which is exactly why the `gpt-image-2`
orphan survived; it does not even count `llm_models`. Two blocking
postconditions are added in the ADR-215 style: an `llm_models` floor, and the
referential invariant that every `llm_config_overrides.model` names an existing
row. The *runtime* form of that invariant (existence + activation +
`required_kind`) belongs to Lot 0b, which owns the capability gate.

Four more came out of execution.

**A13 — the input budget comes from models.dev's explicit `input`, not from
LiteLLM.** LiteLLM documents `max_input_tokens` as the input budget but
populates it with the TOTAL window on some entries. Over the 19 models where
both registries state an input budget, 13 agree and **all six** disagreements
are exactly `litellm.max_input_tokens == modelsdev.limit.context`: `gpt-5-pro`
(400 000 against a real 272 000), `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.5`,
`gpt-5.5-pro` (1 050 000 against 922 000) and `gpt-realtime-2.1` (128 000
against 96 000). Zero disagreements have any other shape. Precedence is now
models.dev `input` -> LiteLLM `max_input_tokens` -> models.dev
`context - output`.

**A14 — an output cap equal to the model's own window is refused.** models.dev
does that on nine entries (`openai/gpt-4` claims 8192 for both where LiteLLM
states the real 4096). Those fall through to LiteLLM. The two registries
otherwise disagree on 25 of the 143 comparable models with no structural
pattern (16 times LiteLLM smaller, 9 larger); that residue is recorded as a
stated limitation, not a solved problem.

**A15 — provenance follows corroboration, not change.** The first
implementation promoted a row to `imported` only when a value actually moved,
so 15 rows whose values already matched the registry stayed `declared` — and
`get_effective_context_window` ignores a `declared` row. `deepseek-v4-flash`,
the model 27 slots run on, was among them. Promotion now happens whenever the
registry corroborates any correctable field.

**A16 — `verified` gets the producer it lacked, and 21 slots move.**
`LLMCapabilityProvenanceEnum.verified` would otherwise have been a member no
code path could reach. `LLMModelService.update` now stamps it when a human
changes a registry-owned capability (the admin UI and the ADR-228 Excel
round-trip share that path), which is what will stop a future continuous sync
from overwriting a curated row. Creation deliberately does not stamp it: the
form's untouched defaults are exactly what `declared` means, and claiming they
were verified would make the runtime trust an 8 192 placeholder.

Task 9 also turned out to be three time bombs plus a fourth the plan had not
counted: **21 `LLM_DEFAULTS` slots** default to `gpt-4.1-nano`, which retires
2026-10-23 and which models.dev already flags deprecated, and only 5 of them
are overridden by the reference seed. They move to `gpt-4.1-mini`: the only
candidate with an identical capability shape (non-reasoning, accepts
`temperature`/`top_p`, same 1 047 576 window), no deprecation date, and already
present in the compliance matrix. The cheaper candidates were rejected on
evidence — `gpt-5-nano` ($0.05/$0.40 against nano's $0.10/$0.40) is a reasoning
model that accepts neither `temperature` nor `top_p`, so adopting it would mean
rewriting 21 configurations, a behavioural change that belongs to Lot 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/src/infrastructure/llm/catalogue/__init__.py` | package marker |
| `apps/api/src/infrastructure/llm/catalogue/snapshot.json` | vendored, filtered registry snapshot (capabilities only) |
| `apps/api/src/infrastructure/llm/catalogue/NOTICE.md` | upstream MIT notice + provenance |
| `apps/api/src/infrastructure/llm/catalogue/registry_match.py` | canonical provider mapping + the two matchers |
| `apps/api/src/infrastructure/llm/catalogue/field_mapping.py` | `RegistryFacts` + per-field precedence |
| `apps/api/src/infrastructure/llm/catalogue/snapshot_loader.py` | load + cache the vendored snapshot |
| `scripts/llm_catalogue/fetch_snapshot.py` | developer task: download, filter, write the snapshot |
| `scripts/llm_catalogue/sync.py` | compute and print the reviewable diff |
| `apps/api/alembic/versions/2026_08_24_0900-<rev>_llm_model_provenance.py` | schema: provenance + deprecation columns |
| `apps/api/alembic/versions/2026_08_24_0930-<rev>_llm_catalogue_initial_correction.py` | data: apply the audited correction |
| `apps/api/tests/unit/infrastructure/llm/catalogue/test_registry_match.py` | matcher tests |
| `apps/api/tests/unit/infrastructure/llm/catalogue/test_field_mapping.py` | precedence + exclusion tests |
| `apps/api/tests/unit/test_model_capability_provenance_guard.py` | CI guard (shrink-only allowlist) |
| `apps/api/tests/unit/test_no_deprecated_model_referenced_guard.py` | CI guard |
| `apps/api/tests/unit/domains/llm_config/test_effective_context_window.py` | provenance arbitration |

---

### Task 1: Vendored snapshot and its fetch task

**Files:**
- Create: `apps/api/src/infrastructure/llm/catalogue/__init__.py`
- Create: `apps/api/src/infrastructure/llm/catalogue/NOTICE.md`
- Create: `apps/api/src/infrastructure/llm/catalogue/snapshot.json`
- Create: `scripts/llm_catalogue/fetch_snapshot.py`
- Create: `apps/api/src/infrastructure/llm/catalogue/snapshot_loader.py`
- Test: `apps/api/tests/unit/infrastructure/llm/catalogue/test_snapshot_loader.py`
- Modify: `Taskfile.yml`

**Interfaces:**
- Produces: `load_snapshot() -> Snapshot`, where
  `Snapshot = dict[str, dict[str, dict[str, Any]]]` keyed
  `source ("litellm" | "modelsdev") -> entry key -> fields`;
  `SNAPSHOT_PATH: Path`; `snapshot_generated_at() -> datetime`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/catalogue/test_snapshot_loader.py`:

```python
"""The vendored registry snapshot loads, is complete and carries no excluded field."""

from __future__ import annotations

from datetime import UTC, datetime

from src.infrastructure.llm.catalogue.snapshot_loader import (
    SNAPSHOT_PATH,
    load_snapshot,
    snapshot_generated_at,
)

FORBIDDEN_SUBSTRINGS = ("cost", "price", "reasoning", "effort", "streaming", "temperature")


def test_snapshot_file_is_vendored() -> None:
    assert SNAPSHOT_PATH.is_file(), "the snapshot must ship with the source tree"


def test_snapshot_has_both_sources() -> None:
    snap = load_snapshot()
    assert set(snap) == {"litellm", "modelsdev"}
    assert len(snap["litellm"]) > 100
    assert len(snap["modelsdev"]) > 50


def test_snapshot_carries_no_excluded_field() -> None:
    """Prices, reasoning, streaming and sampling flags are never vendored."""
    snap = load_snapshot()
    for source, entries in snap.items():
        for key, fields in entries.items():
            for field in fields:
                lowered = field.lower()
                assert not any(bad in lowered for bad in FORBIDDEN_SUBSTRINGS), (
                    f"{source}/{key} carries excluded field {field!r}"
                )


def test_snapshot_generated_at_is_utc() -> None:
    stamp = snapshot_generated_at()
    assert stamp.tzinfo is UTC or stamp.utcoffset() is not None
    assert stamp <= datetime.now(UTC)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_snapshot_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.infrastructure.llm.catalogue'`.

- [ ] **Step 3: Write the fetch script**

Create `scripts/llm_catalogue/fetch_snapshot.py`:

```python
"""Download, filter and vendor the public model-capability snapshot.

Two upstream registries, both fetched by hand (never at runtime):

- ``BerriAI/litellm`` ``model_prices_and_context_window.json`` — MIT (the file
  sits at the repository root, outside ``enterprise/``).
- ``models.dev`` ``api.json``.

Only capability fields are kept, and only for the providers LIA can serve.
Prices, reasoning metadata, streaming and the sampling flags are dropped on
purpose — see the design spec, sections 0 ter and 0 quinquies.

Usage:
    task llm:catalogue:fetch
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
MODELSDEV_URL = "https://models.dev/api.json"

OUT = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "api"
    / "src"
    / "infrastructure"
    / "llm"
    / "catalogue"
    / "snapshot.json"
)

#: LiteLLM ``litellm_provider`` values LIA can serve.
LITELLM_PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "gemini",
    "vertex_ai-language-models",
    "dashscope",
    "perplexity",
    "ollama",
    "elevenlabs",
}
#: models.dev top-level provider ids LIA can serve (canonical vendors only).
MODELSDEV_PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "google",
    "google-vertex",
    "alibaba",
    "alibaba-cn",
    "perplexity",
    "ollama",
}

LITELLM_KEEP = {
    "litellm_provider",
    "mode",
    "max_input_tokens",
    "max_output_tokens",
    "max_tokens",
    "supports_function_calling",
    "supports_response_schema",
    "supports_vision",
    "deprecation_date",
}
MODELSDEV_KEEP = {"limit", "tool_call", "structured_output", "attachment", "status"}


def _fetch(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _filter_litellm(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict) or value.get("litellm_provider") not in LITELLM_PROVIDERS:
            continue
        out[key] = {k: v for k, v in value.items() if k in LITELLM_KEEP}
    return out


def _filter_modelsdev(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for provider_id, provider in raw.items():
        if provider_id not in MODELSDEV_PROVIDERS:
            continue
        for model_id, model in provider.get("models", {}).items():
            kept = {k: v for k, v in model.items() if k in MODELSDEV_KEEP}
            kept["provider"] = provider_id
            out[f"{provider_id}/{model_id}"] = kept
    return out


def main() -> None:
    """Fetch both registries, filter them and write the vendored snapshot."""
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "litellm": _filter_litellm(_fetch(LITELLM_URL)),
        "modelsdev": _filter_modelsdev(_fetch(MODELSDEV_URL)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(  # noqa: T201  (developer tool, not application code)
        f"wrote {OUT} — litellm={len(snapshot['litellm'])} modelsdev={len(snapshot['modelsdev'])}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the loader**

Create `apps/api/src/infrastructure/llm/catalogue/__init__.py`:

```python
"""Vendored public model-capability registries and their matchers."""
```

Create `apps/api/src/infrastructure/llm/catalogue/snapshot_loader.py`:

```python
"""Load the vendored registry snapshot.

The snapshot ships with the source tree and is the ONLY registry source at
runtime: nothing here touches the network. Refreshing it is a developer task
(``task llm:catalogue:fetch``) whose output is reviewed like any other diff.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("snapshot.json")

Snapshot = dict[str, dict[str, dict[str, Any]]]


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def load_snapshot() -> Snapshot:
    """Return the vendored snapshot, keyed by source then by entry key.

    Returns:
        ``{"litellm": {key: fields}, "modelsdev": {"provider/model": fields}}``.
    """
    raw = _raw()
    return {"litellm": raw["litellm"], "modelsdev": raw["modelsdev"]}


def snapshot_generated_at() -> datetime:
    """Return when the snapshot was fetched (timezone-aware UTC)."""
    return datetime.fromisoformat(_raw()["generated_at"])
```

Create `apps/api/src/infrastructure/llm/catalogue/NOTICE.md`:

```markdown
# Vendored registry snapshot — provenance and licence

`snapshot.json` is a filtered derivative of two public registries.

## BerriAI/litellm — `model_prices_and_context_window.json`

Licensed **MIT**. The file sits at the repository root, outside `enterprise/`,
so the MIT half of the dual-licence header applies.

```
MIT License — Copyright (c) 2023 Berri AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## models.dev — `api.json`

Public aggregate registry, consulted for capability fields only.

## What is kept, and what is not

Only capability fields, and only for providers LIA can serve. **Prices,
reasoning metadata, streaming support and the sampling flags are excluded by
design** — each exclusion is a measured decision recorded in
`docs/superpowers/specs/2026-08-23-llm-model-policy-design.md`.
```

- [ ] **Step 5: Add the Taskfile entry**

In `Taskfile.yml`, next to the other `deps:` tasks, add:

```yaml
  llm:catalogue:fetch:
    desc: Refresh the vendored public model-capability snapshot (network; review the diff)
    cmds:
      - python scripts/llm_catalogue/fetch_snapshot.py
```

- [ ] **Step 6: Generate the snapshot**

Run: `task llm:catalogue:fetch`
Expected: `wrote .../snapshot.json — litellm=<n> modelsdev=<m>` with `n > 100` and `m > 50`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/ -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/infrastructure/llm/catalogue scripts/llm_catalogue Taskfile.yml apps/api/tests/unit/infrastructure/llm/catalogue
git commit -m "feat(llm): vendor a filtered public model-capability snapshot (ADR-244)"
```

---

### Task 2: Canonical-provider-locked matcher

**Files:**
- Create: `apps/api/src/infrastructure/llm/catalogue/registry_match.py`
- Test: `apps/api/tests/unit/infrastructure/llm/catalogue/test_registry_match.py`

**Interfaces:**
- Consumes: `load_snapshot()` from Task 1.
- Produces: `match_litellm(provider: str, model: str) -> dict[str, Any] | None`,
  `match_modelsdev(provider: str, model: str) -> dict[str, Any] | None`,
  `LITELLM_PROVIDERS: dict[str, tuple[str, ...]]`,
  `MODELSDEV_PROVIDERS: dict[str, tuple[str, ...]]`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/catalogue/test_registry_match.py`:

```python
"""A registry entry is accepted only from LIA's canonical provider.

models.dev publishes 193 providers; ``deepseek-v4-flash`` appears under 23 of
them with output caps from 32 768 to 1 048 576, and ``jiekou`` declares
``gpt-5.2`` with the opposite reasoning flags to the canonical ``openai``
entry. Matching by model id alone would ingest resale metadata.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.catalogue.registry_match import (
    LITELLM_PROVIDERS,
    MODELSDEV_PROVIDERS,
    match_litellm,
    match_modelsdev,
)


def test_litellm_matches_canonical_provider() -> None:
    entry = match_litellm("openai", "gpt-5.2")
    assert entry is not None
    assert entry["litellm_provider"] == "openai"


def test_litellm_rejects_wrong_provider() -> None:
    """The same model id under another LIA provider must not match."""
    assert match_litellm("anthropic", "gpt-5.2") is None


def test_modelsdev_matches_canonical_vendor_only() -> None:
    entry = match_modelsdev("openai", "gpt-5.2")
    assert entry is not None
    assert entry["provider"] == "openai"


def test_modelsdev_never_returns_a_reseller_entry() -> None:
    """Every models.dev hit must come from a declared canonical vendor."""
    for lia_provider, vendors in MODELSDEV_PROVIDERS.items():
        for model in ("deepseek-v4-flash", "gpt-5.2", "claude-opus-4-6"):
            entry = match_modelsdev(lia_provider, model)
            if entry is not None:
                assert entry["provider"] in vendors


def test_unknown_provider_returns_none() -> None:
    assert match_litellm("edge", "edge-tts") is None
    assert match_modelsdev("edge", "edge-tts") is None


@pytest.mark.parametrize("lia_provider", sorted(LITELLM_PROVIDERS))
def test_every_declared_provider_is_a_known_lia_provider(lia_provider: str) -> None:
    from src.domains.llm.models import LLMProviderEnum

    assert lia_provider in {member.value for member in LLMProviderEnum}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_registry_match.py -v`
Expected: FAIL — `ModuleNotFoundError: ... registry_match`.

- [ ] **Step 3: Write the matcher**

Create `apps/api/src/infrastructure/llm/catalogue/registry_match.py`:

```python
"""Canonical-provider-locked lookup into the vendored registry snapshot.

Matching a model id alone is FORBIDDEN. models.dev publishes 193 providers and
many republish the same id with contradictory metadata: ``deepseek-v4-flash``
appears under 23 of them with output caps from 32 768 to 1 048 576, and
``jiekou`` declares ``gpt-5.2`` as ``reasoning=False, temperature=True`` — the
opposite of the canonical ``openai`` entry. Every lookup therefore names LIA's
provider, and only entries from that provider's canonical vendor(s) match.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.llm.catalogue.snapshot_loader import load_snapshot

#: LIA provider -> the ``litellm_provider`` values that may serve it.
LITELLM_PROVIDERS: dict[str, tuple[str, ...]] = {
    "openai": ("openai",),
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "gemini": ("gemini", "vertex_ai-language-models"),
    "qwen": ("dashscope",),
    "perplexity": ("perplexity",),
    "ollama": ("ollama",),
    "elevenlabs": ("elevenlabs",),
}

#: LIA provider -> the models.dev vendor ids that may serve it.
MODELSDEV_PROVIDERS: dict[str, tuple[str, ...]] = {
    "openai": ("openai",),
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "gemini": ("google", "google-vertex"),
    "qwen": ("alibaba", "alibaba-cn"),
    "perplexity": ("perplexity",),
    "ollama": ("ollama",),
}


def match_litellm(provider: str, model: str) -> dict[str, Any] | None:
    """Look up ``model`` in the LiteLLM snapshot, locked to ``provider``.

    Args:
        provider: LIA provider id (``llm_models.provider``).
        model: LIA model name (``llm_models.model_name``).

    Returns:
        The snapshot entry, or ``None`` when the model is unknown to that
        provider.
    """
    allowed = LITELLM_PROVIDERS.get(provider)
    if not allowed:
        return None
    entries = load_snapshot()["litellm"]
    direct = entries.get(model)
    if isinstance(direct, dict) and direct.get("litellm_provider") in allowed:
        return direct
    for key, value in entries.items():
        if value.get("litellm_provider") in allowed and key.split("/")[-1] == model:
            return value
    return None


def match_modelsdev(provider: str, model: str) -> dict[str, Any] | None:
    """Look up ``model`` in the models.dev snapshot, locked to ``provider``.

    Args:
        provider: LIA provider id.
        model: LIA model name.

    Returns:
        The snapshot entry, or ``None``.
    """
    entries = load_snapshot()["modelsdev"]
    for vendor in MODELSDEV_PROVIDERS.get(provider, ()):
        entry = entries.get(f"{vendor}/{model}")
        if entry is not None:
            return entry
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_registry_match.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/infrastructure/llm/catalogue/registry_match.py apps/api/tests/unit/infrastructure/llm/catalogue/test_registry_match.py
git commit -m "feat(llm): canonical-provider-locked registry matcher (ADR-244)"
```

---

### Task 3: Per-field precedence mapper

**Files:**
- Create: `apps/api/src/infrastructure/llm/catalogue/field_mapping.py`
- Test: `apps/api/tests/unit/infrastructure/llm/catalogue/test_field_mapping.py`

**Interfaces:**
- Consumes: `match_litellm`, `match_modelsdev` from Task 2.
- Produces: `RegistryFacts` (frozen dataclass with fields `max_input_tokens: int | None`,
  `max_output_tokens: int | None`, `kind: str | None`, `supports_tools: bool | None`,
  `supports_structured_output: bool | None`, `supports_vision: bool | None`,
  `deprecation_date: date | None`, `sources: dict[str, str]`) and
  `registry_facts(provider: str, model: str) -> RegistryFacts | None`.

**Read first:** spec §0 ter and §0 quinquies. They explain, with measurements, why prices, reasoning and streaming are absent from `RegistryFacts`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/catalogue/test_field_mapping.py`:

```python
"""Per-field precedence, and the exclusions that are load-bearing."""

from __future__ import annotations

import dataclasses

from src.infrastructure.llm.catalogue.field_mapping import RegistryFacts, registry_facts


def test_context_window_prefers_litellm() -> None:
    """models.dev ``limit.context`` is the TOTAL window, not the input budget.

    56 of 75 models.dev entries expose only ``context``; using it as
    ``max_input_tokens`` over-estimates. LiteLLM's ``max_input_tokens`` wins.
    """
    facts = registry_facts("openai", "gpt-5.2")
    assert facts is not None
    assert facts.max_input_tokens == 272_000
    assert facts.sources["max_input_tokens"] == "litellm"


def test_unknown_model_returns_none() -> None:
    assert registry_facts("ollama", "a-model-that-does-not-exist") is None


def test_facts_carry_no_price_field() -> None:
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    assert not any("cost" in n or "price" in n for n in names)


def test_facts_carry_no_reasoning_field() -> None:
    """Reasoning metadata is LIA-owned: a naive import invalidated 21 slots."""
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    assert not any("reasoning" in n or "effort" in n for n in names)


def test_facts_carry_no_streaming_or_sampling_field() -> None:
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    for forbidden in ("streaming", "temperature", "top_p", "frequency", "presence"):
        assert not any(forbidden in n for n in names)


def test_every_populated_field_records_its_source() -> None:
    facts = registry_facts("openai", "gpt-5.2")
    assert facts is not None
    for field in dataclasses.fields(RegistryFacts):
        if field.name == "sources":
            continue
        if getattr(facts, field.name) is not None:
            assert field.name in facts.sources
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_field_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: ... field_mapping`.

- [ ] **Step 3: Write the mapper**

Create `apps/api/src/infrastructure/llm/catalogue/field_mapping.py`:

```python
"""Merge the two registries into capability facts, with a declared precedence.

Only fields LIA may safely import appear here. Three families are excluded by
measurement, not by caution (see the design spec):

- **prices** — 85 of 87 models were price-stable over two months and the only
  two "changes" were tier-tracking artefacts; the registries also publish one
  tier among six and follow promotions, and neither can express ADR-223 time
  slots;
- **reasoning metadata** — a naive import invalidates ``effort: off`` on 21
  slots and silently switches the pipeline to thinking mode;
- **streaming and the sampling flags** — a false would break SSE on
  ``response``, and no registry covers them reliably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.infrastructure.llm.catalogue.registry_match import match_litellm, match_modelsdev


@dataclass(frozen=True)
class RegistryFacts:
    """Capability facts a registry may contribute for one model."""

    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    kind: str | None = None
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_vision: bool | None = None
    deprecation_date: date | None = None
    sources: dict[str, str] = field(default_factory=dict)


def _first(
    candidates: list[tuple[str, Any]],
    sources: dict[str, str],
    name: str,
) -> Any:
    """Return the first non-``None`` candidate and record where it came from."""
    for source, value in candidates:
        if value is not None:
            sources[name] = source
            return value
    return None


def _max_input(ll: dict[str, Any] | None, md: dict[str, Any] | None) -> Any:
    """LiteLLM first: models.dev often exposes only the TOTAL window."""
    if ll and ll.get("max_input_tokens"):
        return "litellm", ll["max_input_tokens"]
    limit = (md or {}).get("limit") or {}
    if limit.get("input"):
        return "modelsdev", limit["input"]
    if limit.get("context") and limit.get("output"):
        return "modelsdev", limit["context"] - limit["output"]
    return None, None


def registry_facts(provider: str, model: str) -> RegistryFacts | None:
    """Merge both registries for one model, or ``None`` when neither knows it.

    Args:
        provider: LIA provider id.
        model: LIA model name.

    Returns:
        The merged facts, with a ``sources`` map naming the registry that
        supplied each populated field.
    """
    ll = match_litellm(provider, model)
    md = match_modelsdev(provider, model)
    if ll is None and md is None:
        return None

    sources: dict[str, str] = {}
    limit = (md or {}).get("limit") or {}

    in_source, in_value = _max_input(ll, md)
    if in_value is not None:
        sources["max_input_tokens"] = in_source

    out_value = _first(
        [("modelsdev", limit.get("output")), ("litellm", (ll or {}).get("max_output_tokens"))],
        sources,
        "max_output_tokens",
    )
    kind = _first([("litellm", (ll or {}).get("mode"))], sources, "kind")
    tools = _first(
        [
            ("modelsdev", (md or {}).get("tool_call")),
            ("litellm", (ll or {}).get("supports_function_calling")),
        ],
        sources,
        "supports_tools",
    )
    structured = _first(
        [
            ("modelsdev", (md or {}).get("structured_output")),
            ("litellm", (ll or {}).get("supports_response_schema")),
        ],
        sources,
        "supports_structured_output",
    )
    vision = _first(
        [
            ("modelsdev", (md or {}).get("attachment")),
            ("litellm", (ll or {}).get("supports_vision")),
        ],
        sources,
        "supports_vision",
    )
    raw_deprecation = _first(
        [("litellm", (ll or {}).get("deprecation_date"))], sources, "deprecation_date"
    )
    deprecation = date.fromisoformat(raw_deprecation) if raw_deprecation else None

    return RegistryFacts(
        max_input_tokens=in_value,
        max_output_tokens=out_value,
        kind=kind,
        supports_tools=None if tools is None else bool(tools),
        supports_structured_output=None if structured is None else bool(structured),
        supports_vision=None if vision is None else bool(vision),
        deprecation_date=deprecation,
        sources=sources,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_field_mapping.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/infrastructure/llm/catalogue/field_mapping.py apps/api/tests/unit/infrastructure/llm/catalogue/test_field_mapping.py
git commit -m "feat(llm): per-field registry precedence with measured exclusions (ADR-244)"
```

---

### Task 4: Provenance and deprecation columns

**Files:**
- Modify: `apps/api/src/domains/llm/models.py` (after `is_active`, around line 205)
- Create: `apps/api/alembic/versions/2026_08_24_0900-a0b1c2d3e4f5_llm_model_provenance.py`
- Test: `apps/api/tests/unit/domains/llm/test_model_provenance_column.py`

**Interfaces:**
- Produces: `LLMCapabilityProvenanceEnum` (`declared` / `imported` / `verified`),
  `LLMModel.capability_provenance`, `LLMModel.deprecation_date`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/domains/llm/test_model_provenance_column.py`:

```python
"""Capability provenance: which authority filled a row's capability fields."""

from __future__ import annotations

from src.domains.llm.models import LLMCapabilityProvenanceEnum, LLMModel


def test_provenance_enum_values() -> None:
    assert {m.value for m in LLMCapabilityProvenanceEnum} == {
        "declared",
        "imported",
        "verified",
    }


def test_model_declares_the_columns() -> None:
    columns = LLMModel.__table__.columns
    assert "capability_provenance" in columns
    assert "deprecation_date" in columns
    assert columns["deprecation_date"].nullable is True
    assert columns["capability_provenance"].nullable is False


def test_provenance_defaults_to_declared() -> None:
    """A row nobody curated must announce itself as uncurated."""
    assert (
        LLMModel.__table__.columns["capability_provenance"].default.arg
        is LLMCapabilityProvenanceEnum.declared
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm/test_model_provenance_column.py -v`
Expected: FAIL — `ImportError: cannot import name 'LLMCapabilityProvenanceEnum'`.

- [ ] **Step 3: Add the enum and the columns**

In `apps/api/src/domains/llm/models.py`, after `LLMReasoningWidgetEnum` (around line 92), add:

```python
class LLMCapabilityProvenanceEnum(str, enum.Enum):
    """Which authority filled a model row's capability fields.

    Measured 2026-08-23: 89 of 114 active rows carried the column defaults
    (``max_input_tokens=8192 / max_output_tokens=4096``), so
    ``get_effective_context_window`` returned 8 192 for ``gpt-5.2`` against a
    real 272 000. Provenance is what lets the runtime tell a measurement from a
    default, instead of trusting both equally.
    """

    declared = "declared"  # column defaults — never curated, do not trust
    imported = "imported"  # from the vendored registry snapshot or the pricing sheet
    verified = "verified"  # a human confirmed it; the sync never overwrites this
```

In the `LLMModel` class, after `is_active`, add:

```python
    capability_provenance: Mapped[LLMCapabilityProvenanceEnum] = mapped_column(
        SQLEnum(
            LLMCapabilityProvenanceEnum,
            name="llm_capability_provenance_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMCapabilityProvenanceEnum.declared,
        server_default=LLMCapabilityProvenanceEnum.declared.value,
        comment="Authority that filled the capability fields (declared/imported/verified)",
    )

    deprecation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Provider retirement date from the vendored registry snapshot",
    )
```

Add to the imports at the top of the file: `from datetime import date` and add `Date` to the existing `from sqlalchemy import (...)` block.

- [ ] **Step 4: Create the migration**

Create `apps/api/alembic/versions/2026_08_24_0900-a0b1c2d3e4f5_llm_model_provenance.py`:

```python
"""Capability provenance and provider deprecation date on llm_models (ADR-244).

``capability_provenance`` distinguishes a measured capability from a column
default: 89 of 114 active rows carried the defaults, which is why
``get_effective_context_window`` returned 8 192 for ``gpt-5.2``.
``deprecation_date`` carries the provider retirement date so a retired model
stops being offered.

Revision ID: a0b1c2d3e4f5
Revises: 9b0c1d2e3f4a
Create Date: 2026-08-24 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "9b0c1d2e3f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "llm_capability_provenance_enum"
_VALUES = ("declared", "imported", "verified")


def upgrade() -> None:
    """Add the provenance enum column and the deprecation date."""
    provenance = sa.Enum(*_VALUES, name=_ENUM_NAME)
    provenance.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "llm_models",
        sa.Column(
            "capability_provenance",
            provenance,
            nullable=False,
            server_default="declared",
            comment="Authority that filled the capability fields (declared/imported/verified)",
        ),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "deprecation_date",
            sa.Date(),
            nullable=True,
            comment="Provider retirement date from the vendored registry snapshot",
        ),
    )


def downgrade() -> None:
    """Drop both columns and the enum type."""
    op.drop_column("llm_models", "deprecation_date")
    op.drop_column("llm_models", "capability_provenance")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 5: Apply the migration and verify a single head**

Run: `task db:migrate`
Then: `cd apps/api && .venv/Scripts/alembic heads`
Expected: exactly one head, `a0b1c2d3e4f5`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm/test_model_provenance_column.py -v`
Expected: 3 passed.

- [ ] **Step 7: Verify the migration replays**

Run: `task db:migrate:replay-check`
Expected: success.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/domains/llm/models.py apps/api/alembic/versions/2026_08_24_0900-a0b1c2d3e4f5_llm_model_provenance.py apps/api/tests/unit/domains/llm/test_model_provenance_column.py
git commit -m "feat(llm): capability provenance and deprecation date on llm_models (ADR-244)"
```

---

### Task 5: The reviewable sync diff

**Files:**
- Create: `scripts/llm_catalogue/sync.py`
- Test: `apps/api/tests/unit/infrastructure/llm/catalogue/test_sync_diff.py`
- Modify: `Taskfile.yml`

**Interfaces:**
- Consumes: `registry_facts` from Task 3, `LLMCapabilityProvenanceEnum` from Task 4.
- Produces: `compute_diff(rows: list[CatalogueRow]) -> list[FieldChange]` and
  `CatalogueRow` / `FieldChange` frozen dataclasses, where
  `FieldChange = (model_name, provider, field, current, proposed, source, severity)`
  and `severity ∈ {"auto", "review"}`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/infrastructure/llm/catalogue/test_sync_diff.py`:

```python
"""The sync proposes; it never decides for a human-curated row."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts"))

from llm_catalogue.sync import CatalogueRow, compute_diff  # noqa: E402


def _row(**kwargs: object) -> CatalogueRow:
    base = {
        "model_name": "gpt-5.2",
        "provider": "openai",
        "kind": "chat",
        "max_input_tokens": 8192,
        "max_output_tokens": 4096,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_vision": False,
        "provenance": "declared",
        "deprecation_date": None,
        "is_active": True,
    }
    base.update(kwargs)
    return CatalogueRow(**base)  # type: ignore[arg-type]


def test_declared_row_change_is_auto() -> None:
    changes = compute_diff([_row()])
    windows = [c for c in changes if c.field == "max_input_tokens"]
    assert windows, "the 8192 placeholder must be proposed for correction"
    assert windows[0].proposed == 272_000
    assert windows[0].severity == "auto"


def test_verified_row_change_needs_review() -> None:
    changes = compute_diff([_row(provenance="verified")])
    windows = [c for c in changes if c.field == "max_input_tokens"]
    assert windows[0].severity == "review"


def test_no_change_proposed_when_values_agree() -> None:
    changes = compute_diff([_row(max_input_tokens=272_000)])
    assert not [c for c in changes if c.field == "max_input_tokens"]


def test_unknown_model_yields_no_change() -> None:
    assert compute_diff([_row(model_name="not-a-real-model")]) == []


def test_no_price_or_reasoning_field_is_ever_proposed() -> None:
    fields = {c.field for c in compute_diff([_row()])}
    for forbidden in ("cost", "price", "reasoning", "effort", "streaming", "temperature"):
        assert not any(forbidden in f for f in fields)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_sync_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm_catalogue.sync'`.

- [ ] **Step 3: Write the diff engine**

Create `scripts/llm_catalogue/__init__.py`:

```python
"""Developer tooling for the vendored model-capability catalogue."""
```

Create `scripts/llm_catalogue/sync.py`:

```python
"""Compute a reviewable diff between the catalogue and the vendored snapshot.

Severity, not silence:

- ``auto``   — the row's provenance is ``declared`` (column defaults nobody
  curated). Applying the registry value can lose no human decision.
- ``review`` — the row is ``imported`` or ``verified``. A human decided; the
  sync may only propose.

Prices, reasoning metadata and streaming are never examined (see the design
spec). Nothing here writes to the database: ``task llm:catalogue:sync`` prints
the diff, and the initial correction ships as a versioned migration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from src.infrastructure.llm.catalogue.field_mapping import registry_facts

#: Catalogue column -> the ``RegistryFacts`` attribute that may correct it.
COMPARED_FIELDS: tuple[tuple[str, str], ...] = (
    ("max_input_tokens", "max_input_tokens"),
    ("max_output_tokens", "max_output_tokens"),
    ("supports_tools", "supports_tools"),
    ("supports_structured_output", "supports_structured_output"),
    ("supports_vision", "supports_vision"),
    ("deprecation_date", "deprecation_date"),
)


@dataclass(frozen=True)
class CatalogueRow:
    """One ``llm_models`` row, reduced to what the diff compares."""

    model_name: str
    provider: str
    kind: str
    max_input_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    provenance: str
    deprecation_date: date | None
    is_active: bool


@dataclass(frozen=True)
class FieldChange:
    """One proposed correction."""

    model_name: str
    provider: str
    field: str
    current: object
    proposed: object
    source: str
    severity: str


def compute_diff(rows: list[CatalogueRow]) -> list[FieldChange]:
    """Compare every row against the vendored snapshot.

    Args:
        rows: The catalogue rows to examine.

    Returns:
        One :class:`FieldChange` per differing field, ordered by model then
        field.
    """
    changes: list[FieldChange] = []
    for row in rows:
        facts = registry_facts(row.provider, row.model_name)
        if facts is None:
            continue
        severity = "auto" if row.provenance == "declared" else "review"
        for column, attribute in COMPARED_FIELDS:
            proposed = getattr(facts, attribute)
            if proposed is None:
                continue
            current = getattr(row, column)
            if current == proposed:
                continue
            changes.append(
                FieldChange(
                    model_name=row.model_name,
                    provider=row.provider,
                    field=column,
                    current=current,
                    proposed=proposed,
                    source=facts.sources.get(attribute, "?"),
                    severity=severity,
                )
            )
    return changes


async def _load_rows() -> list[CatalogueRow]:
    from sqlalchemy import select

    from src.domains.llm.models import LLMModel
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        found = list((await db.execute(select(LLMModel).where(LLMModel.is_active))).scalars().all())
    return [
        CatalogueRow(
            model_name=m.model_name,
            provider=m.provider.value,
            kind=m.kind.value,
            max_input_tokens=m.max_input_tokens,
            max_output_tokens=m.max_output_tokens,
            supports_tools=m.supports_tools,
            supports_structured_output=m.supports_structured_output,
            supports_vision=m.supports_vision,
            provenance=m.capability_provenance.value,
            deprecation_date=m.deprecation_date,
            is_active=m.is_active,
        )
        for m in found
    ]


def main() -> None:
    """Print the diff, grouped by severity."""
    changes = asyncio.run(_main_async())
    auto = [c for c in changes if c.severity == "auto"]
    review = [c for c in changes if c.severity == "review"]
    print(f"AUTO   ({len(auto)}) — provenance=declared, no human decision at stake")  # noqa: T201
    for c in auto:
        print(f"  {c.model_name:34s} {c.field:28s} {c.current!r} -> {c.proposed!r}  [{c.source}]")  # noqa: T201
    print(f"\nREVIEW ({len(review)}) — a human curated this row")  # noqa: T201
    for c in review:
        print(f"  {c.model_name:34s} {c.field:28s} {c.current!r} -> {c.proposed!r}  [{c.source}]")  # noqa: T201


async def _main_async() -> list[FieldChange]:
    return compute_diff(await _load_rows())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add the Taskfile entry**

In `Taskfile.yml`, next to `llm:catalogue:fetch`, add:

```yaml
  llm:catalogue:sync:
    desc: Print the reviewable catalogue diff against the vendored snapshot (read-only)
    dir: "{{.API_DIR}}"
    cmds:
      - "{{.PYTHON}} ../../scripts/llm_catalogue/sync.py"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/catalogue/test_sync_diff.py -v`
Expected: 5 passed.

- [ ] **Step 6: Produce the diff and keep it**

Run: `task llm:catalogue:sync > /tmp/catalogue-diff.txt`
Expected: an `AUTO` block with roughly 80 corrections and a short `REVIEW` block. **Keep this output — Task 6 turns it into the migration.**

- [ ] **Step 7: Commit**

```bash
git add scripts/llm_catalogue Taskfile.yml apps/api/tests/unit/infrastructure/llm/catalogue/test_sync_diff.py
git commit -m "feat(llm): reviewable catalogue sync diff (ADR-244)"
```

---

### Task 6: Apply the initial correction

**Files:**
- Create: `apps/api/alembic/versions/2026_08_24_0930-b1c2d3e4f5a6_llm_catalogue_initial_correction.py`
- Test: `apps/api/tests/integration/test_catalogue_initial_correction.py`

**Interfaces:**
- Consumes: the diff from Task 5, the columns from Task 4.
- Produces: a catalogue whose `auto` rows carry registry values and provenance `imported`;
  deprecated-and-unreferenced models deactivated.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/integration/test_catalogue_initial_correction.py`:

```python
"""After the correction, the catalogue tells the truth about the models in use."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.domains.llm.models import LLMCapabilityProvenanceEnum, LLMModel

pytestmark = pytest.mark.integration

#: Cross-checked against both registries on 2026-08-23.
EXPECTED_INPUT_WINDOWS = {
    "gpt-5.2": 272_000,
    "gpt-5.4-mini": 272_000,
    "claude-opus-4-6": 1_000_000,
    "gpt-5.6-luna": 922_000,
}


async def test_corrected_context_windows(db_session) -> None:
    rows = {
        m.model_name: m
        for m in (await db_session.execute(select(LLMModel))).scalars().all()
    }
    for name, expected in EXPECTED_INPUT_WINDOWS.items():
        assert rows[name].max_input_tokens == expected, name
        assert rows[name].capability_provenance is LLMCapabilityProvenanceEnum.imported


async def test_no_active_model_is_past_its_deprecation_date(db_session) -> None:
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    stale = [
        m.model_name
        for m in (await db_session.execute(select(LLMModel).where(LLMModel.is_active)))
        .scalars()
        .all()
        if m.deprecation_date is not None and m.deprecation_date < today
    ]
    assert stale == [], f"deprecated models still active: {stale}"


async def test_no_deactivated_model_is_still_referenced(db_session) -> None:
    """Deactivating a referenced model would fall back to CONSERVATIVE_DEFAULT.

    That profile declares ``is_reasoning_model=False``, so the adapter would
    send sampling parameters to a reasoning model and the provider would answer
    400.
    """
    from src.domains.llm_config.models import LLMConfigOverride

    inactive = {
        m.model_name
        for m in (await db_session.execute(select(LLMModel).where(~LLMModel.is_active)))
        .scalars()
        .all()
    }
    referenced = {
        o.model
        for o in (await db_session.execute(select(LLMConfigOverride))).scalars().all()
        if o.model
    }
    assert not (inactive & referenced), inactive & referenced
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/integration/test_catalogue_initial_correction.py -v`
Expected: FAIL on `test_corrected_context_windows` — `gpt-5.2` is still 8192.

- [ ] **Step 3: Write the migration**

Create `apps/api/alembic/versions/2026_08_24_0930-b1c2d3e4f5a6_llm_catalogue_initial_correction.py`:

```python
"""Apply the audited catalogue correction (ADR-244, Lot 0a).

Three operations, all derived from ``task llm:catalogue:sync`` and reviewed
before this migration was written:

1. capability fields of ``provenance='declared'`` rows are replaced by the
   registry values and the row becomes ``imported``;
2. ``deprecation_date`` is filled from the snapshot;
3. a model past its deprecation date is deactivated ONLY when nothing
   references it — no ``llm_config_overrides`` row, no code default, no seed
   row. A referenced one stays active and is reported instead: deactivating it
   would drop it out of ``ModelCapabilitiesCache`` and fall back to
   ``CONSERVATIVE_DEFAULT``, whose ``is_reasoning_model=False`` makes the
   adapter send sampling parameters to a reasoning model.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-08-24 09:30:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _facts_for(provider: str, model: str):  # type: ignore[no-untyped-def]
    from src.infrastructure.llm.catalogue.field_mapping import registry_facts

    return registry_facts(provider, model)


def upgrade() -> None:
    """Correct declared rows, stamp deprecation dates, deactivate the unreferenced."""
    bind = op.get_bind()
    today = datetime.now(UTC).date()

    rows = bind.execute(
        sa.text(
            "SELECT id, provider, model_name, capability_provenance FROM llm_models "
            "WHERE is_active"
        )
    ).fetchall()
    referenced = {
        r[0]
        for r in bind.execute(
            sa.text("SELECT DISTINCT model FROM llm_config_overrides WHERE model IS NOT NULL")
        ).fetchall()
    }

    corrected = deactivated = skipped = 0
    for row_id, provider, model_name, provenance in rows:
        facts = _facts_for(provider, model_name)
        if facts is None:
            continue

        if provenance == "declared":
            updates: dict[str, object] = {}
            for column, attribute in (
                ("max_input_tokens", "max_input_tokens"),
                ("max_output_tokens", "max_output_tokens"),
                ("supports_tools", "supports_tools"),
                ("supports_structured_output", "supports_structured_output"),
                ("supports_vision", "supports_vision"),
            ):
                value = getattr(facts, attribute)
                if value is not None:
                    updates[column] = value
            if updates:
                updates["capability_provenance"] = "imported"
                assignments = ", ".join(f"{k} = :{k}" for k in updates)
                bind.execute(
                    sa.text(f"UPDATE llm_models SET {assignments} WHERE id = :row_id"),
                    {**updates, "row_id": row_id},
                )
                corrected += 1

        if facts.deprecation_date is not None:
            bind.execute(
                sa.text("UPDATE llm_models SET deprecation_date = :d WHERE id = :row_id"),
                {"d": facts.deprecation_date, "row_id": row_id},
            )
            if facts.deprecation_date < today:
                if model_name in referenced:
                    skipped += 1
                else:
                    bind.execute(
                        sa.text("UPDATE llm_models SET is_active = false WHERE id = :row_id"),
                        {"row_id": row_id},
                    )
                    deactivated += 1

    op.execute(
        sa.text(
            "SELECT 1"  # keeps the migration a no-op statement when nothing matched
        )
    )
    print(  # noqa: T201  (migration report, read during deployment)
        f"catalogue correction: corrected={corrected} deactivated={deactivated} "
        f"kept_because_referenced={skipped}"
    )


def downgrade() -> None:
    """Reverse only what is reversible: provenance and activation.

    Capability values are not restored — the pre-migration values were column
    defaults, and re-installing a known-wrong 8192 would be a regression, not a
    rollback.
    """
    op.execute(
        sa.text(
            "UPDATE llm_models SET capability_provenance = 'declared' "
            "WHERE capability_provenance = 'imported'"
        )
    )
    op.execute(
        sa.text("UPDATE llm_models SET is_active = true WHERE deprecation_date IS NOT NULL")
    )
```

- [ ] **Step 4: Apply and read the report**

Run: `task db:migrate`
Expected: a line `catalogue correction: corrected=<n> deactivated=<m> kept_because_referenced=<k>`.
On the dev instance, `k` must be `0` — verified 2026-08-23: none of the 38 explicit slot models points at a deprecated id. **If `k > 0`, stop and retarget those slots before continuing.**

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/integration/test_catalogue_initial_correction.py -v`
Expected: 3 passed.

- [ ] **Step 6: Verify the replay**

Run: `task db:migrate:replay-check`
Expected: success.

- [ ] **Step 7: Commit**

```bash
git add apps/api/alembic/versions/2026_08_24_0930-b1c2d3e4f5a6_llm_catalogue_initial_correction.py apps/api/tests/integration/test_catalogue_initial_correction.py
git commit -m "fix(llm): apply the audited catalogue correction (ADR-244)"
```

---

### Task 7: Provenance-arbitrated context window

**Files:**
- Modify: `apps/api/src/core/llm_config_helper.py:247-279` (`get_effective_context_window`)
- Modify: `apps/api/src/infrastructure/llm/model_profiles.py` (add `capability_provenance` to `ModelProfile`)
- Modify: `apps/api/src/infrastructure/llm/model_capabilities_cache.py` (`_row_to_profile`)
- Test: `apps/api/tests/unit/domains/llm_config/test_effective_context_window.py`

**Interfaces:**
- Consumes: `LLMCapabilityProvenanceEnum` from Task 4.
- Produces: `ModelProfile.capability_provenance: str` (default `"declared"`).

**Why:** the hand-maintained `MODEL_CONTEXT_WINDOWS` table is itself wrong on 10 of its 56 entries (`gpt-5.2` declared 1 047 576 against a real 272 000; `claude-opus-4-6` declared 200 000 against 1 000 000). Neither internal source is authoritative — the **provenance** decides.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/domains/llm_config/test_effective_context_window.py`:

```python
"""Provenance arbitrates between the catalogue and the hand-maintained table."""

from __future__ import annotations

import pytest

from src.core.llm_config_helper import get_effective_context_window
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile


@pytest.fixture(autouse=True)
def _restore_cache():
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


def _install(model: str, window: int, provenance: str) -> None:
    ModelCapabilitiesCache._cache[model] = ModelProfile(
        max_input_tokens=window,
        model_id=model,
        capability_provenance=provenance,
    )


def test_imported_row_wins_over_the_table() -> None:
    _install("gpt-5.2", 272_000, "imported")
    assert get_effective_context_window("gpt-5.2") == 272_000


def test_verified_row_wins_over_the_table() -> None:
    _install("gpt-5.2", 300_000, "verified")
    assert get_effective_context_window("gpt-5.2") == 300_000


def test_declared_row_falls_back_to_the_table() -> None:
    """A column default must never beat a hand-maintained value."""
    _install("gpt-5.2", 8_192, "declared")
    assert get_effective_context_window("gpt-5.2") == 1_047_576


def test_unknown_model_uses_the_table() -> None:
    ModelCapabilitiesCache._cache.pop("claude-opus-4-6", None)
    assert get_effective_context_window("claude-opus-4-6") == 200_000
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_effective_context_window.py -v`
Expected: FAIL — `ModelProfile` has no `capability_provenance` field.

- [ ] **Step 3: Add the field to the profile**

In `apps/api/src/infrastructure/llm/model_profiles.py`, in `ModelProfile`, after `kind`, add:

```python
    #: Which authority filled the capability fields — ``declared`` means the
    #: column defaults nobody curated, and must not beat MODEL_CONTEXT_WINDOWS.
    capability_provenance: str = "declared"
```

In `apps/api/src/infrastructure/llm/model_capabilities_cache.py`, inside `_row_to_profile`, add to the constructed `ModelProfile`:

```python
            capability_provenance=row.capability_provenance.value,
```

- [ ] **Step 4: Arbitrate in the helper**

In `apps/api/src/core/llm_config_helper.py`, replace the body of `get_effective_context_window` after the cache lookups with:

```python
    if caps is not None and caps.max_input_tokens > 0 and caps.capability_provenance != "declared":
        return caps.max_input_tokens

    return get_model_context_window(model)
```

And replace the docstring's authority paragraph with:

```
    Neither internal source is authoritative on its own. The catalogue carried
    column defaults on 89 of 114 rows (``gpt-5.2`` at 8 192 against a real
    272 000), and ``MODEL_CONTEXT_WINDOWS`` is wrong on 10 of its 56 entries
    (``gpt-5.2`` at 1 047 576, ``claude-opus-4-6`` at 200 000 against
    1 000 000). The **provenance** decides: an ``imported`` or ``verified``
    catalogue row wins; a ``declared`` one falls back to the table.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_effective_context_window.py -v`
Expected: 4 passed.

- [ ] **Step 6: Verify the real value at runtime**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
import asyncio
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.core.llm_config_helper import get_effective_context_window
async def main():
    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)
    for m in ('gpt-5.2','claude-opus-4-6','deepseek-v4-flash','gpt-5.6-luna'):
        print(m, get_effective_context_window(m))
asyncio.run(main())"
```
Expected: `gpt-5.2 272000`, `claude-opus-4-6 1000000`, `deepseek-v4-flash 1000000`, `gpt-5.6-luna 922000`.

- [ ] **Step 7: Report the compaction-threshold movement**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
import asyncio
from src.core.config import settings
from src.core.llm_config_helper import get_effective_context_window, get_llm_config_for_agent
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
async def main():
    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)
        await LLMConfigOverrideCache.load_from_db(db)
    m = get_llm_config_for_agent(settings, 'response').model
    w = get_effective_context_window(m)
    print(f'response model={m} window={w} threshold={int(w*settings.compaction_threshold_ratio)}')
asyncio.run(main())"
```
Expected on the seeded configuration: `response model=deepseek-v4-flash window=1000000 threshold=400000` — **unchanged**, because the seed pins a correctly curated model. Record the output in the commit body.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/core/llm_config_helper.py apps/api/src/infrastructure/llm/model_profiles.py apps/api/src/infrastructure/llm/model_capabilities_cache.py apps/api/tests/unit/domains/llm_config/test_effective_context_window.py
git commit -m "fix(llm): let provenance arbitrate the effective context window (ADR-244)"
```

---

### Task 8: The three CI guards

**Files:**
- Create: `apps/api/tests/unit/test_model_capability_provenance_guard.py`
- Create: `apps/api/tests/unit/test_no_deprecated_model_referenced_guard.py`
- Create: `apps/api/tests/unit/infrastructure/llm/catalogue/test_snapshot_freshness.py`

**Interfaces:**
- Consumes: `registry_facts`, `snapshot_generated_at`, `LLM_DEFAULTS`.
- Produces: `ALLOWED_DECLARED_MODELS: frozenset[str]` — a **shrink-only** allowlist.

- [ ] **Step 1: Write the provenance guard**

Create `apps/api/tests/unit/test_model_capability_provenance_guard.py`:

```python
"""Systemic guard: no configured slot may point at an uncurated model row.

A ``declared`` provenance means the row still carries the column defaults
(``max_input_tokens=8192``). Measured 2026-08-23: 89 of 114 active rows were in
that state, which is why ``get_effective_context_window`` answered 8 192 for
``gpt-5.2`` against a real 272 000 — and why the compaction threshold on such a
model collapses by a factor of 33.

``ALLOWED_DECLARED_MODELS`` is **shrink-only**: entries come out as rows are
curated, and none may be added. A model absent from both public registries
belongs here with its reason, not in the catalogue unmarked.
"""

from __future__ import annotations

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue.field_mapping import registry_facts

#: Models neither registry knows — local runtimes and voice vendors.
#: Shrink-only. Each entry names why no registry can curate it.
ALLOWED_DECLARED_MODELS: frozenset[str] = frozenset(
    {
        "edge-tts",  # Microsoft Edge TTS bridge — no public registry entry
        "scribe_v2",  # ElevenLabs STT — audio-hour pricing, absent from both
        "gpt-image-1",  # image generation — per-image pricing, not a chat model
        "gpt-image-2",  # idem
    }
)


def test_every_default_model_is_registry_known_or_allowlisted() -> None:
    unknown = sorted(
        {
            config.model
            for config in LLM_DEFAULTS.values()
            if config.model
            and config.model not in ALLOWED_DECLARED_MODELS
            and registry_facts(config.provider, config.model) is None
        }
    )
    assert unknown == [], (
        "these LLM_DEFAULTS models are unknown to both registries and not "
        f"allowlisted: {unknown}"
    )


def test_allowlist_is_shrink_only() -> None:
    """A self-check: the allowlist must not grow past its audited size."""
    assert len(ALLOWED_DECLARED_MODELS) <= 4, (
        "ALLOWED_DECLARED_MODELS is shrink-only — curate the row instead of "
        "adding an entry"
    )
```

- [ ] **Step 2: Write the deprecation guard**

Create `apps/api/tests/unit/test_no_deprecated_model_referenced_guard.py`:

```python
"""Systemic guard: no code default may point at a retired model.

Measured 2026-08-23: 17 active catalogue rows were already past their
deprecation date, and two constants were two months from theirs
(``SUMMARIZATION_MODEL_DEFAULT = gpt-4.1-nano`` and
``LLM_DEFAULTS["image_generation"] = gpt-image-1``, both 2026-10-23). This
guard turns that class of outage into a build failure with months of notice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.constants import FALLBACK_MODELS_DEFAULT, SUMMARIZATION_MODEL_DEFAULT
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue.field_mapping import registry_facts

#: How much warning the build gives before a model retires.
NOTICE = timedelta(days=30)


def _deprecation(provider: str, model: str):  # type: ignore[no-untyped-def]
    facts = registry_facts(provider, model)
    return facts.deprecation_date if facts else None


def test_no_llm_default_is_deprecated() -> None:
    horizon = (datetime.now(UTC) + NOTICE).date()
    offenders = sorted(
        f"{slot}:{config.model}"
        for slot, config in LLM_DEFAULTS.items()
        if config.model and (d := _deprecation(config.provider, config.model)) and d <= horizon
    )
    assert offenders == [], f"LLM_DEFAULTS point at retiring models: {offenders}"


def test_summarization_default_is_not_deprecated() -> None:
    horizon = (datetime.now(UTC) + NOTICE).date()
    deprecation = _deprecation("openai", SUMMARIZATION_MODEL_DEFAULT)
    assert deprecation is None or deprecation > horizon, (
        f"SUMMARIZATION_MODEL_DEFAULT={SUMMARIZATION_MODEL_DEFAULT} retires {deprecation}"
    )


def test_fallback_models_are_not_deprecated() -> None:
    horizon = (datetime.now(UTC) + NOTICE).date()
    for name in (m.strip() for m in FALLBACK_MODELS_DEFAULT.split(",") if m.strip()):
        for provider in ("anthropic", "openai", "deepseek", "gemini"):
            facts = registry_facts(provider, name)
            if facts is None:
                continue
            assert facts.deprecation_date is None or facts.deprecation_date > horizon, (
                f"FALLBACK_MODELS_DEFAULT entry {name} retires {facts.deprecation_date}"
            )
            break
        else:
            raise AssertionError(
                f"FALLBACK_MODELS_DEFAULT entry {name!r} is unknown to every registry"
            )
```

- [ ] **Step 3: Write the freshness guard**

Create `apps/api/tests/unit/infrastructure/llm/catalogue/test_snapshot_freshness.py`:

```python
"""The vendored snapshot ages; a stale one warns, it never reds the build.

An old snapshot is a maintenance signal, not a defect: the design forbids any
network access on an execution path, so a build must stay green offline.
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

from src.infrastructure.llm.catalogue.snapshot_loader import snapshot_generated_at

MAX_AGE = timedelta(days=120)


def test_snapshot_age_is_reported() -> None:
    age = datetime.now(UTC) - snapshot_generated_at()
    if age > MAX_AGE:
        warnings.warn(
            f"the vendored catalogue snapshot is {age.days} days old — "
            "run `task llm:catalogue:fetch` and review the diff",
            stacklevel=1,
        )
    assert age.days >= 0, "the snapshot claims to come from the future"
```

- [ ] **Step 4: Run the guards to verify they fail where they should**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_no_deprecated_model_referenced_guard.py -v`
Expected: FAIL on `test_summarization_default_is_not_deprecated` (`gpt-4.1-nano` retires 2026-10-23), on `test_no_llm_default_is_deprecated` (`image_generation` → `gpt-image-1`), and on `test_fallback_models_are_not_deprecated` (`claude-sonnet-4-5` is unknown to every registry). **These failures are the point of Task 9.**

- [ ] **Step 5: Commit the guards**

```bash
git add apps/api/tests/unit/test_model_capability_provenance_guard.py apps/api/tests/unit/test_no_deprecated_model_referenced_guard.py apps/api/tests/unit/infrastructure/llm/catalogue/test_snapshot_freshness.py
git commit -m "test(llm): guards for capability provenance and model deprecation (ADR-244)"
```

---

### Task 9: Retarget the three time bombs

**Files:**
- Modify: `apps/api/src/core/constants.py:2506` (`SUMMARIZATION_MODEL_DEFAULT`)
- Modify: `apps/api/src/core/constants.py:2509` (`FALLBACK_MODELS_DEFAULT`)
- Modify: `apps/api/src/domains/llm_config/constants.py` (`LLM_DEFAULTS["image_generation"]`)
- Modify: `.env.example:504`, `.env.prod.example` (if it carries `FALLBACK_MODELS`)
- Test: the Task 8 guards must go green.

**Interfaces:** none — constants only.

**Why:** all three point at models that are retired or absent. `FALLBACK_MODELS_DEFAULT = "claude-sonnet-4-5,deepseek-chat"` names one model absent from the catalogue entirely and one that is deactivated; `SUMMARIZATION_MODEL_DEFAULT` and the image default retire 2026-10-23.

- [ ] **Step 1: Confirm the replacements against the catalogue**

Run:
```bash
docker exec lia-postgres-dev psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select model_name, provider, is_active, deprecation_date
from llm_models
where model_name in ('gpt-5.6-luna','claude-sonnet-4-6','deepseek-v4-flash','gpt-image-2');"
```
Expected: all four active, none with a past `deprecation_date`. **If any is not, pick another and record why in the commit body.**

- [ ] **Step 2: Retarget the summarization default**

In `apps/api/src/core/constants.py`, replace:

```python
SUMMARIZATION_MODEL_DEFAULT = "gpt-4.1-nano"
```

with:

```python
# gpt-4.1-nano retires 2026-10-23 (registry snapshot). gpt-5.6-luna is the
# cheapest active OpenAI chat model in the catalogue and carries a 922k window.
SUMMARIZATION_MODEL_DEFAULT = "gpt-5.6-luna"
```

- [ ] **Step 3: Retarget the failover chain**

In `apps/api/src/core/constants.py`, replace:

```python
FALLBACK_MODELS_DEFAULT = (
    "claude-sonnet-4-5,deepseek-chat"  # Aligned from .env.prod (was claude-sonnet-4-5)
)
```

with:

```python
# Both previous entries were dead: claude-sonnet-4-5 is absent from the
# catalogue entirely and deepseek-chat is deactivated, so the failover chain
# had no reachable target. Verified against the catalogue 2026-08-24.
FALLBACK_MODELS_DEFAULT = "claude-sonnet-4-6,deepseek-v4-flash"
```

- [ ] **Step 4: Retarget the image default**

In `apps/api/src/domains/llm_config/constants.py`, in `LLM_DEFAULTS["image_generation"]`, change `model="gpt-image-1"` to `model="gpt-image-2"` and add above the entry:

```python
    # gpt-image-1 retires 2026-10-23; the reference seed already pins gpt-image-2.
```

- [ ] **Step 5: Align the environment samples**

In `.env.example`, replace the `FALLBACK_MODELS=` line with:

```
FALLBACK_MODELS=claude-sonnet-4-6,deepseek-v4-flash        # Comma-separated fallback model chain
```

Apply the same replacement in `.env.prod.example` if the key is present there.

- [ ] **Step 6: Run the guards to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_no_deprecated_model_referenced_guard.py tests/unit/test_model_capability_provenance_guard.py -v`
Expected: all passed.

- [ ] **Step 7: Run the whole fast unit suite**

Run: `task test:backend:unit:fast`
Expected: green. If `tests/unit/domains/llm_config/test_llm_defaults_compliance.py` fails on the image default, update its expectation to `gpt-image-2` in the same commit.

- [ ] **Step 8: Run the full static gate**

Run: `task lint`
Expected: green, including `lint:hygiene` (`.env.example` parity).

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/core/constants.py apps/api/src/domains/llm_config/constants.py .env.example
git commit -m "fix(llm): retarget summarization, failover and image defaults off retired models (ADR-244)"
```

---

### Task 10: Lot acceptance

**Files:** none — verification only.

- [ ] **Step 1: Run every gate that needs no service**

Run: `task ci:fast`
Expected: green.

- [ ] **Step 2: Verify the runtime truth**

Run:
```bash
docker exec -e PYTHONPATH=/app -w /app lia-api-dev python -c "
import asyncio
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.core.llm_config_helper import get_effective_context_window
async def main():
    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)
    for m in ('gpt-5.2','claude-opus-4-6','gpt-5.4-mini','qwen3.5-plus','gpt-5.6-luna'):
        print(f'{m:20s} {get_effective_context_window(m):>9,d}')
asyncio.run(main())"
```
Expected: `272 000`, `1 000 000`, `272 000`, `991 808`, `922 000` — none of them 8 192.

- [ ] **Step 3: Verify a guard actually reds on a reverted fix**

Temporarily set `SUMMARIZATION_MODEL_DEFAULT` back to `"gpt-4.1-nano"`, run
`cd apps/api && .venv/Scripts/pytest tests/unit/test_no_deprecated_model_referenced_guard.py -v`,
confirm it FAILS, then restore the value. A guard that cannot fail is decoration.

- [ ] **Step 4: Count what the correction touched**

Run: `task llm:catalogue:sync`
Expected: the `AUTO` block is now empty or near-empty (the rows were corrected); the `REVIEW` block lists only rows a human curated.

- [ ] **Step 5: Commit the acceptance record**

```bash
git commit --allow-empty -m "chore(llm): Lot 0a acceptance — catalogue tells the truth (ADR-244)

task ci:fast green.
get_effective_context_window: gpt-5.2 272000, claude-opus-4-6 1000000,
gpt-5.4-mini 272000, qwen3.5-plus 991808, gpt-5.6-luna 922000.
Deprecation guard verified red on a reverted fix."
```

---

## Self-Review

**Spec coverage.** §5.1 mechanism ① (initial correction) → Tasks 1–6. Canonical-provider lock → Task 2. Per-field precedence and the three exclusions → Task 3, with the exclusions asserted as tests. Provenance column → Task 4. Reviewable diff → Task 5. Deactivation rule and its safety check → Task 6. Context-window fix → Task 7. The three guards of §5.1 → Task 8. Constant retargeting → Task 9.

**Deliberately out of this plan** (each has its own lot in the spec): mechanism ② the continuous scheduled sync and its class A/B/C queue (Lot 3), mechanism ③ the create/edit assist (Lot 2), the capability gate and the `llm_type` / `latency_ms` / `status` / `failure_kind` columns (Lot 0b), the failover boot assert and dead-slot removal (Lot 0b), the reasoning unification (Lot 0c, ADR-245), the execution profiles (Lot 1).

**Placeholder scan.** No TBD, no "handle errors appropriately", no "similar to Task N". Every code step carries the code.

**Type consistency.** `RegistryFacts` field names (Task 3) match the attribute names used in `COMPARED_FIELDS` (Task 5) and in the migration's mapping tuple (Task 6). `registry_facts(provider, model)` keeps the same signature in Tasks 5, 6, 8 and 9. `capability_provenance` is a `str` on `ModelProfile` (Task 7) and an enum on `LLMModel` (Task 4) — the cache converts with `.value` in Task 7 Step 3.
