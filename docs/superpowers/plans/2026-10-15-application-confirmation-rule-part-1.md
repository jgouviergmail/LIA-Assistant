# One confirmation rule per application operation — implementation plan, part 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reminder creation, modification and deletion, the routine switch and the three ticket acts direct again, through one declaration per application operation read by one door, and switch the ADR-336 requested-outcome check off by default.

**Architecture:** `ApplicationOperationSpec` carries a `Confirmation` (`ASK`, or `DIRECT` with an optional `ask_when` over the prepared intent). An `ASK` operation keeps the effect gate's path unchanged; a `DIRECT` one is handed by the gate to its door (`application/action_door.py`), which re-checks authority, serves a recorded replay, prepares, decides, and either builds the card or claims → executes → closes the act through the gate's own primitives (`effects/application_effects.py`). The ADR-336 check gets an operator switch read where its verdicts are formed.

**Tech Stack:** Python 3.14, FastAPI, LangGraph 1.x, Pydantic 2, SQLAlchemy 2 (async), pytest (`asyncio_mode = "auto"`), Next.js locales (JSON), Task.

**Spec:** [docs/superpowers/specs/2026-10-15-application-confirmation-rule-design.md](../specs/2026-10-15-application-confirmation-rule-design.md) — this part implements its lots A, 0, 1 and 2; part 2 (lots 3 to 6 and the closing) is written once lot 0's door has shipped (spec §6.1).

## Global Constraints

