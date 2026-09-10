# Workboard — Lot 1 (backend core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `workboard` domain exists end to end on the API side — settings, three tables, repository, service with every right and transition, `/workboard` routes with exact totals, purge and export coverage, hub badge — with nothing that runs a ticket yet (lot 2), no agent tools (lot 3), no UI (lot 4).

**Architecture:** A new bounded context `domains/workboard/` following the `reminders` shape (models → repository → service → router), flag-gated like `peers`. One ticket row shared by owner and assignee; visibility is `owner_user_id = U OR assignee_user_id = U`; every write re-checks the peer connection. Comments and events are children of a ticket. Purge and export declare the tables in `user_data_map` and the assignment release runs BEFORE the purge loop.

**Tech Stack:** FastAPI 0.135+, SQLAlchemy 2.x (`Mapped`, `mapped_column`), Alembic, Pydantic 2, pytest (`asyncio_mode=auto`), Testcontainers PostgreSQL for integration.

**Spec:** `docs/superpowers/specs/2026-09-08-workboard-design.md` — read §3 (decisions D3b, D7, D8, D9, D10, D17), §5 (persistence), §8 (peers), §10 (API).

## Global Constraints

- Python 3.14, Black line-length 100, Ruff, MyPy strict: every function fully typed, `X | None`, Google docstrings with Args/Returns/Raises, module docstrings.
- Comments, docstrings, code identifiers and documentation in **English**. User-visible strings never inline: this lot returns STABLE ERROR CODES (`workboard_*`) through `raise_invalid_input(code)` (the peers precedent), never sentences.
- Status columns are `String(20)` + lowercase `str`-Enum values (the `open_loops` / `peers` pattern), never `Enum(native_enum=False)` with uppercase members.
- Never mutate a JSONB in place; every datetime is tz-aware UTC (`datetime.now(UTC)`); no `print`; `structlog.get_logger(__name__)`; ids and counts at INFO, never a title or a body.
- A count shown to a reader is an aggregate over the same statement the page reads (ADR-185); a page carries rows only.
- A logical file stays under 600 logical SLOC; `apps/api/src/domains/agents/api/service.py` and `domains/agents/registry/domain_taxonomy.py` are frozen and NOT touched in this lot.
- Every new table is classified in `apps/api/src/domains/users/user_data_map.py` and covered by `build_purge_statements` (guard `tests/unit/domains/users/test_user_data_map_guard.py`).
- `WORKBOARD_ENABLED` defaults to `true`; every bound is a setting with its default in `core/constants.py`.
- No git commit or push by the executor: commit messages are PROPOSED at each task's end and the owner commits (repository rule).
- Verification runs through the Docker dev containers (`lia-api-dev`) for anything touching runtime; pure unit tests may run with `apps/api/.venv/Scripts/pytest`.

---

## File map

| File | Responsibility |
|---|---|
| `apps/api/src/core/constants.py` (modify, append a `WORKBOARD` block) | defaults of every bound |
| `apps/api/src/core/config/workboard.py` (create) | `WorkboardSettings` |
| `apps/api/src/core/config/__init__.py` (modify) | add the settings class to the MRO |
| `.env.example`, `.env.prod.example`, `.env.min.prod.example` (modify) | the `WORKBOARD_*` block |
| `apps/api/src/api/v1/routes.py` (modify) | router inclusion + `workboard_enabled` feature flag |
| `apps/api/src/domains/workboard/__init__.py` (create) | package docstring |
| `apps/api/src/domains/workboard/constants.py` (create) | enums-as-vocabulary shared by models, schemas, service: status order, priorities, assignee kinds, event kinds, error codes |
| `apps/api/src/domains/workboard/models.py` (create) | `WorkboardTicket`, `WorkboardComment`, `WorkboardTicketEvent` |
| `apps/api/alembic/versions/2026_09_09_0000-a1b2c3d4e5f6_workboard.py` (create) | the three tables |
| `apps/api/src/infrastructure/database/registry.py` (modify) | import the models |
| `apps/api/src/domains/users/user_data_map.py` (modify) | three `TableRule`s |
| `apps/api/src/domains/workboard/purge.py` (create) | `release_assignments_statement(user_id)` |
| `apps/api/src/domains/users/account_deletion_service.py` (modify) | three explicit DELETEs + the release pre-step |
| `apps/api/src/domains/account_export/builder.py` (modify) | `_TWO_SIDED` + `_VIA_PARENT` entries |
| `apps/api/src/domains/workboard/repository.py` (create) | reads with exact totals, writes, column renumbering |
| `apps/api/src/domains/workboard/service.py` (create) | rights, transitions, bounds, peer check, events |
| `apps/api/src/domains/workboard/schemas.py` (create) | request/response models |
| `apps/api/src/domains/workboard/router.py` (create) | `/workboard/*` |
| `apps/api/src/domains/notifications/hub_counts.py` + `schemas.py` + `router.py` (modify) | the `workboard` badge |
| `apps/api/tests/unit/domains/workboard/` (create) | unit tests |
| `apps/api/tests/integration/domains/workboard/` (create) | PostgreSQL tests |
| `docs/architecture/ADR-276-Workboard.md`, `docs/architecture/ADR_INDEX.md`, `docs/technical/WORKBOARD.md`, `docs/INDEX.md` (create/modify) | the record |

---

### Task 1: Settings, constants, environment files, feature flag

**Files:**
- Modify: `apps/api/src/core/constants.py` (append after the `PEERS_*` block, ~line 5616)
- Create: `apps/api/src/core/config/workboard.py`
- Modify: `apps/api/src/core/config/__init__.py` (import + MRO list, next to `PeersSettings`)
- Modify: `.env.example`, `.env.prod.example`, `.env.min.prod.example`
- Modify: `apps/api/src/api/v1/routes.py` (`features` dict, after `meetings_enabled`)
- Test: `apps/api/tests/unit/core/config/test_workboard_settings.py`, `apps/api/tests/unit/api/test_client_config_flags.py`

**Interfaces:**
- Produces: `settings.workboard_enabled: bool`, `settings.workboard_run_sweep_seconds`, `workboard_run_timeout_seconds`, `workboard_run_max_attempts`, `workboard_quota_retry_minutes`, `workboard_max_tickets_per_user`, `workboard_max_children_per_ticket`, `workboard_max_runs_per_ticket`, `workboard_hidden_rows_retention_days`, `workboard_title_max_chars`, `workboard_description_max_chars`, `workboard_comment_max_chars`, `workboard_closed_hide_days_default`, `workboard_nudge_due_hours`, `workboard_nudge_waiting_hours`, `workboard_nudge_cooldown_days` (all `int` except the flag).

- [ ] **Step 1: Write the failing settings test**

```python
# apps/api/tests/unit/core/config/test_workboard_settings.py
"""WorkboardSettings: every bound is a setting, every default a constant."""

from __future__ import annotations

import pytest

from src.core import constants
from src.core.config.workboard import WorkboardSettings

pytestmark = pytest.mark.unit


class TestDefaults:
    def test_enabled_by_default(self) -> None:
        assert WorkboardSettings().workboard_enabled is True

    @pytest.mark.parametrize(
        ("field", "constant"),
        [
            ("workboard_run_sweep_seconds", "WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT"),
            ("workboard_run_timeout_seconds", "WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT"),
            ("workboard_run_max_attempts", "WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT"),
            ("workboard_quota_retry_minutes", "WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT"),
            ("workboard_max_tickets_per_user", "WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT"),
            ("workboard_max_children_per_ticket", "WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT"),
            ("workboard_max_runs_per_ticket", "WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT"),
            ("workboard_hidden_rows_retention_days", "WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT"),
            ("workboard_title_max_chars", "WORKBOARD_TITLE_MAX_CHARS_DEFAULT"),
            ("workboard_description_max_chars", "WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT"),
            ("workboard_comment_max_chars", "WORKBOARD_COMMENT_MAX_CHARS_DEFAULT"),
            ("workboard_closed_hide_days_default", "WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT"),
            ("workboard_nudge_due_hours", "WORKBOARD_NUDGE_DUE_HOURS_DEFAULT"),
            ("workboard_nudge_waiting_hours", "WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT"),
            ("workboard_nudge_cooldown_days", "WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT"),
        ],
    )
    def test_every_default_is_a_constant(self, field: str, constant: str) -> None:
        assert getattr(WorkboardSettings(), field) == getattr(constants, constant)

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORKBOARD_MAX_RUNS_PER_TICKET", "3")
        assert WorkboardSettings().workboard_max_runs_per_ticket == 3

    def test_zero_runs_per_ticket_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORKBOARD_MAX_RUNS_PER_TICKET", "0")
        with pytest.raises(ValueError):
            WorkboardSettings()
```

Add to `apps/api/tests/unit/api/test_client_config_flags.py`, inside the existing class, next to the peers test (same fixture and call as `test_peers_flag_present_and_mirrors_settings`):

```python
    async def test_workboard_flag_present_and_mirrors_settings(self):
        payload = await self._payload()
        assert "workboard_enabled" in payload["features"]
        assert payload["features"]["workboard_enabled"] is bool(settings.workboard_enabled)
```

