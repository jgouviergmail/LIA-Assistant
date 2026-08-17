# Document Generation Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (owner directive: INLINE execution, no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the assistant a `generate_document` capability (csv, xlsx, docx, pptx, pdf, md, txt) mirroring the `image_generation` domain: internal structured-output LLM → pure renderer → Attachment (TTL purge) → card below the assistant message (download; PDF inline).

**Architecture:** Virtual agent (manifest + tool, no LangGraph graph) registered in the catalogue and domain taxonomy behind a `document_generation_enabled` flag; content produced by a dedicated `document_generation` LLM type via `get_structured_output_with_retry`, rendered by per-format pure renderers (zero new dependency), stored via `AttachmentRepository` with `attachments_ttl_hours`, delivered live via the SSE done chunk and after reload via `message_metadata` — one wire serializer for both.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, LangChain structured output, openpyxl / python-docx / python-pptx / PyMuPDF (Story) / csv stdlib, Next.js 16 + React 19 + vitest, react-i18next (6 locales).

**Spec:** `docs/superpowers/specs/2026-08-17-document-generation-design.md`

## Global Constraints

- **Git**: the executor NEVER commits/pushes — the owner handles all git operations (project rule). Every task therefore ends with a verification step, not a commit step.
- **Inline only** — no subagents (owner directive).
- Python: Black line-length 100, Ruff, **MyPy strict** (full type hints, PEP 604 `X | None`), Google-style docstrings, English comments/docstrings everywhere.
- Logging: `structlog.get_logger(__name__)`; counters/IDs at INFO, contents at DEBUG; never `print()`.
- Datetimes: `datetime.now(UTC)` only; the AST guard `test_no_hardcoded_timezone_guard.py` fails on naive calls.
- i18n: every new frontend key added to **all 6 locales** (en, fr, de, es, it, zh) — pre-commit enforces strict parity with `en`; zh duplicates `_one` where pluralized.
- Tests: `asyncio_mode = "auto"`; thresholds read from `settings`, never hardcoded; tests mirror source structure; no test may skip on a missing provider key.
- File size: every new logical file stays under 600 logical SLOC.
- New env vars land in `.env.example` (and `.env.prod.example` for prod-relevant flags).
- Gates per task: `cd apps/api && .venv/Scripts/pytest <target> -v` for the task's tests; end-of-lot: `task lint` + `task test:backend:unit:fast` (backend) / `task test:frontend` (frontend); before handing back to the owner: `task ci:fast`.
- Existing single Alembic head at plan time includes the uncommitted `3b4c5d6e7f8a` (agent plugins) revision — **verify the actual head with `alembic heads` before writing the migration**.

---

### Task 0: ADR-226 + index cross-references

**Files:**
- Create: `docs/architecture/ADR-226-Document-Generation-Agent.md`
- Modify: `docs/architecture/ADR_INDEX.md` (append entry), `docs/INDEX.md` (if it lists ADRs individually — check and mirror ADR-225's entry style)

**Interfaces:**
- Consumes: the approved spec.
- Produces: the ADR number (226) referenced by code comments and later tasks.

- [ ] **Step 1: Write the ADR** — sections: Status (Accepted), Context (capability gap, image_generation precedent), Decision (internal dedicated LLM type + pure renderers + Attachment TTL reuse + PDF inline disposition + formula-injection neutralization mandatory), Consequences (no new dependency; implicit dependency on ATTACHMENTS capability for card links — same as images; cost = LLM tokens via standard tracking, no pricing table), Alternatives rejected (planner-supplied content only; Skills mechanism). Cite the executed probes (formats writable, `=1+2` → `data_type "f"`, RFC 5987 filenames, utf-8-sig BOM).
- [ ] **Step 2: Add the ADR_INDEX.md line** mirroring the ADR-225 entry format exactly (number, title, date 2026-08-17, one-line summary).
- [ ] **Step 3: Verify** — Run: `task lint:docs`. Expected: PASS (no broken links).

---

### Task 1: Constants + `DocumentGenerationSettings` + Settings MRO + env examples

**Files:**
- Modify: `apps/api/src/core/constants.py` (new block after the image generation block at ~line 4781)
- Create: `apps/api/src/core/config/document_generation.py`
- Modify: `apps/api/src/core/config/__init__.py` (Settings MRO, line ~117, insert after `ImageGenerationSettings`)
- Modify: `.env.example` (~line 1878, after the image generation block; timeout pair near line 1818), `.env.prod.example` (mirror flag block)
- Test: `apps/api/tests/unit/core/config/test_document_generation_settings.py`

**Interfaces:**
- Produces: `settings.document_generation_enabled: bool`, `settings.document_generation_rate_limit_calls: int`, `settings.document_generation_rate_limit_window: int`, `settings.document_generation_tool_timeout_seconds: float`, `settings.max_document_generation_tool_timeout_seconds: float`, `settings.document_generation_max_source_chars: int` — consumed by Tasks 10, 11, 12.

- [ ] **Step 1: Write the failing test**

```python
"""Defaults and env overrides for DocumentGenerationSettings (ADR-226)."""

from src.core.config.document_generation import DocumentGenerationSettings
from src.core.constants import (
    DOCUMENT_GENERATION_ENABLED_DEFAULT,
    DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
)


def test_defaults_come_from_constants() -> None:
    s = DocumentGenerationSettings()
    assert s.document_generation_enabled is DOCUMENT_GENERATION_ENABLED_DEFAULT
    assert s.document_generation_rate_limit_calls == DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT
    assert (
        s.document_generation_rate_limit_window
        == DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT
    )
    assert (
        s.document_generation_tool_timeout_seconds
        == DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT
    )
    assert (
        s.max_document_generation_tool_timeout_seconds
        == MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT
    )
    assert (
        s.document_generation_max_source_chars == DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT
    )


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_GENERATION_ENABLED", "false")
    monkeypatch.setenv("DOCUMENT_GENERATION_RATE_LIMIT_CALLS", "3")
    s = DocumentGenerationSettings()
    assert s.document_generation_enabled is False
    assert s.document_generation_rate_limit_calls == 3


def test_composed_into_settings() -> None:
    from src.core.config import Settings

    assert "document_generation_enabled" in Settings.model_fields
```

- [ ] **Step 2: Run test to verify it fails** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_document_generation_settings.py -v`. Expected: FAIL (`ModuleNotFoundError`/`ImportError`).

- [ ] **Step 3: Add the constants block** in `core/constants.py`, immediately after the image generation constants (~line 4800), same comment style:

```python
# ============================================================================
# DOCUMENT GENERATION (evolution — Document Generation Agent, ADR-226)
# ============================================================================
# Feature flag
DOCUMENT_GENERATION_ENABLED_DEFAULT: bool = True

# Rate limiting: mirrors image generation — 10 calls / 5 min per user bounds a
# runaway loop while never blocking normal usage (1-2 documents per message).
DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT: int = 10
DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT: int = 300

# Timeout family (ADR-160 doctrine, like browser / image / sub-agent): the
# internal structured-output LLM call writes long documents (up to max_tokens
# of the document_generation LLM type), well above the generic 30s default.
# Dedicated ceiling so a planner-requested timeout is never capped below the
# real latency of a large document.
DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT: float = 120.0
MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT: float = 480.0

# Cap on the source_data characters forwarded to the document LLM (research
# results can be arbitrarily large; the excess is truncated and the truncation
# is stated in the tool result — a count shown is a claim).
DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT: int = 60000
```

- [ ] **Step 4: Create `src/core/config/document_generation.py`** — exact mirror of `image_generation.py`'s structure:

```python
"""Document generation configuration module.

Contains settings for the AI document generation feature (ADR-226):
- Feature toggle (document_generation_enabled)
- Rate limiting and tool-timeout family (ADR-160)
- Source-data size cap forwarded to the internal LLM

Note: the model is managed via the admin LLM Config system (LLM type
``document_generation``); the per-user opt-in lives on the User model.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DOCUMENT_GENERATION_ENABLED_DEFAULT,
    DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
)


class DocumentGenerationSettings(BaseSettings):
    """Settings for the AI document generation feature."""

    document_generation_enabled: bool = Field(
        default=DOCUMENT_GENERATION_ENABLED_DEFAULT,
        description=(
            "Global feature flag for AI document generation. When false, the "
            "generate_document tool is not registered and the "
            "document_generation domain is absent from the planner catalogue."
        ),
    )

    document_generation_rate_limit_calls: int = Field(
        default=DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=100,
        description="Max generate_document calls per user per window.",
    )

    document_generation_rate_limit_window: int = Field(
        default=DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate limit window (seconds) for the document tool.",
    )

    document_generation_tool_timeout_seconds: float = Field(
        default=DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=600.0,
        description=(
            "Wall-clock FLOOR (seconds) applied by the parallel executor to a "
            "generate_document step — the internal LLM call writes whole "
            "documents and exceeds the generic 30s tool default."
        ),
    )

    max_document_generation_tool_timeout_seconds: float = Field(
        default=MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=900.0,
        description=(
            "Wall-clock CEILING (seconds) for a generate_document step. "
            "Dedicated to the document family (ADR-160): caps whatever "
            "timeout the planner requests without undercutting reality."
        ),
    )

    document_generation_max_source_chars: int = Field(
        default=DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
        ge=1000,
        le=500000,
        description=(
            "Maximum characters of source_data forwarded to the document "
            "LLM; the excess is truncated and the truncation is reported."
        ),
    )
```

- [ ] **Step 5: Register in the Settings MRO** — `src/core/config/__init__.py`: add `from src.core.config.document_generation import DocumentGenerationSettings` next to the other imports and insert `DocumentGenerationSettings,` on its own line right after `ImageGenerationSettings,` (line ~117).

- [ ] **Step 6: Run tests to verify they pass** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_document_generation_settings.py -v`. Expected: 3 PASS.

- [ ] **Step 7: Update env examples** — `.env.example`: append after the image generation block (~line 1878):

```
# ============================================================================
# [NN] DOCUMENT GENERATION — AI document creation (ADR-226)
# Config: src/core/config/document_generation.py
# ============================================================================

DOCUMENT_GENERATION_ENABLED=true                            # Enable AI document generation feature
DOCUMENT_GENERATION_RATE_LIMIT_CALLS=10                     # Max generate_document calls per user per window
DOCUMENT_GENERATION_RATE_LIMIT_WINDOW=300                   # Rate limit window in seconds
DOCUMENT_GENERATION_MAX_SOURCE_CHARS=60000                  # source_data cap forwarded to the document LLM
```

and add next to the image timeout pair (~line 1818):

```
DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS=120.0              # generate_document floor (internal LLM writes whole documents)
MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS=480.0          # document family ceiling (ADR-160)
```

Use the actual next section number `[NN]` by reading the last numbered section in the file. Mirror `DOCUMENT_GENERATION_ENABLED=true` into `.env.prod.example` in its feature-flag section. Note: the hygiene gate `task lint:hygiene` checks `.env.example` completeness — it will confirm.

- [ ] **Step 8: Verify** — Run: `task lint:backend` then `cd apps/api && .venv/Scripts/pytest tests/unit/core/config -v`. Expected: PASS, no MyPy errors.

---

### Task 2: LLM type `document_generation` (registry + defaults + factory Literal + admin i18n)

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py` (LLM_TYPES_REGISTRY after the `image_generation` entry ~line 531; LLM_DEFAULTS after the `image_generation` entry ~line 1132)
- Modify: `apps/api/src/infrastructure/llm/factory.py` (LLMType Literal at line 122)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (key `settings.admin.llmConfig.types.document_generation`)
- Test: `apps/api/tests/unit/domains/llm_config/test_document_generation_llm_type.py`

**Interfaces:**
- Produces: LLM type string `"document_generation"` usable with `get_llm("document_generation")` and `get_llm_config_for_agent(settings, "document_generation")` — consumed by Task 10.

- [ ] **Step 1: Write the failing test**

```python
"""The document_generation LLM slot exists and is coherently declared (ADR-226)."""

from src.domains.llm_config.constants import (
    CATEGORY_SPECIALIZED,
    LLM_DEFAULTS,
    LLM_TYPES_REGISTRY,
)
from src.infrastructure.llm.models import LLMModelKindEnum


def test_registered_with_chat_kind() -> None:
    meta = LLM_TYPES_REGISTRY["document_generation"]
    assert meta.category == CATEGORY_SPECIALIZED
    assert meta.required_kind == LLMModelKindEnum.chat


def test_defaults_present_and_generous_output() -> None:
    cfg = LLM_DEFAULTS["document_generation"]
    # Whole documents are written in one structured-output call.
    assert cfg.max_tokens >= 8000
    assert cfg.timeout_seconds >= 60.0
```

Note: `LLMModelKindEnum` import path — verify it via the existing import at the top of `llm_config/constants.py` and reuse that exact path.

- [ ] **Step 2: Run test to verify it fails** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_document_generation_llm_type.py -v`. Expected: FAIL (`KeyError: 'document_generation'`).

- [ ] **Step 3: Add the registry entry** in `LLM_TYPES_REGISTRY`, after `image_generation` (~line 531):

```python
    # AI Document Generation (ADR-226): writes whole structured documents
    # (csv/xlsx/docx/pptx/pdf/md/txt) in one structured-output call.
    "document_generation": LLMTypeMetadata(
        llm_type="document_generation",
        display_name="Document Generation",
        category=CATEGORY_SPECIALIZED,
        description_key="settings.admin.llmConfig.types.document_generation",
        required_capabilities=[],
        power_tier=POWER_TIER_HIGH,
    ),
```

and the defaults entry in `LLM_DEFAULTS` after `image_generation` (~line 1132):

```python
    "document_generation": LLMAgentConfig(
        provider="openai",
        model="gpt-4.1",
        temperature=0.2,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=16000,
        timeout_seconds=120.0,
    ),
```

The module-level sync assert (`LLM_TYPES_REGISTRY` keys == `LLM_DEFAULTS` keys, line ~1239) enforces the pairing at import.

- [ ] **Step 4: Extend the factory Literal** — `infrastructure/llm/factory.py:122`: add `"document_generation",` to the `LLMType` Literal (alphabetical/nearby grouping as the list dictates).

- [ ] **Step 5: Add the 6 admin description locales** — key `settings.admin.llmConfig.types.document_generation`, placed next to `types.image_generation` in each file:
  - en: `"Writes complete documents (CSV, Excel, Word, PowerPoint, PDF…) as structured output for the generate_document tool."`
  - fr: `"Rédige des documents complets (CSV, Excel, Word, PowerPoint, PDF…) en sortie structurée pour l'outil generate_document."`
  - de: `"Erstellt vollständige Dokumente (CSV, Excel, Word, PowerPoint, PDF…) als strukturierte Ausgabe für das Werkzeug generate_document."`
  - es: `"Redacta documentos completos (CSV, Excel, Word, PowerPoint, PDF…) como salida estructurada para la herramienta generate_document."`
  - it: `"Redige documenti completi (CSV, Excel, Word, PowerPoint, PDF…) come output strutturato per lo strumento generate_document."`
  - zh: `"以结构化输出为 generate_document 工具撰写完整文档（CSV、Excel、Word、PowerPoint、PDF 等）。"`

- [ ] **Step 6: Verify the default model has pricing rows** — the cost of a `document_generation` call is computed from the llm_pricing table; an absent model row means a silently ZERO tracked cost (a lie by omission). Run: `Grep "gpt-4.1" infrastructure/database/seeds` (or the actual seeds path for llm_pricing) and confirm the chosen default model has an active pricing row; if not, pick a default model that HAS one (e.g. the model used by the `response` slot) — do not add pricing rows in this task.

- [ ] **Step 7: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config -v`. Expected: PASS (including any pre-existing registry completeness tests). Then `task lint:i18n`. Expected: PASS.

---

### Task 3: `User.document_generation_enabled` column + migration + GDPR map + schemas

**Files:**
- Modify: `apps/api/src/domains/users/models.py` (after the image generation block, ~line 555)
- Create: `apps/api/alembic/versions/<generated>_user_document_generation_enabled.py`
- Modify: `apps/api/src/domains/users/schemas.py` (UserPreferencesUpdate ~line 85; UserPreferencesResponse ~line 110)
- Modify: `apps/api/src/domains/users/user_data_map.py` (~line 495, `_PREFERENCE` entry)
- Test: `apps/api/tests/unit/domains/users/test_document_generation_preference.py`

**Interfaces:**
- Produces: `User.document_generation_enabled: Mapped[bool]` — consumed by Task 11 (tool opt-in guard) and Task 16 (frontend toggle via the existing preferences endpoint).

- [ ] **Step 1: Write the failing test**

```python
"""User opt-in for document generation: model default, schema plumbing, GDPR map."""

from src.core.constants import DOCUMENT_GENERATION_ENABLED_DEFAULT
from src.domains.users.schemas import UserPreferencesResponse, UserPreferencesUpdate
from src.domains.users.user_data_map import USER_COLUMN_RULES  # use the actual exported name


def test_model_column_declared() -> None:
    from src.domains.users.models import User

    col = User.__table__.columns["document_generation_enabled"]
    assert col.nullable is False
    assert col.server_default is not None


def test_preferences_update_accepts_flag() -> None:
    upd = UserPreferencesUpdate(document_generation_enabled=False)
    assert upd.document_generation_enabled is False


def test_preferences_response_default_matches_constant() -> None:
    resp = UserPreferencesResponse()
    assert resp.document_generation_enabled is DOCUMENT_GENERATION_ENABLED_DEFAULT


def test_gdpr_map_classifies_as_preference() -> None:
    assert "document_generation_enabled" in USER_COLUMN_RULES
```

Before writing: open `user_data_map.py` and use the ACTUAL dict name holding the `"image_generation_enabled": _PREFERENCE` entry (line 492) in the test import; if a completeness guard test already fails on the missing entry, that guard replaces `test_gdpr_map_classifies_as_preference`.

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`KeyError`/`AttributeError`/validation error).

- [ ] **Step 3: Add the model column** (import `DOCUMENT_GENERATION_ENABLED_DEFAULT` at top with the image constants):

```python
    # Document Generation preference (ADR-226)
    document_generation_enabled: Mapped[bool] = mapped_column(
        default=DOCUMENT_GENERATION_ENABLED_DEFAULT,
        nullable=False,
        server_default="true",
        comment="User opt-in for AI document generation feature.",
    )
```

- [ ] **Step 4: Write the migration** — first run `cd apps/api && .venv/Scripts/alembic heads` (must print exactly ONE head; use it as `down_revision`). Create the revision file following the repo's filename convention (`YYYY_MM_DD_HHMM-<rev>_user_document_generation_enabled.py`):

```python
"""Add users.document_generation_enabled (ADR-226).

Revision ID: <new-rev>
Revises: <current-head>
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "<new-rev>"
down_revision = "<current-head>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "document_generation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User opt-in for AI document generation feature.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "document_generation_enabled")
```

- [ ] **Step 5: Wire schemas + GDPR map** — `schemas.py` UserPreferencesUpdate (after `image_generation_output_format`, ~line 85):

```python
    # Document Generation preference (ADR-226)
    document_generation_enabled: bool | None = Field(
        None, description="Enable AI document generation feature"
    )
