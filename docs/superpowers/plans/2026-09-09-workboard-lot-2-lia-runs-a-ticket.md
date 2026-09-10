# Workboard — Lot 2 (LIA exécute un ticket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ticket assigned to LIA is executed out of turn through the pipeline a routine already uses; its answer becomes a ticket comment; a run that needs the person stops honestly in `waiting`; the two archived rows are marked `hidden` so the chat stays quiet unless the reader asked to follow the ticket; and the hidden rows are bounded and visible.

**Architecture:** The routine engine is EXTRACTED into a shared module both callers use. The run's origin travels through a ContextVar (the `capability_directive_ctx` pattern), so `AgentService.stream_chat_response` gains no parameter — it has 9 logical lines of headroom. The gate learns to refuse a `draft` in an unattended source, and records refusals on that same ContextVar so the settle reads a code rather than prose.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x, APScheduler, LangGraph 1.x, pytest, Testcontainers PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-09-08-workboard-design.md` (§3 D1-D5, D9-D12, D18; §6 the run; §7 notifications; §12 registers). **The spec says ADR-274; the shipped ADR is [ADR-276](../../architecture/ADR-276-Workboard.md)** — two ADR numbers were taken by another session between the design and the build.

## Global Constraints

- Python 3.14, Black line-length 100, Ruff, MyPy strict, Google docstrings, English throughout. No `print`; `structlog` only; ids and counts at INFO, never a ticket title or a comment body.
- **Size headroom, measured 2026-09-09 — these are the plan's hard constraints:**

| File | SLOC | Cap | Headroom |
|---|---|---|---|
| `domains/agents/api/service.py` | 1028 | 1037 (frozen) | **9** |
| `domains/conversations/repository.py` | 685 | 688 (frozen) | **3** |
| `domains/conversations/service.py` | 789 | 805 (frozen) | 16 |
| `infrastructure/scheduler/scheduled_action_executor.py` | 488 | 600 (global) | 112 |

  A frozen cap NEVER rises (`task ratchet:update` only lowers). Anything that does not fit is an EXTRACTION, and an extraction must leave the frozen file smaller than it found it.
- Cyclomatic complexity < 15 on every new or touched function (`scripts/audit/measure_cc.py`).
- Every datetime tz-aware UTC; no in-place JSONB mutation; `contextlib.suppress` with a written reason instead of a bare `except: pass`.
- A quota refusal is logged as **skipped**, never as failed (ADR-272).
- Every new Prometheus metric must be referenced by a Grafana panel or an alert, or the metric-coverage ratchet reds the build.
- No git commit or push: commit messages are PROPOSED at each task's end.
- Runtime verification goes through `lia-api-dev`; unit tests may run from `apps/api/.venv`.

---

## File map

| File | Responsibility |
|---|---|
| `apps/api/src/domains/agents/api/run_origin.py` (create) | the ContextVar: what an out-of-turn run is, and the refusals it collected |
| `apps/api/src/domains/agents/api/archive_metadata.py` (modify) | one enricher stamps `hidden` + the ticket reference on the assistant row |
| `apps/api/src/domains/agents/api/archive_first.py` (modify) | the same stamp on the synthetic user row |
| `apps/api/src/domains/conversations/message_visibility.py` (create) | the ONE read predicate, extracted so the frozen repository shrinks |
| `apps/api/src/domains/conversations/repository.py` (modify) | every message read applies the predicate; `include_hidden` opt-out |
| `apps/api/alembic/versions/…_workboard_hidden_messages.py` (create) | `conversation_messages.hidden` (boolean, server default false) + partial index |
| `apps/api/src/domains/agents/effects/gate.py` (modify) | `draft` is refused in an unattended source; the refusal is collected |
| `apps/api/src/infrastructure/scheduler/out_of_turn_run.py` (create) | the engine extracted from `execute_single_action` |
| `apps/api/src/infrastructure/scheduler/scheduled_action_executor.py` (modify) | delegates to the engine; the file SHRINKS |
| `apps/api/src/infrastructure/scheduler/workboard_runner.py` (create) | claim, run, settle, snapshot the cost, notify, reap, retention |
| `apps/api/src/domains/workboard/repository.py` (modify) | the claim, the settle, the cost snapshot, the retention read |
| `apps/api/src/domains/workboard/brief.py` (create) | the instruction a run receives |
| `apps/api/src/domains/agents/prompts/v1/workboard_ticket_brief_prompt.txt` (create) | the versioned prompt |
| `apps/api/src/domains/workboard/notifications.py` (create) | who is told what, under the follow flags |
| `apps/api/src/core/i18n_proactive.py` (modify) | the workboard notification titles and bodies, six languages |
| `apps/api/src/infrastructure/startup/schedulers.py` (modify) | register the sweep, jittered, flag-gated |
| `apps/api/src/domains/product/…` or the rollup (modify) | `lia_hidden_run_rows` / `lia_hidden_run_bytes` |
| `infrastructure/observability/grafana/dashboards/29-workboard.json` (create) | the panels the metrics need |

