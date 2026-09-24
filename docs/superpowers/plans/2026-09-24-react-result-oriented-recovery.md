# ReAct Result-Oriented Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ReAct turn that meets an obstacle climbs a bounded recovery ladder before it may state a gap, and relative dates become absolute before they reach a tool.

**Architecture:** The model closes its final message with an `<unresolved>` block; one predicate (`should_recover`) sends such a turn to a model-less `react_recovery` node, which removes the draft from the thread and records a pass; every later model call of the turn is shown, right after the draft's place, the draft again (as an assistant message) and a directive naming the missing facts — both composed per call, never persisted, so the roles keep alternating on every provider and no later turn reads them. The ReAct doctrine is rewritten around a verification step and the ladder; the weather tool publishes an ISO contract and refuses what it cannot read.

**Tech Stack:** Python 3.14, LangGraph 1.x, LangChain 1.x, Pydantic 2.x settings, prometheus_client, pytest (asyncio auto), Grafana JSON dashboards.

**Spec:** `docs/superpowers/specs/2026-09-24-react-result-oriented-recovery-design.md`

## Global Constraints

- Owner rule: NO git action (no add, commit, stash, restore); the owner handles git. « Checkpoint » steps below run the task's tests instead of committing.
- Never reason on a specific provider or model; every slot is configurable.
- Prompt text is English with generic examples; a prompt states only what the code enforces (ADR-284); every `{placeholder}` has a producer; no placeholder before `DYNAMIC_CONTEXT_MARKER` unless listed in the hygiene guard.
- Tool payload messages are technical English (ADR-256); user-visible strings go through i18n (none added here).
- No PII at INFO: log counts and ids, never a declared fact's text.
- `REACT_RECOVERY_PASSES_MAX` default 1, bounds 0..3, 0 disables; declared in `core/constants.py`, `core/config/agents.py`, the 4 main `.env` files and the 4 demonstrator files (CRLF preserved where present).
- Shrink-only ratchets (file size 600 SLOC / frozen caps, CC ≥ 15, cycles, mypy debt, metric coverage).
- Bench: at most 2 USD, no Anthropic call, run only once the implementation is green.
- Python patches on Windows: write with `newline="\n"` or bytes; check `git ls-files --eol` on touched files.

## Review Focus

1. The model writes `<unresolved>` in the person's language with a « nothing » line (`aucun`, `none`, `-`) → no pass is taken (Task 3, `test_a_nothing_line_declares_nothing`).
2. During the pass the model re-declares the same gaps without calling any tool → the turn ends after `REACT_RECOVERY_PASSES_MAX` passes, outcome `still_unresolved`, no loop (Task 6, `test_a_pass_that_changes_nothing_ends_the_turn`).
3. A HITL interrupt during the pass (sandbox permission question) → on resume the directive is re-inserted from the checkpointed state (Task 4, `test_the_directive_survives_a_resume`).
4. The draft's predecessor is the question and the cross-turn cache flag places the turn's context as a trailing system message → the directive goes after that context, never between the question and its context (Task 3, `test_the_directive_never_splits_the_question_from_its_context`).
5. The draft carries `tool_calls` as well as a block → it is not a final message and no pass is taken (Task 3, `test_a_message_with_tool_calls_never_recovers`).

---

### Task 1: The weather tool reads ISO dates and refuses what it cannot read

**Files:**
- Modify: `apps/api/src/domains/agents/tools/weather_tools.py` (`_calculate_target_date`, remove `_parse_date_offset`, both `execute_api_call` that call it, both `format_registry_response`)
- Modify: `apps/api/src/domains/agents/weather/catalogue_manifests.py` (`_DATE_PARAM`)
- Test: `apps/api/tests/unit/domains/agents/tools/test_weather_date_parsing.py` (migrate from the removed wrapper, add the refusal)

**Interfaces:**
- Produces: `class UnreadableDateError(ValueError)` with attribute `reference: str`; `_calculate_target_date(date_ref, user_timezone) -> tuple[str, int, bool]` raising `UnreadableDateError`; `_unreadable_date_result(reference: str, user_timezone: str) -> dict[str, Any]` returning `{"success": False, "error": "invalid_date", "error_code": ToolErrorCode.INVALID_INPUT.value, "message": ...}`.

- [ ] **Step 1: Write the failing tests** (replace `_parse_date_offset` by a local helper over `_calculate_target_date`, keep every existing case, turn the unknown-reference case into a refusal)

```python
def _offset(ref: str | None, tz: str = TEST_TIMEZONE) -> int:
    from src.domains.agents.tools.weather_tools import _calculate_target_date

    return _calculate_target_date(ref, tz)[1]


class TestAnUnreadableReferenceIsRefused:
    """2026-09-23: « demain » fell back to TODAY in silence and the loop served
    the wrong day as a success. A value the tool cannot read is refused."""

    @pytest.mark.parametrize("ref", ["demain", "mañana", "morgen", "gibberish", "next month"])
    def test_an_unreadable_reference_raises(self, ref: str) -> None:
        from src.domains.agents.tools.weather_tools import (
            UnreadableDateError,
            _calculate_target_date,
        )

        with pytest.raises(UnreadableDateError) as caught:
            _calculate_target_date(ref, TEST_TIMEZONE)
        assert caught.value.reference == ref

    def test_the_refusal_says_what_to_send_and_what_today_is(self) -> None:
        from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
        from src.domains.agents.tools.common import ToolErrorCode
        from src.domains.agents.tools.weather_tools import (
            _get_today_in_timezone,
            _unreadable_date_result,
        )

        result = _unreadable_date_result("demain", DEFAULT_USER_DISPLAY_TIMEZONE)
        today = _get_today_in_timezone(DEFAULT_USER_DISPLAY_TIMEZONE).date().isoformat()
        assert result["success"] is False
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        assert "'demain'" in result["message"] and "YYYY-MM-DD" in result["message"]
        assert today in result["message"] and DEFAULT_USER_DISPLAY_TIMEZONE in result["message"]

    def test_no_date_still_means_today(self) -> None:
        assert _offset(None) == 0
        assert _offset("") == 0

    def test_the_lenient_readings_are_kept(self) -> None:
        assert _offset("tomorrow") == 1
        assert _offset("in 3 days") == 3
        assert _offset("this week") == 0
```