```

UserPreferencesResponse (~line 111):

```python
    # Document Generation preference (ADR-226)
    document_generation_enabled: bool = Field(
        default=True, description="AI document generation enabled"
    )
```

`user_data_map.py` (next to line 492): `"document_generation_enabled": _PREFERENCE,`

- [ ] **Step 6: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/users/test_document_generation_preference.py -v`. Expected: PASS. Also run any existing user_data_map completeness guard: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/users -v`. Expected: PASS.

- [ ] **Step 7: Migration replay check** — Run: `task db:migrate:replay-check`. Expected: PASS, single head. (Requires the disposable-DB target only — never the dev DB.)

---

### Task 4: Platform capability `DOCUMENT_GENERATION`

**Files:**
- Modify: `apps/api/src/domains/system_settings/models.py` (~line 65: `CAPABILITY_DOCUMENT_GENERATION_ENABLED = "capability_document_generation_enabled"`)
- Modify: `apps/api/src/domains/feature_switches/registry.py` (enum ~line 63 + `CAPABILITY_SPECS` entry after IMAGE_GENERATION ~line 126)
- Test: `apps/api/tests/unit/domains/feature_switches/test_document_generation_capability.py`

**Interfaces:**
- Produces: `PlatformCapability.DOCUMENT_GENERATION` with `agents=("document_generation_agent",)` — the runtime admin switch filters the catalogue agent, mirroring IMAGE_GENERATION.

- [ ] **Step 1: Write the failing test**

```python
"""DOCUMENT_GENERATION is an administrable capability wired to the env flag (ADR-226)."""

from src.core.config import Settings
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability


def test_capability_spec_registered() -> None:
    spec = CAPABILITY_SPECS[PlatformCapability.DOCUMENT_GENERATION]
    assert spec.env_flag == "document_generation_enabled"
    assert "document_generation_agent" in (spec.agents or ())


def test_env_flag_is_a_real_setting() -> None:
    # The spec's env_flag must resolve on Settings — a typo here silently
    # disconnects the admin switch from the runtime flag.
    assert CAPABILITY_SPECS[PlatformCapability.DOCUMENT_GENERATION].env_flag in Settings.model_fields
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`AttributeError: DOCUMENT_GENERATION`).

- [ ] **Step 3: Implement** — add enum member `DOCUMENT_GENERATION = "document_generation"` after `IMAGE_GENERATION` (line 63); add the `SystemSettingKey` member; add the spec entry after the IMAGE_GENERATION spec (~line 126), mirroring the TTS pattern for enforcement (no route of its own):

```python
    PlatformCapability.DOCUMENT_GENERATION: CapabilitySpec(
        capability=PlatformCapability.DOCUMENT_GENERATION,
        env_flag="document_generation_enabled",
        setting_key=SystemSettingKey.CAPABILITY_DOCUMENT_GENERATION_ENABLED,
        agents=("document_generation_agent",),
        # No route of its own: the gate lives at the generate_document tool
        # entry (settings flag + user opt-in), like TTS's synthesis chokepoint.
        service_enforced=True,
    ),
```

Before writing, read the `CapabilitySpec` dataclass at the top of `registry.py` and keep only the fields it actually declares (drop `service_enforced` if the field does not exist; the mirror is the field set of the TTS entry).

- [ ] **Step 4: Frontend admin labels check** — Run: `Grep "capability_image_generation" apps/web` and `Grep "IMAGE_GENERATION" apps/web/locales/en/translation.json`. If the admin capabilities UI resolves per-capability labels from locale keys, add the matching `document_generation` label to all 6 locales in the same namespace; if no match (expected — the 2026-08-17 scan found none under `apps/web/src/**/admin/**`), nothing to do.

- [ ] **Step 5: Run tests** — `cd apps/api && .venv/Scripts/pytest tests/unit/domains/feature_switches -v`. Expected: PASS (new + any pre-existing completeness guards over CAPABILITY_SPECS).

---

### Task 5: Document content schemas

**Files:**
- Create: `apps/api/src/domains/document_generation/__init__.py` (empty docstring module)
- Create: `apps/api/src/domains/document_generation/schemas.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_schemas.py` (+ empty `__init__.py` files mirroring source)

**Interfaces:**
- Produces (consumed by Tasks 6-8, 10, 11):
  - `DocumentType(str, Enum)` with members `CSV, XLSX, DOCX, PPTX, PDF, MD, TXT` (values lowercase).
  - `TableSheet(name: str, headers: list[str], rows: list[list[str]])`
  - `TabularContent(filename_stem: str, title: str, sheets: list[TableSheet])`
  - `SectionBlock(kind: Literal["heading","paragraph","bullets","table"], level: int, text: str, items: list[str], table: TableSheet | None)`
  - `SectionedContent(filename_stem: str, title: str, blocks: list[SectionBlock])`
  - `Slide(title: str, bullets: list[str], notes: str)`
  - `SlideContent(filename_stem: str, title: str, slides: list[Slide])`
  - `DocumentContent = TabularContent | SectionedContent | SlideContent`
  - `SCHEMA_BY_DOC_TYPE: dict[DocumentType, type[TabularContent] | type[SectionedContent] | type[SlideContent]]`

- [ ] **Step 1: Write the failing test**

```python
"""Content schemas: per-type schema selection is total; models validate (ADR-226)."""

import pytest
from pydantic import ValidationError

from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentType,
    SectionBlock,
    SectionedContent,
    SlideContent,
    TableSheet,
    TabularContent,
)


def test_schema_map_is_total() -> None:
    # Boot-time completeness doctrine (ADR-085): every DocumentType maps.
    assert set(SCHEMA_BY_DOC_TYPE) == set(DocumentType)


def test_tabular_for_spreadsheets_sectioned_for_text_slides_for_pptx() -> None:
    assert SCHEMA_BY_DOC_TYPE[DocumentType.CSV] is TabularContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.XLSX] is TabularContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.DOCX] is SectionedContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.PDF] is SectionedContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.MD] is SectionedContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.TXT] is SectionedContent
    assert SCHEMA_BY_DOC_TYPE[DocumentType.PPTX] is SlideContent


def test_tabular_requires_at_least_one_sheet() -> None:
    with pytest.raises(ValidationError):
        TabularContent(filename_stem="x", title="t", sheets=[])


def test_section_block_defaults() -> None:
    block = SectionBlock(kind="paragraph", text="hello")
    assert block.level == 2
    assert block.items == []
    assert block.table is None
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (import error).

- [ ] **Step 3: Implement `schemas.py`**

```python
"""Structured content models produced by the document_generation LLM (ADR-226).

One schema family per output shape — the service selects the schema by
``doc_type`` BEFORE the LLM call, so each call is a plain (strict-compatible)
Pydantic schema rather than a discriminated union:

- Tabular (csv, xlsx): sheets of headers + string rows.
- Sectioned (docx, pdf, md, txt): a tree of heading/paragraph/bullets/table blocks.
- Slides (pptx): title + bullet slides with optional speaker notes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Supported output formats for generate_document."""

    CSV = "csv"
    XLSX = "xlsx"
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    MD = "md"
    TXT = "txt"