- **No git action of any kind** (no `git add`, `commit`, `checkout`, `stash`): the owner handles git. Work in the `main` working tree, uncommitted. Several files below already carry other sessions' uncommitted changes: read each file before editing it and change nothing else in it.
- Every step that says "Run" runs on the host from `apps/api` with `.venv/Scripts/pytest` (or the named `task`); runtime proofs run in the `lia-api-dev` container. No paid model call anywhere in this plan; never an Anthropic API call.
- Python: Black (line length 100), Ruff (E, W, F, I, B, C4, UP), MyPy strict — complete type hints, no new `Any`, no `cast`, no `# type: ignore`. Google-style docstrings, module docstrings, comments in English.
- No function of cyclomatic complexity ≥ 15; no file above 600 logical SLOC (`scripts/audit/measure_sloc.py`); `apps/api/src/domains/agents/effects/runtime.py` is at 555 today and must stay under 600.
- Messages the model reads are technical English (ADR-256, ADR-323); a sentence a person reads goes through the existing i18n tables, in the six languages (`fr`, `en`, `es`, `de`, `it`, `zh-CN` backend; `fr`, `en`, `es`, `de`, `it`, `zh` web), French register « tu ».
- Never a hardcoded timezone literal (`DEFAULT_USER_DISPLAY_TIMEZONE`), never `datetime.now()` without `UTC`.
- A characterized behavior (draft type and content, `source_tool`, persisted command, origin binding, every refusal's code, message and metadata) does not change during a migration step; it changes only in a step titled « Flip », and every test whose expectation changes there is listed in that step.
- Every lot ends with its gates and an exhaustive cold review of every file it touched (each line read again; findings fixed before the next lot).

## Review Focus

1. **A replayed direct act after an interrupt** (a ReAct iteration where `cancel_reminder_tool` and a draft tool were called together, then resumed): the deletion must be served from the register, never answered « not found » — pinned in Task 0.5 (`test_a_replayed_act_is_served_before_anything_is_prepared`, the gate's hand-off) and on PostgreSQL in Task 1.6 (`test_a_replayed_deletion_is_served_from_its_record_not_reprepared`).
2. **« Remind me in one minute » written as `HH:MM` that lands seconds in the past**: created and fired at the next sweep, never refused — pinned in Task 1.4 (`test_an_instant_within_the_grace_is_accepted`) and on PostgreSQL in Task 1.6 (`test_an_instant_seconds_behind_is_created_not_refused`).
3. **An unattended run (a routine) asking a ticket update with `run_now`**: refused with the gate's own verdict, no card and no command written — pinned in Task 0.5 (`test_an_ask_when_card_nobody_can_answer_is_refused_before_anything_is_written`) and on PostgreSQL in Task 2.4 (`test_in_a_routine_a_requested_run_is_refused_and_nothing_is_written`).
4. **A preference change through the door with a withdrawn capability** (operator switches `APPLICATION_TOOLS` off between two turns, then a replay arrives): refused, never served from the old record — pinned in Task 0.3 (`test_a_replay_never_bypasses_a_withdrawn_capability`).
5. **The same act reached through an alias and through its own tool**: the same register label, the same result shape — pinned in Task 1.5 (`test_one_act_one_label_whichever_tool`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `apps/api/src/core/constants.py` | `REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT`, `REMINDER_PAST_INSTANT_GRACE_SECONDS` | A1, 1.4 |
| `apps/api/src/core/config/agents.py` | `requested_outcomes_check_enabled` setting | A1 |
| `apps/api/src/domains/agents/analysis/requested_outcomes.py` | `requested_outcomes_check_enabled()`, the switch's one reader, with the TODO | A1 |
| `apps/api/src/domains/agents/services/outcome_directive.py` | the response directive honours the switch | A1 |
| `apps/api/src/domains/agents/nodes/react_observed_gaps.py` | the ReAct requirements honour the switch | A1 |
| `apps/api/src/domains/agents/application/operation_spec.py` | `ConfirmationRule`, `AskWhen`, `Confirmation`, spec fields, alias index | 0.1 |
| `apps/api/src/domains/agents/application/confirmation_policy.py` | the decision function, the field rules, authority for a direct act | 0.2, 0.5 |
| `apps/api/src/domains/agents/effects/repository.py` | `find_by_key` | 0.3 |
| `apps/api/src/domains/agents/effects/runtime.py` | `_Ledger.find`, `_build_request(label=)`, `_run_claimed`, the hand-off | 0.3, 0.5 |
| `apps/api/src/domains/agents/effects/application_effects.py` (new) | the register as a door uses it | 0.3 |
| `apps/api/src/domains/agents/effects/labels.py` | `APPLICATION_LABELS`, `operation_label`, completeness by operation | 0.4 |
| `apps/api/src/domains/agents/application/refusals.py` (new) | `Refusal`, `refused`, `Refusals`, the door's tables | 0.5 |
| `apps/api/src/domains/agents/application/direct_execution.py` (renamed from `reversible_execution.py`) | `execute_direct_action`, neutral output | 0.5 |
| `apps/api/src/domains/agents/application/action_door.py` (new) | `application_action`, the door | 0.5 |
| `apps/api/src/domains/agents/application/native_tool_preparation.py` | `prepare_native_tool`, now a thin call to the door | 0.5 |
| `apps/api/src/domains/agents/application/draft_execution.py` | `APPLICATION_EXECUTORS` at module level | 0.6 |
| `apps/api/src/domains/agents/application/preference_dispatch.py` | `has_preference_executor` | 0.6 |
| `apps/api/tests/unit/domains/agents/application/test_application_door_guard.py` (new) | AST guard + shrink-only list | 0.7 |
| `apps/api/src/domains/agents/tools/application_reminder_tools.py`, `reminder_tools.py`, `application_routine_tools.py`, `automation_tools.py` | lot 1 migrations and aliases | 1.2, 1.3 |
| `apps/api/src/domains/agents/application/reminder_creation.py`, `reminder_update.py`, `result_projection.py` | grace rule, projections | 1.4 |
| `apps/api/src/domains/agents/tools/workboard_creation_tool.py` | lot 2 migration | 2.2 |
| `docs/architecture/ADR-347-…md` (new) and amendments | documentation | A2, 3.2 |

---

## Lot A — the ADR-336 switch

### Task A1: The requested-outcome check reads one switch, off by default

**Files:**
- Modify: `apps/api/src/core/constants.py` (after `REACT_RECOVERY_PASSES_MAX_DEFAULT`, line ~6408)
- Modify: `apps/api/src/core/config/agents.py` (import block line ~289; field after `react_recovery_passes_max`, line ~992)
- Modify: `apps/api/src/domains/agents/analysis/requested_outcomes.py`
- Modify: `apps/api/src/domains/agents/services/outcome_directive.py:7,42-46`
- Modify: `apps/api/src/domains/agents/nodes/react_observed_gaps.py:7-11,21-23`
- Modify: `apps/api/tests/unit/domains/agents/nodes/test_react_checkpointed_execution.py` (one autouse fixture)
- Modify: `apps/api/tests/unit/domains/agents/nodes/test_react_delegation_policy.py` (import that fixture)
- Test: `apps/api/tests/unit/domains/agents/semantic/test_requested_outcomes_check_switch.py` (new)

**Interfaces:**
- Produces: `requested_outcomes_check_enabled() -> bool` in `src.domains.agents.analysis.requested_outcomes`; setting `settings.requested_outcomes_check_enabled: bool` (default `False`).

- [ ] **Step 1: Write the failing test**

```python
"""The requested-outcome check has an operator switch, off by default (ADR-336 amendment 2026-10-15)."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.requested_outcomes import GoalRequirement
from src.domains.agents.nodes.react_observed_gaps import (
    observed_gaps,
    proven_final_content,
    requested_final_report,
    requested_outcome_block,
    requested_requirements,
)
from src.domains.agents.services.outcome_directive import build_requested_outcomes_block
from src.domains.agents.services.planner.human_message import build_planner_human_message

pytestmark = pytest.mark.unit

_QUERY = "What reminders do I have"
_GOAL = GoalRequirement(domain="reminder", label="pending reminders", source_quote=_QUERY)


def _state() -> dict[str, Any]:
    """A checkpointed turn whose analyzer kept one requirement and whose tools observed nothing."""
    return {
        "query_intelligence": {
            "original_query": _QUERY,
            "domains": ["reminder"],
            "requested_outcomes": [_GOAL.model_dump(mode="json")],
        },
        "user_timezone": DEFAULT_USER_DISPLAY_TIMEZONE,
        "requested_outcome_evidence": [],
    }


def test_the_switch_ships_off() -> None:
    from src.core.constants import REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT

    assert REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT is False
    assert type(settings).model_fields["requested_outcomes_check_enabled"].default is False


def test_on_the_verdicts_reach_the_directive_and_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "requested_outcomes_check_enabled", True)
    state = _state()
    assert requested_requirements(state) == (_GOAL,)
    assert build_requested_outcomes_block(state)
    assert requested_outcome_block(state)
    assert requested_final_report(state)
    assert proven_final_content(state, "answer") == ""
    assert observed_gaps(state) == ("pending reminders: missing",)


def test_off_a_checkpointed_requirement_is_judged_by_nobody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "requested_outcomes_check_enabled", False)
    state = _state()
    assert requested_requirements(state) == ()
    assert build_requested_outcomes_block(state) == ""
    assert requested_outcome_block(state) is None
    assert requested_final_report(state) == {}
    assert proven_final_content(state, "answer") == "answer"
    assert observed_gaps(state) == ()


def test_off_a_failed_read_still_buys_its_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-310's recovery of a failed read does not depend on ADR-336."""
    monkeypatch.setattr(settings, "requested_outcomes_check_enabled", False)
    state = {
        **_state(),
        "react_read_observations": {
            "abc123def456": {"tool_name": "get_lia_reminders_tool", "outcome": "failed"}
        },
    }
    assert observed_gaps(state) == (
        "get_lia_reminders_tool: started read returned failed (observation abc123def456)",
    )


def test_off_the_planner_still_receives_the_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "requested_outcomes_check_enabled", False)
    intelligence = QueryIntelligence(
        original_query=_QUERY,
        english_query=_QUERY,
        immediate_intent="read",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="the user lists their reminders",
        requested_outcomes=(_GOAL,),
    )
    assert "Explicit requested results" in build_planner_human_message(intelligence)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/semantic/test_requested_outcomes_check_switch.py -v`
Expected: FAIL — `ImportError: cannot import name 'REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT'` and `KeyError: 'requested_outcomes_check_enabled'`.

- [ ] **Step 3: Add the default and the setting**

In `apps/api/src/core/constants.py`, directly after `REACT_RECOVERY_PASSES_MAX_DEFAULT: int = 1`:

```python
# ADR-336 amendment (2026-10-15): the requested-outcome CHECK — the verdicts the
# response directive and the ReAct recovery read — ships OFF until its own
# programme repairs the false negatives measured that day (the TODO at
# ``analysis.requested_outcomes.requested_outcomes_check_enabled`` lists them).
# The extraction is not switched: the planner still reads the requirements.
REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT: bool = False
```

In `apps/api/src/core/config/agents.py`, add `REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT,` to the `from src.core.constants import (...)` block (alphabetical place, next to `REACT_RECOVERY_PASSES_MAX_DEFAULT`), then after the `react_recovery_passes_max` field:

```python
    # TODO(ADR-336): back to True once the dedicated programme repairs the
    # false negatives listed at ``requested_outcomes_check_enabled``.
    requested_outcomes_check_enabled: bool = Field(
        default=REQUESTED_OUTCOMES_CHECK_ENABLED_DEFAULT,
        description=(
            "Whether the requested-outcome check of ADR-336 judges a turn: the response "
            "directive and the ReAct gaps, recovery trigger and final report read its "
            "verdicts. Off by default until its own programme repairs the false negatives "
            "measured on 2026-10-15; the planner still receives the requirements as a hint."
        ),
    )
```

- [ ] **Step 4: Add the one reader, with the TODO**

In `apps/api/src/domains/agents/analysis/requested_outcomes.py`, add `from src.core.config import settings` to the imports (after `from src.core.date_quotes import date_from_quote`), and append at the end of the module:

```python
# TODO(ADR-336): switch the check back on (REQUESTED_OUTCOMES_CHECK_ENABLED) once
# its dedicated programme repairs what was measured on 2026-10-15 — 232 analyses
# and 24 real English turns, no Anthropic slot:
# - with the semantic pivot on, a non-English request keeps no requirement: the
#   analyzer quotes the English pivot, and the second anchoring compares that
#   quote with the ORIGINAL message (query_analyzer_service.py);
# - the field paths an action is checked on are never published to the
#   analyzer, which invents them (title, reminder_text, instruction…), so an
#   action reads « unknown »;
# - an application result nests its values under application_result.values,
#   where the check never looks: every direct settings change reads « unknown »;
# - a model invents counts (min_count) that the anchoring then refuses;
# - a literal value is compared with exact, case-sensitive equality
#   (« chanter » against « Chanter » reads « missing »);
# - the directive forbids turning « unknown » into success, and one answer in
#   four then said a change failed that the register shows succeeded.
def requested_outcomes_check_enabled() -> bool:
    """Whether the requested-outcome check judges a turn (ADR-336 amendment 2026-10-15).

    The ONE reader of the switch, called where a verdict is formed: the response
    directive (``outcome_directive.build_requested_outcomes_block``) and the ReAct
    requirements (``react_observed_gaps.requested_requirements``, which feeds the
    evidence collection, the gaps, the recovery trigger and the final report).
    Off, a turn behaves as one whose analyzer extracted nothing — the measured
    state of every non-English turn — including on a checkpoint written while it
    was on. The extraction is not switched: the planner still reads the
    requirements as a hint (``planner/human_message.py``).

    Returns:
        True when the check runs.
    """
    return settings.requested_outcomes_check_enabled
```

- [ ] **Step 5: Read the switch where the verdicts are formed**

`apps/api/src/domains/agents/services/outcome_directive.py` — replace the import line 7 and the head of `build_requested_outcomes_block`:

```python
from src.domains.agents.analysis.requested_outcomes import (
    anchored_requirements,
    parse_requirements,
    requested_outcomes_check_enabled,
)
```

```python
def build_requested_outcomes_block(state: Mapping[str, object]) -> str:
    """Never infer successful external execution from a pending draft or prose."""
    if not requested_outcomes_check_enabled():
        return ""
    intelligence = state.get("query_intelligence")
```

`apps/api/src/domains/agents/nodes/react_observed_gaps.py` — extend the import and guard `requested_requirements`:

```python
from src.domains.agents.analysis.requested_outcomes import (
    GoalRequirement,
    anchored_requirements,
    parse_requirements,
    requested_outcomes_check_enabled,
)
```

```python
def requested_requirements(state: MessagesState) -> tuple[GoalRequirement, ...]:
    """Only literal, current-request anchors become obligations — when the check runs."""
    if not requested_outcomes_check_enabled():
        return ()
    requirements = parse_requirements(get_qi_attr(state, "requested_outcomes", default=()))
```

- [ ] **Step 6: Keep the two suites that exercise the check running it**

In `apps/api/tests/unit/domains/agents/nodes/test_react_checkpointed_execution.py`, after the existing fixtures `contracts` and `no_services`, add:

```python
@pytest.fixture(autouse=True)
def requested_outcomes_check_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """These scenarios exercise the ADR-336 check itself, which now ships off."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "requested_outcomes_check_enabled", True)
```

In `apps/api/tests/unit/domains/agents/nodes/test_react_delegation_policy.py`, add `requested_outcomes_check_on,` to the import list from `test_react_checkpointed_execution` and change `_FIXTURES = (contracts, no_services)` to `_FIXTURES = (contracts, no_services, requested_outcomes_check_on)`.

- [ ] **Step 7: Run the new test and every suite that reads the verdicts**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/semantic tests/unit/domains/agents/nodes/test_react_checkpointed_execution.py tests/unit/domains/agents/nodes/test_react_delegation_policy.py tests/unit/domains/agents/nodes/test_react_recovery.py tests/unit/domains/agents/services/test_planner_human_message.py -v`
Expected: all PASS.

### Task A2: The switch in every environment file, and the ADR-336 amendment

**Files:**
- Modify: `.env.example`, `.env.prod.example` (after `REACT_RECOVERY_PASSES_MAX=…`)
- Modify: `.env.demo-instance.example`, `.env.demo-instance.prod.example` (after the `REACT_RECOVERY_PASSES_MAX` block)
- Modify (live, git-ignored): `.env`, `.env.prod`, `.env.demo-instance`, `.env.demo-instance.prod` — same line, value `false`
- Not touched: `.env.min.prod.example` (lists only what boot requires) and the `*.encrypted` copies (re-encrypted by `scripts/deploy/deploy-prod.ps1`)
- Modify: `docs/architecture/ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md` (new amendment before « Implementation references »)

- [ ] **Step 1: Write the line in the two `.env.*.example` files that use inline comments**

After the `REACT_RECOVERY_PASSES_MAX=1 …` line of `.env.example` and of `.env.prod.example`:

```
REQUESTED_OUTCOMES_CHECK_ENABLED=false                      # ADR-336 (amended 2026-10-15): whether the requested-outcome check judges a turn (response directive, ReAct gaps and recovery). Off until its own programme repairs the measured false negatives (non-English requests, nested application results, invented field names); the planner still receives the requirements (default: false)
```

- [ ] **Step 2: Write the block in the two demonstrator templates (comment lines above, their style)**

After the `REACT_RECOVERY_PASSES_MAX=1` line of `.env.demo-instance.example` and `.env.demo-instance.prod.example`:

```
# ADR-336 (amended 2026-10-15): the requested-outcome check judges a turn's answer
# against what the request named; off until its own programme repairs the false
# negatives measured that day. The planner still receives the requirements.
REQUESTED_OUTCOMES_CHECK_ENABLED=false
```

- [ ] **Step 3: Write the same line in the four live files**

Read each of `.env`, `.env.prod`, `.env.demo-instance`, `.env.demo-instance.prod` first (Codex also edits them); insert the line from Step 1 (for `.env`, `.env.prod`) or the block from Step 2 (for the two demonstrator files) right after their own `REACT_RECOVERY_PASSES_MAX=` line, changing nothing else. Then verify: `grep -c "^REQUESTED_OUTCOMES_CHECK_ENABLED=false" .env .env.prod .env.demo-instance .env.demo-instance.prod .env.example .env.prod.example .env.demo-instance.example .env.demo-instance.prod.example` → `1` for each of the eight.

- [ ] **Step 4: Write the ADR-336 amendment**

Insert before `## Implementation references`:

```markdown
## Amendment 2026-10-15 — the check ships switched off

Measured on 2026-10-15 on the dev stack, no Anthropic slot (dev and production
run `claude-haiku-5-5` on the analyzer, which this measurement therefore does
not cover):

- *Analysis stage*, 232 analyses (semantic pivot + analyzer + both anchorings,
  3 models × 24 requests × 3 passes, plus 16 without the pivot; 0.49 USD). With
  the deployed pivot no requirement survives for a non-English request (0 of 117
  reminder analyses; 4 of 27 other acts, a quoted title carried verbatim by the
  translation): the analyzer quotes the English pivot and the second anchoring
  compares that quote with the original message
  (`query_analyzer_service.py`). In English, 31 of 72 analyses keep a checked
  requirement, model-dependent (16/24, 15/24, 0/24 — the third model always
  invents a `min_count` the anchoring refuses). Field names are mostly invented
  (`title`, `reminder_text`, `instruction`).
- *Real English turns*, proof account, 24 turns, 0.09 EUR. Every direct settings
  change drew a requirement judged `unknown` — even `font_size = 18` exact,
  because an application result nests its values under
  `application_result.values` — and one answer in four said the change had
  failed while the register shows it `succeeded`. A read asking for « the next
  2 » of an empty list was judged `missing` and paid a recovery pass for nothing.

**Decision.** An operator switch, `REQUESTED_OUTCOMES_CHECK_ENABLED`, ships
`false` in every environment file. One predicate reads it where a verdict is
formed — `build_requested_outcomes_block` (the response directive) and
`requested_requirements` (the ReAct evidence collection, gaps, recovery trigger
and final report); off, a turn behaves as one whose analyzer extracted nothing,
including on a checkpoint written while it was on. The extraction is not
switched: the planner still reads the requirements as a hint
(`planner/human_message.py`). A failed read keeps its own recovery (ADR-310).
The dedicated programme that follows must repair, before switching it back on:
the anchoring against the original language, the field paths never published to
the analyzer, the nested application values, the invented counts, the
case-sensitive equality, and the `unknown` directive turning into a claimed
failure. Pinned by `test_requested_outcomes_check_switch.py`.
```

- [ ] **Step 5: Run the documentation and hygiene gates**

Run (from repo root): `task lint:hygiene` then `task lint:docs`
Expected: both exit 0 (`check_env_example_completeness` finds `REQUESTED_OUTCOMES_CHECK_ENABLED` documented).
Run: `.venv/Scripts/pytest tests/unit/test_demo_instance_env_template.py -v` (from `apps/api`) → PASS.

- [ ] **Step 6: Cold review of lot A**

Read again, line by line: the seven code and test files of Task A1 and the eight environment files' new lines (compare each live file's line to its template's — never copy a value). Confirm nothing else changed in any of them (`git diff --stat` is a read-only check you may run; it changes nothing).

---

## Lot 0 — the declaration and the door

### Task 0.1: The declaration lives on the spec, aliases resolve to their operation

**Files:**
- Modify: `apps/api/src/domains/agents/application/operation_spec.py`
- Test: `apps/api/tests/unit/domains/agents/application/test_confirmation_declaration.py` (new)

**Interfaces:**
- Produces (in `src.domains.agents.application.operation_spec`): `ConfirmationRule` (`ASK`, `DIRECT`), `AskWhen(name: str, reason: str, test: Callable[[Mapping[str, object]], bool])`, `Confirmation(rule, reason, ask_when)` with property `may_act_directly: bool`, `ALWAYS_ASK`, `direct(reason: str, *, ask_when: AskWhen | None = None) -> Confirmation`; `ApplicationOperationSpec.confirmation: Confirmation = ALWAYS_ASK`, `.aliases: tuple[str, ...] = ()`, `.binds_origin: bool = False`, property `.binds_command_origin: bool`; `OperationRegistry.get_by_tool_name(name)` resolves aliases.

- [ ] **Step 1: Write the failing test**

```python
"""One confirmation declaration per application operation (ADR-347)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import BaseModel

from src.domains.agents.application.operation_spec import (
    ALWAYS_ASK,
    ApplicationOperationSpec,
    AskWhen,
    Confirmation,
    ConfirmationRule,
    OperationKind,
    OperationRegistry,
    direct,
)

pytestmark = pytest.mark.unit

_ASK_ON_RUN = AskWhen(name="run_requested", reason="A run is billed work.", test=lambda _: True)


def _spec(**changes: object) -> ApplicationOperationSpec:
    base = ApplicationOperationSpec(
        operation_id="sample.update",
        tool_name="update_sample_tool",
        sections=("sample",),
        input_model=BaseModel,
        output_model=BaseModel,
        kind=OperationKind.ACTION,
    )
    return replace(base, **changes)


def test_an_operation_asks_unless_it_declares_otherwise() -> None:
    assert _spec().confirmation is ALWAYS_ASK
    assert not ALWAYS_ASK.may_act_directly


def test_acting_directly_requires_a_written_reason() -> None:
    with pytest.raises(ValueError, match="written reason"):
        Confirmation(rule=ConfirmationRule.DIRECT)
    with pytest.raises(ValueError, match="written reason"):
        direct("  ")
    assert direct("Undone by one call.").may_act_directly


def test_only_a_direct_operation_declares_when_it_still_asks() -> None:
    with pytest.raises(ValueError, match="Only a direct operation"):
        Confirmation(ask_when=_ASK_ON_RUN)
    assert direct("Editable.", ask_when=_ASK_ON_RUN).ask_when is _ASK_ON_RUN


def test_an_exception_names_itself_and_states_its_reason() -> None:
    with pytest.raises(ValueError, match="names itself"):
        AskWhen(name="", reason="why", test=lambda _: True)
    with pytest.raises(ValueError, match="names itself"):
        AskWhen(name="run", reason=" ", test=lambda _: True)


@pytest.mark.parametrize(
    "kind", [OperationKind.READ, OperationKind.DEVICE, OperationKind.SECURE_HANDOFF]
)
def test_only_an_action_may_run_without_its_card(kind: OperationKind) -> None:
    with pytest.raises(ValueError, match="Only an action"):
        _spec(kind=kind, confirmation=direct("Anodyne."))


def test_an_administrative_operation_always_asks() -> None:
    with pytest.raises(ValueError, match="administrative"):
        _spec(administrative=True, confirmation=direct("Anodyne."))


@pytest.mark.parametrize("aliases", [("update_sample_tool",), ("legacy_tool", "legacy_tool")])
def test_an_alias_names_another_tool_once(aliases: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="alias"):
        _spec(aliases=aliases)


def test_a_device_operation_binds_its_origin_by_its_kind() -> None:
    with pytest.raises(ValueError, match="by its kind"):
        _spec(kind=OperationKind.DEVICE, binds_origin=True)
    assert _spec(kind=OperationKind.DEVICE).binds_command_origin
    assert _spec(binds_origin=True).binds_command_origin
    assert not _spec().binds_command_origin


def test_an_alias_resolves_to_its_operation_and_never_to_two() -> None:
    registry = OperationRegistry()
    spec = _spec(aliases=("legacy_sample_tool",))
    registry.register(spec)
    assert registry.get_by_tool_name("legacy_sample_tool") is spec
    assert registry.get_by_tool_name("update_sample_tool") is spec
    other = _spec(operation_id="other.update", tool_name="legacy_sample_tool")
    with pytest.raises(ValueError, match="Duplicate application tool"):
        registry.register(other)
    taken_alias = _spec(
        operation_id="third.update", tool_name="third_tool", aliases=("update_sample_tool",)
    )
    with pytest.raises(ValueError, match="Duplicate application tool"):
        registry.register(taken_alias)
    assert registry.all() == (spec,)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_confirmation_declaration.py -v`
Expected: FAIL — `ImportError: cannot import name 'ALWAYS_ASK'`.

- [ ] **Step 3: Implement the declaration**

In `apps/api/src/domains/agents/application/operation_spec.py`: change the imports to

```python
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Literal
```

then, after `class ApplicationEmptyRead`, add:

```python
class ConfirmationRule(StrEnum):
    """Whether an operation's calls show their confirmation card (ADR-347)."""

    ASK = "ask"
    DIRECT = "direct"


@dataclass(frozen=True)
class AskWhen:
    """A named, pure test over a PREPARED intent that sends a direct call to its card.

    It reads the prepared intent, never the raw call: only the source knows, for
    instance, whether a comment answers a pending action.
    """

    name: str
    reason: str
    test: Callable[[Mapping[str, object]], bool]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.reason.strip():
            raise ValueError("A confirmation exception names itself and states its reason")


@dataclass(frozen=True)
class Confirmation:
    """One operation's confirmation declaration — what ``mutation_policy`` is to a tool."""

    rule: ConfirmationRule = ConfirmationRule.ASK
    reason: str | None = None
    ask_when: AskWhen | None = None

    def __post_init__(self) -> None:
        if self.rule is ConfirmationRule.DIRECT and not (self.reason or "").strip():
            raise ValueError("Acting without a confirmation requires a written reason")
        if self.ask_when is not None and self.rule is not ConfirmationRule.DIRECT:
            raise ValueError("Only a direct operation declares when it still asks")

    @property
    def may_act_directly(self) -> bool:
        """True when some call of the operation may run without its card."""
        return self.rule is ConfirmationRule.DIRECT


ALWAYS_ASK = Confirmation()


def direct(reason: str, *, ask_when: AskWhen | None = None) -> Confirmation:
    """An operation that acts at once: why that is acceptable, and when it still asks."""
    return Confirmation(rule=ConfirmationRule.DIRECT, reason=reason, ask_when=ask_when)
```

In `ApplicationOperationSpec`, after `addressed_device: bool = False`:

```python
    confirmation: Confirmation = ALWAYS_ASK
    aliases: tuple[str, ...] = ()
    binds_origin: bool = False
```

after the `interaction_kind` property:

```python
    @property
    def binds_command_origin(self) -> bool:
        """Whether the persisted command is bound to the originating browser."""
        return self.binds_origin or self.interaction_kind is not None
```

and at the end of `__post_init__`:

```python
        if self.confirmation.may_act_directly and self.kind != OperationKind.ACTION:
            raise ValueError("Only an action may run without its confirmation card")
        if self.confirmation.may_act_directly and self.administrative:
            raise ValueError("An administrative operation always asks")
        if self.tool_name in self.aliases or len(set(self.aliases)) != len(self.aliases):
            raise ValueError("An alias names another tool, once")
        if self.binds_origin and self.interaction_kind is not None:
            raise ValueError("A device or secure operation binds its origin by its kind")
```

Replace `OperationRegistry.register` and document `get_by_tool_name`:

```python
    def register(self, spec: ApplicationOperationSpec) -> None:
        if spec.operation_id in self._operations:
            raise ValueError(f"Duplicate application operation: {spec.operation_id}")
        names = (spec.tool_name, *spec.aliases)
        taken = [name for name in names if name in self._tools]
        if taken:
            raise ValueError(f"Duplicate application tool: {', '.join(taken)}")
        self._operations[spec.operation_id] = spec
        for name in names:
            self._tools[name] = spec

    def get(self, operation_id: str) -> ApplicationOperationSpec:
        return self._operations[operation_id]

    def get_by_tool_name(self, tool_name: str) -> ApplicationOperationSpec | None:
        """The operation a tool serves — its own tool or a declared alias (ADR-347)."""
        return self._tools.get(tool_name)
```

- [ ] **Step 4: Run the new test and the registry's own tests**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_confirmation_declaration.py tests/unit/domains/agents/application/test_operation_tool_identity.py tests/unit/domains/agents/application/test_operation_registry.py -v`
Expected: all PASS (no existing spec declares anything yet).

### Task 0.2: One decision function, and the eight field rules as declarations

**Files:**
- Modify: `apps/api/src/domains/agents/application/confirmation_policy.py`
- Modify: `apps/api/src/domains/agents/application/habit_spec.py` (`HABIT_SETTINGS_OPERATION`), `psyche_catalogue.py` (`PSYCHE_SETTINGS_OPERATION`), `journal_catalogue.py` (`JOURNAL_SETTINGS_OPERATION`), `interest_spec.py` (`INTEREST_SETTINGS_OPERATION`), `registry.py` (heartbeat loop, layout loop, assistant loop, `preferences.update`)
- Modify: `apps/api/src/domains/agents/application/native_tool_preparation.py:54`, `reversible_execution.py:28` (call the new signature)
- Modify: `apps/api/tests/unit/domains/agents/application/test_confirmation_policy.py`, `test_setting_choice_source_guard.py:22-29`

**Interfaces:**
- Consumes: Task 0.1's `Confirmation`, `AskWhen`, `direct`, `ConfirmationRule`.
- Produces (in `src.domains.agents.application.confirmation_policy`): `FreeFields(free: frozenset[str], sensitive_enable: frozenset[str])`, `free_fields(*fields: str, sensitive_enable: frozenset[str] = frozenset()) -> Confirmation`, the eight `*_CONFIRMATION` constants, `requires_confirmation(spec: ApplicationOperationSpec, intent: Mapping[str, object]) -> bool`, `implied_manifest_policy(spec: ApplicationOperationSpec) -> str`. `CONFIRMATION_FREE_FIELDS` and `SENSITIVE_ENABLE_FIELDS` are deleted.

- [ ] **Step 1: Rewrite the decision tests (they fail: the signature changes)**

Replace `apps/api/tests/unit/domains/agents/application/test_confirmation_policy.py` with:

```python
"""Confirmation exceptions are reviewed declarations, never HTTP-method guesses (ADR-347)."""

import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.unit

#: Every operation whose calls may run without their card. A flip edits this
#: list, in the same change as the declaration and the manifest (ADR-347).
DIRECT_OPERATIONS = frozenset(
    {
        "assistant_preferences.update",
        "habit_settings.update",
        "heartbeat_preferences.update",
        "interest_settings.update",
        "journal_settings.update",
        "layout_preferences.update",
        "preferences.update",
        "psyche_settings.update",
    }
)


@pytest.mark.parametrize(
    "operation, intent, expected",
    [
        ("preferences.update", {"color_theme": "forest"}, False),
        ("preferences.update", {"font_size": 17}, False),
        ("preferences.update", {"image_generation_enabled": False}, False),
        ("habit_settings.update", {"habits_enabled": False}, False),
        ("psyche_settings.update", {"psyche_display_avatar": False}, False),
        ("journal_settings.update", {"journals_enabled": False}, False),
        ("journal_settings.update", {"journal_max_total_chars": 1000}, True),
        ("interest_settings.update", {"interests_enabled": False}, False),
        ("heartbeat_preferences.update", {"heartbeat_enabled": False}, False),
        ("assistant_preferences.update", {"tokens_display_enabled": True}, False),
        ("assistant_preferences.update", {"voice_mode_enabled": True}, True),
        ("assistant_preferences.update", {"voice_mode_enabled": False}, False),
        (
            "assistant_preferences.update",
            {"voice_mode_enabled": True, "tokens_display_enabled": False},
            True,
        ),
        ("assistant_preferences.update", {"voice_stt_mode": "remote"}, True),
        (
            "assistant_preferences.update",
            {"tokens_display_enabled": True, "voice_stt_mode": "remote"},
            True,
        ),
        ("assistant_preferences.update", {"login_notifications_enabled": False}, True),
        ("preferences.update", {}, True),
        ("meeting_device.control", {"device_recording": {"action": "start"}}, True),
        ("knowledge_space.delete", {}, True),
    ],
)
def test_risk_based_confirmation(operation: str, intent: dict[str, object], expected: bool) -> None:
    from src.domains.agents.application.confirmation_policy import requires_confirmation
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    assert requires_confirmation(APPLICATION_OPERATIONS.get(operation), intent) is expected


def test_an_undeclared_operation_always_asks() -> None:
    from src.domains.agents.application.confirmation_policy import requires_confirmation
    from src.domains.agents.application.operation_spec import (
        ApplicationOperationSpec,
        OperationKind,
    )

    spec = ApplicationOperationSpec(
        operation_id="future_settings.update",
        tool_name="update_future_settings_tool",
        sections=("future",),
        input_model=BaseModel,
        output_model=BaseModel,
        kind=OperationKind.ACTION,
    )
    assert requires_confirmation(spec, {"enabled": True}) is True


def test_the_operations_that_may_act_directly_are_reviewed() -> None:
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    declared = {
        spec.operation_id
        for spec in APPLICATION_OPERATIONS.all()
        if spec.confirmation.may_act_directly
    }
    assert declared == DIRECT_OPERATIONS


def test_a_field_rule_reads_the_manifest_as_a_card_that_may_ask() -> None:
    from src.domains.agents.application.confirmation_policy import implied_manifest_policy
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    assert implied_manifest_policy(APPLICATION_OPERATIONS.get("preferences.update")) == "draft"
    assert implied_manifest_policy(APPLICATION_OPERATIONS.get("knowledge_space.delete")) == "draft"
```

In `apps/api/tests/unit/domains/agents/application/test_setting_choice_source_guard.py`, replace `test_new_personalization_fields_require_confirmation_review` with:

```python
def test_new_personalization_fields_require_confirmation_review():
    from src.domains.agents.application.confirmation_policy import (
        PREFERENCES_CONFIRMATION,
        FreeFields,
    )
    from src.domains.agents.application.preference_fields import PreferenceField

    rule = PREFERENCES_CONFIRMATION.ask_when
    assert rule is not None and isinstance(rule.test, FreeFields)
    assert rule.test.free == {field.value for field in PreferenceField if field.writable}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_confirmation_policy.py tests/unit/domains/agents/application/test_setting_choice_source_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'implied_manifest_policy'` / `'PREFERENCES_CONFIRMATION'`.

- [ ] **Step 3: Rewrite the head of `confirmation_policy.py`**

Replace lines 1-79 (the docstring, `CONFIRMATION_FREE_FIELDS`, `SENSITIVE_ENABLE_FIELDS` and `requires_confirmation`) with:

```python
"""One confirmation declaration per application operation, and its one reader (ADR-347).

Credentials, external delivery, microphone capture, deletion and autonomous
execution permissions are deliberately outside the field rules below: a field a
rule does not list keeps the confirmation.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from src.domains.agents.application.operation_spec import (
    ApplicationOperationSpec,
    AskWhen,
    Confirmation,
    ConfirmationRule,
    direct,
)


@dataclass(frozen=True)
class FreeFields:
    """The reviewed fields an operation changes at once; any other field asks.

    A sensitive field asks when it is ENABLED: a saved hands-free preference can
    start the wake-word microphone owner when the interface applies it, while
    stopping it is still an immediate action.
    """

    free: frozenset[str]
    sensitive_enable: frozenset[str] = frozenset()

    def __call__(self, intent: Mapping[str, object]) -> bool:
        """True when this prepared intent must show its card."""
        if not intent or not set(intent) <= self.free:
            return True
        return any(intent[field] is not False for field in set(intent) & self.sensitive_enable)


def free_fields(*fields: str, sensitive_enable: frozenset[str] = frozenset()) -> Confirmation:
    """A personalization operation: the listed fields change at once, any other asks."""
    return direct(
        "Reviewed reversible personalization: the listed fields change at once and are "
        "changed back the same way.",
        ask_when=AskWhen(
            name="field_outside_free_list",
            reason=(
                "A field outside the reviewed list, or a sensitive field being enabled, "
                "keeps the confirmation."
            ),
            test=FreeFields(frozenset(fields), sensitive_enable),
        ),
    )


HABIT_SETTINGS_CONFIRMATION = free_fields("habits_enabled")
PSYCHE_SETTINGS_CONFIRMATION = free_fields(
    "psyche_display_avatar", "psyche_sensitivity", "psyche_stability"
)
JOURNAL_SETTINGS_CONFIRMATION = free_fields("journals_enabled", "journal_consolidation_enabled")
INTEREST_SETTINGS_CONFIRMATION = free_fields(
    "interests_enabled",
    "interests_notify_start_hour",
    "interests_notify_end_hour",
    "interests_notify_min_per_day",
    "interests_notify_max_per_day",
)
HEARTBEAT_PREFERENCES_CONFIRMATION = free_fields(
    "heartbeat_enabled",
    "heartbeat_notify_start_hour",
    "heartbeat_notify_end_hour",
    "heartbeat_disabled_sources",
    "moment_kinds_disabled",
)
PREFERENCES_CONFIRMATION = free_fields(
    "timezone",
    "language",
    "personality_id",
    "theme",
    "color_theme",
    "font_family",
    "font_size",
    "image_generation_enabled",
    "image_generation_default_quality",
    "image_generation_default_size",
    "image_generation_output_format",
    "image_generation_prompt_enhancement",
    "exchange_rhythm",
)
LAYOUT_PREFERENCES_CONFIRMATION = free_fields(
    "briefing_preferences", "chat_shortcuts", "settings_shortcuts"
)
ASSISTANT_PREFERENCES_CONFIRMATION = free_fields(
    "memory_enabled",
    "execution_mode",
    "voice_enabled",
    "voice_mode_enabled",
    "tokens_display_enabled",
    "onboarding_completed",
    "debug_panel_enabled",
    "response_display_mode",
    sensitive_enable=frozenset({"voice_mode_enabled"}),
)


def requires_confirmation(spec: ApplicationOperationSpec, intent: Mapping[str, object]) -> bool:
    """THE decision for one prepared intent: does this call show its card?"""
    if spec.confirmation.rule is ConfirmationRule.ASK:
        return True
    ask_when = spec.confirmation.ask_when
    return ask_when is not None and ask_when.test(intent)


def implied_manifest_policy(spec: ApplicationOperationSpec) -> str:
    """The policy every static reader of the manifest is told (ADR-347 §4.4)."""
    confirmation = spec.confirmation
    if confirmation.may_act_directly and confirmation.ask_when is None:
        return "reversible"
    return "draft"
```

Adapt `policy_for_call` (removed in Task 0.5; kept consistent until then):

```python
def policy_for_call(
    tool_name: str, arguments: Mapping[str, object], policy: str | None
) -> str | None:
    """The outer ledger and the native executor use the same reviewed decision."""
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    operation = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
    if operation is None or not operation.confirmation.may_act_directly:
        return policy
    request = _call_intent(operation.operation_id, arguments)
    return (
        "reversible"
        if request is not None and not requires_confirmation(operation, request)
        else policy
    )
```

- [ ] **Step 4: Give the eight operations their declaration**

Each edit adds ONE keyword argument to the existing constructor; import the constant from `src.domains.agents.application.confirmation_policy`:

- `habit_spec.py`, `HABIT_SETTINGS_OPERATION`: `confirmation=HABIT_SETTINGS_CONFIRMATION,`
- `psyche_catalogue.py`, `PSYCHE_SETTINGS_OPERATION`: `confirmation=PSYCHE_SETTINGS_CONFIRMATION,`
- `journal_catalogue.py`, `JOURNAL_SETTINGS_OPERATION`: `confirmation=JOURNAL_SETTINGS_CONFIRMATION,`
- `interest_spec.py`, `INTEREST_SETTINGS_OPERATION`: `confirmation=INTEREST_SETTINGS_CONFIRMATION,`
- `registry.py`, heartbeat loop: `confirmation=(HEARTBEAT_PREFERENCES_CONFIRMATION if heartbeat_kind == OperationKind.ACTION else ALWAYS_ASK),`
- `registry.py`, layout loop: `confirmation=(LAYOUT_PREFERENCES_CONFIRMATION if kind == OperationKind.ACTION else ALWAYS_ASK),`
- `registry.py`, assistant loop: `confirmation=(ASSISTANT_PREFERENCES_CONFIRMATION if kind == OperationKind.ACTION else ALWAYS_ASK),`
- `registry.py`, `preferences.update`: `confirmation=PREFERENCES_CONFIRMATION,`

(`ALWAYS_ASK` is imported in `registry.py` from `operation_spec`.)

- [ ] **Step 5: The two callers read the new signature**

`native_tool_preparation.py:54`:

```python
            if not requires_confirmation(
                APPLICATION_OPERATIONS.get(content.operation_id), content.intent
            ):
```

`reversible_execution.py:28`:

```python
    if spec.administrative or requires_confirmation(spec, content.intent):
```

- [ ] **Step 6: Run the decision tests and every suite that exercises these eight operations**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application -q`
Expected: all PASS. Then `.venv/Scripts/pytest tests/unit/domains/agents/effects -q` → all PASS (the gate still decides through `policy_for_call`, unchanged in behavior).

### Task 0.3: The register as a door uses it

**Files:**
- Modify: `apps/api/src/domains/agents/effects/repository.py` (`find_by_key`; `claim` reuses it)
- Modify: `apps/api/src/domains/agents/effects/runtime.py` (`_Ledger.find`, `_build_request(label=)`, `_record_refusal`, `_run_claimed`, `reset_policy_cache`)
- Create: `apps/api/src/domains/agents/effects/application_effects.py`
- Test: `apps/api/tests/unit/domains/agents/effects/test_application_effects.py` (new)
- Test: `apps/api/tests/integration/domains/agents/effects/test_effect_find_by_key_db.py` (new)

**Interfaces:**
- Produces (in `src.domains.agents.effects.application_effects`): `decided_at_its_door(tool_name: str) -> bool`, `reset_door_cache() -> None`, `served_replay(tool_name: str) -> object | None`, `unanswerable_draft() -> GateDecision | None`, `refuse_draft(tool_name: str, decision: GateDecision, arguments: dict[str, object]) -> str`, `perform_claimed(tool_name: str, arguments: dict[str, object], act: Callable[[], Awaitable[object]], *, label: dict[str, object]) -> object`.
- Produces (repository): `EffectLedgerRepository.find_by_key(thread_id: str, idempotency_key: str) -> AgentEffect | None`.

- [ ] **Step 1: Write the failing unit tests**

```python
"""The register as an application door uses it (ADR-347): the gate's own primitives."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects import application_effects
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE, GateAction
from src.domains.agents.effects.schemas import EffectSourceName
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit

_LABEL = {"i18n_key": "effects.labels.create_reminder_tool", "values": {"target": "sing"}}


class _Ledger:
    def __init__(self, found: gate_runtime.ClaimTicket | None = None, won: bool = True) -> None:
        self.found = found
        self.won = won
        self.claims: list[Any] = []
        self.closed: list[bool] = []
        self.refused: list[str] = []

    async def find(self, thread_id: str, key: str) -> gate_runtime.ClaimTicket | None:
        return self.found

    async def claim(self, request: Any) -> gate_runtime.ClaimTicket:
        self.claims.append(request)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(),
            claim_token=uuid.uuid4() if self.won else None,
            served_result={"success": True, "message": "recorded"} if not self.won else None,
            served_status=None if self.won else "succeeded",
        )

    async def close(self, effect_id: Any, token: Any, *, outcome: Any) -> None:
        self.closed.append(outcome.succeeded)

    async def refuse(self, request: Any, *, error_code: str) -> None:
        self.refused.append(error_code)


@pytest.fixture
def context() -> Any:
    ctx = SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-A",
        execution_mode="react",
        is_automated_source=False,
    )
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=ctx,
    ):
        yield ctx


def _scope(source: EffectSourceName = "user") -> EffectScope:
    return EffectScope(run_id="run-1", idempotency_key="call:abc", source=source)


class TestPerformClaimed:
    async def test_the_act_is_claimed_once_with_its_label_and_closed_from_its_outcome(
        self, context: Any
    ) -> None:
        ledger = _Ledger()
        act = AsyncMock(return_value=UnifiedToolOutput.action_success(message="done"))
        with patch.object(gate_runtime, "_LEDGER", ledger), effect_scope(_scope()):
            result = await application_effects.perform_claimed(
                "create_reminder_tool", {"request": {"content": "sing"}}, act, label=_LABEL
            )
        assert result.success
        act.assert_awaited_once()
        assert len(ledger.claims) == 1
        assert ledger.claims[0].mutation_policy == "reversible"
        assert ledger.claims[0].label == _LABEL
        assert ledger.closed == [True]

    async def test_a_lost_claim_is_served_and_never_performed(self, context: Any) -> None:
        ledger = _Ledger(won=False)
        act = AsyncMock()
        with patch.object(gate_runtime, "_LEDGER", ledger), effect_scope(_scope()):
            result = await application_effects.perform_claimed(
                "create_reminder_tool", {}, act, label=_LABEL
            )
        act.assert_not_awaited()
        assert result == {"success": True, "message": "recorded"}


class TestServedReplay:
    async def test_no_scope_or_no_run_means_no_replay(self) -> None:
        assert await application_effects.served_replay("cancel_reminder_tool") is None

    async def test_a_recorded_act_is_served_after_authority_is_checked(self, context: Any) -> None:
        ticket = gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(),
            claim_token=None,
            served_result={"success": True, "message": "deleted"},
            served_status="succeeded",
        )
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(found=ticket)),
            patch(
                "src.domains.agents.application.confirmation_policy.replay_access_refusal",
                AsyncMock(return_value=None),
            ),
            effect_scope(_scope()),
        ):
            served = await application_effects.served_replay("cancel_reminder_tool")
        assert served == {"success": True, "message": "deleted"}

    async def test_a_replay_never_bypasses_a_withdrawn_capability(self, context: Any) -> None:
        ticket = gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=None, served_result={"success": True}
        )
        refusal = UnifiedToolOutput.failure(
            message="Application action access refused.", error_code="CAPABILITY_DISABLED"
        )
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(found=ticket)),
            patch(
                "src.domains.agents.application.confirmation_policy.replay_access_refusal",
                AsyncMock(return_value=refusal),
            ),
            effect_scope(_scope()),
        ):
            served = await application_effects.served_replay("cancel_reminder_tool")
        assert served is refusal


class TestDraftsNobodyCanAnswer:
    def test_in_the_chat_a_card_can_be_answered(self, context: Any) -> None:
        with effect_scope(_scope("user")):
            assert application_effects.unanswerable_draft() is None

    def test_in_a_routine_it_is_refused_with_the_gate_s_verdict(self, context: Any) -> None:
        with effect_scope(_scope("scheduled")):
            decision = application_effects.unanswerable_draft()
        assert decision is not None and decision.action is GateAction.REFUSE
        assert decision.error_code == ERROR_CONFIRMATION_IMPOSSIBLE

    async def test_the_refusal_is_recorded_like_the_gate_s(self, context: Any) -> None:
        ledger = _Ledger()
        with patch.object(gate_runtime, "_LEDGER", ledger), effect_scope(_scope("scheduled")):
            decision = application_effects.unanswerable_draft()
            assert decision is not None
            message = await application_effects.refuse_draft(
                "update_ticket_tool", decision, {"request": {"run_now": True}}
            )
        assert ledger.refused == [ERROR_CONFIRMATION_IMPOSSIBLE]
        assert "runs unattended" in message
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/effects/test_application_effects.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.domains.agents.effects.application_effects'`.

- [ ] **Step 3: `find_by_key` in the repository**

In `EffectLedgerRepository`, add after `claim`:

```python
    async def find_by_key(self, thread_id: str, idempotency_key: str) -> AgentEffect | None:
        """The row holding ``idempotency_key`` in ``thread_id``, if any (ADR-347).

        A refused row is suffixed (``_REFUSED_KEY_SUFFIX``) and is never found
        under the key of the operation it refused.

        Args:
            thread_id: The conversation.
            idempotency_key: The call's key.

        Returns:
            The row, or None.
        """
        effect: AgentEffect | None = (
            await self.db.execute(
                select(AgentEffect).where(
                    AgentEffect.thread_id == thread_id,
                    AgentEffect.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return effect
```

and in `claim`, replace the `existing = (await self.db.execute(select(...))).scalar_one()` statement with:

```python
        existing = await self.find_by_key(req.thread_id, req.idempotency_key)
        if existing is None:  # pragma: no cover - the conflict proves the row exists
            raise RuntimeError("the row holding a conflicting key vanished")
```

- [ ] **Step 4: The gate's primitives a door reuses (`effects/runtime.py`)**

(a) In `_Ledger`, after `claim`:

```python
    async def find(self, thread_id: str, idempotency_key: str) -> ClaimTicket | None:
        """What an earlier attempt of this call recorded, read without claiming (ADR-347).

        Best-effort: None when nothing holds the key or the ledger is down — the
        caller then prepares and CLAIMS, which stays atomic.

        Args:
            thread_id: The conversation.
            idempotency_key: The call's key.

        Returns:
            A lost-claim ticket carrying the record, or None.
        """
        from src.domains.agents.effects.repository import EffectLedgerRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                effect = await EffectLedgerRepository(db).find_by_key(thread_id, idempotency_key)
                if effect is None:
                    return None
                served = (
                    None
                    if effect.result_truncated
                    else EffectLedgerRepository.decrypted_result(effect)
                )
                return ClaimTicket(
                    effect_id=effect.id,
                    claim_token=None,
                    served_result=served,
                    served_status=effect.status.value,
                )
        except Exception as exc:  # noqa: BLE001 - the claim that follows stays atomic
            effect_ledger_failures_total.labels(operation="find").inc()
            logger.error("effect_ledger_find_failed", error_type=type(exc).__name__, exc_info=True)
            return None
```

(b) `_build_request` gains a keyword `label: dict[str, Any] | None = None` (documented in Args) and writes `label=label if label is not None else build_effect_label(tool_name, kwargs),`.

(c) Split `_refuse_or_ask` so its recording half has one implementation:

```python
async def _record_refusal(
    tool_name: str,
    decision: GateDecision,
    request: ClaimRequest | None,
    scope: EffectScope | None,
) -> str:
    """Record one refusal and return what the model is told (gate and door alike).

    Args:
        tool_name: The tool that was stopped.
        decision: The gate's verdict.
        request: The claim that would have been made, when an identity exists.
        scope: The authority in force.

    Returns:
        The refusal's message, naming a stand-in when a ReAct loop may call one.
    """
    if request is not None:
        await _LEDGER.refuse(request, error_code=str(decision.error_code))
    stand_in = _nameable_stand_in(tool_name, decision, request)
    note_refusal(
        tool_name,
        str(decision.error_code),
        source=scope.source if scope else None,
        stand_in=stand_in[0] if stand_in else None,
    )
    return unattended_refusal_message(*stand_in) if stand_in else str(decision.llm_message)
```

and `_refuse_or_ask` becomes (same Args/Returns docstring as today):

```python
    message = await _record_refusal(tool_name, decision, request, scope)
    if decision.error_code == ERROR_CONFIRMATION_MISSING:
        # Someone IS there to answer: ask, do not fail (ADR-263).
        from src.domains.agents.effects.confirmation import confirmation_draft

        return confirmation_draft(tool_name, named)
    return _refusal_output(tool_name, str(decision.error_code), message)
```

(d) Extract the LEDGER branch:

```python
async def _run_claimed(
    tool_name: str,
    policy: str,
    request: ClaimRequest | None,
    act: Callable[[], Awaitable[Any]],
    *,
    unscoped: bool,
) -> Any:
    """Claim, act, close — the gate's LEDGER branch, shared with the application door.

    Args:
        tool_name: The capability about to act.
        policy: Its policy, as the row records it.
        request: The claim, or None without an identity.
        act: The effect itself.
        unscoped: Whether no executor published an authority.

    Returns:
        The act's result, a served record, or a refusal.
    """
    ticket = await _LEDGER.claim(request) if request is not None else None
    _count_claim(policy, request, ticket)
    if ticket is None:
        refusal = await _unrecorded_or_refused(tool_name, policy, request, unscoped)
        return refusal if refusal is not None else await act()
    if ticket.claim_token is None:
        return _serve_lost_claim(tool_name, ticket)
    return await _perform_and_close(ticket, act, policy=policy)
```

and replace the LEDGER block of `_run_gated` (from `# LEDGER: claim, act, close.` to its final `return await _perform_and_close(...)`) with:

```python
        # LEDGER: claim, act, close.
        return await _run_claimed(
            tool_name,
            str(policy),
            request,
            lambda: observe_activity(tool_name, policy, lambda: coroutine(*args, **kwargs)),
            unscoped=bool(decision.unscoped),
        )
```

(e) `reset_policy_cache` also forgets the door's memo:

```python
def reset_policy_cache() -> None:
    """Forget the memoised policies and door decisions (tests, and a catalogue reload)."""
    from src.domains.agents.effects.application_effects import reset_door_cache

    _policy_cache.clear()
    reset_door_cache()
```

- [ ] **Step 5: Create `effects/application_effects.py`**

```python
"""The effect register, as an application door uses it (ADR-347).

A DIRECT application operation is decided by its door on the PREPARED intent,
not by the gate on the raw call, so the door files the act itself — through the
gate's own primitives, reached here and never copied (the in-turn sandbox
effects are the precedent, ADR-298): whether a tool's door decides, the replay
of an act already recorded, the verdict and record of a card nobody can
answer, and the claim → act → close of the act itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.domains.agents.api.run_origin import current_origin_carries_drafts
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import GateAction, GateDecision, decide_effect
from src.domains.agents.effects.scope import current_scope

_DOOR_DECIDES: dict[str, bool] = {}


def decided_at_its_door(tool_name: str) -> bool:
    """Whether an application door decides this tool's calls, memoised.

    True for the tool, or an alias, of an operation that may act without its
    card: the gate then hands the call over instead of deciding it.

    Args:
        tool_name: The registered tool name.

    Returns:
        True when the door decides.
    """
    if tool_name not in _DOOR_DECIDES:
        from src.domains.agents.application.registry import APPLICATION_OPERATIONS

        spec = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
        _DOOR_DECIDES[tool_name] = spec is not None and spec.confirmation.may_act_directly
    return _DOOR_DECIDES[tool_name]


def reset_door_cache() -> None:
    """Forget the memoised door decisions (tests, and a catalogue reload)."""
    _DOOR_DECIDES.clear()


async def served_replay(tool_name: str) -> object | None:
    """A call whose act an earlier attempt already recorded: served, never prepared again.

    LangGraph replays a node's calls after an interrupt under the same key, and a
    preparation re-reads a state the first execution already changed — a replayed
    deletion would answer « not found ». Current authority is re-checked before
    a record is served: a replay never bypasses a withdrawn capability.

    Args:
        tool_name: The called tool.

    Returns:
        The served record or a refusal, or None when nothing was recorded.
    """
    from src.domains.agents.application.confirmation_policy import replay_access_refusal
    from src.domains.agents.context.runtime_context import runtime_context_if_running

    scope = current_scope()
    context = runtime_context_if_running()
    if scope is None or context is None:
        return None
    ticket = await gate_runtime._LEDGER.find(context.thread_id, scope.idempotency_key)
    if ticket is None:
        return None
    refusal = await replay_access_refusal(tool_name)
    return refusal if refusal is not None else gate_runtime._serve_lost_claim(tool_name, ticket)


def unanswerable_draft() -> GateDecision | None:
    """The gate's refusal of a card nobody can answer now, or None — pure."""
    decision = decide_effect("draft", current_scope(), carrier=current_origin_carries_drafts())
    return decision if decision.action is GateAction.REFUSE else None


async def refuse_draft(
    tool_name: str, decision: GateDecision, arguments: dict[str, object]
) -> str:
    """Record that refusal exactly as the gate does, and return what the model is told.

    Args:
        tool_name: The called tool.
        decision: The verdict ``unanswerable_draft`` returned.
        arguments: What the call asked, for the row's digest.

    Returns:
        The refusal's message.
    """
    scope = current_scope()
    request = gate_runtime._build_request(tool_name, "draft", dict(arguments), scope)
    return await gate_runtime._record_refusal(tool_name, decision, request, scope)


async def perform_claimed(
    tool_name: str,
    arguments: dict[str, object],
    act: Callable[[], Awaitable[object]],
    *,
    label: dict[str, object],
) -> object:
    """Claim the act as ``reversible``, perform it, close its row from its outcome.

    Args:
        tool_name: The called tool.
        arguments: What the call asked, for the row's digest.
        act: The act itself.
        label: The row's label, built from the prepared content (ADR-347 §4.6).

    Returns:
        The act's result, or the record a concurrent duplicate already served.
    """
    scope = current_scope()
    request = gate_runtime._build_request(
        tool_name, "reversible", dict(arguments), scope, label=dict(label)
    )
    return await gate_runtime._run_claimed(
        tool_name, "reversible", request, act, unscoped=scope is None
    )
```

(`replay_access_refusal` is written in Task 0.5; until then `served_replay` is only reached by its own test, which patches it.)

- [ ] **Step 6: Write the PostgreSQL test for `find_by_key`**

`apps/api/tests/integration/domains/agents/effects/test_effect_find_by_key_db.py`:

```python
"""The door reads a call's record by its key — and never a refusal's (ADR-347)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_THREAD = "thread-find-by-key"


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    row = User(
        email=f"find-key-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Find Key Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _request(user: User, key: str) -> ClaimRequest:
    return ClaimRequest(
        user_id=user.id,
        thread_id=_THREAD,
        run_id="run-1",
        source="user",
        execution_mode="react",
        tool_name="cancel_reminder_tool",
        mutation_policy="reversible",
        idempotency_key=key,
        args_digest="c" * 64,
    )


async def test_a_claimed_call_is_found_by_its_key(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    claimed = await repo.claim(_request(user, "call:one"))
    assert claimed.claim_token is not None
    await repo.close_success(claimed.effect.id, claimed.claim_token, result_payload={"ok": True})
    found = await repo.find_by_key(_THREAD, "call:one")
    assert found is not None and found.id == claimed.effect.id
    assert await repo.find_by_key(_THREAD, "call:two") is None


async def test_a_refusal_never_occupies_the_key_it_refused(
    async_session: AsyncSession, user: User
) -> None:
    repo = EffectLedgerRepository(async_session)
    await repo.refuse(_request(user, "call:refused"), error_code="confirmation_impossible")
    assert await repo.find_by_key(_THREAD, "call:refused") is None
```

- [ ] **Step 7: Run the new tests and every gate suite (the refactors must change nothing)**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/effects -q`
Expected: all PASS, including `test_gate_runtime.py`, `test_gate_totality.py`, `test_effect_metrics.py`, `test_unattended_refusal.py`, `test_in_turn_effects.py`.
Run: `task test:backend:integration -- tests/integration/domains/agents/effects -q` (PostgreSQL up) → all PASS.
Run (repo root): `apps/api/.venv/Scripts/python.exe scripts/audit/measure_sloc.py apps/api/src | grep "effects/runtime.py"` → below 600.

### Task 0.4: An application act is labelled by its operation

**Files:**
- Modify: `apps/api/src/domains/agents/effects/labels.py`
- Test: `apps/api/tests/unit/domains/agents/effects/test_effect_labels.py` (new class at the end)

**Interfaces:**
- Produces (in `src.domains.agents.effects.labels`): `APPLICATION_LABELS: dict[str, tuple[str, tuple[str, ...]]]` (operation id → wording key, field path in the prepared intent), `operation_label(content: ApplicationActionDraftContent) -> dict[str, Any]`. `assert_effect_label_completeness` accepts an application tool or alias as labelled through its operation.

- [ ] **Step 1: Write the failing tests**

Append to `test_effect_labels.py`:

```python
class TestAnApplicationActIsLabelledByItsOperation:
    """ADR-347 §4.6: one label per act, whichever tool and whether confirmed or direct."""

    @staticmethod
    def _content(operation_id: str, intent: dict[str, object]) -> dict[str, object]:
        return {"operation_id": operation_id, "title": "Change", "intent": intent}

    def test_a_declared_operation_names_its_object_from_the_prepared_intent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.effects import labels

        monkeypatch.setitem(
            labels.APPLICATION_LABELS,
            "reminder.delete",
            ("effects.labels.draft.reminder_delete", ("reminder_to_delete", "content")),
        )
        label = build_effect_label(
            "draft:application_action",
            {"draft": self._content("reminder.delete", {"reminder_to_delete": {"content": "sing"}})},
        )
        assert label == {
            "i18n_key": "effects.labels.draft.reminder_delete",
            "values": {"target": "sing"},
        }

    def test_an_undeclared_operation_keeps_the_label_that_copies_nothing(self) -> None:
        label = build_effect_label(
            "draft:application_action",
            {"draft": self._content("knowledge_space.delete", {"secret": "never shown"})},
        )
        assert label["i18n_key"] == "effects.labels.draft.application_action_named"
        assert "never shown" not in str(label)

    def test_every_declared_wording_is_translated(self) -> None:
        from src.core.i18n_effects import EFFECT_LABELS
        from src.domains.agents.effects.labels import APPLICATION_LABELS

        missing = sorted(
            key for key, _ in APPLICATION_LABELS.values() if key not in EFFECT_LABELS["en"]
        )
        assert not missing

    def test_a_direct_application_tool_needs_no_builder_of_its_own(self) -> None:
        from src.domains.agents.effects.labels import labelled_by_operation

        assert labelled_by_operation("update_lia_preferences_tool")
        assert labelled_by_operation("cancel_reminder_tool") is False  # not an alias yet
        assert not labelled_by_operation("get_lia_preferences_tool")
```

(The `cancel_reminder_tool` line flips to `True` in Task 1.2, when the alias is declared; the test is edited there.)

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/effects/test_effect_labels.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'APPLICATION_LABELS'`.

- [ ] **Step 3: Implement**

In `labels.py`, add `from collections.abc import Callable, Mapping` (replacing the `Callable` import) and, under `TYPE_CHECKING`, `from src.domains.agents.application.draft_models import ApplicationActionDraftContent`. After `EFFECT_LABEL_BUILDERS`:

```python
#: An application operation that names its object in the register (ADR-347 §4.6):
#: the wording the register already uses for that act, and the path of the field
#: of the operation's PREPARED content that names the object. Only a declared
#: field reaches a label: an arbitrary operation's content may hold what a
#: register line must not, so any other operation keeps the label that copies
#: nothing (« Application action: … »). Keyed by OPERATION, beside the builders
#: keyed by capability, so a confirmed act and a direct one read the same.
APPLICATION_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {}


def _declared_application_label(
    operation_id: str, intent: Mapping[str, Any]
) -> dict[str, Any] | None:
    """The declared label of an application act, or None when undeclared."""
    declared = APPLICATION_LABELS.get(operation_id)
    if declared is None:
        return None
    key, path = declared
    value: Any = intent
    for part in path:
        value = value.get(part) if isinstance(value, Mapping) else None
    return {"i18n_key": key, "values": {"target": _text(value)}}


def operation_label(content: ApplicationActionDraftContent) -> dict[str, Any]:
    """The label of an application act, built exactly as a confirmed one's.

    Args:
        content: The prepared content the act executes.

    Returns:
        ``{"i18n_key": ..., "values": {...}}``.
    """
    return build_effect_label(
        f"{DRAFT_TOOL_PREFIX}application_action", {"draft": content.model_dump(mode="json")}
    )


def labelled_by_operation(tool_name: str) -> bool:
    """Whether a tool's acts are labelled through its operation (ADR-347).

    Args:
        tool_name: A registered tool name, or an alias.

    Returns:
        True for the tool or alias of a non-read application operation.
    """
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    spec = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
    return spec is not None and spec.kind is not OperationKind.READ
```

In `_application_label`, after `if spec.kind == OperationKind.READ: return None`, insert:

```python
    intent = content.get("intent")
    declared = _declared_application_label(
        spec.operation_id, intent if isinstance(intent, Mapping) else {}
    )
    if declared is not None:
        return declared
```

In `assert_effect_label_completeness`, change the manifest condition to:

```python
        if (
            policy in ACTING_POLICIES - {"draft"}
            and name not in EFFECT_LABEL_BUILDERS
            and not labelled_by_operation(name)
        ):
```

- [ ] **Step 4: Run the label suite**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/effects/test_effect_labels.py -v`
Expected: all PASS.

### Task 0.5: The door decides; the gate hands direct operations over

**Files:**
- Create: `apps/api/src/domains/agents/application/refusals.py`
- Create: `apps/api/src/domains/agents/application/action_door.py`
- Rename + modify: `apps/api/src/domains/agents/application/reversible_execution.py` → `direct_execution.py`
- Modify: `apps/api/src/domains/agents/application/native_tool_preparation.py` (whole module)
- Modify: `apps/api/src/domains/agents/application/confirmation_policy.py` (delete `policy_for_call`, `_call_intent`; rename the replay check)
- Modify: `apps/api/src/domains/agents/effects/runtime.py` (`_run_gated` head; delete `_call_effect_policy`)
- Modify (patch paths): `tests/unit/domains/agents/application/test_native_action_boundary.py:53,97`, `test_heartbeat_tool_boundary.py:96,126`, `tests/integration/test_application_layout_preferences.py:55`, `test_application_reversible_features.py:101`, `test_application_reversible_preferences.py:55`
- Modify: `tests/unit/domains/agents/application/test_reversible_refusals.py` (renamed check)
- Test: `apps/api/tests/unit/domains/agents/application/test_action_door.py` (new)

**Interfaces:**
- Consumes: Tasks 0.1–0.4.
- Produces: `application_action(request, runtime, *, name, validate, prepare, refusals, sessions=get_db_context, language=None) -> UnifiedToolOutput` (in `application.action_door`); `Refusal`, `refused`, `answer_from`, `Refusals`, `NATIVE_REFUSALS`, `DIRECT_REFUSALS`, `command_code` (in `application.refusals`); `execute_direct_action(content) -> UnifiedToolOutput` (in `application.direct_execution`); `authorize_replay(tool_name) -> None`, `replay_access_refusal(tool_name) -> UnifiedToolOutput | None` (in `application.confirmation_policy`). `prepare_native_tool` keeps its signature.

- [ ] **Step 1: Write the failing door tests**

```python
"""The one door an application action goes through (ADR-347)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel

from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application import action_door
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import (
    ApplicationOperationSpec,
    AskWhen,
    OperationKind,
    direct,
)
from src.domains.agents.application.refusals import NATIVE_REFUSALS, Refusals, refused
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE, GateAction, GateDecision
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_TOOL = "update_sample_tool"


class _Request(BaseModel):
    run_now: bool = False


def _spec(**changes: object) -> ApplicationOperationSpec:
    base = ApplicationOperationSpec(
        operation_id="sample.update",
        tool_name=_TOOL,
        sections=("sample",),
        input_model=_Request,
        output_model=_Request,
        kind=OperationKind.ACTION,
    )
    return replace(base, **changes)


_ASKS_ON_RUN = AskWhen(
    name="run_requested",
    reason="A run is billed work.",
    test=lambda intent: bool(intent["run_now"]),
)


def _content(actor: UUID, run_now: bool) -> ApplicationActionDraftContent:
    return ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=actor,
        operation_id="sample.update",
        schema_fingerprint="a" * 64,
        expected_digest="b" * 64,
        intent={"run_now": run_now},
        before={},
        after={"run_now": run_now},
        title="Sample change",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncMock]:
    yield AsyncMock()


async def _prepared(_db: object, actor_id: UUID, selected: _Request) -> ApplicationActionDraftContent:
    return _content(actor_id, selected.run_now)


class _FakeDrafts:
    """The card a registered operation's renderer would draw; the sample is not registered."""

    def create_draft(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            metadata={"requires_confirmation": True},
            registry_updates={"draft-1": object()},
        )


async def _call(
    spec: ApplicationOperationSpec | None,
    request: object,
    *,
    record: MagicMock | None = None,
    perform: AsyncMock | None = None,
    execute: AsyncMock | None = None,
    unanswerable: GateDecision | None = None,
    refuse: AsyncMock | None = None,
    save: AsyncMock | None = None,
    prepare: AsyncMock | None = None,
    refusals: Refusals = NATIVE_REFUSALS,
) -> UnifiedToolOutput:
    runtime = make_tool_runtime(user_id=uuid4(), store=InMemoryStore())
    with (
        patch.object(action_door.APPLICATION_OPERATIONS, "get_by_tool_name", return_value=spec),
        patch.object(action_door, "record_treatment", record or MagicMock()),
        patch.object(action_door, "save_command", save or AsyncMock()),
        patch.object(action_door, "DraftService", _FakeDrafts),
        patch(
            "src.domains.agents.effects.application_effects.perform_claimed",
            perform or AsyncMock(side_effect=lambda name, arguments, act, label: act()),
        ),
        patch(
            "src.domains.agents.application.direct_execution.execute_direct_action",
            execute or AsyncMock(return_value=UnifiedToolOutput.action_success(message="done")),
        ),
        patch(
            "src.domains.agents.effects.application_effects.unanswerable_draft",
            MagicMock(return_value=unanswerable),
        ),
        patch(
            "src.domains.agents.effects.application_effects.refuse_draft",
            refuse or AsyncMock(return_value="nobody can answer"),
        ),
    ):
        return await action_door.application_action(
            request,
            runtime,
            name=_TOOL,
            validate=_Request.model_validate,
            prepare=prepare or AsyncMock(side_effect=_prepared),
            refusals=refusals,
            sessions=_session,
        )


async def test_a_direct_call_is_performed_once_and_labelled_by_its_operation() -> None:
    perform = AsyncMock(side_effect=lambda name, arguments, act, label: act())
    execute = AsyncMock(return_value=UnifiedToolOutput.action_success(message="done"))
    result = await _call(
        _spec(confirmation=direct("Editable.")), {"run_now": False}, perform=perform, execute=execute
    )
    assert result.success
    perform.assert_awaited_once()
    name, arguments = perform.await_args.args[:2]
    assert name == _TOOL
    assert arguments == {"request": {"run_now": False}}
    label = perform.await_args.kwargs["label"]
    assert label["i18n_key"].startswith("effects.labels.draft.application_action")
    execute.assert_awaited_once()


async def test_an_ask_when_call_builds_the_card_and_files_a_consultation() -> None:
    record = MagicMock()
    save = AsyncMock()
    perform = AsyncMock()
    result = await _call(
        _spec(confirmation=direct("Editable.", ask_when=_ASKS_ON_RUN)),
        {"run_now": True},
        record=record,
        save=save,
        perform=perform,
    )
    assert result.metadata.get("requires_confirmation")
    save.assert_awaited_once()
    perform.assert_not_awaited()
    record.assert_called_once()
    assert record.call_args.kwargs["succeeded"] is True


async def test_an_ask_when_card_nobody_can_answer_is_refused_before_anything_is_written() -> None:
    save = AsyncMock()
    refuse = AsyncMock(return_value="This action requires an explicit confirmation")
    decision = GateDecision(
        action=GateAction.REFUSE, error_code=ERROR_CONFIRMATION_IMPOSSIBLE, llm_message="x"
    )
    result = await _call(
        _spec(confirmation=direct("Editable.", ask_when=_ASKS_ON_RUN)),
        {"run_now": True},
        save=save,
        refuse=refuse,
        unanswerable=decision,
    )
    assert not result.success
    assert result.error_code == "FORBIDDEN"
    assert f"[{ERROR_CONFIRMATION_IMPOSSIBLE}]" in result.message
    save.assert_not_awaited()
    refuse.assert_awaited_once()


async def test_an_always_asking_operation_leaves_the_registers_to_the_gate() -> None:
    record = MagicMock()
    save = AsyncMock()
    result = await _call(_spec(), {"run_now": False}, record=record, save=save)
    assert result.metadata.get("requires_confirmation")
    save.assert_awaited_once()
    record.assert_not_called()


async def test_a_preparation_refusal_is_a_failed_consultation_never_an_act() -> None:
    record = MagicMock()
    perform = AsyncMock()
    result = await _call(
        _spec(confirmation=direct("Editable.")),
        {"run_now": False},
        record=record,
        perform=perform,
        prepare=AsyncMock(side_effect=ResourceNotFoundError("sample", "x")),
    )
    assert result.error_code == "NOT_FOUND_OR_UNAUTHORIZED"
    perform.assert_not_awaited()
    assert record.call_args.kwargs["succeeded"] is False


async def test_an_invalid_input_answers_the_tool_s_own_sentence() -> None:
    own = Refusals(
        invalid_input=refused(ValueError, message="Invalid sample.", code="INVALID_INPUT"),
        preparation=(),
    )
    result = await _call(_spec(), {"run_now": "maybe"}, refusals=own)
    assert result.error_code == "INVALID_INPUT"
    assert result.message == "Invalid sample."


async def test_an_exception_no_entry_names_propagates_as_before_the_door() -> None:
    own = Refusals(
        invalid_input=refused(ValueError, message="Invalid sample.", code="INVALID_INPUT"),
        preparation=(),
    )
    with pytest.raises(ResourceNotFoundError):
        await _call(
            _spec(),
            {"run_now": False},
            refusals=own,
            prepare=AsyncMock(side_effect=ResourceNotFoundError("sample", "x")),
        )


async def test_a_tool_that_serves_no_operation_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="serves no application operation"):
        await _call(None, {"run_now": False})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_action_door.py -v`
Expected: FAIL — `ImportError: cannot import name 'action_door'`.

- [ ] **Step 3: Create `application/refusals.py`**

```python
"""What an application tool answers when it cannot propose or perform (ADR-347).

Every tool keeps its own sentences and codes — its characterization tests pin
them — so a door call carries the tool's COMPLETE exception table, tried in
order; an exception no entry names propagates exactly as it did before the door
existed. The door's own tables are below: the generic one of the operations
that never had a draft of their own (``NATIVE_REFUSALS``), and the one for what
can only happen while performing a direct act (``DIRECT_REFUSALS``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, BaseAPIException, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.tools.output import UnifiedToolOutput


class Answers(Protocol):
    """One entry of a refusal table."""

    def answers(self, error: BaseException) -> UnifiedToolOutput | None:
        """The tool's answer to ``error``, or None when this entry does not name it."""
        ...