---

### Task 1: The run origin, and the hidden stamp

**Files:**
- Create: `apps/api/src/domains/agents/api/run_origin.py`
- Modify: `apps/api/src/domains/agents/api/archive_metadata.py`, `archive_first.py`
- Test: `apps/api/tests/unit/domains/agents/api/test_run_origin.py`

**Interfaces:**
- Produces: `RunOrigin` dataclass (`kind: str`, `ticket_id: str`, `run_id: str`, `refusals: list[tuple[str, str]]`), `out_of_turn_origin_ctx: ContextVar[RunOrigin | None]`, `current_origin() -> RunOrigin | None`, `record_refusal(tool_name: str, error_code: str) -> None`, `with_hidden_stamp(metadata: dict) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/domains/agents/api/test_run_origin.py
"""What an out-of-turn run says about itself, and how a row carries it."""

from __future__ import annotations

import pytest

from src.domains.agents.api.run_origin import (
    RunOrigin,
    current_origin,
    out_of_turn_origin_ctx,
    record_refusal,
    with_hidden_stamp,
)

pytestmark = pytest.mark.unit


class TestOutsideARun:
    def test_no_origin_by_default(self) -> None:
        assert current_origin() is None

    def test_the_stamp_is_a_no_op(self) -> None:
        """A chat turn's rows are never hidden."""
        assert with_hidden_stamp({"type": "answer"}) == {"type": "answer"}

    def test_recording_a_refusal_outside_a_run_is_harmless(self) -> None:
        record_refusal("send_email_tool", "confirmation_impossible_unattended")


class TestInsideARun:
    def test_the_stamp_marks_the_row_and_names_its_ticket(self) -> None:
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        token = out_of_turn_origin_ctx.set(origin)
        try:
            stamped = with_hidden_stamp({"type": "answer"})
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert stamped["hidden"] is True
        assert stamped["workboard"] == {"ticket_id": "t-1", "run_id": "r-1"}
        assert stamped["type"] == "answer", "the caller's keys survive"

    def test_the_stamp_returns_a_new_dict(self) -> None:
        """One turn's metadata can never leak into another's."""
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        token = out_of_turn_origin_ctx.set(origin)
        original = {"type": "answer"}
        try:
            stamped = with_hidden_stamp(original)
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert stamped is not original
        assert "hidden" not in original

    def test_refusals_accumulate_in_order(self) -> None:
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        token = out_of_turn_origin_ctx.set(origin)
        try:
            record_refusal("send_email_tool", "confirmation_impossible_unattended")
            record_refusal("delete_event_tool", "confirmation_missing")
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert origin.refusals == [
            ("send_email_tool", "confirmation_impossible_unattended"),
            ("delete_event_tool", "confirmation_missing"),
        ]

    def test_a_child_task_sees_the_origin(self) -> None:
        """A ContextVar is copied into a task at creation — the settle reads
        refusals recorded deep inside the graph."""
        import asyncio

        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")

        async def inner() -> str | None:
            seen = current_origin()
            return seen.ticket_id if seen else None

        async def outer() -> str | None:
            token = out_of_turn_origin_ctx.set(origin)
            try:
                return await asyncio.create_task(inner())
            finally:
                out_of_turn_origin_ctx.reset(token)

        assert asyncio.run(outer()) == "t-1"
```

