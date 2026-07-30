# Peer Connections — Lot 1 (Backend Socle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (INLINE execution —
> this project forbids subagent delegation, standing user rule). Steps use checkbox (`- [ ]`)
> syntax for tracking. **Git rule: NEVER commit/push — every "Checkpoint" step means
> "propose the commit to the user and stop"**.

**Goal:** Ship the complete backend foundation of the peer-connections feature: config,
models + migration + GDPR wiring, repository, service with every lifecycle guard, REST
router, and backend i18n — flag-off by default, zero user-visible change.

**Architecture:** New bounded context `apps/api/src/domains/peers/` imitating `open_loops`
(most recent flag-guarded domain). Master spec:
`docs/superpowers/specs/2026-07-29-peer-connections-design.md` (§2 arbitrations, §4-5, §12-13).
Standing directive: **lean maximally on proven existing mechanisms — every task names the
canonical file it imitates.**

**Tech Stack:** FastAPI 0.135+, SQLAlchemy 2.x (`Mapped`/`mapped_column`), Alembic,
Pydantic v2, pytest (`asyncio_mode="auto"`).

## Global Constraints

- Python 3.12+, Black line-length 100, Ruff, MyPy strict (no `Any`, PEP 604 unions).
- Comments/docstrings in English. **No inline French (or any language) in Python** — user
  -visible strings go through `core.i18n_*`.
- All datetimes tz-aware UTC (`datetime.now(UTC)`); AST guards enforce.
- Thresholds settings-driven; **tests read `settings`, never hardcode values**.
- New files decomposed (< 600 logical SLOC; CC < 15). No test may skip on env vars.
- JSONB: not used in this lot. AsyncSession: never shared across concurrent tasks.
- **Deviation from spec §4.1 (recorded):** status columns are `String(20)` + `str`-Enum
  classes with lowercase values (imitate `open_loops/models.py:21-33`), NOT
  `Enum(native_enum=False)` — avoids the uppercase-members telephony trap entirely.
- `constants.py` and `.env*` files move frequently: **Read before Edit at execution time.**

---

### Task 1: Constants + config module + Settings wiring + env examples

**Files:**
- Modify: `apps/api/src/core/constants.py` (append a `# Peers` block)
- Create: `apps/api/src/core/config/peers.py`
- Modify: `apps/api/src/core/config/__init__.py` (import + MRO)
- Modify: `apps/api/.env.example`, `.env.prod.example` (PEERS block; check `.env.min.prod`)
- Test: `apps/api/tests/unit/core/config/test_peers_settings.py`

**Interfaces:**
- Produces: `settings.peers_enabled: bool` (default False), `settings.peers_discovery_rate_limit_calls: int` (10), `settings.peers_discovery_rate_limit_window_seconds: int` (60), `settings.peers_message_max_per_day: int` (20), `settings.peers_message_max_per_day_per_pair: int` (10), `settings.peers_message_max_chars: int` (2000), `settings.peers_request_cooldown_days: int` (7), `settings.peers_request_expiry_days: int` (30), `settings.peers_delivery_sweep_seconds: int` (60), `settings.peers_delivery_max_attempts: int` (5), `settings.peers_access_log_retention_days: int` (90).

- [x] **Step 1: Write the failing test**

```python
"""Peers settings composition tests (Lot 1, Task 1)."""

from src.core.config import Settings, settings


def test_peers_settings_composed_with_defaults() -> None:
    """PeersSettings is in the Settings MRO with documented defaults."""
    assert settings.peers_enabled is False  # flag-off by default (spec §4.2)
    assert settings.peers_discovery_rate_limit_calls >= 1
    assert settings.peers_message_max_per_day >= 1
    assert settings.peers_message_max_per_day_per_pair <= settings.peers_message_max_per_day
    assert settings.peers_request_cooldown_days >= 1
    assert settings.peers_delivery_max_attempts >= 1
    assert settings.peers_access_log_retention_days >= 1


def test_peers_settings_env_overridable() -> None:
    """Field names follow the PEERS_* env convention (pydantic-settings)."""
    field_names = set(Settings.model_fields)
    assert {"peers_enabled", "peers_message_max_chars"} <= field_names
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_peers_settings.py -v`
Expected: FAIL (`AttributeError: peers_enabled`)

- [x] **Step 3: Implement**

`constants.py` — append (imitate the `OPEN_LOOPS_*` block):

