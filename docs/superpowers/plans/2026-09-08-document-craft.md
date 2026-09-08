# Document Craft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (owner rule: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking. **Never run a git command** — the owner commits; every task ends with its gate green instead.

**Goal:** Every generated document (docx, pptx, xlsx, pdf, md, txt, csv) follows the codes of its format — title block, table of contents, numbered headings, headers/footers, named styles, captions, typed spreadsheet columns, 16:9 slides whose text always fits — while the model gains a small semantic vocabulary and a truncated model output is refused instead of rescued.

**Architecture:** The craft belongs to the renderers (a package, one module per format, one typography module, a calibrated text estimator, a column typer, a normalizer that repairs instead of refusing); the meaning belongs to the model (additive schema fields with defaults, published to the prompt with the budgets the renderer enforces). A cross-cutting predicate reads the provider's own "output budget exhausted" verdict before any JSON rescue.

**Tech Stack:** Python 3.14, Pydantic 2, python-docx 1.2.0, python-pptx 1.0.2, openpyxl 3.1.5, PyMuPDF 1.27.2, pytest (`asyncio_mode=auto`), structlog. Office COM (Word/PowerPoint/Excel 16) on the owner's Windows machine for the measurement harness only.

**Spec:** `docs/superpowers/specs/2026-09-08-document-craft-design.md`

## Global Constraints

- Every module stays under 600 logical SLOC; no function with cyclomatic complexity ≥ 15 (block/slide kinds dispatch through dicts).
- `document_generation` never imports `agents` (coupling ratchet); `_call_document_llm` stays in `service.py` (`LLM_SPEND_ROADS`).
- No `"Europe/Paris"` literal, no naive `datetime.now()`; dates through `core.time_utils.format_date_only`; the fallback timezone is the constant `DEFAULT_USER_DISPLAY_TIMEZONE`.
- No user-visible string inline in Python: renderer labels come from `core/i18n_documents.py` (6 languages, `zh-CN` backend-canonical).
- No new bound in a model-facing schema; the existing `level` bound is removed and clamped (design §5.4). `min_length=1` stays.
- Every tunable is a setting from `core/constants.py` defaults, declared in `.env.example` and `.env.prod.example`.
- Tests are unconditional (no skip on a missing key); the Office measurement is a script, never a CI gate.
- Comments, docstrings and documentation in English; Google-style docstrings; MyPy strict.
- Slides are **16:9 landscape** (960 × 540 pt), pinned by a test.
- Plan-level ordering decision: the vocabulary (design §6) lands in Lot 1 so every renderer is written once; the prompt publishes it only in Lot 3, and until then the model never emits the new fields (all default), so behaviour does not change early.

---

## File map

| File | Responsibility |
|---|---|
| `apps/api/src/infrastructure/llm/output_truncation.py` (create) | `is_output_truncated(message)` — the one reading of five provider shapes |
| `apps/api/src/infrastructure/llm/structured_output.py` (modify) | `StructuredOutputTruncatedError`, `_raise_truncated`, checks before rescue, no retry |
| `apps/api/src/domains/document_generation/schemas.py` (modify) | vocabulary (§6), `level` bound removed |
| `apps/api/src/domains/document_generation/context.py` (create) | `RenderContext`, `build_render_context`, `default_render_context` |
| `apps/api/src/core/i18n_documents.py` (create) | `DOCUMENT_LABELS`, `document_label` |
| `apps/api/src/core/config/document_generation.py`, `core/constants.py`, `.env.example`, `.env.prod.example` (modify) | 4 settings + constants |
| `apps/api/src/domains/document_generation/inline.py` (create) | `Span`, `parse_inline`, `strip_inline` |
| `apps/api/src/domains/document_generation/tables.py` (create) | `ColumnKind`, `ColumnType`, `infer_column_types`, `typed_value`, `sanitize_headers`, `normalize_sheet`, `excel_table_name`, `chunk_rows`, `is_excel_legal_name` |
| `apps/api/src/domains/document_generation/normalize.py` (create) | `normalize_sectioned`, `document_is_numbered`, `HeadingNumberer`, `normalize_slides`, `normalize_tabular`, `normalize_content` |
| `apps/api/src/domains/document_generation/fit.py` (create) | `TextFrame`, `line_count`, `text_height`, `fits`, `choose_body_size`, `SlidePlan`, `plan_body`, `fit_title`, `table_font_size`, `rows_per_slide` |
| `apps/api/src/domains/document_generation/typography.py` (create) | constants, `pdf_css` |
| `apps/api/src/domains/document_generation/renderers/__init__.py` (create; `renderers.py` deleted) | `RENDERERS`, `render_document`, `DOCUMENT_MIME_TYPES`, `DOCUMENT_EXTENSIONS` |
| `.../renderers/text.py`, `xlsx.py`, `docx.py`, `docx_ooxml.py`, `pptx.py`, `pptx_geometry.py`, `pdf.py`, `pdf_layout.py` (create) | one format each |
| `apps/api/src/domains/document_generation/service.py` (modify) | `user_id` at the door, truncation → `DocumentOutputTruncatedError`, context, prompt placeholders |
| `apps/api/src/domains/agents/tools/document_generation_tools.py` (modify) | truncation failure branch, `timezone` |
| `apps/api/src/domains/meetings/delivery.py` (modify) | `RenderContext(structure="plain")` |
| `apps/api/src/domains/agents/prompts/v1/document_generation_prompt.txt` (modify) | vocabulary + budgets + cache marker |
| `apps/api/tests/fixtures/document_corpus/*.json` (create) | corpus |
| `apps/api/scripts/document_generation/render_corpus.py`, `measure_office.ps1` (create), `Taskfile.yml`, `.gitignore` (modify) | harness |
| `docs/architecture/ADR-274-*.md`, `ADR-275-*.md`, `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md`, `docs/technical/DOCUMENT_GENERATION.md`, `CLAUDE.md`, `AGENTS.md` | documentation |

Run tests from `apps/api/` with `.venv/Scripts/pytest` (Windows) — e.g. `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation -q`.

---

# Lot 0 — Honesty

### Task 1: The truncation predicate and its error

**Files:**
- Create: `apps/api/src/infrastructure/llm/output_truncation.py`
- Modify: `apps/api/src/infrastructure/llm/structured_output.py` (after `class StructuredOutputError`, line 243-258; `_buffered_invoke` lines ~748-790; `_structured_via_auto_tool`; `get_structured_output_with_retry` loop ~1130-1150)
- Test: `apps/api/tests/unit/infrastructure/llm/test_output_truncation.py`

**Interfaces:**
- Produces: `is_output_truncated(message: Any) -> bool`; `StructuredOutputTruncatedError(StructuredOutputError)`; `_raise_truncated(raw_message, provider, schema_name) -> NoReturn`.

- [ ] **Step 1: Write the failing tests**

```python
"""A truncated structured output is a refusal, never a rescue (ADR-275)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    StructuredOutputTruncatedError,
    _get_native_structured_output,
    _structured_via_auto_tool,
    get_structured_output_with_retry,
)

pytestmark = [pytest.mark.unit]


class _Report(BaseModel):
    title: str
    items: list[str]


@pytest.mark.parametrize(
    "metadata",
    [
        {"finish_reason": "length"},  # OpenAI chat completions, DeepSeek, Perplexity
        {"finish_reason": "MAX_TOKENS"},  # Google
        {"stop_reason": "max_tokens"},  # Anthropic
        {"done_reason": "length"},  # Ollama
        {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},  # Responses
    ],
)
def test_every_provider_shape_is_read(metadata: dict[str, Any]) -> None:
    assert is_output_truncated(AIMessage(content="{", response_metadata=metadata))


@pytest.mark.parametrize(
    "metadata",
    [
        {"finish_reason": "stop"},
        {"finish_reason": "tool_calls"},
        {"stop_reason": "end_turn"},
        {"done_reason": "stop"},
        {"status": "completed"},
        {"status": "incomplete", "incomplete_details": {"reason": "content_filter"}},
        {},
    ],
)
def test_any_other_stop_is_not_a_truncation(metadata: dict[str, Any]) -> None:
    assert not is_output_truncated(AIMessage(content="{}", response_metadata=metadata))


def test_a_non_message_is_not_a_truncation() -> None:
    assert not is_output_truncated(None)
    assert not is_output_truncated("length")


class _FakeStructured:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self._bundle = bundle

    async def ainvoke(self, messages: Any, **_: Any) -> dict[str, Any]:
        return self._bundle


class _FakeLLM:
    """The two attributes the native path reads, and the wrapper it builds."""

    model_name = "gpt-test"

    def __init__(self, bundle: dict[str, Any]) -> None:
        self._bundle = bundle

    def with_structured_output(self, schema: Any, **_: Any) -> _FakeStructured:
        return _FakeStructured(self._bundle)


async def test_a_cut_payload_is_refused_before_any_rescue() -> None:
    """The closable prefix would validate as a shorter report — it must not."""
    raw = AIMessage(
        content='{"title": "Report", "items": ["a", "b", "c"',
        response_metadata={"finish_reason": "length"},
    )
    llm = _FakeLLM({"raw": raw, "parsed": None, "parsing_error": ValueError("EOF")})
    with pytest.raises(StructuredOutputTruncatedError) as excinfo:
        await _get_native_structured_output(
            llm=llm, messages=[], schema=_Report, provider="openai"  # type: ignore[arg-type]
        )
    assert excinfo.value.schema_name == "_Report"
    assert isinstance(excinfo.value, StructuredOutputError)


async def test_the_auto_tool_path_refuses_a_cut_answer() -> None:
    raw = AIMessage(content="", response_metadata={"stop_reason": "max_tokens"})

    class _Bound:
        async def ainvoke(self, payload: Any, **_: Any) -> AIMessage:
            return raw

    class _LLM:
        def bind_tools(self, tools: Any, tool_choice: str) -> _Bound:
            return _Bound()

    with pytest.raises(StructuredOutputTruncatedError):
        await _structured_via_auto_tool(
            llm=_LLM(), messages=[], schema=_Report, reasoning_emit=None, provider="anthropic"  # type: ignore[arg-type]
        )


async def test_the_retry_wrapper_does_not_retry_a_truncation() -> None:
    door = AsyncMock(
        side_effect=StructuredOutputTruncatedError("cut", provider="openai", schema_name="_Report")
    )
    with patch("src.infrastructure.llm.structured_output.get_structured_output", door):
        with pytest.raises(StructuredOutputTruncatedError):
            await get_structured_output_with_retry(
                llm=object(), messages=[], schema=_Report, provider="openai", max_retries=3  # type: ignore[arg-type]
            )
    assert door.await_count == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_output_truncation.py -q`
Expected: FAIL — `ImportError: cannot import name 'is_output_truncated'`.

- [ ] **Step 3: Create the predicate module**

```python
"""One reading of « the provider stopped at its output budget » (ADR-275).

Five adapters spell it five ways, and until 2026-09-08 none of them was read:
a payload cut by ``max_tokens`` reached ``json_recovery``, which closes an open
structure mechanically, and the shortened object validated — a report missing
its last sections was rendered and announced complete (measured: 12 of 100
cuts of a report and 14 of a deck validated as SHORTER documents). When the
repair did not validate, the call was retried three times with the same
prompt, which cannot complete what the budget cut.

The predicate reads the provider's own verdict, never the shape of the text.
Each shape was read in the installed adapter and is pinned by a fixture in
``tests/unit/infrastructure/llm/test_output_truncation.py``.
"""

from __future__ import annotations

from typing import Any

#: ``finish_reason`` values meaning « output budget exhausted »: OpenAI chat
#: completions (and the OpenAI-compatible DeepSeek / Perplexity) say ``length``;
#: Google spells its enum name.
_FINISH_REASONS_TRUNCATED: frozenset[str] = frozenset({"length", "MAX_TOKENS"})


def is_output_truncated(message: Any) -> bool:
    """Whether the provider itself reports the answer as cut at its output budget.

    Args:
        message: The raw ``AIMessage`` — anything carrying ``response_metadata``.

    Returns:
        True on a budget stop; False on any other stop, on missing metadata, and
        on anything that is not a message.
    """
    metadata = getattr(message, "response_metadata", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get("finish_reason") in _FINISH_REASONS_TRUNCATED:
        return True
    if metadata.get("stop_reason") == "max_tokens":  # Anthropic
        return True
    if metadata.get("done_reason") == "length":  # Ollama
        return True
    details = metadata.get("incomplete_details")  # OpenAI Responses API
    return (
        metadata.get("status") == "incomplete"
        and isinstance(details, dict)
        and details.get("reason") == "max_output_tokens"
    )
```

- [ ] **Step 4: Add the error class and the refusal helper to `structured_output.py`**

Right after `class StructuredOutputError` (line 258), and add `NoReturn` to the `typing` import plus `from src.infrastructure.llm.output_truncation import is_output_truncated`:

```python
class StructuredOutputTruncatedError(StructuredOutputError):
    """The provider stopped at its output budget (ADR-275).

    The payload is incomplete by the provider's own account, and the same
    prompt cannot complete it — so the retry wrapper never retries this one.
    """


def _raise_truncated(raw_message: Any, provider: str, schema_name: str) -> NoReturn:
    """Refuse a payload the provider reports as cut — before any rescue can shorten it.

    Args:
        raw_message: The raw ``AIMessage``.
        provider: Provider name (logging and error payload).
        schema_name: Target schema name.

    Raises:
        StructuredOutputTruncatedError: Always.
    """
    raw_text = coerce_content_to_text(getattr(raw_message, "content", None) or "")
    logger.warning(
        "structured_output_truncated",
        provider=provider,
        schema=schema_name,
        raw_chars=len(raw_text),
    )
    raise StructuredOutputTruncatedError(
        f"Structured output for {schema_name} was cut at the provider's output budget",
        provider=provider,
        schema_name=schema_name,
        raw_output=raw_text[:2000] or None,
    )
```

- [ ] **Step 5: Check before the rescue in `_buffered_invoke`**

Replace the head of the inner function body:

```python
            bundle = await raw_structured_llm.ainvoke(messages, **invoke_kwargs)
            raw_message = bundle.get("raw") if isinstance(bundle, dict) else None
            # The provider's own verdict comes first: a cut payload must never
            # reach the rescue below, which would close it into a shorter,
            # valid-looking object (ADR-275).
            if is_output_truncated(raw_message):
                _raise_truncated(raw_message, provider, schema_name)
            parsed = bundle.get("parsed") if isinstance(bundle, dict) else bundle
            if isinstance(parsed, schema):
                return parsed
            parsing_error = bundle.get("parsing_error") if isinstance(bundle, dict) else None
```

(delete the old `raw_message = bundle.get("raw") ...` line further down so it is assigned once).

- [ ] **Step 6: Check in the auto-tool path**

Add `provider: str = "unknown",` to `_structured_via_auto_tool`'s signature after `reasoning_emit`, pass `provider=provider` at its call site in `_get_native_structured_output`, replace "Never raises." in the docstring by "Raises ``StructuredOutputTruncatedError`` when the provider reports the answer cut at its output budget (ADR-275); never raises otherwise.", and insert after the `try/except` that obtains `ai_msg`:

```python
    if is_output_truncated(ai_msg):
        _raise_truncated(ai_msg, provider, schema_name)
```

- [ ] **Step 7: Never retry it**

In `get_structured_output_with_retry`, before `except StructuredOutputError as e:`:

```python
        except StructuredOutputTruncatedError:
            # Deterministic: the same prompt is cut at the same place, and each
            # retry would be paid in full (ADR-275).
            raise
```

- [ ] **Step 8: Run the tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_output_truncation.py tests/unit/infrastructure/llm -q -k "truncat or structured"`
Expected: PASS. Then `.venv/Scripts/pytest tests/unit/infrastructure/llm -q` (the usage-guard chokepoint test still names both doors) — PASS.

- [ ] **Step 9: Gate**

Run: `task lint:backend` — 0 errors (MyPy strict sees `NoReturn`; Ruff sees the ordered imports).

---

### Task 2: The document door — owner and honest failure

**Files:**
- Modify: `apps/api/src/domains/document_generation/service.py` (`_call_document_llm` lines 66-113; `generate_document_for_user` lines 123-165)
- Modify: `apps/api/src/domains/agents/tools/document_generation_tools.py` (imports; the `try/except` around `generate_document_for_user`, lines ~134-155)
- Test: `apps/api/tests/unit/domains/document_generation/test_service.py`, `apps/api/tests/unit/domains/agents/tools/test_document_generation_tools.py`

**Interfaces:**
- Produces: `DocumentOutputTruncatedError(budget_tokens: int)` in `service.py`; `_call_document_llm(..., user_id: uuid.UUID, ...)`.

- [ ] **Step 1: Write the failing tests (service)**

Append to `test_service.py`:

```python
@pytest.mark.unit
async def test_the_structured_door_receives_the_owner(monkeypatch) -> None:
    """ADR-272: the caller knows the account, so the door is told (design §11)."""
    from src.domains.document_generation import service as svc
    from src.domains.document_generation.schemas import TableSheet, TabularContent

    door = AsyncMock(
        return_value=TabularContent(
            filename_stem="x", title="T", sheets=[TableSheet(name="S", headers=["a"], rows=[])]
        )
    )
    user_id = uuid.uuid4()
    with (
        patch.object(svc, "get_structured_output_with_retry", door),
        patch.object(svc, "get_llm", lambda _type: object()),
        patch.object(svc, "get_llm_config_for_agent", lambda *_: MagicMock(provider="openai")),
        patch.object(svc, "load_document_prompt", lambda *_: "{language}{instructions}{source_data}"),
    ):
        await svc._call_document_llm(
            doc_type=DocumentType.CSV,
            instructions="i",
            source_data="",
            language="fr",
            config=None,
            user_id=user_id,
        )
    assert door.await_args.kwargs["user_id"] == user_id


@pytest.mark.unit
async def test_a_truncated_document_is_an_explicit_failure_naming_the_budget(
    tmp_path, monkeypatch
) -> None:
    from src.core.config import settings as app_settings
    from src.domains.document_generation import service as svc
    from src.infrastructure.llm.structured_output import StructuredOutputTruncatedError

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    cut = StructuredOutputTruncatedError("cut", provider="openai", schema_name="SectionedContent")
    with (
        patch.object(svc, "_call_document_llm", AsyncMock(side_effect=cut)),
        patch.object(svc, "get_llm_config_for_agent", lambda *_: MagicMock(max_tokens=16000)),
    ):
        with pytest.raises(svc.DocumentOutputTruncatedError) as excinfo:
            await svc.generate_document_for_user(
                user_id=uuid.uuid4(),
                conversation_id="conv-trunc",
                doc_type=DocumentType.DOCX,
                instructions="x",
                source_data="",
                requested_filename="",
                language="fr",
                config=None,
            )
    assert excinfo.value.budget_tokens == 16000
    # Nothing was written and no card was queued.
    from src.domains.document_generation.document_store import get_and_clear_pending_documents

    assert not any(tmp_path.iterdir())
    assert get_and_clear_pending_documents("conv-trunc") == []
```

Add `MagicMock` to the `unittest.mock` import of that file. Existing tests that call `svc.generate_document_for_user` keep their signature (no new required parameter in this task).

- [ ] **Step 2: Write the failing test (tool)**

Append to `test_document_generation_tools.py`, following its patch style (`_runtime()`, `_user()`, `_fake_settings()` helpers already there):

```python
@pytest.mark.unit
async def test_a_truncated_document_names_the_budget_and_produces_no_card() -> None:
    from src.domains.agents.tools import document_generation_tools as mod
    from src.domains.document_generation.service import DocumentOutputTruncatedError

    with (
        patch.object(mod, "settings", _fake_settings()),
        patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
        patch.object(
            mod,
            "generate_document_for_user",
            AsyncMock(side_effect=DocumentOutputTruncatedError(16000)),
        ),
    ):
        result = await mod.generate_document.coroutine(  # the registered tool exposes its coroutine
            instructions="long", doc_type="docx", runtime=_runtime()
        )
    assert result.success is False
    assert "16000" in result.message
    assert "No document was produced" in result.message
```

(Use the same invocation shape the file's other tests use to call the tool — copy it from `test_service_receives_user_language_and_context`.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation/test_service.py tests/unit/domains/agents/tools/test_document_generation_tools.py -q`
Expected: FAIL — `TypeError: unexpected keyword 'user_id'`, `AttributeError: DocumentOutputTruncatedError`.

- [ ] **Step 4: Implement in `service.py`**

Imports: add `from src.infrastructure.llm.structured_output import StructuredOutputTruncatedError, get_structured_output_with_retry`.

```python
class DocumentOutputTruncatedError(Exception):
    """The document LLM was cut at the slot's output budget — nothing usable exists.

    Raised instead of a document: a truncated payload is never rendered
    (ADR-275), and the tool turns this into an explicit failure naming the
    budget so the caller can ask for a shorter document.
    """

    def __init__(self, budget_tokens: int) -> None:
        super().__init__(f"document output cut at the slot budget of {budget_tokens} tokens")
        self.budget_tokens = budget_tokens
```

`_call_document_llm` gains `user_id: uuid.UUID` (keyword-only, documented "Account the call belongs to; the door asks its ceiling (ADR-272)") and passes `user_id=user_id` to `get_structured_output_with_retry`.

In `generate_document_for_user`, replace the `content = await _call_document_llm(...)` call:

```python
    slot = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE)
    try:
        content = await _call_document_llm(
            doc_type=doc_type,
            instructions=instructions,
            source_data=source_data[:cap],
            language=language,
            config=config,
            user_id=user_id,
        )
    except StructuredOutputTruncatedError as exc:
        logger.warning(
            "document_generation_output_truncated",
            user_id=str(user_id),
            doc_type=doc_type.value,
            budget_tokens=slot.max_tokens,
        )
        raise DocumentOutputTruncatedError(slot.max_tokens) from exc
```

- [ ] **Step 5: Implement in the tool**

Import `DocumentOutputTruncatedError` next to `generate_document_for_user`; before the generic `except Exception as exc:` add:

```python
    except DocumentOutputTruncatedError as exc:
        logger.warning(
            "document_generation_too_long",
            doc_type=parsed_type.value,
            user_id=str(user_id),
            budget_tokens=exc.budget_tokens,
        )
        return UnifiedToolOutput.failure(
            message=(
                "The document exceeded the output budget of the document_generation slot "
                f"({exc.budget_tokens} tokens). No document was produced. Ask for a shorter "
                "document, or split it into several documents."
            ),
            error_code="TOOL_ERROR",
        )
```

- [ ] **Step 6: Run the tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation tests/unit/domains/agents/tools/test_document_generation_tools.py -q`
Expected: PASS.

- [ ] **Step 7: Gate**

Run: `task lint:backend && cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_every_spend_site_is_bounded.py tests/unit/infrastructure/llm/test_llm_spend_road_completeness.py -q`
Expected: 0 errors, PASS (the module path did not move).

---

### Task 3: ADR-275

**Files:**
- Create: `docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md`
- Modify: `docs/architecture/ADR_INDEX.md` (append after the ADR-273 entry, same format: `### ADR-275 : …`, `**Fichier**`, `**Décision** :` in French)

- [ ] **Step 1: Write the ADR** (English, header format of ADR-273):

```markdown
# ADR-275 — A truncated structured output is a refusal, never a rescue

**Status:** Accepted — 2026-09-08
**Amends:** ADR-220 (JSON recovery), ADR-226 (document generation — "an overflow fails honestly"), ADR-272 (every spend site answers to both ceilings)

---

## Context

`json_recovery.extract_json_payload` closes an open structure mechanically —
written for fences, prose and trailing commas — and `_rescue_structured_from_text`
validates what is left. Measured 2026-09-08 by cutting a valid document payload at
100 positions: **12 report cuts and 14 deck cuts validated as SHORTER documents**.
A document cut by `max_tokens` was therefore rendered, stored and announced
"generated successfully", while ADR-226 states that an overflow fails honestly.
When the repair did not validate, the call was retried three times with the same
prompt: a truncation is deterministic, so each retry was paid in full for nothing.
`finish_reason` was read nowhere in `structured_output.py`.

Every structured caller was exposed — meeting minutes, the relationship debrief,
the planner — not only documents.

A second finding on the same door: `resolve_owner` reads
`config["metadata"]["user_id"]`, and LangGraph never puts it there (probed: only
`thread_id` is merged into the run metadata). The document service knew the
account and did not pass it, so at that door only the instance ceiling was
asked; the per-account ceiling held only because the turn entrance asks it.
`test_every_spend_site_is_bounded` accepts `get_structured_output_with_retry`
by NAME ("carrying the owner") — this call carried nothing.

## Decision

1. **One predicate reads the provider's own verdict**
   (`infrastructure/llm/output_truncation.py::is_output_truncated`): OpenAI chat
   `finish_reason=length`, Responses `status=incomplete` +
   `incomplete_details.reason=max_output_tokens`, Anthropic
   `stop_reason=max_tokens`, Ollama `done_reason=length`, Google
   `finish_reason=MAX_TOKENS`. Each shape was read in the installed adapter and
   is pinned by a fixture.
2. **It runs before any rescue**, in the buffered path (on the `include_raw`
   bundle) and in the auto-tool path, and raises
   `StructuredOutputTruncatedError(StructuredOutputError)`.
3. **The retry wrapper never retries it.** Callers keep handling the parent
   class by inheritance; the document tool names the budget in its failure.
4. **The document service passes `user_id` to the door.** The guard's blind
   spot (a "bounded caller" accepted by name) is recorded here; tightening it
   to require the `user_id=` keyword is a follow-up audit, because other
   `TURN` modules may legitimately rely on the entrance.

## Consequences

- Every structured caller now fails honestly where it used to receive a
  silently shortened object or three paid retries. Watched through the
  `structured_output_truncated` log event (no new metric: a metric nobody
  panels is a metric nobody reads — ADR-148).
- The streaming reasoning path has no raw message in hand; it falls back to the
  buffered call, which does.
- ADR-226's sentence "an overflow fails honestly rather than shipping a silently
  truncated file" is now true.
```