And a manifest test in the same file:

```python
def test_the_manifest_publishes_the_iso_contract() -> None:
    from src.domains.agents.weather.catalogue_manifests import _DATE_PARAM

    assert "YYYY-MM-DD" in _DATE_PARAM.description
    assert "temporal reference" not in _DATE_PARAM.description
```

- [ ] **Step 2: Run them — expect FAIL** (`ImportError: UnreadableDateError`, manifest text)

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/tools/test_weather_date_parsing.py -q --no-cov`

- [ ] **Step 3: Implement**

In `weather_tools.py`, above `_calculate_target_date`:

```python
class UnreadableDateError(ValueError):
    """A ``date`` value the forecast tools cannot read (2026-09-23 defect).

    It used to fall back to TODAY in silence, so « demain » sent by a ReAct loop
    in French came back as a successful forecast for the wrong day.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"unreadable date reference: {reference!r}")
        self.reference = reference


def _unreadable_date_result(reference: str, user_timezone: str) -> dict[str, Any]:
    """The failure a forecast tool returns for a date it cannot read.

    Technical English (ADR-256): the model corrects its own call from it — the
    accepted format and the person's current date, so the fix is computable.
    """
    today = _get_today_in_timezone(user_timezone).date().isoformat()
    return {
        "success": False,
        "error": "invalid_date",
        "error_code": ToolErrorCode.INVALID_INPUT.value,
        "message": (
            f"date '{reference}' is not readable: pass an ISO date (YYYY-MM-DD) or an "
            f"ISO datetime, resolved from the current date; today is {today} ({user_timezone})."
        ),
    }
```

In `_calculate_target_date`, replace the final fallback (`# Default: today, not specific` / `return today_date.isoformat(), 0, False`) with `raise UnreadableDateError(ref)`, add `Raises:` to its docstring, and delete the deprecated `_parse_date_offset` (no caller in `src/`). In both `execute_api_call` methods wrap the call:

```python
        try:
            target_date, date_offset, is_specific_date = _calculate_target_date(
                date_ref, user_timezone
            )
        except UnreadableDateError as exc:
            return _unreadable_date_result(exc.reference, user_timezone)
```

In both `format_registry_response` failure branches: `error_code=result.get("error_code", "weather_forecast_error")` (resp. `"hourly_forecast_error"`). Import `ToolErrorCode` from `src.domains.agents.tools.common` if absent.

In `catalogue_manifests.py`:

```python
_DATE_PARAM = ParameterSchema(
    name="date",
    type="string",
    required=False,
    description=(
        "Target date: an ISO date (YYYY-MM-DD) or an ISO datetime — for weather at a "
        "CALENDAR EVENT, the event's start_datetime. Resolve a relative expression "
        "yourself from the current date before passing it."
    ),
    semantic_type="event_start_datetime",  # Cross-domain: weather for a calendar event
)
```

- [ ] **Step 4: Run the file and the weather suites — expect PASS**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/tools/ -q --no-cov -k "weather"`

- [ ] **Step 5: Checkpoint** — no git action; note the files for the final report.

---

### Task 2: Absolute dates in the initiative and planner prompts

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/initiative_prompt.txt` (STEP 2, static part)
- Modify: `apps/api/src/domains/agents/prompts/v1/smart_planner_prompt.txt` (INDEXABLE paragraph, static part)
- Test: `apps/api/tests/unit/domains/agents/prompts/test_absolute_dates_directive.py` (create)

**Interfaces:** none (prompt text).

- [ ] **Step 1: Write the failing test**

```python
"""Every prompt that writes tool parameters from the person's words resolves dates.