class TableSheet(BaseModel):
    """A single table: one CSV file, one XLSX worksheet, or an embedded table."""

    name: str = Field(description="Sheet/table name (short, human readable).")
    headers: list[str] = Field(description="Column headers, in order.")
    rows: list[list[str]] = Field(
        description="Data rows; every cell as a string, aligned with headers."
    )


class TabularContent(BaseModel):
    """Content for csv/xlsx outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (used as metadata).")
    sheets: list[TableSheet] = Field(
        min_length=1,
        description="Worksheets; csv output uses ONLY the first sheet.",
    )


class SectionBlock(BaseModel):
    """One block of a sectioned document, rendered in order."""

    kind: Literal["heading", "paragraph", "bullets", "table"] = Field(
        description="Block type."
    )
    level: int = Field(default=2, ge=1, le=4, description="Heading level (headings only).")
    text: str = Field(default="", description="Text for heading/paragraph blocks.")
    items: list[str] = Field(default_factory=list, description="Bullet items (bullets only).")
    table: TableSheet | None = Field(default=None, description="Table payload (table only).")


class SectionedContent(BaseModel):
    """Content for docx/pdf/md/txt outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (rendered as the top heading).")
    blocks: list[SectionBlock] = Field(min_length=1, description="Ordered content blocks.")


class Slide(BaseModel):
    """A single presentation slide."""

    title: str = Field(description="Slide title.")
    bullets: list[str] = Field(default_factory=list, description="Bullet points.")
    notes: str = Field(default="", description="Optional speaker notes.")


class SlideContent(BaseModel):
    """Content for pptx output."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Presentation title (first slide).")
    slides: list[Slide] = Field(min_length=1, description="Ordered slides.")


DocumentContent = TabularContent | SectionedContent | SlideContent

SCHEMA_BY_DOC_TYPE: dict[
    DocumentType, type[TabularContent] | type[SectionedContent] | type[SlideContent]
] = {
    DocumentType.CSV: TabularContent,
    DocumentType.XLSX: TabularContent,
    DocumentType.DOCX: SectionedContent,
    DocumentType.PDF: SectionedContent,
    DocumentType.MD: SectionedContent,
    DocumentType.TXT: SectionedContent,
    DocumentType.PPTX: SlideContent,
}

# Boot-time completeness (ADR-085): refuse to import with a partial map.
assert set(SCHEMA_BY_DOC_TYPE) == set(DocumentType), (
    "SCHEMA_BY_DOC_TYPE must cover every DocumentType"
)
```

- [ ] **Step 4: Run tests** — Expected: all PASS.

---

### Task 6: Sanitization helpers + text renderers (csv, md, txt)

**Files:**
- Create: `apps/api/src/domains/document_generation/sanitize.py`
- Create: `apps/api/src/domains/document_generation/renderers.py` (single module for the 7 render functions + registry — they share helpers and stay well under the SLOC cap)
- Test: `apps/api/tests/unit/domains/document_generation/test_sanitize.py`, `apps/api/tests/unit/domains/document_generation/test_renderers_text.py`

**Interfaces:**
- Produces (consumed by Tasks 7, 8, 10):
  - `neutralize_formula(value: str) -> str`
  - `sanitize_filename_stem(stem: str, fallback: str = "document") -> str`
  - `render_document(doc_type: DocumentType, content: DocumentContent) -> bytes` (dispatch; raises `ValueError` on content/schema mismatch)
  - `DOCUMENT_MIME_TYPES: dict[DocumentType, str]`, `DOCUMENT_EXTENSIONS: dict[DocumentType, str]`

- [ ] **Step 1: Write the failing tests**

`test_sanitize.py`:

```python
"""Formula-injection neutralization and filename sanitization (ADR-226).

The openpyxl probe (2026-08-17) proved a leading '=' string is stored as a
FORMULA (data_type 'f'): neutralization is a correctness requirement.
"""

import pytest

from src.domains.document_generation.sanitize import (
    neutralize_formula,
    sanitize_filename_stem,
)


@pytest.mark.parametrize("raw", ["=1+2", "+A1", "-2+3", "@cmd", "\tx", "\rx"])
def test_dangerous_prefixes_neutralized(raw: str) -> None:
    assert neutralize_formula(raw) == f"'{raw}"


@pytest.mark.parametrize("raw", ["hello", "12", "a=b", "", "négatif -5 après texte"])
def test_safe_values_untouched(raw: str) -> None:
    assert neutralize_formula(raw) == raw


@pytest.mark.parametrize("raw", ["-5", "-5.2", "-0.001", "+3", "+3.14", "-1e6"])
def test_plain_numbers_are_not_formulas(raw: str) -> None:
    # A legitimate negative/signed NUMBER must never be defaced: '-5.2 in a
    # data column is a rendering defect. Only spreadsheet-ACTIVE strings
    # (containing operators/references beyond a plain numeric literal) are
    # neutralized.
    assert neutralize_formula(raw) == raw


def test_filename_strips_separators_and_controls() -> None:
    assert sanitize_filename_stem("../..\\évil\x00name") == "évil_name" or (
        "/" not in sanitize_filename_stem("../..\\évil\x00name")
        and "\\" not in sanitize_filename_stem("../..\\évil\x00name")
    )


def test_filename_empty_falls_back() -> None:
    assert sanitize_filename_stem("   ") == "document"


def test_filename_capped_at_80() -> None:
    assert len(sanitize_filename_stem("x" * 300)) <= 80
```

`test_renderers_text.py`:

```python
"""Text-family renderers: csv (BOM + neutralization), md, txt (ADR-226)."""

import csv
import io

from src.domains.document_generation.renderers import (
    DOCUMENT_EXTENSIONS,
    DOCUMENT_MIME_TYPES,
    render_document,
)
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    TableSheet,
    TabularContent,
)


def _tabular() -> TabularContent:
    return TabularContent(
        filename_stem="llm-models",
        title="LLM models",
        sheets=[
            TableSheet(
                name="Models",
                headers=["model", "provider"],
                rows=[["Fable 5", "Anthropic"], ["=HYPERLINK(1)", "évil"]],
            )
        ],
    )


def test_csv_has_bom_and_neutralized_formula() -> None:
    data = render_document(DocumentType.CSV, _tabular())
    assert data[:3] == b"\xef\xbb\xbf"  # Excel-compatible utf-8-sig
    text = data.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0] == ["model", "provider"]
    assert reader[2][0] == "'=HYPERLINK(1)"  # neutralized, quote preserved by csv round-trip


def _sectioned() -> SectionedContent:
    return SectionedContent(
        filename_stem="alsace",
        title="L'Alsace",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Géographie"),
            SectionBlock(kind="paragraph", text="Plaine du Rhin."),
            SectionBlock(kind="bullets", items=["Strasbourg", "Colmar"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="Villes", headers=["ville"], rows=[["Mulhouse"]]),
            ),
        ],
    )


def test_md_renders_every_block_kind() -> None:
    text = render_document(DocumentType.MD, _sectioned()).decode("utf-8")
    assert "# L'Alsace" in text
    assert "## Géographie" in text
    assert "- Strasbourg" in text
    assert "| ville |" in text


def test_txt_is_plain_and_complete() -> None:
    text = render_document(DocumentType.TXT, _sectioned()).decode("utf-8")
    for fragment in ("L'Alsace", "Géographie", "Plaine du Rhin.", "Strasbourg", "Mulhouse"):
        assert fragment in text
    assert "|" not in text.splitlines()[0]  # no markdown table syntax leak in the title


def test_mime_and_extension_maps_are_total() -> None:
    assert set(DOCUMENT_MIME_TYPES) == set(DocumentType)
    assert set(DOCUMENT_EXTENSIONS) == set(DocumentType)
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (import errors).

- [ ] **Step 3: Implement `sanitize.py`**

```python
"""Sanitization helpers for generated documents (ADR-226).

``neutralize_formula`` closes the spreadsheet formula-injection surface proven
by the 2026-08-17 probe: openpyxl stores any string starting with ``=`` as a
real formula, and Excel/Calc also evaluate ``+``/``-``/``@`` starters from CSV.
``sanitize_filename_stem`` keeps human-meaningful names (accents allowed —
Starlette emits RFC 5987 ``filename*``) while stripping anything path-shaped.
"""

from __future__ import annotations

import re

_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")

# A plain signed numeric literal ("-5", "+3.14", "-1e6") is data, not a
# formula: neutralizing it would deface every negative number in a table.
_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+([.,]\d+)?|[.,]\d+)([eE][+-]?\d+)?$")

# Path separators, control chars, characters invalid on Windows filesystems.
_FILENAME_FORBIDDEN = re.compile(r'[\\/\x00-\x1f<>:"|?*]+')
_WHITESPACE_RUN = re.compile(r"\s+")

FILENAME_STEM_MAX_LENGTH = 80


def neutralize_formula(value: str) -> str:
    """Prefix spreadsheet-active values with a quote so they stay text.

    Plain signed numbers are exempt — they are legitimate data and carry no
    formula semantics; everything else starting with an active prefix
    (``= + - @`` and tab/CR) is prefixed with ``'`` (OWASP CSV-injection
    mitigation; the quote is visible on those rare values, an accepted
    trade-off for a uniform, auditable rule).

    Args:
        value: Raw cell value.

    Returns:
        The value, prefixed with ``'`` when it would be parsed as a formula.
    """
    if value.startswith(_FORMULA_PREFIXES) and not _PLAIN_NUMBER.match(value):
        return f"'{value}"
    return value


def sanitize_filename_stem(stem: str, fallback: str = "document") -> str:
    """Make an LLM- or user-suggested filename stem safe for downloads.

    Args:
        stem: Suggested filename without extension.
        fallback: Stem used when nothing survives sanitization.

    Returns:
        A non-empty stem with no separators/control characters, no leading
        dots, collapsed whitespace, capped at ``FILENAME_STEM_MAX_LENGTH``.
    """
    cleaned = _FILENAME_FORBIDDEN.sub("_", stem)
    cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip().lstrip(".").strip()
    if not cleaned:
        return fallback
    return cleaned[:FILENAME_STEM_MAX_LENGTH].rstrip(" .") or fallback
```

- [ ] **Step 4: Implement the text part of `renderers.py`** (office/pdf functions land in Tasks 7-8; create the module now with the registry scaffold so the dispatch signature is final):

```python
"""Pure renderers: structured content -> document bytes (ADR-226).

Every renderer is a pure function (content in, bytes out) so it is unit-tested
without I/O; CPU-bound rendering is offloaded with ``asyncio.to_thread`` by the
CALLER (service layer). The registry is completeness-asserted at import.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable

from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import (
    DocumentContent,
    DocumentType,
    SectionBlock,
    SectionedContent,
    SlideContent,
    TableSheet,
    TabularContent,
)

DOCUMENT_MIME_TYPES: dict[DocumentType, str] = {
    DocumentType.CSV: "text/csv",
    DocumentType.XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    DocumentType.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    DocumentType.PPTX: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    DocumentType.PDF: "application/pdf",
    DocumentType.MD: "text/markdown",
    DocumentType.TXT: "text/plain",
}

DOCUMENT_EXTENSIONS: dict[DocumentType, str] = {
    DocumentType.CSV: "csv",
    DocumentType.XLSX: "xlsx",
    DocumentType.DOCX: "docx",
    DocumentType.PPTX: "pptx",
    DocumentType.PDF: "pdf",
    DocumentType.MD: "md",
    DocumentType.TXT: "txt",
}


def _render_csv(content: DocumentContent) -> bytes:
    if not isinstance(content, TabularContent):
        raise ValueError("csv rendering requires TabularContent")
    sheet = content.sheets[0]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([neutralize_formula(h) for h in sheet.headers])
    for row in sheet.rows:
        writer.writerow([neutralize_formula(cell) for cell in row])
    # utf-8-sig: Excel needs the BOM to detect UTF-8 (probe 2026-08-17).
    return buf.getvalue().encode("utf-8-sig")


def _md_table(table: TableSheet) -> list[str]:
    header = "| " + " | ".join(table.headers) + " |"
    rule = "| " + " | ".join("---" for _ in table.headers) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in table.rows]
    return [header, rule, *rows]


def _render_md(content: DocumentContent) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("md rendering requires SectionedContent")
    lines: list[str] = [f"# {content.title}", ""]
    for block in content.blocks:
        lines.extend(_md_block(block))
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _md_block(block: SectionBlock) -> list[str]:
    if block.kind == "heading":
        # The document title owns "#"; content headings start at "##" even
        # when the LLM says level 1 — same shift the PDF renderer applies.
        return [f"{'#' * max(block.level, 2)} {block.text}"]
    if block.kind == "paragraph":
        return [block.text]
    if block.kind == "bullets":
        return [f"- {item}" for item in block.items]
    if block.table is not None:
        return _md_table(block.table)
    return []