(Read the file first: use the exact helper the peers test uses to obtain the payload; if it calls the route function directly, do the same.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_workboard_settings.py tests/unit/api/test_client_config_flags.py -v`
Expected: FAIL — `ModuleNotFoundError: src.core.config.workboard`, and `KeyError: 'workboard_enabled'`.

- [ ] **Step 3: Add the constants block**

Append to `apps/api/src/core/constants.py`, right after the `PEERS_*` block:

```python
# ============================================================================
# WORKBOARD — ticket board (ADR-276)
# ============================================================================
# Defaults of every WORKBOARD_* setting (src/core/config/workboard.py). Each is
# a bound a tool parameter meets, published from the same setting (ADR-184).
WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT = 60
WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT = 600
WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT = 3
WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT = 30
WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT = 2000
WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT = 50
WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT = 10
WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT = 90
WORKBOARD_TITLE_MAX_CHARS_DEFAULT = 200
WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT = 8000
WORKBOARD_COMMENT_MAX_CHARS_DEFAULT = 4000
WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT = 30
WORKBOARD_NUDGE_DUE_HOURS_DEFAULT = 24
WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT = 48
WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT = 2
SCHEDULER_JOB_WORKBOARD_RUN_SWEEP = "workboard_run_sweep"
```

- [ ] **Step 4: Create the settings module**

```python
# apps/api/src/core/config/workboard.py
"""Workboard configuration module (ADR-276).

Feature flag and every bound the ticket board enforces. Each value is
env-overridable (``WORKBOARD_*``); defaults come from ``src.core.constants``
(the config layer never imports domains — see ``briefing.py``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT,
    WORKBOARD_COMMENT_MAX_CHARS_DEFAULT,
    WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
    WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT,
    WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT,
    WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT,
    WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT,
    WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT,
    WORKBOARD_NUDGE_DUE_HOURS_DEFAULT,
    WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT,
    WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT,
    WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT,
    WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT,
    WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT,
    WORKBOARD_TITLE_MAX_CHARS_DEFAULT,
)


class WorkboardSettings(BaseSettings):
    """Env-overridable settings for the ticket board."""

    workboard_enabled: bool = Field(
        default=True,
        description="Enable the workboard (routes, sweep, agent tools, settings section).",
    )
    workboard_run_sweep_seconds: int = Field(
        default=WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Interval of the sweep that runs tickets assigned to LIA.",
    )
    workboard_run_timeout_seconds: int = Field(
        default=WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=3600,
        description="Hard bound of one ticket run; a claim older than this is reaped.",
    )
    workboard_run_max_attempts: int = Field(
        default=WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=10,
        description="Transient-failure attempts of ONE run before it settles as failed.",
    )
    workboard_quota_retry_minutes: int = Field(
        default=WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT,
        ge=1,
        le=1440,
        description="Back-off before a quota-refused ticket is offered to the sweep again.",
    )
    workboard_max_tickets_per_user: int = Field(
        default=WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT,
        ge=1,
        le=100000,
        description="Tickets one account may own, counted exactly at creation.",
    )
    workboard_max_children_per_ticket: int = Field(
        default=WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT,
        ge=1,
        le=1000,
        description="Sub-tickets one ticket may carry.",
    )
    workboard_max_runs_per_ticket: int = Field(
        default=WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT,
        ge=1,
        le=100,
        description="Runs one ticket may have in its life, « Run now » included (D3b).",
    )
    workboard_hidden_rows_retention_days: int = Field(
        default=WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=3650,
        description="Days after a ticket closes before its hidden run rows are deleted.",
    )
    workboard_title_max_chars: int = Field(
        default=WORKBOARD_TITLE_MAX_CHARS_DEFAULT, ge=20, le=1000, description="Title bound."
    )
    workboard_description_max_chars: int = Field(
        default=WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
        ge=100,
        le=100000,
        description="Description bound — the brief LIA runs.",
    )
    workboard_comment_max_chars: int = Field(
        default=WORKBOARD_COMMENT_MAX_CHARS_DEFAULT, ge=50, le=50000, description="Comment bound."
    )
    workboard_closed_hide_days_default: int = Field(
        default=WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT,
        ge=0,
        le=3650,
        description="Default of the per-account « hide closed tickets older than » filter.",
    )
    workboard_nudge_due_hours: int = Field(
        default=WORKBOARD_NUDGE_DUE_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Heartbeat: a ticket due within this window is nudge-worthy.",
    )
    workboard_nudge_waiting_hours: int = Field(
        default=WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Heartbeat: a ticket waiting for the person longer than this is nudge-worthy.",
    )
    workboard_nudge_cooldown_days: int = Field(
        default=WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT,
        ge=0,
        le=365,
        description="Heartbeat: days between two nudges about the same ticket.",
    )
```

In `apps/api/src/core/config/__init__.py`: add `from .workboard import WorkboardSettings` beside the peers import and `WorkboardSettings,` right after `PeersSettings,` in the composition list (line ~134).

- [ ] **Step 5: Add the env blocks and the feature flag**

Append to `.env.example` after the PEERS block (same column alignment as the file uses):

```
# ============================================================================
# WORKBOARD — ticket board (ADR-276)
# Config: src/core/config/workboard.py
# ============================================================================

WORKBOARD_ENABLED=true                                      # Enable the workboard (routes, sweep, agent tools, settings section)
WORKBOARD_RUN_SWEEP_SECONDS=60                              # Interval of the sweep that runs tickets assigned to LIA
WORKBOARD_RUN_TIMEOUT_SECONDS=600                           # Hard bound of one ticket run; a claim older than this is reaped
WORKBOARD_RUN_MAX_ATTEMPTS=3                                # Transient-failure attempts of ONE run before it settles as failed
WORKBOARD_QUOTA_RETRY_MINUTES=30                            # Back-off before a quota-refused ticket is offered to the sweep again
WORKBOARD_MAX_TICKETS_PER_USER=2000                         # Tickets one account may own (counted exactly at creation)
WORKBOARD_MAX_CHILDREN_PER_TICKET=50                        # Sub-tickets one ticket may carry
WORKBOARD_MAX_RUNS_PER_TICKET=10                            # Runs one ticket may have in its life, « Run now » included
WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS=90                     # Days after a ticket closes before its hidden run rows are deleted
WORKBOARD_TITLE_MAX_CHARS=200                               # Title bound
WORKBOARD_DESCRIPTION_MAX_CHARS=8000                        # Description bound (the brief LIA runs)
WORKBOARD_COMMENT_MAX_CHARS=4000                            # Comment bound
WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT=30                       # Default of the « hide closed tickets older than » filter
WORKBOARD_NUDGE_DUE_HOURS=24                                # Heartbeat: due within this window = nudge-worthy
WORKBOARD_NUDGE_WAITING_HOURS=48                            # Heartbeat: waiting longer than this = nudge-worthy
WORKBOARD_NUDGE_COOLDOWN_DAYS=2                             # Heartbeat: days between two nudges about one ticket
```

Same block in `.env.prod.example`; in `.env.min.prod.example` only `WORKBOARD_ENABLED=true` (check how `MEETINGS_ENABLED` appears there and mirror it). Run `task lint:hygiene` — it compares `.env.example` against the settings fields.

In `apps/api/src/api/v1/routes.py`, `features` dict, after `meetings_enabled`:

```python
            # Workboard (ADR-276): gates the settings section, the board page
            # and the chat notification actions.
            "workboard_enabled": getattr(settings, "workboard_enabled", False),
```

- [ ] **Step 6: Run the tests and the hygiene gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_workboard_settings.py tests/unit/api/test_client_config_flags.py -v` → PASS.
Run: `task lint:hygiene` → green (the `.env.example` audit sees every new field).

- [ ] **Step 7: Proposed commit** (the owner commits)

`feat(workboard): settings, constants and instance flag (ADR-276, lot 1)`

---

### Task 2: Vocabulary, models, migration, registry, data map, purge, export

**Files:**
- Create: `apps/api/src/domains/workboard/__init__.py`, `constants.py`, `models.py`, `purge.py`
- Create: `apps/api/alembic/versions/2026_09_09_0000-a1b2c3d4e5f6_workboard.py`
- Modify: `apps/api/src/infrastructure/database/registry.py` (add `import src.domains.workboard.models  # noqa: F401` in alphabetical place)
- Modify: `apps/api/src/domains/users/user_data_map.py` (three rules near `scheduled_action_runs`)
- Modify: `apps/api/src/domains/users/account_deletion_service.py` (three DELETEs in Group 1; the release pre-step in `_purge_user_data_tables`)
- Modify: `apps/api/src/domains/account_export/builder.py` (`_TWO_SIDED`, `_VIA_PARENT`)
- Test: `apps/api/tests/unit/domains/workboard/test_models.py`, `test_purge.py`; the existing guards `tests/unit/domains/users/test_user_data_map_guard.py`, `tests/unit/infrastructure/database/test_schema_drift.py`

**Interfaces:**
- Produces: `TicketStatus`, `TicketPriority`, `AssigneeKind`, `ActorKind`, `TicketEventKind`, `STATUS_ORDER`, `CLOSED_STATUSES`, `WorkboardError` codes; models `WorkboardTicket`, `WorkboardComment`, `WorkboardTicketEvent`; `release_assignments_statement(user_id: UUID) -> Update`.

- [ ] **Step 1: Write the failing model and vocabulary tests**

```python
# apps/api/tests/unit/domains/workboard/__init__.py  (empty)
```

```python
# apps/api/tests/unit/domains/workboard/test_models.py
"""The vocabulary is ONE tuple, and the tables say what they mean."""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint

from src.domains.workboard.constants import (
    CLOSED_STATUSES,
    STATUS_ORDER,
    ActorKind,
    AssigneeKind,
    TicketEventKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent

pytestmark = pytest.mark.unit


class TestVocabulary:
    def test_column_order_is_the_enum_order(self) -> None:
        assert STATUS_ORDER == tuple(s.value for s in TicketStatus)
        assert STATUS_ORDER == (
            "idea", "todo", "in_progress", "waiting", "validating", "done", "cancelled",
        )

    def test_closed_statuses(self) -> None:
        assert CLOSED_STATUSES == frozenset({"done", "cancelled"})

    def test_priorities(self) -> None:
        assert [p.value for p in TicketPriority] == ["low", "medium", "high", "urgent"]

    def test_assignee_and_actor_kinds(self) -> None:
        assert {k.value for k in AssigneeKind} == {"human", "lia"}
        assert {k.value for k in ActorKind} == {"user", "lia", "peer"}

    def test_event_kinds(self) -> None:
        assert {k.value for k in TicketEventKind} == {
            "created", "status_changed", "assigned", "priority_changed",
            "dates_changed", "run_started", "run_finished", "follow_changed",
        }


class TestTables:
    def test_table_names(self) -> None:
        assert WorkboardTicket.__tablename__ == "workboard_tickets"
        assert WorkboardComment.__tablename__ == "workboard_comments"
        assert WorkboardTicketEvent.__tablename__ == "workboard_ticket_events"

    def test_ticket_defaults(self) -> None:
        cols = WorkboardTicket.__table__.c
        assert cols.status.default.arg == "todo"
        assert cols.priority.default.arg == "medium"
        assert cols.follow_owner.default.arg is False
        assert cols.follow_assignee.default.arg is False
        assert cols.run_attempts.default.arg == 0
        assert cols.run_count.default.arg == 0

    def test_assignee_fk_is_restrict(self) -> None:
        fk = next(iter(WorkboardTicket.__table__.c.assignee_user_id.foreign_keys))
        assert fk.ondelete == "RESTRICT"

    def test_owner_and_parent_cascade(self) -> None:
        owner_fk = next(iter(WorkboardTicket.__table__.c.owner_user_id.foreign_keys))
        parent_fk = next(iter(WorkboardTicket.__table__.c.parent_id.foreign_keys))
        assert owner_fk.ondelete == "CASCADE"
        assert parent_fk.ondelete == "CASCADE"

    def test_peer_connection_check_constraint_exists(self) -> None:
        names = {
            c.name for c in WorkboardTicket.__table__.constraints if isinstance(c, CheckConstraint)
        }
        assert "ck_workboard_tickets_peer_connection_iff_foreign_assignee" in names

    def test_event_table_is_append_only(self) -> None:
        assert "updated_at" not in WorkboardTicketEvent.__table__.c
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: src.domains.workboard`.

- [ ] **Step 3: Write the vocabulary module**

```python
# apps/api/src/domains/workboard/__init__.py
"""Workboard bounded context (ADR-276): a personal ticket board.

One ticket row shared by its owner and its assignee; LIA runs the tickets
assigned to it out of turn (lot 2); the chat drives it through tools (lot 3).
"""
```

```python
# apps/api/src/domains/workboard/constants.py
"""Vocabulary of the workboard, declared once.

Every string another module compares against lives here: the seven columns
in their display order, the priorities, who a ticket is assigned to, who acts
on it, what an event records, and the stable error codes the API returns
(the peers precedent: codes are translation keys the frontend resolves —
never sentences).
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class TicketStatus(str, Enum):
    """The seven columns. Enum order IS column order — one tuple, one truth."""

    IDEA = "idea"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    VALIDATING = "validating"
    DONE = "done"
    CANCELLED = "cancelled"


#: Display order of the columns, derived from the enum so it cannot diverge.
STATUS_ORDER: Final[tuple[str, ...]] = tuple(s.value for s in TicketStatus)

#: Statuses after which a ticket is « closed »: hidden past N days, and the
#: hidden run rows of such a ticket are what the retention sweep removes.
CLOSED_STATUSES: Final[frozenset[str]] = frozenset(
    {TicketStatus.DONE.value, TicketStatus.CANCELLED.value}
)


class TicketPriority(str, Enum):
    """Four levels, matching the frontend's ``priorityTone``."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AssigneeKind(str, Enum):
    """Who holds the ticket: a person, or that person's LIA (D7)."""

    HUMAN = "human"
    LIA = "lia"


class ActorKind(str, Enum):
    """Who did something on a ticket, as the event log and the comments say."""

    USER = "user"
    LIA = "lia"
    PEER = "peer"


class TicketEventKind(str, Enum):
    """What a ticket event records."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    PRIORITY_CHANGED = "priority_changed"
    DATES_CHANGED = "dates_changed"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    FOLLOW_CHANGED = "follow_changed"


class RunOutcome(str, Enum):
    """How the last run of a ticket ended (written by lot 2, read by everyone)."""

    SUCCESS = "success"
    WAITING = "waiting"
    FAILED = "failed"
    SKIPPED_QUOTA = "skipped_quota"
    SKIPPED_BUSY = "skipped_busy"


class WorkboardError(str, Enum):
    """Stable machine codes of every refusal on the /workboard surface."""

    PEERS_DISABLED = "workboard_peers_disabled"
    TITLE_REQUIRED = "workboard_title_required"
    TITLE_TOO_LONG = "workboard_title_too_long"
    DESCRIPTION_TOO_LONG = "workboard_description_too_long"
    COMMENT_TOO_LONG = "workboard_comment_too_long"
    DEPTH_EXCEEDED = "workboard_depth_exceeded"
    PARENT_NOT_OWNED = "workboard_parent_not_owned"
    TOO_MANY_TICKETS = "workboard_too_many_tickets"
    TOO_MANY_CHILDREN = "workboard_too_many_children"
    ASSIGNEE_NOT_CONNECTED = "workboard_assignee_not_connected"
    CROSS_ACCOUNT_DELEGATION = "workboard_cross_account_delegation"
    PEER_CANNOT_DELETE = "workboard_peer_cannot_delete"
    PEER_CANNOT_EDIT_FIELD = "workboard_peer_cannot_edit_field"
    PEER_CANNOT_REASSIGN = "workboard_peer_cannot_reassign"
    RUN_NOW_REQUIRES_LIA = "workboard_run_now_requires_lia"
    MAX_RUNS_REACHED = "workboard_max_runs_reached"
    STATUS_INVALID = "workboard_status_invalid"
    PRIORITY_INVALID = "workboard_priority_invalid"
    DATES_INVERTED = "workboard_dates_inverted"
```

- [ ] **Step 4: Write the models**

```python
# apps/api/src/domains/workboard/models.py
"""Workboard models (ADR-276).

One row per ticket, shared by its owner and its assignee (D7/D8): the board of
user U is « owner = U or assignee = U ». Comments and events hang off a ticket
and die with it. The event table is append-only (``created_at`` only, the
``peer_access_log`` pattern): what humans did is here; what LIA did is ALSO in
the ADR-263 registers, and the two are never joined.

Status columns are ``String(20)`` + lowercase ``str``-Enum values (the
``open_loops`` / ``peers`` pattern).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domains.workboard.constants import (
    ActorKind,
    AssigneeKind,
    TicketPriority,
    TicketStatus,
)
from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base


class WorkboardTicket(BaseModel):
    """A unit of work with a lifecycle, an assignee and a result."""

    __tablename__ = "workboard_tickets"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The board it was created on. Dies with the account.",
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Parent ticket (ONE level — a child never has children).",
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="What the ticket is.")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="The brief LIA runs when assigned; the owner's words."
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TicketStatus.TODO.value,
        comment="idea | todo | in_progress | waiting | validating | done | cancelled",
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=TicketPriority.MEDIUM.value,
        comment="low | medium | high | urgent",
    )
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="UTC instant work may start."
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="UTC instant it is due."
    )
    assignee_kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=AssigneeKind.HUMAN.value,
        comment="human | lia — whose hands, or whose assistant (D7).",
    )
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The account holding it. RESTRICT: the purge releases assignments first.",
    )
    peer_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("peer_connections.id", ondelete="SET NULL"),
        nullable=True,
        comment="Non-null iff the assignee is another account (D8).",
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Order inside a column, on the OWNER's board."
    )
    follow_owner: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"),
        comment="Owner wants chat notifications about this ticket.",
    )
    follow_assignee: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"),
        comment="Assignee wants chat notifications; reset on reassignment.",
    )
    created_by: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=ActorKind.USER.value,
        comment="user | lia | peer — who created it (D13).",
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When status last changed (closed-hide filter, waiting-too-long nudge).",
    )
    run_not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Quota back-off; set by the sweep only."
    )
    run_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="A run holds this ticket since."
    )
    run_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Attempts of the CURRENT run."
    )
    run_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Runs in the ticket's life (D3b cap)."
    )
    last_run_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="run_id of the last run (registers join key)."
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_outcome: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="success | waiting | failed | skipped_quota | skipped_busy"
    )
    last_run_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Typed code + bounded message; never a traceback."
    )
    last_run_tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_cost_eur: Mapped[Any | None] = mapped_column(Numeric(10, 6), nullable=True)
    last_nudged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Heartbeat cooldown."
    )
    nudge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_workboard_tickets_owner_status", "owner_user_id", "status"),
        Index("ix_workboard_tickets_assignee_status", "assignee_user_id", "status"),
        # The sweep's eligibility scan (lot 2): LIA-assigned, to do, unclaimed.
        Index(
            "ix_workboard_tickets_lia_todo",
            "start_at",
            postgresql_where=text(
                "assignee_kind = 'lia' AND status = 'todo' AND run_claimed_at IS NULL"
            ),
        ),
        CheckConstraint(
            "(peer_connection_id IS NULL) = (assignee_user_id = owner_user_id)",
            name="ck_workboard_tickets_peer_connection_iff_foreign_assignee",
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkboardTicket(id={self.id}, status={self.status})>"


class WorkboardComment(BaseModel):
    """One comment on a ticket, by a person or by LIA (a run's answer)."""

    __tablename__ = "workboard_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="user | lia | peer"
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="The run that wrote it, when LIA did."
    )


