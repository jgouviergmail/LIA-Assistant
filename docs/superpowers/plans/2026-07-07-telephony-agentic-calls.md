# Agentic Telephony — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user ask LIA to place an outbound phone call to a contact, hold a goal-directed conversation on their behalf via ElevenLabs (ElevenAgents), and asynchronously bring a summary + optional action proposal back into the user's LIA conversation — configured per-user as a connector.

**Architecture:** New bounded context `domains/telephony/` (no LangGraph graft). Per-user `ELEVENLABS_TELEPHONY` connector (full BYO: user's own ElevenLabs key + number) reusing the existing `Connector` storage. `place_phone_call` is a **draft-producing tool** (like `create_event`): it emits a `PHONE_CALL` draft → `draft_critique` (confirm/edit/cancel) → `draft_executor` places the call. In-call availability comes from a **pre-fetched, minimized free/busy** window (v1 has no live capability endpoint). On call end, a per-user HMAC-verified **post-call webhook** triggers a **tool-less synthesis** LLM call that composes the proposal, delivered via `NotificationDispatcher`. The actual mutation (e.g. create event) is the user's next live turn.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / LangGraph 1.0 / Pydantic v2 / structlog / httpx / ElevenLabs SDK (present) / Next.js 16 (frontend). Source spec: `docs/superpowers/specs/2026-07-07-telephony-agentic-calls-design.md` (v5).

## Global Constraints

- **Feature flag:** everything gated by `settings.telephony_enabled` (`TELEPHONY_ENABLED`, default `false`).
- **No LIA-side metering of telephony minutes** (D-9): no pricing rows, no `UserStatistics` cost columns, no usage-limit impact. Only the synthesis LLM call is tracked by existing token infra. `PhoneCall.call_seconds` is metadata only.
- **No call recording / audio storage** (D-8): pass `call_recording_enabled=false`; persist only `summary` + typed `structured_data`; the raw transcript is transient (never written). Retention TTL via `expires_at`.
- **Secrets only in `credentials_encrypted`** (never JSONB): ElevenLabs API key AND the post-call webhook HMAC secret. `connector_metadata` holds non-secret ids only (`agent_id`, `agent_phone_number_id`, `caller_number_display`).
- **HITL via the draft pattern** (V-1): manifest `hitl_required=False`; the `PHONE_CALL` draft + `draft_critique` + `draft_executor` gate the call. Never rely on `hitl_required=True`.
- **UTC-aware datetimes only** (`datetime.now(UTC)`); no naive `now()`/`utcnow()`/`date.today()`. User display timezone from preferences, never a hardcoded `"Europe/Paris"`.
- **JSONB:** never mutate in place — reassign a new dict (`obj.meta = {**(obj.meta or {}), **updates}`).
- **i18n:** every user-visible string in all 6 languages (en, fr, de, es, it, zh); backend via `HitlMessages`/`APIMessages`/i18n modules, never inline. Frontend via `apps/web/locales/{lang}/translation.json` with strict key parity.
- **Logging:** `structlog.get_logger(__name__)`; no PII at INFO (callee names/numbers, transcript content); ids/counters at INFO, content at DEBUG/redacted. No `print()`.
- **Tools:** `@track_tool_metrics` + `@rate_limit`; return `ToolResponse`/`UnifiedToolOutput` or `ToolErrorModel`+`ToolErrorCode` on failure.
- **File size:** keep each logical file < 600 SLOC (`scripts/audit/measure_sloc.py` semantics); extract a cohesive module rather than growing one.
- **Git:** commit after each task. Do NOT push, do NOT create PRs, do NOT run git without the user's explicit request — the user handles git. (The `git commit` steps below are the intended granularity; the executor must still get the user's go-ahead per project rules.)
- **Never `--no-verify`.** The pre-commit hook (format + lint + fast unit tests + i18n parity) must pass; fix the root cause.

## Phase Map (6 sequential sub-plans, each shippable behind the flag)

| Phase | Deliverable | Depends on |
|-------|-------------|-----------|
| **P1 — Foundation** | Config + flag, `ConnectorType.ELEVENLABS_TELEPHONY`, `PhoneCall` model + migration + repository + `StructuredCallData`. | — |
| **P2 — Connector & ElevenLabs client** | Per-user connector activation (validate key, list numbers, create agent, capture webhook secret), `client.py` (create-agent, list-numbers, initiate-call), `TelephonyService`. | P1 |
| **P3 — Tool + draft + execution** | `place_phone_call` draft tool, `DraftType.PHONE_CALL` (+ display registry + i18n), `draft_executor` branch, `availability.py` pre-fetch. | P2 |
| **P4 — Return path** | `POST /telephony/webhook` (foreign-filter → per-user HMAC → reconcile), `synthesize_return` (tool-less LLM), `NotificationDispatcher` delivery, stale/retention reapers. | P3 |
| **P5 — Frontend** | Mes Connecteurs telephony card + multi-step activation wizard (Hue precedent), `useTelephony` + call history. | P2/P4 |
| **P6 — Observability, docs, ADR, hardening** | Metrics, ADR, technical doc, user guide (runbook §17), i18n audit, security tests. | all |

> **Vertical-slice note:** the de-risking end-to-end path is P2's ElevenLabs client + one real test call. Before writing P2's client against the exact request/response shapes, run the **spike** in Task P2.0 (place one real call with the SDK) to confirm the `§14` field names, then implement.

---

# PHASE 1 — Foundation

**Files created/modified:**
- Modify: `apps/api/src/core/constants.py` (telephony constants)
- Create: `apps/api/src/core/config/telephony.py` (`TelephonySettings`)
- Modify: `apps/api/src/core/config/__init__.py` (add to `Settings` MRO)
- Modify: `apps/api/.env.example`, `.env.prod.example` (new vars)
- Modify: `apps/api/src/domains/connectors/models.py` (enum value + category + display name)
- Create: `apps/api/src/domains/telephony/__init__.py`, `models.py`, `schemas.py`, `repository.py`
- Modify: `apps/api/alembic/env.py`, `src/infrastructure/database/registry.py`, `src/infrastructure/startup/registries.py` (register model)
- Create: `apps/api/alembic/versions/<rev>-create_phone_calls.py`
- Tests: `apps/api/tests/unit/domains/telephony/test_models.py`, `test_repository.py`, `test_config.py`