- [ ] **Step 2: Run it, expect ModuleNotFoundError**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/api/test_run_origin.py -q --no-cov`

- [ ] **Step 3: Write the module**

```python
# apps/api/src/domains/agents/api/run_origin.py
"""What an out-of-turn run is, published to the turn it drives (ADR-276).

``AgentService.stream_chat_response`` has NINE logical lines of headroom under
its frozen cap, so a run cannot hand it a parameter. It publishes a ContextVar
instead — the shape ``capability_directive_ctx`` already uses — and two readers
consult it:

- the archive enrichers, which stamp both rows of the run as ``hidden`` so the
  chat stays quiet while the record stays whole (the decision register POINTS
  at those rows; a run that archived nothing would look like a deleted
  conversation);
- the effect gate, which records the refusals it issues, so a run's settle
  reads a CODE and never the model's prose.

The ContextVar is copied into every task created under it, so a refusal raised
deep inside the graph reaches the settle.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunOrigin:
    """The out-of-turn run driving the current turn.

    Attributes:
        kind: Which surface started it — ``workboard`` today.
        ticket_id: What it is about, as a string (a metadata value).
        run_id: The turn's own id, shared with the three registers.
        refusals: ``(tool, error_code)`` the gate refused, in order.
    """

    kind: str
    ticket_id: str
    run_id: str
    refusals: list[tuple[str, str]] = field(default_factory=list)


out_of_turn_origin_ctx: ContextVar[RunOrigin | None] = ContextVar(
    "out_of_turn_origin", default=None
)


def current_origin() -> RunOrigin | None:
    """The run driving this turn, or None inside an ordinary chat turn."""
    return out_of_turn_origin_ctx.get()


def record_refusal(tool_name: str, error_code: str) -> None:
    """Note that the gate refused a tool, for the settle to read.

    Best-effort by contract: outside a run there is nothing to record, and the
    register must never cost the turn its answer.

    Args:
        tool_name: The capability that was refused.
        error_code: The gate's stable code.
    """
    origin = out_of_turn_origin_ctx.get()
    if origin is not None:
        origin.refusals.append((tool_name, error_code))


def with_hidden_stamp(metadata: dict[str, Any]) -> dict[str, Any]:
    """Mark a row as belonging to an out-of-turn run, when one is driving.

    Returns a NEW dict rather than mutating: one turn's metadata must never
    leak into another's (the rule every enricher in this package follows).

    Args:
        metadata: What the caller assembled.

    Returns:
        The metadata, stamped when a run is driving, unchanged otherwise.
    """
    origin = out_of_turn_origin_ctx.get()
    if origin is None:
        return metadata
    return {
        **metadata,
        "hidden": True,
        origin.kind: {"ticket_id": origin.ticket_id, "run_id": origin.run_id},
    }
```

- [ ] **Step 4: Wire the two enrichers**

In `archive_metadata.py`, add `with_hidden_stamp` to the enricher chain (read the file: the chain is branch-free, each enricher decides for itself, so this one fits the shape exactly). In `archive_first.py`, apply it to the metadata the synthetic user row carries.

Add to the test file, in a new class, one assertion per enricher: the stamp reaches the row's metadata when a run is driving, and does not when none is.

- [ ] **Step 5: Run and commit**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/api -q --no-cov` → PASS.
Verify the frozen file did not grow: `apps/api/.venv/Scripts/python scripts/audit/measure_sloc.py` semantics on `domains/agents/api/service.py` — it must still be 1028.

Proposed commit: `feat(workboard): the out-of-turn run origin, and the hidden stamp (ADR-276, lot 2)`

---

### Task 2: The hidden column, and the ONE read predicate

**Files:**
- Create: `apps/api/src/domains/conversations/message_visibility.py`
- Create: `apps/api/alembic/versions/<generated>_workboard_hidden_messages.py`
- Modify: `apps/api/src/domains/conversations/models.py`, `repository.py`
- Test: `apps/api/tests/unit/domains/conversations/test_message_visibility.py`, `apps/api/tests/integration/domains/conversations/test_hidden_messages_db.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `ConversationMessage.hidden` (bool, NOT NULL, server default false); `visible_only(stmt, *, include_hidden: bool)` in `message_visibility.py`; every repository message read gains `include_hidden: bool = False`.

**The size constraint decides the shape.** `conversations/repository.py` has **3 logical lines** of headroom under a frozen cap. Adding a predicate inline to seven reads is impossible. So the predicate is a module of its own, and the repository's reads each call it — a net change of roughly zero, which the guard will confirm.

- [ ] **Step 1: Generate a UNIQUE revision id**

```bash
cd apps/api && python -c "
import uuid, pathlib, re
existing = set()
for p in pathlib.Path('alembic/versions').glob('*.py'):
    m = re.search(r'^revision(?:: str)? = \"([0-9a-f]+)\"', p.read_text(encoding='utf-8'), re.M)
    if m: existing.add(m.group(1))
while True:
    c = uuid.uuid4().hex[:12]
    if c not in existing and not c.isdigit(): print(c); break
"
```

**This step is not optional.** In lot 1 the plan's hand-written id collided with an August migration and `alembic heads` reported a CYCLE. Also re-read the current head (`.venv/Scripts/python -m alembic heads`) — another session may have added migrations.

- [ ] **Step 2: Write the failing predicate test**

```python
# apps/api/tests/unit/domains/conversations/test_message_visibility.py
"""One predicate decides which archived rows a reader sees (ADR-276).