@dataclass(frozen=True)
class Refusal[E: BaseException]:
    """The answer a tool gives to one family of exceptions."""

    exceptions: tuple[type[E], ...]
    answer: Callable[[E], UnifiedToolOutput]

    def answers(self, error: BaseException) -> UnifiedToolOutput | None:
        """The tool's answer to ``error``, or None when this entry does not name it."""
        for kind in self.exceptions:
            if isinstance(error, kind):
                return self.answer(error)
        return None


def refused[E: BaseException](
    *exceptions: type[E], message: str, code: str | Callable[[E], str]
) -> Refusal[E]:
    """An entry answering ``exceptions`` with one sentence and one code."""

    def answer(error: E) -> UnifiedToolOutput:
        return UnifiedToolOutput.failure(
            message=message, error_code=code if isinstance(code, str) else code(error)
        )

    return Refusal(exceptions, answer)


def answer_from(table: Sequence[Answers], error: BaseException) -> UnifiedToolOutput | None:
    """The first entry of ``table`` that names ``error``, in order."""
    for entry in table:
        answer = entry.answers(error)
        if answer is not None:
            return answer
    return None


@dataclass(frozen=True)
class Refusals:
    """A tool's complete exception table: its input, then everything after it."""

    invalid_input: Answers
    preparation: tuple[Answers, ...]


def command_code(error: CommandRejected) -> str:
    """A command refusal's finite code."""
    return error.code


def _api_answer(error: BaseAPIException) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(
        message="Source resource unavailable or constraint refused.",
        error_code="DEPENDENCY_ERROR" if error.status_code >= 500 else "CONSTRAINT_VIOLATION",
    )