2026-09-23: « demain » reached the weather tool as a word and the initiative
checked the agenda of the wrong day. The house directive already lives in six
prompts; the three that write tool parameters in a turn carry it too.
"""

from __future__ import annotations

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name", ["react_agent_prompt", "initiative_prompt", "smart_planner_prompt"]
)
def test_the_static_part_resolves_relative_dates(name: str) -> None:
    static = load_prompt(name).split(DYNAMIC_CONTEXT_MARKER, 1)[0]
    assert "in any language" in static and "ISO 8601" in static, name
```

- [ ] **Step 2: Run — expect FAIL** (react prompt passes only after Task 5; initiative and planner fail now)

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/test_absolute_dates_directive.py -q --no-cov`

- [ ] **Step 3: Edit the prompts**

`initiative_prompt.txt`, end of STEP 2 (after « If required parameters are missing or ambiguous, fallback to should_act=false. »):

```
   - Absolute Dates: Resolve every relative date or time expression, in any language, against
     the Current Date and Timezone of the dynamic context into ISO 8601 before writing a
     parameter. The day to check is the day the executed action targets — never a date a
     result merely carries.
```

`smart_planner_prompt.txt`, INDEXABLE paragraph, replace `  → pass to the corresponding tool parameter.` with:

```
  → pass to the corresponding tool parameter. A relative date or time expression, in
    any language, is first resolved against the current datetime (dynamic context
    below) into ISO 8601.
```

- [ ] **Step 4: Run the test (initiative, planner PASS) and the prompt guards**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/ -q --no-cov`

- [ ] **Step 5: Checkpoint.**

---

### Task 3: The recovery protocol — parser, predicate, directive, setting, state

**Files:**
- Create: `apps/api/src/domains/agents/nodes/react_recovery.py`
- Create: `apps/api/src/domains/agents/prompts/v1/react_recovery_directive.txt`
- Modify: `apps/api/src/domains/agents/prompts/prompt_loader.py` (`PromptName` += `"react_recovery_directive"`)
- Modify: `apps/api/src/core/constants.py` (`REACT_RECOVERY_PASSES_MAX_DEFAULT: int = 1`)
- Modify: `apps/api/src/core/config/agents.py` (`react_recovery_passes_max`)
- Modify: `apps/api/src/domains/agents/models.py` (`react_recovery_passes: list[dict[str, Any]]`)
- Modify: `apps/api/src/domains/agents/utils/react_budget.py` (`ReactTurnReset` + `react_turn_reset()`)
- Modify: `apps/api/tests/unit/domains/agents/nodes/test_react_turn_reset_guard.py` (`_DECIDERS` += `react_recovery.should_recover`)
- Modify: `.env.example`, `.env.prod.example`, `.env`, `.env.prod`, `.env.demo-instance`, `.env.demo-instance.example`, `.env.demo-instance.prod`, `.env.demo-instance.prod.example`
- Test: `apps/api/tests/unit/domains/agents/nodes/test_react_recovery.py` (create)

**Interfaces:**
- Produces:
  - `EMPTY_DECLARATIONS: frozenset[str]`
  - `declared_unresolved(message: BaseMessage | None) -> tuple[str, ...]`
  - `should_recover(state: MessagesState) -> bool`
  - `react_recovery_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]` (returns `{"messages": [RemoveMessage(id=draft.id)], "react_recovery_passes": [...]}`; each pass `{"anchor_id": str, "draft": str, "unresolved": list[str]}` — `anchor_id` is the draft's PREDECESSOR, `draft` its full text)
  - `with_recovery_directives(messages: Sequence[BaseMessage], passes: Sequence[Mapping[str, Any]]) -> list[BaseMessage]` — inserts, after each anchor (and after the system messages glued to it), `AIMessage(draft)` then `HumanMessage(directive)`
  - `recovery_outcome(passes: Sequence[Mapping[str, Any]], final: BaseMessage | None, *, cut: bool) -> str | None` → `"resolved" | "partial" | "still_unresolved" | "cut" | None`
- Consumes: `react_exit_reason(state)` from `utils/react_budget.py`; `coerce_content_to_text` from the message-text helper; `load_prompt`.

- [ ] **Step 1: Write the failing tests** (`test_react_recovery.py`)

```python
"""A declared gap buys a bounded recovery pass (ADR-310)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.domains.agents.nodes import react_recovery as rr

pytestmark = pytest.mark.unit

GAP = "Mon texte.\n<unresolved>\n- Forecast for 2026-09-25: tool served 2026-09-24\n</unresolved>"


def _state(last: Any, passes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "messages": [HumanMessage("q", id="h1"), ToolMessage("r", tool_call_id="c", id="t1"), last],
        "react_iteration": 3,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 1.0,
        "react_recovery_passes": passes or [],
    }


class TestTheDeclaration:
    def test_the_lines_of_the_block_are_the_declaration(self) -> None:
        assert rr.declared_unresolved(AIMessage(GAP)) == (
            "Forecast for 2026-09-25: tool served 2026-09-24",
        )

    def test_no_block_declares_nothing(self) -> None:
        assert rr.declared_unresolved(AIMessage("All good.")) == ()

    @pytest.mark.parametrize("line", ["none", "None.", "-", "aucun", "rien", "nada", "无", "N/A"])
    def test_a_nothing_line_declares_nothing(self, line: str) -> None:
        assert rr.declared_unresolved(AIMessage(f"<unresolved>{line}</unresolved>")) == ()

    def test_case_bullets_and_several_blocks(self) -> None:
        text = "<thought><UNRESOLVED>1. A</UNRESOLVED></thought>\n<unresolved>* B\n* A</unresolved>"
        assert rr.declared_unresolved(AIMessage(text)) == ("A", "B")

    def test_list_content_is_read_as_text(self) -> None:
        msg = AIMessage(content=[{"type": "text", "text": "<unresolved>A</unresolved>"}])
        assert rr.declared_unresolved(msg) == ("A",)