```python
# Peers (peer-connections program, Lot 1)
PEERS_DISCOVERY_RATE_LIMIT_CALLS_DEFAULT = 10
PEERS_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT = 60
PEERS_MESSAGE_MAX_PER_DAY_DEFAULT = 20
PEERS_MESSAGE_MAX_PER_DAY_PER_PAIR_DEFAULT = 10
PEERS_MESSAGE_MAX_CHARS_DEFAULT = 2000
PEERS_REQUEST_COOLDOWN_DAYS_DEFAULT = 7
PEERS_REQUEST_EXPIRY_DAYS_DEFAULT = 30
PEERS_DELIVERY_SWEEP_SECONDS_DEFAULT = 60
PEERS_DELIVERY_MAX_ATTEMPTS_DEFAULT = 5
PEERS_ACCESS_LOG_RETENTION_DAYS_DEFAULT = 90
PEERS_CONTEXT_MESSAGE_MAX_CHARS = 500
```

`core/config/peers.py` — full module (imitate `core/config/open_loops.py` verbatim style:
module docstring, defaults imported from constants, `Field(description=…)` on every field,
`ge`/`le` bounds):

```python
"""Peers configuration module (peer-connections program, Lot 1).

User-to-user connections feature flag and policy thresholds. Every value is
env-overridable (``PEERS_*``) so quotas and cadences can be tuned in
production without a code change. Defaults imported from ``src.core.constants``
(the config layer never imports domains — see ``briefing.py``'s rationale).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    PEERS_ACCESS_LOG_RETENTION_DAYS_DEFAULT,
    PEERS_DELIVERY_MAX_ATTEMPTS_DEFAULT,
    PEERS_DELIVERY_SWEEP_SECONDS_DEFAULT,
    PEERS_DISCOVERY_RATE_LIMIT_CALLS_DEFAULT,
    PEERS_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    PEERS_MESSAGE_MAX_CHARS_DEFAULT,
    PEERS_MESSAGE_MAX_PER_DAY_DEFAULT,
    PEERS_MESSAGE_MAX_PER_DAY_PER_PAIR_DEFAULT,
    PEERS_REQUEST_COOLDOWN_DAYS_DEFAULT,
    PEERS_REQUEST_EXPIRY_DAYS_DEFAULT,
)


class PeersSettings(BaseSettings):
    """Env-overridable settings for user-to-user peer connections."""

    peers_enabled: bool = Field(
        default=False,
        description="Enable the peer-connections feature (discovery, messages, sharing).",
    )
    peers_discovery_rate_limit_calls: int = Field(
        default=PEERS_DISCOVERY_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=100,
        description="Discovery searches allowed per user per window (anti-enumeration).",
    )
    peers_discovery_rate_limit_window_seconds: int = Field(
        default=PEERS_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Window of the discovery-search rate limit.",
    )
    peers_message_max_per_day: int = Field(
        default=PEERS_MESSAGE_MAX_PER_DAY_DEFAULT,
        ge=1,
        le=500,
        description="Relayed messages a sender may enqueue per UTC day (all peers).",
    )
    peers_message_max_per_day_per_pair: int = Field(
        default=PEERS_MESSAGE_MAX_PER_DAY_PER_PAIR_DEFAULT,
        ge=1,
        le=100,
        description="Relayed messages a sender may enqueue per UTC day toward one peer.",
    )
    peers_message_max_chars: int = Field(
        default=PEERS_MESSAGE_MAX_CHARS_DEFAULT,
        ge=100,
        le=10000,
        description="Max characters of a relayed-message directive.",
    )
    peers_request_cooldown_days: int = Field(
        default=PEERS_REQUEST_COOLDOWN_DAYS_DEFAULT,
        ge=0,
        le=365,
        description="Days before a declined pair may receive a new request.",
    )
    peers_request_expiry_days: int = Field(
        default=PEERS_REQUEST_EXPIRY_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Pending requests older than this are expired silently.",
    )
    peers_delivery_sweep_seconds: int = Field(
        default=PEERS_DELIVERY_SWEEP_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Interval of the pending-message delivery sweep (Lot 4).",
    )
    peers_delivery_max_attempts: int = Field(
        default=PEERS_DELIVERY_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Real delivery failures before a message is marked failed (Lot 4).",
    )
    peers_access_log_retention_days: int = Field(
        default=PEERS_ACCESS_LOG_RETENTION_DAYS_DEFAULT,
        ge=7,
        le=730,
        description="Sweep prunes peer_access_log rows older than this (Lot 5).",
    )
```

`core/config/__init__.py`: add `from .peers import PeersSettings` (alphabetical among
imports, `core/config/__init__.py:51-58` block) and add `PeersSettings,` to the `Settings`
MRO (next to `OpenLoopsSettings`, line ~116).

`.env.example` + `.env.prod.example`: append a commented `# --- Peers ---` block with
`PEERS_ENABLED=false` and one line per var above (defaults spelled out).