NATIVE_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, ValueError, message="Invalid application proposal.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Application proposal refused.",
            code=application_access_error_code,
        ),
        refused(
            ResourceNotFoundError,
            message="Selected resource unavailable.",
            code="NOT_FOUND_OR_UNAUTHORIZED",
        ),
        refused(DomainValidationError, message="Source constraint refused.", code="CONSTRAINT_VIOLATION"),
        refused(CommandRejected, message="Application proposal refused.", code=command_code),
        Refusal((BaseAPIException,), _api_answer),
        refused(
            SQLAlchemyError,
            RedisError,
            OSError,
            message="Application proposal unavailable.",
            code="DEPENDENCY_ERROR",
        ),
        refused(
            ValidationError, ValueError, message="Source state invalid.", code="INVALID_RESPONSE_FORMAT"
        ),
    ),
)

DIRECT_REFUSALS: tuple[Answers, ...] = (
    refused(
        AuthorizationError,
        message="Application action access refused.",
        code=application_access_error_code,
    ),
    refused(CommandRejected, message="Application action refused.", code=command_code),
    refused(
        SQLAlchemyError,
        RedisError,
        OSError,
        message="Application action unavailable.",
        code="DEPENDENCY_ERROR",
    ),
)
```

(Order of `NATIVE_REFUSALS.preparation` is today's `except` order in `native_tool_preparation.py:69-99`; `CommandRejected` subclasses `ValueError`, so it must stay before the last entry.)

- [ ] **Step 4: Rename the direct execution and neutralize its words**

Create `apps/api/src/domains/agents/application/direct_execution.py` with the body of `reversible_execution.py`, then delete `reversible_execution.py`:

```python
"""Execute an application operation at once, through its confirmed executor (ADR-347)."""

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.confirmation_policy import requires_confirmation
from src.domains.agents.application.draft_execution import _execute_outcome
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.setting_choices import describe_setting_values
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.scope import current_scope
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.database.session import get_db_context


async def execute_direct_action(content: ApplicationActionDraftContent) -> UnifiedToolOutput:
    """Run the operation's own confirmed executor now, under current authority.

    Args:
        content: The prepared content.

    Returns:
        The act's outcome and its public values, in neutral technical words.

    Raises:
        CommandRejected: Outside the turn's own authority, or when the
            declaration asks for this intent.
    """
    context = runtime_context_if_running()
    scope = current_scope()
    if context is None or context.user_id != content.actor_id or scope is None:
        raise CommandRejected("FORBIDDEN")
    spec = APPLICATION_OPERATIONS.get(content.operation_id)
    if spec.administrative or requires_confirmation(spec, content.intent):
        raise CommandRejected("CONFIRMATION_MISSING")
    async with get_db_context() as db:
        await require_application_tools(db)
        await load_actor(db, content.actor_id)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)
    receipt = PreferenceWriteReceipt()
    outcome = await _execute_outcome(content, content.actor_id, receipt)
    publish_preference_change(content, receipt)
    if not outcome.success:
        return UnifiedToolOutput(
            success=False,
            message="Application action did not complete. Inspect committed state before retrying.",
            error_message="Application action did not complete.",
            error_code=outcome.error_code or "EXECUTION_FAILED",
            structured_data={"application_result": outcome.model_dump(mode="json")},
        )
    return UnifiedToolOutput.data_success(
        message="Application action completed.",
        structured_data={
            "application_result": outcome.model_dump(mode="json"),
            "setting_choices": describe_setting_values(outcome.values, context.language),
        },
    )
```

- [ ] **Step 5: Create the door, `application/action_door.py`**

```python
"""The one door an application action goes through (ADR-347).

An operation declares whether its calls show their confirmation card
(``ApplicationOperationSpec.confirmation``). An ``ASK`` operation keeps the
effect gate's path — consultation row, refusal where nobody can answer — and
this door only builds its card and command. A ``DIRECT`` operation is handed
here by the gate (after the gate served any recorded replay): the door
prepares, decides on the PREPARED intent, and either builds the card or
performs the act through the gate's own claim → act → close.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application import direct_execution
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.confirmation_policy import requires_confirmation
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.application.refusals import DIRECT_REFUSALS, Refusals, answer_from
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.effects import application_effects
from src.domains.agents.effects.gate import GateDecision
from src.domains.agents.effects.labels import operation_label
from src.domains.agents.effects.outcome import succeeded_only
from src.domains.agents.effects.runtime import resolve_policy
from src.domains.agents.effects.treatments import record_treatment
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context

Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class _Decided:
    """What the preparation session decided, acted on once that session is closed."""

    content: ApplicationActionDraftContent
    card: UnifiedToolOutput | None
    unanswerable: GateDecision | None


async def application_action[Request](
    request: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    *,
    name: str,
    validate: Callable[[object], Request],
    prepare: Callable[[AsyncSession, UUID, Request], Awaitable[ApplicationActionDraftContent]],
    refusals: Refusals,
    sessions: Sessions = get_db_context,
    language: str | None = None,
) -> UnifiedToolOutput:
    """Prepare one application action, decide whether it asks, and record what happened.

    Args:
        request: The tool's argument as received.
        runtime: The injected tool runtime.
        name: The CALLED tool — the operation's own or an alias — for the registers.
        validate: The tool's own input validation.
        prepare: The tool's own preparation, including any resolution it performs.
        refusals: The tool's complete exception table.
        sessions: The session factory the preparation runs in.
        language: The card's language when the tool resolved it itself.

    Returns:
        The card, the act's result, or the tool's refusal.

    Raises:
        ValueError: When ``name`` serves no application operation.
    """
    actor = validate_runtime_config(runtime, name)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    spec = _operation(name)
    started = time.perf_counter()
    try:
        selected = validate(request)
    except (ValidationError, ValueError) as error:
        answer = refusals.invalid_input.answers(error)
        if answer is None:
            raise
        return _consulted(name, spec, started, answer)
    try:
        decided = await _decide(
            spec, selected, UUID(actor.user_id), prepare, sessions, runtime.context, language
        )
    except Exception as error:
        answer = answer_from(refusals.preparation, error)
        if answer is None:
            raise
        return _consulted(name, spec, started, answer)
    if decided.unanswerable is not None:
        message = await application_effects.refuse_draft(
            name, decided.unanswerable, _arguments(selected)
        )
        return UnifiedToolOutput.failure(
            message=f"{message} [{decided.unanswerable.error_code}]", error_code="FORBIDDEN"
        )
    if decided.card is not None:
        return _consulted(name, spec, started, decided.card)
    performed = await application_effects.perform_claimed(
        name,
        _arguments(selected),
        lambda: _perform(decided.content),
        label=operation_label(decided.content),
    )
    return _as_output(performed)


def _operation(name: str) -> ApplicationOperationSpec:
    spec = APPLICATION_OPERATIONS.get_by_tool_name(name)
    if spec is None:
        raise ValueError(f"{name} serves no application operation")
    return spec


async def _decide[Request](
    spec: ApplicationOperationSpec,
    selected: Request,
    actor_id: UUID,
    prepare: Callable[[AsyncSession, UUID, Request], Awaitable[ApplicationActionDraftContent]],
    sessions: Sessions,
    context: LiaRuntimeContext,
    language: str | None,
) -> _Decided:
    """Prepare, decide, and write the card and command when the call asks.

    A direct call writes nothing here: its act runs on sessions of its own once
    this one is closed. A card nobody can answer writes nothing either.
    """
    async with sessions() as db:
        content = await prepare(db, actor_id, selected)
        if not requires_confirmation(spec, content.intent):
            return _Decided(content, None, None)
        if spec.confirmation.may_act_directly:
            unanswerable = application_effects.unanswerable_draft()
            if unanswerable is not None:
                return _Decided(content, None, unanswerable)
        card = DraftService().create_draft(
            draft_type=DraftType.APPLICATION_ACTION,
            content=content.model_dump(mode="json"),
            source_tool=spec.tool_name,
            user_language=language or context.language,
        )
        await save_command(
            db,
            content,
            next(iter(card.registry_updates)),
            origin=context.application_origin if spec.binds_command_origin else None,
            bind_device=spec.addressed_device,
        )
        return _Decided(content, card, None)


async def _perform(content: ApplicationActionDraftContent) -> UnifiedToolOutput:
    try:
        return await direct_execution.execute_direct_action(content)
    except Exception as error:
        answer = answer_from(DIRECT_REFUSALS, error)
        if answer is None:
            raise
        return answer


def _consulted(
    name: str, spec: ApplicationOperationSpec, started: float, output: UnifiedToolOutput
) -> UnifiedToolOutput:
    """File the consultation the gate files for an always-asking operation.

    The gate handed this call over (the operation may act directly), so the
    consultation it would have filed is filed here: a card, or a call that
    stopped before any act was attempted.
    """
    if spec.confirmation.may_act_directly:
        record_treatment(
            name,
            resolve_policy(name),
            succeeded=succeeded_only(output),
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )
    return output


def _arguments(selected: object) -> dict[str, object]:
    """What the call asked, for the register's digest — never stored in clear."""
    if isinstance(selected, BaseModel):
        return {"request": selected.model_dump(mode="json")}
    return {} if selected is None else {"request": str(selected)}


def _as_output(result: object) -> UnifiedToolOutput:
    """The act's own output — or, on a concurrent duplicate, what the register served."""
    if isinstance(result, UnifiedToolOutput):
        return result
    try:
        return UnifiedToolOutput.model_validate(result)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="This action was already handled under the same call and was not repeated.",
            error_code="ALREADY_PERFORMED",
        )
```

- [ ] **Step 6: `prepare_native_tool` becomes a call to the door**

Replace the body of `apps/api/src/domains/agents/application/native_tool_preparation.py` with:

```python
"""One typed native proposal boundary; source-domain preparation stays specific."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_door import application_action
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.refusals import NATIVE_REFUSALS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput


async def prepare_native_tool[Request: BaseModel](
    request: Request | dict[str, object],
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    *,
    name: str,
    model: type[Request],
    prepare: Callable[[AsyncSession, UUID, Request], Awaitable[ApplicationActionDraftContent]],
    sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> UnifiedToolOutput:
    """The door, with the generic refusals of the operations that had no draft of their own."""
    return await application_action(
        request,
        runtime,
        name=name,
        validate=model.model_validate,
        prepare=prepare,
        refusals=NATIVE_REFUSALS,
        sessions=sessions,
    )
```

- [ ] **Step 7: The replay check, renamed and generic; the raw-call reading deleted**

In `confirmation_policy.py`, delete `policy_for_call` and `_call_intent`, and replace `authorize_reversible_replay` / `reversible_access_refusal` with:

```python
async def authorize_replay(tool_name: str) -> None:
    """A recorded act is never served past current account or platform permissions."""
    from src.domains.agents.application.authorization import load_actor
    from src.domains.agents.application.availability import require_application_tools
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.context.runtime_context import runtime_context_if_running
    from src.domains.feature_switches.guard import require_capability_fresh
    from src.infrastructure.database.session import get_db_context

    context = runtime_context_if_running()
    if context is None:
        raise CommandRejected("FORBIDDEN")
    spec = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
    if spec is None:
        raise CommandRejected("UNKNOWN_OPERATION")
    async with get_db_context() as db:
        await require_application_tools(db)
        await load_actor(db, context.user_id, administrative=spec.administrative)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)


async def replay_access_refusal(tool_name: str) -> object | None:
    """The refusal a replay meets when current authority is gone, else None."""
    from sqlalchemy.exc import SQLAlchemyError

    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application.availability import application_access_error_code
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.tools.output import UnifiedToolOutput

    try:
        await authorize_replay(tool_name)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application action access refused.",
            error_code=application_access_error_code(exc),
        )
    except CommandRejected as exc:
        return UnifiedToolOutput.failure(
            message="Application action access refused.", error_code=exc.code
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application action access unavailable.",
            error_code="DEPENDENCY_ERROR",
        )
    return None
```

Update `test_reversible_refusals.py`: patch `authorize_replay` (not `authorize_reversible_replay`) and call `replay_access_refusal(...)`; the asserted codes are unchanged.

- [ ] **Step 8: The gate hands direct operations to their door — test first**

Append to `tests/unit/domains/agents/effects/test_application_effects.py`:

```python
class TestTheGateHandsDirectOperationsToTheirDoor:
    async def test_a_replayed_act_is_served_before_anything_is_prepared(self) -> None:
        calls: list[str] = []

        async def door() -> str:
            calls.append("prepared")
            return "door output"

        with (
            patch.object(application_effects, "decided_at_its_door", return_value=True),
            patch.object(
                application_effects,
                "served_replay",
                AsyncMock(return_value={"success": True, "message": "deleted"}),
            ),
        ):
            result = await gate_runtime.gated("cancel_reminder_tool", door)()
        assert result == {"success": True, "message": "deleted"}
        assert calls == []

    async def test_without_a_record_the_door_runs_and_the_gate_claims_nothing(self) -> None:
        async def door() -> str:
            return "door output"

        ledger = _Ledger()
        with (
            patch.object(gate_runtime, "_LEDGER", ledger),
            patch.object(application_effects, "decided_at_its_door", return_value=True),
            patch.object(application_effects, "served_replay", AsyncMock(return_value=None)),
        ):
            result = await gate_runtime.gated("cancel_reminder_tool", door)()
        assert result == "door output"
        assert ledger.claims == []
```

Run: `.venv/Scripts/pytest tests/unit/domains/agents/effects/test_application_effects.py -k TestTheGateHands -v` → FAIL (the gate does not hand over yet). Then, in `effects/runtime.py`, `_run_gated` begins:

```python
    @functools.wraps(coroutine)
    async def _run_gated(*args: Any, **kwargs: Any) -> Any:
        policy = resolve_policy(tool_name)
        # Imported here: application_effects reaches this module's primitives.
        from src.domains.agents.effects import application_effects

        if application_effects.decided_at_its_door(tool_name):
            # ADR-347: an application operation that may act without its card is
            # decided, claimed and recorded by its door on the PREPARED intent.
            # The gate serves a replay of an act already recorded, and observes.
            replayed = await application_effects.served_replay(tool_name)
            if replayed is not None:
                return replayed
            return await observe_activity(tool_name, policy, lambda: coroutine(*args, **kwargs))
        scope = current_scope()
```

(the two former lines `policy, refusal = await _call_effect_policy(...)` and `if refusal is not None: return refusal` are removed), and delete `_call_effect_policy` entirely.

- [ ] **Step 9: Point the existing tests at the renamed modules**

- `test_native_action_boundary.py:53,97` and `test_heartbeat_tool_boundary.py:96`: patch target `"src.domains.agents.application.direct_execution.execute_direct_action"`, and add a patch of `"src.domains.agents.effects.application_effects.perform_claimed"` with `AsyncMock(side_effect=lambda name, args, act, label: act())` (outside a run there is no register to write; these tests pin the input path).
- `test_heartbeat_tool_boundary.py:126`: patch target `"src.domains.agents.application.action_door.save_command"`.
- `tests/integration/test_application_layout_preferences.py:55`, `test_application_reversible_features.py:101`, `test_application_reversible_preferences.py:55`: replace `"reversible_execution"` by `"direct_execution"` in the module tuple.

- [ ] **Step 10: Run the door tests, the application and effect suites, and the agent suite**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application tests/unit/domains/agents/effects -q`
Expected: all PASS.
Run: `task test:backend:agents` → PASS (the `tests/agents/` suite the pre-commit hook does not run).
Run: `task test:backend:integration -- tests/integration/test_application_reversible_preferences.py tests/integration/test_application_reversible_features.py tests/integration/test_application_layout_preferences.py tests/integration/test_application_confirmed_preferences.py -q` → PASS. In those suites, a direct preference change now writes one effect row labelled `effects.labels.draft.application_action_named` (spec §4.9, change 1): where a test asserts the label key `effects.labels.generic` for a direct change, update it to the named key and note it in the cold review.

### Task 0.6: The declaration is read the same way everywhere

**Files:**
- Modify: `apps/api/src/domains/agents/application/draft_execution.py` (the inline dispatch dict becomes the module-level `APPLICATION_EXECUTORS`)
- Modify: `apps/api/src/domains/agents/application/preference_dispatch.py` (`has_preference_executor`)
- Test: `apps/api/tests/unit/domains/agents/application/test_confirmation_consistency.py` (new)

**Interfaces:**
- Produces: `APPLICATION_EXECUTORS: dict[str, Callable[[AsyncSession, UUID, ApplicationActionDraftContent, PreferenceWriteReceipt], Awaitable[None]]]`; `has_preference_executor(operation_id: str) -> bool`.

- [ ] **Step 1: Write the failing consistency tests**

```python
"""One declaration, read the same way by every reader (ADR-347 §4.4, §4.5, §4.7, §3.4)."""

from __future__ import annotations

import re

import pytest

from src.core.application_tools import APPLICATION_TOOL_ALIASES, APPLICATION_TOOL_NAMES
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.confirmation_policy import implied_manifest_policy
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.registry.catalogue import ToolManifest

pytestmark = pytest.mark.unit

#: Capability members that serve no operation, each with why.
UNSERVED_CAPABILITY_MEMBERS: dict[str, str] = {
    "import_user_skill": "proposes a skill install; the card's click installs (ADR-327)",
    "get_ticket_tool": "a ticket reader with no application operation of its own",
    "list_tickets_tool": "a ticket reader with no application operation of its own",
    "list_reminders_tool": "the compact reminder reader beside get_lia_reminders_tool",
    "create_scheduled_action_tool": "builds its own routine draft (SCHEDULED_ACTION)",
    "list_scheduled_actions_tool": "the compact routine reader beside get_lia_routines_tool",
    # Declared as aliases in lot 1 (Tasks 1.2 and 1.3), which delete these three lines.
    "create_reminder_tool": "an alias of reminder.create from Task 1.2",
    "cancel_reminder_tool": "an alias of reminder.delete from Task 1.2",
    "toggle_scheduled_action_tool": "an alias of routine_state.update from Task 1.3",
}

_PROMISES_A_CONFIRMATION = re.compile(r"confirm|approv", re.IGNORECASE)


def _alias_manifests() -> list[ToolManifest]:
    from src.domains.agents.automation.catalogue_manifests import (
        toggle_scheduled_action_catalogue_manifest,
    )
    from src.domains.agents.reminders.catalogue_manifests import (
        cancel_reminder_catalogue_manifest,
        create_reminder_catalogue_manifest,
    )

    return [
        create_reminder_catalogue_manifest,
        cancel_reminder_catalogue_manifest,
        toggle_scheduled_action_catalogue_manifest,
    ]


def test_every_manifest_carries_the_policy_its_declaration_implies() -> None:
    for manifest in [*APPLICATION_MANIFESTS, *_alias_manifests()]:
        spec = APPLICATION_OPERATIONS.get_by_tool_name(manifest.name)
        if spec is None or spec.kind is OperationKind.READ:
            continue
        assert manifest.mutation_policy == implied_manifest_policy(spec), manifest.name
        if manifest.mutation_policy == "reversible":
            assert manifest.mutation_policy_reason == spec.confirmation.reason, manifest.name


def test_the_capability_lists_every_tool_and_alias_and_names_the_others() -> None:
    served = {spec.tool_name for spec in APPLICATION_OPERATIONS.all()} | {
        alias for spec in APPLICATION_OPERATIONS.all() for alias in spec.aliases
    }
    assert set(APPLICATION_TOOL_NAMES) | set(APPLICATION_TOOL_ALIASES) == served | set(
        UNSERVED_CAPABILITY_MEMBERS
    )
    assert {alias for spec in APPLICATION_OPERATIONS.all() for alias in spec.aliases} <= set(
        APPLICATION_TOOL_ALIASES
    )


def test_every_declared_alias_is_a_registered_tool_with_a_manifest_here() -> None:
    from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

    ensure_tools_loaded()
    aliases = {alias for spec in APPLICATION_OPERATIONS.all() for alias in spec.aliases}
    assert aliases <= set(get_all_tools())
    assert aliases <= {manifest.name for manifest in _alias_manifests()}


def test_every_action_keeps_a_confirmed_executor() -> None:
    from src.domains.agents.application.draft_execution import APPLICATION_EXECUTORS
    from src.domains.agents.application.preference_dispatch import has_preference_executor

    missing = sorted(
        spec.operation_id
        for spec in APPLICATION_OPERATIONS.all()
        if spec.kind is OperationKind.ACTION
        and spec.operation_id not in APPLICATION_EXECUTORS
        and not has_preference_executor(spec.operation_id)
    )
    assert not missing


def test_a_tool_that_never_asks_promises_no_confirmation() -> None:
    from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

    ensure_tools_loaded()
    tools = get_all_tools()
    manifests = {manifest.name: manifest for manifest in [*APPLICATION_MANIFESTS, *_alias_manifests()]}
    for spec in APPLICATION_OPERATIONS.all():
        if implied_manifest_policy(spec) != "reversible":
            continue
        for name in (spec.tool_name, *spec.aliases):
            assert not _PROMISES_A_CONFIRMATION.search(manifests[name].description), name
            assert not _PROMISES_A_CONFIRMATION.search(tools[name].description), name


def test_the_policy_guard_names_a_forgotten_flip() -> None:
    from dataclasses import replace

    from src.domains.agents.application.operation_spec import direct

    asking = APPLICATION_OPERATIONS.get("knowledge_space.delete")
    flipped = replace(asking, confirmation=direct("Sample flip."))
    assert implied_manifest_policy(flipped) == "reversible"
    manifest = next(m for m in APPLICATION_MANIFESTS if m.name == asking.tool_name)
    assert manifest.mutation_policy != implied_manifest_policy(flipped)


def test_the_wording_guard_reads_a_promised_confirmation() -> None:
    assert _PROMISES_A_CONFIRMATION.search("Prepare exact human confirmation to delete")
    assert _PROMISES_A_CONFIRMATION.search("No write before approval.")
    assert not _PROMISES_A_CONFIRMATION.search("Delete one owned pending reminder at once.")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_confirmation_consistency.py -v`
Expected: FAIL — `ImportError: cannot import name 'APPLICATION_EXECUTORS'` (the other tests PASS: no operation is `reversible` yet).

- [ ] **Step 3: Expose the executors and the preference predicate**

In `draft_execution.py`, move the dict literal of `_apply_approved_action` (lines 185-279, unchanged entries) to module level:

```python
ApplicationExecutorFn = Callable[
    [AsyncSession, UUID, ApplicationActionDraftContent, PreferenceWriteReceipt],
    Awaitable[None],
]

#: The confirmed executor of every operation not served by the preference
#: dispatch — also what a direct call runs (ADR-347 §4.7).
APPLICATION_EXECUTORS: dict[str, ApplicationExecutorFn] = {
    "knowledge_source.unlink": execute_source_unlink,
    # … every entry of today's literal, in the same order …
    "routine.execute": execute_routine_launch,
}
```

and in `_apply_approved_action`: `execute = APPLICATION_EXECUTORS.get(draft.operation_id)`. (Every entry is copied verbatim from the literal; nothing is added or removed. Add `from collections.abc import Awaitable` and `from sqlalchemy.ext.asyncio import AsyncSession` if absent.)

In `preference_dispatch.py`, after `preference_model`:

```python
def has_preference_executor(operation_id: str) -> bool:
    """Whether the preference dispatch executes this operation."""
    return operation_id in _PREFERENCE_MODELS
```

- [ ] **Step 4: Run them**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_confirmation_consistency.py tests/unit/domains/agents/application/test_manifest_parity.py -v`
Expected: all PASS.

### Task 0.7: No application draft and no command outside the door

**Files:**
- Test: `apps/api/tests/unit/domains/agents/application/test_application_door_guard.py` (new)

- [ ] **Step 1: Write the guard (it passes at once; its sample must fail)**

```python
"""No application draft and no persisted command outside the door (ADR-347 §4.8).

AST-based: a call to ``save_command`` or a ``create_draft`` naming
``DraftType.APPLICATION_ACTION`` anywhere under ``src/`` outside the door is a
second decision point. The modules not yet migrated are listed, shrink-only:
a migrated module MUST leave the list, and the list ends empty (part 2).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[5] / "src"
_DOOR = {
    "domains/agents/application/action_door.py",
    "domains/agents/application/command_repository.py",
}
#: Shrink-only. Lot 1 removes the reminder and routine modules, lot 2 the ticket
#: creation, part 2 the rest — and then this set is empty.
NOT_YET_MIGRATED: frozenset[str] = frozenset(
    {
        "domains/agents/tools/application_channel_tools.py",
        "domains/agents/tools/application_connection_tools.py",
        "domains/agents/tools/application_connector_tools.py",
        "domains/agents/tools/application_export_tools.py",
        "domains/agents/tools/application_habit_action_tools.py",
        "domains/agents/tools/application_health_tools.py",
        "domains/agents/tools/application_interest_lifecycle_tools.py",
        "domains/agents/tools/application_interest_tools.py",
        "domains/agents/tools/application_journal_tools.py",
        "domains/agents/tools/application_live_connector_tools.py",
        "domains/agents/tools/application_live_tools.py",
        "domains/agents/tools/application_location_tools.py",
        "domains/agents/tools/application_management_export_tools.py",
        "domains/agents/tools/application_memory_tools.py",
        "domains/agents/tools/application_notification_tools.py",
        "domains/agents/tools/application_open_loop_action_tools.py",
        "domains/agents/tools/application_peer_tools.py",
        "domains/agents/tools/application_phone_tools.py",
        "domains/agents/tools/application_psyche_reset_tools.py",
        "domains/agents/tools/application_psyche_tools.py",
        "domains/agents/tools/application_relation_tools.py",
        "domains/agents/tools/application_reminder_tools.py",
        "domains/agents/tools/application_routine_tools.py",
        "domains/agents/tools/application_session_tools.py",
        "domains/agents/tools/application_shared_mcp_tools.py",
        "domains/agents/tools/workboard_creation_tool.py",
    }
)


def _is_application_draft(call: ast.Call) -> bool:
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "create_draft"):
        return False
    values = [keyword.value for keyword in call.keywords if keyword.arg == "draft_type"]
    values += call.args[:1]
    return any(
        isinstance(value, ast.Attribute)
        and value.attr == "APPLICATION_ACTION"
        and isinstance(value.value, ast.Name)
        and value.value.id == "DraftType"
        for value in values
    )


def _is_save_command(call: ast.Call) -> bool:
    func = call.func
    return (isinstance(func, ast.Name) and func.id == "save_command") or (
        isinstance(func, ast.Attribute) and func.attr == "save_command"
    )


def offenders(source: str) -> bool:
    return any(
        isinstance(node, ast.Call) and (_is_application_draft(node) or _is_save_command(node))
        for node in ast.walk(ast.parse(source))
    )


def _offending_modules() -> set[str]:
    return {
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if offenders(path.read_text(encoding="utf-8"))
    } - _DOOR