class TestThePredicate:
    def test_a_declared_gap_with_a_pass_left_recovers(self) -> None:
        assert rr.should_recover(_state(AIMessage(GAP, id="d1"))) is True

    def test_a_message_with_tool_calls_never_recovers(self) -> None:
        msg = AIMessage(GAP, id="d1", tool_calls=[{"id": "c2", "name": "t", "args": {}}])
        assert rr.should_recover(_state(msg)) is False

    def test_no_pass_left(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_recovery_passes_max", 1)
        passes = [{"anchor_id": "t1", "draft": "x", "unresolved": ["A"]}]
        assert rr.should_recover(_state(AIMessage(GAP, id="d2"), passes)) is False

    def test_zero_switches_it_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_recovery_passes_max", 0)
        assert rr.should_recover(_state(AIMessage(GAP, id="d1"))) is False

    def test_a_budget_reached_never_recovers(self) -> None:
        state = _state(AIMessage(GAP, id="d1"))
        state["react_iteration"] = 70
        assert rr.should_recover(state) is False

    def test_a_draft_without_an_id_never_recovers(self) -> None:
        assert rr.should_recover(_state(AIMessage(GAP))) is False


class TestTheNode:
    async def test_the_draft_leaves_the_thread_and_travels_in_the_pass(self) -> None:
        update = await rr.react_recovery_node(_state(AIMessage(GAP, id="d1")), {})
        assert update["messages"] == [RemoveMessage(id="d1")]
        (record,) = update["react_recovery_passes"]
        assert record["anchor_id"] == "t1"
        assert record["unresolved"] == ["Forecast for 2026-09-25: tool served 2026-09-24"]
        assert record["draft"] == GAP


class TestTheDirective:
    PASS = {"anchor_id": "t1", "draft": "Mon texte. <unresolved>A\nB</unresolved>", "unresolved": ["A", "B"]}

    def test_the_draft_then_the_directive_follow_the_anchor(self) -> None:
        sent = [SystemMessage("s"), HumanMessage("q", id="h1"), ToolMessage("r", tool_call_id="c", id="t1")]
        out = rr.with_recovery_directives(sent, [self.PASS])
        assert [m.id for m in out[:3]] == [None, "h1", "t1"]
        draft, directive = out[3], out[4]
        assert isinstance(draft, AIMessage) and draft.content == self.PASS["draft"]
        assert isinstance(directive, HumanMessage)
        assert "- A\n- B" in str(directive.content) and "RECOVERY LADDER" in str(directive.content)

    def test_the_roles_keep_alternating_after_the_question(self) -> None:
        """A draft right after the question: never two human messages in a row."""
        out = rr.with_recovery_directives([HumanMessage("q", id="h1")], [{**self.PASS, "anchor_id": "h1"}])
        assert [type(m).__name__ for m in out] == ["HumanMessage", "AIMessage", "HumanMessage"]

    def test_the_directive_never_splits_the_question_from_its_context(self) -> None:
        sent = [SystemMessage("s"), HumanMessage("q", id="h1"), SystemMessage("ctx")]
        out = rr.with_recovery_directives(sent, [{**self.PASS, "anchor_id": "h1"}])
        assert [type(m).__name__ for m in out] == [
            "SystemMessage", "HumanMessage", "SystemMessage", "AIMessage", "HumanMessage"
        ]

    def test_it_is_never_written_to_the_given_list(self) -> None:
        sent = [HumanMessage("q", id="h1")]
        rr.with_recovery_directives(sent, [{**self.PASS, "anchor_id": "h1"}])
        assert len(sent) == 1

    def test_a_missing_anchor_still_shows_the_directive(self) -> None:
        out = rr.with_recovery_directives([HumanMessage("q", id="h1")], [{**self.PASS, "anchor_id": "zz"}])
        assert isinstance(out[-2], AIMessage) and isinstance(out[-1], HumanMessage)


class TestTheOutcome:
    P = [{"anchor_id": "t1", "draft": "x", "unresolved": ["A", "B"]}]

    def test_outcomes(self) -> None:
        assert rr.recovery_outcome([], AIMessage("done"), cut=False) is None
        assert rr.recovery_outcome(self.P, AIMessage("done"), cut=False) == "resolved"
        assert rr.recovery_outcome(self.P, AIMessage("<unresolved>A</unresolved>"), cut=False) == "partial"
        assert rr.recovery_outcome(self.P, AIMessage("<unresolved>A\nB</unresolved>"), cut=False) == "still_unresolved"
        assert rr.recovery_outcome(self.P, AIMessage(""), cut=True) == "cut"
```

Also add to `test_react_turn_reset_guard.py` `_DECIDERS`: `react_recovery.should_recover` (import `from src.domains.agents.nodes import react_recovery`).

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: react_recovery`)

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/test_react_recovery.py tests/unit/domains/agents/nodes/test_react_turn_reset_guard.py -q --no-cov`

- [ ] **Step 3: Implement**

`react_recovery_directive.txt`:

```
[RECOVERY PASS] Your answer above declared these facts unresolved:
{unresolved}
Before concluding, apply the RECOVERY LADDER to each of them, starting with the rungs you have not tried yet. Conclude again once every remaining rung is tried or can bring no new information, and keep in <unresolved> only the facts still missing.
```

`nodes/react_recovery.py` (module docstring explaining ADR-310; functions below):

```python
_BLOCK = re.compile(r"<unresolved>(.*?)</unresolved>", re.IGNORECASE | re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")

#: Lines that declare nothing. The prompt says to OMIT the block when nothing is
#: missing; a model that writes it anyway writes one of these, in the person's
#: language (the final message is written in it). Six languages, lower-cased,
#: trailing punctuation stripped.
EMPTY_DECLARATIONS: frozenset[str] = frozenset(
    {"", "-", "none", "n/a", "nothing", "aucun", "aucune", "rien", "keine", "keiner",
     "nichts", "nada", "ninguno", "ninguna", "nessuno", "niente", "无", "没有"}
)


def declared_unresolved(message: BaseMessage | None) -> tuple[str, ...]:
    if message is None:
        return ()
    lines: list[str] = []
    for block in _BLOCK.findall(coerce_content_to_text(message.content)):
        for raw in block.splitlines():
            line = _BULLET.sub("", raw).strip()
            if line.rstrip(".!").lower() not in EMPTY_DECLARATIONS and line not in lines:
                lines.append(line)
    return tuple(lines)


def should_recover(state: MessagesState) -> bool:
    messages = state.get("messages") or []
    if len(messages) < 2:
        return False
    draft, previous = messages[-1], messages[-2]
    if not isinstance(draft, AIMessage) or draft.tool_calls or not draft.id or not previous.id:
        return False
    if not declared_unresolved(draft):
        return False
    from src.core.config import settings as _settings  # late: routing tests patch it

    passes = state.get("react_recovery_passes") or []
    if len(passes) >= int(_settings.react_recovery_passes_max):
        return False
    return react_exit_reason(state) is None


@trace_node("react_recovery")
async def react_recovery_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    messages = state["messages"]
    draft, previous = messages[-1], messages[-2]
    unresolved = list(declared_unresolved(draft))
    record = {
        "anchor_id": previous.id,
        "draft": coerce_content_to_text(draft.content),
        "unresolved": unresolved,
    }
    passes = [*(state.get("react_recovery_passes") or []), record]
    logger.info("react_recovery_pass_started", pass_number=len(passes),
                declared=len(unresolved), iteration=state.get("react_iteration", 0))
    return {"messages": [RemoveMessage(id=draft.id)], "react_recovery_passes": passes}


def with_recovery_directives(messages, passes) -> list[BaseMessage]:
    out = list(messages)
    for record in passes:
        shown = [
            AIMessage(content=record["draft"]),  # the draft left the thread, not the call
            HumanMessage(content=_directive_text(record["unresolved"])),
        ]
        at = next((i for i, m in enumerate(out) if m.id == record["anchor_id"]), None)
        if at is None:
            logger.warning("react_recovery_anchor_missing", pass_count=len(passes))
            out.extend(shown)
            continue
        at += 1
        while at < len(out) and isinstance(out[at], SystemMessage):
            at += 1  # the turn's context stays glued to its question (ADR-308)
        out[at:at] = shown
    return out


def _directive_text(unresolved: Sequence[str]) -> str:
    return load_prompt("react_recovery_directive").format(
        unresolved="\n".join(f"- {line}" for line in unresolved),
    )


def recovery_outcome(passes, final, *, cut: bool) -> str | None:
    if not passes:
        return None
    if cut:
        return "cut"
    remaining = len(declared_unresolved(final))
    declared = len(passes[0]["unresolved"])
    if remaining == 0:
        return "resolved"
    return "partial" if remaining < declared else "still_unresolved"
```

Settings: in `core/constants.py` after `REACT_CROSS_TURN_HISTORY_BLOCK_FRACTION_DEFAULT`:

```python
# ADR-310: recovery passes a ReAct turn may take when its final message declares
# facts it could not obtain (an <unresolved> block). One pass re-opens the loop
# with the draft and the gaps; 0 switches the pass off.
REACT_RECOVERY_PASSES_MAX_DEFAULT: int = 1
```

In `core/config/agents.py` after `react_cross_turn_history_block_fraction`:

```python
    react_recovery_passes_max: int = Field(
        default=REACT_RECOVERY_PASSES_MAX_DEFAULT,
        ge=0,
        le=3,
        description=(
            "Recovery passes a ReAct turn may take when its final message declares facts "
            "it could not obtain (ADR-310): the loop resumes with the draft and the gaps "
            "instead of ending. 0 = off. The iteration, compute and tool budgets stay the "
            "hard bounds."
        ),
    )
```

State: `models.py` after `react_call_digests`:

```python
    # ADR-310: the recovery passes of this turn — one record per pass (the draft
    # removed from the thread, its predecessor's id, the declared gaps).
    react_recovery_passes: list[dict[str, Any]]
```

`react_budget.py`: `ReactTurnReset.react_recovery_passes: list[dict[str, Any]]` and in `react_turn_reset()`: `react_recovery_passes=[]` with the comment « ADR-310: a turn starts with no recovery pass ».

Env (main files, after `REACT_CROSS_TURN_HISTORY_BLOCK_FRACTION`):

```
REACT_RECOVERY_PASSES_MAX=1                                  # ADR-310: recovery passes a ReAct turn may take when its answer declares facts it could not obtain — the loop resumes with the draft and the gaps (0 = off, at most 3)
```

Demonstrator files: a comment line `# ADR-310: recovery passes when a ReAct answer declares missing facts (0 = off).` then `REACT_RECOVERY_PASSES_MAX=1`.

- [ ] **Step 4: Run — expect PASS** (same command as Step 2, plus `tests/unit/core/test_config_constants.py`)

- [ ] **Step 5: Checkpoint.**

---

### Task 4: Wire the pass into the loop — router, graph, call node, finalize, metric

**Files:**
- Modify: `apps/api/src/domains/agents/constants.py` (`NODE_REACT_RECOVERY = "react_recovery"` + `__all__`)
- Modify: `apps/api/src/domains/agents/nodes/routing.py` (`route_from_react_call_model`)
- Modify: `apps/api/src/domains/agents/graph.py` (node, mapping, edge)
- Modify: `apps/api/src/domains/agents/nodes/react_nodes.py` (`react_call_model_node`, `react_finalize_node`)
- Modify: `apps/api/src/infrastructure/observability/metrics_react.py` (`react_recovery_turns_total`)
- Modify: `infrastructure/observability/grafana/dashboards/20-react-browser.json` (panel id 76)
- Test: `apps/api/tests/unit/domains/agents/nodes/test_routing_react.py`, `apps/api/tests/unit/domains/agents/nodes/test_react_recovery_wiring.py` (create), `apps/api/tests/agents/test_graph_build.py`

**Interfaces:**
- Consumes: Task 3's `should_recover`, `react_recovery_node`, `with_recovery_directives`, `recovery_outcome`.
- Produces: `react_agent_result["recovery"] = {"passes": int, "outcome": str}` when a pass happened; metric `react_recovery_turns_total{outcome}`.

- [ ] **Step 1: Write the failing tests**

In `test_routing_react.py`:

```python
    def test_a_declared_gap_routes_to_the_recovery_pass(self) -> None:
        ai = AIMessage(content="x <unresolved>A</unresolved>", id="d1")
        state: dict = {
            "messages": [HumanMessage("q", id="h1"), ai],
            "react_iteration": 2,
            "react_max_iterations_effective": 70,
        }
        assert route_from_react_call_model(state) == NODE_REACT_RECOVERY
```

`test_react_recovery_wiring.py` (the `sent` fixture of `test_react_cross_turn_cache_wiring.py`, repeated here):

```python
async def test_the_call_shows_the_directive_after_the_anchor(state, sent) -> None:
    state["react_recovery_passes"] = [{"anchor_id": "t1", "draft": "D", "unresolved": ["A"]}]
    await rn.react_call_model_node(state, config={})
    ids = [m.id for m in sent[0]]
    at = ids.index("t1")
    assert isinstance(sent[0][at + 1], AIMessage) and sent[0][at + 1].content == "D"
    assert isinstance(sent[0][at + 2], HumanMessage)
    assert "RECOVERY LADDER" in str(sent[0][at + 2].content)


async def test_the_directive_survives_a_resume(state, sent) -> None:
    """The directive is composed from the checkpointed state, so a resumed call shows it again."""
    state["react_recovery_passes"] = [{"anchor_id": "t1", "draft": "D", "unresolved": ["A"]}]
    await rn.react_call_model_node(state, config={})
    await rn.react_call_model_node(state, config={})
    assert all(any("RECOVERY LADDER" in str(m.content) for m in call) for call in sent)


async def test_the_directive_never_reaches_the_checkpoint(state, sent) -> None:
    state["react_recovery_passes"] = [{"anchor_id": "t1", "draft": "D", "unresolved": ["A"]}]
    result = await rn.react_call_model_node(state, config={})
    assert [m.id for m in result["messages"]] == ["out"]


async def test_finalize_reports_the_outcome() -> None:
    state = {
        "messages": [HumanMessage("q", id="h1"), AIMessage("answer", id="f1")],
        "react_iteration": 5,
        "react_elapsed_seconds": 1.0,
        "react_recovery_passes": [{"anchor_id": "h1", "draft": "D", "unresolved": ["A"]}],
    }
    result = await rn.react_finalize_node(state, {})
    assert result["react_agent_result"]["recovery"] == {"passes": 1, "outcome": "resolved"}


async def test_finalize_without_a_pass_reports_nothing() -> None:
    state = {"messages": [HumanMessage("q"), AIMessage("answer")], "react_iteration": 2}
    result = await rn.react_finalize_node(state, {})
    assert "recovery" not in result["react_agent_result"]
```

In `tests/agents/test_graph_build.py::test_graph_has_correct_nodes` add `"react_recovery"` to `expected_nodes`.

- [ ] **Step 2: Run — expect FAIL.**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/test_routing_react.py tests/unit/domains/agents/nodes/test_react_recovery_wiring.py tests/agents/test_graph_build.py -q --no-cov`

- [ ] **Step 3: Implement**

`routing.py`, in `route_from_react_call_model`, return type `Literal["react_execute_tools", "react_finalize", "react_recovery"]`, before the final « No tool_calls » finalize:

```python
    # ADR-310: a final message that declares facts it could not obtain buys a
    # bounded recovery pass instead of ending the turn.
    from src.domains.agents.nodes.react_recovery import should_recover

    if should_recover(state):
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_react_call_model",
            decision=NODE_REACT_RECOVERY,
        ).inc()
        return NODE_REACT_RECOVERY