- [x] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_peers_settings.py -v`
Expected: PASS (2 tests)

- [x] **Step 5: Checkpoint — propose commit to user**

Suggested: `feat(peers): add PeersSettings config module and defaults (Lot 1.1)`

---

### Task 2: Shared name-folding helper (hoisted from relations)

**Files:**
- Create: `apps/api/src/domains/shared/text_normalization.py`
- Modify: `apps/api/src/domains/relations/service.py:47-56` (`_normalize_name` body → import)
- Test: `apps/api/tests/unit/domains/shared/test_text_normalization.py`

**Interfaces:**
- Produces: `fold_name(name: str) -> str` — NFKD-strips diacritics, casefolds, strips
  whitespace; `""` for empty/whitespace input. Consumed by Task 6 (discovery) and by
  `relations/service.py` (existing behavior, unchanged).

- [x] **Step 1: Write the failing test**

```python
"""Name-folding helper tests (hoisted from relations — Lot 1, Task 2)."""

from src.domains.shared.text_normalization import fold_name


def test_fold_name_strips_accents_and_case() -> None:
    assert fold_name("Jérôme GOUVIER") == "jerome gouvier"


def test_fold_name_handles_empty_and_whitespace() -> None:
    assert fold_name("") == ""
    assert fold_name("   ") == ""


def test_fold_name_is_idempotent() -> None:
    once = fold_name("Måns Öberg")
    assert fold_name(once) == once
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/shared/test_text_normalization.py -v`
Expected: FAIL (ModuleNotFoundError)

- [x] **Step 3: Implement**

`shared/text_normalization.py` — move the exact body of
`relations/service.py::_normalize_name` (verified `relations/service.py:47-56`):

```python
"""Shared text-normalization helpers.

``fold_name`` is the single identity-folding chokepoint used by the relations
CRM and the peers discovery search. Hoisted from ``relations/service.py``
(peer-connections program, Lot 1) — behavior unchanged.
"""

import unicodedata


def fold_name(name: str) -> str:
    """Fold a display name for exact-match comparison.

    NFKD strips diacritics; casefold lowercases aggressively. Empty or
    whitespace-only input folds to the empty string.

    Args:
        name: Raw display name.

    Returns:
        The folded name.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    return stripped.casefold().strip()
```

`relations/service.py`: replace `_normalize_name`'s body with a delegation (keep the private
name so its call sites and tests stay untouched):

```python
from src.domains.shared.text_normalization import fold_name

def _normalize_name(name: str) -> str:
    """Delegates to the shared folding chokepoint (see text_normalization)."""
    return fold_name(name)
```

- [x] **Step 4: Run new AND relations tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/shared/test_text_normalization.py tests/unit/domains/relations/ -v`
Expected: PASS, zero relations regressions

- [x] **Step 5: Checkpoint — propose commit to user**

Suggested: `refactor(shared): hoist name folding to shared chokepoint (Lot 1.2)`

---

### Task 3: Models + users column + migration + 3-place registration

**Files:**
- Create: `apps/api/src/domains/peers/__init__.py`, `apps/api/src/domains/peers/models.py`
- Modify: `apps/api/src/domains/users/models.py` (add `discovery_enabled`)
- Modify: `apps/api/alembic/env.py`, `apps/api/src/infrastructure/database/registry.py`,
  `apps/api/src/infrastructure/startup/registries.py` (model imports — imitate how
  `open_loops.models` is registered in each)
- Create: migration via `task db:migrate:create -- "add peers tables"`
- Test: `apps/api/tests/unit/domains/peers/test_models.py`

**Interfaces:**
- Produces: `PeerConnection`, `PeerBlock`, `PeerDomainShare`, `PeerMessage`, `PeerAccessLog`
  ORM models; enums `PeerConnectionStatus` (`pending|accepted|declined|removed`),
  `PeerShareDomain` (`calendar|task`), `PeerShareLevel` (`availability|details|titles`),
  `PeerMessageStatus` (`pending|delivered|failed|cancelled`);
  `canonical_pair(u1: UUID, u2: UUID) -> tuple[UUID, UUID]`;
  `User.discovery_enabled: bool` (default False).

- [x] **Step 1: Write the failing test**

```python
"""Peers ORM model tests (Lot 1, Task 3)."""

from uuid import UUID

from src.domains.peers.models import (
    PeerConnection,
    PeerConnectionStatus,
    PeerMessageStatus,
    PeerShareDomain,
    PeerShareLevel,
    canonical_pair,
)

U1 = UUID("00000000-0000-0000-0000-000000000001")
U2 = UUID("00000000-0000-0000-0000-000000000002")


def test_canonical_pair_orders_uuids() -> None:
    assert canonical_pair(U2, U1) == (U1, U2)
    assert canonical_pair(U1, U2) == (U1, U2)


def test_status_enums_are_lowercase_values() -> None:
    """String(20) columns + lowercase str-enum values (open_loops pattern)."""
    assert PeerConnectionStatus.PENDING.value == "pending"
    assert PeerMessageStatus.CANCELLED.value == "cancelled"
    assert PeerShareDomain.CALENDAR.value == "calendar"
    assert PeerShareLevel.AVAILABILITY.value == "availability"


def test_connection_table_constraints_declared() -> None:
    names = {c.name for c in PeerConnection.__table_args__ if hasattr(c, "name")}
    assert "uq_peer_connections_pair" in names
    assert "ck_peer_connections_pair_order" in names
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/peers/test_models.py -v`
Expected: FAIL (ModuleNotFoundError)

- [x] **Step 3: Implement models**

`domains/peers/models.py` (imitate `open_loops/models.py` for style, `users/models.py:608`
`AdminAuditLog` for the immutable log). Key content (full file, docstrings included, ~180
SLOC — under every ratchet):

```python
"""Peers domain models (peer-connections program, Lot 1).