def test_only_the_door_writes_application_drafts_and_commands() -> None:
    assert _offending_modules() <= NOT_YET_MIGRATED


def test_a_migrated_module_leaves_the_list() -> None:
    stale = sorted(NOT_YET_MIGRATED - _offending_modules())
    assert not stale, f"migrated, remove from NOT_YET_MIGRATED: {stale}"


def test_the_guard_catches_a_new_draft_builder() -> None:
    sample = (
        "async def tool():\n"
        "    output = DraftService().create_draft(draft_type=DraftType.APPLICATION_ACTION, content={})\n"
        "    await save_command(db, content, 'id')\n"
    )
    assert offenders(sample)
    assert not offenders("DraftService().create_draft(draft_type=DraftType.EMAIL, content={})")
```

- [ ] **Step 2: Run it**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_application_door_guard.py -v`
Expected: PASS (the 26 modules offend and are listed; the door is exempt; `native_tool_preparation.py` no longer offends since Task 0.5).

### Task 0.8: Lot 0 gates and cold review

- [ ] **Step 1: Static gates**

Run (repo root): `task lint`
Expected: exit 0 (Black, Ruff, MyPy strict, ratchets — SLOC, complexity, coupling cycles —, hygiene, docs).

- [ ] **Step 2: Behavioral gates**

Run: `task test:backend:unit:fast` → PASS. Run: `task test:backend:agents` → PASS. Run: `task test:backend:integration -- tests/integration/domains/agents/effects tests/integration/test_application_reversible_preferences.py tests/integration/test_application_reversible_features.py tests/integration/test_application_layout_preferences.py tests/integration/test_application_confirmed_preferences.py -q` → PASS.

- [ ] **Step 3: Runtime proof on the dev stack, no model call**

`docker restart lia-api-dev`, then `docker logs lia-api-dev --since 2m | grep -E "assert|Completeness|ERROR" | head` → no completeness failure. In the container (scratchpad script, `MSYS_NO_PATHCONV=1 docker exec -i -w /app -e PYTHONPATH=/app lia-api-dev python - < script.py`), on the proof account `d7db1a08-6307-4c5b-9d8a-981d191e533a`, call `update_lia_preferences_tool.coroutine(change={"mode": "set", "patch": {"font_size": 17}}, runtime=...)` under `installed_runtime_context(...)` and an `effect_scope(...)`: assert `application_result.committed`, one `agent_effects` row labelled `effects.labels.draft.application_action_named`, then restore `font_size` to its value read before the call.

- [ ] **Step 4: Exhaustive cold review**

Read again, line by line, every file Tasks 0.1–0.7 created or changed (14 source files, 12 test files). For each: behavior unchanged where the plan says so; names and types match the Interfaces blocks; no dead code (`policy_for_call`, `_call_intent`, `_call_effect_policy`, `reversible_execution.py` all gone, `grep -rn` returns nothing); docstrings say what the code does. Fix every finding before lot 1.

---

## Lot 1 — reminders and routines

### Task 1.1: Characterize the eight tools and three aliases before touching them

**Files:**
- Test: `apps/api/tests/unit/domains/agents/application/test_lot1_refusal_characterization.py` (new)

The success paths (card, persisted command, confirmed execution) are already pinned on PostgreSQL by `tests/integration/test_application_reminder_creation.py`, `test_application_reminder_update_hitl.py`, `test_application_reminder_update_edit.py`, `test_application_reminder_delete_hitl.py`, `test_application_routine_state.py`, `test_application_routine_creation.py`, `test_application_routine_update.py`, `test_application_routine_removal.py`, `test_application_routine_execution.py`. This task pins every refusal sentence and code, which those suites do not cover exhaustively.

- [ ] **Step 1: Write the characterization (it must pass against TODAY's code)**

```python
"""Every refusal of the lot-1 tools, pinned before their migration to the door (ADR-347)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import SQLAlchemyError

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.tools import (
    application_reminder_tools,
    application_routine_tools,
    automation_tools,
    reminder_tools,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_ID = str(uuid4())
_DISABLED = AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
_ROUTINE = RoutineCreateRequest(
    title="Weather",
    action_prompt="Read the weather",
    recurrence=RecurrenceSpec(
        freq="daily",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
        anchor_date=date(2026, 9, 1),
    ),
).model_dump(mode="json")


@dataclass(frozen=True)
class Case:
    tool_module: ModuleType
    tool: str
    kwargs: dict[str, object]
    raising: str
    patches: dict[str, object] = field(default_factory=dict)


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncMock]:
    yield AsyncMock()


async def _run(case: Case, error: BaseException | None) -> UnifiedToolOutput:
    actor = uuid4()
    reminder_row = MagicMock(id=uuid4(), is_enabled=True)
    service = MagicMock()
    service.return_value.resolve_reminder = AsyncMock(return_value=reminder_row)
    service.return_value.get_with_ownership_check = AsyncMock(return_value=reminder_row)
    with ExitStack() as stack:
        # `@with_user_preferences` (the three aliases) reads the user row; a unit test must not.
        stack.enter_context(
            patch(
                "src.domains.agents.tools.runtime_helpers.get_user_preferences",
                AsyncMock(return_value=(DEFAULT_USER_DISPLAY_TIMEZONE, "fr", "fr")),
            )
        )
        for module in (application_reminder_tools, application_routine_tools):
            stack.enter_context(patch.object(module, "get_db_context", _session))
            stack.enter_context(patch.object(module, "require_application_tools", AsyncMock()))
        stack.enter_context(patch.object(application_reminder_tools, "load_actor", AsyncMock()))
        stack.enter_context(patch.object(application_reminder_tools, "ReminderService", service))
        stack.enter_context(
            patch.object(application_routine_tools, "ScheduledActionService", service)
        )
        owner = (
            application_routine_tools
            if case.raising.startswith("prepare_routine")
            else application_reminder_tools
        )
        stack.enter_context(patch.object(owner, case.raising, AsyncMock(side_effect=error)))
        tool = getattr(case.tool_module, case.tool)
        return await tool.coroutine(
            **case.kwargs, runtime=make_tool_runtime(user_id=actor, store=InMemoryStore())
        )


_UPDATE = Case(
    application_reminder_tools,
    "update_lia_reminder_tool",
    {"selection": {"reminder_id": _ID, "changes": {"content": "sing"}}},
    "prepare_reminder_update",
)
_DELETE = Case(
    application_reminder_tools,
    "delete_lia_reminder_tool",
    {"selection": {"reminder_id": _ID}},
    "prepare_reminder_removal",
)
_CANCEL = Case(
    reminder_tools, "cancel_reminder_tool", {"reminder_identifier": "next"}, "prepare_reminder_removal"
)
_CREATE = Case(
    application_reminder_tools,
    "create_lia_reminder_tool",
    {
        "configuration": {
            "content": "sing",
            "original_message": "remind me to sing",
            "trigger_at": "2026-12-01T09:00:00",
        }
    },
    "prepare_reminder_creation",
)
_CREATE_ALIAS = Case(
    reminder_tools,
    "create_reminder_tool",
    {
        "content": "sing",
        "original_message": "remind me to sing",
        "trigger_datetime": "2026-12-01T09:00:00",
    },
    "prepare_reminder_creation",
)
_STATE = Case(
    application_routine_tools,
    "set_lia_routine_state_tool",
    {"change": {"routine_id": _ID, "enabled": False}},
    "prepare_routine_state",
)
_TOGGLE = Case(automation_tools, "toggle_scheduled_action_tool", {"action_id": _ID}, "prepare_routine_state")
_RUN = Case(
    application_routine_tools,
    "execute_lia_routine_tool",
    {"selection": {"routine_id": _ID}},
    "prepare_routine_launch",
)
_ROUTINE_UPDATE = Case(
    application_routine_tools,
    "update_lia_routine_tool",
    {"change": {"routine_id": _ID, "changes": {"title": "Weather"}}},
    "prepare_routine_update",
)
_ROUTINE_DELETE = Case(
    application_routine_tools,
    "delete_lia_routine_tool",
    {"selection": {"routine_id": _ID}},
    "prepare_routine_removal",
)
_ROUTINE_CREATE = Case(
    application_routine_tools,
    "create_lia_routine_tool",
    {"configuration": _ROUTINE},
    "prepare_routine_creation",
)

REFUSALS: list[tuple[Case, BaseException, str, str]] = [
    (_UPDATE, _DISABLED, "Reminder access refused.", "CAPABILITY_DISABLED"),
    (_UPDATE, ResourceNotFoundError("reminder"), "Reminder unavailable.", "NOT_FOUND"),
    (_UPDATE, ResourceConflictError("reminder"), "Reminder is being processed.", "REMINDER_BUSY"),
    (_UPDATE, SQLAlchemyError(), "Reminder proposal unavailable.", "DEPENDENCY_ERROR"),
    (_UPDATE, ValueError("x"), "Invalid reminder change.", "INVALID_INPUT"),
    (_DELETE, _DISABLED, "Reminder access refused.", "CAPABILITY_DISABLED"),
    (_DELETE, ResourceNotFoundError("reminder"), "Reminder unavailable.", "NOT_FOUND"),
    (_DELETE, ResourceConflictError("reminder"), "Reminder is being processed.", "REMINDER_BUSY"),
    (_DELETE, SQLAlchemyError(), "Reminder proposal unavailable.", "DEPENDENCY_ERROR"),
    (_DELETE, ValueError("x"), "Invalid reminder selection.", "INVALID_INPUT"),
    (_CANCEL, _DISABLED, "Reminder access refused.", "CAPABILITY_DISABLED"),
    (_CANCEL, ResourceConflictError("reminder"), "Reminder is being processed.", "REMINDER_BUSY"),
    (_CANCEL, ValueError("x"), "Invalid reminder selection.", "INVALID_INPUT"),
    (_CREATE, _DISABLED, "Reminder access refused.", "CAPABILITY_DISABLED"),
    (_CREATE, SQLAlchemyError(), "Reminder proposal unavailable.", "DEPENDENCY_ERROR"),
    (_CREATE, ValueError("x"), "Invalid reminder configuration.", "INVALID_INPUT"),
    (_CREATE_ALIAS, _DISABLED, "Reminder access refused.", "CAPABILITY_DISABLED"),
    (_CREATE_ALIAS, SQLAlchemyError(), "Reminder proposal unavailable.", "DEPENDENCY_ERROR"),
    (_CREATE_ALIAS, ValueError("x"), "Invalid reminder configuration.", "INVALID_INPUT"),
    (
        _CREATE_ALIAS,
        ResourceNotFoundError("reminder"),
        "Reminder proposal unavailable.",
        "DEPENDENCY_ERROR",
    ),
    (_STATE, _DISABLED, "Routine proposal unavailable.", "CAPABILITY_DISABLED"),
    (_STATE, ResourceNotFoundError("routine"), "Routine unavailable.", "NOT_FOUND"),
    (_STATE, SQLAlchemyError(), "Routine proposal unavailable.", "DEPENDENCY_ERROR"),
    (_STATE, ValueError("x"), "Invalid routine configuration.", "INVALID_INPUT"),
    (_TOGGLE, _DISABLED, "Routine proposal unavailable.", "CAPABILITY_DISABLED"),
    (_TOGGLE, ValueError("x"), "Invalid routine configuration.", "INVALID_INPUT"),
    (_RUN, _DISABLED, "Routine access refused.", "CAPABILITY_DISABLED"),
    (_RUN, ResourceNotFoundError("routine"), "Routine unavailable.", "NOT_FOUND"),
    (_RUN, ResourceConflictError("routine"), "Routine is already executing.", "ALREADY_EXECUTING"),
    (_RUN, SQLAlchemyError(), "Routine proposal unavailable.", "DEPENDENCY_ERROR"),
    (_RUN, ValueError("x"), "Invalid routine configuration.", "INVALID_INPUT"),
    (_ROUTINE_UPDATE, _DISABLED, "Routine access refused.", "CAPABILITY_DISABLED"),
    (_ROUTINE_UPDATE, ResourceNotFoundError("routine"), "Routine unavailable.", "NOT_FOUND"),
    (_ROUTINE_UPDATE, SQLAlchemyError(), "Routine proposal unavailable.", "DEPENDENCY_ERROR"),
    (
        _ROUTINE_UPDATE,
        DomainValidationError("bad"),
        "Invalid routine schedule or configuration.",
        "INVALID_INPUT",
    ),
    (_ROUTINE_DELETE, _DISABLED, "Routine access refused.", "CAPABILITY_DISABLED"),
    (_ROUTINE_DELETE, ResourceNotFoundError("routine"), "Routine unavailable.", "NOT_FOUND"),
    (_ROUTINE_DELETE, SQLAlchemyError(), "Routine proposal unavailable.", "DEPENDENCY_ERROR"),
    (_ROUTINE_DELETE, ValueError("x"), "Invalid routine state.", "INVALID_RESPONSE_FORMAT"),
    (_ROUTINE_CREATE, _DISABLED, "Routine access refused.", "CAPABILITY_DISABLED"),
    (_ROUTINE_CREATE, SQLAlchemyError(), "Routine proposal unavailable.", "DEPENDENCY_ERROR"),
    (
        _ROUTINE_CREATE,
        ValueError("x"),
        "Invalid routine schedule or configuration.",
        "INVALID_INPUT",
    ),
]


@pytest.mark.parametrize(("case", "error", "message", "code"), REFUSALS)
async def test_every_refusal_keeps_its_sentence_and_code(
    case: Case, error: BaseException, message: str, code: str
) -> None:
    result = await _run(case, error)
    assert not result.success
    assert (result.message, result.error_code) == (message, code)


UNLISTED: list[tuple[Case, BaseException]] = [
    (_CREATE, ResourceNotFoundError("reminder")),
    (_ROUTINE_CREATE, ResourceNotFoundError("routine")),
]


@pytest.mark.parametrize(("case", "error"), UNLISTED)
async def test_an_exception_the_tool_never_named_still_propagates(
    case: Case, error: BaseException
) -> None:
    with pytest.raises(type(error)):
        await _run(case, error)


INVALID: list[tuple[Case, dict[str, object], str, str]] = [
    (_UPDATE, {"selection": {"reminder_id": "x", "changes": {}}}, "Invalid reminder change.", "INVALID_INPUT"),
    (_DELETE, {"selection": {"reminder_id": "x"}}, "Invalid reminder selection.", "INVALID_INPUT"),
    (_CREATE, {"configuration": {"content": ""}}, "Invalid reminder configuration.", "INVALID_INPUT"),
    (_STATE, {"change": {"routine_id": _ID, "enabled": "no"}}, "Invalid desired routine state.", "INVALID_INPUT"),
    (_TOGGLE, {"action_id": "x"}, "invalid automation id", "invalid_id"),
    (_RUN, {"selection": {"routine_id": "x"}}, "Invalid routine configuration.", "INVALID_INPUT"),
    (_ROUTINE_UPDATE, {"change": {"routine_id": _ID, "changes": {}}}, "Invalid routine schedule or configuration.", "INVALID_INPUT"),
    (_ROUTINE_DELETE, {"selection": {"routine_id": "x"}}, "Invalid routine selection.", "INVALID_INPUT"),
    (_ROUTINE_CREATE, {"configuration": {"title": ""}}, "Invalid routine configuration.", "INVALID_INPUT"),
]


@pytest.mark.parametrize(("case", "kwargs", "message", "code"), INVALID)
async def test_an_invalid_input_keeps_its_sentence_and_code(
    case: Case, kwargs: dict[str, object], message: str, code: str
) -> None:
    result = await _run(Case(case.tool_module, case.tool, kwargs, case.raising), None)
    assert (result.message, result.error_code) == (message, code)
```

- [ ] **Step 2: Run it against today's code**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_lot1_refusal_characterization.py -v`
Expected: all PASS. A failing row means the row is wrong, not the code: read the tool again and correct the row — never the tool — before going on. (`_CANCEL` uses `"next"`, which reaches `ReminderService.resolve_reminder`, patched; `_TOGGLE` reaches `ScheduledActionService.get_with_ownership_check`, patched.)

### Task 1.2: Reminders through the door

**Files:**
- Modify: `apps/api/src/domains/agents/tools/application_reminder_tools.py` (all but `get_lia_reminders_tool`)
- Modify: `apps/api/src/domains/agents/tools/reminder_tools.py` (`create_reminder_tool` tail, `cancel_reminder_tool`)
- Modify: `apps/api/src/domains/agents/application/reminder_spec.py` (aliases)
- Modify: `apps/api/tests/unit/domains/agents/application/test_confirmation_consistency.py` (delete the two reminder lines of `UNSERVED_CAPABILITY_MEMBERS`)
- Modify: `apps/api/tests/unit/domains/agents/effects/test_effect_labels.py` (`cancel_reminder_tool` is now labelled by its operation: `is True`)
- Modify: `apps/api/tests/unit/domains/agents/application/test_application_door_guard.py` (remove `application_reminder_tools.py` from `NOT_YET_MIGRATED`)
- Modify: `apps/api/tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py` (`_capture_created` patches the new helper, Step 4)

**Interfaces:**
- Produces (in `application_reminder_tools`): `reminder_creation(configuration, runtime, *, name, validate, language=None) -> UnifiedToolOutput`, `reminder_removal(selection, runtime, *, name, validate, language=None) -> UnifiedToolOutput`, `REMINDER_UPDATE_REFUSALS`, `REMINDER_REMOVAL_REFUSALS`, `REMINDER_CREATION_REFUSALS`. `reminder_creation_proposal` and `reminder_removal_proposal` are deleted.

- [ ] **Step 1: Declare the aliases**

`reminder_spec.py`: add `aliases=("cancel_reminder_tool",),` to `REMINDER_DELETE_OPERATION` and `aliases=("create_reminder_tool",),` to `REMINDER_CREATE_OPERATION`.

- [ ] **Step 2: Rewrite the reminder actions on the door**

Replace everything above `@read_tool(name="get_lia_reminders"…` in `application_reminder_tools.py` (keep the read tool and its imports) with:

```python
"""Application reminder readers and actions use the existing source business rules."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_door import application_action
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.refusals import Refusals, refused
from src.domains.agents.application.reminder_create_schemas import ReminderCreateRequest
from src.domains.agents.application.reminder_creation import prepare_reminder_creation
from src.domains.agents.application.reminder_queries import read_reminders
from src.domains.agents.application.reminder_read_schemas import ReminderRead
from src.domains.agents.application.reminder_removal import prepare_reminder_removal
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.agents.application.reminder_update import prepare_reminder_update
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.reminders.service import ReminderService
from src.infrastructure.database.session import get_db_context

ToolRuntimeArg = Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg]

REMINDER_UPDATE_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, ValueError, message="Invalid reminder change.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Reminder access refused.",
            code=application_access_error_code,
        ),
        refused(ResourceNotFoundError, message="Reminder unavailable.", code="NOT_FOUND"),
        refused(
            ResourceConflictError, message="Reminder is being processed.", code="REMINDER_BUSY"
        ),
        refused(SQLAlchemyError, message="Reminder proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(ValidationError, ValueError, message="Invalid reminder change.", code="INVALID_INPUT"),
    ),
)
REMINDER_REMOVAL_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, ValueError, message="Invalid reminder selection.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Reminder access refused.",
            code=application_access_error_code,
        ),
        refused(ResourceNotFoundError, message="Reminder unavailable.", code="NOT_FOUND"),
        refused(
            ResourceConflictError, message="Reminder is being processed.", code="REMINDER_BUSY"
        ),
        refused(SQLAlchemyError, message="Reminder proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            ValidationError, ValueError, message="Invalid reminder selection.", code="INVALID_INPUT"
        ),
    ),
)
REMINDER_CREATION_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, ValueError, message="Invalid reminder configuration.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Reminder access refused.",
            code=application_access_error_code,
        ),
        refused(SQLAlchemyError, message="Reminder proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            ValidationError,
            ValueError,
            message="Invalid reminder configuration.",
            code="INVALID_INPUT",
        ),
    ),
)


def _sparse_change(value: object) -> ReminderUpdateRequest:
    parsed = ReminderUpdateRequest.model_validate(value)
    return ReminderUpdateRequest.model_validate(parsed.model_dump(mode="json", exclude_unset=True))


def _removal_target(value: object) -> UUID:
    parsed = ReminderDeleteRequest.model_validate(value)
    return ReminderDeleteRequest.model_validate(parsed.model_dump()).reminder_id


def _creation_request(value: object) -> ReminderCreateRequest:
    parsed = ReminderCreateRequest.model_validate(value)
    return ReminderCreateRequest.model_validate(parsed.model_dump(mode="json"))


@write_tool(name="update_lia_reminder", agent_name="setting_agent")
async def update_lia_reminder_tool(
    selection: ReminderUpdateRequest,
    runtime: ToolRuntimeArg = None,
) -> UnifiedToolOutput:
    """Prepare a full before/after reminder edit for human confirmation.

    Args:
        selection: Owned reminder id and sparse content or schedule changes.
        runtime: Injected authenticated account context.

    Returns:
        A pending edit preview; no reminder is changed before confirmation.
    """
    return await application_action(
        selection,
        runtime,
        name="update_lia_reminder_tool",
        validate=_sparse_change,
        prepare=prepare_reminder_update,
        refusals=REMINDER_UPDATE_REFUSALS,
        sessions=get_db_context,
    )


async def _prepare_removal(
    db: AsyncSession, actor_id: UUID, selection: UUID | str
) -> ApplicationActionDraftContent:
    """Resolve a legacy reference only now, then approve an exact owned snapshot."""
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if isinstance(selection, UUID):
        identity = selection
    else:
        identity = (await ReminderService(db).resolve_reminder(actor_id, selection)).id
    return await prepare_reminder_removal(db, actor_id, ReminderDeleteRequest(reminder_id=identity))


async def reminder_removal(
    selection: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    *,
    name: str,
    validate: Callable[[object], UUID | str],
    language: str | None = None,
) -> UnifiedToolOutput:
    """Both deletion entries — an owned id or a legacy reference — through the door."""
    return await application_action(
        selection,
        runtime,
        name=name,
        validate=validate,
        prepare=_prepare_removal,
        refusals=REMINDER_REMOVAL_REFUSALS,
        sessions=get_db_context,
        language=language,
    )


@write_tool(name="delete_lia_reminder", agent_name="setting_agent")
async def delete_lia_reminder_tool(
    selection: ReminderDeleteRequest,
    runtime: ToolRuntimeArg = None,
) -> UnifiedToolOutput:
    """Prepare deletion of one exact pending reminder for human approval.

    Args:
        selection: One owned reminder id, with no supplied comparison or account.
        runtime: Injected authenticated account context.

    Returns:
        Pending deletion confirmation; this tool deletes nothing.
    """
    return await reminder_removal(
        selection, runtime, name="delete_lia_reminder_tool", validate=_removal_target
    )


async def reminder_creation(
    configuration: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    *,
    name: str,
    validate: Callable[[object], ReminderCreateRequest],
    language: str | None = None,
) -> UnifiedToolOutput:
    """Native and legacy temporal parsers share the same door."""
    return await application_action(
        configuration,
        runtime,
        name=name,
        validate=validate,
        prepare=prepare_reminder_creation,
        refusals=REMINDER_CREATION_REFUSALS,
        sessions=get_db_context,
        language=language,
    )


@write_tool(name="create_lia_reminder", agent_name="setting_agent")
async def create_lia_reminder_tool(
    configuration: ReminderCreateRequest,
    runtime: ToolRuntimeArg = None,
) -> UnifiedToolOutput:
    """Prepare reminder creation for exact approval; this tool writes no reminder.

    Args:
        configuration: Content, original wording and one explicit instant or recurrence.
        runtime: Injected authenticated account context.

    Returns:
        A full reminder preview waiting for human confirmation.
    """
    return await reminder_creation(
        configuration, runtime, name="create_lia_reminder_tool", validate=_creation_request
    )
```

The docstrings are unchanged here (the migration changes no behavior); Task 1.5 rewrites them with the flip. `get_lia_reminders_tool` keeps its `runtime: Annotated[...]` signature (or uses `ToolRuntimeArg`, the same type).

- [ ] **Step 3: The two aliases reach the same door**

`reminder_tools.py`, `create_reminder_tool`: change the import line in the body to `from src.domains.agents.tools.application_reminder_tools import reminder_creation`, delete `user_id = parse_user_id(config.user_id)`, and replace `return await reminder_creation_proposal(user_id, request, locale)` with:

```python
        return await reminder_creation(
            request,
            runtime,
            name="create_reminder_tool",
            validate=ReminderCreateRequest.model_validate,
            language=locale,
        )
```

`cancel_reminder_tool`: replace its body after `locale = resolve_language(locale)` with:

```python
    from src.domains.agents.tools.application_reminder_tools import reminder_removal

    config = validate_runtime_config(runtime, "cancel_reminder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    return await reminder_removal(
        reminder_identifier, runtime, name="cancel_reminder_tool", validate=str, language=locale
    )
```

(If `parse_user_id` has no other user in `reminder_tools.py`, drop its import.)

- [ ] **Step 4: Point the recurrence test's capture at the new helper**

In `tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py`, `_capture_created` becomes:

```python
@contextmanager
def _capture_created() -> Iterator[dict[str, Any]]:
    """Capture the configuration handed to the shared door adapter (ADR-347).

    Real PostgreSQL tests prove what the door writes; these units keep the
    established relative and recurring time-parser oracle.
    """
    captured: dict[str, Any] = {}

    async def adapter(
        configuration: object,
        runtime: object,
        *,
        name: str,
        validate: object,
        language: str | None = None,
    ) -> UnifiedToolOutput:
        captured["data"] = configuration
        return UnifiedToolOutput.data_success(
            message="Pending confirmation",
            structured_data={"draft": {"id": str(uuid4()), "type": "application_action"}},
            metadata={"requires_confirmation": True},
        )

    with patch(
        "src.domains.agents.tools.application_reminder_tools.reminder_creation", adapter
    ):
        yield captured
```

- [ ] **Step 5: Run the characterization, the reminder suites and the guards**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_lot1_refusal_characterization.py tests/unit/domains/agents/application/test_application_door_guard.py tests/unit/domains/agents/application/test_confirmation_consistency.py tests/unit/domains/agents/effects/test_effect_labels.py tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py -v` → all PASS.
Run: `task test:backend:integration -- tests/integration/test_application_reminder_creation.py tests/integration/test_application_reminder_update_hitl.py tests/integration/test_application_reminder_update_edit.py tests/integration/test_application_reminder_delete_hitl.py -q` → all PASS, unchanged (still cards: the declarations are `ASK`). Where one of them patches `src.domains.agents.tools.application_reminder_tools.save_command`, point it at `src.domains.agents.application.action_door.save_command` — the only accepted edit.

### Task 1.3: Routines through the door

**Files:**
- Modify: `apps/api/src/domains/agents/tools/application_routine_tools.py` (all but `get_lia_routines_tool` and `public_routine_read`)
- Modify: `apps/api/src/domains/agents/tools/automation_tools.py` (`toggle_scheduled_action_tool` body)
- Modify: `apps/api/src/domains/agents/application/routine_spec.py` (`aliases=("toggle_scheduled_action_tool",)` on `ROUTINE_STATE_OPERATION`)
- Modify: `test_confirmation_consistency.py` (delete the toggle line of `UNSERVED_CAPABILITY_MEMBERS`), `test_application_door_guard.py` (remove `application_routine_tools.py`)

**Interfaces:**
- Produces (in `application_routine_tools`): `toggled_routine_state(routine_id: UUID, enabled: bool | None, runtime, language: str) -> UnifiedToolOutput`, `ROUTINE_STATE_REFUSALS`, `ROUTINE_RUN_REFUSALS`, `ROUTINE_UPDATE_REFUSALS`, `ROUTINE_REMOVAL_REFUSALS`, `ROUTINE_CREATION_REFUSALS`. `routine_state_proposal` is deleted.

- [ ] **Step 1: Rewrite the routine actions on the door**

Above `get_lia_routines_tool`, the module becomes (imports: add `from collections.abc import Callable`, `from typing import Literal`, `from pydantic import BaseModel, ConfigDict`, `from sqlalchemy.ext.asyncio import AsyncSession`, `ApplicationActionDraftContent`, `application_action`, `Refusals`, `refused`; drop `save_command`, `DraftType`, `DraftService`):

```python
ToolRuntimeArg = Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg]