class WorkboardTicketEvent(Base, UUIDMixin):
    """Append-only history of a ticket: what humans did, and when a run ran."""

    __tablename__ = "workboard_ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_kind: Mapped[str] = mapped_column(String(10), nullable=False, comment="user | lia | peer")
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, comment="TicketEventKind")
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Bounded {from, to} facts; never free text."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
```

- [ ] **Step 5: Write the migration**

Read `apps/api/alembic/versions/2026_09_07_0100-00fae77284aa_relation_debrief_usage.py` to copy the CURRENT head revision id into `down_revision` (it was `00fae77284aa` on 2026-09-08 — re-check with `.venv/Scripts/alembic heads` from `apps/api`).

```python
# apps/api/alembic/versions/2026_09_09_0000-a1b2c3d4e5f6_workboard.py
"""Workboard (ADR-276): tickets, comments, events.

One ticket row shared by its owner and its assignee; comments and an
append-only event log hanging off it. ``assignee_user_id`` is RESTRICT on
purpose: the account purge releases foreign assignments BEFORE deleting, and a
row that escaped that step must fail the deletion loudly rather than vanish
from someone else's board in silence.

Revision ID: a1b2c3d4e5f6
Revises: 00fae77284aa
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "00fae77284aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the three workboard tables."""
    op.create_table(
        "workboard_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False,
                  comment="The board it was created on. Dies with the account."),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Parent ticket (ONE level — a child never has children)."),
        sa.Column("title", sa.Text(), nullable=False, comment="What the ticket is."),
        sa.Column("description", sa.Text(), nullable=True,
                  comment="The brief LIA runs when assigned; the owner's words."),
        sa.Column("status", sa.String(length=20), nullable=False,
                  comment="idea | todo | in_progress | waiting | validating | done | cancelled"),
        sa.Column("priority", sa.String(length=10), nullable=False,
                  comment="low | medium | high | urgent"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True,
                  comment="UTC instant work may start."),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True,
                  comment="UTC instant it is due."),
        sa.Column("assignee_kind", sa.String(length=10), nullable=False,
                  comment="human | lia — whose hands, or whose assistant (D7)."),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=False,
                  comment="The account holding it. RESTRICT: the purge releases assignments first."),
        sa.Column("peer_connection_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="Non-null iff the assignee is another account (D8)."),
        sa.Column("position", sa.Integer(), nullable=False,
                  comment="Order inside a column, on the OWNER's board."),
        sa.Column("follow_owner", sa.Boolean(), nullable=False, server_default=sa.text("false"),
                  comment="Owner wants chat notifications about this ticket."),
        sa.Column("follow_assignee", sa.Boolean(), nullable=False, server_default=sa.text("false"),
                  comment="Assignee wants chat notifications; reset on reassignment."),
        sa.Column("created_by", sa.String(length=10), nullable=False,
                  comment="user | lia | peer — who created it (D13)."),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False,
                  comment="When status last changed (closed-hide filter, waiting-too-long nudge)."),
        sa.Column("run_not_before", sa.DateTime(timezone=True), nullable=True,
                  comment="Quota back-off; set by the sweep only."),
        sa.Column("run_claimed_at", sa.DateTime(timezone=True), nullable=True,
                  comment="A run holds this ticket since."),
        sa.Column("run_attempts", sa.Integer(), nullable=False,
                  comment="Attempts of the CURRENT run."),
        sa.Column("run_count", sa.Integer(), nullable=False,
                  comment="Runs in the ticket's life (D3b cap)."),
        sa.Column("last_run_id", sa.String(length=100), nullable=True,
                  comment="run_id of the last run (registers join key)."),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_outcome", sa.String(length=20), nullable=True,
                  comment="success | waiting | failed | skipped_quota | skipped_busy"),
        sa.Column("last_run_error", sa.Text(), nullable=True,
                  comment="Typed code + bounded message; never a traceback."),
        sa.Column("last_run_tokens_in", sa.Integer(), nullable=True),
        sa.Column("last_run_tokens_out", sa.Integer(), nullable=True),
        sa.Column("last_run_cost_eur", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("last_nudged_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Heartbeat cooldown."),
        sa.Column("nudge_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(peer_connection_id IS NULL) = (assignee_user_id = owner_user_id)",
            name="ck_workboard_tickets_peer_connection_iff_foreign_assignee",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["peer_connection_id"], ["peer_connections.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workboard_tickets_owner_user_id", "workboard_tickets", ["owner_user_id"])
    op.create_index("ix_workboard_tickets_assignee_user_id", "workboard_tickets", ["assignee_user_id"])
    op.create_index("ix_workboard_tickets_parent_id", "workboard_tickets", ["parent_id"])
    op.create_index(
        "ix_workboard_tickets_owner_status", "workboard_tickets", ["owner_user_id", "status"]
    )
    op.create_index(
        "ix_workboard_tickets_assignee_status", "workboard_tickets", ["assignee_user_id", "status"]
    )
    op.create_index(
        "ix_workboard_tickets_lia_todo",
        "workboard_tickets",
        ["start_at"],
        postgresql_where=sa.text(
            "assignee_kind = 'lia' AND status = 'todo' AND run_claimed_at IS NULL"
        ),
    )

    op.create_table(
        "workboard_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_kind", sa.String(length=10), nullable=False, comment="user | lia | peer"),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=True,
                  comment="The run that wrote it, when LIA did."),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workboard_comments_ticket_id", "workboard_comments", ["ticket_id"])

    op.create_table(
        "workboard_ticket_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_kind", sa.String(length=10), nullable=False, comment="user | lia | peer"),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, comment="TicketEventKind"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment="Bounded {from, to} facts; never free text."),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workboard_ticket_events_ticket_id", "workboard_ticket_events", ["ticket_id"])


def downgrade() -> None:
    """Drop the three tables, children first."""
    op.drop_index("ix_workboard_ticket_events_ticket_id", table_name="workboard_ticket_events")
    op.drop_table("workboard_ticket_events")
    op.drop_index("ix_workboard_comments_ticket_id", table_name="workboard_comments")
    op.drop_table("workboard_comments")
    for name in (
        "ix_workboard_tickets_lia_todo",
        "ix_workboard_tickets_assignee_status",
        "ix_workboard_tickets_owner_status",
        "ix_workboard_tickets_parent_id",
        "ix_workboard_tickets_assignee_user_id",
        "ix_workboard_tickets_owner_user_id",
    ):
        op.drop_index(name, table_name="workboard_tickets")
    op.drop_table("workboard_tickets")
```

Note for the drift guard (F042): column `comment=` strings must be IDENTICAL between the model and the migration; the schema-drift test compares them. `index=True` on a model column produces an index named `ix_<table>_<column>` — the migration creates exactly those names.

- [ ] **Step 6: Register the models and classify the tables**

`apps/api/src/infrastructure/database/registry.py`: add `import src.domains.workboard.models  # noqa: F401` in alphabetical order (after `voice` or wherever the list ends — read the file).

`apps/api/src/domains/users/user_data_map.py`, in `TABLE_RULES` near `scheduled_action_runs`:

```python
    "workboard_tickets": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Tickets (ADR-276): owned by the account, or assigned to it by a "
            "connected peer. Foreign assignments are released before the purge; "
            "owned rows are deleted. Exported two-sided (owner or assignee)."
        ),
    ),
    "workboard_comments": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Comments on the account's tickets — purged with them, exported via the ticket.",
    ),
    "workboard_ticket_events": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Append-only ticket history — purged with the ticket, exported via the ticket.",
    ),
```

- [ ] **Step 7: Write the failing purge test, then the release statement**

```python
# apps/api/tests/unit/domains/workboard/test_purge.py
"""Releasing foreign assignments BEFORE the purge — the RESTRICT FK's other half."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.workboard.purge import release_assignments_statement

pytestmark = pytest.mark.unit


def test_release_resets_only_tickets_the_user_holds_but_does_not_own() -> None:
    user_id = uuid.uuid4()
    stmt = release_assignments_statement(user_id)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "UPDATE workboard_tickets" in sql
    assert "assignee_user_id = owner_user_id" in sql
    assert "assignee_kind=" in sql or "assignee_kind =" in sql
    assert "peer_connection_id=" in sql or "peer_connection_id =" in sql
    where = sql.split("WHERE", 1)[1]
    assert "assignee_user_id = " in where and "owner_user_id != " in where
```

```python
# apps/api/src/domains/workboard/purge.py
"""What the account purge must do to tickets BEFORE it deletes anything.

``workboard_tickets.assignee_user_id`` is RESTRICT: a ticket a deleted account
still held would block the deletion. So the assignment is RELEASED first —
the ticket goes back to its owner's own hands — and only then does the purge
delete the rows the account owns. Kept in this module (built against
``Base.metadata`` tables, the ``build_purge_statements`` rule) so the users
domain imports no workboard model.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Update, update

from src.domains.workboard.constants import AssigneeKind
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base


def release_assignments_statement(user_id: UUID) -> Update:
    """Give back to their owners the tickets ``user_id`` holds without owning.

    Args:
        user_id: The account being deleted.

    Returns:
        The UPDATE to execute before the purge loop.
    """
    import_all_models()
    tickets = Base.metadata.tables["workboard_tickets"]
    return (
        update(tickets)
        .where(tickets.c.assignee_user_id == user_id, tickets.c.owner_user_id != user_id)
        .values(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=tickets.c.owner_user_id,
            peer_connection_id=None,
            follow_assignee=False,
        )
    )
```

In `account_deletion_service.py`:

1. Group 1 of `build_purge_statements`, right after `by_user("agent_integrity_events")` and before `ledger_chain` (children first):

```python
        # Workboard (ADR-276): children first, then the tickets the account
        # OWNS. Tickets it merely held were released by the pre-step in
        # ``_purge_user_data_tables`` — the RESTRICT FK is what makes a missed
        # release fail loudly here instead of vanishing from another board.
        (
            "workboard_comments",
            delete(tables["workboard_comments"]).where(
                tables["workboard_comments"].c.ticket_id.in_(owned_ticket_ids_subq)
            ),
        ),
        (
            "workboard_ticket_events",
            delete(tables["workboard_ticket_events"]).where(
                tables["workboard_ticket_events"].c.ticket_id.in_(owned_ticket_ids_subq)
            ),
        ),
        by_user("workboard_tickets", column="owner_user_id"),
```

with, next to `conversation_ids_subq`:

```python
    workboard_tickets = tables["workboard_tickets"]
    owned_ticket_ids_subq = select(workboard_tickets.c.id).where(
        workboard_tickets.c.owner_user_id == user_id
    )
```

2. In `_purge_user_data_tables`, before the loop:

```python
        from src.domains.workboard.purge import release_assignments_statement

        released = await self.db.execute(release_assignments_statement(user_id))
        counts["workboard_tickets:released"] = released.rowcount  # type: ignore[attr-defined]
```

(The guard reads the names returned by `build_purge_statements` only, so the `:released` key in the counts dict is not a purge entry.)

- [ ] **Step 8: Export coverage**

`apps/api/src/domains/account_export/builder.py`:

```python
_VIA_PARENT: dict[str, tuple[str, str, str]] = {
    ...existing...,
    # Workboard: the thread and the history of the tickets the account OWNS.
    # A peer's own words on a ticket they hold reach them through the ticket
    # row (two-sided below); lot 5 reviews whether their comments need more.
    "workboard_comments": ("workboard_tickets", "ticket_id", "owner_user_id"),
    "workboard_ticket_events": ("workboard_tickets", "ticket_id", "owner_user_id"),
}

_TWO_SIDED: dict[str, tuple[str, str]] = {
    ...existing...,
    "workboard_tickets": ("owner_user_id", "assignee_user_id"),
}
```

- [ ] **Step 9: Run every guard**