def _render_txt(content: DocumentContent) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("txt rendering requires SectionedContent")
    lines: list[str] = [content.title, "=" * len(content.title), ""]
    for block in content.blocks:
        if block.kind == "heading":
            lines.extend([block.text, "-" * len(block.text)])
        elif block.kind == "paragraph":
            lines.append(block.text)
        elif block.kind == "bullets":
            lines.extend(f"  * {item}" for item in block.items)
        elif block.table is not None:
            lines.append(" / ".join(block.table.headers))
            lines.extend(" / ".join(row) for row in block.table.rows)
        lines.append("")
    return "\n".join(lines).encode("utf-8")


RENDERERS: dict[DocumentType, Callable[[DocumentContent], bytes]] = {
    DocumentType.CSV: _render_csv,
    DocumentType.MD: _render_md,
    DocumentType.TXT: _render_txt,
    # xlsx/docx/pptx/pdf registered by their implementation blocks below
    # (Tasks 7-8 of the implementation plan); the assert keeps the map honest.
}


def render_document(doc_type: DocumentType, content: DocumentContent) -> bytes:
    """Render structured content into final document bytes.

    Args:
        doc_type: Target format.
        content: Validated content matching ``SCHEMA_BY_DOC_TYPE[doc_type]``.

    Returns:
        The rendered file bytes.

    Raises:
        ValueError: When the content model does not match the format family.
    """
    return RENDERERS[doc_type](content)
```

**Note:** the final completeness assert `assert set(RENDERERS) == set(DocumentType)` is added at the END of the module in Task 8 (once all 7 renderers exist). Until then, `test_mime_and_extension_maps_are_total` covers the two metadata maps only.

- [ ] **Step 5: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation -v`. Expected: PASS (`test_sanitize.py` + `test_renderers_text.py`).

---

### Task 7: Office renderers (xlsx, docx, pptx)

**Files:**
- Modify: `apps/api/src/domains/document_generation/renderers.py` (add `_render_xlsx`, `_render_docx`, `_render_pptx` + registry entries)
- Test: `apps/api/tests/unit/domains/document_generation/test_renderers_office.py`

**Interfaces:**
- Consumes: Task 5 schemas, Task 6 helpers. Round-trip oracles: `openpyxl.load_workbook`, `docx.Document(io.BytesIO(...))`, `pptx.Presentation(io.BytesIO(...))` — the same libraries the RAG extractors already use.

- [ ] **Step 1: Write the failing tests**

```python
"""Office renderers round-trip through their own readers (ADR-226)."""

import io

import docx
import openpyxl
import pptx

from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
    TabularContent,
)


def test_xlsx_round_trip_and_formula_neutralized() -> None:
    content = TabularContent(
        filename_stem="data",
        title="Data",
        sheets=[
            TableSheet(name="Feuille 1", headers=["a", "b"], rows=[["1", "=2+2"]]),
            TableSheet(name="Feuille 2", headers=["c"], rows=[["x"]]),
        ],
    )
    data = render_document(DocumentType.XLSX, content)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Feuille 1", "Feuille 2"]
    ws = wb["Feuille 1"]
    assert ws["A1"].value == "a"
    assert ws["B2"].value == "'=2+2"
    assert ws["B2"].data_type != "f"  # the probe-proven injection stays closed


def test_xlsx_negative_numbers_survive_untouched() -> None:
    content = TabularContent(
        filename_stem="deltas",
        title="Deltas",
        sheets=[TableSheet(name="D", headers=["delta"], rows=[["-5.2"]])],
    )
    wb = openpyxl.load_workbook(io.BytesIO(render_document(DocumentType.XLSX, content)))
    assert wb.active["A2"].value == "-5.2"


def test_xlsx_sheet_titles_sanitized_and_deduplicated() -> None:
    # openpyxl REJECTS []:*?/\ in titles; the LLM can produce both invalid
    # characters and duplicate names — the renderer must survive both.
    content = TabularContent(
        filename_stem="data",
        title="Data",
        sheets=[
            TableSheet(name="Q1/Q2 [draft]", headers=["a"], rows=[["1"]]),
            TableSheet(name="Q1/Q2 [draft]", headers=["b"], rows=[["2"]]),
            TableSheet(name="", headers=["c"], rows=[["3"]]),
        ],
    )
    wb = openpyxl.load_workbook(io.BytesIO(render_document(DocumentType.XLSX, content)))
    assert len(wb.sheetnames) == 3
    assert len(set(wb.sheetnames)) == 3  # deduplicated
    for title in wb.sheetnames:
        assert not set(title) & set('[]:*?/\\')  # sanitized


def test_docx_round_trip_blocks() -> None:
    content = SectionedContent(
        filename_stem="rapport",
        title="Rapport",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Partie 1"),
            SectionBlock(kind="paragraph", text="Texte accentué éàü."),
            SectionBlock(kind="bullets", items=["un", "deux"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="T", headers=["k"], rows=[["v"]]),
            ),
        ],
    )
    data = render_document(DocumentType.DOCX, content)
    d = docx.Document(io.BytesIO(data))
    texts = [p.text for p in d.paragraphs]
    assert "Rapport" in texts
    assert "Partie 1" in texts
    assert "Texte accentué éàü." in texts
    assert d.tables and d.tables[0].cell(1, 0).text == "v"


def test_pptx_round_trip_slides_and_notes() -> None:
    content = SlideContent(
        filename_stem="alsace",
        title="L'Alsace",
        slides=[Slide(title="Géographie", bullets=["Rhin", "Vosges"], notes="parler lentement")],
    )
    data = render_document(DocumentType.PPTX, content)
    p = pptx.Presentation(io.BytesIO(data))
    assert len(p.slides) == 2  # title slide + 1 content slide
    all_text = [
        run.text
        for slide in p.slides
        for shape in slide.shapes
        if shape.has_text_frame
        for para in shape.text_frame.paragraphs
        for run in para.runs
    ]
    assert "L'Alsace" in all_text
    assert "Géographie" in all_text
    assert "Rhin" in all_text
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`KeyError: DocumentType.XLSX` from the registry).

- [ ] **Step 3: Implement the three renderers** (append to `renderers.py`; local imports keep module import light, mirroring the codebase's lazy-import style for heavy libs):

```python
_XLSX_TITLE_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")  # openpyxl rejects these


def _xlsx_sheet_title(name: str, index: int, used: set[str]) -> str:
    """Sanitize an LLM-suggested worksheet title for openpyxl.

    Strips the characters openpyxl rejects, enforces Excel's 31-char limit,
    falls back to ``Sheet{n}`` when empty, deduplicates with a numeric suffix.
    """
    cleaned = _XLSX_TITLE_FORBIDDEN.sub("_", name).strip()[:31] or f"Sheet{index + 1}"
    candidate = cleaned
    suffix = 2
    while candidate in used:
        tail = f" {suffix}"
        candidate = f"{cleaned[: 31 - len(tail)]}{tail}"
        suffix += 1
    used.add(candidate)
    return candidate


def _render_xlsx(content: DocumentContent) -> bytes:
    if not isinstance(content, TabularContent):
        raise ValueError("xlsx rendering requires TabularContent")
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    default_sheet = wb.active
    used_titles: set[str] = set()
    for index, sheet in enumerate(content.sheets):
        ws = default_sheet if index == 0 else wb.create_sheet()
        ws.title = _xlsx_sheet_title(sheet.name, index, used_titles)
        ws.append([neutralize_formula(h) for h in sheet.headers])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in sheet.rows:
            ws.append([neutralize_formula(value) for value in row])
        for col_index, header in enumerate(sheet.headers, start=1):
            widths = [len(header)] + [
                len(row[col_index - 1]) for row in sheet.rows if len(row) >= col_index
            ]
            ws.column_dimensions[get_column_letter(col_index)].width = min(
                max(widths) + 2, 60
            )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _render_docx(content: DocumentContent) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("docx rendering requires SectionedContent")
    import docx

    document = docx.Document()
    document.add_heading(content.title, level=1)
    for block in content.blocks:
        if block.kind == "heading":
            document.add_heading(block.text, level=min(block.level, 4))
        elif block.kind == "paragraph":
            document.add_paragraph(block.text)
        elif block.kind == "bullets":
            for item in block.items:
                document.add_paragraph(item, style="List Bullet")
        elif block.table is not None:
            table = document.add_table(
                rows=len(block.table.rows) + 1, cols=len(block.table.headers)
            )
            table.style = "Light Grid Accent 1"
            for col, header in enumerate(block.table.headers):
                table.cell(0, col).text = header
            for row_index, row in enumerate(block.table.rows, start=1):
                for col, value in enumerate(row[: len(block.table.headers)]):
                    table.cell(row_index, col).text = value
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _render_pptx(content: DocumentContent) -> bytes:
    if not isinstance(content, SlideContent):
        raise ValueError("pptx rendering requires SlideContent")
    import pptx

    presentation = pptx.Presentation()
    title_slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    title_slide.shapes.title.text = content.title
    for slide_spec in content.slides:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = slide_spec.title
        body = slide.placeholders[1].text_frame
        for index, bullet in enumerate(slide_spec.bullets):
            paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
            paragraph.text = bullet
        if slide_spec.notes:
            slide.notes_slide.notes_text_frame.text = slide_spec.notes
    buf = io.BytesIO()
    presentation.save(buf)
    return buf.getvalue()


RENDERERS[DocumentType.XLSX] = _render_xlsx
RENDERERS[DocumentType.DOCX] = _render_docx
RENDERERS[DocumentType.PPTX] = _render_pptx
```

- [ ] **Step 4: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation -v`. Expected: PASS.

---

### Task 8: PDF renderer (PyMuPDF Story) + registry completeness assert

**Files:**
- Modify: `apps/api/src/domains/document_generation/renderers.py` (add `_render_pdf`, registry entry, final completeness assert)
- Test: `apps/api/tests/unit/domains/document_generation/test_renderer_pdf.py`

**Interfaces:**
- Consumes: the Story API proven by the 2026-08-17 probe (PyMuPDF 1.27.2). Oracle: `fitz.open(stream=...)` text extraction (same lib as RAG PDF extraction).

- [ ] **Step 1: Write the failing test**

```python
"""PDF renderer: HTML->Story->paged PDF; text extraction is the oracle (ADR-226)."""

import fitz

from src.domains.document_generation.renderers import RENDERERS, render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    TableSheet,
)


def _content() -> SectionedContent:
    return SectionedContent(
        filename_stem="alsace",
        title="Rapport Alsace",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Villes"),
            SectionBlock(kind="paragraph", text="Texte avec accents éàü & <balise>."),
            SectionBlock(kind="bullets", items=["Strasbourg", "Colmar"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="V", headers=["ville"], rows=[["Mulhouse"]]),
            ),
        ],
    )


def test_pdf_round_trip_text() -> None:
    data = render_document(DocumentType.PDF, _content())
    doc = fitz.open(stream=data, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()
    for fragment in (
        "Rapport Alsace",
        "Villes",
        "éàü & <balise>",  # html.escape round-trips literally in extracted text
        "Strasbourg",
        "Mulhouse",
    ):
        assert fragment in text


def test_registry_is_complete() -> None:
    assert set(RENDERERS) == set(DocumentType)
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`KeyError: DocumentType.PDF`).

- [ ] **Step 3: Implement** (append to `renderers.py`):

```python
def _pdf_html(content: SectionedContent) -> str:
    from html import escape

    parts: list[str] = [f"<h1>{escape(content.title)}</h1>"]
    for block in content.blocks:
        if block.kind == "heading":
            level = min(block.level + 1, 5)
            parts.append(f"<h{level}>{escape(block.text)}</h{level}>")
        elif block.kind == "paragraph":
            parts.append(f"<p>{escape(block.text)}</p>")
        elif block.kind == "bullets":
            items = "".join(f"<li>{escape(item)}</li>" for item in block.items)
            parts.append(f"<ul>{items}</ul>")
        elif block.table is not None:
            head = "".join(f"<th>{escape(h)}</th>" for h in block.table.headers)
            body = "".join(
                "<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row) + "</tr>"
                for row in block.table.rows
            )
            parts.append(f"<table><tr>{head}</tr>{body}</table>")
    return "".join(parts)


def _render_pdf(content: DocumentContent) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("pdf rendering requires SectionedContent")
    import fitz

    story = fitz.Story(html=_pdf_html(content))
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (36, 36, -36, -36)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buf.getvalue()


RENDERERS[DocumentType.PDF] = _render_pdf