```

(import `NODE_REACT_RECOVERY` beside the two local constants).

`graph.py`: import `react_recovery_node`, `graph.add_node(NODE_REACT_RECOVERY, react_recovery_node)`, add `NODE_REACT_RECOVERY: NODE_REACT_RECOVERY` to the `route_from_react_call_model` mapping, `graph.add_edge(NODE_REACT_RECOVERY, NODE_REACT_CALL_MODEL)`, and extend the flow comment.

`react_nodes.py`, `react_call_model_node`, right after `compose_turn_messages(...)`:

```python
    # ADR-310: a recovery pass shows the model its draft and its gaps right after
    # the draft's place — composed here, never written to the thread.
    messages = with_recovery_directives(messages, state.get("react_recovery_passes") or [])
```

`react_finalize_node`, before building `react_result`:

```python
    passes = state.get("react_recovery_passes") or []
    outcome = recovery_outcome(passes, last_message, cut=pending_tool_calls)
```

then `if outcome is not None: react_result["recovery"] = {"passes": len(passes), "outcome": outcome}` and `react_recovery_turns_total.labels(outcome=outcome).inc()`; add `recovery_passes=len(passes)` to the `react_finalize_complete` log.

`metrics_react.py`:

```python
react_recovery_turns_total = Counter(
    "react_recovery_turns_total",
    "ReAct turns that took at least one recovery pass (ADR-310), by what the "
    "passes achieved: `resolved` (the final answer declares no gap), `partial` "
    "(fewer gaps than first declared), `still_unresolved`, `cut` (a budget ended "
    "the loop during the pass). A high `still_unresolved` share means the ladder "
    "finds no source for those facts; a rising total, that tools serve less.",
    ["outcome"],
)
```

Dashboard 20: panel id 76, `timeseries`, title « Recovery Passes (by outcome) », `gridPos {"h": 8, "w": 12, "x": 0, "y": 102}`, expr `sum by (outcome) (rate(react_recovery_turns_total[$__rate_interval])) or vector(0)`, legend `{{outcome}}`, `noValue` "0", description stating ADR-310 and the four outcomes.

- [ ] **Step 4: Run — expect PASS**, plus `test_metric_coverage_ratchet_guard.py` and the dashboards tests (`-k "dashboard or metric"`).

- [ ] **Step 5: Checkpoint.**

---

### Task 5: The doctrine — ReAct prompt, computation block, response authority

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/react_agent_prompt.txt`
- Modify: `apps/api/src/domains/agents/prompts/v1/react_computation_prompt.txt`
- Modify: `apps/api/src/domains/agents/prompts/v1/response_system_prompt_base.txt`
- Test: `apps/api/tests/unit/domains/agents/prompts/test_react_recovery_doctrine.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""The ReAct doctrine recovers before it concludes (ADR-310)."""

from __future__ import annotations

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit


def _static(name: str) -> str:
    return load_prompt(name).split(DYNAMIC_CONTEXT_MARKER, 1)[0]


class TestTheReactPrompt:
    def test_a_result_is_verified_against_the_request(self) -> None:
        assert "VERIFY" in _static("react_agent_prompt")

    def test_the_ladder_replaces_the_narrow_triggers(self) -> None:
        static = _static("react_agent_prompt")
        assert "RECOVERY LADDER" in static
        assert "Never stall the primary intent for secondary enrichment" not in static
        assert "SELF-CORRECTION & RECOVERY" not in static and "ZERO-RESULT HANDLING" not in static

    def test_the_final_message_declares_gaps_and_fallback_sources(self) -> None:
        static = _static("react_agent_prompt")
        assert "<unresolved>" in static and "(fallback)" in static

    def test_the_exemplar_passes_no_relative_date(self) -> None:
        assert 'date="tomorrow"' not in load_prompt("react_agent_prompt")

    def test_no_attempt_count_is_promised(self) -> None:
        """A prompt states what the code enforces (ADR-284): nothing counts attempts per fact."""
        assert "2 alternate attempts" not in load_prompt("react_agent_prompt")


def test_the_script_rung_lives_where_the_sandbox_is_bound() -> None:
    assert "RECOVERY LADDER" in load_prompt("react_computation_prompt")


def test_the_response_states_fallback_sources_and_gaps() -> None:
    authority = load_prompt("response_system_prompt_base").split("<DataAuthority>", 1)[1]
    authority = authority.split("</DataAuthority>", 1)[0]
    assert "fallback source" in authority and "unresolved" in authority
```