### Task P1.1: TelephonySettings config module + feature flag

**Files:**
- Modify: `apps/api/src/core/constants.py`
- Create: `apps/api/src/core/config/telephony.py`
- Modify: `apps/api/src/core/config/__init__.py`
- Modify: `apps/api/.env.example`, `apps/api/.env.prod.example`
- Test: `apps/api/tests/unit/domains/telephony/test_config.py`

**Interfaces:**
- Produces: `settings.telephony_enabled: bool`, `settings.telephony_ringing_timeout_seconds: int`, `settings.telephony_prefetch_window_days: int`, `settings.telephony_max_call_duration_seconds: int`, `settings.telephony_call_retention_days: int`, `settings.telephony_stale_call_timeout_minutes: int`, `settings.telephony_rate_limit_per_hour: int`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/domains/telephony/test_config.py
import pytest
from src.core.config import settings


@pytest.mark.unit
def test_telephony_settings_defaults():
    assert settings.telephony_enabled is False
    assert settings.telephony_ringing_timeout_seconds == 30
    assert settings.telephony_prefetch_window_days == 10
    assert settings.telephony_max_call_duration_seconds == 600
    assert settings.telephony_call_retention_days == 30
    assert settings.telephony_stale_call_timeout_minutes == 15
    assert settings.telephony_rate_limit_per_hour == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/telephony/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'telephony_enabled'`.

- [ ] **Step 3: Add constants**

Append to `apps/api/src/core/constants.py`:

```python
# ---------------------------------------------------------------------------
# Telephony (agentic outbound calls) defaults
# ---------------------------------------------------------------------------
TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT = 30
TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT = 10
TELEPHONY_MAX_CALL_DURATION_SECONDS_DEFAULT = 600
TELEPHONY_CALL_RETENTION_DAYS_DEFAULT = 30
TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT = 15
TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT = 10
SCHEDULER_JOB_TELEPHONY_STALE_REAPER = "telephony_stale_call_reaper"
SCHEDULER_JOB_TELEPHONY_RETENTION_REAPER = "telephony_retention_reaper"
```

- [ ] **Step 4: Create the settings module**

```python
# apps/api/src/core/config/telephony.py
"""Telephony (agentic outbound calls) settings — no per-user credentials here.

Per-user ElevenLabs key/agent/number live in the ELEVENLABS_TELEPHONY connector
(encrypted). This module carries only deployment-wide knobs.
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    TELEPHONY_CALL_RETENTION_DAYS_DEFAULT,
    TELEPHONY_MAX_CALL_DURATION_SECONDS_DEFAULT,
    TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT,
    TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT,
    TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT,
)


class TelephonySettings(BaseSettings):
    """Telephony feature settings (see docs/.../2026-07-07-telephony...md)."""

    telephony_enabled: bool = Field(
        default=False,
        description="Master switch for the agentic telephony feature.",
    )
    telephony_ringing_timeout_seconds: int = Field(
        default=TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT,
        ge=5,
        le=120,
        description="Ringing timeout passed to ElevenLabs telephony_call_config.",
    )
    telephony_prefetch_window_days: int = Field(
        default=TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Margin (days) around the objective window for availability pre-fetch.",
    )
    telephony_max_call_duration_seconds: int = Field(
        default=TELEPHONY_MAX_CALL_DURATION_SECONDS_DEFAULT,
        ge=30,
        le=3600,
        description="Hard cap on call duration (agent config).",
    )
    telephony_call_retention_days: int = Field(
        default=TELEPHONY_CALL_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Retention TTL for PhoneCall.summary/structured_data (D-8).",
    )
    telephony_stale_call_timeout_minutes: int = Field(
        default=TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description="A dialing/in_progress call with no webhook after this is marked failed.",
    )
    telephony_rate_limit_per_hour: int = Field(
        default=TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT,
        ge=1,
        le=1000,
        description="Per-user place_phone_call rate limit (calls/hour).",
    )
```

- [ ] **Step 5: Add to the Settings MRO**

In `apps/api/src/core/config/__init__.py`, import `TelephonySettings` and add it to the `Settings` class bases (follow the existing pattern used by `VoiceSettings` etc.). Example (adapt to the actual class definition):

```python
from src.core.config.telephony import TelephonySettings
# ...
class Settings(
    # ... existing bases ...
    TelephonySettings,
):
    ...
```

- [ ] **Step 6: Add env vars to examples**

Append to `apps/api/.env.example` and `apps/api/.env.prod.example`:

```dotenv
# --- Telephony (agentic outbound calls) ---
TELEPHONY_ENABLED=false
TELEPHONY_RINGING_TIMEOUT_SECONDS=30
TELEPHONY_PREFETCH_WINDOW_DAYS=10
TELEPHONY_MAX_CALL_DURATION_SECONDS=600
TELEPHONY_CALL_RETENTION_DAYS=30
TELEPHONY_STALE_CALL_TIMEOUT_MINUTES=15
TELEPHONY_RATE_LIMIT_PER_HOUR=10
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/telephony/test_config.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/core/constants.py apps/api/src/core/config/telephony.py apps/api/src/core/config/__init__.py apps/api/.env.example apps/api/.env.prod.example apps/api/tests/unit/domains/telephony/test_config.py
git commit -m "feat(telephony): add TelephonySettings config + feature flag"
```

### Task P1.2: `ELEVENLABS_TELEPHONY` connector type

**Files:**
- Modify: `apps/api/src/domains/connectors/models.py`
- Test: `apps/api/tests/unit/domains/connectors/test_telephony_connector_type.py`

**Interfaces:**
- Produces: `ConnectorType.ELEVENLABS_TELEPHONY = "elevenlabs_telephony"`; functional category `"telephony"`; display name `"Téléphonie"` → `"Telephony"` (display map is language-agnostic label).

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/domains/connectors/test_telephony_connector_type.py
import pytest
from src.domains.connectors.models import (
    ConnectorType,
    get_connector_display_name,
    get_functional_category,
)


@pytest.mark.unit
def test_telephony_connector_type_exists():
    assert ConnectorType.ELEVENLABS_TELEPHONY.value == "elevenlabs_telephony"


@pytest.mark.unit
def test_telephony_is_its_own_category_and_has_display_name():
    assert get_functional_category(ConnectorType.ELEVENLABS_TELEPHONY) == "telephony"
    assert get_connector_display_name(ConnectorType.ELEVENLABS_TELEPHONY) == "Telephony"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/connectors/test_telephony_connector_type.py -v`
Expected: FAIL — `AttributeError: ELEVENLABS_TELEPHONY`.

- [ ] **Step 3: Add the enum value + category + display name**

In `apps/api/src/domains/connectors/models.py`:
- Add to `ConnectorType`: `ELEVENLABS_TELEPHONY = "elevenlabs_telephony"` (under a new `# Telephony (API Key)` comment).
- Add to `CONNECTOR_FUNCTIONAL_CATEGORIES`: `"telephony": frozenset({ConnectorType.ELEVENLABS_TELEPHONY})`.
- Add to `CATEGORY_DISPLAY_NAMES`: `"telephony": "Telephony"`.
- Add to `CONNECTOR_DISPLAY_NAMES`: `ConnectorType.ELEVENLABS_TELEPHONY: "Telephony"`.

> No DB migration needed for the enum: the `connector_type` column is `Enum(..., native_enum=False)` (stored as VARCHAR, no CHECK constraint) — verified.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/connectors/test_telephony_connector_type.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/connectors/models.py apps/api/tests/unit/domains/connectors/test_telephony_connector_type.py
git commit -m "feat(telephony): add ELEVENLABS_TELEPHONY connector type"
```

### Task P1.3: `PhoneCall` model + `StructuredCallData` + registration + migration

**Files:**
- Create: `apps/api/src/domains/telephony/__init__.py`, `apps/api/src/domains/telephony/models.py`, `apps/api/src/domains/telephony/schemas.py`
- Modify: `apps/api/alembic/env.py`, `apps/api/src/infrastructure/database/registry.py`, `apps/api/src/infrastructure/startup/registries.py`
- Create: `apps/api/alembic/versions/<rev>-create_phone_calls.py`
- Test: `apps/api/tests/unit/domains/telephony/test_models.py`

**Interfaces:**
- Produces: `PhoneCall` ORM (table `phone_calls`) with the columns of spec §5; `PhoneCallStatus` and `PhoneCallOutcome` str-enums; `StructuredCallData(BaseModel)` with fields `agreed: bool | None`, `proposed_datetime: str | None`, `location: str | None`, `notes: str | None` (all optional).

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/domains/telephony/test_models.py
import pytest
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.schemas import StructuredCallData


@pytest.mark.unit
def test_phone_call_status_values():
    assert PhoneCallStatus.DIALING.value == "dialing"
    assert {s.value for s in PhoneCallStatus} == {
        "dialing", "in_progress", "completed", "no_answer",
        "voicemail", "failed", "cancelled",
    }


@pytest.mark.unit
def test_structured_call_data_round_trips_through_dict():
    data = StructuredCallData(agreed=True, proposed_datetime="2026-07-11T12:00:00Z",
                              location="L'Ardoise")
    as_dict = data.model_dump()
    assert StructuredCallData.model_validate(as_dict) == data


@pytest.mark.unit
def test_phone_call_tablename():
    assert PhoneCall.__tablename__ == "phone_calls"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/telephony/test_models.py -v`
Expected: FAIL — module `src.domains.telephony.models` not found.

- [ ] **Step 3: Create the package + schemas**

```python
# apps/api/src/domains/telephony/__init__.py
"""Telephony bounded context — agentic outbound calls (see docs spec v5)."""
```

```python
# apps/api/src/domains/telephony/schemas.py
"""Telephony Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StructuredCallData(BaseModel):
    """Minimal, typed structured outcome extracted from a call (D-8).

    Only these fields are persisted (never the raw transcript). All optional —
    a call may yield none of them.
    """

    model_config = ConfigDict(extra="ignore")

    agreed: bool | None = Field(default=None, description="Did the callee agree to the ask?")
    proposed_datetime: str | None = Field(
        default=None, description="ISO-8601 datetime proposed during the call, if any."
    )
    location: str | None = Field(default=None, description="Location proposed/agreed, if any.")
    notes: str | None = Field(default=None, description="Short free-text note, minimized.")