- [ ] **Step 2: Append the ADR_INDEX entry** (French, mirroring the ADR-273 entry's shape: title line, `**Fichier**`, `**Décision** :` one paragraph summarising the four points and the two measurements).

- [ ] **Step 3: Gate**

Run: `git add -N docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md` is a git action — **do not run it**; instead run `task lint:docs:preview` (it reads what `git add -A` would stage). Expected: no broken link, no orphan (ADR files are HISTORICAL for the orphan rule). If the preview reports the ADR as un-indexed, the ADR_INDEX entry title must contain `ADR-275` exactly.

---

# Lot 1 — Vocabulary and shared modules

### Task 4: The vocabulary (schemas)

**Files:**
- Modify: `apps/api/src/domains/document_generation/schemas.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_schemas.py`

**Interfaces:**
- Produces: `SectionBlock.kind ∈ {heading, paragraph, bullets, numbered, quote, callout, table}`, `SectionBlock.caption: str`, `SectionedContent.subtitle: str`, `SlideColumn(heading, bullets)`, `Slide.kind ∈ {content, section, comparison, table}`, `Slide.subtitle`, `Slide.columns`, `Slide.table`, `SlideContent.subtitle`. `SectionBlock.level` has no bound.

- [ ] **Step 1: Write the failing tests** (replace `test_heading_level_bounds`, add the rest; import `TableSheet` too):

```python
    def test_heading_level_is_not_bounded_by_the_schema(self) -> None:
        """A bound refuses the whole document (ADR-269 lesson); levels are clamped downstream."""
        assert SectionBlock(kind="heading", text="t", level=9).level == 9
        assert SectionBlock(kind="heading", text="t", level=0).level == 0

    def test_new_kinds_and_fields_default(self) -> None:
        block = SectionBlock(kind="callout", text="watch out")
        assert block.caption == ""
        assert SectionBlock(kind="numbered", items=["a"]).items == ["a"]
        assert SectionBlock(kind="quote", text="q").text == "q"
        assert SectionedContent(filename_stem="x", title="t", blocks=[block]).subtitle == ""

    def test_slide_vocabulary_defaults(self) -> None:
        from src.domains.document_generation.schemas import Slide, SlideColumn

        slide = Slide(title="t")
        assert slide.kind == "content"
        assert slide.subtitle == "" and slide.columns == [] and slide.table is None
        cmp_ = Slide(
            title="A vs B",
            kind="comparison",
            columns=[SlideColumn(heading="A", bullets=["x"]), SlideColumn(heading="B")],
        )
        assert cmp_.columns[1].bullets == []
        assert SlideContent(filename_stem="d", title="D", slides=[slide]).subtitle == ""

    def test_the_schema_the_model_sees_carries_no_bound(self) -> None:
        """Only min_length on the three lists stays (nothing to render otherwise)."""
        import json

        for schema in (TabularContent, SectionedContent, SlideContent):
            text = json.dumps(schema.model_json_schema())
            for keyword in ('"maximum"', '"minimum"', '"maxLength"', '"maxItems"', '"pattern"'):
                assert keyword not in text, f"{schema.__name__} publishes {keyword}"

    def test_strict_verdict_is_unchanged(self) -> None:
        from src.infrastructure.llm.strict_schema import _analyze_schema_strict_compatibility

        for schema in (TabularContent, SectionedContent, SlideContent):
            compatible, reason = _analyze_schema_strict_compatibility(schema)
            assert compatible, f"{schema.__name__}: {reason}"

    def test_descriptions_are_one_line(self) -> None:
        """Class docstrings are sent to the model as ``description``."""
        for schema in (TabularContent, SectionedContent, SlideContent, SectionBlock, TableSheet):
            assert "\n" not in (schema.__doc__ or "").strip()
```

- [ ] **Step 2: Run** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/document_generation/test_schemas.py -q` → FAIL (`ValidationError` on level 9, unknown kinds, missing `SlideColumn`).

- [ ] **Step 3: Rewrite the models in `schemas.py`** (module docstring names ADR-274; class docstrings stay ONE line; `DocumentType`, `DocumentContent`, `SCHEMA_BY_DOC_TYPE` and the completeness assert unchanged):

```python
class TableSheet(BaseModel):
    """A single table: one CSV file, one XLSX worksheet, or an embedded table."""

    name: str = Field(description="Sheet/table name (short, human readable).")
    headers: list[str] = Field(description="Column headers, in order, unique and non-empty.")
    rows: list[list[str]] = Field(
        description="Data rows; every cell as a string, aligned with headers."
    )


class TabularContent(BaseModel):
    """Content for csv/xlsx outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (used as metadata).")
    sheets: list[TableSheet] = Field(
        min_length=1, description="Worksheets; csv output uses ONLY the first sheet."
    )


class SectionBlock(BaseModel):
    """One block of a sectioned document, rendered in order."""

    kind: Literal["heading", "paragraph", "bullets", "numbered", "quote", "callout", "table"] = (
        Field(
            description=(
                "What the block is: a heading, running text, an unordered list, an "
                "ordered sequence, a verbatim quote, a callout (warning or key "
                "takeaway), or a table."
            )
        )
    )
    # No bound here: an out-of-range level is clamped at normalization, never
    # refused — a bound fails the whole document three paid times over.
    level: int = Field(default=2, description="Heading level 1-4 (headings only).")
    text: str = Field(
        default="", description="Text for heading, paragraph, quote and callout blocks."
    )
    items: list[str] = Field(
        default_factory=list, description="Items (bullets and numbered only)."
    )
    table: TableSheet | None = Field(default=None, description="Table payload (table only).")
    caption: str = Field(default="", description="Caption naming a table (table only).")


class SectionedContent(BaseModel):
    """Content for docx/pdf/md/txt outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (rendered as the top heading).")
    subtitle: str = Field(
        default="", description="One line under the title: audience or purpose."
    )
    blocks: list[SectionBlock] = Field(min_length=1, description="Ordered content blocks.")


class SlideColumn(BaseModel):
    """One side of a comparison slide."""

    heading: str = Field(description="Short heading of this side.")
    bullets: list[str] = Field(
        default_factory=list, description="Bullet points of this side."
    )


class Slide(BaseModel):
    """A single presentation slide."""

    title: str = Field(description="Slide title: an assertion or a precise topic.")
    kind: Literal["content", "section", "comparison", "table"] = Field(
        default="content",
        description=(
            "What the slide is: content (bullets), a section opener, a comparison "
            "of two sides, or data (a table)."
        ),
    )
    subtitle: str = Field(
        default="",
        description="Tagline of a section opener or lead line of a content slide.",
    )
    bullets: list[str] = Field(default_factory=list, description="Bullet points (content).")
    columns: list[SlideColumn] = Field(
        default_factory=list, description="The two sides (comparison)."
    )
    table: TableSheet | None = Field(default=None, description="Data (table).")
    notes: str = Field(default="", description="Speaker notes: the full sentences.")


class SlideContent(BaseModel):
    """Content for pptx output."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Presentation title (cover slide).")
    subtitle: str = Field(
        default="", description="Cover subtitle: audience, occasion or date."
    )
    slides: list[Slide] = Field(min_length=1, description="Ordered slides.")
```

- [ ] **Step 4: Run** the schema tests → PASS; then `.venv/Scripts/pytest tests/unit/domains/document_generation tests/unit/domains/meetings tests/unit/domains/agents/services/catalogue/test_catalogue_parameter_bounds.py -q` → PASS.

- [ ] **Step 5: Gate** `task lint:backend` → 0 errors.

---

### Task 5: Settings, constants, labels and the render context

**Files:**
- Modify: `apps/api/src/core/constants.py` (after `DOCUMENT_GENERATION_LLM_TYPE`, line ~5362)
- Modify: `apps/api/src/core/config/document_generation.py`
- Modify: `.env.example` (after line 2356), `.env.prod.example` (after line 2034)
- Create: `apps/api/src/core/i18n_documents.py`, `apps/api/src/domains/document_generation/context.py`
- Test: `apps/api/tests/unit/core/config/test_document_generation_settings.py`, `apps/api/tests/unit/core/test_i18n_documents.py`, `apps/api/tests/unit/domains/document_generation/test_context.py`

**Interfaces:**
- Produces: settings `document_generation_page_size: Literal["a4","letter"]`, `document_generation_toc_min_headings: int`, `document_generation_slide_max_bullets: int`, `document_generation_slide_max_bullet_chars: int`; constants `DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT`, `DOCUMENT_GENERATION_TOC_MIN_HEADINGS_DEFAULT`, `DOCUMENT_GENERATION_SLIDE_MAX_BULLETS_DEFAULT`, `DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS_DEFAULT`, `DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN`; `document_label(language, key, **values) -> str`; `RenderContext(language, timezone, page_size, generated_at, structure)` with `.label(key, **values)` and `.date_line`; `build_render_context(*, language, timezone, generated_at, structure="auto")`; `default_render_context()`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/core/test_i18n_documents.py`:

```python
"""Renderer-generated labels exist in the six languages with the same keys (ADR-274)."""

import re

import pytest

from src.core.i18n_documents import (
    DOCUMENT_LABELS,
    SUPPORTED_DOCUMENT_LABEL_LANGUAGES,
    document_label,
)

pytestmark = [pytest.mark.unit]
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_six_languages_same_keys_same_placeholders() -> None:
    assert set(DOCUMENT_LABELS) == set(SUPPORTED_DOCUMENT_LABEL_LANGUAGES)
    assert set(DOCUMENT_LABELS) == {"fr", "en", "de", "es", "it", "zh-CN"}
    reference = DOCUMENT_LABELS["en"]
    for language, table in DOCUMENT_LABELS.items():
        assert set(table) == set(reference), language
        for key, template in table.items():
            assert set(_PLACEHOLDER.findall(template)) == set(
                _PLACEHOLDER.findall(reference[key])
            ), (language, key)


def test_labels_render_and_normalise_the_locale() -> None:
    assert document_label("fr-FR", "documents.page_of", page=2, total=5) == "Page 2 / 5"
    assert document_label("zh", "documents.toc_heading") == "目录"
    assert document_label("xx", "documents.table_label", n=3) == "Table 3"
```

`tests/unit/domains/document_generation/test_context.py`:

```python
"""RenderContext: language normalised, date in the reader's zone, page from settings."""

from datetime import UTC, datetime

import pytest

from src.domains.document_generation.context import (
    RenderContext,
    build_render_context,
    default_render_context,
)

pytestmark = [pytest.mark.unit]


def test_build_normalises_language_and_reads_the_page_setting(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_page_size", "letter")
    ctx = build_render_context(
        language="zh",
        timezone="Asia/Shanghai",
        generated_at=datetime(2026, 9, 8, 23, 30, tzinfo=UTC),
    )
    assert ctx.language == "zh-CN"
    assert ctx.page_size == "letter"
    assert ctx.structure == "auto"
    assert "2026" in ctx.date_line and "9" in ctx.date_line  # 9 September in Shanghai


def test_no_generated_at_means_no_date_line() -> None:
    assert RenderContext(language="fr").date_line == ""


def test_default_context_states_nothing() -> None:
    ctx = default_render_context()
    assert ctx.generated_at is None
    assert ctx.language
    assert ctx.page_size in ("a4", "letter")


def test_label_goes_through_the_document_labels() -> None:
    assert RenderContext(language="de").label("documents.column_label", n=2) == "Spalte 2"
```

Extend `test_document_generation_settings.py`: add the four env vars to the `delenv` list; assert `s.document_generation_page_size == DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT` and the three ints against their constants; add:

```python
    def test_page_size_is_a_closed_choice(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentGenerationSettings(document_generation_page_size="a5")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run** the three files → FAIL (imports / attributes).

- [ ] **Step 3: Constants** — append to the document generation section of `core/constants.py`:

```python
# Page size of docx/pdf outputs (ISO A4 everywhere except North America; a
# deployment picks). Slides are 16:9 landscape and not configurable.
DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT: Literal["a4", "letter"] = "a4"

# Headings from which a document is "long": table of contents, heading
# numbering and a page break before each part switch on TOGETHER (ADR-274).
DOCUMENT_GENERATION_TOC_MIN_HEADINGS_DEFAULT: int = 5

# Slide density budgets PUBLISHED to the writer and ENFORCED by the renderer
# (beyond them the slide is split — never overflowed; ADR-184, ADR-274).
DOCUMENT_GENERATION_SLIDE_MAX_BULLETS_DEFAULT: int = 6
DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS_DEFAULT: int = 110

# Words the writer may spend per output token of the slot (JSON overhead and
# the token/word ratio folded in). A conversion factor, not a tunable.
DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN: float = 0.55
```

(`Literal` is imported from `typing` at the top of `constants.py`; add it if absent.)

- [ ] **Step 4: Settings** — add a "Rendering" section to `DocumentGenerationSettings` (import `Literal` and the four constants):

```python
    document_generation_page_size: Literal["a4", "letter"] = Field(
        default=DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT,
        description="Page size of docx/pdf documents: a4 or letter (slides are 16:9).",
    )
    document_generation_toc_min_headings: int = Field(
        default=DOCUMENT_GENERATION_TOC_MIN_HEADINGS_DEFAULT,
        ge=2,
        le=50,
        description=(
            "Headings from which a document gets a table of contents, numbered "
            "headings and a page break before each part."
        ),
    )
    document_generation_slide_max_bullets: int = Field(
        default=DOCUMENT_GENERATION_SLIDE_MAX_BULLETS_DEFAULT,
        ge=2,
        le=12,
        description=(
            "Bullets per slide published to the writer; beyond it the renderer "
            "splits the slide."
        ),
    )
    document_generation_slide_max_bullet_chars: int = Field(
        default=DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS_DEFAULT,
        ge=40,
        le=400,
        description=(
            "Characters per bullet published to the writer; beyond it the "
            "renderer shrinks the text, then splits the slide."
        ),
    )
```

`.env.example` (after the `DOCUMENT_GENERATION_MAX_SOURCE_CHARS` line):

```
DOCUMENT_GENERATION_PAGE_SIZE=a4                            # docx/pdf page size: a4 or letter (slides are 16:9)
DOCUMENT_GENERATION_TOC_MIN_HEADINGS=5                      # headings from which a document gets a TOC, numbering and part breaks
DOCUMENT_GENERATION_SLIDE_MAX_BULLETS=6                     # slide density budget published to the writer, enforced by the renderer
DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS=110              # bullet length budget published to the writer, enforced by the renderer
```

`.env.prod.example`: the same four keys with their values, after `DOCUMENT_GENERATION_MAX_SOURCE_CHARS=60000`.

- [ ] **Step 5: Create `core/i18n_documents.py`**

```python
"""Labels a document renderer writes on its own (ADR-274).

The model writes the document in the reader's language; the renderer adds a
handful of words of its own — the table of contents heading, the page footer,
a table label, a generated column name — and those must exist in the six
languages too. Data module (ratchet-exempt like ``i18n_effects``): the SAME
key set under every language, checked by ``tests/unit/core/test_i18n_documents.py``.
"""

from __future__ import annotations

from src.core.i18n import normalize_language

#: Backend-canonical codes every label exists in.
SUPPORTED_DOCUMENT_LABEL_LANGUAGES: tuple[str, ...] = ("fr", "en", "de", "es", "it", "zh-CN")

DOCUMENT_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "documents.toc_heading": "Sommaire",
        "documents.page_of": "Page {page} / {total}",
        "documents.table_label": "Tableau {n}",
        "documents.column_label": "Colonne {n}",
    },
    "en": {
        "documents.toc_heading": "Contents",
        "documents.page_of": "Page {page} of {total}",
        "documents.table_label": "Table {n}",
        "documents.column_label": "Column {n}",
    },
    "de": {
        "documents.toc_heading": "Inhalt",
        "documents.page_of": "Seite {page} von {total}",
        "documents.table_label": "Tabelle {n}",
        "documents.column_label": "Spalte {n}",
    },
    "es": {
        "documents.toc_heading": "Índice",
        "documents.page_of": "Página {page} de {total}",
        "documents.table_label": "Tabla {n}",
        "documents.column_label": "Columna {n}",
    },
    "it": {
        "documents.toc_heading": "Indice",
        "documents.page_of": "Pagina {page} di {total}",
        "documents.table_label": "Tabella {n}",
        "documents.column_label": "Colonna {n}",
    },
    "zh-CN": {
        "documents.toc_heading": "目录",
        "documents.page_of": "第 {page} 页，共 {total} 页",
        "documents.table_label": "表 {n}",
        "documents.column_label": "列 {n}",
    },
}


def document_label(language: str, key: str, **values: object) -> str:
    """A renderer label in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.
        key: One of the ``documents.*`` keys.
        **values: Placeholder values.

    Returns:
        The rendered label; English when the language is unknown.
    """
    table = DOCUMENT_LABELS.get(normalize_language(language), DOCUMENT_LABELS["en"])
    template = table.get(key) or DOCUMENT_LABELS["en"][key]
    return template.format(**values)
```

- [ ] **Step 6: Create `document_generation/context.py`**

```python
"""What a renderer needs beyond the content (ADR-274).

The content says what the document contains; the context says for whom and
where: the reader's language (the labels the renderer writes itself), their
timezone (the date on the title block), the deployment's page size, and whether
the long-document apparatus — table of contents, heading numbering, page breaks
before parts — may switch itself on. A caller that already shapes its document
(meeting minutes) pins ``structure="plain"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import normalize_language
from src.core.i18n_documents import document_label
from src.core.time_utils import format_date_only

PageSize = Literal["a4", "letter"]
Structure = Literal["auto", "plain"]


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Reader- and deployment-side facts a renderer reads."""

    language: str
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE
    page_size: PageSize = "a4"
    generated_at: datetime | None = None
    structure: Structure = "auto"

    def label(self, key: str, **values: object) -> str:
        """A renderer-generated label in the reader's language."""
        return document_label(self.language, key, **values)

    @property
    def date_line(self) -> str:
        """The localized generation date, or an empty string when no date is wanted."""
        if self.generated_at is None:
            return ""
        return format_date_only(self.generated_at, self.timezone, self.language)


def build_render_context(
    *,
    language: str,
    timezone: str,
    generated_at: datetime,
    structure: Structure = "auto",
) -> RenderContext:
    """The context of a document generated for a person.

    Args:
        language: Any locale spelling.
        timezone: The person's IANA timezone (falls back to the central default).
        generated_at: Aware generation instant.
        structure: ``auto`` (long-document apparatus by threshold) or ``plain``.

    Returns:
        The context, page size taken from settings.
    """
    return RenderContext(
        language=normalize_language(language),
        timezone=timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        page_size=settings.document_generation_page_size,
        generated_at=generated_at,
        structure=structure,
    )


def default_render_context() -> RenderContext:
    """The context of a caller that states nothing: deployment language and page, no date."""
    return RenderContext(
        language=normalize_language(settings.default_language),
        page_size=settings.document_generation_page_size,
    )
```

- [ ] **Step 7: Run** the three test files → PASS. **Gate:** `task lint:backend && task lint:hygiene` → 0 errors (the `.env.example` completeness check sees the four keys).

---

### Task 6: Inline emphasis (`inline.py`)

**Files:**
- Create: `apps/api/src/domains/document_generation/inline.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_inline.py`

**Interfaces:**
- Produces: `Span(text, bold=False, italic=False, code=False)`, `parse_inline(text) -> list[Span]`, `strip_inline(text) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
"""Inline emphasis: one span list for docx/pptx/pdf; orphans stay literal (ADR-274)."""

import pytest

from src.domains.document_generation.inline import Span, parse_inline, strip_inline

pytestmark = [pytest.mark.unit]


def test_bold_italic_code_and_plain() -> None:
    assert parse_inline("a **b** c *d* e `f` g") == [
        Span("a "), Span("b", bold=True), Span(" c "), Span("d", italic=True),
        Span(" e "), Span("f", code=True), Span(" g"),
    ]


def test_bold_italic_combined_and_underscore_italic() -> None:
    assert parse_inline("***x*** _y_") == [Span("x", bold=True, italic=True), Span(" "), Span("y", italic=True)]


@pytest.mark.parametrize("text", ["2 * 3 * 4", "a*b*c", "snake_case_name", "price: 5*", "**unclosed"])
def test_orphan_and_intra_word_markers_stay_literal(text: str) -> None:
    assert parse_inline(text) == [Span(text)]


def test_links_become_text_and_url() -> None:
    assert parse_inline("see [LIA](https://example.org/x) now") == [Span("see LIA (https://example.org/x) now")]


def test_escapes_and_cjk() -> None:
    assert parse_inline(r"a \*literal\* **粗体**") == [Span("a *literal* "), Span("粗体", bold=True)]


def test_empty_and_strip() -> None:
    assert parse_inline("") == []
    assert strip_inline("**b** and *i* and `c`") == "b and i and c"
```

- [ ] **Step 2: Run** → FAIL (import).

- [ ] **Step 3: Implement**

```python
"""Inline emphasis a model writes and a renderer turns into runs (ADR-274).

The prompt allows ``**bold**`` and ``*italic*``; models also produce
``_italic_``, ```code``` and ``[text](url)``. Every rich renderer (docx, pptx,
pdf) consumes the SAME span list, so an emphasis renders identically in the
three; md passes the markup through and txt strips it. Unmatched or intra-word
markers are literal text — a stray asterisk in a price list must survive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_TOKEN = re.compile(
    r"(?P<bi>\*\*\*(?=\S).+?(?<=\S)\*\*\*)"
    r"|(?P<b>\*\*(?=\S).+?(?<=\S)\*\*)"
    r"|(?P<i>(?<![\w*])\*(?=[^\s*]).+?(?<=[^\s*])\*(?![\w*]))"
    r"|(?P<u>(?<!\w)_(?=\S).+?(?<=\S)_(?!\w))"
    r"|(?P<c>`[^`\n]+`)"
)
#: Escaped markers are hidden from the tokenizer, then restored as plain text.
_ESCAPES: dict[str, str] = {r"\*": "\x00", r"\_": "\x01", r"\`": "\x02"}
_UNESCAPES: dict[str, str] = {"\x00": "*", "\x01": "_", "\x02": "`"}


@dataclass(frozen=True, slots=True)
class Span:
    """A run of text with its emphasis."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


def _restore(text: str) -> str:
    for hidden, marker in _UNESCAPES.items():
        text = text.replace(hidden, marker)
    return text


def parse_inline(text: str) -> list[Span]:
    """Split a line into emphasis spans.

    Args:
        text: Model text, possibly carrying ``**``, ``*``, ``_``, backticks and
            markdown links.

    Returns:
        Spans in order; an empty text yields no span. Links become
        ``text (url)`` — a document is read on paper too.
    """
    if not text:
        return []
    for escaped, hidden in _ESCAPES.items():
        text = text.replace(escaped, hidden)
    text = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    spans: list[Span] = []
    position = 0
    for match in _TOKEN.finditer(text):
        if match.start() > position:
            spans.append(Span(_restore(text[position : match.start()])))
        token, kind = match.group(0), match.lastgroup
        if kind == "bi":
            spans.append(Span(_restore(token[3:-3]), bold=True, italic=True))
        elif kind == "b":
            spans.append(Span(_restore(token[2:-2]), bold=True))
        elif kind in ("i", "u"):
            spans.append(Span(_restore(token[1:-1]), italic=True))
        else:
            spans.append(Span(_restore(token[1:-1]), code=True))
        position = match.end()
    if position < len(text):
        spans.append(Span(_restore(text[position:])))
    return spans


def strip_inline(text: str) -> str:
    """The plain text of a line, markers removed."""
    return "".join(span.text for span in parse_inline(text))
```

- [ ] **Step 4: Run** → PASS (adjust the `"**unclosed"` and `"price: 5*"` expectations only if the regex proves them different — the intent is: literal). **Gate:** `task lint:backend`.

---

### Task 7: Tables — typing, headers, names, chunks (`tables.py`)

**Files:**
- Create: `apps/api/src/domains/document_generation/tables.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_tables.py`

**Interfaces:**
- Produces: `ColumnKind` (TEXT, INT, DECIMAL, PERCENT, DATE, DATETIME), `ColumnType(kind, decimals)` with `.numeric` and `.number_format`, `infer_column_types(headers, rows) -> list[ColumnType]`, `typed_value(cell, column) -> str | int | float | date | datetime | None`, `sanitize_headers(headers, language) -> list[str]`, `normalize_sheet(sheet, language) -> TableSheet | None`, `excel_table_name(index) -> str`, `is_excel_legal_name(name) -> bool`, `chunk_rows(rows, size) -> list[list[list[str]]]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tables: typing by column unanimity, legal headers and names, chunks (ADR-274)."""

from datetime import date, datetime

import pytest

from src.domains.document_generation.schemas import TableSheet
from src.domains.document_generation.tables import (
    ColumnKind,
    chunk_rows,
    excel_table_name,
    infer_column_types,
    is_excel_legal_name,
    normalize_sheet,
    sanitize_headers,
    typed_value,
)

pytestmark = [pytest.mark.unit]


def _types(*columns: list[str]) -> list[ColumnKind]:
    rows = [list(row) for row in zip(*columns, strict=True)]
    return [t.kind for t in infer_column_types([f"h{i}" for i in range(len(columns))], rows)]


def test_unanimous_columns_are_typed_and_mixed_ones_are_text() -> None:
    assert _types(["1", "2", ""], ["1.5", "2", "3.25"], ["12%", "3.5 %", "0%"]) == [
        ColumnKind.INT, ColumnKind.DECIMAL, ColumnKind.PERCENT
    ]
    assert _types(["2026-09-08", "2026-01-01"], ["2026-09-08 14:30", "2026-09-08T09:00:00"]) == [
        ColumnKind.DATE, ColumnKind.DATETIME
    ]
    assert _types(["1", "x"], ["2026-13-45", "2026-01-01"], ["1", "2026-01-01"]) == [ColumnKind.TEXT] * 3


def test_codes_years_phones_and_formulas_stay_text_or_int_as_data_demands() -> None:
    assert _types(["67000", "01000"])[0] is ColumnKind.TEXT  # a leading zero protects the column
    assert _types(["2026", "2027"])[0] is ColumnKind.INT  # years are ints, formatted without separator
    assert _types(["+33 6 12"])[0] is ColumnKind.TEXT
    assert _types(["=1+1", "2"])[0] is ColumnKind.TEXT


def test_decimals_follow_the_widest_cell_and_formats_are_derived() -> None:
    column = infer_column_types(["h"], [["1.5"], ["2.125"], ["3"]])[0]
    assert column.kind is ColumnKind.DECIMAL and column.decimals == 3
    assert column.number_format == "0.000"
    percent = infer_column_types(["h"], [["12%"], ["3.5%"]])[0]
    assert percent.number_format == "0.0%"
    assert infer_column_types(["h"], [["1"], ["2"]])[0].number_format == "0"


def test_typed_values() -> None:
    integer = infer_column_types(["h"], [["7"]])[0]
    assert typed_value("7", integer) == 7 and typed_value("", integer) is None
    assert typed_value("12.5%", infer_column_types(["h"], [["12.5%"]])[0]) == pytest.approx(0.125)
    assert typed_value("2026-09-08", infer_column_types(["h"], [["2026-09-08"]])[0]) == date(2026, 9, 8)
    assert typed_value("2026-09-08 14:30", infer_column_types(["h"], [["2026-09-08 14:30"]])[0]) == datetime(2026, 9, 8, 14, 30)
    text = infer_column_types(["h"], [["=1+1"]])[0]
    assert typed_value("=1+1", text) == "'=1+1"  # neutralized, unchanged doctrine


def test_headers_become_unique_and_non_empty() -> None:
    assert sanitize_headers(["a", "A", "", "  b  ", "a"], "fr") == ["a", "A (2)", "Colonne 3", "b", "a (3)"]


def test_ragged_rows_are_widened_never_truncated() -> None:
    sheet = normalize_sheet(TableSheet(name="s", headers=["a", "b"], rows=[["1"], ["1", "2", "3"], ["", " "]]), "en")
    assert sheet is not None
    assert sheet.headers == ["a", "b", "Column 3"]
    assert sheet.rows == [["1", "", ""], ["1", "2", "3"]]  # the blank row is dropped


def test_missing_headers_are_generated_and_nothing_is_none() -> None:
    assert normalize_sheet(TableSheet(name="s", headers=[], rows=[["x", "y"]]), "en").headers == ["Column 1", "Column 2"]
    assert normalize_sheet(TableSheet(name="s", headers=[], rows=[]), "en") is None


def test_excel_names_are_generated_and_legal() -> None:
    assert excel_table_name(1) == "Table1"
    assert is_excel_legal_name("Table1") and is_excel_legal_name("_x")
    for bad in ("Q1 2026", "1abc", "A1", "R1C1", "", "Ventes-2026"):
        assert not is_excel_legal_name(bad), bad


def test_chunks() -> None:
    assert chunk_rows([[str(i)] for i in range(5)], 2) == [[["0"], ["1"]], [["2"], ["3"]], [["4"]]]
    assert chunk_rows([], 3) == []
```

- [ ] **Step 2: Run** → FAIL (import).

- [ ] **Step 3: Implement**

```python
"""Tables: typed columns, legal headers, generated names, chunks (ADR-274).

Typing is by UNANIMITY: a column becomes a number, a percentage or a date only
when every non-empty cell obeys the same rule, so one stray value keeps the
whole column text rather than corrupting it. Integers are formatted without a
thousands separator (a year or a postal code is an integer too) and a leading
zero protects a column of codes. Excel refuses a workbook whose Table has a
duplicate or empty header and a name with a space or shaped like a cell
reference (measured 2026-09-08) — headers are made unique here and the Table
name is never taken from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from src.core.i18n_documents import document_label
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import TableSheet

_INT = re.compile(r"^[+-]?\d{1,15}$")
_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_DECIMAL = re.compile(r"^[+-]?\d{1,15}\.\d{1,6}$")
_PERCENT = re.compile(r"^[+-]?\d{1,15}(\.\d{1,6})?\s?%$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")
_EXCEL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_CELL_REFERENCE = re.compile(r"^([A-Za-z]{1,3}\d{1,7}|R\d+C\d+)$", re.IGNORECASE)
MAX_HEADER_LENGTH = 255
MAX_DECIMALS = 4


class ColumnKind(str, Enum):
    """What every non-empty cell of a column obeys."""

    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    PERCENT = "percent"
    DATE = "date"
    DATETIME = "datetime"


@dataclass(frozen=True, slots=True)
class ColumnType:
    """A column's kind and, for decimals and percentages, its widest scale."""

    kind: ColumnKind
    decimals: int = 0

    @property
    def numeric(self) -> bool:
        """Right-aligned in every format."""
        return self.kind in (ColumnKind.INT, ColumnKind.DECIMAL, ColumnKind.PERCENT)

    @property
    def number_format(self) -> str:
        """The Excel number format of the column."""
        scale = "0" * self.decimals
        if self.kind is ColumnKind.INT:
            return "0"
        if self.kind is ColumnKind.DECIMAL:
            return f"0.{scale}" if scale else "0"
        if self.kind is ColumnKind.PERCENT:
            return f"0.{scale}%" if scale else "0%"
        if self.kind is ColumnKind.DATE:
            return "yyyy-mm-dd"
        if self.kind is ColumnKind.DATETIME:
            return "yyyy-mm-dd hh:mm"
        return "@"


def _decimals_of(number: str) -> int:
    return len(number.split(".")[1]) if "." in number else 0


def _cell_kind(cell: str) -> tuple[ColumnKind, int] | None:
    """The rule one non-empty cell obeys, with its scale; None for text."""
    value = cell.strip()
    if _LEADING_ZERO.match(value):
        return None
    if _INT.match(value):
        return ColumnKind.INT, 0
    if _DECIMAL.match(value):
        return ColumnKind.DECIMAL, _decimals_of(value)
    if _PERCENT.match(value):
        return ColumnKind.PERCENT, _decimals_of(value.rstrip("%").strip())
    if _DATE.match(value) and _parses(value, "%Y-%m-%d"):
        return ColumnKind.DATE, 0
    if _DATETIME.match(value) and _parses_datetime(value):
        return ColumnKind.DATETIME, 0
    return None


def _parses(value: str, pattern: str) -> bool:
    try:
        datetime.strptime(value, pattern)  # noqa: DTZ007 - format check only
    except ValueError:
        return False
    return True


def _parses_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return False
    return True


def _resolve(kinds: set[ColumnKind], decimals: int) -> ColumnType:
    if kinds == {ColumnKind.INT}:
        return ColumnType(ColumnKind.INT)
    if kinds <= {ColumnKind.INT, ColumnKind.DECIMAL}:
        return ColumnType(ColumnKind.DECIMAL, min(decimals, MAX_DECIMALS))
    if len(kinds) == 1:
        kind = next(iter(kinds))
        scale = min(decimals, MAX_DECIMALS) if kind is ColumnKind.PERCENT else 0
        return ColumnType(kind, scale)
    return ColumnType(ColumnKind.TEXT)


def infer_column_types(headers: list[str], rows: list[list[str]]) -> list[ColumnType]:
    """One type per header column, by unanimity of the non-empty cells."""
    types: list[ColumnType] = []
    for index in range(len(headers)):
        kinds: set[ColumnKind] = set()
        decimals = 0
        seen = False
        for row in rows:
            cell = row[index] if index < len(row) else ""
            if not cell.strip():
                continue
            seen = True
            matched = _cell_kind(cell)
            if matched is None:
                kinds = {ColumnKind.TEXT}
                break
            kinds.add(matched[0])
            decimals = max(decimals, matched[1])
        types.append(_resolve(kinds, decimals) if seen else ColumnType(ColumnKind.TEXT))
    return types


def typed_value(cell: str, column: ColumnType) -> str | int | float | date | datetime | None:
    """The spreadsheet value of one cell under its column's type."""
    value = cell.strip()
    if not value:
        return None
    if column.kind is ColumnKind.INT:
        return int(value)
    if column.kind is ColumnKind.DECIMAL:
        return float(value)
    if column.kind is ColumnKind.PERCENT:
        return float(value.rstrip("%").strip()) / 100
    if column.kind is ColumnKind.DATE:
        return date.fromisoformat(value)
    if column.kind is ColumnKind.DATETIME:
        return datetime.fromisoformat(value.replace(" ", "T"))
    return neutralize_formula(value)


def sanitize_headers(headers: list[str], language: str) -> list[str]:
    """Unique, non-empty, bounded headers — Excel refuses a Table otherwise."""
    result: list[str] = []
    taken: set[str] = set()
    for index, raw in enumerate(headers, start=1):
        base = " ".join(raw.split())[:MAX_HEADER_LENGTH] or document_label(
            language, "documents.column_label", n=index
        )
        name, suffix = base, 2
        while name.casefold() in taken:
            name = f"{base} ({suffix})"
            suffix += 1
        taken.add(name.casefold())
        result.append(name)
    return result


def normalize_sheet(sheet: TableSheet, language: str) -> TableSheet | None:
    """Widen ragged rows, generate missing headers, drop blank rows; None when empty."""
    width = max(len(sheet.headers), max((len(row) for row in sheet.rows), default=0))
    if width == 0:
        return None
    headers = sanitize_headers(list(sheet.headers) + [""] * (width - len(sheet.headers)), language)
    rows = [(list(row) + [""] * (width - len(row)))[:width] for row in sheet.rows]
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    return TableSheet(name=sheet.name, headers=headers, rows=rows)


def excel_table_name(index: int) -> str:
    """A workbook-unique, Excel-legal Table name — never the model's words."""
    return f"Table{index}"


def is_excel_legal_name(name: str) -> bool:
    """Excel's rules for a Table name: identifier-shaped, not a cell reference."""
    return bool(_EXCEL_NAME.match(name)) and not _CELL_REFERENCE.match(name)


def chunk_rows(rows: list[list[str]], size: int) -> list[list[list[str]]]:
    """Rows in slices of ``size`` (the last one shorter), for slide tables."""
    return [rows[start : start + size] for start in range(0, len(rows), max(1, size))]
```

- [ ] **Step 4: Run** → PASS. **Gate:** `task lint:backend`.

---

### Task 8: Normalization — repairs, never refusals (`normalize.py`)

**Files:**
- Create: `apps/api/src/domains/document_generation/normalize.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_normalize.py`

**Interfaces:**
- Consumes: `normalize_sheet` (Task 7), `RenderContext` (Task 5), settings `document_generation_toc_min_headings`.
- Produces: `document_is_numbered(content, context) -> bool`, `normalize_sectioned(content, context) -> SectionedContent`, `HeadingNumberer` (`.number(level) -> str`), `normalize_slides(content, language) -> SlideContent`, `normalize_tabular(content, language) -> TabularContent`, `normalize_content(doc_type, content, context) -> DocumentContent`, `MAX_HEADING_LEVEL = 4`.

- [ ] **Step 1: Write the failing tests**

```python
"""Every incoherence is repaired, none is refused (design §6.1, §13)."""

import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import (
    HeadingNumberer,
    document_is_numbered,
    normalize_sectioned,
    normalize_slides,
    normalize_tabular,
)
from src.domains.document_generation.schemas import (
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
    TabularContent,
)

pytestmark = [pytest.mark.unit]
_CTX = RenderContext(language="en")


def _doc(*blocks: SectionBlock) -> SectionedContent:
    return SectionedContent(filename_stem="d", title="T", blocks=list(blocks))


def test_levels_are_clamped_and_empty_blocks_dropped() -> None:
    out = normalize_sectioned(_doc(
        SectionBlock(kind="heading", level=9, text="H"),
        SectionBlock(kind="heading", level=0, text="  "),
        SectionBlock(kind="paragraph", text=" "),
        SectionBlock(kind="bullets", items=["", "  "]),
        SectionBlock(kind="table"),
    ), _CTX)
    assert [(b.kind, b.level, b.text) for b in out.blocks] == [("heading", 4, "H")]


def test_markdown_that_leaked_into_a_paragraph_becomes_its_block() -> None:
    out = normalize_sectioned(_doc(
        SectionBlock(kind="paragraph", text="- a\n- b\n* c"),
        SectionBlock(kind="paragraph", text="1. one\n2) two"),
        SectionBlock(kind="paragraph", text="### Inner"),
        SectionBlock(kind="bullets", text="just text", items=[]),
    ), _CTX)
    assert [b.kind for b in out.blocks] == ["bullets", "numbered", "heading", "paragraph"]
    assert out.blocks[0].items == ["a", "b", "c"]
    assert out.blocks[2].level == 3 and out.blocks[2].text == "Inner"
    assert out.blocks[3].text == "just text"


def test_heading_numbers_written_by_the_model_are_stripped_only_when_numbered(monkeypatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "document_generation_toc_min_headings", 2)
    blocks = [SectionBlock(kind="heading", level=1, text="1. Context"), SectionBlock(kind="heading", level=2, text="1.1) Market")]
    numbered = normalize_sectioned(_doc(*blocks), _CTX)
    assert [b.text for b in numbered.blocks] == ["Context", "Market"]
    assert document_is_numbered(numbered, _CTX)
    plain = normalize_sectioned(_doc(*blocks), RenderContext(language="en", structure="plain"))
    assert [b.text for b in plain.blocks] == ["1. Context", "1.1) Market"]
    assert not document_is_numbered(plain, RenderContext(language="en", structure="plain"))
    monkeypatch.setattr(settings, "document_generation_toc_min_headings", 5)
    assert not document_is_numbered(numbered, _CTX)


def test_tables_are_normalized_and_captions_only_on_tables() -> None:
    out = normalize_sectioned(_doc(
        SectionBlock(kind="table", caption=" Key figures ", table=TableSheet(name="t", headers=["a", "a"], rows=[["1"]])),
        SectionBlock(kind="paragraph", text="p", caption="ignored"),
    ), _CTX)
    assert out.blocks[0].table is not None and out.blocks[0].table.headers == ["a", "a (2)"]
    assert out.blocks[0].caption == "Key figures" and out.blocks[1].caption == ""


def test_heading_numberer() -> None:
    numberer = HeadingNumberer()
    assert [numberer.number(level) for level in (1, 2, 2, 3, 1, 4)] == ["1", "1.1", "1.2", "1.2.1", "2", ""]


def _slides(*slides: Slide) -> list[Slide]:
    return normalize_slides(SlideContent(filename_stem="d", title="D", slides=list(slides)), "en").slides


def test_effective_kinds_follow_the_payload() -> None:
    table = TableSheet(name="t", headers=["a"], rows=[["1"]])
    assert [s.kind for s in _slides(Slide(title="t", bullets=["x"]))] == ["content"]
    assert [s.kind for s in _slides(Slide(title="t", table=table))] == ["table"]
    assert [s.kind for s in _slides(Slide(title="t", bullets=["x"], table=table))] == ["content", "table"]
    assert [s.kind for s in _slides(Slide(title="t", kind="table"))] == ["content"]
    assert [s.kind for s in _slides(Slide(title="t"))] == ["content"]


def test_section_with_bullets_is_a_divider_then_a_content_slide() -> None:
    out = _slides(Slide(title="Part", kind="section", subtitle="tag", bullets=["a"], notes="n"))
    assert [(s.kind, s.subtitle, s.bullets, s.notes) for s in out] == [("section", "tag", [], "n"), ("content", "", ["a"], "")]


def test_comparison_columns_one_two_three() -> None:
    two = [SlideColumn(heading="A", bullets=["a1"]), SlideColumn(heading="B", bullets=["b1", "b2"])]
    assert [s.kind for s in _slides(Slide(title="t", kind="comparison", columns=two))] == ["comparison"]
    assert [s.kind for s in _slides(Slide(title="t", columns=two))] == ["comparison"]  # declared content, payload says comparison
    one = _slides(Slide(title="t", kind="comparison", columns=two[:1]))
    assert one[0].kind == "content" and one[0].bullets == ["a1"]
    three = _slides(Slide(title="t", kind="comparison", columns=[*two, SlideColumn(heading="C", bullets=["c1"])]))
    assert three[0].kind == "table"
    assert three[0].table is not None and three[0].table.headers == ["A", "B", "C"]
    assert three[0].table.rows == [["a1", "b1", "c1"], ["", "b2", ""]]


def test_tabular_sheets_are_normalized_and_never_empty() -> None:
    out = normalize_tabular(TabularContent(filename_stem="t", title="Title", sheets=[TableSheet(name="s", headers=[], rows=[])]), "en")
    assert len(out.sheets) == 1 and out.sheets[0].headers == ["Title"]
```

- [ ] **Step 2: Run** → FAIL (import).

- [ ] **Step 3: Implement**

```python
"""The canonical form of what the model produced (ADR-274, design §6.1).

Every incoherence a writer can produce is REPAIRED here, mechanically, and
never reported as a defect (ADR-184): a heading level outside 1..4 is clamped,
an empty block is dropped, markdown that leaked into a paragraph becomes the
block it is, a heading the model numbered itself loses its prefix when the
renderer numbers, a slide's effective kind follows the payload it actually
carries. Renderers consume the output of this module, never the raw content.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from itertools import zip_longest

from src.core.config import settings
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.schemas import (
    DocumentContent,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
    TabularContent,
)
from src.domains.document_generation.tables import normalize_sheet

MAX_HEADING_LEVEL = 4
_HEADING_NUMBER = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s+")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_BULLET = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
_MD_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")


def _clean(text: str) -> str:
    return " ".join(text.split())


def _heading_count(content: SectionedContent) -> int:
    return sum(1 for block in content.blocks if block.kind == "heading" and block.text.strip())


def document_is_numbered(content: SectionedContent, context: RenderContext) -> bool:
    """Whether the long-document apparatus (TOC, numbering, part breaks) is on."""
    return (
        context.structure == "auto"
        and _heading_count(content) >= settings.document_generation_toc_min_headings
    )


class HeadingNumberer:
    """1 / 1.1 / 1.1.1 counters for levels 1-3; deeper levels are unnumbered."""

    def __init__(self) -> None:
        self._counters = [0, 0, 0]

    def number(self, level: int) -> str:
        """The number of the next heading at ``level``, advancing the counters."""
        if level > 3:
            return ""
        self._counters[level - 1] += 1
        for deeper in range(level, 3):
            self._counters[deeper] = 0
        return ".".join(str(count) for count in self._counters[:level])


def _leaked_markdown(block: SectionBlock) -> SectionBlock | None:
    """A paragraph that is really a list or a heading, or None."""
    lines = [line for line in block.text.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) == 1 and (match := _MD_HEADING.match(lines[0])):
        return SectionBlock(kind="heading", level=len(match.group(1)), text=match.group(2))
    for pattern, kind in ((_MD_BULLET, "bullets"), (_MD_NUMBERED, "numbered")):
        matches = [pattern.match(line) for line in lines]
        if all(matches):
            return SectionBlock(kind=kind, items=[m.group(1) for m in matches if m])  # type: ignore[arg-type]
    return None


def _canonical_block(block: SectionBlock, language: str) -> SectionBlock | None:
    """One block in canonical form, or None when there is nothing to render."""
    if block.kind == "paragraph" and (leaked := _leaked_markdown(block)) is not None:
        block = leaked
    items = [_clean(item) for item in block.items if item.strip()]
    text = _clean(block.text)
    if block.kind in ("bullets", "numbered"):
        if items:
            return SectionBlock(kind=block.kind, items=items)
        return SectionBlock(kind="paragraph", text=text) if text else None
    if block.kind == "table":
        sheet = normalize_sheet(block.table, language) if block.table is not None else None
        if sheet is None:
            return None
        return SectionBlock(kind="table", table=sheet, caption=_clean(block.caption))
    if not text:
        return None
    if block.kind == "heading":
        level = min(max(block.level, 1), MAX_HEADING_LEVEL)
        return SectionBlock(kind="heading", level=level, text=text)
    return SectionBlock(kind=block.kind, text=text)


def normalize_sectioned(content: SectionedContent, context: RenderContext) -> SectionedContent:
    """Canonical blocks; heading prefixes stripped when the renderer numbers."""
    blocks = [
        canonical
        for block in content.blocks
        if (canonical := _canonical_block(block, context.language)) is not None
    ]
    canonical_content = SectionedContent(
        filename_stem=content.filename_stem,
        title=_clean(content.title) or content.title,
        subtitle=_clean(content.subtitle),
        blocks=blocks or [SectionBlock(kind="paragraph", text=_clean(content.title))],
    )
    if document_is_numbered(canonical_content, context):
        for block in canonical_content.blocks:
            if block.kind == "heading":
                block.text = _HEADING_NUMBER.sub("", block.text) or block.text
    return canonical_content


def _columns_to_table(columns: list[SlideColumn], language: str) -> TableSheet | None:
    headers = [column.heading for column in columns]
    rows = [list(cells) for cells in zip_longest(*(c.bullets for c in columns), fillvalue="")]
    return normalize_sheet(TableSheet(name="comparison", headers=headers, rows=rows), language)


def _effective_slides(slide: Slide, language: str) -> list[Slide]:
    title = _clean(slide.title)
    subtitle = _clean(slide.subtitle)
    notes = slide.notes.strip()
    bullets = [_clean(b) for b in slide.bullets if b.strip()]
    columns = [
        SlideColumn(heading=_clean(c.heading), bullets=[_clean(b) for b in c.bullets if b.strip()])
        for c in slide.columns
        if c.heading.strip() or any(b.strip() for b in c.bullets)
    ]
    table = normalize_sheet(slide.table, language) if slide.table is not None else None
    if slide.kind == "section":
        rest = Slide(title=title, bullets=bullets, columns=columns, table=table)
        divider = Slide(title=title, kind="section", subtitle=subtitle, notes=notes)
        tail = _effective_slides(rest, language) if (bullets or columns or table) else []
        return [divider, *tail]
    if len(columns) >= 3:
        folded = _columns_to_table(columns, language)
        table, columns = (table or folded), []
    elif len(columns) == 1:
        bullets, columns = bullets + columns[0].bullets, []
    out: list[Slide] = []
    if bullets:
        out.append(Slide(title=title, kind="content", subtitle=subtitle, bullets=bullets))
    if len(columns) == 2:
        out.append(Slide(title=title, kind="comparison", subtitle=subtitle, columns=columns))
    if table is not None:
        out.append(Slide(title=title, kind="table", subtitle=subtitle, table=table))
    if not out:
        out.append(Slide(title=title, kind="content", subtitle=subtitle))
    out[0].notes = notes
    return out


def normalize_slides(content: SlideContent, language: str) -> SlideContent:
    """Effective kinds, cleaned text, consistent payloads."""
    slides = [
        effective for slide in content.slides for effective in _effective_slides(slide, language)
    ]
    return SlideContent(
        filename_stem=content.filename_stem,
        title=_clean(content.title) or content.title,
        subtitle=_clean(content.subtitle),
        slides=slides,
    )


def normalize_tabular(content: TabularContent, language: str) -> TabularContent:
    """Sheets normalized; a workbook always has one sheet."""
    sheets = [
        sheet
        for raw in content.sheets
        if (sheet := normalize_sheet(raw, language)) is not None
    ]
    if not sheets:
        sheets = [TableSheet(name=content.title, headers=[content.title], rows=[])]
    return TabularContent(filename_stem=content.filename_stem, title=content.title, sheets=sheets)


_NORMALIZERS: dict[type[DocumentContent], Callable[..., DocumentContent]] = {
    SectionedContent: lambda content, context: normalize_sectioned(content, context),
    SlideContent: lambda content, context: normalize_slides(content, context.language),
    TabularContent: lambda content, context: normalize_tabular(content, context.language),
}


def normalize_content(content: DocumentContent, context: RenderContext) -> DocumentContent:
    """The canonical form of any content family."""
    return _NORMALIZERS[type(content)](content, context)
```

Note for MyPy: `_NORMALIZERS` is typed with `Callable[..., DocumentContent]`; the `DocumentType` import is unused — drop it. Pydantic models are mutable by default, so `block.text = …` and `out[0].notes = …` are valid.

- [ ] **Step 4: Run** → PASS. **Gate:** `task lint:backend` (watch the complexity of `_effective_slides`: it must stay < 15 — it is ~10).

---

### Task 9: The fit estimator (`fit.py`) and its calibration fixture

**Files:**
- Create: `apps/api/src/domains/document_generation/fit.py`
- Create: `apps/api/tests/unit/domains/document_generation/fixtures/pptx_calibration.json`
- Test: `apps/api/tests/unit/domains/document_generation/test_fit.py`

**Interfaces:**
- Produces: `TextFrame(width_pt, height_pt, indent_pt=BULLET_INDENT_PT)` with `.usable_width`; `line_count(text, size_pt, frame) -> int`; `text_height(paragraphs, size_pt, frame) -> float`; `fits(paragraphs, size_pt, frame) -> bool`; `base_body_size(count) -> int`; `choose_body_size(paragraphs, frame) -> int | None`; `SlidePlan(bullets: tuple[str, ...], size_pt: int)`; `plan_body(bullets, frame) -> list[SlidePlan]`; `fit_title(title, frame) -> tuple[int, int]`; `table_font_size(columns) -> int`; `rows_per_slide(columns, frame) -> int`; constants `AVG_CHAR_WIDTH_EM = 0.42`, `LINE_HEIGHT_FACTOR = 1.2`, `PARAGRAPH_SPACING_FACTOR = 0.2`, `SAFETY_FACTOR = 1.05`, `INSET_PT = 7.2`, `BULLET_INDENT_PT = 27.0`, `BODY_SIZE_FLOOR_PT = 14`, `TITLE_SIZE_BASE_PT = 40`, `TITLE_SIZE_FLOOR_PT = 24`, `TITLE_TWO_LINES_FROM_PT = 36`.

- [ ] **Step 1: Write the calibration fixture** — `fixtures/pptx_calibration.json`, the 54 PowerPoint 16 measurements of 2026-09-08 on the 16:9 body frame (863.98 × 356.38 pt): each object `{"size": s, "bullets": n, "chars": c, "lines": l, "bound_height": h}`:

```json
{"frame": {"width_pt": 863.98, "height_pt": 356.38}, "rows": [
{"size":14,"bullets":1,"chars":25,"lines":1,"bound_height":16.8},{"size":14,"bullets":1,"chars":70,"lines":1,"bound_height":16.8},{"size":14,"bullets":1,"chars":140,"lines":2,"bound_height":33.6},
{"size":14,"bullets":4,"chars":25,"lines":4,"bound_height":77.28},{"size":14,"bullets":4,"chars":70,"lines":4,"bound_height":77.28},{"size":14,"bullets":4,"chars":140,"lines":8,"bound_height":144.48},
{"size":14,"bullets":8,"chars":25,"lines":8,"bound_height":157.92},{"size":14,"bullets":8,"chars":70,"lines":8,"bound_height":157.92},{"size":14,"bullets":8,"chars":140,"lines":16,"bound_height":292.32},
{"size":16,"bullets":1,"chars":25,"lines":1,"bound_height":19.2},{"size":16,"bullets":1,"chars":70,"lines":1,"bound_height":19.2},{"size":16,"bullets":1,"chars":140,"lines":2,"bound_height":38.4},
{"size":16,"bullets":4,"chars":25,"lines":4,"bound_height":88.32},{"size":16,"bullets":4,"chars":70,"lines":4,"bound_height":88.32},{"size":16,"bullets":4,"chars":140,"lines":8,"bound_height":165.12},
{"size":16,"bullets":8,"chars":25,"lines":8,"bound_height":180.48},{"size":16,"bullets":8,"chars":70,"lines":8,"bound_height":180.48},{"size":16,"bullets":8,"chars":140,"lines":16,"bound_height":334.08},
{"size":18,"bullets":1,"chars":25,"lines":1,"bound_height":21.6},{"size":18,"bullets":1,"chars":70,"lines":1,"bound_height":21.6},{"size":18,"bullets":1,"chars":140,"lines":2,"bound_height":43.2},
{"size":18,"bullets":4,"chars":25,"lines":4,"bound_height":99.36},{"size":18,"bullets":4,"chars":70,"lines":4,"bound_height":99.36},{"size":18,"bullets":4,"chars":140,"lines":8,"bound_height":185.76},
{"size":18,"bullets":8,"chars":25,"lines":8,"bound_height":203.04},{"size":18,"bullets":8,"chars":70,"lines":8,"bound_height":203.04},{"size":18,"bullets":8,"chars":140,"lines":16,"bound_height":375.84},
{"size":20,"bullets":1,"chars":25,"lines":1,"bound_height":24.0},{"size":20,"bullets":1,"chars":70,"lines":1,"bound_height":24.0},{"size":20,"bullets":1,"chars":140,"lines":2,"bound_height":48.0},
{"size":20,"bullets":4,"chars":25,"lines":4,"bound_height":110.4},{"size":20,"bullets":4,"chars":70,"lines":4,"bound_height":110.4},{"size":20,"bullets":4,"chars":140,"lines":8,"bound_height":206.4},
{"size":20,"bullets":8,"chars":25,"lines":8,"bound_height":225.6},{"size":20,"bullets":8,"chars":70,"lines":8,"bound_height":225.6},{"size":20,"bullets":8,"chars":140,"lines":16,"bound_height":417.6},
{"size":24,"bullets":1,"chars":25,"lines":1,"bound_height":28.8},{"size":24,"bullets":1,"chars":70,"lines":1,"bound_height":28.8},{"size":24,"bullets":1,"chars":140,"lines":2,"bound_height":57.6},
{"size":24,"bullets":4,"chars":25,"lines":4,"bound_height":132.48},{"size":24,"bullets":4,"chars":70,"lines":4,"bound_height":132.48},{"size":24,"bullets":4,"chars":140,"lines":8,"bound_height":247.68},
{"size":24,"bullets":8,"chars":25,"lines":8,"bound_height":270.72},{"size":24,"bullets":8,"chars":70,"lines":8,"bound_height":270.72},{"size":24,"bullets":8,"chars":140,"lines":16,"bound_height":501.12},
{"size":28,"bullets":1,"chars":25,"lines":1,"bound_height":33.6},{"size":28,"bullets":1,"chars":70,"lines":2,"bound_height":67.2},{"size":28,"bullets":1,"chars":140,"lines":3,"bound_height":100.8},
{"size":28,"bullets":4,"chars":25,"lines":4,"bound_height":154.56},{"size":28,"bullets":4,"chars":70,"lines":8,"bound_height":288.96},{"size":28,"bullets":4,"chars":140,"lines":12,"bound_height":423.36},
{"size":28,"bullets":8,"chars":25,"lines":8,"bound_height":315.84},{"size":28,"bullets":8,"chars":70,"lines":16,"bound_height":584.64},{"size":28,"bullets":8,"chars":140,"lines":24,"bound_height":853.44}
]}
```

- [ ] **Step 2: Write the failing tests**

```python
"""The estimator against PowerPoint's own measurements (ADR-274 §9)."""

import json
from pathlib import Path

import pytest

from src.domains.document_generation.fit import (
    BODY_SIZE_FLOOR_PT,
    TextFrame,
    base_body_size,
    choose_body_size,
    fit_title,
    fits,
    line_count,
    plan_body,
    rows_per_slide,
    table_font_size,
    text_height,
)

pytestmark = [pytest.mark.unit]
_CALIBRATION = json.loads(
    (Path(__file__).parent / "fixtures" / "pptx_calibration.json").read_text(encoding="utf-8")
)
_FRAME = TextFrame(**_CALIBRATION["frame"])
_ROWS = _CALIBRATION["rows"]


def _bullet(chars: int) -> str:
    return ("mesure " * 40)[:chars].rstrip()


@pytest.mark.parametrize("row", _ROWS, ids=lambda r: f"{r['size']}pt-{r['bullets']}b-{r['chars']}c")
def test_lines_are_exact_and_height_never_under_predicts(row: dict) -> None:
    bullets = [_bullet(row["chars"])] * row["bullets"]
    assert sum(line_count(b, row["size"], _FRAME) for b in bullets) == row["lines"]
    assert text_height(bullets, row["size"], _FRAME) >= row["bound_height"]


def test_monotonic_in_size_and_length() -> None:
    short, long = ["a" * 40], ["a" * 400]
    assert text_height(short, 14, _FRAME) < text_height(short, 28, _FRAME)
    assert text_height(short, 20, _FRAME) < text_height(long, 20, _FRAME)


def test_base_sizes_and_floor() -> None:
    assert (base_body_size(3), base_body_size(6), base_body_size(7)) == (24, 20, 18)
    assert choose_body_size(["x"] * 3, _FRAME) == 24
    assert choose_body_size([_bullet(140)] * 9, _FRAME) is None  # even 14 pt overflows: split


def test_plan_splits_greedily_at_the_floor_and_keeps_order() -> None:
    bullets = [f"{i} " + _bullet(140) for i in range(9)]
    plans = plan_body(bullets, _FRAME)
    assert len(plans) >= 2
    assert [b for plan in plans for b in plan.bullets] == bullets
    for plan in plans:
        assert plan.size_pt >= BODY_SIZE_FLOOR_PT
        assert fits(list(plan.bullets), plan.size_pt, _FRAME)


def test_a_bullet_too_long_for_a_slide_is_cut_at_sentences_never_truncated() -> None:
    monster = ". ".join(f"Sentence number {i} of a very long bullet" for i in range(60)) + "."
    plans = plan_body([monster], _FRAME)
    assert len(plans) >= 2
    assert " ".join(b for plan in plans for b in plan.bullets).replace("  ", " ") == monster
    for plan in plans:
        assert fits(list(plan.bullets), plan.size_pt, _FRAME)


def test_titles_shrink_then_take_two_lines() -> None:
    title_frame = TextFrame(863.98, 90.0, indent_pt=0)
    assert fit_title("Short", title_frame) == (40, 1)
    size, lines = fit_title("Un titre de diapositive assez long pour tester la casse sur deux lignes", title_frame)
    assert lines == 2 and 24 <= size <= 36


def test_table_budget() -> None:
    assert table_font_size(6) == 12 and table_font_size(7) == 10
    assert rows_per_slide(3, _FRAME) == 11
    assert rows_per_slide(9, _FRAME) == 13
```

- [ ] **Step 3: Run** → FAIL (import).

- [ ] **Step 4: Implement**

```python
"""Text measurement without a font (ADR-274 §9).

python-pptx computes no autofit, PowerPoint applies none on open, and
python-pptx's ``fit_text`` ignores the master's paragraph spacing (it chose
21 pt where PowerPoint still measured +364 pt of overflow). This estimator was
CALIBRATED against PowerPoint 16 on 2026-09-08, 54 combinations of size,
bullets and length on the 16:9 body frame: 0.42 em per character gives 0 line-
count errors, and lines × size × 1.2 + paragraphs × size × 0.2, times 1.05,
gives 0 under-predictions. The measurements are the fixture of ``test_fit.py``.

Stated limit: Calibri metrics. Carlito is metric-compatible; other viewers
substitute — the 14 pt floor and the 5 % margin cover the common case.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

AVG_CHAR_WIDTH_EM = 0.42
LINE_HEIGHT_FACTOR = 1.2
PARAGRAPH_SPACING_FACTOR = 0.2
SAFETY_FACTOR = 1.05
INSET_PT = 7.2  # the placeholder's left/right inset (0.1 in)
BULLET_INDENT_PT = 27.0  # level-1 bullet indent of the default master
BODY_SIZE_FLOOR_PT = 14
BODY_SIZE_STEP_PT = 2
TITLE_SIZE_BASE_PT = 40
TITLE_SIZE_FLOOR_PT = 24
TITLE_TWO_LINES_FROM_PT = 36
TABLE_ROW_HEIGHT_PT = {12: 28.8, 10: 24.0}
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass(frozen=True, slots=True)
class TextFrame:
    """A placeholder's box, in points."""

    width_pt: float
    height_pt: float
    indent_pt: float = BULLET_INDENT_PT

    @property
    def usable_width(self) -> float:
        """Width left for glyphs once insets and the bullet indent are taken."""
        return self.width_pt - 2 * INSET_PT - self.indent_pt


def line_count(text: str, size_pt: float, frame: TextFrame) -> int:
    """Lines one paragraph takes at ``size_pt`` — exact on the calibration set."""
    if not text:
        return 1
    return max(1, math.ceil(len(text) * AVG_CHAR_WIDTH_EM * size_pt / frame.usable_width))


def text_height(paragraphs: Sequence[str], size_pt: float, frame: TextFrame) -> float:
    """Height of the paragraphs at ``size_pt``, with the safety margin."""
    lines = sum(line_count(paragraph, size_pt, frame) for paragraph in paragraphs)
    spacing = len(paragraphs) * size_pt * PARAGRAPH_SPACING_FACTOR
    return (lines * size_pt * LINE_HEIGHT_FACTOR + spacing) * SAFETY_FACTOR


def fits(paragraphs: Sequence[str], size_pt: float, frame: TextFrame) -> bool:
    """Whether the paragraphs stay inside the frame at ``size_pt``."""
    return text_height(paragraphs, size_pt, frame) <= frame.height_pt


def base_body_size(count: int) -> int:
    """The starting body size by bullet count: airy for few, tighter for many."""
    if count <= 3:
        return 24
    return 20 if count <= 6 else 18


def choose_body_size(paragraphs: Sequence[str], frame: TextFrame) -> int | None:
    """The largest size from the base down to the floor that fits, or None."""
    size = base_body_size(len(paragraphs))
    while size >= BODY_SIZE_FLOOR_PT:
        if fits(paragraphs, size, frame):
            return size
        size -= BODY_SIZE_STEP_PT
    return None


@dataclass(frozen=True, slots=True)
class SlidePlan:
    """The bullets of one slide and the size they are set at."""

    bullets: tuple[str, ...]
    size_pt: int


def _pieces_that_fit(text: str, frame: TextFrame) -> list[str]:
    """Cut one oversized paragraph at sentence ends, then at words, into fitting pieces."""
    if fits([text], BODY_SIZE_FLOOR_PT, frame):
        return [text]
    units = [u for u in _SENTENCE_END.split(text) if u]
    if len(units) == 1:
        units = text.split(" ")
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip()
        if current and not fits([candidate], BODY_SIZE_FLOOR_PT, frame):
            pieces.append(current)
            current = unit
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def plan_body(bullets: Sequence[str], frame: TextFrame) -> list[SlidePlan]:
    """Shrink first; when the floor is not enough, fill slides greedily in order."""
    if not bullets:
        return [SlidePlan((), base_body_size(0))]
    size = choose_body_size(bullets, frame)
    if size is not None:
        return [SlidePlan(tuple(bullets), size)]
    plans: list[SlidePlan] = []
    current: list[str] = []
    for bullet in (piece for bullet in bullets for piece in _pieces_that_fit(bullet, frame)):
        if current and not fits([*current, bullet], BODY_SIZE_FLOOR_PT, frame):
            plans.append(SlidePlan(tuple(current), choose_body_size(current, frame) or BODY_SIZE_FLOOR_PT))
            current = []
        current.append(bullet)
    if current:
        plans.append(SlidePlan(tuple(current), choose_body_size(current, frame) or BODY_SIZE_FLOOR_PT))
    return plans


def fit_title(title: str, frame: TextFrame) -> tuple[int, int]:
    """(size, lines) for a title: shrink from the base; two lines allowed from 36 pt down.

    Decides with the SAME ``fits`` the overflow oracle re-checks, so the two can
    never disagree about a title.
    """
    size = TITLE_SIZE_BASE_PT
    while size >= TITLE_SIZE_FLOOR_PT:
        lines = line_count(title, size, frame)
        allowed = 2 if size <= TITLE_TWO_LINES_FROM_PT else 1
        if lines <= allowed and fits([title], size, frame):
            return size, lines
        size -= BODY_SIZE_STEP_PT
    return TITLE_SIZE_FLOOR_PT, line_count(title, TITLE_SIZE_FLOOR_PT, frame)


def table_font_size(columns: int) -> int:
    """12 pt up to six columns, 10 pt beyond."""
    return 12 if columns <= 6 else 10


def rows_per_slide(columns: int, frame: TextFrame) -> int:
    """Data rows one slide holds at the table's font size, header row excluded."""
    row_height = TABLE_ROW_HEIGHT_PT[table_font_size(columns)]
    return max(1, int(frame.height_pt / row_height) - 1)
```

- [ ] **Step 5: Run** → PASS (54 parametrized rows + 6). **Gate:** `task lint:backend`.

---

### Task 10: Typography — the one place a document's look is decided

**Files:**
- Create: `apps/api/src/domains/document_generation/typography.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_typography.py`

**Interfaces:**
- Produces the constants below and `pdf_css(page_size) -> str`, `page_rect_name(page_size) -> str`, `docx_margin_cm(page_size) -> float`.

- [ ] **Step 1: Write the failing test**

```python
"""One source for the look; the CSS is built from it, never written twice."""

import pytest

from src.domains.document_generation import typography as t

pytestmark = [pytest.mark.unit]


def test_css_carries_the_scale_and_the_safe_table_recipe() -> None:
    css = t.pdf_css("a4")
    assert f"font-size: {t.PDF_BODY_PT}pt" in css
    assert f"h1 {{ font-size: {t.PDF_HEADING_PT[1]}pt" in css
    # The MuPDF phantom rectangle (measured 2026-09-08): no background on th,
    # no border-collapse; banding on td only.
    assert "th {" in css and "background" not in css.split("th {")[1].split("}")[0]
    assert "border-collapse" not in css


def test_pages_and_margins() -> None:
    assert t.page_rect_name("a4") == "a4" and t.page_rect_name("letter") == "letter"
    assert t.docx_margin_cm("a4") == 2.5 and t.docx_margin_cm("letter") == 2.54
    assert t.PPTX_SLIDE_WIDTH_IN > t.PPTX_SLIDE_HEIGHT_IN  # landscape
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

```python
"""The one place a document's look is decided (ADR-274).

Neutral by design — ink on paper, one grey band, one grey rule — because these
files leave the person's hands: no brand, no theme colour, no vendored
template. Every renderer reads its sizes, colours, geometries and built-in
style identifiers here; a future theme is a parametrisation of this module.
"""

from __future__ import annotations

from typing import Literal

PageSize = Literal["a4", "letter"]

# --- Faces ------------------------------------------------------------------
FONT_BODY = "Calibri"
FONT_EAST_ASIA = "Microsoft YaHei"  # declared so CJK never falls back to a Latin face
PDF_FONT_FAMILY = "sans-serif"  # PyMuPDF's bundled Nimbus Sans; Droid Sans Fallback for CJK

# --- Ink --------------------------------------------------------------------
INK = "1A1A1A"
HEADING_INK = "262626"
MUTED = "595959"
RULE = "BFBFBF"
RULE_LIGHT = "DDDDDD"
BAND = "F2F2F2"

# --- DOCX -------------------------------------------------------------------
DOCX_BODY_PT = 11
DOCX_TITLE_PT = 26
DOCX_SUBTITLE_PT = 13
DOCX_HEADING_PT: dict[int, int] = {1: 18, 2: 14, 3: 12, 4: 11}
DOCX_CAPTION_PT = 9
DOCX_HEADER_PT = 9
DOCX_LINE_SPACING = 1.15
DOCX_SPACE_AFTER_PT = 6
DOCX_TABLE_STYLE = "Light List"  # non-accent built-in; confirmed on the corpus render (Task 13)
DOCX_TOC_INDENT_CM = 0.75
_DOCX_MARGIN_CM: dict[str, float] = {"a4": 2.5, "letter": 2.54}

# --- PPTX (16:9 landscape) --------------------------------------------------
PPTX_SLIDE_WIDTH_IN = 13.333
PPTX_SLIDE_HEIGHT_IN = 7.5
PPTX_TABLE_STYLE_ID = "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}"  # "Light Style 1", grayscale
PPTX_SUBTITLE_PT = 24
PPTX_DATE_PT = 16
PPTX_SECTION_TAGLINE_PT = 20
PPTX_COMPARISON_HEADING_PT = 22

# --- XLSX -------------------------------------------------------------------
XLSX_TABLE_STYLE = "TableStyleLight1"  # grayscale built-in; confirmed on the corpus render (Task 12)
XLSX_COLUMN_WIDTH_MIN = 8
XLSX_COLUMN_WIDTH_MAX = 60

# --- PDF --------------------------------------------------------------------
PDF_BODY_PT = 10.5
PDF_HEADING_PT: dict[int, float] = {1: 22, 2: 15, 3: 12.5, 4: 11}
PDF_LINE_HEIGHT = 1.35
PDF_MARGIN_PT: tuple[float, float, float, float] = (56, 56, 56, 64)  # left, top, right, bottom
PDF_STAMP_PT = 8
_PAGE_RECT_NAME: dict[str, str] = {"a4": "a4", "letter": "letter"}


def page_rect_name(page_size: PageSize) -> str:
    """The ``fitz.paper_rect`` name of a page size."""
    return _PAGE_RECT_NAME[page_size]


def docx_margin_cm(page_size: PageSize) -> float:
    """Word margins: 2.5 cm on A4, one inch on Letter."""
    return _DOCX_MARGIN_CM[page_size]


def pdf_css(page_size: PageSize) -> str:  # noqa: ARG001 - the page drives nothing in CSS yet; kept for symmetry
    """The stylesheet PyMuPDF's Story lays the document out with.

    Tables carry NO header background and NO ``border-collapse``: with both,
    MuPDF repaints a phantom header rectangle at the top of every continuation
    page (measured 2026-09-08). Banding sits on ``td`` only.
    """
    return (
        f"body {{ font-family: {PDF_FONT_FAMILY}; font-size: {PDF_BODY_PT}pt; "
        f"line-height: {PDF_LINE_HEIGHT}; color: #{INK}; }}\n"
        f"h1 {{ font-size: {PDF_HEADING_PT[1]}pt; margin: 0 0 4pt 0; color: #{INK}; }}\n"
        f"h2 {{ font-size: {PDF_HEADING_PT[2]}pt; margin: 18pt 0 6pt 0; color: #{HEADING_INK}; "
        f"border-bottom: 0.5pt solid #{RULE}; }}\n"
        f"h3 {{ font-size: {PDF_HEADING_PT[3]}pt; margin: 12pt 0 4pt 0; color: #{HEADING_INK}; }}\n"
        f"h4 {{ font-size: {PDF_HEADING_PT[4]}pt; margin: 10pt 0 3pt 0; color: #{HEADING_INK}; }}\n"
        "p { margin: 0 0 8pt 0; }\n"
        f"p.subtitle {{ font-size: {PDF_BODY_PT + 2}pt; color: #{MUTED}; margin-bottom: 2pt; }}\n"
        f"p.date {{ font-size: {PDF_BODY_PT - 1}pt; color: #{MUTED}; margin-bottom: 14pt; }}\n"
        f"p.caption {{ font-size: {PDF_BODY_PT - 1.5}pt; color: #{MUTED}; font-style: italic; "
        "margin: 8pt 0 3pt 0; }\n"
        "p.toc { margin: 0 0 3pt 0; }\n"
        "p.toc2 { margin: 0 0 3pt 14pt; }\n"
        "p.toc3 { margin: 0 0 3pt 28pt; }\n"
        "ul, ol { margin: 0 0 8pt 0; }\n"
        "li { margin: 0 0 2pt 0; }\n"
        f"blockquote {{ margin: 6pt 18pt; padding-left: 8pt; border-left: 2pt solid #{RULE}; "
        f"color: #{MUTED}; }}\n"
        f"div.callout {{ background-color: #{BAND}; border-left: 2pt solid #{MUTED}; "
        "padding: 6pt 8pt; margin: 6pt 0 10pt 0; }\n"
        "table { width: 100%; margin: 2pt 0 10pt 0; }\n"
        f"th {{ font-weight: bold; text-align: left; padding: 3pt 5pt; "
        f"border-bottom: 1pt solid #{MUTED}; }}\n"
        f"td {{ padding: 3pt 5pt; border-bottom: 0.3pt solid #{RULE_LIGHT}; }}\n"
        f"tr:nth-child(even) td {{ background-color: #{BAND}; }}\n"
        "td.num, th.num { text-align: right; }\n"
        "code { font-family: monospace; }\n"
    )
```

- [ ] **Step 4: Run** → PASS. **Gate:** `task lint:backend`.

---

# Lot 2 — The renderers

### Task 11: The renderers package (verbatim move) and the text family

**Files:**
- Create: `apps/api/src/domains/document_generation/renderers/__init__.py`, `renderers/text.py`, `renderers/xlsx.py`, `renderers/docx.py`, `renderers/pptx.py`, `renderers/pdf.py`
- Delete: `apps/api/src/domains/document_generation/renderers.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_renderers_text.py` (extend), `test_renderers_office.py` and `test_renderer_pdf.py` (unchanged, must stay green)

**Interfaces:**
- Produces: `render_document(doc_type, content, context=None) -> bytes` (normalizes through `normalize_content`, then dispatches); `RENDERERS: dict[DocumentType, Renderer]` where `Renderer = Callable[[DocumentContent, RenderContext], bytes]`; `DOCUMENT_MIME_TYPES`, `DOCUMENT_EXTENSIONS` re-exported; per-format `render_csv/md/txt/xlsx/docx/pptx/pdf(content, context)`.

- [ ] **Step 1: Move** — create the package: `__init__.py` holds the two maps, `RENDERERS`, the ADR-085 assert and `render_document`; each format module receives its current function verbatim (renamed public, signature `(content: DocumentContent, context: RenderContext) -> bytes`; the `context` is unused in this task except by the text renderers below). `xlsx.py` keeps `_xlsx_sheet_title`. Delete `renderers.py`.

```python
"""Pure renderers: canonical content -> document bytes (ADR-226, ADR-274).

One module per format; every renderer is a pure function of the NORMALIZED
content and a ``RenderContext``, so it is unit-tested without I/O and the
CPU-bound work is offloaded with ``asyncio.to_thread`` by the caller. The
registry is completeness-asserted at import (ADR-085).
"""

from __future__ import annotations

from collections.abc import Callable

from src.domains.document_generation.context import RenderContext, default_render_context
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers.docx import render_docx
from src.domains.document_generation.renderers.pdf import render_pdf
from src.domains.document_generation.renderers.pptx import render_pptx
from src.domains.document_generation.renderers.text import render_csv, render_md, render_txt
from src.domains.document_generation.renderers.xlsx import render_xlsx
from src.domains.document_generation.schemas import DocumentContent, DocumentType

Renderer = Callable[[DocumentContent, RenderContext], bytes]

DOCUMENT_MIME_TYPES: dict[DocumentType, str] = { ...verbatim... }
DOCUMENT_EXTENSIONS: dict[DocumentType, str] = { ...verbatim... }

RENDERERS: dict[DocumentType, Renderer] = {
    DocumentType.CSV: render_csv,
    DocumentType.MD: render_md,
    DocumentType.TXT: render_txt,
    DocumentType.XLSX: render_xlsx,
    DocumentType.DOCX: render_docx,
    DocumentType.PPTX: render_pptx,
    DocumentType.PDF: render_pdf,
}
assert set(RENDERERS) == set(DocumentType), "RENDERERS must cover every DocumentType"


def render_document(
    doc_type: DocumentType, content: DocumentContent, context: RenderContext | None = None
) -> bytes:
    """Render structured content into final document bytes.

    Args:
        doc_type: Target format.
        content: Validated content matching ``SCHEMA_BY_DOC_TYPE[doc_type]``.
        context: Reader and deployment facts; a caller that states nothing
            gets the deployment defaults and no date line.

    Returns:
        The rendered file bytes.

    Raises:
        ValueError: When the content model does not match the format family.
    """
    resolved = context or default_render_context()
    return RENDERERS[doc_type](normalize_content(content, resolved), resolved)
```

The family check (`isinstance(content, …)` → `ValueError`) stays inside each renderer, verbatim.

- [ ] **Step 2: Run the whole domain suite** → PASS unchanged (`.venv/Scripts/pytest tests/unit/domains/document_generation tests/unit/domains/meetings -q`). This proves the move.

- [ ] **Step 3: Write the failing text-family tests** (append to `test_renderers_text.py`):

```python
def _rich() -> SectionedContent:
    return SectionedContent(
        filename_stem="r", title="Title", subtitle="For the board",
        blocks=[
            SectionBlock(kind="numbered", items=["first", "second"]),
            SectionBlock(kind="quote", text="verbatim words"),
            SectionBlock(kind="callout", text="watch **this**"),
            SectionBlock(kind="table", caption="Key figures", table=TableSheet(name="t", headers=["k"], rows=[["v"]])),
        ],
    )


@pytest.mark.unit
def test_markdown_renders_the_new_kinds() -> None:
    from src.domains.document_generation.context import RenderContext

    text = render_document(DocumentType.MD, _rich(), RenderContext(language="en")).decode("utf-8")
    assert "# Title\n\n*For the board*" in text
    assert "1. first\n2. second" in text
    assert "> verbatim words" in text
    assert "> **Note.** watch **this**" in text
    assert "*Table 1 — Key figures*\n\n| k |" in text


@pytest.mark.unit
def test_txt_renders_the_new_kinds_without_markup() -> None:
    from src.domains.document_generation.context import RenderContext

    text = render_document(DocumentType.TXT, _rich(), RenderContext(language="fr")).decode("utf-8")
    assert "1) first" in text and "2) second" in text
    assert "    verbatim words" in text
    assert "watch this" in text and "**" not in text
    assert "Tableau 1 — Key figures" in text
```

- [ ] **Step 4: Run** → FAIL. **Step 5: Implement `renderers/text.py`** (csv verbatim; md and txt rewritten around a per-kind dispatch):

```python
"""Text family: csv (BOM + neutralization), md, txt (ADR-226, ADR-274)."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.inline import strip_inline
from src.domains.document_generation.normalize import HeadingNumberer, document_is_numbered
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import (
    DocumentContent,
    SectionBlock,
    SectionedContent,
    TableSheet,
    TabularContent,
)


def render_csv(content: DocumentContent, context: RenderContext) -> bytes:  # noqa: ARG001
    ...verbatim body of _render_csv...


class _Doc:
    """Per-document state the block renderers share: numbering and table count."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.context = context
        self.numbered = document_is_numbered(content, context)
        self.numberer = HeadingNumberer()
        self.tables = 0

    def heading(self, block: SectionBlock) -> str:
        number = self.numberer.number(block.level) if self.numbered else ""
        return f"{number} {block.text}".strip()

    def table_label(self, block: SectionBlock) -> str:
        self.tables += 1
        label = self.context.label("documents.table_label", n=self.tables)
        return f"{label} — {block.caption}" if block.caption else label


def _md_table(table: TableSheet) -> list[str]:
    header = "| " + " | ".join(table.headers) + " |"
    rule = "| " + " | ".join("---" for _ in table.headers) + " |"
    return [header, rule, *("| " + " | ".join(row) + " |" for row in table.rows)]


_MD_BLOCKS: dict[str, Callable[[SectionBlock, _Doc], list[str]]] = {
    # The title owns "#": headings start at "##" even at level 1 (unchanged rule).
    "heading": lambda b, d: [f"{'#' * max(b.level, 2)} {d.heading(b)}"],
    "paragraph": lambda b, d: [b.text],
    "bullets": lambda b, d: [f"- {item}" for item in b.items],
    "numbered": lambda b, d: [f"{i}. {item}" for i, item in enumerate(b.items, start=1)],
    "quote": lambda b, d: [f"> {b.text}"],
    "callout": lambda b, d: [f"> **Note.** {b.text}"],
    "table": lambda b, d: [f"*{d.table_label(b)}*", "", *_md_table(b.table)] if b.table else [],
}


def render_md(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("md rendering requires SectionedContent")
    doc = _Doc(content, context)
    lines: list[str] = [f"# {content.title}", ""]
    if content.subtitle:
        lines += [f"*{content.subtitle}*", ""]
    if context.date_line:
        lines += [context.date_line, ""]
    for block in content.blocks:
        lines += [*_MD_BLOCKS[block.kind](block, doc), ""]
    return "\n".join(lines).encode("utf-8")


_TXT_BLOCKS: dict[str, Callable[[SectionBlock, _Doc], list[str]]] = {
    "heading": lambda b, d: [d.heading(b), "-" * len(d.heading(b))],
    "paragraph": lambda b, d: [strip_inline(b.text)],
    "bullets": lambda b, d: [f"  * {strip_inline(item)}" for item in b.items],
    "numbered": lambda b, d: [f"  {i}) {strip_inline(item)}" for i, item in enumerate(b.items, start=1)],
    "quote": lambda b, d: [f"    {strip_inline(b.text)}"],
    "callout": lambda b, d: ["-" * 40, strip_inline(b.text), "-" * 40],
    "table": lambda b, d: (
        [d.table_label(b), " / ".join(b.table.headers), *(" / ".join(r) for r in b.table.rows)]
        if b.table
        else []
    ),
}


def render_txt(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("txt rendering requires SectionedContent")
    doc = _Doc(content, context)
    lines: list[str] = [content.title, "=" * len(content.title)]
    if content.subtitle:
        lines.append(content.subtitle)
    if context.date_line:
        lines.append(context.date_line)
    lines.append("")
    for block in content.blocks:
        lines += [*_TXT_BLOCKS[block.kind](block, doc), ""]
    return "\n".join(lines).encode("utf-8")
```

`_Doc.heading` is called twice in the txt heading lambda — compute once: `"heading": lambda b, d: (lambda h: [h, "-" * len(h)])(d.heading(b))`.

- [ ] **Step 6: Run** the text tests and the whole domain suite → PASS (the old `test_level_one_heading_is_shifted_below_title` still holds). **Gate:** `task lint:backend`.

---

### Task 12: XLSX craft

**Files:**
- Modify: `apps/api/src/domains/document_generation/renderers/xlsx.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_renderer_xlsx.py` (new; move the `TestXlsxRenderer` class out of `test_renderers_office.py`)

**Interfaces:**
- Consumes: `infer_column_types`, `typed_value`, `excel_table_name` (Task 7); `typography.XLSX_*`; the content is already normalized (unique headers, widened rows).

- [ ] **Step 1: Write the failing tests** (`test_renderer_xlsx.py`; keep the three moved tests, change `test_negative_numbers_survive_untouched` to expect the float `-5.2`, and add):

```python
def _sheet(**kwargs) -> TableSheet:
    base = {"name": "Data", "headers": ["City", "Date", "Amount", "Share", "Zip"], "rows": [
        ["Strasbourg", "2026-09-01", "1234.5", "12%", "67000"],
        ["Colmar", "2026-09-02", "-98.25", "3.5%", "01000"],
    ]}
    return TableSheet(**{**base, **kwargs})


def _book(*sheets: TableSheet) -> openpyxl.Workbook:
    content = TabularContent(filename_stem="d", title="Data", sheets=list(sheets))
    return openpyxl.load_workbook(io.BytesIO(render_document(DocumentType.XLSX, content, RenderContext(language="en"))))


class TestXlsxCraft:
    def test_columns_are_typed_and_formatted(self) -> None:
        ws = _book(_sheet()).active
        assert ws["B2"].value.date().isoformat() == "2026-09-01" and ws["B2"].number_format == "yyyy-mm-dd"
        assert ws["C2"].value == 1234.5 and ws["C2"].number_format == "0.00"
        assert ws["D3"].value == pytest.approx(0.035) and ws["D3"].number_format == "0.0%"
        assert ws["E3"].value == "01000"  # the leading zero kept the column text
        assert ws["C2"].alignment.horizontal == "right"

    def test_table_filter_freeze_and_name(self) -> None:
        wb = _book(_sheet(), _sheet(name="Other"))
        first, second = wb.worksheets
        assert first.freeze_panes == "A2"
        assert list(first.tables) == ["Table1"] and list(second.tables) == ["Table2"]
        assert first.tables["Table1"].autoFilter is not None
        assert first.tables["Table1"].tableStyleInfo.showRowStripes

    def test_header_row_is_bold_and_widths_are_bounded(self) -> None:
        ws = _book(_sheet(rows=[["x" * 200, "2026-01-01", "1", "1%", "1"]])).active
        assert ws["A1"].font.bold
        assert 8 <= ws.column_dimensions["A"].width <= 60
        assert ws["A2"].alignment.wrap_text

    def test_a_sheet_without_rows_has_no_table_but_keeps_its_header(self) -> None:
        ws = _book(_sheet(rows=[])).active
        assert list(ws.tables) == [] and ws["A1"].value == "City"

    def test_workbook_title_metadata(self) -> None:
        wb = _book(_sheet())
        assert wb.properties.title == "Data"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement `renderers/xlsx.py`**

```python
"""xlsx: typed columns, a named Table, frozen header, filter (ADR-226, ADR-274)."""

from __future__ import annotations

import io
from datetime import UTC

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import DocumentContent, TableSheet, TabularContent
from src.domains.document_generation.tables import (
    ColumnKind,
    ColumnType,
    excel_table_name,
    infer_column_types,
    typed_value,
)

...keep _XLSX_TITLE_FORBIDDEN, _XLSX_TITLE_MAX and _xlsx_sheet_title verbatim...


def _alignment(column: ColumnType) -> Alignment | None:
    if column.numeric:
        return Alignment(horizontal="right")
    if column.kind in (ColumnKind.DATE, ColumnKind.DATETIME):
        return Alignment(horizontal="center")
    return None


def _fill_sheet(ws: Worksheet, sheet: TableSheet, table_index: int) -> None:
    types = infer_column_types(sheet.headers, sheet.rows)
    ws.append([neutralize_formula(header) for header in sheet.headers])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.rows:
        ws.append([typed_value(value, column) for value, column in zip(row, types, strict=True)])
    for index, (header, column) in enumerate(zip(sheet.headers, types, strict=True), start=1):
        letter = get_column_letter(index)
        longest = max([len(header), *(len(row[index - 1]) for row in sheet.rows)])
        width = min(max(longest + 2, typography.XLSX_COLUMN_WIDTH_MIN), typography.XLSX_COLUMN_WIDTH_MAX)
        ws.column_dimensions[letter].width = width
        alignment = _alignment(column)
        for (cell,) in ws.iter_rows(min_row=2, min_col=index, max_col=index):
            cell.number_format = column.number_format
            if alignment is not None:
                cell.alignment = alignment
            elif width >= typography.XLSX_COLUMN_WIDTH_MAX:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    if sheet.rows:
        reference = f"A1:{get_column_letter(len(sheet.headers))}{len(sheet.rows) + 1}"
        table = Table(displayName=excel_table_name(table_index), ref=reference)
        table.tableStyleInfo = TableStyleInfo(
            name=typography.XLSX_TABLE_STYLE,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)


def render_xlsx(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, TabularContent):
        raise ValueError("xlsx rendering requires TabularContent")
    wb = openpyxl.Workbook()
    wb.properties.title = content.title
    if context.generated_at is not None:
        wb.properties.created = context.generated_at.astimezone(UTC).replace(tzinfo=None)
    used_titles: set[str] = set()
    for index, sheet in enumerate(content.sheets):
        ws = wb.active if index == 0 else wb.create_sheet()
        ws.title = _xlsx_sheet_title(sheet.name, index, used_titles)
        _fill_sheet(ws, sheet, index + 1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run** the xlsx tests → PASS. Delete `TestXlsxRenderer` from `test_renderers_office.py`. **Gate:** `task lint:backend`. Then **render the corpus sheet through Excel** at Task 17's measurement and confirm `TableStyleLight1` reads as grayscale stripes; if it renders blue, switch `XLSX_TABLE_STYLE` to `TableStyleLight8` and record the choice in `typography.py`.

---

### Task 13: DOCX craft

**Files:**
- Create: `apps/api/src/domains/document_generation/renderers/docx_ooxml.py`
- Modify: `apps/api/src/domains/document_generation/renderers/docx.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_renderer_docx.py` (new; move `TestDocxRenderer` out of `test_renderers_office.py`)

**Interfaces:**
- `docx_ooxml.py` produces: `add_field(paragraph, instruction, cached="")`, `mark_header_row(row)`, `set_table_look(table, *, first_column)`, `add_heading_numbering(document)`, `detach_toc_heading(document)`, `fresh_list_num(document, style_name) -> int`, `set_paragraph_num(paragraph, num_id)`, `set_east_asian_font(style, name)`, `shade_paragraph_style(style, fill_hex)`, `left_border_style(style, color_hex)`, `recolor_title_rule(style, color_hex)`, `naive_utc(dt) -> datetime`.
- Consumes: `parse_inline`, `HeadingNumberer`, `document_is_numbered`, `infer_column_types`, typography constants, `context.label`.

- [ ] **Step 1: Write the failing tests**

```python
"""docx: named styles, fields, numbering, TOC, lists, tables — read back by python-docx."""

import io

import docx
import pytest
from docx.oxml.ns import qn

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import DocumentType, SectionBlock, SectionedContent, TableSheet

pytestmark = [pytest.mark.unit]


def _long(subtitle: str = "For the board") -> SectionedContent:
    blocks = []
    for part in range(1, 4):
        blocks.append(SectionBlock(kind="heading", level=1, text=f"{part}. Part {part}"))
        blocks.append(SectionBlock(kind="paragraph", text="Body **strong** text."))
        blocks.append(SectionBlock(kind="heading", level=2, text="Detail"))
        blocks.append(SectionBlock(kind="numbered", items=["one", "two"]))
    blocks.append(SectionBlock(kind="quote", text="verbatim"))
    blocks.append(SectionBlock(kind="callout", text="watch out"))
    blocks.append(SectionBlock(kind="table", caption="Figures", table=TableSheet(name="t", headers=["City", "Pop"], rows=[["A", "1"], ["B", "22"]])))
    return SectionedContent(filename_stem="r", title="Report", subtitle=subtitle, blocks=blocks)


def _render(content: SectionedContent, **ctx) -> docx.document.Document:
    context = RenderContext(language="en", **ctx)
    return docx.Document(io.BytesIO(render_document(DocumentType.DOCX, content, context)))


def _xml(document) -> str:
    return document.element.xml


class TestDocxCraft:
    def test_only_named_styles_and_a_title_block(self) -> None:
        d = _render(_long())
        styles = {p.style.name for p in d.paragraphs}
        assert {"Title", "Subtitle", "Heading 1", "Heading 2", "List Number", "Quote", "Callout", "Caption"} <= styles
        assert d.paragraphs[0].text == "Report" and d.paragraphs[1].text == "For the board"
        assert d.core_properties.title == "Report" and d.core_properties.subject == "For the board"

    def test_long_document_has_toc_numbering_and_part_breaks(self, monkeypatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "document_generation_toc_min_headings", 5)
        d = _render(_long())
        xml = _xml(d)
        assert 'TOC \\o "1-3" \\h \\z \\u \\n' in xml
        toc_entries = [p.text for p in d.paragraphs if p.style.name.startswith("TOC ")]
        assert toc_entries == ["1\tPart 1", "1.1\tDetail", "2\tPart 2", "2.1\tDetail", "3\tPart 3", "3.1\tDetail"]
        # The model's own "1." prefix was stripped; the numbering is native.
        assert [p.text for p in d.paragraphs if p.style.name == "Heading 1"] == ["Part 1", "Part 2", "Part 3"]
        heading1 = d.styles["Heading 1"].element
        assert heading1.pPr.find(qn("w:numPr")) is not None
        breaks = [p for p in d.paragraphs if p.style.name == "Heading 1" and p.paragraph_format.page_break_before]
        assert len(breaks) == 2  # every part but the first
        toc_heading = d.styles["TOC Heading"].element.pPr
        assert toc_heading.find(qn("w:numPr")).find(qn("w:numId")).get(qn("w:val")) == "0"

    def test_short_or_plain_documents_have_none_of_it(self, monkeypatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "document_generation_toc_min_headings", 50)
        d = _render(_long())
        assert "TOC \\o" not in _xml(d)
        assert [p.text for p in d.paragraphs if p.style.name == "Heading 1"] == ["1. Part 1", "2. Part 2", "3. Part 3"]
        monkeypatch.setattr(settings, "document_generation_toc_min_headings", 2)
        assert "TOC \\o" not in _xml(_render(_long(), structure="plain"))

    def test_footer_fields_header_and_page_size(self) -> None:
        d = _render(_long(), page_size="letter")
        section = d.sections[0]
        assert round(section.page_width.inches, 1) == 8.5
        assert section.header.paragraphs[0].text == "Report"
        footer_xml = section.footer._element.xml
        assert "PAGE" in footer_xml and "NUMPAGES" in footer_xml and "Page " in section.footer.paragraphs[0].text
        a4 = _render(_long(), page_size="a4").sections[0]
        assert round(a4.page_width.mm) == 210

    def test_numbered_lists_restart_per_list(self) -> None:
        xml = _xml(_render(_long()))
        assert xml.count("<w:startOverride") == 3  # one fresh num per numbered list

    def test_table_caption_header_repeat_and_numeric_alignment(self) -> None:
        d = _render(_long())
        assert [p.text for p in d.paragraphs if p.style.name == "Caption"] == ["Table 1 — Figures"]
        table = d.tables[0]
        assert table.rows[0]._tr.trPr.find(qn("w:tblHeader")) is not None
        assert table.cell(1, 1).paragraphs[0].alignment == 2  # WD_ALIGN_PARAGRAPH.RIGHT
        assert table.cell(1, 0).paragraphs[0].alignment in (None, 0)

    def test_inline_emphasis_becomes_runs_and_cjk_font_is_declared(self) -> None:
        d = _render(_long())
        strong = [r for p in d.paragraphs for r in p.runs if r.text == "strong"]
        assert strong and strong[0].bold
        assert 'w:eastAsia="Microsoft YaHei"' in d.styles["Normal"].element.xml

    def test_date_line_when_generated_at_is_given(self) -> None:
        from datetime import UTC, datetime

        d = _render(_long(), generated_at=datetime(2026, 9, 8, 12, tzinfo=UTC), timezone="Europe/Berlin")
        assert any("2026" in p.text for p in d.paragraphs[:3])
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Create `renderers/docx_ooxml.py`**

```python
"""Raw OOXML python-docx has no API for (ADR-274): fields, numbering, borders.

Each helper does ONE thing to ONE element and is exercised by the docx renderer
tests through Word's own reader (python-docx round trip) and, on the owner's
machine, by Word itself through the measurement harness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def naive_utc(moment: datetime) -> datetime:
    """Core properties are written as naive UTC by both python-docx and openpyxl."""
    return moment.astimezone(UTC).replace(tzinfo=None)


def _element(tag: str, **attributes: str) -> Any:
    element = OxmlElement(tag)
    for name, value in attributes.items():
        element.set(qn(f"w:{name}"), value)
    return element


def add_field(paragraph: Any, instruction: str, cached: str = "") -> None:
    """A complex field: begin / instruction / separate / cached result / end."""
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="begin"))
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    paragraph.add_run()._r.append(instr)
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="separate"))
    paragraph.add_run(cached)
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="end"))


def open_field(paragraph: Any, instruction: str) -> None:
    """The begin/instruction/separate triple of a field whose result spans paragraphs."""
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="begin"))
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    paragraph.add_run()._r.append(instr)
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="separate"))


def close_field(paragraph: Any) -> None:
    """The end marker of a field opened with :func:`open_field`."""
    paragraph.add_run()._r.append(_element("w:fldChar", fldCharType="end"))


def mark_header_row(row: Any) -> None:
    """Repeat this row at the top of every page the table continues on."""
    row._tr.get_or_add_trPr().append(_element("w:tblHeader", val="true"))


def set_table_look(table: Any, *, first_column: bool) -> None:
    """Which conditional formats of the style apply (header row on, banding on)."""
    tbl_pr = table._tbl.tblPr
    for stale in tbl_pr.findall(qn("w:tblLook")):
        tbl_pr.remove(stale)
    tbl_pr.append(
        _element(
            "w:tblLook",
            firstRow="1",
            lastRow="0",
            firstColumn="1" if first_column else "0",
            lastColumn="0",
            noHBand="0",
            noVBand="1",
        )
    )


def _numbering_root(document: Any) -> Any:
    return document.part.numbering_part.element


def _next_id(root: Any, tag: str, attribute: str) -> int:
    return max((int(n.get(qn(attribute))) for n in root.findall(qn(tag))), default=-1) + 1


def add_heading_numbering(document: Any) -> None:
    """One multilevel list bound to Heading 1-3 (1 / 1.1 / 1.1.1)."""
    root = _numbering_root(document)
    abstract_id = _next_id(root, "w:abstractNum", "w:abstractNumId")
    abstract = _element("w:abstractNum", abstractNumId=str(abstract_id))
    abstract.append(_element("w:multiLevelType", val="multilevel"))
    for level, text in enumerate(("%1", "%1.%2", "%1.%2.%3")):
        lvl = _element("w:lvl", ilvl=str(level))
        lvl.append(_element("w:start", val="1"))
        lvl.append(_element("w:numFmt", val="decimal"))
        lvl.append(_element("w:pStyle", val=f"Heading{level + 1}"))
        lvl.append(_element("w:lvlText", val=text))
        lvl.append(_element("w:lvlJc", val="left"))
        ppr = OxmlElement("w:pPr")
        ppr.append(_element("w:ind", left="0", hanging="0"))
        lvl.append(ppr)
        abstract.append(lvl)
    first_num = root.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(abstract)  # abstractNum elements precede num elements
    else:
        root.append(abstract)
    num_id = _next_id(root, "w:num", "w:numId") or 1
    num = _element("w:num", numId=str(num_id))
    num.append(_element("w:abstractNumId", val=str(abstract_id)))
    root.append(num)
    for level in range(3):
        ppr = document.styles[f"Heading {level + 1}"].element.get_or_add_pPr()
        numpr = OxmlElement("w:numPr")
        numpr.append(_element("w:ilvl", val=str(level)))
        numpr.append(_element("w:numId", val=str(num_id)))
        ppr.append(numpr)


def detach_toc_heading(document: Any) -> None:
    """``TOC Heading`` is based on Heading 1: take it out of the numbering and the outline."""
    ppr = document.styles["TOC Heading"].element.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    numpr.append(_element("w:ilvl", val="0"))
    numpr.append(_element("w:numId", val="0"))
    ppr.append(numpr)
    ppr.append(_element("w:outlineLvl", val="9"))


def fresh_list_num(document: Any, style_name: str) -> int:
    """A new ``w:num`` on the style's abstract list, restarting at 1."""
    root = _numbering_root(document)
    style_numpr = document.styles[style_name].element.pPr.find(qn("w:numPr"))
    style_num_id = style_numpr.find(qn("w:numId")).get(qn("w:val"))
    abstract_id = next(
        num.find(qn("w:abstractNumId")).get(qn("w:val"))
        for num in root.findall(qn("w:num"))
        if num.get(qn("w:numId")) == style_num_id
    )
    num_id = _next_id(root, "w:num", "w:numId")
    num = _element("w:num", numId=str(num_id))
    num.append(_element("w:abstractNumId", val=abstract_id))
    override = _element("w:lvlOverride", ilvl="0")
    override.append(_element("w:startOverride", val="1"))
    num.append(override)
    root.append(num)
    return num_id


def set_paragraph_num(paragraph: Any, num_id: int) -> None:
    """Bind a list paragraph to a numbering instance."""
    numpr = OxmlElement("w:numPr")
    numpr.append(_element("w:ilvl", val="0"))
    numpr.append(_element("w:numId", val=str(num_id)))
    paragraph._p.get_or_add_pPr().append(numpr)


def set_east_asian_font(style: Any, name: str) -> None:
    """Declare the East-Asian face so CJK never falls back to a Latin one."""
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def shade_paragraph_style(style: Any, fill_hex: str) -> None:
    """Background fill of every paragraph of the style."""
    style.element.get_or_add_pPr().append(_element("w:shd", val="clear", color="auto", fill=fill_hex))


def left_border_style(style: Any, color_hex: str) -> None:
    """A left rule on every paragraph of the style."""
    borders = OxmlElement("w:pBdr")
    borders.append(_element("w:left", val="single", sz="18", space="8", color=color_hex))
    style.element.get_or_add_pPr().append(borders)


def recolor_title_rule(style: Any, color_hex: str) -> None:
    """The Title style's theme-blue bottom rule becomes a neutral grey one."""
    ppr = style.element.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    bottom = borders.find(qn("w:bottom")) if borders is not None else None
    if bottom is not None:
        bottom.set(qn("w:color"), color_hex)
        for theme_attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
            bottom.attrib.pop(qn(theme_attr), None)
```

- [ ] **Step 4: Rewrite `renderers/docx.py`**

```python
"""docx: named styles, fields, numbering, table of contents, tables (ADR-226, ADR-274).

Everything is a NAMED style redefined once from ``typography`` — a reader can
restyle the document from Word's gallery — and everything Word computes itself
(page numbers, the table of contents, heading numbers) is a field or a
numbering definition, never text pretending to be one. The long-document
apparatus follows ONE predicate (``document_is_numbered``): table of contents,
heading numbering and a page break before each part switch on together.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from typing import Any

import docx
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Mm, Pt, RGBColor

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.normalize import HeadingNumberer, document_is_numbered
from src.domains.document_generation.renderers import docx_ooxml as ooxml
from src.domains.document_generation.schemas import DocumentContent, SectionBlock, SectionedContent
from src.domains.document_generation.tables import infer_column_types

_PAGE_OF_TOKENS = re.compile(r"(\{page\}|\{total\})")
_TOC_LEVELS = 3
_CALLOUT_STYLE = "Callout"


class _Writer:
    """Per-document state: the python-docx document, numbering, table count."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.document = docx.Document()
        self.numbered = document_is_numbered(content, context)
        self.numberer = HeadingNumberer()
        self.tables = 0
        self.first_part_seen = False

    # --- setup -----------------------------------------------------------
    def setup(self) -> None:
        section = self.document.sections[0]
        if self.context.page_size == "letter":
            section.page_width, section.page_height = Inches(8.5), Inches(11)
        else:
            section.page_width, section.page_height = Mm(210), Mm(297)
        margin = Cm(typography.docx_margin_cm(self.context.page_size))
        section.left_margin = section.right_margin = margin
        section.top_margin = section.bottom_margin = margin
        self._styles()
        properties = self.document.core_properties
        properties.title = self.content.title
        properties.subject = self.content.subtitle
        properties.language = self.context.language
        if self.context.generated_at is not None:
            properties.created = ooxml.naive_utc(self.context.generated_at)

    def _styles(self) -> None:
        styles = self.document.styles
        for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3", "Heading 4",
                     "Caption", "Quote", "List Bullet", "List Number", "Header", "Footer", "TOC Heading"):
            style = styles[name]
            style.font.name = typography.FONT_BODY
            ooxml.set_east_asian_font(style, typography.FONT_EAST_ASIA)
        normal = styles["Normal"]
        normal.font.size = Pt(typography.DOCX_BODY_PT)
        normal.font.color.rgb = RGBColor.from_string(typography.INK)
        normal.paragraph_format.line_spacing = typography.DOCX_LINE_SPACING
        normal.paragraph_format.space_after = Pt(typography.DOCX_SPACE_AFTER_PT)
        normal.paragraph_format.widow_control = True
        title = styles["Title"]
        title.font.size = Pt(typography.DOCX_TITLE_PT)
        title.font.color.rgb = RGBColor.from_string(typography.INK)
        ooxml.recolor_title_rule(title, typography.RULE)
        subtitle = styles["Subtitle"]
        subtitle.font.size = Pt(typography.DOCX_SUBTITLE_PT)
        subtitle.font.color.rgb = RGBColor.from_string(typography.MUTED)
        subtitle.font.italic = False
        for level, size in typography.DOCX_HEADING_PT.items():
            heading = styles[f"Heading {level}"]
            heading.font.size = Pt(size)
            heading.font.bold = True
            heading.font.color.rgb = RGBColor.from_string(typography.HEADING_INK)
        for name in ("Caption", "Header", "Footer"):
            styles[name].font.size = Pt(typography.DOCX_CAPTION_PT)
            styles[name].font.color.rgb = RGBColor.from_string(typography.MUTED)
        quote = styles["Quote"]
        quote.font.italic = True
        quote.font.color.rgb = RGBColor.from_string(typography.MUTED)
        quote.paragraph_format.left_indent = Cm(1)
        callout = styles.add_style(_CALLOUT_STYLE, WD_STYLE_TYPE.PARAGRAPH)
        callout.base_style = normal
        callout.paragraph_format.left_indent = Cm(0.5)
        callout.paragraph_format.space_before = Pt(6)
        callout.paragraph_format.space_after = Pt(10)
        ooxml.shade_paragraph_style(callout, typography.BAND)
        ooxml.left_border_style(callout, typography.MUTED)
        toc_heading = styles["TOC Heading"]
        toc_heading.font.color.rgb = RGBColor.from_string(typography.HEADING_INK)
        ooxml.detach_toc_heading(self.document)
        for level in range(1, _TOC_LEVELS + 1):
            name = f"TOC {level}"
            if name not in {s.name for s in styles}:
                toc_style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
                toc_style.base_style = normal
                toc_style.paragraph_format.left_indent = Cm(typography.DOCX_TOC_INDENT_CM * (level - 1))
                toc_style.paragraph_format.space_after = Pt(2)
        if self.numbered:
            ooxml.add_heading_numbering(self.document)

    # --- front matter ----------------------------------------------------
    def front_matter(self) -> None:
        self.document.add_paragraph(self.content.title, style="Title")
        if self.content.subtitle:
            self.document.add_paragraph(self.content.subtitle, style="Subtitle")
        if self.context.date_line:
            date = self.document.add_paragraph()
            run = date.add_run(self.context.date_line)
            run.font.color.rgb = RGBColor.from_string(typography.MUTED)
        section = self.document.sections[0]
        section.header.paragraphs[0].text = self.content.title
        section.header.paragraphs[0].style = self.document.styles["Header"]
        footer = section.footer.paragraphs[0]
        footer.style = self.document.styles["Footer"]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for piece in _PAGE_OF_TOKENS.split(self.context.label("documents.page_of", page="{page}", total="{total}")):
            if piece == "{page}":
                ooxml.add_field(footer, "PAGE", "1")
            elif piece == "{total}":
                ooxml.add_field(footer, "NUMPAGES", "1")
            elif piece:
                footer.add_run(piece)
        if self.numbered:
            self._table_of_contents()

    def _table_of_contents(self) -> None:
        self.document.add_paragraph(self.context.label("documents.toc_heading"), style="TOC Heading")
        entries = []
        numberer = HeadingNumberer()
        for block in self.content.blocks:
            if block.kind == "heading" and block.level <= _TOC_LEVELS:
                entries.append((block.level, f"{numberer.number(block.level)}\t{block.text}"))
        paragraph = None
        for index, (level, text) in enumerate(entries):
            paragraph = self.document.add_paragraph(style=f"TOC {level}")
            if index == 0:
                ooxml.open_field(paragraph, f'TOC \\o "1-{_TOC_LEVELS}" \\h \\z \\u \\n')
            paragraph.add_run(text)
        if paragraph is not None:
            ooxml.close_field(paragraph)
        self.document.add_page_break()

    # --- blocks ----------------------------------------------------------
    def runs(self, paragraph: Any, text: str) -> None:
        for span in parse_inline(text):
            run = paragraph.add_run(span.text)
            run.bold = span.bold or None
            run.italic = span.italic or None
            if span.code:
                run.font.name = "Consolas"

    def heading(self, block: SectionBlock) -> None:
        paragraph = self.document.add_heading(block.text, level=block.level)
        if self.numbered and block.level == 1:
            paragraph.paragraph_format.page_break_before = self.first_part_seen
            self.first_part_seen = True

    def paragraph(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(), block.text)

    def bullets(self, block: SectionBlock) -> None:
        for item in block.items:
            self.runs(self.document.add_paragraph(style="List Bullet"), item)

    def numbered_list(self, block: SectionBlock) -> None:
        num_id = ooxml.fresh_list_num(self.document, "List Number")
        for item in block.items:
            paragraph = self.document.add_paragraph(style="List Number")
            ooxml.set_paragraph_num(paragraph, num_id)
            self.runs(paragraph, item)

    def quote(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(style="Quote"), block.text)

    def callout(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(style=_CALLOUT_STYLE), block.text)

    def table(self, block: SectionBlock) -> None:
        sheet = block.table
        if sheet is None:
            return
        self.tables += 1
        label = self.context.label("documents.table_label", n=self.tables)
        if block.caption:
            self.document.add_paragraph(f"{label} — {block.caption}", style="Caption")
        types = infer_column_types(sheet.headers, sheet.rows)
        table = self.document.add_table(rows=1, cols=len(sheet.headers))
        table.style = typography.DOCX_TABLE_STYLE
        table.autofit = True
        ooxml.set_table_look(table, first_column=False)
        for index, header in enumerate(sheet.headers):
            table.cell(0, index).text = header
        ooxml.mark_header_row(table.rows[0])
        for row in sheet.rows:
            cells = table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = value
                if types[index].numeric:
                    cells[index].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        self.document.add_paragraph()


_BLOCKS: dict[str, Callable[[_Writer, SectionBlock], None]] = {
    "heading": _Writer.heading,
    "paragraph": _Writer.paragraph,
    "bullets": _Writer.bullets,
    "numbered": _Writer.numbered_list,
    "quote": _Writer.quote,
    "callout": _Writer.callout,
    "table": _Writer.table,
}


def render_docx(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("docx rendering requires SectionedContent")
    writer = _Writer(content, context)
    writer.setup()
    writer.front_matter()
    for block in content.blocks:
        _BLOCKS[block.kind](writer, block)
    buf = io.BytesIO()
    writer.document.save(buf)
    return buf.getvalue()
```

If `_Writer` pushes `docx.py` past the SLOC cap, move `_styles` into `docx_styles.py` (a `define_styles(document, numbered)` function) — same tests.

- [ ] **Step 5: Run** the docx tests → PASS; run the meetings tests → PASS. Delete `TestDocxRenderer` from `test_renderers_office.py`. **Gate:** `task lint:backend`. At Task 17's measurement, look at the Word export of the corpus report: if "Light List" (black header) reads too heavy, switch `DOCX_TABLE_STYLE` to `"Light Grid"` and re-run the docx tests.

---

### Task 14: PPTX craft — 16:9, layouts by kind, nothing overflows

**Files:**
- Create: `apps/api/src/domains/document_generation/renderers/pptx_geometry.py`
- Modify: `apps/api/src/domains/document_generation/renderers/pptx.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_renderer_pptx.py` (new; move `TestPptxRenderer` out of `test_renderers_office.py`, then delete that file)

**Interfaces:**
- `pptx_geometry.py` produces: `base_presentation()`, `placeholder(slide, idx)`, `add_slide_number(slide, layout)`, `frame_of(shape, indent_pt=BULLET_INDENT_PT) -> TextFrame`, `remove_shape(shape)`, constants `LAYOUT_TITLE=0, LAYOUT_CONTENT=1, LAYOUT_SECTION=2, LAYOUT_COMPARISON=4, LAYOUT_TITLE_ONLY=5`, `EMU_PER_PT = 12700`, `TABLE_LEFT_IN=0.667`, `TABLE_TOP_IN=1.75`, `TABLE_WIDTH_IN=12.0`, `TABLE_AREA_HEIGHT_IN=4.95`.
- Consumes: `plan_body`, `fit_title`, `rows_per_slide`, `table_font_size`, `TABLE_ROW_HEIGHT_PT` (Task 9); `parse_inline`; `infer_column_types`, `chunk_rows`; typography.

- [ ] **Step 1: Write the failing tests**

```python
"""pptx: 16:9 landscape, a layout per kind, slide numbers, and nothing overflows."""

import io

import pptx
import pytest
from pptx.util import Pt

from pptx.enum.shapes import PP_PLACEHOLDER

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import BULLET_INDENT_PT, TextFrame, fits
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.renderers.pptx_geometry import EMU_PER_PT
from src.domains.document_generation.schemas import DocumentType, Slide, SlideColumn, SlideContent, TableSheet

pytestmark = [pytest.mark.unit]
_TITLE_TYPES = (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)


def _deck(*slides: Slide, subtitle: str = "") -> pptx.presentation.Presentation:
    content = SlideContent(filename_stem="d", title="Deck", subtitle=subtitle, slides=list(slides))
    data = render_document(DocumentType.PPTX, content, RenderContext(language="en"))
    return pptx.Presentation(io.BytesIO(data))


def _assert_nothing_overflows(presentation) -> None:
    """The internal oracle: every text frame stays inside the estimator's budget."""
    for slide in presentation.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame or not shape.text_frame.text.strip():
                continue
            placeholder_type = shape.placeholder_format.type if shape.is_placeholder else None
            if placeholder_type == PP_PLACEHOLDER.SLIDE_NUMBER:
                continue
            indent = 0.0 if placeholder_type in _TITLE_TYPES else BULLET_INDENT_PT
            frame = TextFrame(shape.width / EMU_PER_PT, shape.height / EMU_PER_PT, indent_pt=indent)
            paragraphs = [p.text for p in shape.text_frame.paragraphs]
            sizes = [r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size]
            assert fits(paragraphs, max(sizes) if sizes else 18.0, frame), (shape.name, paragraphs[:2])


class TestPptxCraft:
    def test_slides_are_16_9_landscape(self) -> None:
        p = _deck(Slide(title="t", bullets=["a"]))
        assert (round(p.slide_width / EMU_PER_PT), round(p.slide_height / EMU_PER_PT)) == (960, 540)
        assert p.slide_width > p.slide_height

    def test_cover_then_layouts_by_kind_and_slide_numbers(self) -> None:
        table = TableSheet(name="t", headers=["City", "Pop"], rows=[["A", "1"]])
        p = _deck(
            Slide(title="Part", kind="section", subtitle="tag"),
            Slide(title="Content", bullets=["a", "b"]),
            Slide(title="A vs B", kind="comparison", columns=[SlideColumn(heading="A", bullets=["a"]), SlideColumn(heading="B", bullets=["b"])]),
            Slide(title="Data", kind="table", table=table),
            subtitle="Board",
        )
        names = [s.slide_layout.name for s in p.slides]
        assert names == ["Title Slide", "Section Header", "Title and Content", "Comparison", "Title Only"]
        for index, slide in enumerate(p.slides):
            has_number = any("slidenum" in shape._element.xml for shape in slide.shapes)
            assert has_number == (index > 0), index
        assert any(shape.has_table for shape in p.slides[4].shapes)

    def test_dense_content_is_split_never_overflowed(self) -> None:
        bullets = [f"Point {i} — " + "texte assez long pour tester le débordement " * 3 for i in range(9)]
        p = _deck(Slide(title="Dense", bullets=bullets, notes="n"))
        content_slides = [s for s in p.slides if s.slide_layout.name == "Title and Content"]
        assert len(content_slides) >= 2
        titles = [s.shapes.title.text for s in content_slides]
        assert titles[0].endswith(f"(1/{len(content_slides)})")
        assert "".join(p.text for s in content_slides for p in s.placeholders[1].text_frame.paragraphs).count("Point") == 9
        assert content_slides[0].has_notes_slide and "n" in content_slides[0].notes_slide.notes_text_frame.text
        _assert_nothing_overflows(p)

    def test_long_titles_shrink(self) -> None:
        p = _deck(Slide(title="Un titre de diapositive assez long pour tester la casse sur deux lignes", bullets=["a"]))
        title = p.slides[1].shapes.title
        assert max(r.font.size.pt for para in title.text_frame.paragraphs for r in para.runs) < 40
        _assert_nothing_overflows(p)

    def test_tables_are_chunked_with_the_header_repeated_and_neutral_style(self) -> None:
        rows = [[f"City {i}", str(100000 + i)] for i in range(30)]
        p = _deck(Slide(title="Cities", kind="table", table=TableSheet(name="t", headers=["City", "Population"], rows=rows)))
        table_slides = [s for s in p.slides if any(sh.has_table for sh in s.shapes)]
        assert len(table_slides) == 3
        assert [s.shapes.title.text for s in table_slides] == ["Cities (1/3)", "Cities (2/3)", "Cities (3/3)"]
        for slide in table_slides:
            table = next(sh for sh in slide.shapes if sh.has_table).table
            assert table.cell(0, 0).text == "City"
        assert "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}" in table_slides[0]._element.xml

    def test_comparison_headings_and_section_without_caps(self) -> None:
        p = _deck(
            Slide(title="Part", kind="section", subtitle="tag"),
            Slide(title="A vs B", kind="comparison", columns=[SlideColumn(heading="A", bullets=["a1"]), SlideColumn(heading="B", bullets=["b1"])]),
        )
        section = p.slides[1]
        assert 'cap="none"' in section.shapes.title._element.xml
        texts = {sh.text_frame.text for sh in p.slides[2].shapes if sh.has_text_frame}
        assert {"A", "B", "a1", "b1", "A vs B"} <= texts

    def test_inline_emphasis_becomes_runs(self) -> None:
        p = _deck(Slide(title="t", bullets=["a **b** c"]))
        runs = [r for para in p.slides[1].placeholders[1].text_frame.paragraphs for r in para.runs]
        assert [(r.text, bool(r.font.bold)) for r in runs] == [("a ", False), ("b", True), (" c", False)]
```

The oracle and the renderer share ONE formula: `fit_title` (Task 9) and every single-line fill below decide with `fits(...)`, exactly what `_assert_nothing_overflows` re-checks.

- [ ] **Step 2: Run** → FAIL. **Step 3: Create `renderers/pptx_geometry.py`**

```python
"""16:9 by scaling the default template; placeholders; slide numbers (ADR-274).

python-pptx's default template is 4:3 and its layout placeholders do not follow
a slide-size change. Scaling every master shape and every layout placeholder
that OWNS an ``xfrm`` by 4/3 makes a 13.333 × 7.5 in deck whose placeholders
sit where PowerPoint expects them (measured 2026-09-08: no overflow, slide
numbers rendered). Writing an INHERITED position freezes ``y``/``cy`` at 0 —
only owned transforms are touched.
"""

from __future__ import annotations

import copy
from typing import Any

import pptx
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.util import Inches

from src.domains.document_generation import typography
from src.domains.document_generation.fit import BULLET_INDENT_PT, TextFrame

LAYOUT_TITLE = 0
LAYOUT_CONTENT = 1
LAYOUT_SECTION = 2
LAYOUT_COMPARISON = 4
LAYOUT_TITLE_ONLY = 5
EMU_PER_PT = 12700
TABLE_LEFT_IN = 0.667
TABLE_TOP_IN = 1.75
TABLE_WIDTH_IN = 12.0
TABLE_AREA_HEIGHT_IN = 4.95


def _scale(shapes: Any, scale: float) -> None:
    for shape in shapes:
        sp_pr = shape._element.spPr
        if sp_pr is None or sp_pr.xfrm is None:
            continue
        shape.left = int(shape.left * scale)
        shape.width = int(shape.width * scale)


def base_presentation() -> Any:
    """The default template turned 16:9 landscape, placeholders in place."""
    presentation = pptx.Presentation()
    width = Inches(typography.PPTX_SLIDE_WIDTH_IN)
    scale = width / presentation.slide_width
    presentation.slide_width = width
    presentation.slide_height = Inches(typography.PPTX_SLIDE_HEIGHT_IN)
    _scale(presentation.slide_master.shapes, scale)
    for layout in presentation.slide_layouts:
        _scale(layout.placeholders, scale)
    return presentation


def placeholder(slide: Any, idx: int) -> Any:
    """The placeholder with this layout index."""
    for candidate in slide.placeholders:
        if candidate.placeholder_format.idx == idx:
            return candidate
    raise KeyError(idx)


def add_slide_number(slide: Any, layout: Any) -> None:
    """Clone the layout's slide-number placeholder; PowerPoint renders the field."""
    for candidate in layout.placeholders:
        if candidate.placeholder_format.type == PP_PLACEHOLDER.SLIDE_NUMBER:
            slide.shapes._spTree.append(copy.deepcopy(candidate._element))
            return


def remove_shape(shape: Any) -> None:
    """Drop an unused placeholder so no "Click to add" prompt survives."""
    element = shape._element
    element.getparent().remove(element)


def frame_of(shape: Any, indent_pt: float = BULLET_INDENT_PT) -> TextFrame:
    """The shape's box as a text frame in points."""
    return TextFrame(shape.width / EMU_PER_PT, shape.height / EMU_PER_PT, indent_pt=indent_pt)
```

- [ ] **Step 4: Rewrite `renderers/pptx.py`**

```python
"""pptx: a layout per kind, slide numbers, text that always fits (ADR-226, ADR-274)."""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from typing import Any

from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import (
    BODY_SIZE_FLOOR_PT,
    TABLE_ROW_HEIGHT_PT,
    SlidePlan,
    TextFrame,
    fit_title,
    fits,
    plan_body,
    rows_per_slide,
    table_font_size,
)
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.schemas import DocumentContent, Slide, SlideContent, TableSheet
from src.domains.document_generation.tables import chunk_rows, infer_column_types


def _continued(title: str, index: int, total: int) -> str:
    return title if total == 1 else f"{title} ({index}/{total})"


def _set_title(shape: Any, text: str) -> None:
    size, _ = fit_title(text, geometry.frame_of(shape, indent_pt=0))
    frame = shape.text_frame
    frame.text = ""
    run = frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(size)


def _fit_single(lines: Sequence[str], shape: Any, base_pt: int) -> int:
    """The largest size from ``base_pt`` down to the floor at which ``lines`` fit the shape."""
    frame = geometry.frame_of(shape)
    size = base_pt
    while size > BODY_SIZE_FLOOR_PT and not fits(lines, size, frame):
        size -= 2
    return size


def _fill(text_frame: Any, items: Sequence[str], size_pt: float, *, color: str | None = None) -> None:
    text_frame.text = ""
    for index, item in enumerate(items):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        for span in parse_inline(item):
            run = paragraph.add_run()
            run.text = span.text
            run.font.size = Pt(size_pt)
            run.font.bold = span.bold or None
            run.font.italic = span.italic or None
            if color is not None:
                from pptx.dml.color import RGBColor

                run.font.color.rgb = RGBColor.from_string(color)


class _Deck:
    """Per-deck state: the presentation and its layouts."""

    def __init__(self, content: SlideContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.presentation = geometry.base_presentation()
        self.layouts = self.presentation.slide_layouts
        # Layout placeholders carry the geometry every slide of that layout gets.
        self.body_frame = geometry.frame_of(geometry.placeholder(self.layouts[geometry.LAYOUT_CONTENT], 1))
        self.half_frame = geometry.frame_of(geometry.placeholder(self.layouts[geometry.LAYOUT_COMPARISON], 2))

    def _new(self, layout_index: int, title: str, notes: str = "") -> Any:
        layout = self.layouts[layout_index]
        slide = self.presentation.slides.add_slide(layout)
        _set_title(slide.shapes.title, title)
        geometry.add_slide_number(slide, layout)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        return slide

    def cover(self) -> None:
        slide = self.presentation.slides.add_slide(self.layouts[geometry.LAYOUT_TITLE])
        _set_title(slide.shapes.title, self.content.title)
        subtitle = geometry.placeholder(slide, 1)
        lines = [line for line in (self.content.subtitle, self.context.date_line) if line]
        if not lines:
            geometry.remove_shape(subtitle)
            return
        size = _fit_single(lines, subtitle, typography.PPTX_SUBTITLE_PT)
        _fill(subtitle.text_frame, lines[:1], size)
        if len(lines) == 2:
            paragraph = subtitle.text_frame.add_paragraph()
            run = paragraph.add_run()
            run.text = lines[1]
            run.font.size = Pt(min(size, typography.PPTX_DATE_PT))

    def content_slide(self, spec: Slide) -> None:
        plans = plan_body(spec.bullets, self.body_frame)
        for index, plan in enumerate(plans, start=1):
            slide = self._new(geometry.LAYOUT_CONTENT, _continued(spec.title, index, len(plans)), spec.notes if index == 1 else "")
            body = geometry.placeholder(slide, 1)
            if plan.bullets:
                _fill(body.text_frame, plan.bullets, plan.size_pt)
            else:
                geometry.remove_shape(body)

    def section(self, spec: Slide) -> None:
        slide = self._new(geometry.LAYOUT_SECTION, spec.title, spec.notes)
        for paragraph in slide.shapes.title.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font._rPr.set("cap", "none")
        tagline = geometry.placeholder(slide, 1)
        if spec.subtitle:
            size = _fit_single([spec.subtitle], tagline, typography.PPTX_SECTION_TAGLINE_PT)
            _fill(tagline.text_frame, [spec.subtitle], size, color=typography.MUTED)
        else:
            geometry.remove_shape(tagline)

    def comparison(self, spec: Slide) -> None:
        plans = [plan_body(column.bullets, self.half_frame) for column in spec.columns]
        total = max(len(side) for side in plans)
        for index in range(total):
            slide = self._new(geometry.LAYOUT_COMPARISON, _continued(spec.title, index + 1, total), spec.notes if index == 0 else "")
            for side, (heading_idx, body_idx) in enumerate(((1, 2), (3, 4))):
                heading = geometry.placeholder(slide, heading_idx)
                heading_size = _fit_single([spec.columns[side].heading], heading, typography.PPTX_COMPARISON_HEADING_PT)
                _fill(heading.text_frame, [spec.columns[side].heading], heading_size)
                plan: SlidePlan | None = plans[side][index] if index < len(plans[side]) else None
                body = geometry.placeholder(slide, body_idx)
                if plan is not None and plan.bullets:
                    _fill(body.text_frame, plan.bullets, plan.size_pt)
                else:
                    geometry.remove_shape(body)

    def table(self, spec: Slide) -> None:
        sheet = spec.table
        if sheet is None:
            return
        columns = len(sheet.headers)
        font_pt = table_font_size(columns)
        area = TextFrame(geometry.TABLE_WIDTH_IN * 72, geometry.TABLE_AREA_HEIGHT_IN * 72)
        chunks = chunk_rows(sheet.rows, rows_per_slide(columns, area)) or [[]]
        types = infer_column_types(sheet.headers, sheet.rows)
        for index, rows in enumerate(chunks, start=1):
            slide = self._new(geometry.LAYOUT_TITLE_ONLY, _continued(spec.title, index, len(chunks)), spec.notes if index == 1 else "")
            self._table_shape(slide, TableSheet(name=sheet.name, headers=sheet.headers, rows=rows), types, font_pt)

    def _table_shape(self, slide: Any, sheet: TableSheet, types: Any, font_pt: int) -> None:
        row_height = Pt(TABLE_ROW_HEIGHT_PT[font_pt])
        shape = slide.shapes.add_table(
            len(sheet.rows) + 1, len(sheet.headers),
            Inches(geometry.TABLE_LEFT_IN), Inches(geometry.TABLE_TOP_IN),
            Inches(geometry.TABLE_WIDTH_IN), row_height * (len(sheet.rows) + 1),
        )
        table = shape.table
        shape._element.graphic.graphicData.tbl.tblPr.find(qn("a:tableStyleId")).text = typography.PPTX_TABLE_STYLE_ID
        table.first_row, table.horz_banding, table.first_col = True, True, False
        widths = [max(len(header), *(len(row[i]) for row in sheet.rows), 4) for i, header in enumerate(sheet.headers)]
        total = sum(widths)
        for i, weight in enumerate(widths):
            table.columns[i].width = int(Inches(geometry.TABLE_WIDTH_IN) * weight / total)
        for column, header in enumerate(sheet.headers):
            self._cell(table.cell(0, column), header, font_pt, bold=True, right=types[column].numeric)
        for row_index, row in enumerate(sheet.rows, start=1):
            for column, value in enumerate(row):
                self._cell(table.cell(row_index, column), value, font_pt, bold=False, right=types[column].numeric)

    @staticmethod
    def _cell(cell: Any, text: str, font_pt: int, *, bold: bool, right: bool) -> None:
        cell.text = text
        paragraph = cell.text_frame.paragraphs[0]
        paragraph.font.size = Pt(font_pt)
        paragraph.font.bold = bold
        if right:
            paragraph.alignment = PP_ALIGN.RIGHT


_KINDS: dict[str, Callable[[_Deck, Slide], None]] = {
    "content": _Deck.content_slide,
    "section": _Deck.section,
    "comparison": _Deck.comparison,
    "table": _Deck.table,
}


def render_pptx(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, SlideContent):
        raise ValueError("pptx rendering requires SlideContent")
    deck = _Deck(content, context)
    deck.cover()
    for spec in content.slides:
        _KINDS[spec.kind](deck, spec)
    buf = io.BytesIO()
    deck.presentation.save(buf)
    return buf.getvalue()
```

One detail the tests pin: `geometry.placeholder` works on a layout as on a slide (both expose `.placeholders`), which is how `_Deck.__init__` reads the two frames once.

- [ ] **Step 5: Run** the pptx tests → PASS; delete `test_renderers_office.py`. **Gate:** `task lint:backend` (if `pptx.py` exceeds the SLOC cap or `_Deck` grows a function ≥ 15, move the table code into `pptx_tables.py`).

---

### Task 15: PDF craft — stylesheet, exact TOC, bookmarks, stamps, safe tables

**Files:**
- Create: `apps/api/src/domains/document_generation/renderers/pdf_layout.py`
- Modify: `apps/api/src/domains/document_generation/renderers/pdf.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_renderer_pdf.py` (extend)

**Interfaces:**
- `pdf_layout.py` produces: `Placed(page: int, rect: fitz.Rect)`, `LaidOut(pdf: bytes, pages: int, positions: dict[str, Placed])`, `lay_out(html, css, page_size) -> LaidOut`, `finish(laid, *, header, footer_label, outline, links) -> bytes` where `outline: list[tuple[int, str, int]]` (level, title, page) and `links: list[tuple[str, int]]` (element id → target page), `content_rect(page_size) -> fitz.Rect`.
- Consumes: `typography.pdf_css`, `page_rect_name`, `PDF_MARGIN_PT`, `PDF_STAMP_PT`, `MUTED`; `parse_inline`; `HeadingNumberer`, `document_is_numbered`; `infer_column_types`; `context.label`.

- [ ] **Step 1: Write the failing tests** (append to `test_renderer_pdf.py`; keep the existing three):

```python
from src.domains.document_generation.context import RenderContext


def _long_pdf(structure: str = "auto", pages_of_text: int = 3) -> bytes:
    blocks = []
    for part in range(1, 7):
        blocks.append(SectionBlock(kind="heading", level=1, text=f"Part {part}"))
        blocks.append(SectionBlock(kind="paragraph", text="Lorem ipsum dolor sit amet. " * 60 * pages_of_text))
    blocks.append(SectionBlock(kind="callout", text="Key point — " + "words " * 200))
    rows = [[f"Ville {i}", str(100000 + i * 1234), f"{(i % 7) - 3:.1f}"] for i in range(80)]
    blocks.append(SectionBlock(kind="table", caption="Cities", table=TableSheet(name="t", headers=["Ville", "Population", "Growth (%)"], rows=rows)))
    blocks.append(SectionBlock(kind="heading", level=2, text="中文测试"))
    blocks.append(SectionBlock(kind="paragraph", text="这是一个中文段落。"))
    content = SectionedContent(filename_stem="r", title="Rapport", subtitle="Comité", blocks=blocks)
    return render_document(DocumentType.PDF, content, RenderContext(language="fr", structure=structure))  # type: ignore[arg-type]


@pytest.mark.unit
class TestPdfCraft:
    def test_header_and_footer_on_every_page_and_metadata(self) -> None:
        document = fitz.open(stream=_long_pdf(), filetype="pdf")
        total = document.page_count
        assert total >= 4
        for number, page in enumerate(document, start=1):
            text = page.get_text()
            assert "Rapport" in text and f"Page {number} / {total}" in text
        assert document.metadata["title"] == "Rapport" and document.metadata["subject"] == "Comité"

    def test_toc_pages_are_exact_and_the_outline_is_set(self) -> None:
        document = fitz.open(stream=_long_pdf(), filetype="pdf")
        outline = document.get_toc()
        assert [entry[1] for entry in outline][:6] == [f"{i} Part {i}" for i in range(1, 7)]
        first_page_text = document[0].get_text()
        assert "Sommaire" in first_page_text
        for level, title, page in outline:
            assert title in document[page - 1].get_text(), (title, page)
        assert any(link["kind"] == fitz.LINK_GOTO for link in document[0].get_links())

    def test_plain_structure_has_no_toc_and_no_numbers(self) -> None:
        document = fitz.open(stream=_long_pdf(structure="plain"), filetype="pdf")
        assert "Sommaire" not in document[0].get_text()
        assert document.get_toc() == [] or all(not e[1][0].isdigit() for e in document.get_toc())
        assert "Part 1" in document[0].get_text() and "1 Part 1" not in document[0].get_text()

    def test_no_phantom_fill_on_continuation_pages(self) -> None:
        """Every non-white filled rectangle on a page after the first contains text (MuPDF quirk oracle)."""
        document = fitz.open(stream=_long_pdf(), filetype="pdf")
        for page in list(document)[1:]:
            for drawing in page.get_drawings():
                fill = drawing.get("fill")
                rect = drawing["rect"]
                if fill is None or min(fill) > 0.99 or rect.height < 4:
                    continue
                assert page.get_text("text", clip=rect).strip(), (page.number, rect, fill)

    def test_cjk_and_callout_render(self) -> None:
        text = "".join(page.get_text() for page in fitz.open(stream=_long_pdf(), filetype="pdf"))
        assert "中文测试" in text and "这是一个中文段落" in text and "Key point" in text
        assert "Tableau 1 — Cities" in text

    def test_page_size_follows_the_context(self) -> None:
        content = SectionedContent(filename_stem="x", title="T", blocks=[SectionBlock(kind="paragraph", text="p")])
        letter = fitz.open(stream=render_document(DocumentType.PDF, content, RenderContext(language="en", page_size="letter")), filetype="pdf")
        assert round(letter[0].rect.width) == 612
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Create `renderers/pdf_layout.py`**

```python
"""Two-pass Story layout, stamping, outline and links (ADR-274 §8.4).

PyMuPDF's Story paginates HTML but knows nothing of page numbers, running
heads or bookmarks. Elements carry ids; ``lay_out`` records the page each id
landed on, so the caller can write a table of contents with EXACT numbers
(re-laying out until the pages are stable) and then ``finish`` stamps every
page, sets the outline and links the entries.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import fitz  # type: ignore[import-untyped]  # PyMuPDF

from src.domains.document_generation import typography
from src.domains.document_generation.typography import PageSize


@dataclass(frozen=True, slots=True)
class Placed:
    """Where an identified element landed."""

    page: int
    rect: fitz.Rect


@dataclass(frozen=True, slots=True)
class LaidOut:
    """One layout pass."""

    pdf: bytes
    pages: int
    positions: dict[str, Placed] = field(default_factory=dict)


def content_rect(page_size: PageSize) -> fitz.Rect:
    """The area the Story lays text into (margins from typography)."""
    left, top, right, bottom = typography.PDF_MARGIN_PT
    return fitz.paper_rect(typography.page_rect_name(page_size)) + (left, top, -right, -bottom)


def lay_out(html: str, css: str, page_size: PageSize) -> LaidOut:
    """Paginate the HTML, recording the FIRST page and rect of every identified element."""
    story = fitz.Story(html=html, user_css=css)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    mediabox = fitz.paper_rect(typography.page_rect_name(page_size))
    where = content_rect(page_size)
    positions: dict[str, Placed] = {}
    page_no = 0
    more = True
    while more:
        page_no += 1
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        current = page_no

        def _record(position: Any) -> None:
            if position.id and position.id not in positions:
                positions[position.id] = Placed(current, fitz.Rect(position.rect))

        story.element_positions(_record)
        story.draw(device)
        writer.end_page()
    writer.close()
    return LaidOut(pdf=buffer.getvalue(), pages=page_no, positions=positions)


def finish(
    laid: LaidOut,
    *,
    header: str,
    footer_label: Callable[[int, int], str],
    outline: Sequence[tuple[int, str, int]],
    links: Sequence[tuple[str, int]],
    metadata: dict[str, str],
) -> bytes:
    """Stamp the running head and footer, set the outline, link the entries."""
    document = fitz.open(stream=laid.pdf, filetype="pdf")
    left, _top, _right, _bottom = typography.PDF_MARGIN_PT
    grey = tuple(int(typography.MUTED[i : i + 2], 16) / 255 for i in (0, 2, 4))
    for number, page in enumerate(document, start=1):
        page.insert_text((left, 40), header, fontsize=typography.PDF_STAMP_PT, color=grey, fontname="helv")
        label = footer_label(number, document.page_count)
        width = fitz.get_text_length(label, fontname="helv", fontsize=typography.PDF_STAMP_PT)
        page.insert_text(((page.rect.width - width) / 2, page.rect.height - 36), label, fontsize=typography.PDF_STAMP_PT, color=grey, fontname="helv")
    if outline:
        document.set_toc([[level, title, page] for level, title, page in outline])
    for element_id, target_page in links:
        placed = laid.positions.get(element_id)
        if placed is None:
            continue
        document[placed.page - 1].insert_link({"kind": fitz.LINK_GOTO, "from": placed.rect, "page": target_page - 1, "to": fitz.Point(0, 0)})
    document.set_metadata({"title": metadata.get("title", ""), "subject": metadata.get("subject", ""), "creationDate": metadata.get("creationDate", "")})
    return document.tobytes()
```

- [ ] **Step 4: Rewrite `renderers/pdf.py`**

```python
"""pdf: stylesheet, title block, exact table of contents, bookmarks, tables (ADR-226, ADR-274)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from html import escape

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.normalize import HeadingNumberer, document_is_numbered
from src.domains.document_generation.renderers import pdf_layout
from src.domains.document_generation.schemas import DocumentContent, SectionBlock, SectionedContent
from src.domains.document_generation.tables import infer_column_types

_TOC_LEVELS = 3
_MAX_PASSES = 3


def _inline_html(text: str) -> str:
    parts: list[str] = []
    for span in parse_inline(text):
        piece = escape(span.text)
        if span.code:
            piece = f"<code>{piece}</code>"
        if span.italic:
            piece = f"<i>{piece}</i>"
        if span.bold:
            piece = f"<b>{piece}</b>"
        parts.append(piece)
    return "".join(parts)


class _Html:
    """Builds the HTML of one document; called once per layout pass."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.numbered = document_is_numbered(content, context)
        self.headings: list[tuple[str, int, str]] = []  # (id, level, numbered text) in order
        numberer = HeadingNumberer()
        for index, block in enumerate(content.blocks):
            if block.kind == "heading":
                number = numberer.number(block.level) if self.numbered else ""
                self.headings.append((f"h-{index}", block.level, f"{number} {block.text}".strip()))

    def build(self, toc_pages: dict[str, int] | None, repeat_header_before: set[str]) -> str:
        parts = [f"<h1>{escape(self.content.title)}</h1>"]
        if self.content.subtitle:
            parts.append(f'<p class="subtitle">{escape(self.content.subtitle)}</p>')
        if self.context.date_line:
            parts.append(f'<p class="date">{escape(self.context.date_line)}</p>')
        if self.numbered:
            parts.append(f"<h2>{escape(self.context.label('documents.toc_heading'))}</h2>")
            for element_id, level, text in self.headings:
                if level > _TOC_LEVELS:
                    continue
                page = "" if toc_pages is None else f" — {toc_pages.get(element_id, '')}"
                css_class = "toc" if level == 1 else f"toc{level}"
                parts.append(f'<p class="{css_class}" id="toc-{element_id}">{escape(text)}{page}</p>')
        tables = 0
        heading_iter = iter(self.headings)
        for index, block in enumerate(self.content.blocks):
            if block.kind == "heading":
                element_id, level, text = next(heading_iter)
                tag = min(level + 1, 5)  # the title owns h1; headings shift one level down
                parts.append(f'<h{tag} id="{element_id}">{escape(text)}</h{tag}>')
            elif block.kind == "table" and block.table is not None:
                tables += 1
                parts.append(self._table(block, index, tables, repeat_header_before))
            else:
                parts.append(_SIMPLE[block.kind](block))
        return "".join(parts)

    def _table(self, block: SectionBlock, index: int, number: int, repeat_before: set[str]) -> str:
        sheet = block.table
        assert sheet is not None
        types = infer_column_types(sheet.headers, sheet.rows)
        classes = ['class="num"' if t.numeric else "" for t in types]
        header = "<tr>" + "".join(f"<th {c}>{escape(h)}</th>" for h, c in zip(sheet.headers, classes, strict=True)) + "</tr>"
        rows: list[str] = []
        for row_index, row in enumerate(sheet.rows):
            row_id = f"r-{index}-{row_index}"
            if row_id in repeat_before:
                rows.append(header)
            cells = "".join(f"<td {c}>{escape(v)}</td>" for v, c in zip(row, classes, strict=True))
            rows.append(f'<tr id="{row_id}">{cells}</tr>')
        label = self.context.label("documents.table_label", n=number)
        caption = f'<p class="caption">{escape(label)} — {escape(block.caption)}</p>' if block.caption else ""
        return f"{caption}<table>{header}{''.join(rows)}</table>"


_SIMPLE: dict[str, Callable[[SectionBlock], str]] = {
    "paragraph": lambda b: f"<p>{_inline_html(b.text)}</p>",
    "bullets": lambda b: "<ul>" + "".join(f"<li>{_inline_html(i)}</li>" for i in b.items) + "</ul>",
    "numbered": lambda b: "<ol>" + "".join(f"<li>{_inline_html(i)}</li>" for i in b.items) + "</ol>",
    "quote": lambda b: f"<blockquote>{_inline_html(b.text)}</blockquote>",
    "callout": lambda b: f'<div class="callout">{_inline_html(b.text)}</div>',
    "table": lambda b: "",  # tables carry ids and are built by _Html._table
}


def _first_rows_on_continuation_pages(laid: pdf_layout.LaidOut) -> set[str]:
    """For every table, the first row id of each page after the table's first page."""
    first_row_by_page: dict[tuple[str, int], tuple[int, str]] = {}
    table_first_page: dict[str, int] = {}
    for element_id, placed in laid.positions.items():
        if not element_id.startswith("r-"):
            continue
        table_id, row_index = element_id.rsplit("-", 1)
        table_first_page[table_id] = min(table_first_page.get(table_id, placed.page), placed.page)
        key = (table_id, placed.page)
        current = first_row_by_page.get(key)
        if current is None or int(row_index) < current[0]:
            first_row_by_page[key] = (int(row_index), element_id)
    return {
        row_id
        for (table_id, page), (_, row_id) in first_row_by_page.items()
        if page > table_first_page[table_id]
    }


def render_pdf(content: DocumentContent, context: RenderContext) -> bytes:
    if not isinstance(content, SectionedContent):
        raise ValueError("pdf rendering requires SectionedContent")
    html = _Html(content, context)
    css = typography.pdf_css(context.page_size)
    laid = pdf_layout.lay_out(html.build(None, set()), css, context.page_size)
    toc_pages: dict[str, int] = {}
    if html.numbered:
        # Pass 2..n: the TOC with numbers may shift pages; stop when stable.
        for _ in range(_MAX_PASSES):
            candidate = {eid: p.page for eid, p in laid.positions.items() if eid.startswith("h-")}
            laid = pdf_layout.lay_out(html.build(candidate, set()), css, context.page_size)
            pages_now = {eid: p.page for eid, p in laid.positions.items() if eid.startswith("h-")}
            if pages_now == candidate:
                toc_pages = candidate
                break
        else:
            laid = pdf_layout.lay_out(html.build({}, set()), css, context.page_size)  # honest: no numbers
    toc_arg = toc_pages if html.numbered else None
    repeat = _first_rows_on_continuation_pages(laid)
    if repeat:
        # Best effort: repeated header rows shift rows; accept only a stable set.
        for _ in range(2):
            candidate_laid = pdf_layout.lay_out(html.build(toc_arg, repeat), css, context.page_size)
            again = _first_rows_on_continuation_pages(candidate_laid)
            if again == repeat and (not html.numbered or {e: p.page for e, p in candidate_laid.positions.items() if e.startswith("h-")} == toc_pages):
                laid = candidate_laid
                break
            repeat = again
    outline = [
        (level, text, laid.positions[eid].page)
        for eid, level, text in html.headings
        if eid in laid.positions
    ]
    links = [(f"toc-{eid}", laid.positions[eid].page) for eid, _, _ in html.headings if eid in laid.positions]
    created = (
        context.generated_at.astimezone(UTC).strftime("D:%Y%m%d%H%M%SZ") if context.generated_at else ""
    )
    return pdf_layout.finish(
        laid,
        header=content.title,
        footer_label=lambda page, total: context.label("documents.page_of", page=page, total=total),
        outline=outline,
        links=links if html.numbered else [],
        metadata={"title": content.title, "subject": content.subtitle, "creationDate": created},
    )
```

When the TOC passes did not converge, `toc_pages` stays `{}` and a numbered document is rebuilt with `{}`: the entries show no page number — the honest fallback.

- [ ] **Step 5: Run** → PASS (the phantom oracle is the falsifier: if a `td` band ever ghosts, the fix is to drop the `tr:nth-child(even)` rule in `typography.pdf_css`, and the test stays). Run the meetings tests → PASS. **Gate:** `task lint:backend`; if `render_pdf` reaches complexity 15, extract the two convergence loops into `_stable_toc(html, css, page_size)` and `_stable_headers(...)` in `pdf_layout.py`.

---

### Task 16: Wiring — the service builds the context, the tool passes the timezone, the minutes stay plain

**Files:**
- Modify: `apps/api/src/domains/document_generation/service.py` (`generate_document_for_user` signature + render call)
- Modify: `apps/api/src/domains/agents/tools/document_generation_tools.py` (pass `timezone=user.timezone`)
- Modify: `apps/api/src/domains/meetings/delivery.py:48-52`
- Test: `apps/api/tests/unit/domains/document_generation/test_service.py`, `apps/api/tests/unit/domains/agents/tools/test_document_generation_tools.py`, `apps/api/tests/unit/domains/meetings/test_delivery.py`

**Interfaces:**
- Produces: `generate_document_for_user(..., language: str, timezone: str, config)`; `render_pdf(meeting, report, *, language, gaps)` unchanged signature, now passing `RenderContext(language=normalize_language(language), structure="plain")`.

- [ ] **Step 1: Write the failing tests**

`test_service.py` — extend `test_generate_csv_end_to_end`'s call with `timezone="Europe/Berlin"` (every call site in the file gains it) and add:

```python
@pytest.mark.unit
async def test_the_renderer_receives_the_readers_context(tmp_path, monkeypatch, tabular_result) -> None:
    from src.core.config import settings as app_settings
    from src.domains.document_generation import service as svc

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    seen: dict = {}

    def _fake_render(doc_type, content, context):
        seen["context"] = context
        return b"x"

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
        patch.object(svc, "render_document", _fake_render),
    ):
        await svc.generate_document_for_user(
            user_id=uuid.uuid4(), conversation_id="c", doc_type=DocumentType.CSV, instructions="i",
            source_data="", requested_filename="", language="zh", timezone="Asia/Tokyo", config=None,
        )
    context = seen["context"]
    assert context.language == "zh-CN" and context.timezone == "Asia/Tokyo"
    assert context.generated_at is not None and context.generated_at.tzinfo is not None
    assert context.structure == "auto"
```

`test_document_generation_tools.py` — in `test_service_receives_user_language_and_context`, set `user.timezone = "America/Montreal"` on the fake user and assert `kwargs["timezone"] == "America/Montreal"`.

`test_delivery.py` (meetings) — add:

```python
def test_render_pdf_keeps_the_minutes_plain_and_undated() -> None:
    import fitz

    from src.domains.meetings import delivery

    seen = {}

    def _spy(doc_type, content, context=None):
        seen["context"] = context
        return b"%PDF-1.4"

    with patch.object(delivery, "render_document", _spy):
        delivery.render_pdf(_meeting(), _report(), language="fr")
    assert seen["context"].structure == "plain" and seen["context"].generated_at is None
    assert seen["context"].language == "fr"
```

(`_meeting()` / `_report()` are the file's existing builders; `patch` from `unittest.mock`.)

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

`service.py`: add `timezone: str` after `language` in `generate_document_for_user` (docstring: "The person's IANA timezone: the date on the title block."); build the context and pass it:

```python
    context = build_render_context(
        language=language, timezone=timezone, generated_at=datetime.now(UTC)
    )
    data = await asyncio.to_thread(render_document, doc_type, content, context)
```

with `from src.domains.document_generation.context import build_render_context`.

Tool: `timezone=user.timezone,` next to `language=normalize_language(user.language),`.

`meetings/delivery.py`:

```python
from src.core.i18n import normalize_language
from src.domains.document_generation.context import RenderContext
...
    # The minutes shape themselves (their header carries the dates): no table
    # of contents, no numbering, no generation date — header, footer and table
    # craft only (ADR-274, owner decision 2026-09-08).
    return render_document(
        DocumentType.PDF, content, RenderContext(language=normalize_language(language), structure="plain")
    )
```

- [ ] **Step 4: Run** the three files and the whole `tests/unit/domains/document_generation`, `tests/unit/domains/meetings`, `tests/unit/domains/agents/tools/test_document_generation_tools.py` → PASS. **Gate:** `task lint:backend`.

---

### Task 17: Corpus, parametrized test, harness

**Files:**
- Create: `apps/api/tests/fixtures/document_corpus/*.json` (12 files, below)
- Create: `apps/api/tests/unit/domains/document_generation/test_corpus.py`
- Create: `apps/api/scripts/document_generation/__init__.py` (empty), `render_corpus.py`, `measure_office.ps1`
- Modify: `Taskfile.yml` (after `recurrence:corpus:measure`), `.gitignore` (after `apps/api/data/tool_cache/`)

**Interfaces:**
- Fixture shape: `{"doc_types": ["docx", "pdf", "md", "txt"], "content": {...SectionedContent...}}` or `{"doc_types": ["pptx"], "content": {...SlideContent...}}` or `{"doc_types": ["xlsx", "csv"], "content": {...TabularContent...}}`; `language` optional (default `en`).
- Produces: `task documents:corpus:render` (writes `apps/api/data/document_corpus_out/<fixture>.<ext>`), `task documents:corpus:measure` (Windows only).

- [ ] **Step 1: Write the corpus** — twelve deterministic fixtures, each a JSON object; names and what each one exercises:

| File | Content |
|---|---|
| `memo_short.json` | sectioned, 2 headings, 3 paragraphs, one bullets — short: no TOC, no numbering |
| `report_long.json` | sectioned, 8 H1 + 10 H2 (headings pre-numbered by the model "1. …"), paragraphs with `**bold**` and a `[link](https://example.org)`, numbered, quote, callout, 3 tables (one 40 rows) with captions, subtitle |
| `table_wide.json` | sectioned, one table with 12 columns × 25 rows, long header names |
| `deck_kinds.json` | slides: cover subtitle, section, content (4 bullets), comparison (2 columns), table (8 rows), a content slide carrying both bullets and a table, notes everywhere |
| `deck_dense.json` | 25 content slides, 9 bullets of 140 chars each, one 2 000-char bullet, a 70-char title |
| `deck_columns.json` | comparison with 1 column, with 3 columns, a section with bullets, a `table` kind without a table |
| `zh_document.json` | `language: "zh"`, sectioned, 6 headings, CJK text everywhere, a table |
| `edge_cases.json` | sectioned: heading level 0 and 9, empty bullets, empty table, a paragraph that is a markdown list, a paragraph that is a `### heading`, a `bullets` block with text and no items |
| `sheet_typed.json` | tabular, 2 sheets: dates, ints, decimals, `%`, postal codes with a leading zero, negatives, `=1+1`, a duplicate header, a ragged row, a sheet name with `[]/` |
| `sheet_empty.json` | tabular, one sheet with headers only, one with nothing |
| `titles_long.json` | slides: 5 slides whose titles are 90-120 characters |
| `minutes_shaped.json` | sectioned in the exact block shapes `meetings/render.py` emits (paragraph header, bullets of "label : value", H2 sections, H3 topics, transcript lines), `structure: "plain"` |

Every fixture validates against its schema; the values are fixed text (no randomness).

- [ ] **Step 2: Write the parametrized test**

```python
"""Every corpus document renders in every applicable format and passes the structural oracles."""

import io
import json
from pathlib import Path

import docx
import fitz
import openpyxl
import pptx
import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import SCHEMA_BY_DOC_TYPE, DocumentType

pytestmark = [pytest.mark.unit]
CORPUS = sorted((Path(__file__).parents[4] / "fixtures" / "document_corpus").glob("*.json"))


def _load(path: Path) -> tuple[list[DocumentType], object, RenderContext]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc_types = [DocumentType(t) for t in raw["doc_types"]]
    content = SCHEMA_BY_DOC_TYPE[doc_types[0]].model_validate(raw["content"])
    context = RenderContext(language=raw.get("language", "en"), structure=raw.get("structure", "auto"))
    return doc_types, content, context


_OPENERS = {
    DocumentType.DOCX: lambda data: docx.Document(io.BytesIO(data)),
    DocumentType.PPTX: lambda data: pptx.Presentation(io.BytesIO(data)),
    DocumentType.XLSX: lambda data: openpyxl.load_workbook(io.BytesIO(data)),
    DocumentType.PDF: lambda data: fitz.open(stream=data, filetype="pdf"),
    DocumentType.CSV: lambda data: data.decode("utf-8-sig"),
    DocumentType.MD: lambda data: data.decode("utf-8"),
    DocumentType.TXT: lambda data: data.decode("utf-8"),
}


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_every_corpus_document_renders_and_reopens(path: Path) -> None:
    doc_types, content, context = _load(path)
    for doc_type in doc_types:
        data = render_document(doc_type, content, context)
        assert data, (path.stem, doc_type)
        _OPENERS[doc_type](data)  # the format's own reader accepts the bytes


def test_the_corpus_covers_every_format_and_both_structures() -> None:
    seen: set[DocumentType] = set()
    structures: set[str] = set()
    for path in CORPUS:
        raw = json.loads(path.read_text(encoding="utf-8"))
        seen.update(DocumentType(t) for t in raw["doc_types"])
        structures.add(raw.get("structure", "auto"))
    assert seen == set(DocumentType) and structures == {"auto", "plain"}
```

Reuse `_assert_nothing_overflows` from `test_renderer_pptx.py` (move it to a shared `tests/unit/domains/document_generation/pptx_oracles.py` helper module) and call it for every pptx corpus deck inside `test_every_corpus_document_renders_and_reopens`.

- [ ] **Step 3: Run** → FAIL until the fixtures exist and validate; then PASS. Fix every renderer defect the corpus reveals (this is the point of the corpus).

- [ ] **Step 4: The harness** — `apps/api/scripts/document_generation/render_corpus.py`:

```python
"""Render the document corpus to disk, every fixture in every applicable format.

Usage (from apps/api): .venv/Scripts/python scripts/document_generation/render_corpus.py [--out DIR]
A rendering step, never a gate: the files are for eyes and for the Office
measurement (``measure_office.ps1``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.domains.document_generation.context import RenderContext  # noqa: E402
from src.domains.document_generation.renderers import DOCUMENT_EXTENSIONS, render_document  # noqa: E402
from src.domains.document_generation.schemas import SCHEMA_BY_DOC_TYPE, DocumentType  # noqa: E402

CORPUS = REPO_ROOT / "tests" / "fixtures" / "document_corpus"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "document_corpus_out"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(CORPUS.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        doc_types = [DocumentType(t) for t in raw["doc_types"]]
        content = SCHEMA_BY_DOC_TYPE[doc_types[0]].model_validate(raw["content"])
        context = RenderContext(language=raw.get("language", "en"), structure=raw.get("structure", "auto"))
        for doc_type in doc_types:
            target = out / f"{path.stem}.{DOCUMENT_EXTENSIONS[doc_type]}"
            target.write_bytes(render_document(doc_type, content, context))
            written += 1
    print(f"rendered {written} files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`measure_office.ps1` (Windows, Office 16 through COM): for every `.pptx` in the output directory, open it read-only, for every shape with text compare `TextRange.BoundHeight` with `Shape.Height` and count overflows, export a PDF; for every `.docx`, open, report `TablesOfContents.Count`, the first three heading `ListString`s, the footer text as opened, export a PDF; for every `.xlsx`, open (a failure is a refusal), report `ListObjects.Count` and `FreezePanes`. Print one line per file and a final `OVERFLOWS=<n>` line; exit 1 when `n > 0` or any workbook refused. (The COM sequences are the ones used for the design probes; `$app.Presentations.Open($path, $true, $false, $false)`, `$pres.SaveAs($pdf, 32)`, `$word.Documents.Open($path, $false, $true)`, `$doc.ExportAsFixedFormat($pdf, 17)`, `$excel.Workbooks.Open($path)` with `DisplayAlerts = $false`.)

Taskfile (after `recurrence:corpus:measure`):

```yaml
  documents:corpus:render:
    desc: Render the document corpus in every format (a rendering step, never a gate)
    dir: "{{.API_DIR}}"
    cmds:
      - cmd: .venv/Scripts/python scripts/document_generation/render_corpus.py {{.CLI_ARGS}}
        platforms: [windows]
      - cmd: .venv/bin/python scripts/document_generation/render_corpus.py {{.CLI_ARGS}}
        platforms: [linux, darwin]

  documents:corpus:measure:
    desc: Measure the rendered corpus with Word, PowerPoint and Excel through COM (Windows, on demand, never a gate)
    dir: "{{.API_DIR}}"
    deps: [documents:corpus:render]
    cmds:
      - cmd: pwsh -NoProfile -File scripts/document_generation/measure_office.ps1 -Dir data/document_corpus_out
        platforms: [windows]
```

`.gitignore`: `apps/api/data/document_corpus_out/` with a one-line comment ("rendered document corpus — regenerated by task documents:corpus:render").

- [ ] **Step 5: Run** `task documents:corpus:render` then `task documents:corpus:measure` → read the report: `OVERFLOWS=0`, every workbook opened, TOC present on `report_long.docx` and absent on `memo_short.docx`, numbering `[1]`, `[1.1]`. Open the exported PDFs' first pages (rasterize with PyMuPDF and look). Decide the two deferred styles (`DOCX_TABLE_STYLE`, `XLSX_TABLE_STYLE`) on what is seen and record the choice in `typography.py`. **Gate:** `task lint:ci-parity` (the new tasks are task calls, no inline `run:`) and `task lint:backend`.

---

# Lot 3 — Publication

### Task 18: The prompt publishes the vocabulary and the budgets

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/document_generation_prompt.txt`
- Modify: `apps/api/src/domains/document_generation/service.py` (`_call_document_llm` placeholder values)
- Modify: `apps/api/tests/unit/domains/agents/prompts/test_prompt_cache_hygiene.py` (`MARKER_REQUIRED` gains `"document_generation_prompt"`)
- Create: `apps/api/tests/unit/domains/agents/prompts/test_document_generation_prompt.py`
- Test: `apps/api/tests/unit/domains/document_generation/test_service.py` (extend)

**Interfaces:**
- Produces: `prompt_values(*, language, instructions, source_data) -> dict[str, str | int]` in `service.py` — every placeholder the prompt uses: `language`, `instructions`, `source_data`, `max_bullets_per_slide`, `max_bullet_chars`, `toc_min_headings`, `length_budget_words`.

- [ ] **Step 1: Write the failing tests**

`test_document_generation_prompt.py`:

```python
"""What the renderer enforces, the prompt publishes (ADR-184, ADR-274)."""

import re
from pathlib import Path
from typing import get_args

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.document_generation.schemas import SectionBlock, Slide
from src.domains.document_generation.service import prompt_values

pytestmark = [pytest.mark.unit]
PROMPT = Path(__file__).parents[5] / "src/domains/agents/prompts/v1/document_generation_prompt.txt"
_PLACEHOLDER = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def _text() -> str:
    return PROMPT.read_text(encoding="utf-8")


def test_every_placeholder_is_supplied_and_nothing_is_hard_coded() -> None:
    values = prompt_values(language="fr", instructions="x", source_data="")
    placeholders = set(_PLACEHOLDER.findall(_text()))
    assert placeholders == set(values)
    rendered = _text().format(**values)
    assert not _PLACEHOLDER.search(rendered)
    static = _text().split(DYNAMIC_CONTEXT_MARKER)[0]
    # No number stands for a budget in the static prose: they travel as placeholders.
    assert not re.search(r"\b(?:110|16000|8800)\b", static)


def test_the_vocabulary_is_published_in_full() -> None:
    text = _text()
    for kind in get_args(SectionBlock.model_fields["kind"].annotation):
        assert f"`{kind}`" in text, kind
    for kind in get_args(Slide.model_fields["kind"].annotation):
        assert f"`{kind}`" in text, kind
    for field in ("caption", "subtitle", "columns", "notes"):
        assert f"`{field}`" in text, field


def test_the_dynamic_tail_is_marked_and_the_language_sits_in_it() -> None:
    text = _text()
    assert DYNAMIC_CONTEXT_MARKER in text
    static, dynamic = text.split(DYNAMIC_CONTEXT_MARKER, 1)
    assert "{language}" in dynamic and "{language}" not in static
    assert "{instructions}" in dynamic and "{source_data}" in dynamic


def test_the_writer_is_told_not_to_number_or_write_a_toc() -> None:
    text = _text().lower()
    assert "table of contents" in text and "do not number" in text
```

`test_service.py` — add:

```python
@pytest.mark.unit
def test_prompt_values_read_settings_and_the_slot_budget(monkeypatch) -> None:
    from src.core.config import settings as app_settings
    from src.core.constants import DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN
    from src.domains.document_generation import service as svc

    monkeypatch.setattr(app_settings, "document_generation_slide_max_bullets", 7)
    monkeypatch.setattr(app_settings, "document_generation_slide_max_bullet_chars", 99)
    monkeypatch.setattr(app_settings, "document_generation_toc_min_headings", 4)
    with patch.object(svc, "get_llm_config_for_agent", lambda *_: MagicMock(max_tokens=10000)):
        values = svc.prompt_values(language="de", instructions="i", source_data="s")
    assert values["max_bullets_per_slide"] == 7 and values["max_bullet_chars"] == 99
    assert values["toc_min_headings"] == 4
    assert values["length_budget_words"] == int(10000 * DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN)
    assert values["language"] == "German" and values["instructions"] == "i" and values["source_data"] == "s"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Rewrite the prompt** (whole file):

```
You are a senior professional document writer. Produce the COMPLETE, final content of exactly one document, matching the requested format family. The reader will judge this document on its own: it must stand without the conversation that produced it.

QUALITY BAR (substance)
- Deliver finished work: no placeholders, no "TBD", no meta-comments about the document, no apologies, no offers to expand later.
- Be accurate and specific: prefer concrete facts, figures, dates and named entities over vague generalities. Never invent precise-looking data (statistics, prices, dates) that you do not actually know; when a figure is uncertain, qualify it honestly (an approximation or a range) or omit it.
- Ground the content in the SOURCE DATA when provided: it is the primary evidence. Do not contradict it, do not silently drop material facts from it, and do not pad it with invented details. If it appears truncated, work with what is present without mentioning the truncation inside the document.
- Cover the subject with the depth the request calls for: a "detailed" request deserves substantial, well-developed content; a quick export stays lean. Depth means more relevant substance, never filler or repetition.
- Adapt tone and register to the stated audience and purpose; default to clear, neutral, professional prose. Use terminology consistently throughout.

QUALITY BAR (form)
- Choose a short, descriptive filename_stem in the document's language (no extension, no path, no special characters; words separated by hyphens).
- Give the document a precise, informative title — a name, not a summary sentence — and, when the audience or purpose is known, a one-line `subtitle`.
- Order content logically: general before specific, context before detail, findings before recommendations. Each unit (row, section, slide) carries one clear idea and no duplicate of another unit.
- Write self-explanatory labels: column headers, section headings and slide titles must be understandable out of context.
- Inside any text, the only markup allowed is `**bold**` and `*italic*`. No other markdown: no headings inside a paragraph, no lists inside a paragraph, no links — say the source in words.

LENGTH BUDGET
- The whole answer must stay under {length_budget_words} words in total. Beyond that the output is cut and the document FAILS; a shorter, complete document beats a longer, cut one.

TABULAR OUTPUT (spreadsheets and CSV)
- Design the columns first: each column holds ONE atomic attribute with a consistent type and unit across all rows; name units in the header (e.g. "Price (EUR)"), never mixed into cell values inconsistently. Headers are unique and non-empty.
- Every cell is a plain string; no formulas. Write values so the spreadsheet can type the column: plain digits with a dot as decimal separator (1234.5, never 1,234.5 or 1 234,5), ISO 8601 dates (2026-09-08), percentages as a number followed by % (12.5%), empty cells as empty strings (not "N/A" variants). A column whose every cell obeys one of these forms becomes a typed column; one stray value keeps it text.
- Rows are homogeneous records of the same entity, sorted in an order that serves the reader (chronological, alphabetical or by importance — pick one and keep it).
- Split genuinely distinct record types into separate sheets with meaningful names rather than mixing them in one table.

SECTIONED OUTPUT (reports, articles, notes)
- Open with a short introduction that states the subject and what the document covers; close substantial documents with a conclusion or summary of key takeaways.
- Build a logical hierarchy of headings (`heading` blocks, level 1 for parts, 2 and 3 below); every heading announces exactly what its section contains. Balance section depth: avoid a lone subsection under a heading. Do not number your headings and do not write a table of contents: from {toc_min_headings} headings the renderer numbers the headings and adds a table of contents itself.
- Use the right block for the content: flowing analysis in `paragraph` blocks; enumerable parallel facts in `bullets` (each item grammatically parallel, no orphan half-sentences); an ordered sequence of steps in `numbered`; someone's exact words in `quote`; a warning or the one thing to remember in `callout`; comparable structured data in `table`, with a `caption` naming what the table shows. Do not force everything into bullets.
- Keep paragraphs focused (one idea each) and transitions explicit so the document reads as a whole, not as fragments.

SLIDES OUTPUT (presentations)
- Build a narrative arc: an opening slide framing the subject, a body where each slide advances ONE idea announced by its title, and a closing slide with the takeaways or next steps. A deck with three or more parts opens each part with a `section` slide (title plus a `subtitle` tagline).
- Choose what each slide IS: `content` for an idea supported by bullets; `comparison` for two options side by side (`columns`: exactly two, each with a heading and its bullets); `table` for numeric data (a `table`); `section` to open a part. The renderer chooses the layout.
- Slide titles are assertions or precise topics, not generic labels ("Costs rise with volume", not "Costs").
- Bullets are short, parallel and scannable — key words and figures, not full paragraphs; the slide must be readable at a glance. At most {max_bullets_per_slide} bullets per slide and {max_bullet_chars} characters per bullet: beyond that the renderer splits the slide in two, which breaks the one-idea rule.
- Put the full sentences in the speaker `notes`: context, evidence and what to actually say, so the deck works both projected and presented.

--- DYNAMIC CONTEXT
Write the entire document in {language}.

USER REQUEST:
{instructions}

SOURCE DATA (may be empty or truncated):
{source_data}
```

- [ ] **Step 4: `service.py`** — add `prompt_values` and use it in `_call_document_llm`:

```python
def prompt_values(*, language: str, instructions: str, source_data: str) -> dict[str, str | int]:
    """Every placeholder of the document prompt, budgets read from settings and the slot.

    What the renderer enforces is published here (ADR-184): the slide density
    budgets, the long-document threshold and the length budget derived from
    the slot's effective ``max_tokens``.

    Args:
        language: Backend-canonical language code.
        instructions: What the document must contain.
        source_data: Raw material (already truncated by the caller).

    Returns:
        The ``str.format`` mapping of the prompt file.
    """
    slot = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE)
    return {
        "language": get_language_name(language),
        "instructions": instructions,
        "source_data": source_data,
        "max_bullets_per_slide": settings.document_generation_slide_max_bullets,
        "max_bullet_chars": settings.document_generation_slide_max_bullet_chars,
        "toc_min_headings": settings.document_generation_toc_min_headings,
        "length_budget_words": int(slot.max_tokens * DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN),
    }
```

and in `_call_document_llm`: `system = load_document_prompt("document_generation_prompt", "v1").format(**prompt_values(language=language, instructions=instructions, source_data=source_data))`. Import `DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN`.

- [ ] **Step 5: `test_prompt_cache_hygiene.py`** — add `"document_generation_prompt",` under a new comment `# Documents (ADR-274): static rules first, the request in the tail` in `MARKER_REQUIRED`.

- [ ] **Step 6: Run** the prompt tests, the cache hygiene test, the service tests → PASS. Measure the new prompt with tiktoken (`o200k_base`) and note the count for the ADR (expected ≈ 1 200 tokens against 855). **Gate:** `task lint:backend`.

---

### Task 19: ADR-274, technical doc, indexes, pointers

**Files:**
- Create: `docs/architecture/ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md`
- Modify: `docs/architecture/ADR_INDEX.md` (entry after ADR-273), `docs/INDEX.md` (the DOCUMENT_GENERATION.md row's description), `docs/technical/DOCUMENT_GENERATION.md` (rewrite), `CLAUDE.md` (a pointer bullet in "Useful Documentation Pointers" for ADR-274 and one for ADR-275; the ADR counts line is regenerated), `AGENTS.md` (generated), `apps/api/src/domains/agents/document_generation/catalogue_manifests.py` (`CostProfile`: `est_tokens_in=2500`, `est_tokens_out=9000` — the measured deltas)

- [ ] **Step 1: ADR-274** (English; header as ADR-273; sections Context / Decision / Consequences / Rejected):

Context: the owner's observation, the two ceilings (§1 of the design), the measured table (§2-3: 4:3 template, 2 of 11 layouts, 4 of 164 styles, no CSS, +1 087 pt overflow, `fit_text` wrong by ×2, TOC empty on open, Excel refusing duplicate headers, MuPDF phantom rectangle, fonts bundled).

Decision: the ten decisions of design §5, each in one paragraph, plus the estimator's constants and calibration (§9), the effective-kind table (§6.1), the repairs table (§13), the harness (§16.3), the stated limits (Word TOC without page numbers, PDF header repetition best effort, estimator calibration on Calibri, no thousands separators), the deferred choices as made (the two table styles, the PDF banding verdict from the phantom oracle), the prompt token count before/after.

Consequences: meeting minutes keep their shape and gain header/footer/tables; cost per document (+≈ 350 input tokens, +≈ 10 % output); one LLM call per document unchanged; no new spend site; behaviour on a truncated output is now ADR-275's.

Rejected: vendored `.dotx`/`.potx` templates (an identity, opaque to review, drifts); a layout catalogue chosen by the model (the model says what a thing is; the renderer draws it); `python-pptx.fit_text` (measured wrong); `updateFields` on open (a Word dialog on every open); a reportlab/weasyprint dependency for the PDF (ADR-226 already rejected a new dependency; the Story engine plus a two-pass layout gives exact numbers).

- [ ] **Step 2: `DOCUMENT_GENERATION.md`** — rewrite: Overview (unchanged intent + "craft" paragraph), Architecture (data flow now: prompt with published budgets → structured call with `user_id` → truncation refusal → normalization → renderer with context → attachment), the vocabulary and its repairs, per-format craft (one subsection each), the estimator, settings table (+ the four rows), the corpus and the harness (`task documents:corpus:render` / `:measure`), stated limits, "Why not…" (the rejected alternatives). Keep every existing environment-variable row and the two switches.

- [ ] **Step 3: Indexes and pointers** — `ADR_INDEX.md` entry (French, ADR-273 format); `docs/INDEX.md` row 139 description: `AI Document Generation (ADR-226, ADR-274) — dedicated LLM slot, crafted renderers (csv/xlsx/docx/pptx/pdf/md/txt), TTL attachment cards`; CLAUDE.md pointers:

```
- Document craft: the renderer owns the form, the model owns the meaning (ADR-274, amending ADR-226): `docs/architecture/ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md` — a small SEMANTIC vocabulary (`numbered`, `quote`, `callout`, a table `caption`, a slide `kind` — section / comparison / table), never a layout; every incoherence REPAIRED at normalization (levels clamped, empties dropped, leaked markdown converted, model-written heading numbers stripped, ragged rows widened, headers made unique — Excel REFUSES a Table with a duplicate header, measured); 16:9 landscape by scaling the default template's OWNED transforms; text measured by an estimator CALIBRATED on 54 PowerPoint measurements (0.42 em, ×1.2 + ×0.2, ×1.05 → 0 under-predictions), shrunk to 14 pt then SPLIT, never clipped; ONE predicate (`document_is_numbered`) switches TOC, heading numbering and part breaks together, and meeting minutes pin `structure="plain"`; Word's TOC is pre-rendered without page numbers (F9 regenerates it), the PDF's carries EXACT numbers from a two-pass layout; no `th` background with `border-collapse` in the PDF (MuPDF phantom rectangle) and a test that every fill on a continuation page contains text; what the renderer enforces the prompt publishes as placeholders read from settings.
- A truncated structured output is a refusal, never a rescue (ADR-275, amending ADR-220, ADR-226, ADR-272): `docs/architecture/ADR-275-Truncated-Structured-Output-Is-A-Refusal.md` — `json_recovery` closes an open structure and the shortened object VALIDATES (12 of 100 report cuts, 14 of 100 deck cuts became shorter valid documents announced complete); `is_output_truncated` reads the provider's own verdict (five shapes) BEFORE any rescue, raises `StructuredOutputTruncatedError`, and the retry wrapper never retries it; the document service now passes `user_id` to the structured door — `resolve_owner` reads `config.metadata.user_id`, which LangGraph never sets (only `thread_id` is merged), so a "bounded caller" accepted by name carried no owner.
```

Then `task release:sync-counts` (ADR counts in CLAUDE.md, docs/INDEX.md, README) and `task docs:sync-agents` (AGENTS.md). `CostProfile` edit with a comment naming the measurement.

- [ ] **Step 4: Gate** `task lint:docs:preview` → 0 findings (the new ADRs are indexed, the technical doc's code paths exist, no orphan); `task lint:docs` may still report the un-staged files — that is the preview's job, not a defect.

---

### Task 20: Review — gates, measurement, evidence

- [ ] **Step 1:** `task lint` → every linter, ratchet, hygiene, lockfile, CI-parity, i18n and docs gate green (docs via the preview when untracked files are involved).
- [ ] **Step 2:** `task test:backend:unit:fast` → green, note the counts. `task test:backend:unit:coverage` → note the measured coverage; if it exceeds the floor by ≥ 2 pts more than before, raise the floor accordingly (shrink-only ratchet).
- [ ] **Step 3:** `cd apps/api && .venv/Scripts/pytest tests/agents -q -x` (the suite outside the hook — memory: it has bitten four times).
- [ ] **Step 4:** `task documents:corpus:render && task documents:corpus:measure` → `OVERFLOWS=0`, every workbook opened, TOC/numbering/fields as expected; rasterize `report_long.pdf`, `deck_kinds.pdf`, `deck_dense.pdf` first pages and LOOK; paste the report lines into ADR-274's "Measured" paragraph.
- [ ] **Step 5:** `task ci:fast` → green.
- [ ] **Step 6:** Update the memory index: one project file for this programme (what shipped, the deferred choices as decided, the measurements, the traps met), and reference files for any new trap found while implementing; keep MEMORY.md entries to one line.
- [ ] **Step 7:** Report to the owner: exact commands, exit codes, test counts, the measurement lines, the deferred choices as decided, what was left out (nothing expected) — no git action.

---

## Plan self-review (done while writing)

- **Spec coverage:** §5.1-5.10 → Tasks 4, 8, 9, 13-15 (craft), 16 (minutes plain), 1-2 (truncation, owner); §6 → Task 4; §6.1 → Task 8; §7 → Tasks 5, 10, 11; §7.1 → Task 5; §7.2 → Task 5; §8.1 → Task 13; §8.2 → Task 14; §8.3 → Tasks 7, 12; §8.4 → Task 15; §8.5 → Task 11; §9 → Task 9; §10 → Task 1; §11 → Task 2; §12 → Task 18; §13 → Tasks 7, 8, 9, 14, 15; §14 → Tasks 16, 19; §16 → every task's tests + Task 17; §17 → Tasks 3, 19; §18 → the lot order (with the vocabulary moved first, stated in Global Constraints).
- **Placeholders:** none — every step carries its code; the two style choices are explicit measurement steps with a named fallback.
- **Type consistency:** `render_document(doc_type, content, context=None)` (Task 11) is what Tasks 12-17 call; `RenderContext` fields (Task 5) are read by every renderer; `document_is_numbered(content, context)` (Task 8) is used by Tasks 11, 13, 15; `plan_body/fit_title/fits/TextFrame/BULLET_INDENT_PT/BODY_SIZE_FLOOR_PT/TABLE_ROW_HEIGHT_PT/rows_per_slide/table_font_size` (Task 9) are what Task 14 imports; `infer_column_types/typed_value/excel_table_name/chunk_rows` (Task 7) are what Tasks 12-15 import; `StructuredOutputTruncatedError` (Task 1) is what Task 2 catches; `prompt_values` (Task 18) is what its tests import; `generate_document_for_user(..., timezone, ...)` (Task 16) is what the tool passes.

---

## Test plan, as executed (enriched during implementation)

The plan's §16 was written before the code; this is what the suites actually
assert, plus what implementation added. Run this list at review.

### Automated (every run, `task test:backend:unit:fast`)

| Area | File | What it pins |
|---|---|---|
| Truncation | `infrastructure/llm/test_output_truncation.py` (27) | five provider shapes and their negatives; refusal at the THREE doors; **a complete answer is kept despite the verdict**; no retry; the JSON-mode rescue still works when the provider says it finished |
| Meetings | `domains/meetings/test_processing_flow.py` | a truncated synthesis is PERMANENT (`synthesis_too_long`, `transient=False`) |
| Validator | `agents/orchestration/test_validation_prompt_contract.py` | a truncation is not replayed and falls open at once |
| Vocabulary | `document_generation/test_schemas.py` | defaults; **no bound in the model-facing schema**; the strict-mode verdict PINNED per family with its depth; one-line docstrings |
| Labels | `core/test_i18n_documents.py` | six languages, identical keys AND placeholders; the unknown locale follows `normalize_language` |
| Context | `document_generation/test_context.py` | language normalised, date read in the READER's timezone, `plain` pinned, immutable |
| Repairs | `test_normalize.py` (20) | the effective-kind table; leaked markdown; a paragraph that merely mentions a dash is left alone; heading numbers stripped only when numbered; idempotence; ADR-085 dispatch completeness |
| Emphasis | `test_inline.py` (16) | bold/italic/code/links; `__bold__`; orphan and intra-word markers literal; CJK |
| Tables | `test_tables.py` (23) | unanimity typing; leading zero protects a code; Excel-illegal names; ragged rows widened |
| Estimator | `test_fit.py` (74) | **the 54 PowerPoint measurements**: lines exact, height never under-predicted; the constant inside its zero-error interval; splits keep every word |
| Typography | `test_typography.py` | the CSS comes from the constants; every colour is grey; slides are landscape |
| DOCX | `test_renderer_docx.py` (13) | named styles; TOC field with entries == headings; numbering bound to Heading 1-3; `startOverride` per list (in `numbering.xml`); `tblHeader`; page size |
| PPTX | `test_renderer_pptx.py` (15) | 960 × 540 landscape; a layout per kind; slide numbers; **nothing overflows** (the shared oracle); no gratuitous split; chunked tables |
| XLSX | `test_renderer_xlsx.py` (14) | typed cells and formats; Table + filter + freeze; duplicate headers made unique; no Table on an empty sheet |
| PDF | `test_renderer_pdf.py` (20) | header/footer on every page; contents numbers == where the headings really are; links and bookmarks; **no phantom fill** (tolerance = one line box, falsified 0 vs 42); **no table rule crosses the right margin** (3→16 columns); CJK; ligatures normalised |
| Corpus | `test_corpus.py` (14) | 12 documents × their formats through the format's own reader; the corpus covers every format, both structures and two scripts; **the corpus is not empty** (a paramétrized suite over an empty list is green by absence) |
| End to end | `test_end_to_end_simulation.py` (5) | tool → service → renderer → disk, opened by the format's reader; a Chinese reader gets 目录 |
| Prompt | `agents/prompts/test_document_generation_prompt.py` | every placeholder supplied, no hard-coded budget, the whole vocabulary published, the cacheable prefix marked |

### Manual, at review (`task documents:corpus:measure`, Windows + Office)

1. `task documents:corpus:render` then `task documents:corpus:measure`.
2. Read: `OVERFLOWS=0 REFUSED=0`; Word's `TOC=1` on `report_long` and
   `zh_document`, `TOC=0` on `memo_short`; footers `Page 1 / 10` and
   `第 1 页，共 7 页`; H1 numbers `[1] [2] [3]`; Excel `tables=1 freeze=True`.
3. LOOK at `report_long.pdf` (contents on its own page, exact numbers),
   `table_wide.pdf` (12 columns inside the page), `minutes_shaped.pdf` (no
   apparatus), `deck_kinds.pptx` and `deck_dense.pptx`.
4. Result 2026-09-08: 0 overflows on 62 slides, every workbook opened, and the
   two defects the eye caught (a harness overwriting the artefact it measured,
   a 12-column table running 714 pt wide on a 595 pt page) fixed with an oracle
   each.

### Gates run

`task lint:backend` (ruff, black, **mypy strict on 1 483 files**),
`task lint:docs`, `task lint:hygiene`, `task lint:ci-parity`, `task lint:i18n`,
`task test:markers`, `task test:backend:unit:fast` (**23 562 passed**),
`task test:frontend` (**7 626 passed**), the shrink-only ratchets (file size —
`structured_output.py` was brought back under its cap by EXTRACTING its error
taxonomy, never by raising the cap — complexity, coupling).