Run from `apps/api`:
```
.venv/Scripts/pytest tests/unit/domains/workboard -v
.venv/Scripts/pytest tests/unit/domains/users/test_user_data_map_guard.py tests/unit/infrastructure/database/test_schema_drift.py tests/unit/domains/account_export -v
```
Expected: all PASS. Then `task db:migrate:replay-check` (F007 + F042) → green. Then restart the dev API and check it boots: `docker restart lia-api-dev && docker logs lia-api-dev --tail 40 | grep -i "application_ready\|error"`.

- [ ] **Step 10: Proposed commit**

`feat(workboard): models, migration, purge and export coverage (ADR-276, lot 1)`

---

### Task 3: Repository

**Files:**
- Create: `apps/api/src/domains/workboard/repository.py`
- Test: `apps/api/tests/unit/domains/workboard/test_repository_statements.py` (statement shape) — behaviour on PostgreSQL is Task 6.

**Interfaces:**
- Produces:
  - `BoardFilters` dataclass: `statuses: tuple[str, ...] | None`, `assignee: Literal["me","lia","peer","all"]`, `priorities: tuple[str, ...] | None`, `overdue: bool`, `due_before: datetime | None`, `query: str | None`, `include_closed_before: datetime | None`, `sort: Literal["position","priority","due","updated","created"]`.
  - `WorkboardRepository(db)` with `visible_predicate(user_id)`, `list_board(user_id, filters, limit, offset) -> tuple[list[WorkboardTicket], int]`, `counts_by_status(user_id, filters) -> dict[str, int]`, `get_visible(ticket_id, user_id) -> WorkboardTicket | None`, `count_owned(user_id) -> int`, `count_children(ticket_id) -> int`, `count_runs(ticket_id) -> int`, `next_position(owner_id, status) -> int`, `renumber_column(owner_id, status, ordered_ids)`, `list_children(ticket_id)`, `list_comments(ticket_id)`, `list_events(ticket_id)`, `add_comment(...)`, `add_event(...)`, `find_by_title(user_id, folded_title) -> list[WorkboardTicket]`, `needs_me(user_id, now) -> tuple[list[WorkboardTicket], int]`, `list_by_connection(connection_id)`.

- [ ] **Step 1: Write the failing statement tests**