class _RoutineTarget(BaseModel):
    """A routine and the state asked for; None inverts the observed state (legacy toggle)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_id: UUID
    enabled: bool | None = None


ROUTINE_STATE_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, message="Invalid desired routine state.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Routine proposal unavailable.",
            code=application_access_error_code,
        ),
        refused(ResourceNotFoundError, message="Routine unavailable.", code="NOT_FOUND"),
        refused(SQLAlchemyError, message="Routine proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            ValidationError, ValueError, message="Invalid routine configuration.", code="INVALID_INPUT"
        ),
    ),
)
ROUTINE_RUN_REFUSALS = Refusals(
    invalid_input=refused(ValueError, message="Invalid routine configuration.", code="INVALID_INPUT"),
    preparation=(
        refused(
            AuthorizationError, message="Routine access refused.", code=application_access_error_code
        ),
        refused(ResourceNotFoundError, message="Routine unavailable.", code="NOT_FOUND"),
        refused(
            ResourceConflictError, message="Routine is already executing.", code="ALREADY_EXECUTING"
        ),
        refused(SQLAlchemyError, message="Routine proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(ValueError, message="Invalid routine configuration.", code="INVALID_INPUT"),
    ),
)
ROUTINE_UPDATE_REFUSALS = Refusals(
    invalid_input=refused(
        DomainValidationError,
        ValueError,
        message="Invalid routine schedule or configuration.",
        code="INVALID_INPUT",
    ),
    preparation=(
        refused(
            AuthorizationError, message="Routine access refused.", code=application_access_error_code
        ),
        refused(ResourceNotFoundError, message="Routine unavailable.", code="NOT_FOUND"),
        refused(SQLAlchemyError, message="Routine proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            DomainValidationError,
            ValueError,
            message="Invalid routine schedule or configuration.",
            code="INVALID_INPUT",
        ),
    ),
)
ROUTINE_REMOVAL_REFUSALS = Refusals(
    invalid_input=refused(ValidationError, message="Invalid routine selection.", code="INVALID_INPUT"),
    preparation=(
        refused(
            AuthorizationError, message="Routine access refused.", code=application_access_error_code
        ),
        refused(ResourceNotFoundError, message="Routine unavailable.", code="NOT_FOUND"),
        refused(SQLAlchemyError, message="Routine proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(ValueError, message="Invalid routine state.", code="INVALID_RESPONSE_FORMAT"),
    ),
)
ROUTINE_CREATION_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, message="Invalid routine configuration.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError, message="Routine access refused.", code=application_access_error_code
        ),
        refused(SQLAlchemyError, message="Routine proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            DomainValidationError,
            ValueError,
            message="Invalid routine schedule or configuration.",
            code="INVALID_INPUT",
        ),
    ),
)


def _validated[Request: BaseModel](
    model: type[Request],
    *,
    exclude_unset: bool = False,
    mode: Literal["python", "json"] = "python",
) -> Callable[[object], Request]:
    """Each routine tool's own round trip through its input model."""

    def validate(value: object) -> Request:
        parsed = model.model_validate(value)
        return model.model_validate(parsed.model_dump(mode=mode, exclude_unset=exclude_unset))

    return validate


async def _prepare_state(
    db: AsyncSession, actor_id: UUID, target: _RoutineTarget
) -> ApplicationActionDraftContent:
    """Legacy toggle resolves its desired state once; neither caller makes a write."""
    await require_application_tools(db)
    enabled = target.enabled
    if enabled is None:
        row = await ScheduledActionService(db).get_with_ownership_check(target.routine_id, actor_id)
        enabled = not row.is_enabled
    return await prepare_routine_state(
        db, actor_id, RoutineStateRequest(routine_id=target.routine_id, enabled=enabled)
    )


def _desired_state(value: object) -> _RoutineTarget:
    request = _validated(RoutineStateRequest)(value)
    return _RoutineTarget(routine_id=request.routine_id, enabled=request.enabled)


async def toggled_routine_state(
    routine_id: UUID,
    enabled: bool | None,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    language: str,
) -> UnifiedToolOutput:
    """The legacy toggle: an explicit desired state, or the observed one inverted."""
    return await application_action(
        _RoutineTarget(routine_id=routine_id, enabled=enabled),
        runtime,
        name="toggle_scheduled_action_tool",
        validate=_RoutineTarget.model_validate,
        prepare=_prepare_state,
        refusals=ROUTINE_STATE_REFUSALS,
        sessions=get_db_context,
        language=language,
    )
```

and each `@write_tool` body becomes one door call (docstrings unchanged):

```python
    # execute_lia_routine_tool
    return await application_action(
        selection,
        runtime,
        name="execute_lia_routine_tool",
        validate=_validated(RoutineRunRequest),
        prepare=prepare_routine_launch,
        refusals=ROUTINE_RUN_REFUSALS,
        sessions=get_db_context,
    )

    # update_lia_routine_tool
    return await application_action(
        change,
        runtime,
        name="update_lia_routine_tool",
        validate=_validated(RoutineUpdateRequest, exclude_unset=True, mode="json"),
        prepare=prepare_routine_update,
        refusals=ROUTINE_UPDATE_REFUSALS,
        sessions=get_db_context,
    )

    # delete_lia_routine_tool
    return await application_action(
        selection,
        runtime,
        name="delete_lia_routine_tool",
        validate=_validated(RoutineDeleteRequest),
        prepare=prepare_routine_removal,
        refusals=ROUTINE_REMOVAL_REFUSALS,
        sessions=get_db_context,
    )

    # create_lia_routine_tool
    return await application_action(
        configuration,
        runtime,
        name="create_lia_routine_tool",
        validate=_validated(RoutineCreateRequest, mode="json"),
        prepare=prepare_routine_creation,
        refusals=ROUTINE_CREATION_REFUSALS,
        sessions=get_db_context,
    )

    # set_lia_routine_state_tool
    return await application_action(
        change,
        runtime,
        name="set_lia_routine_state_tool",
        validate=_desired_state,
        prepare=_prepare_state,
        refusals=ROUTINE_STATE_REFUSALS,
        sessions=get_db_context,
    )
```

(`Literal` is imported from `typing` beside `Annotated`.)

- [ ] **Step 2: The toggle alias reaches the same door**

`automation_tools.py`, `toggle_scheduled_action_tool`: replace its last two lines with

```python
    from src.domains.agents.tools.application_routine_tools import toggled_routine_state

    return await toggled_routine_state(target, None, runtime, locale or resolve_language())
```

and delete `user_id = parse_user_id(config.user_id)` if nothing else reads it.

- [ ] **Step 3: Run the characterization and the routine suites**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_lot1_refusal_characterization.py tests/unit/domains/agents/application/test_routine_state_contract.py tests/unit/domains/agents/application/test_application_door_guard.py tests/unit/domains/agents/application/test_confirmation_consistency.py -v` → all PASS.
Run: `task test:backend:integration -- tests/integration/test_application_routine_state.py tests/integration/test_application_routine_creation.py tests/integration/test_application_routine_update.py tests/integration/test_application_routine_removal.py tests/integration/test_application_routine_execution.py -q` → all PASS, unchanged (the only accepted edit: a `save_command` patch target moved to `action_door`).

### Task 1.4: A reminder survives the minute a model writes

**Files:**
- Modify: `apps/api/src/core/constants.py` (`REMINDER_PAST_INSTANT_GRACE_SECONDS`)
- Create: `apps/api/src/domains/agents/application/reminder_instants.py`
- Modify: `apps/api/src/domains/agents/application/reminder_creation.py:42-43,87,121`, `reminder_update.py:60-61,107`, `reminder_operations.py:87`
- Modify: `apps/api/src/domains/agents/tools/application_reminder_tools.py` (one refusal entry in two tables)
- Modify: `apps/api/src/domains/agents/tools/reminder_tools.py` (`repeat='once'` repair)
- Modify: `apps/api/src/core/i18n_api_messages.py` (`reminder_trigger_params_conflict`, `reminder_trigger_params_missing`)
- Modify: `apps/api/src/domains/agents/application/result_projection.py` (`_reminder_values`)
- Test: `apps/api/tests/unit/domains/agents/application/test_reminder_instants.py` (new)
- Test: `apps/api/tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py` (two cases appended)

**Interfaces:**
- Produces: `instant_still_accepted(trigger_at: datetime, now: datetime) -> bool`, `ReminderInstantPassed(now: datetime, timezone: str)` (a `ValueError`) with `.local_now: str`, `.timezone: str` (in `application.reminder_instants`).

- [ ] **Step 1: Write the failing tests**

`test_reminder_instants.py`:

```python
"""A reminder instant written to the minute is never refused for the seconds it lost (ADR-347)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, REMINDER_PAST_INSTANT_GRACE_SECONDS
from src.domains.agents.application.reminder_instants import (
    ReminderInstantPassed,
    instant_still_accepted,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 15, 6, 7, 2, tzinfo=UTC)


def test_an_instant_within_the_grace_is_accepted() -> None:
    assert instant_still_accepted(_NOW - timedelta(seconds=2), _NOW)
    assert instant_still_accepted(
        _NOW - timedelta(seconds=REMINDER_PAST_INSTANT_GRACE_SECONDS - 1), _NOW
    )


def test_an_instant_past_the_grace_is_refused() -> None:
    assert not instant_still_accepted(
        _NOW - timedelta(seconds=REMINDER_PAST_INSTANT_GRACE_SECONDS), _NOW
    )


def test_a_future_instant_is_accepted() -> None:
    assert instant_still_accepted(_NOW + timedelta(minutes=1), _NOW)


def test_the_refusal_carries_the_local_time() -> None:
    error = ReminderInstantPassed(_NOW, DEFAULT_USER_DISPLAY_TIMEZONE)
    assert isinstance(error, ValueError)
    assert error.timezone == DEFAULT_USER_DISPLAY_TIMEZONE
    assert error.local_now.startswith("2026-10-15T")
```

Append to `test_reminder_tool_recurrence.py` (its `_runtime` fixture and `_capture_created` helper, Task 1.2), adding `from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE` to its imports:

```python
class TestRepeatOnceBesideAnInstant:
    """ADR-347: `repeat='once'` beside `trigger_datetime` is one way of saying when."""

    @pytest.mark.asyncio
    async def test_it_is_the_same_single_firing(self, _runtime: MagicMock) -> None:
        coroutine = create_reminder_tool.coroutine
        assert coroutine is not None
        with _capture_created() as created:
            result = await coroutine(
                content="chanter",
                original_message="rappelle-moi de chanter dans une minute",
                runtime=_runtime,
                trigger_datetime="2099-01-15T09:00:00",
                repeat="once",
                user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
                locale="fr",
            )
        assert result.success is True
        assert created["data"].recurrence is None

    @pytest.mark.asyncio
    async def test_with_a_schedule_field_it_stays_a_conflict(self, _runtime: MagicMock) -> None:
        coroutine = create_reminder_tool.coroutine
        assert coroutine is not None
        with _capture_created() as created:
            result = await coroutine(
                content="chanter",
                original_message="x",
                runtime=_runtime,
                trigger_datetime="2099-01-15T09:00:00",
                repeat="once",
                times=["09:00"],
                user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
                locale="fr",
            )
        assert result.error_code == "invalid_parameters"
        assert "data" not in created
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_reminder_instants.py tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py -v`
Expected: FAIL — `ImportError: cannot import name 'REMINDER_PAST_INSTANT_GRACE_SECONDS'`, and the `repeat='once'` case answers `invalid_parameters`.

- [ ] **Step 3: The grace rule, one implementation**

`constants.py`, beside the other reminder constants:

```python
# ADR-347: a single reminder instant at most this far in the past is still
# accepted and fires at the reminder sweep's next pass (every minute). One
# minute is the precision of the clock a model writes (HH:MM): « in one minute »
# rounded down lands a few seconds behind. Structural, not tunable.
REMINDER_PAST_INSTANT_GRACE_SECONDS: int = 60
```

`apps/api/src/domains/agents/application/reminder_instants.py`:

```python
"""When a reminder instant is still acceptable, said once (ADR-347)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.constants import REMINDER_PAST_INSTANT_GRACE_SECONDS


def instant_still_accepted(trigger_at: datetime, now: datetime) -> bool:
    """Whether a single instant may still be armed: future, or within the grace.

    Args:
        trigger_at: The aware instant asked for.
        now: The aware current instant.

    Returns:
        True when the instant is later than ``now`` minus the grace.
    """
    return trigger_at > now - timedelta(seconds=REMINDER_PAST_INSTANT_GRACE_SECONDS)


class ReminderInstantPassed(ValueError):
    """The instant asked for is older than the grace; the model is told the time it is."""

    def __init__(self, now: datetime, timezone: str) -> None:
        self.timezone = timezone
        self.local_now = now.astimezone(ZoneInfo(timezone)).replace(microsecond=0).isoformat()
        super().__init__("A reminder instant has already passed")
```

Use it everywhere a reminder instant is judged:

- `reminder_creation.py:42-43`:
  ```python
      now = datetime.now(UTC)
      if not instant_still_accepted(arming.trigger_at, now):
          raise ReminderInstantPassed(now, timezone)
  ```
- `reminder_creation.py:87`: `if arming.trigger_at != proposal.trigger_at or not instant_still_accepted(arming.trigger_at, datetime.now(UTC)):`
- `reminder_creation.py:121`: `if not instant_still_accepted(proposal.trigger_at, now):`
- `reminder_update.py:60-61`:
  ```python
      now = datetime.now(UTC)
      if validated.changes.changes_schedule and not instant_still_accepted(
          configuration.trigger_at, now
      ):
          raise ReminderInstantPassed(now, timezone)
  ```
- `reminder_update.py:107`: `if desired.changes.changes_schedule and not instant_still_accepted(actual.trigger_at, datetime.now(UTC)):`
- `reminder_operations.py:87`: `if future_trigger_at is not None and not instant_still_accepted(future_trigger_at, now):`

- [ ] **Step 4: The refusal says what time it is**

In `application_reminder_tools.py`, add `from src.domains.agents.application.reminder_instants import ReminderInstantPassed` and:

```python
def _passed_instant(error: ReminderInstantPassed) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(
        message=(
            f"The reminder time has already passed: it is now {error.local_now} for the person "
            f"({error.timezone}). Recompute the instant from that time and call again; ask the "
            "person only if their time is ambiguous."
        ),
        error_code="INVALID_INPUT",
    )
```

and insert `Refusal((ReminderInstantPassed,), _passed_instant),` as the FIRST entry of `REMINDER_CREATION_REFUSALS.preparation` and of `REMINDER_UPDATE_REFUSALS.preparation` (it subclasses `ValueError`, so it must precede the generic entry; import `Refusal`).

- [ ] **Step 5: `repeat='once'` beside an instant is one way of saying when**

In `create_reminder_tool`, directly before `ways = [...]`:

```python
        # ADR-347: `repeat='once'` beside `trigger_datetime` is the same single
        # firing said twice. Drop the redundant word before judging the ways — a
        # mechanical repair (ADR-184); any other combination stays a conflict.
        schedule_fields = (
            times, weekdays, month_days, months, nth_weekday, every_minutes,
            window_start, window_end, until_date, max_occurrences, starting_on,
        )
        if (
            repeat == "once"
            and trigger_datetime
            and repeat_every == 1
            and all(value is None for value in schedule_fields)
        ):
            repeat = None
```

- [ ] **Step 6: The conflict and missing messages name the three ways**

Replace the two dictionaries in `i18n_api_messages.py` (docstrings become « More than one way of saying when. » and « No way of saying when. »):

```python
        messages = {
            "fr": "Indique le moment d'une seule façon : trigger_datetime (une seule fois), repeat et ses champs de planification (récurrent) ou relative_trigger (FOR_EACH).",
            "en": "Say when in one way only: trigger_datetime (a single firing), repeat with its schedule fields (a series), or relative_trigger (FOR_EACH).",
            "es": "Indica el momento de una sola forma: trigger_datetime (una sola vez), repeat con sus campos de programación (una serie) o relative_trigger (FOR_EACH).",
            "de": "Gib den Zeitpunkt nur auf eine Weise an: trigger_datetime (einmalig), repeat mit seinen Planungsfeldern (eine Serie) oder relative_trigger (FOR_EACH).",
            "it": "Indica il momento in un solo modo: trigger_datetime (una sola volta), repeat con i suoi campi di pianificazione (una serie) o relative_trigger (FOR_EACH).",
            "zh-CN": "只能用一种方式指定时间：trigger_datetime（单次）、repeat 及其日程字段（重复）或 relative_trigger（FOR_EACH）。",
        }
```

```python
        messages = {
            "fr": "Indique le moment : trigger_datetime (une seule fois), repeat et ses champs de planification (récurrent) ou relative_trigger (FOR_EACH).",
            "en": "Say when: trigger_datetime (a single firing), repeat with its schedule fields (a series), or relative_trigger (FOR_EACH).",
            "es": "Indica el momento: trigger_datetime (una sola vez), repeat con sus campos de programación (una serie) o relative_trigger (FOR_EACH).",
            "de": "Gib den Zeitpunkt an: trigger_datetime (einmalig), repeat mit seinen Planungsfeldern (eine Serie) oder relative_trigger (FOR_EACH).",
            "it": "Indica il momento: trigger_datetime (una sola volta), repeat con i suoi campi di pianificazione (una serie) o relative_trigger (FOR_EACH).",
            "zh-CN": "请指定时间：trigger_datetime（单次）、repeat 及其日程字段（重复）或 relative_trigger（FOR_EACH）。",
        }
```

(In both French strings the space before « : » is a no-break space, U+00A0.)

- [ ] **Step 7: The result reads in the person's time**

In `result_projection.py`, add the imports `from src.core.i18n import resolve_language`, `from src.core.recurrence import describe`, `from src.core.time_utils import format_datetime_for_display`, and:

```python
def _readable_schedule(
    trigger_at: datetime, timezone: str, recurrence: RecurrenceSpec
) -> dict[str, JsonValue]:
    """The armed instant in the person's own clock, and a series in words (ADR-347)."""
    language = resolve_language()
    values: dict[str, JsonValue] = {
        "trigger_at_local": format_datetime_for_display(
            trigger_at, user_timezone=timezone, locale=language
        )
    }
    if recurrence.freq != "once":
        values["schedule"] = describe(recurrence, language)
    return values
```

then in `_reminder_values`: the `reminder.update` branch returns `{..., **_readable_schedule(edited_reminder.configuration.trigger_at, edited_reminder.configuration.user_timezone, edited_reminder.configuration.recurrence)}`, and the `reminder.create` branch adds `**_readable_schedule(reminder.trigger_at, reminder.user_timezone, reminder.recurrence)`. (Import `datetime` and `RecurrenceSpec`.)

- [ ] **Step 8: Run the reminder suites**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_reminder_instants.py tests/unit/domains/agents/tools/test_reminder_tool_recurrence.py tests/unit/domains/agents/application/test_reminder_creation_contract.py tests/unit/domains/agents/application/test_reminder_update_contract.py tests/unit/domains/agents/application/test_reminder_result_budget.py -v` → PASS.
Run: `task test:backend:integration -- tests/integration/test_application_reminder_creation.py tests/integration/test_application_reminder_update_hitl.py -q` → PASS. `test_first_trigger_elapsing_during_the_source_write_is_not_committed` must still refuse: if it moves the clock by less than the grace, widen its offset beyond `REMINDER_PAST_INSTANT_GRACE_SECONDS` (read from the constant, never a literal) and note it in the review.

### Task 1.5: Flip — reminders and the routine switch act at once

**Files:**
- Modify: `apps/api/src/domains/agents/application/reminder_spec.py`, `routine_spec.py` (declarations)
- Modify: `apps/api/src/domains/agents/application/reminder_catalogue.py` (`REMINDER_CREATE_MANIFEST`, `REMINDER_UPDATE_MANIFEST`, `REMINDER_DELETE_MANIFEST`), `routine_catalogue.py` (`ROUTINE_STATE_MANIFEST`)
- Modify: `apps/api/src/domains/agents/reminders/catalogue_manifests.py` (`create_reminder_catalogue_manifest`, `cancel_reminder_catalogue_manifest`), `automation/catalogue_manifests.py` (`toggle_scheduled_action_catalogue_manifest`)
- Modify: docstrings of `update_lia_reminder_tool`, `delete_lia_reminder_tool`, `create_lia_reminder_tool`, `set_lia_routine_state_tool`, `create_reminder_tool`, `cancel_reminder_tool`, `toggle_scheduled_action_tool` (+ its `enabled` parameter)
- Modify: `apps/api/src/domains/agents/effects/labels.py` (`APPLICATION_LABELS`), `apps/api/src/core/i18n_effects.py` (`effects.labels.reminder_update`, six languages), `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (`effects.labels.reminder_update`; four progress labels)
- Modify (tests whose expectation is the old « asks »): listed in Step 7
- Test: `apps/api/tests/unit/domains/agents/application/test_lot1_flip.py` (new); `tests/helpers/application_card_path.py` (new)

- [ ] **Step 1: Write the failing flip tests**

`apps/api/tests/helpers/application_card_path.py`:

```python
"""Exercise a direct operation's card path, kept complete for the day it flips back (ADR-347 §4.7)."""

import pytest


@pytest.fixture
def card_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every call of every operation asks, for the duration of one test."""
    from src.domains.agents.application import action_door

    monkeypatch.setattr(action_door, "requires_confirmation", lambda spec, intent: True)
```

`test_lot1_flip.py`:

```python
"""Reminders and the routine switch act at once, labelled by their operation (ADR-347)."""

import pytest

from src.domains.agents.application.confirmation_policy import implied_manifest_policy
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.labels import build_effect_label

pytestmark = pytest.mark.unit

FLIPPED = ("reminder.create", "reminder.update", "reminder.delete", "routine_state.update")


@pytest.mark.parametrize("operation", FLIPPED)
def test_the_operation_acts_at_once_with_a_written_reason(operation: str) -> None:
    spec = APPLICATION_OPERATIONS.get(operation)
    assert implied_manifest_policy(spec) == "reversible"
    assert spec.confirmation.reason


@pytest.mark.parametrize(
    ("alias", "operation"),
    [
        ("create_reminder_tool", "reminder.create"),
        ("cancel_reminder_tool", "reminder.delete"),
        ("toggle_scheduled_action_tool", "routine_state.update"),
    ],
)
def test_each_alias_serves_its_operation(alias: str, operation: str) -> None:
    resolved = APPLICATION_OPERATIONS.get_by_tool_name(alias)
    assert resolved is not None and resolved.operation_id == operation


@pytest.mark.parametrize(
    ("operation", "intent", "key", "target"),
    [
        (
            "reminder.create",
            {"reminder_to_create": {"configuration": {"content": "Chanter"}}},
            "effects.labels.create_reminder_tool",
            "Chanter",
        ),
        (
            "reminder.update",
            {"reminder_configuration": {"configuration": {"content": "Danser"}}},
            "effects.labels.reminder_update",
            "Danser",
        ),
        (
            "reminder.delete",
            {"reminder_to_delete": {"content": "Chanter"}},
            "effects.labels.draft.reminder_delete",
            "Chanter",
        ),
        (
            "routine_state.update",
            {"routine_state": {"expected": {"title": "Météo"}}},
            "effects.labels.toggle_scheduled_action_tool",
            "Météo",
        ),
    ],
)
def test_one_act_one_label_whichever_tool(
    operation: str, intent: dict[str, object], key: str, target: str
) -> None:
    content = {"operation_id": operation, "title": "Any", "intent": intent}
    label = build_effect_label("draft:application_action", {"draft": content})
    assert label == {"i18n_key": key, "values": {"target": target}}


def test_a_direct_act_through_an_alias_is_not_read_as_pending() -> None:
    from src.core.context import request_tool_manifests_ctx
    from src.domains.agents.registry.semantic_inventory import collect_static_manifests
    from src.domains.agents.services.outcome_evidence import observe_requested_outcome

    raw = {
        "success": True,
        "structured_data": {
            "application_result": {
                "success": True,
                "phase": "committed",
                "committed": True,
                "values": {"content": "Chanter", "deleted": True},
            }
        },
    }
    token = request_tool_manifests_ctx.set(collect_static_manifests())
    try:
        observed = observe_requested_outcome("cancel_reminder_tool", {}, raw)
    finally:
        request_tool_manifests_ctx.reset(token)
    assert observed is not None and observed["pending_confirmation"] is False
```