An out-of-turn run archives its two rows like any turn — the decision register
POINTS at them, and a run that archived nothing would be indistinguishable from
a deleted conversation. What keeps the chat quiet is the READ, and this is it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.domains.conversations.message_visibility import visible_only
from src.domains.conversations.models import ConversationMessage

pytestmark = pytest.mark.unit


def _sql(include_hidden: bool) -> str:
    stmt = visible_only(select(ConversationMessage), include_hidden=include_hidden)
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_a_reader_sees_only_what_was_not_hidden() -> None:
    assert "hidden" in _sql(include_hidden=False)


def test_the_export_asks_for_everything(self=None) -> None:
    """The archive and the registers read the whole record."""
    assert "hidden" not in _sql(include_hidden=True)


def test_the_predicate_reads_a_column_not_a_json_key() -> None:
    """A boolean column costs the pagination index a filter; a JSONB test costs
    a parse per row on the hottest read in the application."""
    assert "message_metadata" not in _sql(include_hidden=False)
```

- [ ] **Step 3: The column, the model, the migration**

Model (`conversations/models.py`, on `ConversationMessage`):

```python
    hidden: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Row of an out-of-turn run: kept in full, excluded from the chat read.",
    )
```

Migration: `op.add_column` with the SAME comment string (the F042 drift guard compares them), plus a partial index for the retention sweep:

```python
    op.create_index(
        "ix_conversation_messages_hidden_workboard",
        "conversation_messages",
        [sa.text("(message_metadata -> 'workboard' ->> 'ticket_id')")],
        postgresql_where=sa.text("hidden"),
    )