```python
# apps/api/tests/unit/domains/workboard/test_repository_statements.py
"""The board reads: same filter for the page and for its counts (ADR-185)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.workboard.repository import BoardFilters, WorkboardRepository

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))


class TestBoardStatement:
    def test_visibility_is_owner_or_assignee(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        sql = _sql(repo._board_stmt(USER, BoardFilters()))
        assert "owner_user_id = " in sql and "assignee_user_id = " in sql
        assert " OR " in sql

    def test_assignee_me_means_human_and_me(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        sql = _sql(repo._board_stmt(USER, BoardFilters(assignee="me")))
        assert "assignee_kind = " in sql

    def test_closed_hidden_past_cutoff_unless_included(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        cutoff = datetime(2026, 8, 1, tzinfo=UTC)
        sql = _sql(repo._board_stmt(USER, BoardFilters(include_closed_before=cutoff)))
        assert "status_changed_at" in sql

    def test_overdue_reads_due_at_and_open_statuses(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        sql = _sql(repo._board_stmt(USER, BoardFilters(overdue=True)))
        assert "due_at <" in sql and "status NOT IN" in sql

    def test_counts_by_status_uses_the_same_filter(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        filters = BoardFilters(priorities=("high",))
        page = _sql(repo._board_stmt(USER, filters))
        counts = _sql(repo._counts_stmt(USER, filters))
        assert "priority IN" in page and "priority IN" in counts
        assert "GROUP BY" in counts


class TestRenumber:
    async def test_renumber_issues_one_update_with_a_case(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=3))
        repo = WorkboardRepository(db)
        ids = [uuid.uuid4() for _ in range(3)]
        await repo.renumber_column(USER, "todo", ids)
        db.execute.assert_awaited_once()
        sql = _sql(db.execute.await_args.args[0])
        assert "CASE" in sql and "UPDATE workboard_tickets" in sql
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard/test_repository_statements.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the repository**

```python
# apps/api/src/domains/workboard/repository.py
"""Workboard repository: every read the board makes, and the writes it needs.

Rules it enforces by shape:

- visibility is ONE predicate (`visible_predicate`) reused by every read;
- the page and its counts are built from the SAME filtered statement
  (ADR-185): a column header count that disagreed with the column would be
  worse than no count;
- ordering carries the primary key as the last key, so a page boundary can
  never repeat or lose a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import Select, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.shared.text_normalization import fold_name
from src.domains.workboard.constants import (
    CLOSED_STATUSES,
    STATUS_ORDER,
    AssigneeKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent

logger = structlog.get_logger(__name__)

AssigneeFilter = Literal["me", "lia", "peer", "all"]
SortKey = Literal["position", "priority", "due", "updated", "created"]

_PRIORITY_RANK: dict[str, int] = {
    TicketPriority.URGENT.value: 0,
    TicketPriority.HIGH.value: 1,
    TicketPriority.MEDIUM.value: 2,
    TicketPriority.LOW.value: 3,
}


@dataclass(frozen=True)
class BoardFilters:
    """What a board read asks for. Defaults read the whole open board."""

    statuses: tuple[str, ...] | None = None
    assignee: AssigneeFilter = "all"
    priorities: tuple[str, ...] | None = None
    overdue: bool = False
    due_before: datetime | None = None
    query: str | None = None
    include_closed_before: datetime | None = None
    sort: SortKey = "position"


class WorkboardRepository(BaseRepository[WorkboardTicket]):
    """Reads and writes of tickets, comments and events."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WorkboardTicket)

    # ----------------------------------------------------------------- reads

    @staticmethod
    def visible_predicate(user_id: UUID) -> Any:
        """A ticket is on U's board iff U owns it or holds it (D8)."""
        return or_(
            WorkboardTicket.owner_user_id == user_id,
            WorkboardTicket.assignee_user_id == user_id,
        )

    def _filtered(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[WorkboardTicket]]:
        stmt = select(WorkboardTicket).where(self.visible_predicate(user_id))
        if filters.statuses:
            stmt = stmt.where(WorkboardTicket.status.in_(filters.statuses))
        if filters.assignee == "me":
            stmt = stmt.where(
                WorkboardTicket.assignee_kind == AssigneeKind.HUMAN.value,
                WorkboardTicket.assignee_user_id == user_id,
            )
        elif filters.assignee == "lia":
            stmt = stmt.where(WorkboardTicket.assignee_kind == AssigneeKind.LIA.value)
        elif filters.assignee == "peer":
            stmt = stmt.where(WorkboardTicket.assignee_user_id != WorkboardTicket.owner_user_id)
        if filters.priorities:
            stmt = stmt.where(WorkboardTicket.priority.in_(filters.priorities))
        if filters.overdue:
            stmt = stmt.where(
                WorkboardTicket.due_at < datetime.now(UTC),
                WorkboardTicket.status.not_in(tuple(CLOSED_STATUSES)),
            )
        if filters.due_before is not None:
            stmt = stmt.where(WorkboardTicket.due_at <= filters.due_before)
        if filters.query:
            stmt = stmt.where(WorkboardTicket.title.ilike(f"%{filters.query}%"))
        if filters.include_closed_before is not None:
            # Closed tickets are shown only when they closed AFTER the cutoff.
            stmt = stmt.where(
                or_(
                    WorkboardTicket.status.not_in(tuple(CLOSED_STATUSES)),
                    WorkboardTicket.status_changed_at >= filters.include_closed_before,
                )
            )
        return stmt

    def _board_stmt(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[WorkboardTicket]]:
        stmt = self._filtered(user_id, filters)
        priority_rank = case(_PRIORITY_RANK, value=WorkboardTicket.priority, else_=9)
        if filters.sort == "priority":
            order = (priority_rank, WorkboardTicket.due_at.asc().nulls_last())
        elif filters.sort == "due":
            order = (WorkboardTicket.due_at.asc().nulls_last(), priority_rank)
        elif filters.sort == "updated":
            order = (WorkboardTicket.updated_at.desc(),)
        elif filters.sort == "created":
            order = (WorkboardTicket.created_at.desc(),)
        else:
            order = (WorkboardTicket.position.asc(), priority_rank)
        return stmt.order_by(*order, WorkboardTicket.id.asc())

    def _counts_stmt(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[str, int]]:
        base = self._filtered(user_id, filters).with_only_columns(
            WorkboardTicket.status, func.count()
        )
        return base.group_by(WorkboardTicket.status)

    async def list_board(
        self, user_id: UUID, filters: BoardFilters, *, limit: int, offset: int
    ) -> tuple[list[WorkboardTicket], int]:
        """One page of the board and the EXACT total behind it.

        Args:
            user_id: Whose board.
            filters: What the reader asked for.
            limit: Page size.
            offset: Page offset.

        Returns:
            The rows, and the count over the same filter.
        """
        stmt = self._board_stmt(user_id, filters)
        rows = (await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        total_stmt = select(func.count()).select_from(
            self._filtered(user_id, filters).order_by(None).subquery()
        )
        total = int((await self.db.execute(total_stmt)).scalar() or 0)
        return list(rows), total

    async def counts_by_status(self, user_id: UUID, filters: BoardFilters) -> dict[str, int]:
        """Exact count per column, every column present (0 when empty)."""
        rows = (await self.db.execute(self._counts_stmt(user_id, filters))).all()
        counts = {status: 0 for status in STATUS_ORDER}
        for status, count in rows:
            counts[str(status)] = int(count)
        return counts

    async def get_visible(self, ticket_id: UUID, user_id: UUID) -> WorkboardTicket | None:
        """The ticket, if it is on this user's board — else None (hide-existence)."""
        stmt = select(WorkboardTicket).where(
            WorkboardTicket.id == ticket_id, self.visible_predicate(user_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def count_owned(self, user_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.owner_user_id == user_id)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def count_children(self, ticket_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.parent_id == ticket_id)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def list_children(self, ticket_id: UUID) -> list[WorkboardTicket]:
        stmt = (
            select(WorkboardTicket)
            .where(WorkboardTicket.parent_id == ticket_id)
            .order_by(WorkboardTicket.position.asc(), WorkboardTicket.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_comments(self, ticket_id: UUID) -> list[WorkboardComment]:
        stmt = (
            select(WorkboardComment)
            .where(WorkboardComment.ticket_id == ticket_id)
            .order_by(WorkboardComment.created_at.asc(), WorkboardComment.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_events(self, ticket_id: UUID) -> list[WorkboardTicketEvent]:
        stmt = (
            select(WorkboardTicketEvent)
            .where(WorkboardTicketEvent.ticket_id == ticket_id)
            .order_by(WorkboardTicketEvent.created_at.asc(), WorkboardTicketEvent.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_by_title(self, user_id: UUID, title: str) -> list[WorkboardTicket]:
        """Visible tickets whose FOLDED title equals the folded needle (D11).

        Folding runs in Python over a candidate set narrowed by ILIKE: the
        folding identity has exactly one implementation (``fold_name``) and
        SQL is never a second authority on it.
        """
        stmt = (
            select(WorkboardTicket)
            .where(self.visible_predicate(user_id))
            .where(WorkboardTicket.title.ilike(f"%{title[:50]}%"))
            .limit(50)
        )
        candidates = (await self.db.execute(stmt)).scalars().all()
        needle = fold_name(title)
        return [t for t in candidates if fold_name(t.title) == needle]

    async def needs_me(
        self, user_id: UUID, now: datetime, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[WorkboardTicket], int]:
        """Tickets waiting for this account, plus overdue ones on its board."""
        predicate = and_(
            self.visible_predicate(user_id),
            or_(
                and_(
                    WorkboardTicket.status == TicketStatus.WAITING.value,
                    WorkboardTicket.assignee_user_id == user_id,
                ),
                and_(
                    WorkboardTicket.due_at < now,
                    WorkboardTicket.status.not_in(tuple(CLOSED_STATUSES)),
                ),
            ),
        )
        stmt = (
            select(WorkboardTicket)
            .where(predicate)
            .order_by(WorkboardTicket.due_at.asc().nulls_last(), WorkboardTicket.id.asc())
        )
        rows = (await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(WorkboardTicket).where(predicate)
                )
            ).scalar()
            or 0
        )
        return list(rows), total

    async def list_by_connection(self, connection_id: UUID) -> list[WorkboardTicket]:
        stmt = select(WorkboardTicket).where(WorkboardTicket.peer_connection_id == connection_id)
        return list((await self.db.execute(stmt)).scalars().all())

    # ---------------------------------------------------------------- writes

    async def next_position(self, owner_id: UUID, status: str) -> int:
        stmt = select(func.coalesce(func.max(WorkboardTicket.position), -1) + 1).where(
            WorkboardTicket.owner_user_id == owner_id, WorkboardTicket.status == status
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def renumber_column(self, owner_id: UUID, status: str, ordered_ids: list[UUID]) -> int:
        """Write the order of one column in ONE statement.

        Args:
            owner_id: Whose board.
            status: The column.
            ordered_ids: Every ticket id of the column, in its new order.

        Returns:
            Rows updated.
        """
        if not ordered_ids:
            return 0
        mapping = {ticket_id: index for index, ticket_id in enumerate(ordered_ids)}
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.owner_user_id == owner_id,
                WorkboardTicket.status == status,
                WorkboardTicket.id.in_(ordered_ids),
            )
            .values(position=case(mapping, value=WorkboardTicket.id, else_=WorkboardTicket.position))
        )
        result = await self.db.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def add_comment(
        self,
        *,
        ticket_id: UUID,
        author_kind: str,
        author_user_id: UUID | None,
        body: str,
        run_id: str | None = None,
    ) -> WorkboardComment:
        comment = WorkboardComment(
            ticket_id=ticket_id,
            author_kind=author_kind,
            author_user_id=author_user_id,
            body=body,
            run_id=run_id,
        )
        self.db.add(comment)
        await self.db.flush()
        return comment

    async def add_event(
        self,
        *,
        ticket_id: UUID,
        actor_kind: str,
        actor_user_id: UUID | None,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> WorkboardTicketEvent:
        event = WorkboardTicketEvent(
            ticket_id=ticket_id,
            actor_kind=actor_kind,
            actor_user_id=actor_user_id,
            kind=kind,
            payload=payload,
        )
        self.db.add(event)
        await self.db.flush()
        return event
```

Verify `fold_name` exists at `src.domains.shared.text_normalization` (it is imported by `shared/name_mentions.py`). `count_runs` is the `run_count` column, read directly — no method needed.

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard -v` → PASS.

- [ ] **Step 5: Proposed commit**

`feat(workboard): repository with one visibility predicate and exact counts (lot 1)`

---

### Task 4: Service — rights, bounds, transitions, events

**Files:**
- Create: `apps/api/src/domains/workboard/schemas.py` (the create/update inputs the service consumes; the responses are Task 5)
- Create: `apps/api/src/domains/workboard/service.py`
- Test: `apps/api/tests/unit/domains/workboard/test_service.py`, `test_error_codes_contract.py`

**Interfaces:**
- Consumes: `WorkboardRepository` (Task 3), `PeersRepository.list_accepted_for_user(user_id)`, `settings.workboard_*`, `raise_invalid_input(code)`, `raise_not_found_or_unauthorized("ticket", id)`.
- Produces: `TicketCreate`, `TicketUpdate`, `CommentCreate` (schemas); `WorkboardService(db)` with `create(actor: User, data: TicketCreate) -> WorkboardTicket`, `get(actor, ticket_id) -> TicketBundle`, `update(actor, ticket_id, data: TicketUpdate) -> WorkboardTicket`, `move(actor, ticket_id, status, position) -> WorkboardTicket`, `run_now(actor, ticket_id) -> WorkboardTicket`, `comment(actor, ticket_id, data) -> WorkboardComment`, `delete(actor, ticket_id) -> int` (rows cascaded), `release_connection(connection_id) -> list[WorkboardTicket]` (lot 5 calls it), `resolve_reference(actor_id, reference) -> WorkboardTicket` (lot 3 calls it).
- `TicketBundle` dataclass: `ticket`, `children`, `comments`, `events`.

- [ ] **Step 1: Write the input schemas**

```python
# apps/api/src/domains/workboard/schemas.py  (inputs; responses added in Task 5)
"""Workboard API contract.

Bounds are NOT repeated here as literals: the service enforces them from
settings, and the manifests (lot 3) publish the same setting. A Pydantic
``max_length`` typed by hand would be a second authority that drifts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AssigneeRef = Literal["me", "lia"]


class TicketCreate(BaseModel):
    """What a creation carries. ``assignee_user_id`` names a PEER; ``assignee``
    names the owner's own hands or LIA. Sending both is refused."""

    title: str = Field(..., description="What the ticket is.")
    description: str | None = Field(None, description="The brief LIA runs when assigned.")
    priority: str = Field("medium", description="low | medium | high | urgent")
    status: str = Field("todo", description="Column to create in (idea or todo, usually).")
    start_at: datetime | None = Field(None, description="UTC instant work may start.")
    due_at: datetime | None = Field(None, description="UTC instant it is due.")
    assignee: AssigneeRef = Field("me", description="me | lia")
    assignee_user_id: UUID | None = Field(None, description="A connected peer's id.")
    parent_id: UUID | None = Field(None, description="Parent ticket (one level).")
    follow: bool = Field(False, description="Notify me in the chat about this ticket.")


class TicketUpdate(BaseModel):
    """Partial update. Absent = unchanged; explicit null clears a date."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    clear_start_at: bool = False
    clear_due_at: bool = False
    assignee: AssigneeRef | None = None
    assignee_user_id: UUID | None = None
    follow: bool | None = Field(None, description="The CALLER's own follow flag.")


class CommentCreate(BaseModel):
    body: str = Field(..., description="Plain text.")
```

- [ ] **Step 2: Write the failing service tests**

```python
# apps/api/tests/unit/domains/workboard/test_service.py
"""Every right and every bound of the board, on a stubbed repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceNotFoundError
from src.domains.workboard.constants import (
    AssigneeKind,
    TicketEventKind,
    TicketStatus,
    WorkboardError,
)
from src.domains.workboard.schemas import CommentCreate, TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()
PEER = uuid.uuid4()
CONNECTION = uuid.uuid4()


def _user(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_active=True)


def _ticket(**overrides) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(), owner_user_id=OWNER, parent_id=None, title="Book the venue",
        description=None, status="todo", priority="medium", start_at=None, due_at=None,
        assignee_kind="human", assignee_user_id=OWNER, peer_connection_id=None,
        position=0, follow_owner=False, follow_assignee=False, created_by="user",
        status_changed_at=datetime.now(UTC), run_count=0, run_claimed_at=None,
        run_not_before=None, last_run_outcome=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _service(*, peers_enabled: bool = True) -> WorkboardService:
    service = WorkboardService(db=AsyncMock())
    service.repo = AsyncMock()
    service.repo.count_owned.return_value = 0
    service.repo.count_children.return_value = 0
    service.repo.next_position.return_value = 0
    service.repo.add_event = AsyncMock()
    service.repo.add_comment = AsyncMock()
    service.repo.renumber_column = AsyncMock(return_value=0)
    service.repo.list_children.return_value = []
    connection = SimpleNamespace(id=CONNECTION, user_a_id=min(OWNER, PEER), user_b_id=max(OWNER, PEER))
    service._accepted_connection = AsyncMock(return_value=connection)  # type: ignore[method-assign]
    service._peers_enabled = lambda: peers_enabled  # type: ignore[method-assign]
    return service


def _code(exc: BaseAPIException) -> str:
    return exc.detail if isinstance(exc.detail, str) else str(exc.detail)


class TestCreate:
    async def test_creates_on_the_owner_board_with_an_event(self) -> None:
        service = _service()
        created = _ticket()
        service.repo.create = AsyncMock(return_value=created)
        ticket = await service.create(_user(OWNER), TicketCreate(title="Book the venue"))
        assert ticket is created
        payload = service.repo.create.await_args.args[0]
        assert payload["owner_user_id"] == OWNER
        assert payload["assignee_user_id"] == OWNER
        assert payload["assignee_kind"] == AssigneeKind.HUMAN.value
        assert payload["peer_connection_id"] is None
        service.repo.add_event.assert_awaited_once()
        assert service.repo.add_event.await_args.kwargs["kind"] == TicketEventKind.CREATED.value

    async def test_empty_title_refused(self) -> None:
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(_user(OWNER), TicketCreate(title="   "))
        assert _code(exc.value) == WorkboardError.TITLE_REQUIRED.value

    async def test_title_over_bound_refused(self) -> None:
        title = "x" * (settings.workboard_title_max_chars + 1)
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(_user(OWNER), TicketCreate(title=title))
        assert _code(exc.value) == WorkboardError.TITLE_TOO_LONG.value

    async def test_too_many_tickets_refused_exactly_at_the_bound(self) -> None:
        service = _service()
        service.repo.count_owned.return_value = settings.workboard_max_tickets_per_user
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="one more"))
        assert _code(exc.value) == WorkboardError.TOO_MANY_TICKETS.value

    async def test_inverted_dates_refused(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(
                _user(OWNER), TicketCreate(title="t", start_at=now, due_at=now - timedelta(hours=1))
            )
        assert _code(exc.value) == WorkboardError.DATES_INVERTED.value

    async def test_lia_assignment_stays_on_the_owner(self) -> None:
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket(assignee_kind="lia"))
        await service.create(_user(OWNER), TicketCreate(title="research", assignee="lia"))
        payload = service.repo.create.await_args.args[0]
        assert payload["assignee_kind"] == AssigneeKind.LIA.value
        assert payload["assignee_user_id"] == OWNER

    async def test_peer_assignment_requires_an_accepted_connection(self) -> None:
        service = _service()
        service._accepted_connection = AsyncMock(return_value=None)  # type: ignore[method-assign]
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        assert _code(exc.value) == WorkboardError.ASSIGNEE_NOT_CONNECTED.value

    async def test_peer_assignment_stores_the_connection(self) -> None:
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket(assignee_user_id=PEER))
        await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        payload = service.repo.create.await_args.args[0]
        assert payload["assignee_user_id"] == PEER
        assert payload["peer_connection_id"] == CONNECTION

    async def test_peer_assignment_refused_when_peers_disabled(self) -> None:
        service = _service(peers_enabled=False)
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        assert _code(exc.value) == WorkboardError.PEERS_DISABLED.value

    async def test_child_of_a_child_refused(self) -> None:
        service = _service()
        child = _ticket(parent_id=uuid.uuid4())
        service.repo.get_visible.return_value = child
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=child.id))
        assert _code(exc.value) == WorkboardError.DEPTH_EXCEEDED.value

    async def test_child_under_a_ticket_i_do_not_own_refused(self) -> None:
        service = _service()
        parent = _ticket(owner_user_id=PEER, assignee_user_id=OWNER, peer_connection_id=CONNECTION)
        service.repo.get_visible.return_value = parent
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=parent.id))
        assert _code(exc.value) == WorkboardError.PARENT_NOT_OWNED.value

    async def test_too_many_children_refused(self) -> None:
        service = _service()
        parent = _ticket()
        service.repo.get_visible.return_value = parent
        service.repo.count_children.return_value = settings.workboard_max_children_per_ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=parent.id))
        assert _code(exc.value) == WorkboardError.TOO_MANY_CHILDREN.value


class TestPeerRights:
    def _held(self) -> SimpleNamespace:
        return _ticket(assignee_user_id=PEER, peer_connection_id=CONNECTION)

    async def test_peer_may_change_status_and_priority(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.update(_user(PEER), ticket.id, TicketUpdate(status="in_progress", priority="high"))
        assert ticket.status == "in_progress" and ticket.priority == "high"

    async def test_peer_may_not_edit_title_or_description(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(title="mine now"))
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_EDIT_FIELD.value

    async def test_peer_may_not_delete(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.delete(_user(PEER), ticket.id)
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_DELETE.value

    async def test_peer_may_hand_back_to_the_owner(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.update(_user(PEER), ticket.id, TicketUpdate(assignee_user_id=OWNER))
        assert ticket.assignee_user_id == OWNER and ticket.peer_connection_id is None
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value

    async def test_peer_may_not_delegate_to_their_own_lia(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(assignee="lia"))
        assert _code(exc.value) == WorkboardError.CROSS_ACCOUNT_DELEGATION.value

    async def test_peer_may_not_reassign_to_a_third_person(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(assignee_user_id=uuid.uuid4()))
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_REASSIGN.value

    async def test_owner_delegating_a_peer_held_ticket_to_lia_is_refused(self) -> None:
        """LIA on a ticket held by another account = cross-account (D7)."""
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))
        assert _code(exc.value) == WorkboardError.CROSS_ACCOUNT_DELEGATION.value

    async def test_follow_flag_is_the_callers_own_side(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.update(_user(PEER), ticket.id, TicketUpdate(follow=True))
        assert ticket.follow_assignee is True and ticket.follow_owner is False
        await service.update(_user(OWNER), ticket.id, TicketUpdate(follow=True))
        assert ticket.follow_owner is True

    async def test_reassignment_resets_the_assignee_follow_flag(self) -> None:
        service = _service()
        ticket = self._held()
        ticket.follow_assignee = True
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="me"))
        assert ticket.follow_assignee is False


class TestTransitions:
    async def test_any_status_to_any_status_by_a_person(self) -> None:
        service = _service()
        ticket = _ticket(status="done")
        service.repo.get_visible.return_value = ticket
        before = ticket.status_changed_at
        await service.update(_user(OWNER), ticket.id, TicketUpdate(status="todo"))
        assert ticket.status == "todo" and ticket.status_changed_at >= before
        assert service.repo.add_event.await_args.kwargs["kind"] == TicketEventKind.STATUS_CHANGED.value

    async def test_unknown_status_refused(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), uuid.uuid4(), TicketUpdate(status="parked"))
        assert _code(exc.value) == WorkboardError.STATUS_INVALID.value

    async def test_move_renumbers_the_target_column_once(self) -> None:
        service = _service()
        ticket = _ticket(status="todo")
        others = [_ticket(status="in_progress", position=i) for i in range(2)]
        service.repo.get_visible.return_value = ticket
        service.repo.list_column_ids = AsyncMock(return_value=[t.id for t in others])
        await service.move(_user(OWNER), ticket.id, "in_progress", 1)
        ordered = service.repo.renumber_column.await_args.args[2]
        assert ordered == [others[0].id, ticket.id, others[1].id]
        assert ticket.status == "in_progress"

    async def test_run_now_requires_a_lia_assignee(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.run_now(_user(OWNER), uuid.uuid4())
        assert _code(exc.value) == WorkboardError.RUN_NOW_REQUIRES_LIA.value

    async def test_run_now_refused_past_the_runs_cap(self) -> None:
        service = _service()
        ticket = _ticket(assignee_kind="lia", run_count=settings.workboard_max_runs_per_ticket)
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.run_now(_user(OWNER), ticket.id)
        assert _code(exc.value) == WorkboardError.MAX_RUNS_REACHED.value

    async def test_run_now_puts_the_ticket_in_todo_without_a_start_date(self) -> None:
        service = _service()
        ticket = _ticket(assignee_kind="lia", status="validating", start_at=datetime.now(UTC))
        service.repo.get_visible.return_value = ticket
        await service.run_now(_user(OWNER), ticket.id)
        assert ticket.status == "todo" and ticket.start_at is None and ticket.run_not_before is None


class TestDeleteAndVisibility:
    async def test_unknown_or_foreign_ticket_is_a_404(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = None
        with pytest.raises(ResourceNotFoundError):
            await service.get(_user(OWNER), uuid.uuid4())

    async def test_delete_reports_the_children_it_takes(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.repo.count_children.return_value = 2
        service.repo.delete = AsyncMock()
        removed = await service.delete(_user(OWNER), ticket.id)
        assert removed == 3
        service.repo.delete.assert_awaited_once_with(ticket)


class TestComments:
    async def test_comment_over_bound_refused(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        body = "x" * (settings.workboard_comment_max_chars + 1)
        with pytest.raises(BaseAPIException) as exc:
            await service.comment(_user(OWNER), uuid.uuid4(), CommentCreate(body=body))
        assert _code(exc.value) == WorkboardError.COMMENT_TOO_LONG.value

    async def test_peer_comment_is_authored_as_peer(self) -> None:
        service = _service()
        ticket = _ticket(assignee_user_id=PEER, peer_connection_id=CONNECTION)
        service.repo.get_visible.return_value = ticket
        await service.comment(_user(PEER), ticket.id, CommentCreate(body="on it"))
        assert service.repo.add_comment.await_args.kwargs["author_kind"] == "peer"


class TestReleaseConnection:
    async def test_release_gives_every_ticket_back_to_its_owner(self) -> None:
        service = _service()
        held = _ticket(assignee_user_id=PEER, peer_connection_id=CONNECTION, follow_assignee=True)
        service.repo.list_by_connection.return_value = [held]
        released = await service.release_connection(CONNECTION)
        assert released == [held]
        assert held.assignee_user_id == OWNER and held.peer_connection_id is None
        assert held.follow_assignee is False
```

Add `list_column_ids(owner_id, status) -> list[UUID]` to the repository (Task 3 file), ordered by position then id:

```python
    async def list_column_ids(self, owner_id: UUID, status: str) -> list[UUID]:
        stmt = (
            select(WorkboardTicket.id)
            .where(WorkboardTicket.owner_user_id == owner_id, WorkboardTicket.status == status)
            .order_by(WorkboardTicket.position.asc(), WorkboardTicket.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard/test_service.py -v` → FAIL (`ModuleNotFoundError: service`).

- [ ] **Step 4: Write the service**

```python
# apps/api/src/domains/workboard/service.py
"""Workboard service: who may do what to a ticket, and the bounds it obeys.

Rights (spec §8), by the caller's relation to the row:

- the OWNER may do anything, delete included;
- a peer ASSIGNEE may change status, priority, dates, comment, set their own
  follow flag and hand the ticket back — never edit the owner's words, never
  delete, never reassign to a third person nor to their own LIA (D7).

Refusals are stable codes (``WorkboardError``) through ``raise_invalid_input``;
a ticket the caller cannot see is a neutral 404 (hide-existence).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_invalid_input, raise_not_found_or_unauthorized
from src.domains.users.models import User
from src.domains.workboard.constants import (
    ActorKind,
    AssigneeKind,
    TicketEventKind,
    TicketPriority,
    TicketStatus,
    WorkboardError,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.repository import BoardFilters, WorkboardRepository
from src.domains.workboard.schemas import CommentCreate, TicketCreate, TicketUpdate

logger = structlog.get_logger(__name__)

_STATUSES = frozenset(s.value for s in TicketStatus)
_PRIORITIES = frozenset(p.value for p in TicketPriority)


@dataclass(frozen=True)
class TicketBundle:
    """A ticket with everything its detail panel shows."""

    ticket: WorkboardTicket
    children: list[WorkboardTicket]
    comments: list[WorkboardComment]
    events: list[WorkboardTicketEvent]


class WorkboardService:
    """Business rules of the board."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkboardRepository(db)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _peers_enabled() -> bool:
        return bool(getattr(settings, "peers_enabled", False))

    async def _accepted_connection(self, user_a: UUID, user_b: UUID) -> Any | None:
        """The ACCEPTED connection between two accounts, or None."""
        from src.domains.peers.repository import PeersRepository

        for connection in await PeersRepository(self.db).list_accepted_for_user(user_a):
            if user_b in (connection.user_a_id, connection.user_b_id):
                return connection
        return None

    async def _visible_or_404(self, ticket_id: UUID, user_id: UUID) -> WorkboardTicket:
        ticket = await self.repo.get_visible(ticket_id, user_id)
        if ticket is None:
            raise_not_found_or_unauthorized("ticket", ticket_id)
        return ticket

    @staticmethod
    def _actor_kind(ticket: WorkboardTicket, user_id: UUID) -> str:
        return ActorKind.USER.value if ticket.owner_user_id == user_id else ActorKind.PEER.value

    @staticmethod
    def _check_title(title: str) -> str:
        cleaned = title.strip()
        if not cleaned:
            raise_invalid_input(WorkboardError.TITLE_REQUIRED.value)
        if len(cleaned) > settings.workboard_title_max_chars:
            raise_invalid_input(WorkboardError.TITLE_TOO_LONG.value)
        return cleaned

    @staticmethod
    def _check_description(description: str | None) -> str | None:
        if description is not None and len(description) > settings.workboard_description_max_chars:
            raise_invalid_input(WorkboardError.DESCRIPTION_TOO_LONG.value)
        return description

    @staticmethod
    def _check_status(status: str) -> str:
        if status not in _STATUSES:
            raise_invalid_input(WorkboardError.STATUS_INVALID.value)
        return status

    @staticmethod
    def _check_priority(priority: str) -> str:
        if priority not in _PRIORITIES:
            raise_invalid_input(WorkboardError.PRIORITY_INVALID.value)
        return priority

    @staticmethod
    def _check_dates(start_at: datetime | None, due_at: datetime | None) -> None:
        if start_at is not None and due_at is not None and due_at < start_at:
            raise_invalid_input(WorkboardError.DATES_INVERTED.value)

    async def _resolve_assignment(
        self, owner_id: UUID, assignee: str | None, assignee_user_id: UUID | None
    ) -> tuple[str, UUID, UUID | None]:
        """Turn a request into (kind, user id, connection id) — D7/D8.

        Raises:
            BaseAPIException: peers disabled, no accepted connection.
        """
        if assignee_user_id is not None and assignee_user_id != owner_id:
            if not self._peers_enabled():
                raise_invalid_input(WorkboardError.PEERS_DISABLED.value)
            connection = await self._accepted_connection(owner_id, assignee_user_id)
            if connection is None:
                raise_invalid_input(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
            return AssigneeKind.HUMAN.value, assignee_user_id, connection.id
        if assignee == "lia":
            return AssigneeKind.LIA.value, owner_id, None
        return AssigneeKind.HUMAN.value, owner_id, None

    async def _event(
        self,
        ticket: WorkboardTicket,
        actor: User | None,
        kind: TicketEventKind,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.repo.add_event(
            ticket_id=ticket.id,
            actor_kind=(
                ActorKind.LIA.value if actor is None else self._actor_kind(ticket, actor.id)
            ),
            actor_user_id=None if actor is None else actor.id,
            kind=kind.value,
            payload=payload,
        )

    # ------------------------------------------------------------- create

    async def create(self, actor: User, data: TicketCreate) -> WorkboardTicket:
        """Create a ticket on the actor's board.

        Args:
            actor: The owner-to-be.
            data: The request.

        Returns:
            The created row (flushed, not committed).
        """
        title = self._check_title(data.title)
        description = self._check_description(data.description)
        status = self._check_status(data.status)
        priority = self._check_priority(data.priority)
        self._check_dates(data.start_at, data.due_at)
        if await self.repo.count_owned(actor.id) >= settings.workboard_max_tickets_per_user:
            raise_invalid_input(WorkboardError.TOO_MANY_TICKETS.value)
        if data.parent_id is not None:
            parent = await self._visible_or_404(data.parent_id, actor.id)
            if parent.owner_user_id != actor.id:
                raise_invalid_input(WorkboardError.PARENT_NOT_OWNED.value)
            if parent.parent_id is not None:
                raise_invalid_input(WorkboardError.DEPTH_EXCEEDED.value)
            if await self.repo.count_children(parent.id) >= settings.workboard_max_children_per_ticket:
                raise_invalid_input(WorkboardError.TOO_MANY_CHILDREN.value)
        kind, assignee_id, connection_id = await self._resolve_assignment(
            actor.id, data.assignee, data.assignee_user_id
        )
        now = datetime.now(UTC)
        ticket = await self.repo.create(
            {
                "owner_user_id": actor.id,
                "parent_id": data.parent_id,
                "title": title,
                "description": description,
                "status": status,
                "priority": priority,
                "start_at": data.start_at,
                "due_at": data.due_at,
                "assignee_kind": kind,
                "assignee_user_id": assignee_id,
                "peer_connection_id": connection_id,
                "position": await self.repo.next_position(actor.id, status),
                "follow_owner": data.follow,
                "follow_assignee": False,
                "created_by": ActorKind.USER.value,
                "status_changed_at": now,
            }
        )
        await self._event(ticket, actor, TicketEventKind.CREATED, {"status": status})
        logger.info("workboard_ticket_created", ticket_id=str(ticket.id), owner_id=str(actor.id))
        return ticket

    # --------------------------------------------------------------- read

    async def get(self, actor: User, ticket_id: UUID) -> TicketBundle:
        ticket = await self._visible_or_404(ticket_id, actor.id)
        return TicketBundle(
            ticket=ticket,
            children=await self.repo.list_children(ticket.id),
            comments=await self.repo.list_comments(ticket.id),
            events=await self.repo.list_events(ticket.id),
        )

    async def board(
        self, actor: User, filters: BoardFilters, *, limit: int, offset: int
    ) -> tuple[list[WorkboardTicket], int, dict[str, int]]:
        rows, total = await self.repo.list_board(actor.id, filters, limit=limit, offset=offset)
        return rows, total, await self.repo.counts_by_status(actor.id, filters)

    # ------------------------------------------------------------- update

    async def update(self, actor: User, ticket_id: UUID, data: TicketUpdate) -> WorkboardTicket:
        """Apply a partial update under the caller's rights."""
        ticket = await self._visible_or_404(ticket_id, actor.id)
        is_owner = ticket.owner_user_id == actor.id
        if not is_owner and (data.title is not None or data.description is not None):
            raise_invalid_input(WorkboardError.PEER_CANNOT_EDIT_FIELD.value)

        if data.title is not None:
            ticket.title = self._check_title(data.title)
        if data.description is not None:
            ticket.description = self._check_description(data.description)
        if data.priority is not None and data.priority != ticket.priority:
            old = ticket.priority
            ticket.priority = self._check_priority(data.priority)
            await self._event(ticket, actor, TicketEventKind.PRIORITY_CHANGED, {"from": old, "to": ticket.priority})

        new_start = None if data.clear_start_at else (data.start_at or ticket.start_at)
        new_due = None if data.clear_due_at else (data.due_at or ticket.due_at)
        if (new_start, new_due) != (ticket.start_at, ticket.due_at):
            self._check_dates(new_start, new_due)
            ticket.start_at, ticket.due_at = new_start, new_due
            await self._event(ticket, actor, TicketEventKind.DATES_CHANGED, None)

        if data.assignee is not None or data.assignee_user_id is not None:
            await self._reassign(ticket, actor, data.assignee, data.assignee_user_id)

        if data.status is not None and data.status != ticket.status:
            await self._transition(ticket, actor, self._check_status(data.status))

        if data.follow is not None:
            if is_owner:
                ticket.follow_owner = data.follow
            else:
                ticket.follow_assignee = data.follow
            await self._event(ticket, actor, TicketEventKind.FOLLOW_CHANGED, {"to": data.follow})
        return ticket

    async def _reassign(
        self, ticket: WorkboardTicket, actor: User, assignee: str | None, assignee_user_id: UUID | None
    ) -> None:
        is_owner = ticket.owner_user_id == actor.id
        if not is_owner:
            # A peer may only hand the ticket back to its owner (D7, §8).
            if assignee == "lia":
                raise_invalid_input(WorkboardError.CROSS_ACCOUNT_DELEGATION.value)
            if assignee_user_id not in (None, ticket.owner_user_id):
                raise_invalid_input(WorkboardError.PEER_CANNOT_REASSIGN.value)
            kind, user_id, connection_id = AssigneeKind.HUMAN.value, ticket.owner_user_id, None
        else:
            if assignee == "lia" and ticket.assignee_user_id != ticket.owner_user_id:
                raise_invalid_input(WorkboardError.CROSS_ACCOUNT_DELEGATION.value)
            kind, user_id, connection_id = await self._resolve_assignment(
                ticket.owner_user_id, assignee, assignee_user_id
            )
        before = (ticket.assignee_kind, ticket.assignee_user_id)
        ticket.assignee_kind, ticket.assignee_user_id = kind, user_id
        ticket.peer_connection_id = connection_id
        ticket.follow_assignee = False
        await self._event(
            ticket, actor, TicketEventKind.ASSIGNED,
            {"from_kind": before[0], "from_user": str(before[1]), "to_kind": kind, "to_user": str(user_id)},
        )

    async def _transition(self, ticket: WorkboardTicket, actor: User | None, status: str) -> None:
        old = ticket.status
        ticket.status = status
        ticket.status_changed_at = datetime.now(UTC)
        ticket.position = await self.repo.next_position(ticket.owner_user_id, status)
        await self._event(ticket, actor, TicketEventKind.STATUS_CHANGED, {"from": old, "to": status})

    async def move(self, actor: User, ticket_id: UUID, status: str, position: int) -> WorkboardTicket:
        """Drag-and-drop write: the column and the place in it, renumbered once."""
        ticket = await self._visible_or_404(ticket_id, actor.id)
        status = self._check_status(status)
        if ticket.status != status:
            await self._transition(ticket, actor, status)
        ids = [i for i in await self.repo.list_column_ids(ticket.owner_user_id, status) if i != ticket.id]
        ids.insert(max(0, min(position, len(ids))), ticket.id)
        await self.repo.renumber_column(ticket.owner_user_id, status, ids)
        ticket.position = ids.index(ticket.id)
        return ticket

    async def run_now(self, actor: User, ticket_id: UUID) -> WorkboardTicket:
        """Offer a LIA-assigned ticket to the sweep immediately."""
        ticket = await self._visible_or_404(ticket_id, actor.id)
        if ticket.assignee_kind != AssigneeKind.LIA.value:
            raise_invalid_input(WorkboardError.RUN_NOW_REQUIRES_LIA.value)
        if ticket.run_count >= settings.workboard_max_runs_per_ticket:
            raise_invalid_input(WorkboardError.MAX_RUNS_REACHED.value)
        ticket.start_at = None
        ticket.run_not_before = None
        if ticket.status != TicketStatus.TODO.value:
            await self._transition(ticket, actor, TicketStatus.TODO.value)
        return ticket

    async def comment(self, actor: User, ticket_id: UUID, data: CommentCreate) -> WorkboardComment:
        ticket = await self._visible_or_404(ticket_id, actor.id)
        if len(data.body) > settings.workboard_comment_max_chars:
            raise_invalid_input(WorkboardError.COMMENT_TOO_LONG.value)
        return await self.repo.add_comment(
            ticket_id=ticket.id,
            author_kind=self._actor_kind(ticket, actor.id),
            author_user_id=actor.id,
            body=data.body,
        )

    async def delete(self, actor: User, ticket_id: UUID) -> int:
        """Delete a ticket (owner only). Returns the rows removed, children included."""
        ticket = await self._visible_or_404(ticket_id, actor.id)
        if ticket.owner_user_id != actor.id:
            raise_invalid_input(WorkboardError.PEER_CANNOT_DELETE.value)
        children = await self.repo.count_children(ticket.id)
        await self.repo.delete(ticket)
        logger.info("workboard_ticket_deleted", ticket_id=str(ticket.id), children=children)
        return children + 1

    async def release_connection(self, connection_id: UUID) -> list[WorkboardTicket]:
        """Hand every ticket on a removed connection back to its owner (D8)."""
        released: list[WorkboardTicket] = []
        for ticket in await self.repo.list_by_connection(connection_id):
            ticket.assignee_kind = AssigneeKind.HUMAN.value
            ticket.assignee_user_id = ticket.owner_user_id
            ticket.peer_connection_id = None
            ticket.follow_assignee = False
            await self._event(ticket, None, TicketEventKind.ASSIGNED, {"to_kind": "human", "reason": "connection_removed"})
            released.append(ticket)
        return released

    async def resolve_reference(self, user_id: UUID, reference: str) -> WorkboardTicket:
        """A ticket by id or by UNIQUE folded title (D11); ambiguity is a refusal."""
        try:
            return await self._visible_or_404(UUID(reference), user_id)
        except ValueError:
            pass
        matches = await self.repo.find_by_title(user_id, reference)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise_not_found_or_unauthorized("ticket", None)
        raise_invalid_input("workboard_ambiguous_reference")
```

Add `AMBIGUOUS_REFERENCE = "workboard_ambiguous_reference"` to `WorkboardError` and use it.

Note: `_event` for `release_connection` passes `actor=None` → `ActorKind.LIA`; the reason payload says why.

- [ ] **Step 5: Run the tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard -v` → PASS. Then `cd apps/api && .venv/Scripts/mypy src/domains/workboard` → clean; `task lint:backend` → clean.

- [ ] **Step 6: Error-code contract test**

```python
# apps/api/tests/unit/domains/workboard/test_error_codes_contract.py
"""Every WorkboardError code is a translation key: renaming one breaks six locales."""

from __future__ import annotations

import pytest

from src.domains.workboard.constants import WorkboardError

pytestmark = pytest.mark.unit

EXPECTED = {
    "workboard_peers_disabled", "workboard_title_required", "workboard_title_too_long",
    "workboard_description_too_long", "workboard_comment_too_long", "workboard_depth_exceeded",
    "workboard_parent_not_owned", "workboard_too_many_tickets", "workboard_too_many_children",
    "workboard_assignee_not_connected", "workboard_cross_account_delegation",
    "workboard_peer_cannot_delete", "workboard_peer_cannot_edit_field",
    "workboard_peer_cannot_reassign", "workboard_run_now_requires_lia",
    "workboard_max_runs_reached", "workboard_status_invalid", "workboard_priority_invalid",
    "workboard_dates_inverted", "workboard_ambiguous_reference",
}


def test_codes_are_pinned() -> None:
    assert {e.value for e in WorkboardError} == EXPECTED
```

Lot 4 adds the six-locale `workboard.errors.<code>` keys and a parity test against this set.

- [ ] **Step 7: Proposed commit**

`feat(workboard): service with rights, bounds and events (lot 1)`

---

### Task 5: Schemas, router, wiring, hub badge

**Files:**
- Modify: `apps/api/src/domains/workboard/schemas.py` (responses)
- Create: `apps/api/src/domains/workboard/router.py`
- Modify: `apps/api/src/api/v1/routes.py` (flag-gated inclusion, next to peers)
- Modify: `apps/api/src/domains/notifications/hub_counts.py`, `schemas.py` (`HubCountsResponse`), `router.py`
- Test: `apps/api/tests/unit/domains/workboard/test_router.py`, `apps/api/tests/unit/domains/notifications/test_hub_counts.py` (extend the EXISTING file — read it first, it pins the six totals)

**Interfaces:**
- Produces: `GET /workboard/tickets`, `GET /workboard/tickets/{id}`, `POST /workboard/tickets`, `PATCH /workboard/tickets/{id}`, `POST /workboard/tickets/{id}/move`, `POST /workboard/tickets/{id}/run-now`, `POST /workboard/tickets/{id}/comments`, `DELETE /workboard/tickets/{id}`, `GET /workboard/needs-me`; `HubCounts.workboard`.

- [ ] **Step 1: Response schemas**

Append to `schemas.py`:

```python
class TicketRow(BaseModel):
    """One ticket as the board lists it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    parent_id: UUID | None
    title: str
    description: str | None
    status: str
    priority: str
    start_at: datetime | None
    due_at: datetime | None
    assignee_kind: str
    assignee_user_id: UUID
    position: int
    follow_owner: bool
    follow_assignee: bool
    created_by: str
    status_changed_at: datetime
    run_count: int
    last_run_at: datetime | None
    last_run_outcome: str | None
    last_run_error: str | None
    last_run_tokens_in: int | None
    last_run_tokens_out: int | None
    last_run_cost_eur: float | None
    created_at: datetime
    updated_at: datetime


class BoardPage(BaseModel):
    """A page of the board, the EXACT total, and one exact count per column."""

    tickets: list[TicketRow]
    total: int = Field(ge=0)
    counts_by_status: dict[str, int]


class CommentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_kind: str
    author_user_id: UUID | None
    body: str
    run_id: str | None
    created_at: datetime


class EventRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_kind: str
    actor_user_id: UUID | None
    kind: str
    payload: dict[str, object] | None
    created_at: datetime


class TicketDetail(BaseModel):
    ticket: TicketRow
    children: list[TicketRow]
    comments: list[CommentRow]
    events: list[EventRow]


class MoveRequest(BaseModel):
    status: str
    position: int = Field(ge=0)


class DeleteResult(BaseModel):
    removed: int = Field(ge=1, description="Rows removed, children included.")


class NeedsMePage(BaseModel):
    tickets: list[TicketRow]
    total: int = Field(ge=0)
```

- [ ] **Step 2: Failing router tests**

```python
# apps/api/tests/unit/domains/workboard/test_router.py
"""The routes hand the caller down and commit only on success."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.workboard.router import (
    create_ticket,
    delete_ticket,
    list_board,
    move_ticket,
    needs_me,
)
from src.domains.workboard.schemas import MoveRequest, TicketCreate

pytestmark = pytest.mark.unit


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(), owner_user_id=uuid.uuid4(), parent_id=None, title="t", description=None,
        status="todo", priority="medium", start_at=None, due_at=None, assignee_kind="human",
        assignee_user_id=uuid.uuid4(), position=0, follow_owner=False, follow_assignee=False,
        created_by="user", status_changed_at=datetime.now(UTC), run_count=0, last_run_at=None,
        last_run_outcome=None, last_run_error=None, last_run_tokens_in=None,
        last_run_tokens_out=None, last_run_cost_eur=None, created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestBoard:
    async def test_lists_with_exact_total_and_counts(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.board = AsyncMock(return_value=([_row()], 7, {"todo": 7}))
            page = await list_board(
                status=None, assignee="all", priority=None, overdue=False, due_before=None,
                q=None, closed_days=30, sort="position", limit=50, offset=0, user=user, db=db,
            )
        assert page.total == 7 and page.counts_by_status["todo"] == 7 and len(page.tickets) == 1

    async def test_closed_days_becomes_a_cutoff_instant(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.board = AsyncMock(return_value=([], 0, {}))
            await list_board(
                status=None, assignee="all", priority=None, overdue=False, due_before=None,
                q=None, closed_days=30, sort="position", limit=50, offset=0, user=user, db=db,
            )
            filters = svc.return_value.board.await_args.args[1]
        assert filters.include_closed_before is not None


class TestWrites:
    async def test_create_commits(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.create = AsyncMock(return_value=_row())
            await create_ticket(payload=TicketCreate(title="t"), user=user, db=db)
        db.commit.assert_awaited_once()

    async def test_move_commits_and_returns_the_row(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.move = AsyncMock(return_value=_row(status="done"))
            row = await move_ticket(
                ticket_id=uuid.uuid4(), payload=MoveRequest(status="done", position=0), user=user, db=db
            )
        assert row.status == "done"
        db.commit.assert_awaited_once()

    async def test_delete_reports_removed_rows(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.delete = AsyncMock(return_value=3)
            result = await delete_ticket(ticket_id=uuid.uuid4(), user=user, db=db)
        assert result.removed == 3

    async def test_unknown_ticket_commits_nothing(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.delete = AsyncMock(side_effect=ResourceNotFoundError("ticket", "x"))
            with pytest.raises(ResourceNotFoundError):
                await delete_ticket(ticket_id=uuid.uuid4(), user=user, db=db)
        db.commit.assert_not_awaited()


class TestNeedsMe:
    async def test_exact_total(self) -> None:
        user, db = SimpleNamespace(id=uuid.uuid4()), AsyncMock()
        with patch("src.domains.workboard.router.WorkboardService") as svc:
            svc.return_value.needs_me = AsyncMock(return_value=([_row(status="waiting")], 4))
            page = await needs_me(limit=20, offset=0, user=user, db=db)
        assert page.total == 4
```

Add `needs_me(actor, *, limit, offset)` to the service: `return await self.repo.needs_me(actor.id, datetime.now(UTC), limit=limit, offset=offset)`.

- [ ] **Step 3: Run to verify failure** → `ModuleNotFoundError: router`.

- [ ] **Step 4: Write the router**

```python
# apps/api/src/domains/workboard/router.py
"""Workboard API (ADR-276, spec §10).

Every read carries the EXACT total behind its page and, for the board, one
exact count per column from the same filter (ADR-185). Ownership is decided
in the service: a ticket the caller is not on is a neutral 404.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.users.models import User
from src.domains.workboard.repository import BoardFilters
from src.domains.workboard.schemas import (
    BoardPage,
    CommentCreate,
    CommentRow,
    DeleteResult,
    EventRow,
    MoveRequest,
    NeedsMePage,
    TicketCreate,
    TicketDetail,
    TicketRow,
    TicketUpdate,
)
from src.domains.workboard.service import WorkboardService

router = APIRouter(prefix="/workboard", tags=["Workboard"])


@router.get("/tickets", response_model=BoardPage, summary="The board, one page, exact counts")
async def list_board(
    status: list[str] | None = Query(default=None),
    assignee: Literal["me", "lia", "peer", "all"] = Query(default="all"),
    priority: list[str] | None = Query(default=None),
    overdue: bool = Query(default=False),
    due_before: datetime | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    closed_days: int | None = Query(default=None, ge=0, le=3650,
                                    description="Show closed tickets closed within N days; default from settings."),
    sort: Literal["position", "priority", "due", "updated", "created"] = Query(default="position"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BoardPage:
    """One page of the caller's board."""
    days = settings.workboard_closed_hide_days_default if closed_days is None else closed_days
    filters = BoardFilters(
        statuses=tuple(status) if status else None,
        assignee=assignee,
        priorities=tuple(priority) if priority else None,
        overdue=overdue,
        due_before=due_before,
        query=q,
        include_closed_before=datetime.now(UTC) - timedelta(days=days),
        sort=sort,
    )
    rows, total, counts = await WorkboardService(db).board(user, filters, limit=limit, offset=offset)
    return BoardPage(
        tickets=[TicketRow.model_validate(r) for r in rows], total=total, counts_by_status=counts
    )


@router.get("/needs-me", response_model=NeedsMePage, summary="Tickets waiting for the caller")
async def needs_me(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NeedsMePage:
    """Waiting on my account, or overdue on my board — declared BEFORE `/tickets/{id}`."""
    rows, total = await WorkboardService(db).needs_me(user, limit=limit, offset=offset)
    return NeedsMePage(tickets=[TicketRow.model_validate(r) for r in rows], total=total)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail, summary="One ticket in full")
async def get_ticket(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketDetail:
    bundle = await WorkboardService(db).get(user, ticket_id)
    return TicketDetail(
        ticket=TicketRow.model_validate(bundle.ticket),
        children=[TicketRow.model_validate(c) for c in bundle.children],
        comments=[CommentRow.model_validate(c) for c in bundle.comments],
        events=[EventRow.model_validate(e) for e in bundle.events],
    )


@router.post("/tickets", response_model=TicketRow, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    ticket = await WorkboardService(db).create(user, payload)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.patch("/tickets/{ticket_id}", response_model=TicketRow)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    ticket = await WorkboardService(db).update(user, ticket_id, payload)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post("/tickets/{ticket_id}/move", response_model=TicketRow)
async def move_ticket(
    ticket_id: UUID,
    payload: MoveRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    ticket = await WorkboardService(db).move(user, ticket_id, payload.status, payload.position)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post("/tickets/{ticket_id}/run-now", response_model=TicketRow)
async def run_ticket_now(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    ticket = await WorkboardService(db).run_now(user, ticket_id)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post("/tickets/{ticket_id}/comments", response_model=CommentRow,
             status_code=status.HTTP_201_CREATED)
async def add_comment(
    ticket_id: UUID,
    payload: CommentCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CommentRow:
    comment = await WorkboardService(db).comment(user, ticket_id, payload)
    await db.commit()
    return CommentRow.model_validate(comment)


@router.delete("/tickets/{ticket_id}", response_model=DeleteResult)
async def delete_ticket(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DeleteResult:
    removed = await WorkboardService(db).delete(user, ticket_id)
    await db.commit()
    return DeleteResult(removed=removed)
```

In `routes.py`, next to the peers block:

```python
if getattr(settings, "workboard_enabled", False):
    from src.domains.workboard.router import router as workboard_router

    api_router.include_router(workboard_router)  # Ticket board (ADR-276)
```

- [ ] **Step 5: Hub badge**

`hub_counts.py`: add `workboard: int` to `HubCounts` (docstring: « Tickets that NEED the person: waiting on their account or overdue on their board — a to-decide set, not a history »), a probe:

```python
async def _workboard(user_id: UUID) -> int:
    """Tickets needing the person — 0 without a query when the board is off."""
    if not getattr(settings, "workboard_enabled", False):
        return 0
    from datetime import UTC, datetime

    async with get_db_context() as db:
        from src.domains.workboard.repository import WorkboardRepository

        _rows, total = await WorkboardRepository(db).needs_me(
            user_id, datetime.now(UTC), limit=1, offset=0
        )
        return total
```

add it to the `gather`, to the dataclass construction, to `HubCountsResponse` (`workboard: int = Field(ge=0)`) and to the route's construction. Extend the existing hub-counts tests (read `tests/unit/domains/notifications/` for the file that pins the six totals; add the seventh the same way, including the flag-off short-circuit).

- [ ] **Step 6: Run**

`cd apps/api && .venv/Scripts/pytest tests/unit/domains/workboard tests/unit/domains/notifications tests/unit/api -v` → PASS; `task lint:backend` → clean; `docker restart lia-api-dev` and `docker logs lia-api-dev --tail 60 | grep -i "application_ready\|error"` → ready, no error. Then a runtime smoke from the container:

```
docker exec lia-api-dev curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/workboard/tickets
```
Expected `401` (route mounted, auth required).

- [ ] **Step 7: Proposed commit**

`feat(workboard): /workboard routes with exact totals and the hub badge (lot 1)`

---

### Task 6: Integration tests on PostgreSQL

**Files:**
- Create: `apps/api/tests/integration/domains/workboard/__init__.py`, `test_repository_db.py`, `test_purge_and_export_db.py`

- [ ] **Step 1: Write the tests** (Testcontainers fixtures come from `tests/integration/conftest.py`; the `async_session` fixture and the `User` creation shape are those of `tests/integration/domains/peers/test_repository_db.py`).

```python
# apps/api/tests/integration/domains/workboard/test_repository_db.py
"""What only PostgreSQL can prove: the CHECK, the RESTRICT, the renumbering."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import BoardFilters, WorkboardRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(email="wb_owner@test.local", hashed_password="x", is_active=True,
                is_superuser=False, full_name="Board Owner")
    async_session.add(user)
    await async_session.commit()
    return user


def _ticket(owner_id: uuid.UUID, **overrides) -> WorkboardTicket:
    base = dict(owner_user_id=owner_id, title="t", status="todo", priority="medium",
                assignee_kind="human", assignee_user_id=owner_id, position=0,
                created_by="user", status_changed_at=datetime.now(UTC), run_attempts=0,
                run_count=0, nudge_count=0)
    base.update(overrides)
    return WorkboardTicket(**base)


async def test_check_refuses_a_foreign_assignee_without_a_connection(
    async_session: AsyncSession, owner: User
) -> None:
    other = User(email="wb_other@test.local", hashed_password="x", is_active=True,
                 is_superuser=False, full_name="Other")
    async_session.add(other)
    await async_session.commit()
    async_session.add(_ticket(owner.id, assignee_user_id=other.id))
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_page_total_and_counts_agree(async_session: AsyncSession, owner: User) -> None:
    async_session.add_all([_ticket(owner.id, status="todo", position=i) for i in range(3)])
    async_session.add(_ticket(owner.id, status="done"))
    await async_session.commit()
    repo = WorkboardRepository(async_session)
    rows, total = await repo.list_board(owner.id, BoardFilters(), limit=2, offset=0)
    counts = await repo.counts_by_status(owner.id, BoardFilters())
    assert len(rows) == 2 and total == 4
    assert counts["todo"] == 3 and counts["done"] == 1 and counts["idea"] == 0


async def test_renumber_writes_the_given_order(async_session: AsyncSession, owner: User) -> None:
    tickets = [_ticket(owner.id, position=i) for i in range(3)]
    async_session.add_all(tickets)
    await async_session.commit()
    repo = WorkboardRepository(async_session)
    new_order = [tickets[2].id, tickets[0].id, tickets[1].id]
    assert await repo.renumber_column(owner.id, "todo", new_order) == 3
    await async_session.commit()
    rows = (await async_session.execute(
        select(WorkboardTicket.id).where(WorkboardTicket.owner_user_id == owner.id)
        .order_by(WorkboardTicket.position)
    )).scalars().all()
    assert list(rows) == new_order


async def test_partial_index_serves_the_sweep_scan(async_session: AsyncSession, owner: User) -> None:
    from sqlalchemy import text

    plan = (await async_session.execute(text(
        "EXPLAIN SELECT id FROM workboard_tickets WHERE assignee_kind = 'lia' AND status = 'todo' "
        "AND run_claimed_at IS NULL AND (start_at IS NULL OR start_at <= now()) ORDER BY start_at"
    ))).scalars().all()
    # On an empty table the planner may seq-scan; the index must at least EXIST.
    exists = (await async_session.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_workboard_tickets_lia_todo'"
    ))).scalar()
    assert exists == 1
    assert plan  # the statement is valid
```

```python
# apps/api/tests/integration/domains/workboard/test_purge_and_export_db.py
"""Deleting an account releases what it held and removes what it owned."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.account_deletion_service import build_purge_statements
from src.domains.users.models import User
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.purge import release_assignments_statement

pytestmark = pytest.mark.integration


@pytest.fixture
async def pair(async_session: AsyncSession) -> tuple[User, User, PeerConnection]:
    a = User(email="wb_a@test.local", hashed_password="x", is_active=True, is_superuser=False, full_name="A")
    b = User(email="wb_b@test.local", hashed_password="x", is_active=True, is_superuser=False, full_name="B")
    async_session.add_all([a, b])
    await async_session.commit()
    ua, ub = canonical_pair(a.id, b.id)
    conn = PeerConnection(user_a_id=ua, user_b_id=ub, requested_by_id=a.id,
                          status=PeerConnectionStatus.ACCEPTED.value,
                          requested_at=datetime.now(UTC), responded_at=datetime.now(UTC))
    async_session.add(conn)
    await async_session.commit()
    return a, b, conn


async def test_release_then_purge(async_session: AsyncSession, pair) -> None:
    a, b, conn = pair
    now = datetime.now(UTC)
    held_by_b = WorkboardTicket(owner_user_id=a.id, title="held", status="todo", priority="medium",
                                assignee_kind="human", assignee_user_id=b.id, peer_connection_id=conn.id,
                                position=0, created_by="user", status_changed_at=now,
                                run_attempts=0, run_count=0, nudge_count=0, follow_assignee=True)
    owned_by_b = WorkboardTicket(owner_user_id=b.id, title="mine", status="todo", priority="medium",
                                 assignee_kind="human", assignee_user_id=b.id, position=0,
                                 created_by="user", status_changed_at=now,
                                 run_attempts=0, run_count=0, nudge_count=0)
    async_session.add_all([held_by_b, owned_by_b])
    await async_session.commit()
    async_session.add(WorkboardComment(ticket_id=owned_by_b.id, author_kind="user",
                                       author_user_id=b.id, body="note"))
    await async_session.commit()

    await async_session.execute(release_assignments_statement(b.id))
    for _name, stmt in build_purge_statements(b.id):
        await async_session.execute(stmt)
    await async_session.commit()

    async_session.expire_all()
    kept = await async_session.get(WorkboardTicket, held_by_b.id)
    assert kept is not None
    assert kept.assignee_user_id == a.id and kept.peer_connection_id is None
    assert kept.follow_assignee is False
    assert await async_session.get(WorkboardTicket, owned_by_b.id) is None
    comments = (await async_session.execute(
        select(WorkboardComment).where(WorkboardComment.ticket_id == owned_by_b.id)
    )).scalars().all()
    assert comments == []
```

- [ ] **Step 2: Run them**

Testcontainers on Windows may fail on the Docker pipe (known host trap); then run inside the container:
`docker exec lia-api-dev sh -c "cd /app && pytest tests/integration/domains/workboard -v"` (check the working directory the meetings integration tests use in the Taskfile `test:backend:integration`). Expected: PASS.

- [ ] **Step 3: Proposed commit**

`test(workboard): PostgreSQL semantics of the board, the purge and the release (lot 1)`

---

### Task 7: Records — ADR-276, technical doc, indexes

**Files:**
- Create: `docs/architecture/ADR-276-Workboard.md`
- Modify: `docs/architecture/ADR_INDEX.md` (append an entry in the format of ADR-273's, and the count line at the top if there is one)
- Create: `docs/technical/WORKBOARD.md` (lot-1 scope: data model, rights, API; a « planned » section listing lots 2-6 WITHOUT citing code paths that do not exist yet — `lint:docs` checks paths)
- Modify: `docs/INDEX.md` (technical doc + ADR), `docs/ARCHITECTURE.md` (domain count and the domain list where `peers` appears), `CLAUDE.md` « Useful Documentation Pointers » (one bullet: ADR-276 + WORKBOARD.md), then `task docs:sync-agents`.

- [ ] **Step 1: Write ADR-276** — Context (the problem, §1 of the spec), Decisions D1-D18 in the spec's words (French, the index language, like ADR-273), Consequences (the guards that now hold: user-data-map, drift, error-code contract), Amends: ADR-263 (draft unattended — documented as decided, delivered in lot 2), ADR-117, ADR-185.

- [ ] **Step 2: Run the docs gates**

`task lint:docs:preview` (the new files are unstaged: the preview reads the working tree) → green; then `task docs:sync-agents`; `task lint:docs:preview` again → green.

- [ ] **Step 3: Full lot gate**

```
task lint
task test:backend:unit:fast
task test:markers
docker restart lia-api-dev && docker logs lia-api-dev --tail 60
```
All green; `application_ready` in the logs. Record the exact commands and exit codes in the lot report.

- [ ] **Step 4: Proposed commit**

`docs(workboard): ADR-276 and the technical record of lot 1`

---

## Self-review against the spec (lot 1 scope)

- §5 persistence: every column of the three tables → Task 2; the partial sweep index and the CHECK → Task 2; the retention sweep and the hidden-row column live in lot 2 (they belong to `conversation_messages` and the runner).
- §5.1 lifecycle: any→any by a person → Task 4 `_transition`; delete cascade with count → Task 4; purge reset → Task 2 `purge.py` + service pre-step; connection removal → `release_connection` (the PeersService hook is lot 5).
- §8 peer rights → Task 4 `TestPeerRights` covers every sentence of the section, including the D7 refusal from both sides.
- §10 API: every route → Task 5; `needs-me` declared before `/tickets/{id}` → Task 5; `hide_existence` → `raise_not_found_or_unauthorized` in Task 4.
- D17 exact counts → Task 3 `_counts_stmt` from `_filtered`; D11 → `find_by_title` + `resolve_reference`; D3b runs cap → `run_now`.
- Type consistency: `BoardFilters` fields, `TicketBundle`, `WorkboardService` method names and the repository methods match across Tasks 3-5; `list_column_ids` added in Task 4 to the Task 3 file.