```

- [ ] **Step 4: Create the model**

```python
# apps/api/src/domains/telephony/models.py
"""PhoneCall ORM model — one row per placed call (created at draft execution)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class PhoneCallStatus(str, enum.Enum):
    DIALING = "dialing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhoneCallOutcome(str, enum.Enum):
    OBJECTIVE_MET = "objective_met"
    PARTIAL = "partial"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"


class PhoneCall(BaseModel):
    """A single outbound call. PII (callee_phone) is encrypted at rest."""

    __tablename__ = "phone_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    callee_display: Mapped[str] = mapped_column(Text, nullable=False)
    callee_phone: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted by service
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    objective_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    objective_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[PhoneCallStatus] = mapped_column(
        Enum(PhoneCallStatus, native_enum=False, length=20),
        nullable=False,
        default=PhoneCallStatus.DIALING,
        index=True,
    )
    elevenlabs_conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[PhoneCallOutcome | None] = mapped_column(
        Enum(PhoneCallOutcome, native_enum=False, length=20), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One active call per user (atomic guard — F12).
        Index(
            "uq_phone_calls_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where="status IN ('dialing', 'in_progress')",
        ),
        # Reconciliation fallback; NULL until initiated. Unique among non-null.
        Index(
            "uq_phone_calls_el_conversation",
            "elevenlabs_conversation_id",
            unique=True,
            postgresql_where="elevenlabs_conversation_id IS NOT NULL",
        ),
    )
```

> Verify `BaseModel` provides `id` (UUID PK) + `created_at`/`updated_at`. If the codebase uses `UUIDMixin`/`TimestampMixin` explicitly instead, follow the pattern of a nearby recent model (e.g. `scheduled_actions/models.py`).

- [ ] **Step 5: Register the model in the 3 places**

- `apps/api/alembic/env.py`: add `from src.domains.telephony.models import PhoneCall  # noqa: F401`.
- `apps/api/src/infrastructure/database/registry.py` (`import_all_models`): add the same import.
- `apps/api/src/infrastructure/startup/registries.py` (`import_domain_models`): add the same import.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/telephony/test_models.py -v`
Expected: PASS.

- [ ] **Step 7: Create the Alembic migration**

Run: `cd apps/api && .venv/Scripts/alembic revision --autogenerate -m "create phone_calls"`
Then open the generated file and verify: `create_table("phone_calls", ...)` with all columns, plus the two partial unique indexes (autogenerate may not emit `postgresql_where` — add them manually with `op.create_index(..., postgresql_where=sa.text("..."))` if missing). Confirm `downgrade()` drops the table + indexes.

- [ ] **Step 8: Verify single head + apply**

Run: `cd apps/api && .venv/Scripts/alembic heads` → expect a single head.
Run: `cd apps/api && .venv/Scripts/alembic upgrade head` (against a test DB) → succeeds.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/domains/telephony/ apps/api/alembic/ apps/api/src/infrastructure/database/registry.py apps/api/src/infrastructure/startup/registries.py apps/api/tests/unit/domains/telephony/test_models.py
git commit -m "feat(telephony): add PhoneCall model + migration + registration"
```

### Task P1.4: `TelephonyRepository`

**Files:**
- Create: `apps/api/src/domains/telephony/repository.py`
- Test: `apps/api/tests/integration/domains/telephony/test_repository.py` (integration — needs PostgreSQL for the partial unique index)

**Interfaces:**
- Produces: `TelephonyRepository(db)` with `async create(data: dict) -> PhoneCall`, `async get_by_call_id(call_id: UUID) -> PhoneCall | None`, `async get_active_for_user(user_id: UUID) -> PhoneCall | None`, `async mark_completed(call, *, status, summary, structured_data, outcome, call_seconds) -> PhoneCall`, `async recover_stale(timeout_minutes: int) -> int`, `async purge_expired() -> int`.

- [ ] **Step 1: Write the failing test** (integration; uses the `db` fixture)

```python
# apps/api/tests/integration/domains/telephony/test_repository.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository


@pytest.mark.integration
async def test_one_active_call_per_user_is_enforced(db, seeded_user):
    repo = TelephonyRepository(db)
    await repo.create({"user_id": seeded_user.id, "callee_display": "Marie",
                       "callee_phone": "enc", "objective": "resto",
                       "status": PhoneCallStatus.DIALING})
    await db.commit()
    with pytest.raises(IntegrityError):
        await repo.create({"user_id": seeded_user.id, "callee_display": "Marie",
                           "callee_phone": "enc", "objective": "resto2",
                           "status": PhoneCallStatus.DIALING})
        await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/integration/domains/telephony/test_repository.py -v`
Expected: FAIL — `TelephonyRepository` not found.

- [ ] **Step 3: Implement the repository** (inherit `BaseRepository[PhoneCall]`; imitate `scheduled_actions/repository.py` for `recover_stale` FOR UPDATE SKIP LOCKED + atomic status transition, and for `purge_expired`).

```python
# apps/api/src/domains/telephony/repository.py
"""Repository for PhoneCall rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update