In `test_confirmation_policy.py`, add the four operations to `DIRECT_OPERATIONS`.

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_lot1_flip.py tests/unit/domains/agents/application/test_confirmation_policy.py -v`
Expected: FAIL — the four operations still `ASK`, no `APPLICATION_LABELS` entry.

- [ ] **Step 3: The declarations**

`reminder_spec.py` (import `direct` from `operation_spec`):

```python
REMINDER_UPDATE_OPERATION = ApplicationOperationSpec(
    ...,
    confirmation=direct(
        "Modifying a reminder is not critical and is changed back the same way "
        "(owner decision, 2026-10-15)."
    ),
)
REMINDER_DELETE_OPERATION = ApplicationOperationSpec(
    ...,
    confirmation=direct(
        "Deleting a reminder is not critical (owner decision, 2026-10-15, superseding "
        "ADR-268's « the deletion is the step that asks »); a delivered notification "
        "is never recalled."
    ),
    aliases=("cancel_reminder_tool",),
)
REMINDER_CREATE_OPERATION = ApplicationOperationSpec(
    ...,
    confirmation=direct(
        "Creating a reminder is anodyne and undone by deleting it (owner decision, "
        "ADR-268, reaffirmed 2026-10-15)."
    ),
    aliases=("create_reminder_tool",),
)
```

`routine_spec.py`: `ROUTINE_STATE_OPERATION` gains `confirmation=direct("Pausing or resuming a routine is undone by one call (owner decision, 2026-10-15)."),` beside its alias.

- [ ] **Step 4: What the model reads — manifests and docstrings**

Each of the seven manifests: `mutation_policy="reversible"`, `mutation_policy_reason=<ITS OPERATION>.confirmation.reason` (import the spec constant), its `outputs` reduced to `[OutputFieldSchema(path="application_result", type="object", description="The act's outcome and its public values, or the refusal")]`, and its description:

- `REMINDER_CREATE_MANIFEST`: "Create an owned reminder at once with its full content and either one explicit ISO datetime or a complete recurrence. Never supply both. The application resolves the account timezone and the first UTC trigger; an instant up to one minute past fires at the next pass, an older one is refused with the current local time. Recurrence follows existing reminder limits. Original message is the user's reminder wording; never invent private metadata. Returns the reminder with its local time and, for a series, its schedule in words. Once its last occurrence fires, the reminder is deleted rather than stored as history."
- `REMINDER_UPDATE_MANIFEST`: "Change an owned pending reminder's content, single instant or complete recurrence at once. Omitted fields remain unchanged. Never send null or both clocks. A repeating reminder moves through its recurrence, not a one-time trigger. Content-only changes preserve the stored timezone and schedule; a moved instant up to one minute past fires at the next pass. Returns the changed reminder; future notifications retain existing LLM cost and quota accounting."
- `REMINDER_DELETE_MANIFEST`: "Delete one owned pending reminder at once, including all remaining occurrences of a recurring reminder. A processing reminder is busy; a fired or removed reminder is unavailable. Never re-resolve a natural reference. Returns the deleted reminder's content. A notification already delivered is never recalled."
- `ROUTINE_STATE_MANIFEST`: "Pause or enable one owned routine at once. Read its id first. Set enabled explicitly; repeated enable requests never toggle it off. Pausing stops future triggers and lets an already running execution finish. Enabling resets the source clock and error state, while preserving a running execution reservation."
- `create_reminder_catalogue_manifest`: "Creates a reminder for the user at once. The reminder will be sent as a push notification (FCM) and recorded in conversation history at the scheduled time. Use trigger_datetime for fixed times, or relative_trigger for FOR_EACH (e.g., 'day before each event at 19:00')." — its comment becomes `# Compatibility temporal parsing reaches the same door as create_lia_reminder_tool (ADR-347).`
- `cancel_reminder_catalogue_manifest`: "Deletes a pending reminder and all remaining occurrences at once. Can identify reminder by direct UUID or natural reference ('next', 'the next one')." — its permissions comment becomes `# Direct (ADR-347): the act is recorded by its door; hitl_required stays False.`
- `toggle_scheduled_action_catalogue_manifest`: "Pauses or resumes an existing automation at once. Requires the automation id from list_scheduled_actions_tool. Pass enabled for the state you want (a repeated call then changes nothing); without it the observed state is inverted. Prefer set_lia_routine_state_tool for an explicit desired state." — plus a parameter `ParameterSchema(name="enabled", type="boolean", required=False, description="Desired state: true resumes, false pauses; omitted inverts the observed state")`, and its permissions comment `# Direct (ADR-347).`

Docstrings (the ReAct schema's description), first paragraph and `Returns:`:

- `update_lia_reminder_tool`: « Change an owned reminder's content or schedule at once. » / Returns « The changed reminder, or the refusal. »
- `delete_lia_reminder_tool`: « Delete one exact pending reminder at once. » / « The deleted reminder's content, or the refusal. »
- `create_lia_reminder_tool`: « Create an owned reminder at once. » / « The created reminder with its local time, or the refusal. »
- `set_lia_routine_state_tool`: « Pause or enable a routine by its owned id, at once. » / « The routine's new state. Pausing leaves an ongoing run to finish. »
- `create_reminder_tool`: keep its text; `Returns:` becomes « The created reminder, or a failure the model can relay. »
- `cancel_reminder_tool`: « Cancel a pending reminder and its remaining occurrences, at once. Identifies the reminder by its UUID or a natural reference ('next'). » / « The deleted reminder's content, or the refusal. »
- `toggle_scheduled_action_tool`: « Pause or resume a routine at once: the state passed, or the observed one inverted. » with `enabled` documented in `Args:` / « The routine's new state. »

`toggle_scheduled_action_tool` gains the parameter `enabled: Annotated[bool | None, "Desired state: true resumes, false pauses; omitted inverts the observed state"] = None` (before `user_timezone`) and passes it: `toggled_routine_state(target, enabled, runtime, locale or resolve_language())`.

- [ ] **Step 5: The register names the object, in six languages**

`labels.py`:

```python
APPLICATION_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {
    "reminder.create": (
        "effects.labels.create_reminder_tool",
        ("reminder_to_create", "configuration", "content"),
    ),
    "reminder.update": (
        "effects.labels.reminder_update",
        ("reminder_configuration", "configuration", "content"),
    ),
    "reminder.delete": ("effects.labels.draft.reminder_delete", ("reminder_to_delete", "content")),
    "routine_state.update": (
        "effects.labels.toggle_scheduled_action_tool",
        ("routine_state", "expected", "title"),
    ),
}
```

`core/i18n_effects.py`, after each language's `"effects.labels.create_reminder_tool"` line:

- fr `"effects.labels.reminder_update": "Rappel « {target} » modifié",` (no-break spaces inside the guillemets, as the neighbouring line)
- en `"effects.labels.reminder_update": "Changed the reminder “{target}”",`
- de `"effects.labels.reminder_update": "Erinnerung „{target}“ geändert",`
- es `"effects.labels.reminder_update": "Recordatorio «{target}» modificado",`
- it `"effects.labels.reminder_update": "Promemoria «{target}» modificato",`
- zh-CN `"effects.labels.reminder_update": "已修改提醒「{target}」",`

`apps/web/locales/*/translation.json`, in `effects.labels` after `"create_reminder_tool"`: the same six wordings with `{{target}}`.

Progress labels (same files, the `…steps` object): replace the four values —

| key | en | fr | de | es | it | zh |
|---|---|---|---|---|---|---|
| `create_lia_reminder` | Creating the reminder... | Création du rappel... | Erinnerung wird erstellt... | Creando el recordatorio... | Creazione del promemoria... | 正在创建提醒... |
| `update_lia_reminder` | Updating the reminder... | Modification du rappel... | Erinnerung wird geändert... | Modificando el recordatorio... | Modifica del promemoria... | 正在修改提醒... |
| `delete_lia_reminder` | Deleting the reminder... | Suppression du rappel... | Erinnerung wird gelöscht... | Eliminando el recordatorio... | Eliminazione del promemoria... | 正在删除提醒... |
| `set_lia_routine_state` | Changing the routine state... | Changement d’état de l’automatisation... | Routinenstatus wird geändert... | Cambiando el estado de la automatización... | Modifica dello stato dell’automazione... | 正在更改自动任务状态... |

- [ ] **Step 6: Run the flip tests and the declaration guards**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_lot1_flip.py tests/unit/domains/agents/application/test_confirmation_policy.py tests/unit/domains/agents/application/test_confirmation_consistency.py tests/unit/domains/agents/effects/test_effect_labels.py -v` → PASS (including the guard « a tool that never asks promises no confirmation » and the translation tests).
Run (repo root): `task lint:i18n` → PASS.

- [ ] **Step 7: Re-point the tests that pinned « reminders ask »**

Run: `.venv/Scripts/pytest tests/unit -q -x -p no:randomly` and `task test:backend:agents`, then the integration files below. For every failure, apply ONLY the matching rule; any other failure is a defect to fix in the code:

- A test that obtains a reminder or routine-state CARD from the tool, then confirms it (`test_application_reminder_creation.py::test_native_creation_requires_exact_hitl_and_commits_once`, `…_reminder_creation_edit_replaces_the_approval…`, `…_first_trigger_elapsing…`, `…_reminder_creation_refuses_changed_authority`, `…_recurrence_crossing…`; `test_application_reminder_update_hitl.py`; `test_application_reminder_update_edit.py`; `test_application_reminder_delete_hitl.py::test_native_deletion_requires_exact_hitl…`; `test_application_routine_state.py::test_real_routine_tool_requires_exact_hitl…`, `…_routine_editor_replaces…`): add the `card_path` fixture (`from tests.helpers.application_card_path import card_path`, then the parameter). These now pin the card path §4.7 keeps complete.
- A test asserting that an entry « is a proposal » (`test_all_creation_entries_are_proposals_and_obey_the_global_switch`, `test_both_deletion_entries_are_proposals_and_obey_the_switch`, `test_native_reminder_creation_is_proposal_only…`): rename it `…_act_at_once_and_obey_the_switch` and assert the act (row created or deleted, `result.metadata.get("requires_confirmation")` falsy, `application_result.committed`), keeping the switch-off branch (`CAPABILITY_DISABLED`, nothing written) unchanged.
- `tests/unit/domains/agents/registry/test_mutation_policy.py`: the toggle tool's expected policy is `reversible`.
- `tests/unit/domains/agents/application/test_routine_state_contract.py`, `tests/agents/orchestration/test_for_each_hitl_count.py`, `tests/agents/orchestration/test_semantic_validator.py`, `tests/unit/domains/agents/semantic/test_application_committed_outcome.py`, `test_delegated_outcome_evidence.py`: where an expectation reads the four tools as `draft`/pending, it reads `reversible`/acted; the FOR_EACH confirmation count of `test_for_each_hitl_count.py` is unchanged (it is decided by the tool's category, `tool_is_mutation`).

List every file edited under this step in the lot's review notes.

### Task 1.6: The direct acts, proven on PostgreSQL

**Files:**
- Test: `apps/api/tests/integration/test_application_direct_reminders_and_routines.py` (new)

- [ ] **Step 1: Write the tests**

```python
"""Reminders and the routine switch act at once, recorded once, replays served (ADR-347)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, REMINDER_PAST_INSTANT_GRACE_SECONDS
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.runtime import gated
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.tools.application_reminder_tools import create_lia_reminder_tool
from src.domains.agents.tools.automation_tools import toggle_scheduled_action_tool
from src.domains.agents.tools.reminder_tools import cancel_reminder_tool
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.fixture
def database(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncSession:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for target in (
        "src.domains.agents.tools.application_reminder_tools.get_db_context",
        "src.domains.agents.tools.application_routine_tools.get_db_context",
        "src.domains.agents.application.direct_execution.get_db_context",
        "src.domains.agents.application.draft_execution.get_db_context",
        "src.infrastructure.database.session.get_db_context",
    ):
        monkeypatch.setattr(target, session)
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    return async_session


def _local_in(test_user: User, delta: timedelta) -> str:
    zone = ZoneInfo(test_user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE)
    return (datetime.now(zone) + delta).replace(tzinfo=None, microsecond=0).isoformat()


async def _effects(db: AsyncSession, user: User) -> list[AgentEffect]:
    return list(
        (await db.execute(select(AgentEffect).where(AgentEffect.user_id == user.id))).scalars()
    )


async def test_a_reminder_is_created_at_once_and_recorded_once(
    database: AsyncSession, test_user: User
) -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    with (
        installed_runtime_context(user_id=test_user.id, language="fr", side_channel_queue=queue),
        effect_scope(EffectScope(run_id="run-direct", idempotency_key="call:create")),
    ):
        result = await create_lia_reminder_tool.coroutine(
            configuration={
                "content": "Chanter",
                "original_message": "rappelle-moi de chanter",
                "trigger_at": _local_in(test_user, timedelta(hours=2)),
            },
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert result.success and not result.metadata.get("requires_confirmation")
    values = result.structured_data["application_result"]["values"]
    assert "trigger_at_local" in values
    assert await database.get(Reminder, UUID(values["reminder_id"])) is not None
    effects = await _effects(database, test_user)
    assert [(e.mutation_policy, e.status.value) for e in effects] == [("reversible", "succeeded")]
    label = EffectLedgerRepository.decrypted_label(effects[0])
    assert label == {"i18n_key": "effects.labels.create_reminder_tool", "values": {"target": "Chanter"}}
    commands = (
        await database.execute(
            select(ApplicationCommand).where(ApplicationCommand.actor_id == test_user.id)
        )
    ).scalars()
    assert list(commands) == []
    assert not queue.empty()


async def test_an_instant_seconds_behind_is_created_not_refused(
    database: AsyncSession, test_user: User
) -> None:
    behind = _local_in(test_user, timedelta(seconds=-(REMINDER_PAST_INSTANT_GRACE_SECONDS // 2)))
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        effect_scope(EffectScope(run_id="run-direct", idempotency_key="call:grace")),
    ):
        result = await create_lia_reminder_tool.coroutine(
            configuration={
                "content": "Chanter",
                "original_message": "rappelle-moi de chanter dans une minute",
                "trigger_at": behind,
            },
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert result.success


async def test_a_replayed_deletion_is_served_from_its_record_not_reprepared(
    database: AsyncSession, test_user: User
) -> None:
    row = await ReminderService(database).create_reminder(
        test_user.id,
        ReminderCreate(
            content="Chanter",
            original_message="x",
            trigger_at=datetime.now(UTC) + timedelta(days=1),
        ),
        "UTC",
    )
    await database.commit()
    tool = gated("cancel_reminder_tool", cancel_reminder_tool.coroutine)
    runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore())
    scope = EffectScope(run_id="run-replay", idempotency_key="call:cancel")
    with installed_runtime_context(user_id=test_user.id, language="fr"), effect_scope(scope):
        first = await tool(reminder_identifier=str(row.id), runtime=runtime)
        second = await tool(reminder_identifier=str(row.id), runtime=runtime)
    assert first.success
    assert await database.get(Reminder, row.id) is None
    assert second["success"] is True, "the replay is served, never answered « not found »"
    assert len(await _effects(database, test_user)) == 1


async def test_a_routine_toggle_with_a_target_is_a_no_op_the_second_time(
    database: AsyncSession, test_user: User
) -> None:
    routine = await ScheduledActionService(database).create(
        test_user.id,
        ScheduledActionCreate(
            title="Météo",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        test_user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
    )
    await database.commit()
    runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore())
    for key in ("call:pause-1", "call:pause-2"):
        with (
            installed_runtime_context(user_id=test_user.id, language="fr"),
            effect_scope(EffectScope(run_id="run-toggle", idempotency_key=key)),
        ):
            result = await toggle_scheduled_action_tool.coroutine(
                action_id=str(routine.id), enabled=False, runtime=runtime, locale="fr"
            )
        assert result.success
    refreshed = await database.get(ScheduledAction, routine.id, populate_existing=True)
    assert refreshed is not None and refreshed.is_enabled is False


async def test_with_the_capability_off_nothing_is_written(
    database: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        effect_scope(EffectScope(run_id="run-off", idempotency_key="call:off")),
    ):
        result = await create_lia_reminder_tool.coroutine(
            configuration={
                "content": "Chanter",
                "original_message": "x",
                "trigger_at": _local_in(test_user, timedelta(hours=2)),
            },
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert result.error_code == "CAPABILITY_DISABLED"
    assert await _effects(database, test_user) == []
```

- [ ] **Step 2: Run them**

Run: `task test:backend:integration -- tests/integration/test_application_direct_reminders_and_routines.py -v`
Expected: all PASS.

### Task 1.7: Lot 1 gates, runtime proof and cold review

- [ ] **Step 1: Gates** — `task lint`; `task test:backend:unit:fast`; `task test:backend:agents`; `task test:backend:integration -- tests/integration/test_application_reminder_creation.py tests/integration/test_application_reminder_update_hitl.py tests/integration/test_application_reminder_update_edit.py tests/integration/test_application_reminder_delete_hitl.py tests/integration/test_application_routine_state.py tests/integration/test_application_routine_creation.py tests/integration/test_application_routine_update.py tests/integration/test_application_routine_removal.py tests/integration/test_application_routine_execution.py tests/integration/test_application_direct_reminders_and_routines.py -q`. All exit 0.
- [ ] **Step 2: Runtime proof, no model call** — restart `lia-api-dev`; check the boot (no completeness error); in the container, on the proof account, call `create_lia_reminder_tool`, `update_lia_reminder_tool`, `delete_lia_reminder_tool`, `create_reminder_tool`, `cancel_reminder_tool`, `set_lia_routine_state_tool`, `toggle_scheduled_action_tool` under `installed_runtime_context` and a fresh `effect_scope` each: every one acts, one `agent_effects` row each with the operation's label, no `application_commands` row; a reminder far in the future is used and deleted again, the routine's state is restored, nothing is left on the account.
- [ ] **Step 3: Cold review** — every file of Tasks 1.1–1.6, line by line; the list of tests re-pointed in Task 1.5 Step 7, each against its rule; and the card scope of a direct deletion (spec §5): `prepare_reminder_removal` captures the selection and `execute_reminder_removal` runs under `reminder_card_scope` in the same call — read both against the door's direct path.

---

## Lot 2 — tickets

### Task 2.1: Characterize ticket creation before touching it

**Files:**
- Test: `apps/api/tests/unit/domains/agents/application/test_ticket_creation_characterization.py` (new)

The success path (card, command, confirmed execution) is pinned by `tests/integration/test_application_workboard_create_flow.py`.

- [ ] **Step 1: Write the characterization (it must pass against TODAY's code)**

```python
"""Every refusal of the ticket creation tool, pinned before its migration (ADR-347)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.tools import workboard_creation_tool, workboard_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncMock]:
    yield AsyncMock()


async def _create(error: BaseException | None, **kwargs: object) -> UnifiedToolOutput:
    with (
        patch.object(workboard_creation_tool, "get_db_context", _session),
        patch.object(workboard_creation_tool, "creation_access", AsyncMock()),
        patch.object(
            workboard_creation_tool, "prepare_workboard_creation", AsyncMock(side_effect=error)
        ),
    ):
        coroutine = workboard_tools.create_ticket_tool.coroutine
        assert coroutine is not None
        result: UnifiedToolOutput = await coroutine(
            **kwargs, runtime=make_tool_runtime(user_id=uuid4(), store=InMemoryStore())
        )
        return result


_REQUEST = {"request": {"title": "Plan the trip"}}


@pytest.mark.parametrize(
    ("error", "message", "code"),
    [
        (
            AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"}),
            "Workboard proposal refused.",
            "CAPABILITY_DISABLED",
        ),
        (
            ResourceNotFoundError("ticket"),
            "Selected parent or assignee unavailable.",
            "NOT_FOUND_OR_UNAUTHORIZED",
        ),
        (SQLAlchemyError(), "Workboard proposal unavailable.", "DEPENDENCY_ERROR"),
        (ValueError("x"), "Invalid Workboard configuration.", "INVALID_INPUT"),
    ],
)
async def test_every_refusal_keeps_its_sentence_and_code(
    error: BaseException, message: str, code: str
) -> None:
    result = await _create(error, **_REQUEST)
    assert (result.message, result.error_code) == (message, code)


async def test_a_source_constraint_names_itself_in_the_metadata() -> None:
    result = await _create(DomainValidationError("workboard_cap_reached"), **_REQUEST)
    assert (result.message, result.error_code) == ("workboard_cap_reached", "CONSTRAINT_VIOLATION")
    assert result.metadata["workboard_error"] == "workboard_cap_reached"


async def test_the_full_request_and_legacy_fields_are_exclusive() -> None:
    result = await _create(None, title="Legacy", **_REQUEST)
    assert (result.message, result.error_code) == (
        "Use the full request or legacy fields, not both.",
        "INVALID_INPUT",
    )
```

- [ ] **Step 2: Run it against today's code**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_ticket_creation_characterization.py -v` → all PASS (a failing row is corrected against the code, never the reverse).

### Task 2.2: Ticket creation through the door

**Files:**
- Modify: `apps/api/src/domains/agents/tools/workboard_creation_tool.py` (whole module)
- Modify: `test_application_door_guard.py` (remove `workboard_creation_tool.py` — the list then holds the 23 modules of part 2)

- [ ] **Step 1: Rewrite the module on the door**

```python
"""Compatibility parsing ends in the same exact native creation, through the door (ADR-347)."""

from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.action_door import application_action
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.refusals import Refusal, Refusals, refused
from src.domains.agents.application.workboard_create import (
    creation_access,
    prepare_workboard_creation,
)
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, validate_runtime_config
from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context


class _CreationAsk(BaseModel):
    """What the call asked: the full request, or the legacy fields — never both.

    Both stay raw JSON here: the full request is validated INSIDE the preparation,
    where today's refusal table reads its failure.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    request: dict[str, JsonValue] | None = None
    legacy: dict[str, JsonValue] = Field(default_factory=dict)


def _source_constraint(error: DomainValidationError) -> UnifiedToolOutput:
    code = str(error.detail)
    return UnifiedToolOutput.failure(
        message=code, error_code="CONSTRAINT_VIOLATION", metadata={"workboard_error": code}
    )


WORKBOARD_CREATION_REFUSALS = Refusals(
    invalid_input=refused(
        ValidationError, ValueError, message="Invalid Workboard configuration.", code="INVALID_INPUT"
    ),
    preparation=(
        refused(
            AuthorizationError,
            message="Workboard proposal refused.",
            code=application_access_error_code,
        ),
        refused(
            ResourceNotFoundError,
            message="Selected parent or assignee unavailable.",
            code="NOT_FOUND_OR_UNAUTHORIZED",
        ),
        Refusal((DomainValidationError,), _source_constraint),
        refused(SQLAlchemyError, message="Workboard proposal unavailable.", code="DEPENDENCY_ERROR"),
        refused(
            ValidationError, ValueError, message="Invalid Workboard configuration.", code="INVALID_INPUT"
        ),
    ),
)


async def _legacy_request(
    db: AsyncSession, owner_id: UUID, zone: str, values: dict[str, object]
) -> WorkboardCreateInput:
    service = WorkboardService(db)
    values = await normalize_workboard_legacy(service, owner_id, zone, values)
    return WorkboardCreateInput.model_validate(values)


async def propose_workboard_creation(
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    request: WorkboardCreateInput | None,
    values: dict[str, object],
) -> UnifiedToolOutput:
    """The creation tool's legacy and full forms, resolved once, through the door."""
    actor = validate_runtime_config(runtime, "create_ticket_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    legacy = {key: value for key, value in values.items() if value is not None}
    if request is not None and legacy:
        return UnifiedToolOutput.failure(
            message="Use the full request or legacy fields, not both.", error_code="INVALID_INPUT"
        )

    async def prepare(
        db: AsyncSession, owner: UUID, asked: _CreationAsk
    ) -> ApplicationActionDraftContent:
        await creation_access(db, owner)
        if asked.request is not None:
            parsed = WorkboardCreateInput.model_validate(asked.request)
            selected = WorkboardCreateInput.model_validate(parsed.model_dump())
        else:
            zone, _, _ = await get_user_preferences(runtime)
            fields: dict[str, object] = {key: value for key, value in asked.legacy.items()}
            selected = await _legacy_request(db, owner, zone, fields)
        return await prepare_workboard_creation(db, owner, selected)

    return await application_action(
        {
            "request": (
                request.model_dump(mode="json") if isinstance(request, BaseModel) else request
            ),
            "legacy": legacy,
        },
        runtime,
        name="create_ticket_tool",
        validate=_CreationAsk.model_validate,
        prepare=prepare,
        refusals=WORKBOARD_CREATION_REFUSALS,
        sessions=get_db_context,
    )
```

- [ ] **Step 2: Run the characterization and the ticket suites**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_ticket_creation_characterization.py tests/unit/domains/agents/tools/test_workboard_tools.py tests/unit/domains/agents/application/test_application_door_guard.py -v` → PASS.
Run: `task test:backend:integration -- tests/integration/test_application_workboard_create_flow.py tests/integration/test_workboard_legacy_read_capabilities.py -q` → PASS, unchanged.

### Task 2.3: Flip — tickets act at once, except a run or an answer

**Files:**
- Modify: `apps/api/src/domains/agents/application/workboard_create_spec.py`, `workboard_update_spec.py`, `workboard_comment_spec.py`
- Modify: `apps/api/src/domains/agents/workboard/creation_manifest.py` (`create_ticket_catalogue_manifest`), `workboard/catalogue_manifests.py` (`update_ticket_catalogue_manifest`, `comment_ticket_catalogue_manifest` descriptions)
- Modify: docstrings of `create_ticket_tool`, `update_ticket_tool`, `comment_ticket_tool` (`tools/workboard_tools.py`)
- Modify: `apps/api/src/domains/agents/effects/labels.py` (three `APPLICATION_LABELS` entries)
- Modify: `test_confirmation_policy.py` (`DIRECT_OPERATIONS` + 3)
- Modify (tests whose expectation is the old « asks »): Step 6
- Test: `apps/api/tests/unit/domains/agents/application/test_ticket_flip.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""Tickets act at once; a run requested or a pending action answered still asks (ADR-347)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domains.agents.application.confirmation_policy import (
    implied_manifest_policy,
    requires_confirmation,
)
from src.domains.agents.application.workboard_comment_schemas import (
    WorkboardCommentInput,
    WorkboardCommentPatch,
    WorkboardCommentSelection,
)
from src.domains.agents.application.workboard_comment_spec import WORKBOARD_COMMENT_OPERATION
from src.domains.agents.application.workboard_create_spec import WORKBOARD_CREATE_OPERATION
from src.domains.agents.application.workboard_update_schemas import (
    WorkboardUpdateInput,
    WorkboardUpdatePatch,
    WorkboardUpdateSelection,
)
from src.domains.agents.application.workboard_update_spec import WORKBOARD_UPDATE_OPERATION
from src.domains.agents.effects.labels import build_effect_label
from src.domains.workboard.answers import Answer