# Boot-time completeness (ADR-085): a partial renderer map refuses to import.
assert set(RENDERERS) == set(DocumentType), "RENDERERS must cover every DocumentType"
```

- [ ] **Step 4: Run all domain tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation -v`. Expected: PASS. Check module size: `cd apps/api && .venv/Scripts/python ../../scripts/audit/measure_sloc.py src/domains/document_generation/renderers.py` (adjust invocation to the script's CLI). Expected: < 600 logical SLOC.

---

### Task 9: Pending document store

**Files:**
- Create: `apps/api/src/domains/document_generation/document_store.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_document_store.py`

**Interfaces:**
- Produces (consumed by Tasks 10, 13):
  - `PendingDocument(url: str, filename: str, doc_type: str, size_bytes: int, expires_at: str | None)`
  - `store_pending_document(conversation_id: str, document: PendingDocument) -> None`
  - `peek_pending_documents(conversation_id: str) -> list[PendingDocument]`
  - `get_and_clear_pending_documents(conversation_id: str) -> list[PendingDocument]`
  - `to_wire_metadata(documents: Sequence[PendingDocument]) -> list[dict[str, str | int | None]]`

- [ ] **Step 1: Write the failing test**

```python
"""Pending document store: thread-safe FIFO per conversation, one wire shape (ADR-226)."""

from src.domains.document_generation.document_store import (
    PendingDocument,
    get_and_clear_pending_documents,
    peek_pending_documents,
    store_pending_document,
    to_wire_metadata,
)


def _doc(name: str = "a.csv") -> PendingDocument:
    return PendingDocument(
        url="/api/v1/attachments/x",
        filename=name,
        doc_type="csv",
        size_bytes=42,
        expires_at="2026-08-19T00:00:00+00:00",
    )


def test_peek_does_not_clear_and_clear_clears() -> None:
    store_pending_document("conv1", _doc())
    store_pending_document("conv1", _doc("b.pdf"))
    assert [d.filename for d in peek_pending_documents("conv1")] == ["a.csv", "b.pdf"]
    cleared = get_and_clear_pending_documents("conv1")
    assert len(cleared) == 2
    assert peek_pending_documents("conv1") == []
    assert get_and_clear_pending_documents("conv1") == []


def test_wire_metadata_shape() -> None:
    wire = to_wire_metadata([_doc()])
    assert wire == [
        {
            "url": "/api/v1/attachments/x",
            "filename": "a.csv",
            "doc_type": "csv",
            "size_bytes": 42,
            "expires_at": "2026-08-19T00:00:00+00:00",
        }
    ]


def test_conversations_are_isolated() -> None:
    store_pending_document("conv-a", _doc())
    assert peek_pending_documents("conv-b") == []
    get_and_clear_pending_documents("conv-a")
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (import error).

- [ ] **Step 3: Implement** — exact structural mirror of `image_store.py` (module docstring explaining SSE injection + archive peek; `threading.Lock`; INFO logs `pending_document_stored` / `pending_documents_retrieved` with counts and IDs only — the filename is user content, log it at DEBUG):

```python
"""Module-level store for generated document metadata pending delivery (ADR-226).

Mirror of ``image_generation/image_store.py``: the generate_document tool saves
the file via AttachmentRepository and stores the attachment URL here; the
streaming layer peeks it for message-metadata archiving and clears it into the
SSE done chunk. ``to_wire_metadata`` is the SINGLE serializer for both sites —
the frontend maps both through one ``GeneratedDocument`` type.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PendingDocument:
    """A generated document pending SSE injection.

    Attributes:
        url: Relative attachment URL (``/api/v1/attachments/{id}``).
        filename: Human-meaningful download filename (sanitized stem + ext).
        doc_type: DocumentType value ("csv", "xlsx", ...).
        size_bytes: Rendered file size.
        expires_at: ISO-8601 UTC purge deadline, ``None`` when unknown —
            the UI then says nothing rather than guess (N2 rule).
    """

    url: str
    filename: str
    doc_type: str
    size_bytes: int
    expires_at: str | None = None


_pending_documents: dict[str, list[PendingDocument]] = {}
_lock = threading.Lock()


def store_pending_document(conversation_id: str, document: PendingDocument) -> None:
    """Queue a generated document for delivery to the frontend."""
    with _lock:
        _pending_documents.setdefault(conversation_id, []).append(document)
    logger.info(
        "pending_document_stored",
        conversation_id=conversation_id,
        doc_type=document.doc_type,
        size_bytes=document.size_bytes,
    )


def peek_pending_documents(conversation_id: str) -> list[PendingDocument]:
    """Read pending documents without clearing (message-metadata archiving)."""
    with _lock:
        return list(_pending_documents.get(conversation_id, []))


def get_and_clear_pending_documents(conversation_id: str) -> list[PendingDocument]:
    """Retrieve and clear pending documents (SSE done chunk)."""
    with _lock:
        documents = _pending_documents.pop(conversation_id, [])
    if documents:
        logger.info(
            "pending_documents_retrieved",
            conversation_id=conversation_id,
            count=len(documents),
        )
    return documents


def to_wire_metadata(
    documents: Sequence[PendingDocument],
) -> list[dict[str, str | int | None]]:
    """Serialize for the client — SAME shape on the done chunk and the archive."""
    return [
        {
            "url": document.url,
            "filename": document.filename,
            "doc_type": document.doc_type,
            "size_bytes": document.size_bytes,
            "expires_at": document.expires_at,
        }
        for document in documents
    ]
```

- [ ] **Step 4: Run tests** — Expected: PASS.

---

### Task 10: Prompt file + `DocumentGenerationService`

**Files:**
- Create: `apps/api/src/domains/agents/prompts/v1/document_generation_prompt.txt`
- Modify: `apps/api/src/domains/agents/prompts/prompt_loader.py` (add `"document_generation_prompt"` to the `PromptName` Literal, line ~71 — the sync test `test_prompt_name_literal_sync.py` enforces file ↔ literal pairing)
- Create: `apps/api/src/domains/document_generation/service.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_service.py`

**Interfaces:**
- Consumes: `get_llm("document_generation")`, `get_llm_config_for_agent(settings, "document_generation").provider`, `get_structured_output_with_retry` (exact import path: copy the imports used by `src/domains/telephony/return_synthesis.py:269-279` — the canonical caller), `SCHEMA_BY_DOC_TYPE`, `render_document`, `sanitize_filename_stem`, `store_pending_document`, `AttachmentRepository`.
- Produces (consumed by Task 11):
  ```python
  @dataclass
  class GeneratedDocumentResult:
      attachment_id: str
      url: str
      filename: str
      doc_type: str
      size_bytes: int
      expires_at_iso: str | None
      truncated_source: bool

  async def generate_document_for_user(
      *,
      user_id: uuid.UUID,
      conversation_id: str,
      doc_type: DocumentType,
      instructions: str,
      source_data: str,
      requested_filename: str,
      language: str,
      config: RunnableConfig | None,
  ) -> GeneratedDocumentResult
  ```

- [ ] **Step 1: Write the prompt file** `document_generation_prompt.txt` (English, no numeric tunables in prose — the source cap is applied in code and reported by code):

```
You are a professional document writer. Produce the COMPLETE content of one document, in the user's language ({language}), matching the requested format family.

Rules:
- Write final, polished content — never placeholders, never "TBD", never meta-comments about the document.
- Ground the content in SOURCE DATA when provided; do not invent figures that contradict it. If source data was truncated, work with what is present.
- Choose a short, descriptive filename_stem (no extension, no path).
- Tabular output: consistent columns, every cell a plain string, no formulas.
- Sectioned output: a logical structure of headings, paragraphs, bullet lists and tables.
- Slides output: one idea per slide, concise bullets, optional speaker notes.

USER REQUEST:
{instructions}

SOURCE DATA (may be empty or truncated):
{source_data}
```

- [ ] **Step 2: Write the failing service test** (mock the LLM boundary, real renderers, tmp storage):

```python
"""DocumentGenerationService: LLM->render->attachment->pending store (ADR-226)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.document_generation.schemas import (
    DocumentType,
    TableSheet,
    TabularContent,
)


@pytest.fixture
def tabular_result() -> TabularContent:
    return TabularContent(
        filename_stem="modeles-llm",
        title="Modèles LLM",
        sheets=[TableSheet(name="M", headers=["modèle"], rows=[["Fable 5"]])],
    )


async def test_generate_csv_end_to_end(tmp_path, monkeypatch, tabular_result) -> None:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))

    from src.domains.document_generation import service as svc

    created: dict = {}

    class _FakeRepo:
        def __init__(self, db) -> None: ...

        async def create(self, payload: dict):
            created.update(payload)

            class _A:
                id = uuid.UUID("00000000-0000-0000-0000-000000000001")
                expires_at = payload["expires_at"]

            return _A()

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
    ):
        result = await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv1",
            doc_type=DocumentType.CSV,
            instructions="liste des modèles",
            source_data="",
            requested_filename="",
            language="fr",
            config=None,
        )

    assert result.filename == "modeles-llm.csv"
    assert result.url.endswith("00000000-0000-0000-0000-000000000001")
    assert created["mime_type"] == "text/csv"
    assert created["content_type"] == "document"
    stored = tmp_path / created["file_path"]
    assert stored.is_file() and stored.stat().st_size == result.size_bytes

    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    pending = get_and_clear_pending_documents("conv1")
    assert len(pending) == 1 and pending[0].doc_type == "csv"


async def test_source_data_truncation_flagged(monkeypatch, tmp_path, tabular_result) -> None:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    # Threshold read from settings — computed relative, never hardcoded.
    cap = app_settings.document_generation_max_source_chars

    from src.domains.document_generation import service as svc

    captured: dict = {}

    async def _fake_llm(**kwargs):
        captured.update(kwargs)
        return tabular_result

    class _FakeRepo:
        def __init__(self, db) -> None: ...

        async def create(self, payload: dict):
            class _A:
                id = uuid.uuid4()
                expires_at = payload["expires_at"]

            return _A()

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "_call_document_llm", AsyncMock(side_effect=_fake_llm)),
    ):
        result = await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv2",
            doc_type=DocumentType.CSV,
            instructions="x",
            source_data="y" * (cap + 100),
            requested_filename="",
            language="fr",
            config=None,
        )

    assert result.truncated_source is True
    assert len(captured["source_data"]) == cap