- [ ] **Step 2: Run — expect FAIL.**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/test_react_recovery_doctrine.py tests/unit/domains/agents/prompts/test_absolute_dates_directive.py -q --no-cov`

- [ ] **Step 3: Edit the prompts**

`react_agent_prompt.txt` — OBSERVE (step 3), replace the two sub-bullets with:

```
   - VERIFY: A result counts only if it answers what you asked — the right entity, date or period, place, and complete (a list the tool says it cut, or a partial answer, is not complete). A result that answers another question is an OBSTACLE, exactly like an error.
   - OBSTACLES: Every fact your answer will state — cross-check facts included — goes through the RECOVERY LADDER (see Rules) when it is missing, wrong or unverifiable. Keep the results you already hold while you recover the rest.
```

CROSS-CHECK DEPTH: append « Recovering a cross-check you already started is not a new cross-check. »
DECIDE: replace « If blocked after retries: document the gap and finalize. » with « If a fact is still missing after the RECOVERY LADDER: declare it in <unresolved> and finalize. »

Rules: delete « NEVER return an empty result without at least one query relaxation attempt. », ZERO-RESULT HANDLING, SELF-CORRECTION & RECOVERY and « Do NOT call the same tool with identical arguments twice. »; add after AMBIGUITY RESOLUTION:

```
- ABSOLUTE DATES: Resolve every relative date or time expression, in any language, against the Date and Timezone in <Context> into an ISO 8601 value before passing it to a tool. When an expression is ambiguous (e.g. "tomorrow" shortly after midnight), choose the most likely reading and log it as an assumption.
- RECOVERY LADDER: For each fact that is missing, wrong or unverifiable, climb in order and stop at the first rung that delivers it:
  1. Your own call — correct the parameters (an absolute date, an exact value, a wider window, a relaxed query) and call again; an error payload says what to fix.
  2. Another source — a sibling tool of the same domain, then, for public facts, the web search or page fetch tools of this turn's list. Mark the fact with the source you used.
  3. Conclude — list the fact in <unresolved> with the rungs you tried.
  Never repeat a call that already failed with the same arguments, and stop climbing when no rung left can bring new information.