One row per user pair in ``peer_connections`` (canonical order user_a < user_b
— the UNIQUE + CHECK constraints make duplicate/self pairs unrepresentable).
Re-requests after decline/removal are STATUS TRANSITIONS on the existing row,
never new rows (spec §5.3). ``peer_access_log`` is immutable (AdminAuditLog
pattern): created_at only, no updates.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base


class PeerConnectionStatus(str, Enum):
    """Lifecycle of a pair row (single row per pair — transitions only)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REMOVED = "removed"


class PeerShareDomain(str, Enum):
    """Shareable domains, v1 set (spec A1). Singular vocabulary."""

    CALENDAR = "calendar"
    TASK = "task"


class PeerShareLevel(str, Enum):
    """Granularity of a share (calendar: availability|details; task: titles)."""

    AVAILABILITY = "availability"
    DETAILS = "details"
    TITLES = "titles"


class PeerMessageStatus(str, Enum):
    """Delivery lifecycle of a relayed message (Lot 4 consumes)."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


def canonical_pair(u1: uuid.UUID, u2: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return the (user_a, user_b) canonical ordering of a pair (a < b)."""
    return (u1, u2) if u1 < u2 else (u2, u1)


class PeerConnection(BaseModel):
    """One row per user pair; status transitions carry the whole lifecycle."""

    __tablename__ = "peer_connections"

    user_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Which side initiated the CURRENT pending/last request.",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PeerConnectionStatus.PENDING.value, index=True
    )
    context_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional requester note, shown provenance-framed to the addressee.",
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_peer_connections_pair"),
        CheckConstraint("user_a_id < user_b_id", name="ck_peer_connections_pair_order"),
    )
```

(`PeerBlock`, `PeerDomainShare`, `PeerMessage` follow the same shape: `PeerBlock` =
`blocker_id`/`blocked_id` + `uq_peer_blocks_pair` UNIQUE + `ck_peer_blocks_not_self` CHECK
`blocker_id != blocked_id`; `PeerDomainShare` = `connection_id` FK
`peer_connections.id ondelete=CASCADE` + `owner_user_id` FK users CASCADE + `domain`
String(20) + `level` String(20) + `uq_peer_domain_shares_owner_domain`
UNIQUE(connection_id, owner_user_id, domain); `PeerMessage` = `connection_id` FK CASCADE,
`sender_id`/`recipient_id` FK users CASCADE, `content: Text | None` (scrubbed post-delivery),
`status` String(20) default pending + index, `attempts: int` default 0, `delivered_at`,
`last_error: String(50) | None` (typed code only), index on (`status`, `created_at`).
`PeerAccessLog(Base, UUIDMixin)` — NOT BaseModel: immutable, `created_at` only (copy the
`AdminAuditLog` timestamp column verbatim, `users/models.py:640-646`), columns
`accessor_id`/`owner_id` FK users CASCADE, `connection_id` FK `ondelete="SET NULL"` nullable,
`domain` String(20), `tool_name` String(100), index on (`owner_id`, `created_at`).)

`users/models.py` — add next to `memory_enabled` (`users/models.py:141`):

```python
    # Peer discovery opt-in (peer-connections program, Lot 1)
    discovery_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="Opt-in: this user can be found by peer discovery search. Default off.",
    )
```

- [x] **Step 4: Register models in the 3 mandated places**

Grep `open_loops` in `alembic/env.py`, `infrastructure/database/registry.py`
(`import_all_models`) and `infrastructure/startup/registries.py` (`import_domain_models`);
add the identical `src.domains.peers.models` import line in each.

- [x] **Step 5: Run model tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/peers/test_models.py -v`
Expected: PASS

- [x] **Step 6: Create + verify migration**

Run: `task db:migrate:create -- "add peers tables"` then inspect the generated file: 5
`create_table` + 1 `add_column` (users.discovery_enabled with `server_default="false"`),
`downgrade()` exact inverse (drop column + 5 drop_table, reverse order). Then:
`task db:migrate:replay-check` and verify `alembic heads` prints a single head.
Expected: replay-check green.

- [x] **Step 7: Checkpoint — propose commit to user**

Suggested: `feat(peers): models, users.discovery_enabled, migration + registration (Lot 1.3)`

---

### Task 4: GDPR — user_data_map classification + purge statements

**Files:**
- Modify: `apps/api/src/domains/users/user_data_map.py`
- Modify: `apps/api/src/domains/users/account_deletion_service.py`
  (`build_purge_statements`)
- Test: the existing CI guard `tests/unit/domains/users/test_user_data_map_guard.py`
  (no edits — it must pass as-is; it fails on any unclassified table and cross-checks purge
  coverage)

**Interfaces:**
- Consumes: table names from Task 3.
- Produces: purge + export classification for the 5 tables; `USER_COLUMNS` entry for
  `discovery_enabled`.

- [x] **Step 1: Run the guard to see it fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/users/test_user_data_map_guard.py -v`
Expected: FAIL — 5 unclassified tables + 1 unclassified users column.

- [x] **Step 2: Classify**

`user_data_map.py` — add to `TABLE_RULES` (follow the in-file grouping comments):

```python
    "peer_connections": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="User-to-user connection lifecycle rows (either side) — purged on deletion.",
    ),
    "peer_blocks": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Anti-harassment blocks (either side) — purged on deletion.",
    ),
    "peer_domain_shares": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason="Cascades from peer_connections; exported as the user's sharing choices.",
    ),
    "peer_messages": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Relay delivery metadata (content scrubbed post-delivery) — purged on deletion.",
    ),
    "peer_access_log": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Cross-user read audit (accessor or owner side) — purged on deletion.",
    ),
```

and to `USER_COLUMNS` (next to `"memory_enabled"`, line ~366):
`"discovery_enabled": _PREFERENCE,`

- [x] **Step 3: Extend purge statements**

In `build_purge_statements` (`account_deletion_service.py:49`): child tables first —
`peer_domain_shares` is CASCADE-covered but the guard may require explicit coverage for
USER_PURGED only; add explicit deletes for `peer_messages` (sender OR recipient),
`peer_access_log` (accessor OR owner), `peer_blocks` (blocker OR blocked),
`peer_connections` (user_a OR user_b), following the file's existing
`Table.delete().where(or_(...))` idiom for two-column ownership (imitate an existing
two-sided example in the file if present; otherwise `sa.or_` on the metadata table columns).

- [x] **Step 4: Run the guard + deletion-service tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/users/ -v -k "data_map or deletion"`
Expected: PASS.

- [x] **Step 5: Checkpoint — propose commit to user**

Suggested: `feat(peers): GDPR classification + purge coverage (Lot 1.4)`

---

### Task 5: Repository layer

**Files:**
- Create: `apps/api/src/domains/peers/repository.py`
- Test: `apps/api/tests/unit/domains/peers/test_repository_logic.py` (pure logic) and
  `apps/api/tests/integration/domains/peers/test_repository_db.py` (constraints, marked
  `@pytest.mark.integration` — real PostgreSQL semantics: pair uniqueness, canonical CHECK)

**Interfaces:**
- Consumes: models from Task 3, `BaseRepository` (`src/core/repository.py:45`).
- Produces (exact signatures, all `async`, all on `PeersRepository(db: AsyncSession)`):
  - `get_pair(u1: UUID, u2: UUID) -> PeerConnection | None`
  - `create_or_reuse_request(requester_id: UUID, addressee_id: UUID, context_message: str | None) -> PeerConnection` — INSERT new pair row, or transition an existing `declined|removed` row back to `pending` (updates `requested_by_id`, `requested_at`, `context_message`, clears `responded_at`/`removed_at`)
  - `transition_status(connection: PeerConnection, new_status: PeerConnectionStatus, *, now: datetime) -> PeerConnection` — sets `responded_at` (accepted/declined) or `removed_at` (removed)
  - `list_pending_for_user(user_id: UUID) -> list[PeerConnection]` (incoming + outgoing)
  - `list_accepted_for_user(user_id: UUID) -> list[PeerConnection]`
  - `has_block_between(u1: UUID, u2: UUID) -> bool` (either direction)
  - `create_block(blocker_id: UUID, blocked_id: UUID) -> PeerBlock` /
    `delete_block(blocker_id: UUID, blocked_id: UUID) -> bool` /
    `list_blocks(blocker_id: UUID) -> list[PeerBlock]`
  - `upsert_share(connection_id: UUID, owner_user_id: UUID, domain: PeerShareDomain, level: PeerShareLevel) -> PeerDomainShare` (pg
    `ON CONFLICT DO UPDATE` on the UNIQUE triple — imitate
    `ChatRepository.create_or_update_token_summary`) /
    `delete_share(connection_id: UUID, owner_user_id: UUID, domain: PeerShareDomain) -> bool` /
    `list_shares(connection_id: UUID) -> list[PeerDomainShare]` (both owners)
  - `count_messages_today(sender_id: UUID, *, now: datetime) -> int` and
    `count_messages_today_for_pair(sender_id: UUID, recipient_id: UUID, *, now: datetime) -> int`
    (UTC-day window)
  - `enqueue_message(connection_id: UUID, sender_id: UUID, recipient_id: UUID, content: str) -> PeerMessage`
  - `log_access(accessor_id: UUID, owner_id: UUID, connection_id: UUID | None, domain: str, tool_name: str) -> None`
  - `list_access_log_for_owner(owner_id: UUID, limit: int) -> list[PeerAccessLog]`
  - `expire_stale_pending(older_than: datetime) -> int` (pending → removed, bulk UPDATE)
  - (Lot 4 will add `claim_pending_messages` with `FOR UPDATE SKIP LOCKED` — NOT in this lot.)

- [x] **Step 1: Write failing pure-logic tests** (UTC-day boundary via settings-free logic;
  canonicalization delegation) — file `test_repository_logic.py`:

```python
"""Pure-logic tests for PeersRepository helpers (Lot 1, Task 5)."""

from datetime import UTC, datetime

from src.domains.peers.repository import utc_day_bounds


def test_utc_day_bounds_covers_the_utc_day() -> None:
    now = datetime(2026, 7, 29, 23, 59, 59, tzinfo=UTC)
    start, end = utc_day_bounds(now)
    assert start == datetime(2026, 7, 29, 0, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)
```

- [x] **Step 2: Run to verify failure**, then implement `repository.py`: class
  `PeersRepository` with the exact signatures above, module-level helper
  `utc_day_bounds(now: datetime) -> tuple[datetime, datetime]`. Every query uses the
  canonical pair (`canonical_pair` from models) before touching `user_a_id`/`user_b_id`.
  Docstrings Google-style on every method. Repository never commits — sessions are owned by
  the service/router layer (imitate `open_loops/repository.py`).

- [x] **Step 3: Write integration tests** (`@pytest.mark.integration`,
  `tests/integration/domains/peers/test_repository_db.py`): pair uniqueness raises on
  duplicate INSERT regardless of argument order; CHECK rejects self-pairs;
  `create_or_reuse_request` transitions a declined row instead of inserting;
  `upsert_share` is idempotent on the triple. Imitate an existing integration module's
  session fixture (grep `tests/integration/` for the canonical DB fixture).

- [x] **Step 4: Run both suites**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/peers/ -v` then
`task test:backend:integration` (requires PostgreSQL+Redis up).
Expected: PASS.

- [x] **Step 5: Checkpoint — propose commit to user**

Suggested: `feat(peers): repository with pair-canonical queries (Lot 1.5)`

---

### Task 6: Service layer — lifecycle guards + discovery

**Files:**
- Create: `apps/api/src/domains/peers/service.py`
- Create: `apps/api/src/domains/peers/schemas.py` (service-level DTOs, Pydantic v2,
  `Field(description=…)` everywhere, `ConfigDict(from_attributes=True)` where ORM-fed)
- Test: `apps/api/tests/unit/domains/peers/test_service.py` (mock repository — behavioral
  guards) + integration happy-path in Task 7's router tests

**Interfaces:**
- Consumes: `PeersRepository` (Task 5), `fold_name` (Task 2), `settings` (Task 1),
  exception raisers (`core/exceptions.py`), `mask_email` (produced here).
- Produces (class `PeersService`, constructor `(self, db: AsyncSession)` — creates its
  repository, service-layer pattern):
  - `mask_email(email: str) -> str` (module-level, pure): `"jerome@gmail.com"` →
    `"j…@g….com"` — first char of local part, `…@`, first char of domain, `…`, final
    `.suffix`; single-char parts degrade gracefully (`"a@b.co"` → `"a…@b….co"`).
  - `search_discoverable(searcher_id: UUID, full_name: str) -> list[DiscoveryMatch]` —
    folds the query; empty fold → `[]`; scans users `WHERE is_active AND deleted_at IS NULL
    AND discovery_enabled AND full_name IS NOT NULL`, folds candidates in Python (O(N)
    accepted at self-hosted instance scale — documented in the docstring), excludes self and
    any pair with a block in either direction. `DiscoveryMatch = {peer_id, display_name,
    email_hint}`.
  - `set_discovery(user_id: UUID, enabled: bool) -> None`
  - `request_connection(requester_id: UUID, addressee_id: UUID, context_message: str | None) -> ConnectionView` —
    guard order (each guard's test is mandatory): (1) addressee exists, active, opted-in and
    unblocked both directions, else `raise_user_not_found(addressee_id)` — the NEUTRAL
    not-found, never a distinct "blocked" error (hide_existence, spec §12.2); (2) context
    message ≤ `PEERS_CONTEXT_MESSAGE_MAX_CHARS` else `raise_invalid_input`; (3) existing
    pair row: `accepted` → `raise_invalid_input("already_connected")`; own `pending` →
    idempotent return; **their** `pending` → auto-accept (crossing rule, spec §5.2);
    `declined` within `settings.peers_request_cooldown_days` of `responded_at` →
    neutral `raise_user_not_found` (cooldown must be indistinguishable); else
    `create_or_reuse_request`.
  - `respond_request(user_id: UUID, connection_id: UUID, accept: bool) -> ConnectionView` —
    only the NON-requesting side of a `pending` row may respond; else
    `raise_permission_denied`.
  - `remove_connection(user_id: UUID, connection_id: UUID) -> ConnectionView` — participant
    of an `accepted` row; transitions to `removed`, deletes its shares.
  - `block_peer(blocker_id: UUID, blocked_id: UUID) -> None` — creates block (idempotent),
    transitions any pair row to `removed`, deletes shares. Never notifies (spec A2).
  - `unblock_peer(blocker_id: UUID, blocked_id: UUID) -> bool`
  - `set_share(user_id: UUID, connection_id: UUID, domain: PeerShareDomain, level: PeerShareLevel | None) -> None` —
    participant + `accepted` only; `level=None` deletes; validates domain/level combinations
    (calendar: availability|details; task: titles) else `raise_invalid_input`.
  - `get_connections(user_id: UUID) -> list[ConnectionView]` — each with `my_shares` and
    `their_shares` (both directions, explicit requirement) + peer display name + pinned
    `email_hint` (spec §12.8).
  - `get_access_log(user_id: UUID, limit: int) -> list[AccessLogEntry]`
  - Events for Lot 3: every state-changing method returns the view + appends to
    `self.pending_events: list[PeerEvent]` (`PeerEvent = {kind, connection_id, actor_id,
    affected_ids}`) — Lot 3's dispatcher wiring consumes them; Lot 1 just exposes the list
    (tested), keeping notification concerns out of this lot.

- [x] **Step 1: Write the failing guard tests** — one test per guard above (real function
  names, mocked repository), plus `mask_email` cases:

```python
def test_mask_email_standard() -> None:
    assert mask_email("jerome@gmail.com") == "j…@g….com"

def test_mask_email_short_parts() -> None:
    assert mask_email("a@b.co") == "a…@b….co"

async def test_request_to_blocked_addressee_is_neutral_not_found() -> None:
    """Blocked pairs answer exactly like unknown users (hide_existence)."""
    ...  # repo.has_block_between returns True → expect the user-not-found HTTP error,
         # assert the response body is BYTE-IDENTICAL to the genuinely-unknown case.

async def test_crossing_requests_auto_accept() -> None:
    ...  # existing pending row requested by THE OTHER side → respond path, status accepted

async def test_declined_within_cooldown_is_neutral() -> None:
    ...  # declined row, responded_at = now - (cooldown_days - 1) read from settings
```

- [x] **Step 2: Run to verify failure, implement `service.py` + `schemas.py`** (split
  `service.py` if it approaches 600 logical SLOC: `service_discovery.py` for
  search/mask_email is the natural cut). Structured logging (`structlog`, ids only — no
  names at INFO), Google docstrings, guards in the exact order above.

- [x] **Step 3: Run service tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/peers/test_service.py -v`
Expected: PASS.

- [x] **Step 4: Checkpoint — propose commit to user**

Suggested: `feat(peers): service with lifecycle guards + neutral-error discovery (Lot 1.6)`

---

### Task 7: Router + rate limit + flag-guarded wiring

**Files:**
- Create: `apps/api/src/domains/peers/router.py`
- Modify: `apps/api/src/api/v1/routes.py` (flag-guarded include — imitate the
  `open_loops` block at `routes.py:73-76`)
- Test: `apps/api/tests/unit/domains/peers/test_router.py` (FastAPI TestClient/httpx with
  dependency overrides — imitate an existing router test in
  `tests/unit/domains/open_loops/`)

**Interfaces:**
- Consumes: `PeersService` (Task 6), `get_current_active_session`, `get_db`,
  `create_user_rate_limiter` (imitate `account_export/router.py:34-37`).
- Produces endpoints (prefix `/peers`, tags `["peers"]`, response models from
  `schemas.py`): `GET /peers/me`, `PUT /peers/me` (body `{discovery_enabled: bool}`),
  `POST /peers/discovery/search` (body `{full_name: str}`, dependency
  `rate_limit_peer_discovery = create_user_rate_limiter(action="peers_discovery",
  max_calls=<settings-driven>)` — if `create_user_rate_limiter` only accepts constants,
  pass a callable or read settings at request time following the tool decorators' lambda
  idiom; verify its signature at execution), `POST /peers/requests`,
  `GET /peers/requests`, `POST /peers/requests/{connection_id}/respond`
  (body `{accept: bool}`), `GET /peers/connections`,
  `DELETE /peers/connections/{connection_id}`,
  `PUT /peers/connections/{connection_id}/shares` (body `{domain, level | null}`),
  `GET /peers/connections/{connection_id}/access-log`, `POST /peers/blocks`
  (body `{peer_id}`), `DELETE /peers/blocks/{peer_id}`, `GET /peers/blocks`.

- [x] **Step 1: Write failing router tests** — auth required (401 unauthenticated), the
  discovery rate limit fires (429 after `settings.peers_discovery_rate_limit_calls` calls),
  neutral-404 parity (blocked vs unknown byte-identical), respond forbidden for the
  requester side (403), full happy path request→respond→shares→remove.
- [x] **Step 2: Implement `router.py`**, then wire `routes.py`:

```python
if getattr(settings, "peers_enabled", False):
    from src.domains.peers.router import router as peers_router

    api_router.include_router(peers_router)
```

- [x] **Step 3: Run router tests + flag-off test** (app boots with `peers_enabled=False`
  and `/api/v1/peers/me` returns 404 — route absent).
- [x] **Step 4: Checkpoint — propose commit to user**

Suggested: `feat(peers): REST surface, rate-limited discovery, flag-guarded (Lot 1.7)`

---

### Task 8: Backend i18n (API messages)

**Files:**
- Modify: `apps/api/src/core/i18n_api_messages.py` (follow the in-file table structure —
  Read first; keys in all 6 backend languages, `zh-CN` canonical)
- Test: extend the existing i18n completeness test for APIMessages if one exists (grep
  `i18n_api_messages` in `tests/unit/core/`); otherwise add
  `tests/unit/core/test_i18n_peers_messages.py` asserting every new key exists in all 6
  languages.

**Interfaces:**
- Produces message keys consumed by Tasks 6-7 raisers/details: `peers_already_connected`,
  `peers_request_sent`, `peers_request_accepted`, `peers_request_declined`,
  `peers_connection_removed`, `peers_share_updated`, `peers_invalid_share_level`,
  `peers_context_message_too_long`. (Chat/proactive bodies are Lot 3 —
  `ProactiveMessages` untouched here.)

- [x] **Step 1: Write the failing completeness test** (iterate the 6 supported languages
  from `SUPPORTED_LANGUAGES`, assert each new key resolves non-empty and differs from the
  raw key).
- [x] **Step 2: Add the 8 keys × 6 languages** (translations written properly per language,
  `zh-CN` key — never `zh`).
- [x] **Step 3: Run the test + the i18n guards.** Expected: PASS.
- [x] **Step 4: Checkpoint — propose commit to user**

Suggested: `feat(peers): backend i18n for API messages, 6 languages (Lot 1.8)`

---

### Task 9: Lot gate

- [x] **Step 1:** `task lint` — zero new violations (ratchets shrink-only).
- [x] **Step 2:** `task test:backend:unit:fast` — full fast suite green.
- [x] **Step 3:** `task test:backend:integration` — with PostgreSQL + Redis up.
- [x] **Step 4:** `task db:migrate:replay-check` — green; `alembic heads` single.
- [x] **Step 5:** `task ci:fast` — the pre-push gate, in full.
- [x] **Step 6:** Report evidence (exact commands, exit codes, test counts) and propose the
  final Lot 1 commit to the user. Update the peers program memory file status.

---

## Self-review notes (done at plan writing)

- Spec coverage: Lot 1 scope = spec §4.1-§4.3, §5 (guards), §12.1-2/5-8 (neutral errors,
  logging, GDPR), §13 rows relevant to lifecycle. Chat/notifications (§6) deliberately Lot 3;
  tools (§7), relay (§8-9), sharing reads (§5/A1 read path) Lots 4-5; frontend (§10) Lot 2 —
  no Lot 1 gap found.
- Type consistency: `PeerConnectionStatus`/`PeerShareDomain`/`PeerShareLevel`/
  `PeerMessageStatus` names used identically across Tasks 3/5/6/7.
- No placeholder patterns remain; the two "verify at execution" notes (rate-limiter
  signature, purge idiom for two-sided ownership) name the exact file to check and the
  fallback idiom to use.