```

Adjust the fake repo/DB seam to the actual service code (the service opens `get_db_context()` internally like `generate_image` — patch `svc.get_db_context` with an async-context-manager stub if needed; keep the boundary faithful: the repo receives the payload dict).

- [ ] **Step 3: Run to verify failure** — Expected: FAIL (module missing).

- [ ] **Step 4: Implement `service.py`** — structure (follow `generate_image` steps 7-8 and `return_synthesis.py` for the LLM call):

```python
"""Document generation service: LLM structured content -> rendered attachment (ADR-226)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.attachments.models import AttachmentContentType, AttachmentStatus
from src.domains.attachments.repository import AttachmentRepository
from src.domains.document_generation.document_store import (
    PendingDocument,
    store_pending_document,
)
from src.domains.document_generation.renderers import (
    DOCUMENT_EXTENSIONS,
    DOCUMENT_MIME_TYPES,
    render_document,
)
from src.domains.document_generation.sanitize import sanitize_filename_stem
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentContent,
    DocumentType,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_LLM_TYPE = "document_generation"


@dataclass
class GeneratedDocumentResult:
    """Outcome of a successful document generation."""

    attachment_id: str
    url: str
    filename: str
    doc_type: str
    size_bytes: int
    expires_at_iso: str | None
    truncated_source: bool


async def _call_document_llm(
    *,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    language: str,
    config: RunnableConfig | None,
) -> DocumentContent:
    """Produce structured document content with the dedicated LLM slot.

    Module-level seam (patched in unit tests). Mirrors
    ``telephony/return_synthesis.py``: get_llm + provider from resolved config
    + retried structured output; passing ``config`` through keeps the graph's
    token-tracking callbacks attached (node_name = the LLM type).
    """
    # Copy the exact imports return_synthesis.py uses for
    # get_llm_config_for_agent and get_structured_output_with_retry.
    from src.core.config.llm_helpers import get_llm_config_for_agent  # verify path
    from src.infrastructure.llm.structured_output import (  # verify path
        get_structured_output_with_retry,
    )

    system = load_prompt("document_generation_prompt", "v1").format(
        language=language, instructions=instructions, source_data=source_data
    )
    llm = get_llm(_LLM_TYPE)
    provider = get_llm_config_for_agent(settings, _LLM_TYPE).provider
    return await get_structured_output_with_retry(
        llm=llm,
        messages=[SystemMessage(content=system), HumanMessage(content="Produce the document now.")],
        schema=SCHEMA_BY_DOC_TYPE[doc_type],
        provider=provider,
        node_name=_LLM_TYPE,
        config=config,
    )


async def _write_document_file(data: bytes, relative_path: str) -> None:
    """Persist rendered bytes under the attachments storage root (off-loop)."""
    absolute_path = Path(settings.attachments_storage_path) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, data)


async def generate_document_for_user(
    *,
    user_id: uuid.UUID,
    conversation_id: str,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    requested_filename: str,
    language: str,
    config: RunnableConfig | None,
) -> GeneratedDocumentResult:
    """Generate, render and store one document; queue its card for delivery.

    Raises:
        Exception: LLM/renderer/storage failures propagate — the TOOL layer
            translates them into honest UnifiedToolOutput failures.
    """
    cap = settings.document_generation_max_source_chars
    truncated = len(source_data) > cap
    content = await _call_document_llm(
        doc_type=doc_type,
        instructions=instructions,
        source_data=source_data[:cap],
        language=language,
        config=config,
    )

    data = await asyncio.to_thread(render_document, doc_type, content)

    stem = sanitize_filename_stem(requested_filename or content.filename_stem)
    extension = DOCUMENT_EXTENSIONS[doc_type]
    download_filename = f"{stem}.{extension}"
    stored_filename = f"{uuid.uuid4()}.{extension}"
    relative_path = f"{user_id}/{stored_filename}"
    await _write_document_file(data, relative_path)

    async with get_db_context() as db:
        repo = AttachmentRepository(db)
        attachment = await repo.create(
            {
                "user_id": user_id,
                "original_filename": download_filename,
                "stored_filename": stored_filename,
                "mime_type": DOCUMENT_MIME_TYPES[doc_type],
                "file_size": len(data),
                "file_path": relative_path,
                "content_type": AttachmentContentType.DOCUMENT,
                "status": AttachmentStatus.READY,
                "expires_at": datetime.now(UTC)
                + timedelta(hours=settings.attachments_ttl_hours),
            }
        )
        expires_at_iso = attachment.expires_at.isoformat() if attachment.expires_at else None
        await db.commit()
        attachment_id = str(attachment.id)

    url = f"/api/v1/attachments/{attachment_id}"
    store_pending_document(
        conversation_id,
        PendingDocument(
            url=url,
            filename=download_filename,
            doc_type=doc_type.value,
            size_bytes=len(data),
            expires_at=expires_at_iso,
        ),
    )
    logger.info(
        "document_generation_attachment_saved",
        attachment_id=attachment_id,
        user_id=str(user_id),
        doc_type=doc_type.value,
        file_size=len(data),
    )
    return GeneratedDocumentResult(
        attachment_id=attachment_id,
        url=url,
        filename=download_filename,
        doc_type=doc_type.value,
        size_bytes=len(data),
        expires_at_iso=expires_at_iso,
        truncated_source=truncated,
    )
```

**Import verification step**: before finalizing, open `src/domains/telephony/return_synthesis.py` and copy its EXACT import lines for `get_llm_config_for_agent` and `get_structured_output_with_retry` (the paths in the sketch carry `# verify path` markers and MUST be replaced by the real ones).

- [ ] **Step 5: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation -v`. Expected: PASS, plus `tests/unit/domains/agents/prompts/test_prompt_name_literal_sync.py` PASS (new prompt paired with its Literal entry).

---

### Task 11: `generate_document` tool

**Files:**
- Create: `apps/api/src/domains/agents/tools/document_generation_tools.py`
- Modify: `apps/api/src/domains/agents/constants.py` (add `AGENT_DOCUMENT = "document_generation_agent"` next to `AGENT_IMAGE`, line ~67)
- Test: `apps/api/tests/unit/domains/agents/tools/test_document_generation_tools.py`

**Interfaces:**
- Consumes: Task 10 `generate_document_for_user`, Task 1 settings, Task 3 user column.
- Produces: registered tool `generate_document` returning `UnifiedToolOutput` — consumed by Task 12 manifests and the tool-registry smoke test (which auto-imports and invokes every registered tool in CI).

- [ ] **Step 1: Write the failing tests** (guard order mirrors `generate_image`; each test patches only what its guard needs):

```python
"""generate_document tool: guard order, honest failures, success path (ADR-226)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.domains.agents.tools import document_generation_tools as mod


def _runtime(user_id: str | None = "11111111-1111-1111-1111-111111111111") -> MagicMock:
    runtime = MagicMock()
    runtime.config = {"configurable": {"user_id": user_id, "thread_id": "conv1"}}
    return runtime


async def test_missing_user_id_fails_auth() -> None:
    result = await mod.generate_document.func(
        instructions="x", doc_type="csv", runtime=_runtime(user_id=None)
    )
    assert result.success is False and result.error_code == "AUTH_ERROR"