```

Exemplar: `calendar_get_events(time_min="<tomorrow 00:00, ISO 8601>", time_max="<tomorrow 23:59, ISO 8601>")` and `arrival_time="<tomorrow 12:30, ISO 8601>"`.

FinalResponse, add:

```
- A fact obtained outside the tool dedicated to its domain carries its source: "Source: <site or tool> (fallback)".
- Close the message with <unresolved>...</unresolved>, one line per fact the answer needs but could not obtain, each with the rungs you tried; omit the block entirely when nothing is missing.
```

`react_computation_prompt.txt`, job 3, append: « It is also the RECOVERY LADDER's rung before concluding, for a fact your tools could not deliver. »

`response_system_prompt_base.txt`, `<DataAuthority>`, two lines before `</DataAuthority>`:

```
A fact the current turn data marks as coming from a fallback source is stated with that source, in a few words.
Facts the current turn data lists as unresolved are missing: say so, with what was tried — never an estimate.
```

- [ ] **Step 4: Run all prompt tests and guards — expect PASS**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/ tests/unit/domains/agents/nodes/ -q --no-cov`

- [ ] **Step 5: Checkpoint.**

---

### Task 6: The loop, end to end with a scripted model

**Files:**
- Test: `apps/api/tests/unit/domains/agents/nodes/test_react_recovery_loop.py` (create)

- [ ] **Step 1: Write the tests** (drive the real nodes and the real reducer; the model is scripted)