pytestmark = pytest.mark.unit


def _update(*, run_now: bool, answer: Answer | None) -> dict[str, object]:
    selection = WorkboardUpdateSelection(
        request=WorkboardUpdateInput(ticket_id=uuid4(), run_now=run_now),
        before={},
        after={"title": "Plan the trip"},
        pending_preview=[],
        answer_note="ok" if answer else None,
        answer=answer,
        pending_before=answer is not None,
        pending_after=False,
        pending_approved=answer is Answer.APPROVE,
        holder_name=None,
        owner_id=uuid4(),
        requires_peers=False,
        statuses=("todo",),
        events_before=0,
        expected_events=[],
        state_digest="a" * 64,
        result_digest="b" * 64,
    )
    return WorkboardUpdatePatch(workboard_update=selection).model_dump(mode="json")


def _comment(answer: Answer | None) -> dict[str, object]:
    selection = WorkboardCommentSelection(
        request=WorkboardCommentInput(ticket_id=uuid4(), body="Looks good"),
        title="Plan the trip",
        owner_id=uuid4(),
        status="confirming" if answer else "todo",
        assignee_kind="lia",
        holder_id=uuid4(),
        answer=answer,
        pending_preview=[],
        max_comment_chars=1000,
        max_runs=3,
        state_digest="a" * 64,
    )
    return WorkboardCommentPatch(workboard_comment=selection).model_dump(mode="json")


def test_a_ticket_is_created_at_once() -> None:
    assert implied_manifest_policy(WORKBOARD_CREATE_OPERATION) == "reversible"


@pytest.mark.parametrize(
    ("run_now", "answer", "asks"),
    [
        (False, None, False),
        (True, None, True),
        (False, Answer.APPROVE, True),
        (False, Answer.REFUSE, True),
    ],
)
def test_an_update_asks_only_to_run_or_to_answer(
    run_now: bool, answer: Answer | None, asks: bool
) -> None:
    intent = _update(run_now=run_now, answer=answer)
    assert requires_confirmation(WORKBOARD_UPDATE_OPERATION, intent) is asks


@pytest.mark.parametrize(("answer", "asks"), [(None, False), (Answer.AMEND, True)])
def test_a_comment_asks_only_when_it_answers(answer: Answer | None, asks: bool) -> None:
    assert requires_confirmation(WORKBOARD_COMMENT_OPERATION, _comment(answer)) is asks


def test_the_three_acts_name_the_ticket() -> None:
    content = {
        "operation_id": "workboard_ticket.comment",
        "title": "Any",
        "intent": _comment(None),
    }
    label = build_effect_label("draft:application_action", {"draft": content})
    assert label == {
        "i18n_key": "effects.labels.comment_ticket_tool",
        "values": {"target": "Plan the trip"},
    }
```

Add `"workboard_ticket.create"`, `"workboard_ticket.update"`, `"workboard_ticket.comment"` to `DIRECT_OPERATIONS` in `test_confirmation_policy.py`.

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_ticket_flip.py tests/unit/domains/agents/application/test_confirmation_policy.py -v` → FAIL (still `ASK`).

- [ ] **Step 3: The declarations and their two exceptions**

`workboard_create_spec.py`: `WORKBOARD_CREATE_OPERATION` gains `confirmation=direct("A ticket the person can edit or delete at any time (owner decision, 2026-10-15; direct under ADR-276 before 2026-10-11)."),`.

`workboard_update_spec.py`:

```python
def _runs_or_answers(intent: Mapping[str, object]) -> bool:
    """A requested run, or the answer to a pending action, keeps the card."""
    selection = WorkboardUpdatePatch.model_validate(intent).workboard_update
    return selection.request.run_now or selection.answer is not None


WORKBOARD_UPDATE_OPERATION = ApplicationOperationSpec(
    ...,
    confirmation=direct(
        "An edit is changed back the same way (owner decision, 2026-10-15).",
        ask_when=AskWhen(
            name="run_or_answer",
            reason=(
                "Launching LIA on the ticket is autonomous, billed work, and handing a "
                "« confirming » ticket back applies the owner's last note as the answer to "
                "a pending action (ADR-276 lot 9)."
            ),
            test=_runs_or_answers,
        ),
    ),
)
```

`workboard_comment_spec.py`:

```python
def _answers(intent: Mapping[str, object]) -> bool:
    """A comment that answers a pending action keeps the card."""
    return WorkboardCommentPatch.model_validate(intent).workboard_comment.answer is not None


WORKBOARD_COMMENT_OPERATION = ApplicationOperationSpec(
    ...,
    confirmation=direct(
        "A note is anodyne (owner decision, 2026-10-15).",
        ask_when=AskWhen(
            name="answers_pending_action",
            reason=(
                "On a « confirming » ticket the comment IS the approval or refusal of what "
                "LIA waits to do (ADR-276 lot 9)."
            ),
            test=_answers,
        ),
    ),
)
```

(`Mapping` from `collections.abc`; `AskWhen`, `direct` from `operation_spec`; the patch models from the spec's own schema modules.)

`labels.py`, `APPLICATION_LABELS`:

```python
    "workboard_ticket.create": (
        "effects.labels.create_ticket_tool",
        ("workboard_create", "request", "title"),
    ),
    "workboard_ticket.update": (
        "effects.labels.update_ticket_tool",
        ("workboard_update", "after", "title"),
    ),
    "workboard_ticket.comment": (
        "effects.labels.comment_ticket_tool",
        ("workboard_comment", "title"),
    ),
```

- [ ] **Step 4: What the model reads**

`create_ticket_catalogue_manifest`: `mutation_policy="reversible"`, `mutation_policy_reason=WORKBOARD_CREATE_OPERATION.confirmation.reason`, outputs `[OutputFieldSchema(path="application_result", type="object", description="The created ticket, or the refusal")]`, and the description's first sentences become « Creates a ticket on the user's workboard at once. Use the full request schema, or legacy fields exclusively. Assigning to LIA permits later paid execution under normal quotas; never claim it already ran. Unknown completion is not automatically retried. » (the rest — « Use when they want to keep track… NOT for … (use automation). » — unchanged).

`update_ticket_catalogue_manifest` (stays `draft`): replace « Preparation produces mandatory native human confirmation, without persisting a change or sending notifications. » with « The change happens at once; a change that sets run_now, or that hands a confirming ticket back to LIA with the owner's answer, asks the person first and changes nothing until they confirm. » — the rest unchanged.

`comment_ticket_catalogue_manifest` (stays `draft`): replace « Prepare mandatory human confirmation for an exact literal comment. Preparation posts nothing. » with « Post an exact literal comment at once. On an owner-held confirming ticket the comment is an answer, and it asks the person first: » — the rest (« the source classifies the complete comment: … ») unchanged.

Docstrings, first paragraph and `Returns:` — `create_ticket_tool`: « Create an exact ticket at once. » / « The created ticket, or the refusal. »; `update_ticket_tool`: « Update, move or run a ticket — at once, except a run or an answer, which asks first. » / « The updated ticket, a confirmation card, or the refusal. »; `comment_ticket_tool`: « Post a literal comment at once; a comment that answers a pending action asks first. » / « The posted comment, a confirmation card, or the refusal. »

- [ ] **Step 5: Run the flip tests and the declaration guards**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/application/test_ticket_flip.py tests/unit/domains/agents/application/test_confirmation_policy.py tests/unit/domains/agents/application/test_confirmation_consistency.py tests/unit/domains/agents/effects/test_effect_labels.py -v` → PASS.

- [ ] **Step 6: Re-point the tests that pinned « tickets ask »**

Same rules as Task 1.5 Step 7: a test that obtains a ticket CARD and confirms it (`test_application_workboard_create_flow.py::test_original_create_tool_human_confirmation`, `test_application_workboard_update_flow.py::test_update_tool_uses_the_common_confirmed_executor`, `test_application_workboard_comment_flow.py::test_comment_tool_requires_human_confirmation`) gets the `card_path` fixture; a test asserting that a creation, a plain update or a plain comment « is a proposal » asserts the act; `tests/unit/domains/agents/tools/test_workboard_tools.py`, `tests/unit/domains/agents/workboard/test_wording.py`, `tests/unit/domains/agents/application/test_workboard_update_contract.py`, `test_workboard_comment_contract.py`, `tests/unit/domains/agents/semantic/test_native_payload_semantics.py`: an expectation reading these tools as `draft`/pending reads `reversible`/acted for creation, and « acted unless run or answer » for the two others. Every edited file goes in the lot's review notes.

### Task 2.4: The ticket acts, proven on PostgreSQL

**Files:**
- Test: `apps/api/tests/integration/test_application_direct_tickets.py` (new)

- [ ] **Step 1: Write the tests**

```python
"""Tickets act at once; a requested run asks, and nobody can answer it in a routine (ADR-347)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.tools import workboard_tools
from src.domains.users.models import User
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.fixture
def database(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for target in (
        "src.domains.agents.tools.workboard_creation_tool.get_db_context",
        "src.domains.agents.tools.workboard_update_tool.get_db_context",
        "src.domains.agents.tools.workboard_comment_tool.get_db_context",
        "src.domains.agents.application.direct_execution.get_db_context",
        "src.domains.agents.application.draft_execution.get_db_context",
        "src.infrastructure.database.session.get_db_context",
    ):
        monkeypatch.setattr(target, session)
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    return async_session


def _runtime(user: User) -> object:
    return make_tool_runtime(user_id=user.id, store=InMemoryStore())


async def test_a_ticket_is_created_and_commented_at_once(
    database: AsyncSession, test_user: User
) -> None:
    with (
        installed_runtime_context(user_id=test_user.id, deps=object()),
        effect_scope(EffectScope(run_id="run-ticket", idempotency_key="call:create")),
    ):
        created = await workboard_tools.create_ticket_tool.coroutine(
            request={"title": "Plan the trip"}, runtime=_runtime(test_user)
        )
    assert created.success and not created.metadata.get("requires_confirmation")
    assert await database.scalar(select(func.count(WorkboardTicket.id))) == 1
    with (
        installed_runtime_context(user_id=test_user.id, deps=object()),
        effect_scope(EffectScope(run_id="run-ticket", idempotency_key="call:comment")),
    ):
        commented = await workboard_tools.comment_ticket_tool.coroutine(
            ticket="Plan the trip", body="Booked the train", runtime=_runtime(test_user)
        )
    assert commented.success and not commented.metadata.get("requires_confirmation")
    assert await database.scalar(select(func.count(WorkboardComment.id))) == 1
    policies = list(
        (
            await database.execute(
                select(AgentEffect.mutation_policy).where(AgentEffect.user_id == test_user.id)
            )
        ).scalars()
    )
    assert policies == ["reversible", "reversible"]
    assert await database.scalar(select(func.count(ApplicationCommand.id))) == 0


async def test_a_requested_run_asks(database: AsyncSession, test_user: User) -> None:
    await WorkboardService(database).create(test_user, TicketCreate(title="Run me", assignee="lia"))
    await database.commit()
    with (
        installed_runtime_context(user_id=test_user.id, deps=object()),
        effect_scope(EffectScope(run_id="run-ticket", idempotency_key="call:run")),
    ):
        result = await workboard_tools.update_ticket_tool.coroutine(
            ticket="Run me", run_now=True, runtime=_runtime(test_user)
        )
    assert result.metadata.get("requires_confirmation")
    assert await database.scalar(select(func.count(ApplicationCommand.id))) == 1


async def test_in_a_routine_a_requested_run_is_refused_and_nothing_is_written(
    database: AsyncSession, test_user: User
) -> None:
    await WorkboardService(database).create(test_user, TicketCreate(title="Run me", assignee="lia"))
    await database.commit()
    with (
        installed_runtime_context(user_id=test_user.id, deps=object()),
        effect_scope(
            EffectScope(run_id="run-routine", idempotency_key="call:run", source="scheduled")
        ),
    ):
        result = await workboard_tools.update_ticket_tool.coroutine(
            ticket="Run me", run_now=True, runtime=_runtime(test_user)
        )
    assert not result.success and result.error_code == "FORBIDDEN"
    assert await database.scalar(select(func.count(ApplicationCommand.id))) == 0
```

- [ ] **Step 2: Run them**

Run: `task test:backend:integration -- tests/integration/test_application_direct_tickets.py -v` → PASS.

### Task 2.5: Lot 2 gates, runtime proof and cold review

- [ ] **Step 1: Gates** — `task lint`; `task test:backend:unit:fast`; `task test:backend:agents`; `task test:backend:integration -- tests/integration/test_application_workboard_create_flow.py tests/integration/test_application_workboard_update_flow.py tests/integration/test_application_workboard_comment_flow.py tests/integration/test_workboard_legacy_read_capabilities.py tests/integration/test_application_direct_tickets.py -q`.
- [ ] **Step 2: Runtime proof, no model call** — on the proof account, in the container: create a ticket (acts), comment it (acts), update its title (acts), update with `run_now` (card, then the card cancelled), delete the ticket afterwards through `delete_ticket_tool`'s own confirmed path so nothing remains.
- [ ] **Step 3: Cold review** — every file of Tasks 2.1–2.4, and the re-pointed tests, each against its rule.

---

## Closing of part 1 — documentation and the full gates

### Task 3.1: ADR-347 and its amendments

`<date>` in this task is the day it runs, ISO `YYYY-MM-DD`, written identically in the ADR, the index entry and the history entry.

**Files:**
- Create: `docs/architecture/ADR-347-One-Confirmation-Declaration-Per-Application-Operation.md`
- Modify: `docs/architecture/ADR-339-Application-Commands-With-Current-Authority-And-Secure-Continuations.md`, `ADR-263-Execution-Authority-Chain-And-Effect-Register.md`, `ADR-268-Generic-Recurrence-And-Reminder-Management.md`, `ADR-276-Workboard.md` (one amendment each, before their « Implementation references » or at the end)
- Modify: `docs/architecture/ADR_INDEX.md` (ADR-347 entry after ADR-346), `docs/technical/APPLICATION_COMMANDS.md` (« Preparation, execution and continuation »)

- [ ] **Step 1: Write ADR-347**

```markdown
# ADR-347 — One confirmation declaration per application operation

**Status:** Accepted — lots A, 0, 1 and 2 implemented; the migration of the
remaining 51 own-path operations follows (part 2 of the plan).
**Date:** <date>
**Deciders:** the owner (decisions of 2026-10-15); Claude recorded the design,
the measurements and the implementation.
**Amends:** ADR-339, ADR-263, ADR-268, ADR-276, ADR-336.

## Context

Since 2026-10-11 the native `create_reminder_tool` built the application
settings card instead of writing (`499c4cecc`), reversing ADR-268's owner
decision without an amendment; switching a routine and the three ticket acts
asked too. An application action had no declaration of its own: 68 operations
went through a shared door reading a field list (`CONFIRMATION_FREE_FIELDS`, 8
operations), 60 built their own draft and always asked, and the field rule was
decided twice — by the gate on the raw call and by the door on the prepared
intent.

## Decision

1. **One declaration per operation** — `ApplicationOperationSpec.confirmation`:
   `ASK`, or `DIRECT` with a written reason and an optional `ask_when`, a named
   pure test over the PREPARED intent. `DIRECT` is refused on device, secure
   and administrative operations. `requires_confirmation(spec, intent)` is its
   one reader.
2. **One decision per call.** An `ASK` operation keeps the effect gate's path
   unchanged; the gate hands a `DIRECT` operation's tool, and its declared
   aliases, to the door (`application/action_door.py`), which prepares, decides
   and either builds the card or claims → executes → closes the act through the
   gate's own primitives (`effects/application_effects.py`). The raw-call
   reading (`policy_for_call`) is gone.
3. **A replay is served before anything is prepared**: the gate reads the
   register by the call's key, re-checks current authority, and serves the
   record; only a call with no record reaches the door.
4. **Registers as they were**: an action row for a direct act, the consultation
   row for a card, a failed consultation for a call that stopped before its act.
5. **One label per act**, from its operation and its prepared content
   (`APPLICATION_LABELS`), whichever tool performed it, confirmed or direct;
   only a declared field reaches a label.
6. **The manifest states the declaration**: `ASK` or `DIRECT` with `ask_when` →
   `draft`, `DIRECT` → `reversible` with the declaration's reason; a test holds
   every manifest to it, and a `DIRECT` tool's description and docstring
   promise no confirmation.
7. **Direct operations (owner decisions, 2026-10-15)**: `reminder.create`,
   `.update`, `.delete` (superseding ADR-268's « the deletion is the step that
   asks »), `routine_state.update`, `workboard_ticket.create`, `.update` (asks
   for a run or an answer) and `.comment` (asks for an answer); the eight
   personalization operations keep their field rule as an `ask_when`.
8. **A reminder survives the minute a model writes**: an instant up to
   `REMINDER_PAST_INSTANT_GRACE_SECONDS` in the past is accepted and fires at the
   next sweep; an older one is refused with the current local time;
   `repeat='once'` beside an instant is repaired.

## Flipping an operation — the checklist

1. Its declaration on the spec, with the reason (and `ask_when` when needed).
2. Its manifest's policy literal (and `mutation_policy_reason=SPEC.confirmation.reason`).
3. Its manifest description and its tool docstring.
4. Its progress label in the six web locales.
5. Its `APPLICATION_LABELS` entry when its acts should name their object.
6. `DIRECT_OPERATIONS` in `test_confirmation_policy.py`; the tests that pinned
   the old behavior keep the card path through the `card_path` fixture.

## Consequences

- « Delete all my reminders » deletes one by one without asking in the ReAct
  loop; the pipeline keeps its FOR_EACH confirmation (decided by the tool's
  category), and no longer shows the grouped card after it.
- The eight personalization operations are labelled by their operation, read
  neutral technical messages, and file a failed consultation — not a failed
  action — when their preparation refuses.
- The card path of every `DIRECT` operation stays complete and tested.

## Validation

`test_confirmation_declaration.py`, `test_confirmation_policy.py`,
`test_action_door.py`, `test_application_effects.py`,
`test_confirmation_consistency.py`, `test_application_door_guard.py`,
`test_lot1_refusal_characterization.py`, `test_ticket_creation_characterization.py`,
`test_lot1_flip.py`, `test_ticket_flip.py`, and on PostgreSQL
`test_effect_find_by_key_db.py`, `test_application_direct_reminders_and_routines.py`,
`test_application_direct_tickets.py`.

## Implementation references

- [Declaration](../../apps/api/src/domains/agents/application/operation_spec.py)
- [Decision and field rules](../../apps/api/src/domains/agents/application/confirmation_policy.py)
- [The door](../../apps/api/src/domains/agents/application/action_door.py)
- [The register as a door uses it](../../apps/api/src/domains/agents/effects/application_effects.py)
- [Labels](../../apps/api/src/domains/agents/effects/labels.py)
- [Spec](../superpowers/specs/2026-10-15-application-confirmation-rule-design.md)
```

- [ ] **Step 2: The four amendments (one paragraph each)**

- ADR-339: « **Amendment (ADR-347).** An operation declares whether its calls show their card (`ApplicationOperationSpec.confirmation`); requirement F03's field list became the `ask_when` of the eight personalization operations, and every application action goes through one door (part 1: the reminder, routine and ticket tools; part 2: the rest). »
- ADR-263: « **Amendment (ADR-347).** A `DIRECT` application operation is claimed and closed by its door, not by the gate, through the gate's own `_run_claimed`; the gate serves its replays before the tool runs. `policy_for_call` is gone. »
- ADR-268: « **Amendment (ADR-347).** Creating, modifying and deleting a reminder act at once (owner decision, 2026-10-15) — the deletion no longer asks. An instant up to one minute past is accepted. »
- ADR-276: « **Amendment (ADR-347).** Creating, updating and commenting a ticket act at once again; an update that requests a run or answers a pending action, and a comment that answers one, still ask. »

- [ ] **Step 3: Index and technical document**

`ADR_INDEX.md`, after the ADR-346 entry:

```markdown
### ADR-347: one confirmation declaration per application operation

**File**: `docs/architecture/ADR-347-One-Confirmation-Declaration-Per-Application-Operation.md`

**Status**: Accepted, <date>. Amends ADR-339, ADR-263, ADR-268, ADR-276, ADR-336.

**Decision**: An application operation declares whether its calls show their confirmation card — `ASK`, or `DIRECT` with a written reason and an optional `ask_when` read on the prepared intent — and one door reads it: an asking operation keeps the effect gate's path, a direct one is prepared, decided and recorded by its door through the gate's own claim → act → close, its replay served from the register before anything is prepared. Reminders (create, change, delete), the routine switch and the three ticket acts act at once again; a ticket run or an answer to a pending action still asks. One label per act, from its operation.
```

`APPLICATION_COMMANDS.md`, at the start of « Preparation, execution and continuation », a paragraph: « Each operation declares whether its calls show their card (`confirmation`, ADR-347). An `ASK` operation follows the flow below. A `DIRECT` operation is handed by the effect gate to the door, which prepares, decides on the prepared intent and either builds the card (when `ask_when` fires) or performs the act at once through the same confirmed executor, recorded as a reversible act. »

- [ ] **Step 4: Living maps, six languages**

`apps/web/src/data/maps/history.json`, after the ADR-346 entry: `{"adr": 347, "date": "<date>", "theme": "orchestration", "functional": ["f.application", "f.hitl", "f.reminders", "f.routines", "f.workboard"], "technical": ["t.application", "t.hitl", "t.registers", "t.toolsys"]}`.

`apps/web/src/data/maps/text/history.<lang>.json`, `entries["347"]` (`title`, `summary`; `task docs:maps` stamps `src`):

- fr — « Une seule déclaration de confirmation par opération d'application » / « Une opération de l'application déclare si ses appels montrent leur carte de confirmation : toujours, ou jamais sauf un cas nommé lu sur l'intention préparée. Une seule porte prépare, décide et inscrit l'acte ; créer, modifier et supprimer un rappel, mettre une routine en pause et les actes sur les tickets se font de nouveau sans carte. Un acte rejoué après une interruption est servi depuis le registre, jamais préparé une seconde fois. »
- en — "One confirmation declaration per application operation" / "An application operation declares whether its calls show their confirmation card: always, or never except a named case read on the prepared intent. One door prepares, decides and records the act; creating, changing and deleting a reminder, pausing a routine and the ticket acts happen at once again. An act replayed after an interruption is served from the register, never prepared twice."
- de — „Eine Bestätigungserklärung pro Anwendungsoperation“ / „Eine Anwendungsoperation erklärt, ob ihre Aufrufe ihre Bestätigungskarte zeigen: immer, oder nie außer in einem benannten Fall, der an der vorbereiteten Absicht gelesen wird. Eine einzige Tür bereitet die Handlung vor, entscheidet und verzeichnet sie; eine Erinnerung erstellen, ändern und löschen, eine Routine pausieren und die Ticket-Aktionen geschehen wieder sofort. Eine nach einer Unterbrechung wiederholte Handlung wird aus dem Register bedient, nie ein zweites Mal vorbereitet.“
- es — «Una declaración de confirmación por operación de la aplicación» / «Una operación de la aplicación declara si sus llamadas muestran su tarjeta de confirmación: siempre, o nunca salvo un caso nombrado que se lee en la intención preparada. Una sola puerta prepara, decide y registra el acto; crear, modificar y eliminar un recordatorio, pausar una rutina y las acciones sobre tickets vuelven a ocurrir al instante. Un acto repetido tras una interrupción se sirve desde el registro, nunca se prepara dos veces.»
- it — «Una dichiarazione di conferma per ogni operazione dell'applicazione» / «Un'operazione dell'applicazione dichiara se le sue chiamate mostrano la scheda di conferma: sempre, oppure mai salvo un caso nominato letto sull'intenzione preparata. Un'unica porta prepara, decide e registra l'atto; creare, modificare ed eliminare un promemoria, mettere in pausa una routine e le azioni sui ticket tornano ad avvenire subito. Un atto ripetuto dopo un'interruzione viene servito dal registro, mai preparato una seconda volta.»
- zh — 「每个应用操作一条确认声明」 / 「应用操作声明其调用是否显示确认卡片：总是显示，或除在准备好的意图上读到的具名情形外从不显示。唯一的入口负责准备、决定并记录该操作；创建、修改和删除提醒、暂停例程以及工单操作重新即时生效。中断后重放的操作从登记册中直接返回，绝不会再次准备。」

(The guillemets above delimit the text in this plan; the JSON strings carry the sentences only.)

- [ ] **Step 5: CLAUDE.md pointer, counts, AGENTS mirror**

In `CLAUDE.md`, « Useful Documentation Pointers », after the ADR-346 line:

```markdown
- One confirmation declaration per application operation (ADR-347): an operation declares `ASK` or `DIRECT` (+ `ask_when` on the prepared intent); an asking one keeps the gate's path, a direct one is decided and recorded by its door, replays served from the register: `docs/architecture/ADR-347-One-Confirmation-Declaration-Per-Application-Operation.md`
```

Then (repo root): `task release:sync-counts` (realigns « 346 ADR files, ADR-347 latest »), `task docs:maps`, `task docs:sync-agents`.

- [ ] **Step 6: Documentation gate**

Run: `task lint:docs` → exit 0. If it names files moved but not staged, run `task lint:docs:preview` (read-only) — never `git add`; the owner stages.

### Task 3.2: Full gates of part 1, memory, and the hand-off to part 2

- [ ] **Step 1:** `task ci:fast` → exit 0 (report the test counts, warnings and any skipped gate verbatim).
- [ ] **Step 2:** `task test:backend:integration -- tests/integration -k "application or effects or workboard or reminder or routine" -q` → exit 0.
- [ ] **Step 3:** Update the memory note `project_reminder_direct_and_confirmation_rule_2026_10_15.md` and its index line: part 1 implemented, not committed, gates green, what part 2 must migrate (`NOT_YET_MIGRATED`, 23 modules, 51 operations).
- [ ] **Step 4:** Write part 2 of the plan (`docs/superpowers/plans/<date>-application-confirmation-rule-part-2.md`): one task per module of `NOT_YET_MIGRATED`, each « characterize the refusals (as Task 1.1) → move onto `application_action` with the module's own `Refusals` (as Tasks 1.2/1.3) → remove it from the list » (the session module also declares `binds_origin=True` on `device_session.revoke`, spec §4.1, and keeps its « Authenticated browser required. » check in the tool, before the door), then the closing (empty list, `task ci:fast`, ADR-347 status « fully implemented »). Submit it to the owner before touching code.