```

An expression index is not round-trippable by autogenerate; check `include_object` in `alembic/env.py` (`test_schema_drift.py::test_excludes_un_round_trippable_indexes` shows the exclusion list) and add it there if the replay check reports a spurious diff.

- [ ] **Step 4: The predicate module and the repository wiring**

```python
# apps/api/src/domains/conversations/message_visibility.py
"""Which archived rows a reader sees, decided once (ADR-276).

An out-of-turn run archives its two rows exactly like any turn: archive-first
(ADR-117) and the decision register's two pointers both depend on it, and a run
that archived nothing would leave a register row indistinguishable from a
deleted conversation. What keeps the chat quiet is this predicate, applied at
the READ.

It lives in its own module because ``conversations/repository.py`` sits three
logical lines under a frozen cap: a predicate written inline seven times would
not fit, and a cap never rises.

``include_hidden=True`` is for the readers that must see the whole record — the
account export, the three registers, and the retention sweep. A guard refuses
any new message read that names neither.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.sql import Select

from src.domains.conversations.models import ConversationMessage

_S = TypeVar("_S", bound=Select)


def visible_only(stmt: _S, *, include_hidden: bool) -> _S:
    """Narrow a message read to what a chat reader may see.

    Args:
        stmt: The statement to narrow.
        include_hidden: True for the export and the registers, which read the
            whole record.

    Returns:
        The statement, narrowed unless the caller asked for everything.
    """
    if include_hidden:
        return stmt
    return stmt.where(ConversationMessage.hidden.is_(False))
```

Apply it in `repository.py` to: `get_messages_for_conversation` (line ~241), `get_messages_with_token_summaries` (~340), `get_conversation_with_messages` (~465, the `selectinload` needs its own `and_` on the relationship — read the code), `get_last_user_message` (~993), `get_proactive_messages_after` (~1055). Each gains `include_hidden: bool = False`. `delete_messages_for_conversation` and the token totals do NOT take the predicate: a reset removes everything, and a total says what ran on the account.

- [ ] **Step 5: The guard**

```python
# in apps/api/tests/unit/domains/conversations/test_message_visibility.py
class TestEveryReadDecides:
    def test_no_message_read_forgets_the_predicate(self) -> None:
        """A read that names neither ``visible_only`` nor ``include_hidden`` is
        a read that shows a run's transcript in the chat."""
        from pathlib import Path
        import ast

        source = Path("src/domains/conversations/repository.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            body = ast.get_source_segment(source, node) or ""
            reads_messages = "select(ConversationMessage)" in body or "ConversationMessage," in body
            decides = "visible_only" in body or "include_hidden" in body
            allowed = node.name in {
                "delete_messages_for_conversation",  # a reset removes everything
                "get_token_totals",  # a total says what RAN on the account
                "create_message",
                "update_message_tts",
                "merge_message_metadata",
                "mark_proactive_feedback_submitted",
            }
            if reads_messages and not decides and node.name not in allowed:
                offenders.append(node.name)
        assert offenders == [], f"message reads with no visibility decision: {offenders}"
```

Verify the allowlist against the real file before trusting it — the method names above were read on 2026-09-09 and a neighbouring session may have added one.

- [ ] **Step 6: Integration proof**

```python
# apps/api/tests/integration/domains/conversations/test_hidden_messages_db.py
```

Assert on a real server: a hidden row is absent from `get_messages_for_conversation` by default, present with `include_hidden=True`, counted by `get_token_totals`, and removed by `delete_messages_for_conversation`.

- [ ] **Step 7: Run every gate**

```
cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/conversations tests/unit/infrastructure/database -q --no-cov
PG_ADMIN_USER=<superuser> .venv/Scripts/python ../../scripts/db/replay_check_local.py
LIA_REQUIRE_DB=1 .venv/Scripts/python -m pytest tests/integration/domains/conversations -q --no-cov
```

Proposed commit: `feat(workboard): hidden run rows, and the one read predicate (ADR-276, lot 2)`

---

### Task 3: The gate refuses a draft in an unattended source

**Files:**
- Modify: `apps/api/src/domains/agents/effects/gate.py`
- Test: `apps/api/tests/unit/domains/agents/effects/test_gate_decision.py` (extend)

**Interfaces:**
- Consumes: `record_refusal` (Task 1).
- Produces: `decide_effect` refuses `draft` when the scope's source is unattended; the runtime records the refusal.

**Why this belongs in the gate.** Measured on the routine path: a `draft` tool raises a HITL interrupt that `execute_single_action` turns into a non-retryable `RuntimeError`, and the interrupt stays on the thread. The gate already refuses `confirm` for exactly this reason; a draft owes the same answer.

- [ ] **Step 1: Write the failing tests**

Extend `test_gate_decision.py` (a pure decision table, no I/O):

```python
class TestAnUnattendedRunCannotDraft:
    def test_a_draft_is_refused_when_nobody_can_answer_it(self) -> None:
        scope = EffectScope(source="scheduled", approved=False, ...)
        decision = decide_effect("draft", scope)
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == ERROR_CONFIRMATION_IMPOSSIBLE

    def test_a_draft_still_passes_in_an_attended_turn(self) -> None:
        """The 25 draft-producing tools must keep working in the chat."""
        scope = EffectScope(source="user", approved=False, ...)
        assert decide_effect("draft", scope).action is GateAction.PASS_THROUGH

    def test_a_draft_with_no_scope_at_all_passes(self) -> None:
        """No scope is not an unattended scope."""
        assert decide_effect("draft", None).action is GateAction.PASS_THROUGH
```

Read `EffectScope`'s real constructor before writing these — the fields above are indicative.

- [ ] **Step 2: Move `draft` out of the unconditional pass-through**

`PASS_THROUGH_POLICIES` currently holds `{"read", "sandboxed", "draft"}`. `draft` becomes conditional: pass-through when attended, refused when the scope's source is in `UNATTENDED_SOURCES`. Keep `decide_effect` pure and under CC 15.

- [ ] **Step 3: Record the refusal at the runtime, not in the pure function**

In `effects/runtime.py` (where the decision is acted on), call `record_refusal(tool_name, decision.error_code)` on every REFUSE. Best-effort, no I/O, no exception path.

- [ ] **Step 4: Run the gate suites**

```
cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/effects -q --no-cov
```
`test_gate_totality.py` enumerates every policy × scope combination — expect it to need the new row, and read it before editing.

Proposed commit: `feat(effects): an unattended run cannot draft either (ADR-276 amends ADR-263)`

---

### Task 4: The out-of-turn engine, extracted

**Files:**
- Create: `apps/api/src/infrastructure/scheduler/out_of_turn_run.py`
- Modify: `apps/api/src/infrastructure/scheduler/scheduled_action_executor.py`
- Test: `apps/api/tests/unit/infrastructure/scheduler/test_out_of_turn_run.py`; the EXISTING routine tests are the characterisation net

**Interfaces:**
- Produces: `RunRequest` (user, prompt, session_id, timeout, max_attempts, lock_conversation: bool, origin: RunOrigin | None), `RunResult` (text, outcome, error_code, run_id, interrupted: bool, refusals), `run_instruction(request) -> RunResult`.

- [ ] **Step 1: Characterise BEFORE extracting**

Run the existing routine tests and record the exact list: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/infrastructure/scheduler -q --no-cov`. They are the oracle that the extraction changed nothing. Do not edit them.

- [ ] **Step 2: Write the new module's tests first**

Cover, each as its own test: the inactive-user guard; the quota pre-check (`is_user_blocked_for_llm`, layer `workboard_runner`) returning `skipped_quota` and LOGGING « skipped »; the HITL-pending guard returning `skipped_busy`; a held `chat:active_run` lock returning `skipped_busy` WITHOUT running; the lock taken, heartbeated and released in a `finally` even on an exception; the transient-error retry with back-off; the timeout; `content_replacement` REPLACING the accumulated tokens (the routine lesson — a push body built from pre-post-processing text disagrees with the archived message).

- [ ] **Step 3: Extract**

Move the body of `execute_single_action`'s pipeline section into `run_instruction`. `scheduled_action_executor.py` keeps its condition gate, its propose-first branch, its run history and its notification, and calls the engine. **The file must SHRINK** — measure before and after.

- [ ] **Step 4: Prove nothing moved**

Re-run the characterisation set; every test green, none edited. Then `task test:backend:unit:fast`.

Proposed commit: `refactor(scheduler): one engine for an instruction run out of turn (ADR-276, lot 2)`

---

### Task 5: The workboard runner

**Files:**
- Create: `apps/api/src/infrastructure/scheduler/workboard_runner.py`, `apps/api/src/domains/workboard/brief.py`, `apps/api/src/domains/agents/prompts/v1/workboard_ticket_brief_prompt.txt`
- Modify: `apps/api/src/domains/workboard/repository.py` (claim, settle, cost, retention), `apps/api/src/infrastructure/startup/schedulers.py`
- Test: `apps/api/tests/unit/infrastructure/scheduler/test_workboard_runner.py`, `apps/api/tests/integration/domains/workboard/test_claim_db.py`

**Interfaces:**
- Consumes: `run_instruction` (Task 4), `RunOrigin` (Task 1), `WorkboardService`.
- Produces: `claim_next_ticket(db, now) -> WorkboardTicket | None`, `settle_run(...)`, `reap_stale_claims(db, older_than)`, `purge_hidden_rows(db, closed_before)`, `sweep_workboard_runs()`.

- [ ] **Step 1: The eligibility predicate as a table test**

Every combination of (assignee_kind, status, run_claimed_at, start_at, run_not_before, run_attempts, run_count) against expected eligibility. `idea` never runs. This is where a wrong predicate would run somebody's ticket at the wrong moment, so enumerate rather than sample.

- [ ] **Step 2: The claim, on real PostgreSQL**

`FOR UPDATE SKIP LOCKED` + a conditional `UPDATE … RETURNING` that sets `status='in_progress'`, `run_claimed_at`, `last_run_id`, and increments `run_attempts` AND `run_count`. Integration test with TWO independent sessions: exactly one wins.

**Watch the enum trap**: never put a bare enum member as the RESULT of a SQL expression (`case`, `literal`) on a `String` column — carry the column's type (`_status_literal` in `meetings/repository.py` is the canonical shape). Here the values are plain strings, so use `TicketStatus.IN_PROGRESS.value`.

- [ ] **Step 3: The settle, conditional on `last_run_id`**

`WHERE status='in_progress' AND last_run_id=:run_id`. A person who moved the ticket during the run WINS, and the late settle is a no-op that logs `workboard_run_settle_lost`. Test both.

- [ ] **Step 4: The brief**

`brief.py` composes: the ticket's title, its description, its parent's title and its siblings' titles when it is a child. **The OWNER's words only** — comments are excluded, a peer may have written them (ADR-167/170: data are never instructions). The prompt file is versioned and loaded through `load_prompt`; it carries no tunable number in prose (ADR-184).

- [ ] **Step 5: The settle branches**

- an answer, no refusal, no interrupt → LIA comment (the `content_replacement` text), status `validating`, outcome `success`;
- a refusal collected on the origin, or a `hitl_interrupt` chunk → comment « waiting for you: <tool> », status `waiting`, outcome `waiting`, and CLEAR the pending interrupt (`hitl_store.clear_interrupt`, the call `service.py:1469` already makes);
- transient exhausted / non-retryable → stays `in_progress`, outcome `failed`, `last_run_error` = typed code + bounded message.

- [ ] **Step 6: The cost snapshot**

ONE aggregate over `token_usage_logs` where `run_id = :run_id`, written to `last_run_tokens_in/out` and `last_run_cost_eur`. Never a join at render time: `token_usage_logs` is `BILLING_RETAINED` and outlives the account.

- [ ] **Step 7: The sweep, the reaper, the retention**

Register in `startup/schedulers.py` with `jitter=jitter_seconds_for(seconds=settings.workboard_run_sweep_seconds)` — a job without jitter aligns forever with its divisors (ADR-254). Flag-gated. The tick reaps stale claims, deletes the hidden rows of tickets closed longer than the retention window (ONE bounded DELETE), then claims and runs at most one ticket.

- [ ] **Step 8: Runtime proof**

On `lia-api-dev`: create a ticket assigned to LIA with no start date, wait two minutes, then assert — the comment exists, the status is `validating`, the cost is filled, the three ADR-263 registers hold rows under the run id whose decision row's two pointers resolve to HIDDEN rows, and the chat history endpoint shows nothing.

Proposed commit: `feat(workboard): LIA runs a ticket out of turn (ADR-276, lot 2)`

---

### Task 6: Notifications, metrics, dashboard

**Files:**
- Create: `apps/api/src/domains/workboard/notifications.py`
- Modify: `apps/api/src/core/i18n_proactive.py`, the metrics registry, `infrastructure/observability/grafana/dashboards/29-workboard.json`
- Test: `apps/api/tests/unit/domains/workboard/test_notifications.py`

- [ ] **Step 1: The recipient table as a parametrised test**

One case per (event × follow_owner × follow_assignee × who): run started/finished/comment follow the flags; « waiting for you » ALWAYS notifies the account the run belongs to; « assigned to you » ALWAYS notifies the new holder, once.

- [ ] **Step 2: The dispatch**

`NotificationDispatcher.dispatch(task_type="workboard")` inside `proactive_notification_effect(task_type="workboard")` — claimed BEFORE the push leaves, settled from `NotificationResult`, never from the absence of an exception. Metadata: `type=proactive_workboard`, `ticket_id`, `ticket_title`, `event`, `board_url`, `ticket_url`, and `intent` for `waiting`.

Titles and bodies are written sentences in `ProactiveMessages`, six languages, no model call: a notification about a ticket is a fact, not prose to personalise.

- [ ] **Step 3: Metrics and their panels**

`workboard_runs_total{outcome}`, `workboard_run_duration_seconds`, `workboard_notifications_total{event}`, `lia_hidden_run_rows`, `lia_hidden_run_bytes`. **Every one needs a panel or an alert** or the metric-coverage ratchet reds the build. A labelled counter that never fired exposes no series: each panel needs `... or vector(0)` and `"noValue": "0"`.

- [ ] **Step 4: Full gates**

```
task lint
task test:backend:unit:fast
task test:markers
LIA_REQUIRE_DB=1 pytest tests/integration/domains/workboard -q --no-cov
docker restart lia-api-dev && docker logs lia-api-dev --tail 60
```

Proposed commit: `feat(workboard): follow-gated notifications, metrics and dashboard (ADR-276, lot 2)`

---

## Test plan additions this lot brings

Beyond the per-task tests above, the lot's review runs:

1. **The characterisation net** — the routine tests, unedited, green before and after the extraction.
2. **The visibility guard** — no message read escapes the predicate (AST over the repository).
3. **Two-actor claim** on real PostgreSQL: exactly one worker wins.
4. **The settle race**: a person moves the ticket mid-run; the late settle is a no-op.
5. **The falsification pass**: break the lock check and prove the busy-skip test reds; break the predicate and prove the chat shows the run.
6. **The runtime proof**, extended from lot 1's script: a full run end to end, follow off then on, and a `waiting` stop with a working intent link.

## What this lot does NOT do

No agent tools (lot 3), no UI (lot 4), no connection-removal hook (lot 5), no heartbeat source (lot 6). A ticket is created and run through the REST surface only.