```python
"""A declared gap runs one recovery pass, and the thread keeps one answer (ADR-310)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.domains.agents.constants import NODE_REACT_EXECUTE_TOOLS, NODE_REACT_FINALIZE, NODE_REACT_RECOVERY
from src.domains.agents.models import add_messages_with_truncate
from src.domains.agents.nodes import react_nodes as rn
from src.domains.agents.nodes.react_recovery import react_recovery_node
from src.domains.agents.nodes.routing import route_from_react_call_model

pytestmark = pytest.mark.unit


def _apply(state: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        state[key] = add_messages_with_truncate(state[key], value) if key == "messages" else value


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A scripted model: each call pops the next reply and records what it was sent."""
    script: dict[str, Any] = {"replies": [], "sent": []}
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", False)
    monkeypatch.setattr(settings, "react_recovery_passes_max", 1)

    async def fake_stream(_llm: Any, messages: list[BaseMessage], emit: Any, config: Any) -> AIMessage:
        script["sent"].append(list(messages))
        reply: AIMessage = script["replies"].pop(0)
        return reply

    monkeypatch.setattr("src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream)
    return script


def _turn() -> dict[str, Any]:
    return {
        "messages": [HumanMessage("Weather in Lyon tomorrow?", id="h1")],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_system_blocks": ["You are LIA."],
        "react_iteration": 0,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 0.0,
        "react_recovery_passes": [],
    }


async def test_a_gap_is_recovered_and_the_draft_leaves_the_thread(model: dict[str, Any]) -> None:
    model["replies"] = [
        AIMessage("Draft. <unresolved>- forecast for tomorrow</unresolved>", id="d1"),
        AIMessage("", id="a2", tool_calls=[{"id": "c2", "name": "forecast", "args": {"date": "2026-09-25"}}]),
        AIMessage("Sunny, 21 degrees.", id="f1"),
    ]
    state = _turn()
    _apply(state, await rn.react_call_model_node(state, config={}))
    assert route_from_react_call_model(state) == NODE_REACT_RECOVERY
    _apply(state, await react_recovery_node(state, {}))
    assert "d1" not in [m.id for m in state["messages"]]

    _apply(state, await rn.react_call_model_node(state, config={}))
    second = model["sent"][1]
    assert [type(m).__name__ for m in second[-3:]] == ["HumanMessage", "AIMessage", "HumanMessage"]
    assert "RECOVERY LADDER" in str(second[-1].content)
    assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS

    _apply(state, {"messages": [ToolMessage("Sunny", tool_call_id="c2", id="t2")]})
    _apply(state, await rn.react_call_model_node(state, config={}))
    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
    result = await rn.react_finalize_node(state, {})
    assert result["react_agent_result"]["recovery"] == {"passes": 1, "outcome": "resolved"}
    assert [m.id for m in state["messages"]] == ["h1", "a2", "t2", "f1"]


async def test_a_pass_that_changes_nothing_ends_the_turn(model: dict[str, Any]) -> None:
    gap = "<unresolved>- forecast for tomorrow</unresolved>"
    model["replies"] = [AIMessage(f"Draft. {gap}", id="d1"), AIMessage(f"Still. {gap}", id="d2")]
    state = _turn()
    _apply(state, await rn.react_call_model_node(state, config={}))
    _apply(state, await react_recovery_node(state, {}))
    _apply(state, await rn.react_call_model_node(state, config={}))
    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
    result = await rn.react_finalize_node(state, {})
    assert result["react_agent_result"]["recovery"] == {"passes": 1, "outcome": "still_unresolved"}
    assert [m.id for m in state["messages"]] == ["h1", "d2"]
```

- [ ] **Step 2: Run — expect PASS** (Tasks 3-5 in place); if FAIL, fix the code, not the test.

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/test_react_recovery_loop.py -q --no-cov`

- [ ] **Step 3: Checkpoint.**

---

### Task 7: Validation bench (paid, ≤ 2 USD, no Anthropic)

**Files:**
- Create: `apps/api/scripts/react/measure_recovery.py`
- Modify: `Taskfile.yml` (`react:recovery:measure`, the `react:selection:measure` shape)

**Interfaces:**
- Consumes: `load_prompt("react_agent_prompt")` rendered with neutral values; `should_recover`, `with_recovery_directives`, `declared_unresolved`, `recovery_outcome`; `get_llm("react_agent", config_override=...)` as `scripts/measure_journal_themes.py` does.

- [ ] **Step 1: Write the harness**: six scenarios (wrong day served, error then success once corrected, empty until relaxed, dedicated tool down and web search answers, truncated list, clean control), each a small set of `StructuredTool` stubs with deterministic behaviour; a loop that mirrors the node logic through the SAME functions (model call, tool execution, recovery predicate, directive composition); `--models provider:model,...` refusing `anthropic`; `--reps`; per run: tokens in/out, cost from the pricing table, fact obtained, gap declared, repeated failing call, passes, outcome; a JSON report and a summary table.
- [ ] **Step 2: Dry run** (`--dry-run`: stubs and harness only, no model call) — expect every scenario to print its tool set.
- [ ] **Step 3: One-rep probe** on the three families, cost extrapolated; stop if the extrapolation exceeds 2 USD.
- [ ] **Step 4: Full run** (3 reps), report kept outside the repository (scratchpad).
- [ ] **Step 5: Checkpoint** — findings feed ADR-310's Consequences.

---

### Task 8: Documentation and final gates

**Files:**
- Create: `docs/architecture/ADR-310-ReAct-Turn-Judged-On-Its-Result.md`
- Modify: `docs/architecture/ADR_INDEX.md`, `CLAUDE.md` (six invariants + pointer), `docs/technical/REACT_EXECUTION_MODE.md`, `docs/ARCHITECTURE_LANGRAPH.md`, `docs/guides/GUIDE_TOOL_CREATION.md`, the spec (refinements)
- Generated: `AGENTS.md` (`task docs:sync-agents`), counts (`task release:sync-counts`)

- [ ] **Step 1: Write ADR-310** (Context: the measured turn and four causes; Decision: protocol, predicate, node, transient directive, draft removal at the pass, doctrine, dates, weather contract, setting, metric; Consequences: bench figures; Rejected: B, C, a multilingual date reader, a per-fact counter, a persisted directive, a second lookup, pipeline recovery; References).
- [ ] **Step 2: Index, CLAUDE.md, technical docs, guide**; `task docs:sync-agents`; `task release:sync-counts`.
- [ ] **Step 3: Gates**: `task lint:backend`, `task lint:cc`, `task lint:cycles`, `task lint:mypy-debt`, `task lint:hygiene`, `task test:backend:unit:fast`, `cd apps/api && .venv/Scripts/pytest tests/agents/test_graph_build.py -q --no-cov`, `task lint:docs:preview`; raise any ratchet that improved (`task ratchet:update`, `task ratchet:metrics`).
- [ ] **Step 4: Runtime proof on the dev API** (health 200 after reload; one ReAct turn replaying the 2026-09-23 question, logs show the ISO date or the refusal then the correction, and the recovery outcome when a gap is declared).
- [ ] **Step 5: Memory** (`project_react_result_oriented_recovery.md`, index line) and the final report.