async def test_global_flag_off_fails(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_enabled", False)
    result = await mod.generate_document.func(
        instructions="x", doc_type="csv", runtime=_runtime()
    )
    assert result.success is False


async def test_invalid_doc_type_lists_valid_values(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_enabled", True)
    result = await mod.generate_document.func(
        instructions="x", doc_type="exe", runtime=_runtime()
    )
    assert result.success is False
    assert "csv" in result.message  # the enforced bound is published to the caller


async def test_user_opt_out_fails(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_enabled", True)
    user = MagicMock()
    user.document_generation_enabled = False
    with patch.object(mod, "_load_user", AsyncMock(return_value=user)):
        result = await mod.generate_document.func(
            instructions="x", doc_type="csv", runtime=_runtime()
        )
    assert result.success is False


async def test_service_failure_is_honest(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_enabled", True)
    user = MagicMock()
    user.document_generation_enabled = True
    user.language = "fr"
    with (
        patch.object(mod, "_load_user", AsyncMock(return_value=user)),
        patch.object(
            mod, "generate_document_for_user", AsyncMock(side_effect=RuntimeError("render boom"))
        ),
    ):
        result = await mod.generate_document.func(
            instructions="x", doc_type="csv", runtime=_runtime()
        )
    assert result.success is False  # tokens may be spent, but no phantom success


async def test_success_returns_action_success(monkeypatch) -> None:
    from src.core.config import settings
    from src.domains.document_generation.service import GeneratedDocumentResult

    monkeypatch.setattr(settings, "document_generation_enabled", True)
    user = MagicMock()
    user.document_generation_enabled = True
    user.language = "fr"
    outcome = GeneratedDocumentResult(
        attachment_id=str(uuid.uuid4()),
        url="/api/v1/attachments/x",
        filename="a.csv",
        doc_type="csv",
        size_bytes=10,
        expires_at_iso=None,
        truncated_source=False,
    )
    with (
        patch.object(mod, "_load_user", AsyncMock(return_value=user)),
        patch.object(mod, "generate_document_for_user", AsyncMock(return_value=outcome)),
    ):
        result = await mod.generate_document.func(
            instructions="liste", doc_type="csv", runtime=_runtime()
        )
    assert result.success is True
    assert result.structured_data["document_url"] == "/api/v1/attachments/x"
    assert "displayed" in result.message or "download" in result.message.lower()
```

Note: `.func` unwraps `StructuredTool` — check how existing tool tests in `tests/unit/domains/agents/tools/` invoke registered tools (some use `.ainvoke`); mirror the prevailing pattern. Also check how the existing `generate_image` tests neutralize the `@rate_limit` decorator (fixture, settings monkeypatch, or Redis-free in-memory limiter): repeated calls within one test module must not trip the per-user window — copy their harness verbatim.

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (module missing).

- [ ] **Step 3: Implement the tool** — structural mirror of `generate_image` (same decorator stack, same guard order, `_load_user` extracted as a module-level seam):

```python
"""LangChain tool for AI document generation (ADR-226).

Mirrors image_generation_tools.py: runtime context extraction, global flag,
user opt-in, validated inputs, dedicated internal LLM, Attachment storage
(TTL cleanup), pending-store delivery, honest failure semantics.
"""

from __future__ import annotations

import time
from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_DOCUMENT
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.document_generation.schemas import DocumentType
from src.domains.document_generation.service import generate_document_for_user
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = get_logger(__name__)


async def _load_user(user_id):  # full type hints in the real file
    """Load the user row (module-level seam for tests)."""
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await db.get(User, user_id)


@registered_tool
@track_tool_metrics(
    tool_name="generate_document",
    agent_name=AGENT_DOCUMENT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.document_generation_rate_limit_calls,
    window_seconds=lambda: settings.document_generation_rate_limit_window,
    scope="user",
)
async def generate_document(
    instructions: str,
    doc_type: str,
    source_data: str = "",
    filename: str = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Create a downloadable document (csv, xlsx, docx, pptx, pdf, md, txt).

    The document content is written by a dedicated AI writer from your
    instructions and the optional source data, then rendered to the requested
    format and displayed as a downloadable card below the assistant response.

    Args:
        instructions: What the document must contain — subject, structure,
            level of detail, audience. Be specific.
        doc_type: Target format. One of: csv, xlsx, docx, pptx, pdf, md, txt.
        source_data: Optional raw material (e.g. research results from an
            earlier step) the document must be grounded in.
        filename: Optional filename (without extension) requested by the user.
    """
    start_time = time.time()

    configurable = runtime.config.get("configurable", {}) if runtime else {}
    user_id_raw = configurable.get("user_id")
    if not user_id_raw:
        logger.warning("document_generation_no_user_id", has_runtime=runtime is not None)
        return UnifiedToolOutput.failure(
            message="Could not identify user. Please try again.",
            error_code="AUTH_ERROR",
        )

    if not settings.document_generation_enabled:
        return UnifiedToolOutput.failure(
            message="Document generation is currently disabled by the administrator.",
            error_code="TOOL_ERROR",
        )

    try:
        parsed_type = DocumentType(doc_type.strip().lower().lstrip("."))
    except ValueError:
        valid = ", ".join(t.value for t in DocumentType)
        return UnifiedToolOutput.failure(
            message=f"Invalid doc_type '{doc_type}'. Must be one of: {valid}",
            error_code="TOOL_ERROR",
        )

    from src.domains.agents.tools.runtime_helpers import parse_user_id

    user_id = parse_user_id(user_id_raw)
    try:
        user = await _load_user(user_id)
    except Exception as exc:
        logger.error("document_generation_user_load_error", error=str(exc), user_id=str(user_id))
        return UnifiedToolOutput.failure(
            message="Error loading user preferences. Please try again.",
            error_code="TOOL_ERROR",
        )
    if not user:
        return UnifiedToolOutput.failure(message="User not found.", error_code="TOOL_ERROR")
    if not user.document_generation_enabled:
        return UnifiedToolOutput.failure(
            message=(
                "Document generation is not enabled in your settings. "
                "Enable it in Settings > Features > Document Generation."
            ),
            error_code="TOOL_ERROR",
        )

    conversation_id = str(configurable.get("thread_id", "unknown"))
    try:
        result = await generate_document_for_user(
            user_id=user_id,
            conversation_id=conversation_id,
            doc_type=parsed_type,
            instructions=instructions,
            source_data=source_data,
            requested_filename=filename,
            language=user.language,
            config=runtime.config if runtime else None,
        )
    except Exception as exc:
        logger.error(
            "document_generation_failed",
            error_type=type(exc).__name__,
            error=str(exc),
            doc_type=parsed_type.value,
            user_id=str(user_id),
        )
        return UnifiedToolOutput.failure(
            message=(
                f"Document generation failed ({type(exc).__name__}). "
                "No document was produced."
            ),
            error_code="TOOL_ERROR",
        )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "document_generation_tool_success",
        doc_type=result.doc_type,
        file_size=result.size_bytes,
        duration_ms=duration_ms,
        attachment_id=result.attachment_id,
    )
    truncation_note = (
        " Note: the provided source data exceeded the configured limit and was truncated."
        if result.truncated_source
        else ""
    )
    return UnifiedToolOutput.action_success(
        message=(
            f"Document '{result.filename}' generated successfully and displayed as a "
            f"downloadable card below the response.{truncation_note}\n"
            "Do NOT include any markdown link to the document — the card is already shown."
        ),
        structured_data={
            "document_url": result.url,
            "filename": result.filename,
            "doc_type": result.doc_type,
            "size_bytes": result.size_bytes,
        },
    )
```

Normalize `user.language` through `normalize_language` if the User row stores raw locales — check how `return_synthesis` receives `user_language` and mirror.

- [ ] **Step 4: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/tools/test_document_generation_tools.py -v`. Expected: PASS. Then the registry smoke test: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/tools/test_tool_registry_smoke.py -v`. Expected: PASS (the new tool is imported and invoked).

---

### Task 12: Catalogue manifests + taxonomy + loader + timeout family

**Files:**
- Create: `apps/api/src/domains/agents/document_generation/__init__.py`, `apps/api/src/domains/agents/document_generation/catalogue_manifests.py`
- Modify: `apps/api/src/domains/agents/registry/domain_taxonomy.py` (new DomainConfig after `image_generation`, ~line 512)
- Modify: `apps/api/src/domains/agents/registry/catalogue_loader.py` (registration block after the image block, ~line 807)
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py` (`_DOCUMENT_TOOL_NAMES` next to `_IMAGE_TOOL_NAMES` line 1619; floor/ceiling branch next to the image branch, lines ~1700-1725)
- Test: `apps/api/tests/unit/domains/agents/test_document_generation_wiring.py`

**Interfaces:**
- Consumes: `AGENT_DOCUMENT`, tool `generate_document`, Task 1 timeout settings.
- Produces: routable domain `document_generation` (result_key `document_generations`), catalogue entries gated by `document_generation_enabled`.

- [ ] **Step 1: Write the failing tests**

```python
"""Wiring: taxonomy, manifests, loader gating, timeout family (ADR-226)."""

from src.core.config import settings
from src.domains.agents.constants import AGENT_DOCUMENT
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY


def test_domain_registered_and_routable() -> None:
    cfg = DOMAIN_REGISTRY["document_generation"]
    assert cfg.result_key == "document_generations"
    assert cfg.is_routable is True
    assert AGENT_DOCUMENT in cfg.agent_names


def test_manifest_publishes_doc_type_enum() -> None:
    from src.domains.agents.document_generation.catalogue_manifests import (
        generate_document_catalogue_manifest,
    )

    doc_type_param = next(
        p for p in generate_document_catalogue_manifest.parameters if p.name == "doc_type"
    )
    assert doc_type_param.required is True
    # An enforced constraint must be published (ADR-184): the planner sees the
    # exact enum the tool validates against.
    assert set(doc_type_param.enum or []) == {
        "csv", "xlsx", "docx", "pptx", "pdf", "md", "txt",
    }


def test_timeout_family_resolution() -> None:
    from src.domains.agents.orchestration.parallel_executor import (
        _DOCUMENT_TOOL_NAMES,
        resolve_tool_timeout,  # use the ACTUAL function name found at lines ~1630-1725
    )

    assert "generate_document" in _DOCUMENT_TOOL_NAMES
    resolved = resolve_tool_timeout("generate_document", requested_timeout_ms=None)
    assert resolved >= settings.document_generation_tool_timeout_seconds
```

Before writing: open `parallel_executor.py:1630-1725`, note the ACTUAL resolution function name and signature, and shape `test_timeout_family_resolution` on the existing image-family test (search `tests/unit` for `max_image_generation_tool_timeout` to find it) — mirror its call pattern exactly. Also verify `ParameterSchema` supports an `enum` field (open `registry/catalogue.py`); if the field is named differently (e.g. `allowed_values`), use the actual name in manifest and test.

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`KeyError: 'document_generation'`).

- [ ] **Step 3: Implement the manifests** (`catalogue_manifests.py` mirrors the image file):

```python
"""Catalogue manifests for the Document Generation tool (ADR-226)."""

from src.domains.agents.constants import AGENT_DOCUMENT
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

document_agent_manifest = AgentManifest(
    name=AGENT_DOCUMENT,
    description="Agent for AI document generation (csv, xlsx, docx, pptx, pdf, md, txt).",
    tools=["generate_document"],
    max_parallel_runs=1,
    default_timeout_ms=180000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
)

_desc = (
    "**Tool: generate_document** - Create a downloadable document from instructions "
    "and optional source data.\n"
    "The document is displayed as a downloadable card below the assistant response "
    "and expires automatically.\n"
    "**Use for**: 'Export this as CSV/Excel', 'Write a report about... as PDF/Word', "
    "'Make a presentation about...', 'Formalize these results into a file'.\n"
    "**Chaining**: pass research results from earlier steps via source_data "
    "(e.g. $steps.step_1.web_searches) so the document is grounded in them.\n"
    "**Output**: downloadable document card below the response."
)

generate_document_catalogue_manifest = ToolManifest(
    name="generate_document",
    agent=AGENT_DOCUMENT,
    description=_desc,
    semantic_keywords=[
        "create a csv or excel spreadsheet file",
        "export results as a document file",
        "write a report as pdf or word document",
        "make a powerpoint presentation file",
        "formalize data into a structured file",
        "generate a downloadable file",
    ],
    parameters=[
        ParameterSchema(
            name="instructions",
            type="string",
            required=True,
            description=(
                "What the document must contain: subject, structure, level of "
                "detail, audience."
            ),
        ),
        ParameterSchema(
            name="doc_type",
            type="string",
            required=True,
            enum=["csv", "xlsx", "docx", "pptx", "pdf", "md", "txt"],
            description="Target format.",
        ),
        ParameterSchema(
            name="source_data",
            type="string",
            required=False,
            description=(
                "Raw material to ground the document in — typically the result "
                "of earlier research steps."
            ),
        ),
        ParameterSchema(
            name="filename",
            type="string",
            required=False,
            description="Filename requested by the user, without extension.",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation with the generated filename",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=2000,
        est_tokens_out=8000,
        est_cost_usd=0.05,
        est_latency_ms=60000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    tool_category="create",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="\U0001f4c4",  # page facing up
        i18n_key="generate_document",
        visible=True,
        category="tool",
    ),
)
```

(If `ParameterSchema` has no `enum` field, use its actual bounded-values field — `_manifest_to_dict` publishes bounds per ADR-184; check how `min`/`max` are declared and follow the same channel for enumerations.)

- [ ] **Step 4: Taxonomy + loader + executor**

`domain_taxonomy.py` after the `image_generation` entry:

```python
    # AI Document Generation (ADR-226)
    "document_generation": DomainConfig(
        name="document_generation",
        display_name="Document Generation",
        description=(
            "Create downloadable documents (CSV, Excel, Word, PowerPoint, PDF, "
            "Markdown, text) from instructions and optional data. "
            "Use when the user asks for a file, an export, a report document, "
            "a spreadsheet or a presentation. NOT for images."
        ),
        agent_names=["document_generation_agent"],
        result_key="document_generations",
        related_domains=[],
        is_routable=True,
        # requires_api_key False: uses the admin LLM Config slot.
        metadata={"provider": "internal", "requires_oauth": False, "requires_api_key": False},
    ),
```

`catalogue_loader.py` after the image block (~line 807):

```python
    # Register Document Generation manifests (feature-flagged, ADR-226)
    if getattr(_get_settings(), "document_generation_enabled", False):
        from src.domains.agents.document_generation.catalogue_manifests import (
            document_agent_manifest,
            generate_document_catalogue_manifest,
        )

        registry.register_agent_manifest(document_agent_manifest)
        registry.register_tool_manifest(generate_document_catalogue_manifest)
```

`parallel_executor.py`: next to line 1619 add `_DOCUMENT_TOOL_NAMES: frozenset[str] = frozenset({"generate_document"})`; in the timeout resolution function, mirror the image branch (lines ~1700-1725) with `cfg.document_generation_tool_timeout_seconds` / `cfg.max_document_generation_tool_timeout_seconds`, and extend the family comment block at ~line 1630.

- [ ] **Step 5: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/test_document_generation_wiring.py -v` then the taxonomy/catalogue suites: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry -v`. Expected: PASS (including any registry completeness guards).

---

### Task 13: SSE + archive delivery, PDF inline disposition

**Files:**
- Modify: `apps/api/src/domains/agents/api/service.py` (archive block after the image block ~line 1150; done-chunk block after the image block ~line 1593)
- Modify: `apps/api/src/domains/attachments/router.py` (disposition rule, lines 100-110)
- Test: `apps/api/tests/unit/domains/document_generation/test_delivery_wire.py`, extend the existing attachments router test module (find it under `tests/unit/domains/attachments/`)

**Interfaces:**
- Consumes: Task 9 store. Produces: `assistant_metadata["generated_documents"]` and `done_metadata["generated_documents"]` — the SAME `to_wire_metadata` output both times (consumed by Task 14 frontend).

- [ ] **Step 1: Write the failing wire test**

```python
"""Archive and done-chunk carry the identical generated_documents shape (ADR-226)."""

from src.domains.document_generation.document_store import (
    PendingDocument,
    get_and_clear_pending_documents,
    peek_pending_documents,
    to_wire_metadata,
)


def test_peek_then_clear_serialize_identically() -> None:
    doc = PendingDocument(
        url="/api/v1/attachments/y",
        filename="rapport.pdf",
        doc_type="pdf",
        size_bytes=1234,
        expires_at="2026-08-19T00:00:00+00:00",
    )
    from src.domains.document_generation.document_store import store_pending_document

    store_pending_document("conv-wire", doc)
    archived = to_wire_metadata(peek_pending_documents("conv-wire"))
    live = to_wire_metadata(get_and_clear_pending_documents("conv-wire"))
    assert archived == live  # one serializer, zero drift (the GeneratedImage lesson)
```

And the router disposition test (in the existing attachments router test module, following its fixture style):

```python
async def test_pdf_served_inline_docx_as_attachment(...) -> None:
    # Build two attachments (mime application/pdf and the docx mime) with the
    # module's existing factory/fixtures; call the endpoint; assert:
    #   pdf  -> content-disposition starts with "inline"
    #   docx -> content-disposition starts with "attachment"
    ...
```

Write it against the module's real fixtures (client, auth, tmp storage) — copy the closest existing GET test wholesale and change mime + assertion.

- [ ] **Step 2: Run to verify failure** — wire test PASSES already (store exists) — keep it as a regression guard; the router test FAILS (pdf currently served as attachment).

- [ ] **Step 3: Implement**

`attachments/router.py` (replace lines 100-110):

```python
    # "inline" lets the browser display the resource natively: images get the
    # long-press "Save Image" menu on mobile; PDFs open in the browser viewer
    # (generated reports and uploaded PDFs alike — the user owns both).
    # Every other type keeps "attachment" to trigger a download prompt.
    is_inline = attachment.mime_type.startswith("image/") or (
        attachment.mime_type == "application/pdf"
    )

    return FileResponse(
        path=str(file_path),
        media_type=attachment.mime_type,
        filename=attachment.original_filename,
        content_disposition_type="inline" if is_inline else "attachment",
    )
```

`agents/api/service.py` — archive block, inserted right after the image archive block (~line 1150), same guard style:

```python
                            # Persist generated document cards in message metadata
                            # so they survive page reload (ADR-226).
                            if getattr(settings, "document_generation_enabled", False):
                                from src.domains.document_generation.document_store import (
                                    peek_pending_documents,
                                )
                                from src.domains.document_generation.document_store import (
                                    to_wire_metadata as documents_to_wire,
                                )

                                peeked_documents = peek_pending_documents(str(conversation_id))
                                if peeked_documents:
                                    assistant_metadata["generated_documents"] = (
                                        documents_to_wire(peeked_documents)
                                    )
```

done-chunk block, inserted right after the image done block (~line 1593):

```python
                    # === DOCUMENT GENERATION: card metadata in the done chunk (ADR-226) ===
                    if getattr(settings, "document_generation_enabled", False):
                        from src.domains.document_generation.document_store import (
                            get_and_clear_pending_documents,
                        )
                        from src.domains.document_generation.document_store import (
                            to_wire_metadata as documents_to_wire,
                        )

                        pending_documents = get_and_clear_pending_documents(
                            str(conversation_id)
                        )
                        if pending_documents:
                            done_metadata["generated_documents"] = documents_to_wire(
                                pending_documents
                            )
```

(The aliased import avoids shadowing the image `to_wire_metadata` imported in the same scopes.)

- [ ] **Step 4: Run tests** — Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/attachments tests/unit/domains/document_generation -v`. Expected: PASS. Then the fast unit gate: `task test:backend:unit:fast`. Expected: PASS (service.py edits break nothing).

---

### Task 14: Frontend types + reducer + history mapping

**Files:**
- Modify: `apps/web/src/types/chat.ts` (GeneratedDocument interface next to GeneratedImage line 34; `generatedDocuments?` next to line 62; `generated_documents?` next to line 174)
- Modify: `apps/web/src/types/chat-state.ts` (~line 237, next to `generated_images`)
- Modify: `apps/web/src/reducers/chat-reducer.ts` (~line 68)
- Modify: `apps/web/src/hooks/useConversation.ts` (~line 207)
- Test: extend `apps/web/src/reducers/__tests__/chat-reducer.streaming.test.ts` and `apps/web/src/hooks/__tests__/useConversation.api.test.ts`

**Interfaces:**
- Produces (consumed by Task 15):

```typescript
export interface GeneratedDocument {
  /** Relative attachment URL, e.g. `/api/v1/attachments/{id}`. */
  url: string;
  /** Human-meaningful download filename (e.g. "modeles-llm.csv"). */
  filename: string;
  /** Format: csv | xlsx | docx | pptx | pdf | md | txt. */
  doc_type: string;
  /** Rendered file size in bytes. */
  size_bytes: number;
  /** ISO-8601 purge deadline, absent when unknown (UI then stays silent). */
  expires_at?: string | null;
}
```

`Message.generatedDocuments?: GeneratedDocument[]`, wire key `generated_documents`.

- [ ] **Step 1: Write the failing tests** — in `chat-reducer.streaming.test.ts`, next to the `generated_images` case (line ~160):

```typescript
it('maps generated_documents from done metadata onto the message', () => {
  // Copy the existing generated_images done-chunk test wholesale; metadata:
  //   generated_documents: [{ url: '/api/v1/attachments/d1', filename: 'a.csv',
  //     doc_type: 'csv', size_bytes: 42, expires_at: null }]
  // Assert the resulting message carries generatedDocuments with that entry.
});
```

in `useConversation.api.test.ts`, next to the image history case (line ~71/176): the API message fixture gains `message_metadata.generated_documents` and the mapped message asserts `generatedDocuments` present; a message without the key asserts `undefined`.

- [ ] **Step 2: Run to verify failure** — Run: `cd apps/web && pnpm vitest run src/reducers/__tests__/chat-reducer.streaming.test.ts src/hooks/__tests__/useConversation.api.test.ts`. Expected: FAIL (type errors / undefined mapping).

- [ ] **Step 3: Implement** — add the interface + the three type keys (chat.ts twice, chat-state.ts once), then:

`chat-reducer.ts:68` (next to `generatedImages`):

```typescript
    generatedDocuments: metadata.generated_documents,
```

`useConversation.ts:207`:

```typescript
      generatedDocuments:
        (msg.message_metadata?.generated_documents as GeneratedDocument[] | undefined) ?? undefined,
```

Extend the single-declaration comment above `GeneratedImage` (chat.ts lines 28-33) to mention `GeneratedDocument` obeys the same rule.

- [ ] **Step 4: Run tests** — same vitest command. Expected: PASS. Then `cd apps/web && pnpm exec tsc --noEmit --incremental false`. Expected: 0 errors.

---

### Task 15: Document cards in ChatMessage + i18n

**Files:**
- Modify: `apps/web/src/components/chat/ChatMessage.tsx` (new `GeneratedDocumentCards` component next to `GeneratedImageCards` line 392; render site next to line 896)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`
- Test: `apps/web/src/components/chat/__tests__/ChatMessage.documents.test.tsx`

**Interfaces:**
- Consumes: Task 14 types; the existing `ImageExpiryNotice` (same file — verify it takes `expiresAt` and renders format-agnostic copy; if its strings say "image", add a document variant key and a `labelKey` prop instead of duplicating the component).

- [ ] **Step 1: Write the failing test**

```typescript
/**
 * GeneratedDocumentCards — download card per generated document (ADR-226).
 */
import { render, screen } from '@testing-library/react';
// reuse the module's existing renderWithProviders/i18n harness from ChatMessage.test.tsx

const doc = {
  url: '/api/v1/attachments/d1',
  filename: 'modeles-llm.csv',
  doc_type: 'csv',
  size_bytes: 2048,
  expires_at: null,
};

it('renders filename, a download link with the attachment href, and the type', () => {
  renderMessage(makeMessage({ generatedDocuments: [doc] }));
  expect(screen.getByText('modeles-llm.csv')).toBeInTheDocument();
  const link = screen.getByRole('link', { name: /download|télécharger/i });
  expect(link).toHaveAttribute('href', '/api/v1/attachments/d1');
});

it('pdf card opens in a new tab (inline disposition)', () => {
  renderMessage(
    makeMessage({
      generatedDocuments: [{ ...doc, filename: 'r.pdf', doc_type: 'pdf' }],
    })
  );
  const link = screen.getByRole('link', { name: /r\.pdf|open|ouvrir/i });
  expect(link).toHaveAttribute('target', '_blank');
});

it('renders nothing without documents', () => {
  renderMessage(makeMessage({}));
  expect(screen.queryByTestId('generated-document-card')).not.toBeInTheDocument();
});
```

Shape `makeMessage`/`renderMessage` on the builders already used by `ChatMessage.test.tsx:133` (Partial<Props> builders, no `as any`).

- [ ] **Step 2: Run to verify failure** — Expected: FAIL.

- [ ] **Step 3: Implement the component** — same card altitude as image cards; icon by family; native `<a>` (a download is a navigation, not a button):

```tsx
/**
 * AI-generated document cards — download cards below the assistant message.
 * PDF opens inline in a new tab (the API serves application/pdf inline);
 * every other type downloads via the `download` attribute (ADR-226).
 */
function GeneratedDocumentCards({ documents }: { documents: GeneratedDocument[] }) {
  const { t } = useTranslation();
  return (
    <div className="mt-3 space-y-2">
      {documents.map((doc, i) => {
        const isPdf = doc.doc_type === 'pdf';
        const Icon = documentTypeIcon(doc.doc_type);
        return (
          <div
            key={i}
            data-testid="generated-document-card"
            className="flex items-center gap-3 rounded-lg border bg-card p-3 max-w-[512px] mx-auto"
          >
            <Icon className="w-8 h-8 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-sm">{doc.filename}</p>
              <p className="text-xs text-muted-foreground">
                {doc.doc_type.toUpperCase()} · {formatFileSize(doc.size_bytes)}
              </p>
              <ImageExpiryNotice expiresAt={doc.expires_at} />
            </div>
            <a
              href={doc.url}
              {...(isPdf ? { target: '_blank', rel: 'noopener' } : { download: doc.filename })}
              className="p-2 rounded-md hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={
                isPdf
                  ? t('chat.document_card.open', { name: doc.filename })
                  : t('chat.document_card.download', { name: doc.filename })
              }
            >
              {isPdf ? <ExternalLink className="w-4 h-4" /> : <Download className="w-4 h-4" />}
            </a>
          </div>
        );
      })}
    </div>
  );
}
```

with helpers in the same file (or `lib/` if one already exists — check for an existing `formatFileSize` util first and reuse it):

```typescript
function documentTypeIcon(docType: string) {
  switch (docType) {
    case 'csv':
    case 'xlsx':
      return FileSpreadsheet;
    case 'pptx':
      return Presentation;
    case 'pdf':
    case 'docx':
    case 'md':
    case 'txt':
    default:
      return FileText;
  }
}
```

(lucide imports: `FileSpreadsheet`, `Presentation`, `FileText`, `ExternalLink` — `Download` is already imported line 8.) Render site, after the image cards block (line 896-898):

```tsx
            {message.generatedDocuments && message.generatedDocuments.length > 0 && (
              <GeneratedDocumentCards documents={message.generatedDocuments} />
            )}
```

If `ImageExpiryNotice` copy is image-specific, give it a `labelKey` prop defaulting to the current key and pass a `chat.document_card.expires` key here — never hardcode either string.

- [ ] **Step 4: Add i18n keys ×6** — namespace `chat.document_card`: `download` ("Download {{name}}" / "Télécharger {{name}}" / "{{name}} herunterladen" / "Descargar {{name}}" / "Scarica {{name}}" / "下载 {{name}}"), `open` ("Open {{name}}" / "Ouvrir {{name}}" / "{{name}} öffnen" / "Abrir {{name}}" / "Apri {{name}}" / "打开 {{name}}"), plus expiry key if introduced. Also the tool-progress key next to `generate_image` (line 3821): `"generate_document": "Generating document..."` (fr "Génération du document...", de "Dokument wird erstellt...", es "Generando documento...", it "Generazione del documento...", zh "正在生成文档...") and the display key next to `tool_generate_image` (line 2816): `"tool_generate_document": "Generate a document"` translated ×6.

- [ ] **Step 5: Run tests** — Run: `cd apps/web && pnpm vitest run src/components/chat/__tests__/ChatMessage.documents.test.tsx` then `task lint:frontend` (includes tsc + a11y ratchet) and `task lint:i18n`. Expected: PASS.

---

### Task 16: Frontend settings toggle

**Files:**
- Create: `apps/web/src/components/settings/DocumentGenerationSettings.tsx`
- Modify: `apps/web/src/app/[lng]/dashboard/settings/page.tsx` (render next to `ImageGenerationSettings`, lines 449 and 641)
- Modify: `apps/web/src/lib/settings-sections.ts` (declare the section for settings quick-search, mirroring line 144)
- Modify: `apps/web/src/lib/auth.tsx` (add `document_generation_enabled` to the user/preferences type next to `image_generation_enabled`)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (settings namespace)
- Test: `apps/web/src/components/settings/__tests__/DocumentGenerationSettings.test.tsx`

**Interfaces:**
- Consumes: the existing preferences update hook used by `ImageGenerationSettings.tsx` (open it; reuse the same `useApiMutation`/preferences endpoint — the backend field landed in Task 3).

- [ ] **Step 1: Write the failing test** — mirror `ImageGenerationSettings.test.tsx`'s "enable toggle" describe (line 69): renders the switch with a translated accessible name, reflects the current value, fires the preferences mutation with `document_generation_enabled: false` on toggle, disabled/pending state handled per the settings pattern.

- [ ] **Step 2: Run to verify failure** — Expected: FAIL.

- [ ] **Step 3: Implement** — copy `ImageGenerationSettings.tsx` structure REDUCED to the single toggle (no quality/size dropdowns, no options hook): collapsible section, `Label` + switch through the design-system primitives, i18n keys `settings.documentGeneration.title` / `.description` / `.enable` ×6 (fr: "Génération de documents" / "Créez des fichiers CSV, Excel, Word, PowerPoint, PDF téléchargeables dans la conversation." / "Activer la génération de documents"; translate the others consistently). Register the section in `settings-sections.ts` and render `<DocumentGenerationSettings lng={lng} />` at BOTH page sites (449 and 641 — the two layout branches).

- [ ] **Step 4: Run tests** — Run: `cd apps/web && pnpm vitest run src/components/settings/__tests__/DocumentGenerationSettings.test.tsx` then `task lint:i18n`. Expected: PASS.

---

### Task 17: E2E journey + docs + full gates

**Files:**
- Create: `apps/web/e2e/` spec following the existing hermetic pattern (find the closest chat-card journey — e.g. the image-card or smoke specs — and mirror its harness): mock the SSE done chunk with `generated_documents`, assert the card renders with an accessible download link.
- Modify: `docs/ARCHITECTURE_AGENT.md` (agents/tools inventory), `docs/INDEX.md`, `docs/technical/` entry if the index demands one; verify `README.md` feature surfaces only if they enumerate capabilities (release narrative surfaces are ENRICHED at release time, per owner rule).
- Test: the gates themselves.

- [ ] **Step 1: Write the e2e spec** — hermetic (mocked API/SSE, no real backend): user sends a message, the mocked stream ends with a done chunk carrying one `generated_documents` entry, expect `data-testid="generated-document-card"` visible, link role with accessible name, keyboard-focusable. Follow the harness conventions of `apps/web/e2e` (route interception, MSYS_NO_PATHCONV trap documented in memory for local runs).
- [ ] **Step 2: Run it** — Run: `task test:e2e` (or the package's targeted spec command). Expected: PASS.
- [ ] **Step 3: Update docs** — agent/tool inventory in `ARCHITECTURE_AGENT.md`; cross-reference ADR-226; `docs/INDEX.md` entry. Run `task lint:docs`. Expected: PASS.
- [ ] **Step 4: Full backend + frontend gates** — Run in order:
  - `task lint` — Expected: PASS (ratchets untouched or improved).
  - `task test:backend:unit:fast` — Expected: PASS.
  - `task test:frontend:coverage` — Expected: PASS (thresholds intact).
  - `task ci:fast` — Expected: PASS.
- [ ] **Step 5: Hand back to the owner** with the evidence block (commands + exit statuses + test counts), the list of touched files, and the reminder that dev-container runtime verification (`task dev` + a real generation with a configured provider key) and all git operations are owner-side. Raise coverage ratchets only if measured coverage gained ≥2 pts margin (owner rule: lock gains, never shave margins).

---

## Self-Review (performed at plan time)

- **Spec coverage**: decisions 1-7 → Tasks 10 (LLM interne + source_data), 5-8 (formats + renderers), 8 (PDF Story), 13+15 (card + inline PDF), 10 (TTL reuse), 2 (cost via LLM slot), 12 (hitl_required=False). Systemic-rules coverage: completeness asserts (Tasks 5, 8), formula neutralization (6-7), honest failure (11), one wire serializer (9, 13), GDPR map (3), timeout family (12), i18n ×6 (2, 15, 16).
- **Known verify-at-execution points** (flagged inline, not placeholders): exact import paths for `get_llm_config_for_agent` / `get_structured_output_with_retry` (copy from `return_synthesis.py`), `ParameterSchema` enum-field name, `CapabilitySpec` field set, the timeout-resolution function name, current Alembic head, tool test invocation style (`.func` vs `.ainvoke`), the `@rate_limit` test harness used by the image tool tests, and the presence of the default `document_generation` model in the llm_pricing seeds (zero-cost tracking otherwise).
- **Adversarial re-review (2026-08-17, second pass)**: three defects found and fixed in place — (1) plain signed numbers exempted from formula neutralization (negative values were being defaced), (2) xlsx sheet titles sanitized + deduplicated (openpyxl rejects `[]:*?/\` and duplicates), (3) md heading levels aligned with the PDF renderer's title shift.
- **Type consistency**: `GeneratedDocumentResult` (Task 10) fields consumed identically in Task 11; `PendingDocument`/wire shape (Task 9) matches the `GeneratedDocument` TS interface (Task 14) key-for-key; `SCHEMA_BY_DOC_TYPE`/`RENDERERS`/`DOCUMENT_MIME_TYPES`/`DOCUMENT_EXTENSIONS` all keyed by `DocumentType` with completeness asserts.