from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.infrastructure.database.base_repository import BaseRepository


class TelephonyRepository(BaseRepository[PhoneCall]):
    def __init__(self, db):
        super().__init__(db, PhoneCall)

    async def get_by_call_id(self, call_id: UUID) -> PhoneCall | None:
        return await self.db.get(PhoneCall, call_id)

    async def get_active_for_user(self, user_id: UUID) -> PhoneCall | None:
        stmt = select(PhoneCall).where(
            PhoneCall.user_id == user_id,
            PhoneCall.status.in_([PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS]),
        )
        return (await self.db.scalars(stmt)).first()

    async def recover_stale(self, timeout_minutes: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        stmt = (
            update(PhoneCall)
            .where(
                PhoneCall.status.in_([PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS]),
                PhoneCall.created_at < cutoff,
            )
            .values(status=PhoneCallStatus.FAILED, error="stale_no_webhook")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def purge_expired(self) -> int:
        now = datetime.now(UTC)
        stmt = (
            update(PhoneCall)
            .where(PhoneCall.expires_at.is_not(None), PhoneCall.expires_at < now,
                   PhoneCall.summary.is_not(None))
            .values(summary=None, structured_data={})
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0
```

> Confirm `BaseRepository`'s constructor signature and `create()` against `scheduled_actions/repository.py`; adapt imports (`src.infrastructure.database.base_repository` may differ — grep for `class BaseRepository`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/integration/domains/telephony/test_repository.py -v`
Expected: PASS (requires PostgreSQL + Redis running: `task dev:detach` or the integration fixtures).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/telephony/repository.py apps/api/tests/integration/domains/telephony/test_repository.py
git commit -m "feat(telephony): add TelephonyRepository with active-call + reaper queries"
```

**P1 exit check:** `task test:backend:unit:fast` green; `alembic upgrade head` + `downgrade -1` clean; app boots with `TELEPHONY_ENABLED=false` (no behavior change).

---

# PHASE 2 — Connector & ElevenLabs client

**Files:**
- Create: `apps/api/src/domains/telephony/client.py` (ElevenLabs Agents client)
- Create: `apps/api/src/domains/telephony/connector.py` (activation flow)
- Create: `apps/api/src/domains/telephony/service.py` (`TelephonyService`)
- Modify: `apps/api/src/domains/telephony/schemas.py` (activation + client schemas)
- Modify: `apps/api/src/api/v1/routes.py` (mount `/telephony/connector/*` behind the flag)
- Create: `apps/api/src/domains/telephony/router.py` (connector activation endpoints)
- Tests: `tests/unit/domains/telephony/test_client.py`, `test_connector.py`, `test_service.py`

### Task P2.0: Vertical-slice spike (manual, de-risking — NOT a code commit)

- [ ] Provision one ElevenLabs paid account + one FR Twilio number (runbook spec §17 A–E). Create an API key. Import the number.
- [ ] Using the ElevenLabs Python SDK in a throwaway script (`scratchpad/`), call: create-agent, list phone numbers, and `outbound-call` to your own mobile with `dynamic_variables={"call_id": "test"}` and `call_recording_enabled=False`. Configure the workspace `post_call_transcription` webhook to a temporary tunnel and capture ONE real payload.
- [ ] Record the confirmed field names in the spec's §14 (endpoint paths, response keys, the exact webhook JSON path for the echoed `call_id`, `analysis.transcript_summary`, `data_collection_results`). These confirmations feed P2.1 and P4.
- [ ] Delete the throwaway script; do not commit secrets.

> This spike converts the §14 "deferred" items into confirmed constants before writing the client. If any shape differs from the spec, update the spec + this plan before proceeding.

### Task P2.1: ElevenLabs Agents client

**Files:**
- Create: `apps/api/src/domains/telephony/client.py`
- Modify: `apps/api/src/domains/telephony/schemas.py`
- Test: `apps/api/tests/unit/domains/telephony/test_client.py`

**Interfaces:**
- Produces: `ElevenLabsAgentsClient(api_key: str)` with `async validate_key() -> bool`, `async list_phone_numbers() -> list[PhoneNumberInfo]`, `async create_agent(*, name, system_prompt, first_message, language, max_duration_seconds) -> str` (returns `agent_id`), `async update_agent(agent_id, ...) -> None`, `async initiate_outbound_call(*, agent_id, agent_phone_number_id, to_number, dynamic_variables, ringing_timeout_secs) -> OutboundCallResult`, `async delete_agent(agent_id) -> None`.
- `PhoneNumberInfo(BaseModel)`: `phone_number_id: str`, `phone_number: str`, `provider: str`, `assigned_agent: str | None`.
- `OutboundCallResult(BaseModel)`: `success: bool`, `conversation_id: str | None`, `call_sid: str | None`, `message: str | None`.

- [ ] **Step 1: Write the failing test** (mock httpx / the SDK transport)

```python
# apps/api/tests/unit/domains/telephony/test_client.py
import pytest
from src.domains.telephony.client import ElevenLabsAgentsClient
from src.domains.telephony.schemas import OutboundCallResult


@pytest.mark.unit
async def test_initiate_outbound_call_sets_recording_disabled(monkeypatch):
    captured = {}

    async def fake_post(self, url, json, headers):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = json
        class _Resp:
            status_code = 200
            def json(self):
                return {"success": True, "conversation_id": "conv_1", "callSid": "CA1"}
            def raise_for_status(self): ...
        return _Resp()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    client = ElevenLabsAgentsClient(api_key="sk-test")
    res = await client.initiate_outbound_call(
        agent_id="ag_1", agent_phone_number_id="pn_1", to_number="+33600000000",
        dynamic_variables={"call_id": "c1"}, ringing_timeout_secs=30,
    )
    assert isinstance(res, OutboundCallResult)
    assert res.conversation_id == "conv_1"
    assert captured["json"]["call_recording_enabled"] is False
    assert captured["json"]["conversation_initiation_client_data"]["dynamic_variables"]["call_id"] == "c1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/telephony/test_client.py -v`
Expected: FAIL — `ElevenLabsAgentsClient` not found.

- [ ] **Step 3: Implement the client** (against the confirmed shapes from P2.0). Add the schemas to `schemas.py`, then:

```python
# apps/api/src/domains/telephony/client.py
"""Async client for the ElevenLabs ElevenAgents API (per-user API key)."""

from __future__ import annotations

import httpx
import structlog

from src.domains.telephony.schemas import OutboundCallResult, PhoneNumberInfo

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.elevenlabs.io/v1/convai"


class ElevenLabsAgentsClient:
    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0) -> None:
        self._headers = {"xi-api-key": api_key}
        self._timeout = timeout_seconds

    async def validate_key(self) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.get(f"{_BASE_URL}/agents", headers=self._headers)
            return resp.status_code == 200

    async def list_phone_numbers(self) -> list[PhoneNumberInfo]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.get(f"{_BASE_URL}/phone-numbers", headers=self._headers)
            resp.raise_for_status()
            return [PhoneNumberInfo.model_validate(row) for row in resp.json()]

    async def create_agent(self, *, name: str, system_prompt: str, first_message: str,
                           language: str, max_duration_seconds: int) -> str:
        body = {
            "name": name,
            "conversation_config": {
                "agent": {
                    "prompt": {"prompt": system_prompt},
                    "first_message": first_message,
                    "language": language,
                },
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.post(f"{_BASE_URL}/agents/create", json=body, headers=self._headers)
            resp.raise_for_status()
            return resp.json()["agent_id"]

    async def initiate_outbound_call(self, *, agent_id: str, agent_phone_number_id: str,
                                     to_number: str, dynamic_variables: dict,
                                     ringing_timeout_secs: int) -> OutboundCallResult:
        body = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "to_number": to_number,
            "call_recording_enabled": False,  # D-8
            "telephony_call_config": {"ringing_timeout_secs": ringing_timeout_secs},
            "conversation_initiation_client_data": {"dynamic_variables": dynamic_variables},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.post(f"{_BASE_URL}/twilio/outbound-call", json=body,
                                headers=self._headers)
            resp.raise_for_status()
            payload = resp.json()
        return OutboundCallResult(
            success=payload.get("success", False),
            conversation_id=payload.get("conversation_id"),
            call_sid=payload.get("callSid"),
            message=payload.get("message"),
        )

    async def delete_agent(self, agent_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            await c.delete(f"{_BASE_URL}/agents/{agent_id}", headers=self._headers)
```

> Confirm the auth header name (`xi-api-key`) and the exact create-agent body against P2.0. Adjust the `prompt` nesting if the SDK expects `conversation_config.agent.prompt.prompt` vs a different key.

- [ ] **Step 4: Run test to verify it passes** → PASS.
- [ ] **Step 5: Commit** `feat(telephony): add ElevenLabs Agents client`.

### Task P2.2: Connector activation service

**Files:** Create `connector.py`; modify `schemas.py`; Test `test_connector.py`.

**Interfaces:**
- Produces: `TelephonyConnectorService(db)` with `async validate_key(api_key) -> KeyValidationResult`, `async list_numbers(api_key) -> list[PhoneNumberInfo]`, `async activate(*, user_id, api_key, agent_phone_number_id, webhook_secret, user_language, caller_display) -> Connector`, `async deactivate(user_id) -> None`. `activate` builds the guardrailed system prompt from a versioned template, calls `client.create_agent`, then stores an encrypted `APIKeyCredentials`-like payload (api_key + webhook_secret) via `ConnectorService`, with `connector_metadata={agent_id, agent_phone_number_id, caller_number_display}`.

- [ ] Steps mirror P1's TDD rhythm: failing test (activate stores encrypted creds + metadata, agent created via a mocked client), implement, pass, commit. **Key detail:** the webhook secret goes into the encrypted credentials JSON (extend the stored payload with a `webhook_secret` field — do NOT put it in `connector_metadata`). Reuse `ConnectorService.get_api_key_credentials` for retrieval; if the secret must ride alongside, store a small JSON `{api_key, webhook_secret}` as the encrypted blob and add a typed accessor.

> Confirm how `ConnectorService` encrypts/stores the api-key blob (read `activate_api_key_connector` + `get_api_key_credentials` around `service.py:2390`/`:2499`). Extend minimally to carry the second secret; add a unit test asserting the webhook secret never appears in `connector_metadata`.

### Task P2.3: Connector router (activation wizard endpoints)

**Files:** Create `router.py`; modify `routes.py`; Test `test_router.py`.

**Interfaces:**
- Produces: `POST /telephony/connector/validate-key` → `{is_valid, numbers: [...]}`; `POST /telephony/connector/activate` (body: `api_key`, `agent_phone_number_id`, `webhook_secret`, `caller_display`) → `ConnectorAPIKeyInfo`-like; `DELETE /telephony/connector` → 204. All `Depends(get_current_active_session)` + `Depends(get_db)`, guarded by `settings.telephony_enabled`.

- [ ] TDD: failing route test (activation happy path with a mocked service), implement, pass, commit. Mount the router in `routes.py` behind `if getattr(settings, "telephony_enabled", False)`.

**P2 exit check:** a user can validate a key, list numbers, activate the connector (agent auto-created via mocked client in tests; real via the spike), and the encrypted blob carries key + webhook secret; `task lint:backend` + fast unit tests green.

---

# PHASE 3 — Tool + draft + execution

**Files:**
- Modify: `apps/api/src/domains/agents/drafts/models.py` (`DraftType.PHONE_CALL`)
- Modify: `apps/api/src/domains/agents/drafts/display.py` (`DRAFT_DISPLAY_REGISTRY` entry)
- Modify: `apps/api/src/core/i18n_drafts.py` (noun/verb/label keys ×6) — confirm exact module
- Modify: `apps/api/src/domains/agents/services/draft_executor.py` (PHONE_CALL branch)
- Create: `apps/api/src/domains/telephony/availability.py`
- Create: `apps/api/src/domains/agents/tools/telephony_tools.py` (`place_phone_call`)
- Modify: tool registry + catalogue + a manifest for `place_phone_call`
- Modify: `apps/api/src/domains/telephony/service.py` (`initiate_call`)
- Tests: `test_draft_type.py`, `test_availability.py`, `test_place_phone_call_tool.py`, `test_draft_executor_phone_call.py`

### Task P3.1: `DraftType.PHONE_CALL` + display registry + i18n

**Interfaces:** Produces `DraftType.PHONE_CALL = "phone_call"` with a `DRAFT_DISPLAY_REGISTRY[DraftType.PHONE_CALL]` entry (emoji 📞, detail fields: `callee_name`→"contact", `callee_phone`→"phone", `objective`→"body"; `noun_key="call"`, `verb_past_key="placed"`), and the matching `noun`/`verb_past`/preview-label i18n entries in all 6 languages.

- [ ] **Step 1: Failing test** — `assert_registry_completeness()` passes with the new type; `get_draft_display_config("phone_call")` returns a config with emoji "📞".

```python
# apps/api/tests/unit/domains/agents/drafts/test_phone_call_draft_type.py
import pytest
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.display import assert_registry_completeness, get_draft_display_config


@pytest.mark.unit
def test_phone_call_draft_type_registered():
    assert DraftType.PHONE_CALL.value == "phone_call"
    cfg = get_draft_display_config("phone_call")
    assert cfg is not None and cfg.emoji == "\U0001f4de"
    assert_registry_completeness()  # must not raise
```

- [ ] **Step 2: Run → fails** (`DraftType.PHONE_CALL` missing / assert raises).
- [ ] **Step 3: Add** `PHONE_CALL = "phone_call"` to `DraftType`; add the `DRAFT_DISPLAY_REGISTRY` entry (📞, detail fields as above, `noun_key="call"`, `verb_past_key="placed"`); add `"call"`/`"placed"` to `DRAFT_RESULT_NOUNS`/`DRAFT_RESULT_VERBS_PAST` and any `DRAFT_PREVIEW_LABELS` used, for all 6 languages (in `src/core/i18n_drafts.py`). Also add a phone_call **cancel** message to `get_draft_cancel_message` (×6). The **success** message is custom/async and added in Task P3.4 (not the generic `verb_past` template).
- [ ] **Step 4: Run → pass.** Also run `test_display_registry.py` (i18n key coverage) → pass.
- [ ] **Step 5: Commit** `feat(telephony): add PHONE_CALL draft type + display + i18n`.

### Task P3.2: Availability pre-fetch (list_events → free/busy projection)

**Interfaces:** Produces `async build_availability_summary(user_id, window_start, window_end, connector_service, user_timezone) -> str` — returns a compact free/busy text (busy intervals only, localized), **never** titles/attendees/locations.

- [ ] TDD: failing test feeds a fake calendar client returning events with titles/locations; assert the output contains the busy time ranges and **contains none** of the titles/locations (leak assertion). Implement using the calendar connector's `list_events` (verified: no freebusy) + a projection that emits only start/end busy blocks. Pass. Commit.

### Task P3.3: `place_phone_call` draft tool

**Interfaces:** Produces the `@tool async def place_phone_call_tool(contact, objective, date_window=None, context=None, runtime=...)` returning a `StandardToolOutput(requires_confirmation=True, draft_type="phone_call", draft_content={callee_name, callee_phone, objective, date_window})`. Verifies the caller's `ELEVENLABS_TELEPHONY` connector is active (else a `UnifiedToolOutput.failure` guiding to activate it); resolves `contact → phone` via the contacts tools (`search_contacts` → `phoneNumbers`; ambiguity → clarification). Manifest with `hitl_required=False`, `data_classification="SENSITIVE"`, `@track_tool_metrics` + `@rate_limit`.

- [ ] TDD: failing test — calling the tool with an active connector + a resolvable contact returns `requires_confirmation=True` and a draft_content carrying the resolved number + objective; without a connector returns the activation-guidance failure. Implement (model on `create_event_tool` — read `calendar_tools.py:970-1000`). Register in the tool registry + catalogue + manifest. Pass. Commit.

### Task P3.4: `execute_phone_call_draft` (registered executor) + `TelephonyService.initiate_call`

**Verified mechanism (corrected — the plan's earlier "add a branch" was wrong):** the
draft executor is a **per-type function registry** — `_ensure_executors_registered()`
in `services/draft_executor.py` imports `execute_*_draft` from each tool module and
calls `register_executor(DraftType.X.value, fn)`. Executors have the fixed signature
`async (draft_content: dict, user_id: UUID, deps: ToolDependencies) -> dict`. There is
**no branch to add** — write `execute_phone_call_draft` and register it. `PHONE_CALL`
is intentionally **absent** from `_DRAFT_TYPE_TO_TCM_DOMAIN` (it is not a
list/current-item CRUD domain; the `_sync_tcm_after_draft_execution` guard
`if not domain: return` handles it — no TCM wiring).

**Interfaces:** Produces `async execute_phone_call_draft(draft_content, user_id, deps) -> dict`
in `telephony_tools.py`, registered in `_ensure_executors_registered()`. It calls
`TelephonyService(deps.db).initiate_call(user_id, callee_display, callee_phone,
objective, date_window)` which pre-fetches availability, builds `dynamic_variables`
(incl. a fresh `call_id`), creates the `PhoneCall` row (`dialing`, encrypted phone,
`expires_at`), calls `client.initiate_outbound_call`, persists
`elevenlabs_conversation_id`, and returns `{"message": <async-safe text>, "call_id": ...}`.

**Async-message correction:** the generic draft success message is past-tense
completion ("event created" / "call placed") — **wrong** for an async action. Add a
**custom** phone_call success message ("J'appelle {name} maintenant, je te fais un
retour dès que j'ai sa réponse.") to `src/core/i18n_drafts.py::get_draft_success_message`
(×6 languages) instead of relying on the `verb_past` template.

- [ ] **Step 1:** Register the executor — add the import + `register_executor(DraftType.PHONE_CALL.value, execute_phone_call_draft)` inside `_ensure_executors_registered()`.
- [ ] **Step 2 (failing test):** a confirmed phone_call draft routed through `execute_draft_if_confirmed(draft_action_result, config, run_id)` (with mocked `deps` + mocked `ElevenLabsAgentsClient`) creates a `PhoneCall` row (`dialing`, encrypted phone, `call_id` present in the dynamic_variables passed to the client), and the returned message is the async-safe text (NOT past tense). A second concurrent call for the same user surfaces the friendly unique-active guard (no crash).
- [ ] **Step 3:** Run → fails. **Step 4:** implement `execute_phone_call_draft` + `TelephonyService.initiate_call` + the custom i18n success message. **Step 5:** run → pass. **Step 6:** commit `feat(telephony): execute phone_call draft → place call`.

**P3 exit check:** in a unit/integration harness, "call Marie …" → tool → draft_critique confirm → executor places the call (mocked client) → `PhoneCall` row exists; cancel ⇒ no row. `test_hitl_required_consistency.py` still green (manifest `hitl_required=False`).

---

# PHASE 4 — Return path

**Files:**
- Create: `apps/api/src/domains/telephony/webhook_handler.py`
- Create: `apps/api/src/domains/telephony/return_synthesis.py`
- Create: `apps/api/src/domains/agents/prompts/v1/telephony_synthesis.txt` (+ `PromptName` Literal + `telephony_synthesis` LLM type in `core/config/agents.py`)
- Modify: `apps/api/src/domains/telephony/router.py` (`POST /telephony/webhook`, `GET /telephony/calls`)
- Modify: `apps/api/src/infrastructure/proactive/notification.py` (`phone_call` localized title — F10) or pass an explicit `title`
- Modify: `apps/api/src/infrastructure/startup/schedulers.py` (register the two reapers)
- Modify: `apps/api/src/infrastructure/observability/*` (metrics: calls by status, duration histogram, `telephony_webhook_ignored_total`)
- Tests: `test_webhook_handler.py`, `test_return_synthesis.py`, `test_reapers.py`

### Task P4.1: Webhook handler (foreign-filter → per-user HMAC → reconcile)

**Interfaces:** Produces `POST /telephony/webhook` (unauthenticated) that: reads the untrusted body → extracts `call_id` → if missing/unknown/`agent_id` mismatch: 200 + `telephony_webhook_ignored_total.inc()` (log nothing) → resolve `call_id → PhoneCall → connector → webhook_secret` → `construct_event(body, sig_header, secret)` (strict timestamp) → 200 immediately + `safe_fire_and_forget(process_completed_call(payload))`. Endpoint rate-limited.

- [ ] TDD: failing tests — (a) unknown `call_id` → 200, ignored counter, no processing; (b) valid `call_id` but wrong secret → 4xx/ignored; (c) valid signature → 200 + background task scheduled. Implement (mirror `channels/router.py::telegram_webhook`). Pass. Commit.

### Task P4.2: `synthesize_return` (tool-less LLM) + delivery

**Interfaces:** Produces `async synthesize_return(*, transcript, transcript_summary, structured_data, objective, callee_display, user_language) -> ReturnProposal(summary: str, proposal_text: str)` — a single LLM call via the `telephony_synthesis` LLM type + versioned prompt, **no tools**. And `process_completed_call(payload)`: reconcile, extract `call_seconds`/`structured_data` (typed via `StructuredCallData`), `mark_completed`, run synthesis (transcript discarded after — D-8), deliver via `NotificationDispatcher.dispatch(user, content=proposal_text, task_type="phone_call", target_id=str(call_id), db=db, title=<localized>)`.

- [ ] TDD: failing test — given a fake transcript, `synthesize_return` returns a non-empty proposal, and `process_completed_call` writes only `summary` (asserts raw transcript is NOT persisted anywhere on the row) and calls the dispatcher once. Implement; register the LLM type + `PromptName` + prompt file. Pass. Commit.

### Task P4.3: Reapers + `GET /telephony/calls`

- [ ] TDD: register `telephony_stale_call_reaper` (interval) + `telephony_retention_reaper` (daily) in `startup/schedulers.py::init_scheduler` (flag-guarded, `replace_existing=True`, job ids from constants); test each calls the repo method. `GET /telephony/calls` returns the user's recent calls (status/summary; no raw phone at INFO). Pass. Commit.

**P4 exit check:** end-to-end (integration, mocked ElevenLabs): initiate → simulate a signed webhook → summary message archived in the user's conversation + notification; unknown-agent webhook ignored; stale call reaped.

---

# PHASE 5 — Frontend (Mes Connecteurs)

**Files:** `apps/web/src/components/settings/connectors/TelephonyConnectorForm.tsx` (multi-step wizard, modeled on `HueBridgePairingForm.tsx` + `useHueConnect.ts`), `ConnectorIcon` + `constants/connectors.ts` entry, `useTelephony` hook, a call-history surface, `locales/{lang}/translation.json` keys (6 languages).

- [ ] Wizard steps: paste API key → validate (`/telephony/connector/validate-key`) → pick number → show LIA webhook URL + guided instructions to create the workspace `post_call_transcription` webhook and paste the secret → activate (`/telephony/connector/activate`). Billing notice ("Calls are billed on your own ElevenLabs/telephony accounts"). Follow the container pnpm lockfile caveat (CLAUDE.md dev-container pitfalls) for any new dep. Vitest test for the hook. Commit per coherent unit.

**P5 exit check:** `task test:frontend` green; i18n parity check passes; wizard renders and drives the P2/P4 endpoints against a dev backend.

---

# PHASE 6 — Observability, docs, ADR, hardening

- [ ] Metrics registered + dashboards note; structured logging audited (no PII at INFO — grep the new modules).
- [ ] ADR `docs/architecture/ADR-127-agentic-telephony.md` ("per-user connector + read-only capability model + no-cost-metering + v2 live gateway"); cross-ref in `ADR_INDEX.md` + `docs/INDEX.md`.
- [ ] Technical doc `docs/technical/TELEPHONY.md` (architecture, draft flow, security invariants, the §17 setup runbook translated for users ×6).
- [ ] Security test sweep: minimization (availability leak), per-user HMAC + replay, foreign-event filter, no-recording, secrets-only-in-encrypted, no-cost-metering assertion, concurrency guard.
- [ ] `task pre-commit` + `task ci` green; app boots with `TELEPHONY_ENABLED=true` (verify in the Docker dev container per project rule — never declare complete without runtime startup verification).

---

## Self-Review Notes (author)

- **Spec coverage:** every spec section maps to a task — D-2 (P4.2 tool-less synthesis), D-3 (P2 number-agnostic client), D-4/V-1 (P3 draft HITL), D-5 (pre-fetch P3.2; live gateway explicitly out of scope), D-6 (P2 disclosure in agent prompt + P3 draft), D-7 (P2 connector), D-8 (`call_recording_enabled=false` P2.1 + retention reaper P4.3), D-9 (no cost tasks — asserted in P6), §6.4 webhook (P4.1), §17 runbook (P2.0 + P6 docs).
- **Vendor unknowns (§14)** are all funneled through the P2.0 spike, which must run before P2.1/P4.1 code is finalized.
- **Types consistent** across tasks: `OutboundCallResult`, `PhoneNumberInfo`, `StructuredCallData`, `ReturnProposal`, `PhoneCallStatus` used with the same signatures where referenced.
- **Known plan-maturity gap (honest):** P1 + the novel LIA-side tasks (draft type, model, client, executor) are at full/verified detail; **P2.2→P6 are at interface + TDD-rhythm level, not complete-code** — they must be expanded to bite-sized complete code before execution of those phases (the writing-plans bar). Only the *vendor-facing* shapes legitimately wait on the P2.0 spike; the LIA-side code does not.
- **Verified during this review (mechanisms confirmed against the code):**
  - Draft execution = a **per-type function registry** (`register_executor` in
    `_ensure_executors_registered`, `services/draft_executor.py`), executor signature
    `async (draft_content, user_id, deps) -> dict` — **not a branch** (P3.4 corrected).
  - Draft creation = module-level helpers in `src.domains.agents.drafts`
    (`create_email_draft`/`create_event_draft`, exported in `__init__.py`), which call
    `DraftService.create_draft(draft_type, content, source_tool, user_language)` →
    `UnifiedToolOutput` with `metadata.requires_confirmation=True`. → add
    `create_phone_call_draft` there (mirror `create_event_draft`).
  - Draft-producing tool = `execute_api_call` prepares a dict, `format_registry_response`
    returns the `create_*_draft(...)` output (see `CreateEventDraftTool`, calendar_tools).
    place_phone_call is cross-connector, so build it as a `@tool`/`@track_tool_metrics`
    function (perplexity pattern) that checks the telephony connector + resolves the
    contact + returns `create_phone_call_draft(...)`; register like other tools.
  - `BaseRepository` = `src.core.repository.BaseRepository[ModelType]`,
    `__init__(self, db, model)` → `super().__init__(db, PhoneCall)` (NOT
    `infrastructure/...`); `ToolDependencies.db` + `await deps.get_connector_service()`
    (`dependencies.py`).
  - Credential storage: `APIKeyCredentials(api_key, api_secret, key_name)` →
    `encrypt_data(model_dump_json())` (`src.core.security.utils`) → `credentials_encrypted`;
    the webhook HMAC secret rides in **`api_secret`** (already optional) — no shared-schema
    change; `connector_metadata` holds `agent_id`/`agent_phone_number_id` only.
  - `i18n_drafts` = `src/core/i18n_drafts.py`; the post-confirm message = 
    `get_draft_success_message(draft_type, language, name, summary, title)` → add a custom
    async-safe phone_call entry using `name=callee`. phone_call is correctly **outside**
    `_DRAFT_TYPE_TO_TCM_DOMAIN` (guard `if not domain: return`).
  - LLM types are declared in `core/config/agents.py` as `<type>_llm_provider/model/...`
    fields (see `hitl_classifier_llm_*`); add `telephony_synthesis_llm_*` + use
    `get_llm(llm_type="telephony_synthesis")`.
- **Open confirmations that genuinely need execution/spike (not paper-closable):**
  `BaseModel` vs explicit mixins for the model header; the exact `connector_tool` vs
  `@tool` registration wiring; exact ElevenLabs auth header + create-agent body +
  webhook payload paths (P2.0 spike).
