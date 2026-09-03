# Meeting Template Library, Reformatting and Adjustments — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (owner rule: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking. **No git action of any kind** (owner rule): every « commit » step of the usual template is replaced by a **gate** step — the named command must be green before the next task starts.

**Goal:** Let a user keep several minutes templates (built-in and their own), have LIA pick the best one from the transcript, reformat existing minutes with another template in place or as new minutes, plus: minutes emailed from the platform SMTP sender, bulk delete of meetings, a readable template editor, recording controls out of the composer's « + », and download/move of knowledge-space documents.

**Architecture:** Built-in templates live in code and a six-language data module and are referenced as `builtin:<key>`; user templates are `meeting_templates` rows referenced as `user:<uuid>`; every meeting records which template produced its minutes and why. A fifth section kind (`transcript`) is filled by a part-by-part rewrite because the synthesis slot cannot emit a whole meeting in one call. Knowledge-space moves update the document row, its denormalized chunks and the file, in that order.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + Pydantic 2 (backend, Python 3.14), Next.js 16 + React 19 + vitest (frontend), LangChain structured output on the `meeting_synthesis` slot.

**Spec:** `docs/superpowers/specs/2026-09-03-meeting-template-library-design.md` (owner decisions in §7 — they amend §D, §E.2, §E.6).

## Global Constraints

- Six languages everywhere (`en, fr, de, es, it, zh`; backend key `zh-CN`), strict key parity enforced by the pre-commit hook; zh duplicates plural values to `_one`.
- Every user-visible backend string goes through `core/i18n_*` data modules; every prompt fragment lives in `prompts/v1/*.txt` and is loaded by name; no tunable number in prompt prose.
- Template bounds are the existing ones and must not change: ≤ 12 sections, key `^[a-z][a-z0-9_]{1,39}$`, label ≤ 80, instruction ≤ 600 (`schemas.py:24-29`).
- `meeting_synthesis` slot `max_tokens=8000`: a rewrite part must stay under it (`MEETINGS_REWRITE_PART_CHARS=12000` chars in → ≈ 4 k tokens out).
- Frontend: native controls, translated accessible names, `aria-disabled` + handler guard (never `disabled` on a focused control), `RowActions`/`SectionToolbar` for list actions, `EmptyState` for emptiness, no `opacity-0 group-hover`.
- Ratchets are shrink-only (file size 600 logical SLOC, CC < 15, a11y, react-hooks, coverage floors 68 % backend / 75-70-72-76 frontend). `MeetingDetailPanels.tsx`, `service.py` (727 lines) and `processing.py` (753 lines) are near their caps: new behaviour goes into NEW modules named below.
- Never `print`, never inline French in Python, PII never at INFO.
- Gates (run from the repo root unless stated): `task lint`, `task test:backend:unit:fast`, `task test:frontend`, `task test:frontend:coverage`, `task lint:i18n`, `task lint:docs:preview`, `task db:migrate:replay-check`, `task ci:fast` before the final review.

---

## Part A — Bounded adjustments

### Task A1: Minutes email through the platform SMTP sender

**Files:**
- Modify: `apps/api/src/infrastructure/email/email_service.py:35-97`
- Modify: `apps/api/src/domains/meetings/delivery.py` (remove `_resolve_email_client`, rewrite `send_minutes_email`)
- Modify: `apps/api/src/domains/meetings/service.py:690-708` (`email`)
- Modify: `apps/api/src/domains/meetings/processing.py:410-433` (`_auto_email` docstring only)
- Modify: `apps/api/src/core/i18n_meetings.py` (`_HEADER_LABELS` unchanged — the subject reuses `minutes`)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — remove `meetings.errors.email_connector_missing`, reword `meetings.settings.auto_email_hint`
- Modify: `apps/web/src/app/[lng]/dashboard/meetings/[id]/__tests__/page.test.tsx:275-290`
- Modify: `docs/superpowers/specs/2026-09-02-meeting-recording-and-minutes-design.md:231` (API table row)
- Test: `apps/api/tests/unit/infrastructure/email/test_email_service_thread.py` (create), `apps/api/tests/unit/domains/meetings/test_delivery.py`

**Interfaces:**
- Produces: `delivery.minutes_subject(report: MeetingReport, language: str) -> str`; `delivery.send_minutes_email(db, *, user_id, recipient, meeting, report, language, gaps=0) -> None` (same signature, raises `MinutesDeliveryError("email_send_failed")` only).

- [ ] **Step 1: Failing test — the SMTP exchange runs off the event loop and carries the platform sender**

```python
# apps/api/tests/unit/infrastructure/email/test_email_service_thread.py
"""EmailService: the blocking smtplib exchange never runs on the event loop."""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from src.infrastructure.email import email_service as module

pytestmark = pytest.mark.unit


async def test_send_email_runs_smtp_in_a_worker_thread_with_the_platform_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class _Smtp:
        def __init__(self, host: str, port: int) -> None:
            seen["thread"] = threading.current_thread().name
        def __enter__(self): return self
        def __exit__(self, *exc): return None
        def starttls(self): seen["tls"] = True
        def login(self, u, p): seen["login"] = (u, p)
        def sendmail(self, sender, to, payload):
            seen["from"] = sender; seen["to"] = to; seen["payload"] = payload

    monkeypatch.setattr(module.smtplib, "SMTP", _Smtp)
    monkeypatch.setattr(module.settings, "application_smtp_from", "lia@example.test")
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_username", "")
    monkeypatch.setattr(module.settings, "alertmanager_smtp_auth_password", "")
    ok = await module.EmailService().send_email("me@example.test", "S", "<p>h</p>", "t")
    assert ok is True
    assert seen["from"] == "lia@example.test" and seen["to"] == "me@example.test"
    assert seen["thread"] != threading.main_thread().name  # asyncio.to_thread
    assert "From: lia@example.test" in str(seen["payload"])
```

- [ ] **Step 2: Run it** — `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/email/test_email_service_thread.py -v` → FAIL on the thread assertion.

- [ ] **Step 3: Implement** — in `email_service.py`, add `import asyncio`, extract the `with smtplib.SMTP(...)` block into `def _deliver(self, to_email: str, payload: str) -> None` (sync, unchanged body: `starttls`+`login` only when both credentials exist, then `sendmail(self.smtp_from, to_email, payload)`), and in `send_email` replace the block by `await asyncio.to_thread(self._deliver, to_email, msg.as_string())`. Docstring: « The SMTP exchange is synchronous (`smtplib`); it runs in a worker thread so the event loop keeps serving SSE while the relay answers. »

- [ ] **Step 4: Run it** → PASS. Run `pytest tests/unit/infrastructure/email -q` → all green.

- [ ] **Step 5: Failing tests for delivery** — replace the two connector tests in `test_delivery.py` (`test_email_goes_through_the_resolved_client_and_is_recorded`, the `email_connector_missing` one at line ~104) with:

```python
async def test_email_goes_through_the_platform_smtp_service_and_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = SimpleNamespace(send_email=AsyncMock(return_value=True))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "get_email_service", lambda: sender)
    monkeypatch.setattr(delivery, "MeetingRepository", lambda db: repo)
    meeting = _meeting()
    await send_minutes_email(
        object(), user_id=uuid.uuid4(), recipient="me@example.test",
        meeting=meeting, report=_report(), language="fr",
    )
    kwargs = sender.send_email.await_args.kwargs
    assert kwargs["to_email"] == "me@example.test"
    assert kwargs["subject"] == "Compte rendu de réunion · Point projet"
    assert "<h1" in kwargs["html_body"] and kwargs["text_body"].startswith("# Point projet")
    repo.set_email_sent.assert_awaited_once()


async def test_a_refused_delivery_is_email_send_failed_and_nothing_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = SimpleNamespace(send_email=AsyncMock(return_value=False))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "get_email_service", lambda: sender)
    monkeypatch.setattr(delivery, "MeetingRepository", lambda db: repo)
    with pytest.raises(MinutesDeliveryError) as exc:
        await send_minutes_email(
            object(), user_id=uuid.uuid4(), recipient="me@example.test",
            meeting=_meeting(), report=_report(), language="en",
        )
    assert exc.value.code == "email_send_failed"
    repo.set_email_sent.assert_not_awaited()
```

- [ ] **Step 6: Implement `delivery.py`** — delete `_resolve_email_client` and the connector imports; add:

```python
from src.infrastructure.email import get_email_service
from src.domains.meetings.render import render_markdown  # add to the existing import

#: Language-neutral separator between the minutes label and the title.
_SUBJECT_SEPARATOR = " · "


def minutes_subject(report: MeetingReport, language: str) -> str:
    """``<Meeting minutes> · <title>`` — a mailbox lists subjects, not pages."""
    return f"{get_header_label('minutes', language)}{_SUBJECT_SEPARATOR}{report.title}"


async def send_minutes_email(db, *, user_id, recipient, meeting, report, language, gaps=0) -> None:
    """Email the minutes to ``recipient`` from the platform sender (``APPLICATION_SMTP_FROM``).

    Raises:
        MinutesDeliveryError: ``email_send_failed`` when the SMTP relay refused or
            is unreachable (``EmailService`` answers False and logs the cause).
    """
    header = build_header(meeting, report, language=language, gaps=gaps)
    sent = await get_email_service().send_email(
        to_email=recipient,
        subject=minutes_subject(report, language),
        html_body=render_html(report, header),
        text_body=render_markdown(report, header),
    )
    if not sent:
        logger.warning("meeting_minutes_email_failed", meeting_id=str(meeting.id), user_id=str(user_id))
        raise MinutesDeliveryError("email_send_failed", "smtp delivery refused")
    await MeetingRepository(db).set_email_sent(meeting.id, sent_at=datetime.now(UTC))
    logger.info("meeting_minutes_emailed", meeting_id=str(meeting.id), user_id=str(user_id))
```

  Import `get_header_label` from `src.core.i18n_meetings`. In `service.py::email`, drop the `if exc.code == "email_connector_missing"` branch (only `raise_meeting_delivery_failed(exc.code)` remains) and update the docstring (« from the platform sender »). Module docstring of `delivery.py`: replace the connector paragraph by « The email leaves from the platform SMTP sender (`APPLICATION_SMTP_FROM`), like every account email: the minutes are LIA's document, not a message the user writes from their mailbox. »

- [ ] **Step 7: Frontend + docs** — remove `meetings.errors.email_connector_missing` from the six locales; `meetings.settings.auto_email_hint` → en « Sent by LIA from its own address, to yours. » (fr « Envoyé par LIA depuis sa propre adresse, à la vôtre. », de/es/it/zh equivalents); in `page.test.tsx:275-290` replace the 409 case by a 502 `email_send_failed` expecting `toast.error('meetings.errors.email_send_failed')`; spec table row 231 → « To `user.email` from `APPLICATION_SMTP_FROM`; 502 `email_send_failed` ».

- [ ] **Step 8: Gate** — `cd apps/api && .venv/Scripts/pytest tests/unit/domains/meetings tests/unit/infrastructure/email -q` green; `cd apps/web && pnpm exec vitest run "src/app/[lng]/dashboard/meetings"` green; `task lint:i18n` green; `grep -rn email_connector_missing apps docs` returns nothing.

### Task A2: Bulk delete of meetings (API)

**Files:**
- Modify: `apps/api/src/domains/meetings/schemas.py` (requests/responses)
- Modify: `apps/api/src/core/constants.py` (`MEETINGS_BULK_MAX: int = 100`, next to `MEETINGS_RATE_LIMIT_*`)
- Create: `apps/api/src/domains/meetings/bulk.py`
- Modify: `apps/api/src/domains/meetings/router.py` (static path before `/{meeting_id}`)
- Test: `apps/api/tests/unit/domains/meetings/test_bulk.py`

**Interfaces:**
- Produces: `schemas.MeetingBulkDeleteRequest(ids: list[UUID])`, `schemas.BulkSkipped(id, code)`, `schemas.MeetingBulkDeleteResponse(deleted: list[UUID], skipped: list[BulkSkipped])`; `bulk.bulk_delete(service: MeetingService, user_id, ids) -> MeetingBulkDeleteResponse`.

- [ ] **Step 1: Failing test**

```python
# apps/api/tests/unit/domains/meetings/test_bulk.py
"""Bulk delete (ADR-259): every id is answered — deleted or skipped with a code."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.meetings.bulk import bulk_delete
from src.domains.meetings.models import MeetingStatus

pytestmark = pytest.mark.unit


def _service(rows: dict[uuid.UUID, MeetingStatus]) -> MagicMock:
    svc = MagicMock()
    async def _get(user_id, meeting_id):
        if meeting_id not in rows:
            raise BaseAPIException(status_code=404, detail={"code": "meeting_not_found"})
        return MagicMock(id=meeting_id, status=rows[meeting_id])
    svc.get = AsyncMock(side_effect=_get)
    svc.delete = AsyncMock()
    return svc


async def test_ready_rows_are_deleted_in_flight_and_live_rows_are_skipped_with_a_code() -> None:
    ready, busy, live, foreign = (uuid.uuid4() for _ in range(4))
    svc = _service({ready: MeetingStatus.READY, busy: MeetingStatus.PROCESSING, live: MeetingStatus.RECORDING})
    result = await bulk_delete(svc, uuid.uuid4(), [ready, busy, live, foreign])
    assert result.deleted == [ready]
    assert [(s.id, s.code) for s in result.skipped] == [
        (busy, "meeting_in_progress"), (live, "meeting_in_progress"), (foreign, "meeting_not_found"),
    ]
    svc.delete.assert_awaited_once()


async def test_a_failing_delete_is_reported_not_raised() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    svc = _service({a: MeetingStatus.READY, b: MeetingStatus.READY})
    svc.delete = AsyncMock(side_effect=[OSError("disk"), None])
    result = await bulk_delete(svc, uuid.uuid4(), [a, b])
    assert result.deleted == [b] and result.skipped[0].code == "delete_failed"
```

- [ ] **Step 2: Run** → FAIL (`bulk` missing).

- [ ] **Step 3: Implement** — schemas:

```python
class MeetingBulkDeleteRequest(BaseModel):
    """Delete several meetings; each id is answered individually."""
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MEETINGS_BULK_MAX, description="Meeting ids.")

class BulkSkipped(BaseModel):
    id: uuid.UUID
    code: str = Field(description="Stable reason (meeting_not_found, meeting_in_progress, delete_failed).")

class MeetingBulkDeleteResponse(BaseModel):
    deleted: list[uuid.UUID]
    skipped: list[BulkSkipped]
```

  `bulk.py`:

```python
"""Bulk operations on meetings (ADR-259): one answer per id, never a disguised partial success."""
from __future__ import annotations
import uuid
import structlog
from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.meetings.schemas import BulkSkipped, MeetingBulkDeleteResponse
from src.domains.meetings.service import MeetingService

logger = structlog.get_logger(__name__)
_UNDELETABLE = (*LIVE_STATUSES, MeetingStatus.PROCESSING)


async def bulk_delete(service: MeetingService, user_id: uuid.UUID, ids: list[uuid.UUID]) -> MeetingBulkDeleteResponse:
    """Delete the owned, terminal meetings among ``ids``; skip the rest with a reason.

    A live capture is skipped (its client owns the upload queue — discarding
    goes through the banner) and so is a processing job (the worker holds a lease).
    """
    deleted: list[uuid.UUID] = []
    skipped: list[BulkSkipped] = []
    for meeting_id in dict.fromkeys(ids):  # order kept, duplicates folded
        try:
            meeting = await service.get(user_id, meeting_id)
        except BaseAPIException:
            skipped.append(BulkSkipped(id=meeting_id, code="meeting_not_found")); continue
        if meeting.status in _UNDELETABLE:
            skipped.append(BulkSkipped(id=meeting_id, code="meeting_in_progress")); continue
        try:
            await service.delete(user_id, meeting_id)
        except Exception as exc:  # noqa: BLE001 — one failure must not hide the others
            logger.warning("meeting_bulk_delete_item_failed", meeting_id=str(meeting_id), error=exc.__class__.__name__)
            skipped.append(BulkSkipped(id=meeting_id, code="delete_failed")); continue
        deleted.append(meeting_id)
    logger.info("meeting_bulk_delete", user_id=str(user_id), deleted=len(deleted), skipped=len(skipped))
    return MeetingBulkDeleteResponse(deleted=deleted, skipped=skipped)
```

  Router, in the static block: `@router.post("/bulk-delete", response_model=MeetingBulkDeleteResponse, summary="Delete several meetings")` calling `bulk_delete(MeetingService(db), user.id, body.ids)`.

- [ ] **Step 4: Run** → PASS. Gate: `pytest tests/unit/domains/meetings -q`.

### Task A3: Bulk delete of meetings (list page selection)

**Files:**
- Modify: `apps/web/src/types/meetings.ts` (`MeetingBulkDeleteResponse`), `apps/web/src/lib/meetings/api.ts` (`bulkDelete`), `apps/web/src/hooks/useMeetings.ts` (`useMeetingList` returns `bulkDelete`)
- Create: `apps/web/src/components/meetings/MeetingSelectionBar.tsx`, `apps/web/src/lib/meetings/selection.ts`
- Modify: `apps/web/src/app/[lng]/dashboard/meetings/page.tsx`
- Modify: six locales — `meetings.list.select_row`, `select_all_page`, `selected_count_one/_other`, `delete_selected_one/_other`, `confirm_bulk_delete_title`, `confirm_bulk_delete_description_one/_other`, `bulk_deleted_one/_other`, `bulk_skipped_one/_other`, `not_selectable`
- Test: `apps/web/src/lib/meetings/__tests__/selection.test.ts`, `apps/web/src/app/[lng]/dashboard/meetings/__tests__/page.test.tsx`

**Interfaces:**
- Produces: `selection.ts` pure helpers — `isSelectable(meeting: MeetingSummary): boolean` (`status` not in `recording|interrupted|processing`), `toggleId(set: ReadonlySet<string>, id: string): Set<string>`, `pageSelectionState(ids: string[], selected: ReadonlySet<string>): 'none' | 'some' | 'all'`; `MeetingSelectionBar({ lng, count, pageState, onSelectAll, onClear, onDelete, deleting })`.

- [ ] **Step 1: Failing tests for the pure helpers** (`selection.test.ts`): `isSelectable` false for the three in-flight statuses and true for `ready|failed|stopped`; `pageSelectionState` returns `none/some/all`; `toggleId` never mutates its input.

- [ ] **Step 2: Implement `selection.ts`** (pure, 30 lines) → tests PASS.

- [ ] **Step 3: Failing page tests** — in `page.test.tsx` add: « a ready row exposes a checkbox named `meetings.list.select_row` and a processing row's checkbox is `aria-disabled` », « selecting two rows shows the bar with `meetings.list.selected_count` and the delete button; confirming calls `bulkDelete` with both ids and clears the selection », « after deleting the only rows on page 2 the page steps back (refetch with offset 0) ». Mock `useMeetingList` to expose `bulkDelete: vi.fn().mockResolvedValue({deleted: ['m1','m2'], skipped: []})`; mock `@/components/ui/use-confirm` like `[id]/__tests__/page.test.tsx` does.

- [ ] **Step 4: Implement** — `meetingsApi.bulkDelete = (ids) => apiClient.post<MeetingBulkDeleteResponse>(`${BASE}/bulk-delete`, { ids })`; `useMeetingList` adds `bulkDelete` (calls the api, then `refetch`, returns the response) and exposes `isDeleting`. Page: `const [selected, setSelected] = useState<Set<string>>(new Set())`; each row gets, before the title button, a `<label className="flex h-11 w-11 shrink-0 items-center justify-center"><Checkbox checked aria-disabled={!isSelectable(m)} onChange={guarded} aria-label={t('meetings.list.select_row', {title})} /></label>`; `MeetingSelectionBar` above the list when `selected.size > 0` (count line, « select all on page » checkbox with `indeterminate` set through a ref, solid red « Delete (N) » `variant="destructive" size="sm"` `isLoading={deleting}`); on confirm → `bulkDelete([...selected])` → toast success `bulk_deleted` + (if skipped) toast info `bulk_skipped`; if `meetings.length === deleted.length && offset > 0` → `setOffset(offset - PAGE_SIZE)`; clear selection on `offset` change (derive: `useEffect` keyed on offset is a state reset — implement as `key={offset}` on the list wrapper so the selection state resets by remount, no effect).

- [ ] **Step 5: Run** `pnpm exec vitest run "src/app/[lng]/dashboard/meetings" src/lib/meetings` → PASS. Gate: `task lint:frontend`, `task lint:i18n`.

### Task A4: Readable template editor (collapsed instruction)

**Files:**
- Modify: `apps/web/src/components/meetings/MeetingTemplateEditor.tsx`
- Modify: six locales — `meetings.settings.instruction_toggle` (« What LIA must put in this section »), `instruction_missing`, `instruction_preview_empty`
- Test: `apps/web/src/components/meetings/__tests__/MeetingTemplateEditor.test.tsx`

- [ ] **Step 1: Failing tests** — « the instruction textarea is not rendered until the disclosure button (`aria-expanded=false`, name `meetings.settings.instruction_toggle`) is activated; the collapsed row shows the first line of the instruction », « a newly added section is expanded and its textarea focused », « a collapsed section with an empty instruction shows `meetings.settings.instruction_missing` and the toggle carries `aria-invalid`-bearing textarea once opened », « keyboard: Enter on the toggle opens it ».

- [ ] **Step 2: Implement** — state `const [open, setOpen] = useState<Set<string>>(() => new Set(sections.filter(s => !s.instruction.trim()).map(s => s.key)))`; `add()` appends the key to `open`; header row = `grid grid-cols-[auto_1fr_12rem_auto]` on `sm+` (position · heading input · kind select · up/down/remove), phone stacks; below it a `<button type="button" aria-expanded aria-controls={`${base}-instruction-panel`} className="flex w-full items-center gap-2 text-left text-xs">` with `ChevronRight` rotating, the label, and when collapsed a `truncate text-muted-foreground` preview (`instruction.split('\n')[0]` or `instruction_preview_empty`); panel `id=…-instruction-panel` renders the existing `Textarea` (`aria-invalid={!instruction.trim()}`, `rows={3}`) plus the `instruction_missing` caption in `text-destructive` when empty. Focus the textarea after add via a `ref` map + `queueMicrotask`.

- [ ] **Step 3: Run** → PASS; `pnpm cc:ratchet && pnpm a11y:ratchet` unchanged. Gate: `task lint:frontend`.

### Task A5: Recording surfaces — provider above the header, sticky banner, header toggle, mobile menu entry, « + » back to files

**Files:**
- Modify: `apps/web/src/components/meetings/MeetingRecorderProvider.tsx` (split: `MeetingRecorderProvider` keeps the coarse context; add a private `MeetingRecorderBannerContext` holding the full hook return; export `MeetingRecorderBannerSlot({ lng })`)
- Create: `apps/web/src/components/meetings/MeetingRecorderControl.tsx` (header toggle, ≥ `lg`)
- Modify: `apps/web/src/components/dashboard/MobileNavMenu.tsx` (props `action?: { label: string; icon: LucideIcon; tone?: 'default' | 'destructive'; onSelect: () => void }`, `live?: { label: string }`)
- Modify: `apps/web/src/app/[lng]/dashboard/layout.tsx` (provider wraps the shell from `<div className="min-h-screen …">`; `<MeetingRecorderBannerSlot lng={lng} />` first child of `<main>` wrapped in `sticky top-16 z-40`; `<MeetingRecorderControl lng={lng} />` between `ExecutionModeToggle` and `VoiceToggle` inside `hidden lg:block`; `MobileNavMenu` receives `action`/`live` from the context)
- Modify: `apps/web/src/components/chat/ChatInput.tsx:340-462, 976-985` (delete `ComposerAttachmentsControl`'s menu branch, `RecordMenuItem`, `useComposerRecorder` keeps only `meetingRecording`/`pttBlocked`; the « + » is the plain file button; remove `Disc`, `Square`, `FilePlus2`, `DropdownMenu*` imports if unused; keep the red dot? No — the header/menu carry the state now)
- Modify: `apps/web/src/components/meetings/MeetingRecordingBanner.tsx` (no logic change; `mb-3` stays)
- Modify: `apps/web/src/lib/mobile-visibility.ts` (new entry `meeting-recorder-control`, `kind: 'action'`, `tier: 'substituted'`, `minWidth: 1024`, `substitute: 'The logo menu offers Record/Stop and the trigger pulses red while recording (MobileNavMenu action)'`)
- Modify: six locales — `meetings.header.record`, `meetings.header.stop`, `meetings.header.live_label` (« Menu — recording in progress »), `meetings.header.elapsed`; remove `meetings.composer.*` (menu_label, add_file, record, stop) and `chat.attachments.add` stays
- Test: `MeetingRecorderProvider.test.tsx`, `MobileNavMenu.test.tsx`, `ChatInput.meetings.test.tsx`, create `MeetingRecorderControl.test.tsx`, `apps/web/e2e/smoke/dashboard-header-reachability.spec.ts` (re-run)

**Interfaces:**
- Produces: `useMeetingRecorderContext()` unchanged (coarse); `MeetingRecorderBannerSlot` renders `MeetingRecordingBanner` or null; `MeetingRecorderControl` = `<Button variant="ghost" size="sm" className="w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9">` (the `VoiceToggle` geometry) with `aria-pressed={isCapturing}`, `aria-label` = record/stop, `Disc` icon, `text-destructive animate-pulse` while capturing, elapsed `hidden xl:inline tabular-nums` read from the banner context (it is the only consumer allowed the fine-grained values besides the banner); `MobileNavMenu` renders the `action` as a `DropdownMenuItem` after a `DropdownMenuSeparator`, and when `live` is set the trigger adds `from-destructive to-destructive/80 animate-pulse` and `aria-label={live.label}`.

- [ ] **Step 1: Failing tests** — Provider: « the banner renders inside `MeetingRecorderBannerSlot`, not inside the provider itself » and « the coarse context value is referentially stable while `level` changes » (existing test adapted). MobileNavMenu: « an `action` renders as a menu item with its label and calls `onSelect` », « with `live`, the trigger's accessible name is `live.label` and it carries `animate-pulse` ». Control: « idle → name `meetings.header.record`, click calls `start` », « capturing → name `meetings.header.stop`, `aria-pressed=true`, click calls `stop` », « hidden when the context is null ». ChatInput.meetings: « the + button opens the file picker directly and no menu item named `meetings.composer.record` exists » (rewrite the file's expectations).

- [ ] **Step 2: Implement** as listed above. In `layout.tsx`, compute once: `const recorder = useMeetingRecorderContext()` inside a small `HeaderRecorderBits` child component placed INSIDE the provider (the layout function itself is above it), returning `{ action, live }` for `MobileNavMenu` — a component rather than a hook in the layout body because the provider is rendered by the layout.

- [ ] **Step 2b: The banner publishes its height (defect found 2026-09-03 while verifying the plan).** The chat shell is `h-[calc(100dvh-5.25rem-var(--connector-banner-h,0px))]` (`chat/page.tsx:822`) and only `ConnectorHealthBanner` sets that variable through a `ResizeObserver` (`ConnectorHealthBanner.tsx:48-90`). The meeting banner is rendered in the same flow and reports nothing: **while recording on the chat page, the composer already sits ~60 px below the fold**. Fix inside `MeetingRecorderBannerSlot`: the sticky wrapper carries a `ref` and the same observer pattern writes `--meeting-banner-h` on `document.documentElement` (removed on unmount); `chat/page.tsx:822` subtracts BOTH variables: `calc(100dvh-5.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px))`. Test: a unit test on the slot asserts the property is set from `offsetHeight` with a stubbed `ResizeObserver` and removed on unmount (the connector banner's own test is the model); the chat proof in E2 checks the composer's bottom edge ≤ viewport height while a recording banner is shown at 390 px and 1280 px.

- [ ] **Step 2c: `meetings.list.empty_description` ×6** no longer says « from the paperclip » but « from the Record button above, or from the menu » (the FAQ/HOW/knowledge mentions of the paperclip and of the « + » menu are release surfaces, listed for the release pass — `docs/knowledge/02_chat.md:169`, FAQ `whats_new` entries).

- [ ] **Step 3: Run** the four test files + `pnpm exec vitest run src/lib/__tests__/mobile-visibility*` → PASS. Run `task lint:frontend`; run the e2e reachability spec from the container (`apps/web/e2e` README) — verify the header row at 1024 and 1280 px shows every control and the logout button.

---

## Part B — Backend template library

### Task B1: Schema, constants, settings, migration

**Files:**
- Modify: `apps/api/src/domains/meetings/models.py` (MeetingTemplate: `+description`, `+category`, `+builtin_key`, `-is_default` + index; MeetingPreference `+default_template_ref`; Meeting `+template_ref`, `+template_name`, `+template_selection`, `+template_selection_reason`, `+source_meeting_id` FK `meetings.id` `ondelete="SET NULL"`, index `ix_meetings_source`)
- Modify: `apps/api/src/domains/meetings/schemas.py` (§E.4 contracts, `TemplateCategory`, `TemplateSelection`, `SectionKind.TRANSCRIPT`, `TranscriptLine`, `ReportSection.transcript`, `MeetingTemplateSummary`, `MeetingTemplateListResponse`, `MeetingTemplateCreate`, `MeetingTemplateUpdate` (+description/category), `MeetingReformatRequest(template_ref: str, mode: Literal["replace","new"])`, `MeetingReformatResponse(id, status, stage, source_meeting_id)`, `MeetingPreferencesUpdate.default_template_ref: str | None`, `MeetingStartRequest.template_ref: str | None`, `MeetingPatchRequest.template_ref: str | None`, summary/detail fields, `MeetingDetailResponse.derived_count: int = 0`)
- Modify: `apps/api/src/core/constants.py` (`MEETINGS_TEMPLATE_AUTO_SELECT_ENABLED_DEFAULT = True`, `MEETINGS_TEMPLATE_AUTO_MIN_CONFIDENCE_DEFAULT = 0.5`, `MEETINGS_MAX_USER_TEMPLATES_DEFAULT = 50`, `MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS = 6000`, `MEETINGS_REWRITE_PART_CHARS = 12000`, `MEETINGS_REWRITE_MIN_RATIO = 0.4`, `MEETINGS_TEMPLATE_REF_MAX = 80`, `MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY = "default_minutes"`)
- Modify: `apps/api/src/core/config/meetings.py` (three settings), `.env.example` §87, `.env.prod.example`
- Create: `apps/api/alembic/versions/2026_09_03_1200-e0f1a2b3c4d5_meeting_template_library.py`
- Test: `apps/api/tests/unit/domains/meetings/test_models.py` (extend), `apps/api/tests/unit/core/config/test_meetings_settings.py` (extend), `apps/api/tests/unit/test_meeting_template_library_migration_guard.py` (create)

- [ ] **Step 1: Failing tests** — models: `MeetingTemplate.__table__.columns` has `category` with server default `'custom'` and no `is_default`; `Meeting.__table__.c.source_meeting_id.foreign_keys` targets `meetings.id` with `SET NULL`; settings: bounds (`min_confidence` in `[0,1]`, `max_user_templates` in `[1,500]`); migration guard: the file's `upgrade` mentions every added column name and the dropped index name, `downgrade` mentions the reverse, and the down revision is `c8d9e0f1a2b3`.

- [ ] **Step 2: Implement models/schemas/constants/settings** exactly as named. `ReportSection.is_empty` gains `case SectionKind.TRANSCRIPT: return not any(line.text.strip() for line in self.transcript)`. `MeetingPatchRequest._something_to_change` includes `template_ref`. `MeetingTemplateCreate`:

```python
class MeetingTemplateCreate(BaseModel):
    """Create a user template, from scratch or by duplicating a reference."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: TemplateCategory = Field(default=TemplateCategory.CUSTOM)
    sections: list[TemplateSection] | None = Field(default=None, min_length=1, max_length=MAX_TEMPLATE_SECTIONS)
    duplicate_of: str | None = Field(default=None, max_length=MEETINGS_TEMPLATE_REF_MAX, pattern=TEMPLATE_REF_PATTERN)

    @model_validator(mode="after")
    def _sections_or_source(self) -> MeetingTemplateCreate:
        if (self.sections is None) == (self.duplicate_of is None):
            raise ValueError("exactly one of sections or duplicate_of")
        if self.sections is not None and self.name is None:
            raise ValueError("name is required without duplicate_of")
        return self
```

  with `TEMPLATE_REF_PATTERN = r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-f-]{36})$"` in `schemas.py` and the unique-keys validator shared through a module function `_unique_keys(sections)` used by both Create and Update.

- [ ] **Step 3: Migration** — `upgrade()`: `op.add_column("meeting_templates", sa.Column("description", sa.Text(), nullable=True))`, `sa.Column("category", sa.String(30), nullable=False, server_default="custom")`, `sa.Column("builtin_key", sa.String(60), nullable=True)`; `op.drop_index("uq_meeting_templates_one_default_per_user", table_name="meeting_templates")`; `op.drop_column("meeting_templates", "is_default")`; `op.add_column("meeting_preferences", sa.Column("default_template_ref", sa.String(80), nullable=True))`; meetings: `template_ref String(80)`, `template_name String(120)`, `template_selection String(12)`, `template_selection_reason String(300)`, `source_meeting_id UUID FK meetings.id ondelete SET NULL` + `op.create_index("ix_meetings_source", "meetings", ["source_meeting_id"])`; data step: `UPDATE meetings SET template_selection = 'preference' WHERE template_snapshot IS NOT NULL` (name stays NULL for historical rows — the frontend shows the untitled-format fallback; owner decision 4: no personalised data to carry). `downgrade()`: reverse, re-adding `is_default` `server_default=true` and the partial index `WHERE is_default = true` — with a guard `UPDATE meeting_templates SET is_default = false WHERE id NOT IN (SELECT DISTINCT ON (user_id) id FROM meeting_templates ORDER BY user_id, created_at)` so the unique index can be recreated. Docstring in the ADR-258 migration style.

- [ ] **Step 4: Run** unit tests → PASS. Gate: `task db:migrate:replay-check` (dev containers; remember `docker restart lia-api-dev` if the reload wedges).

### Task B2: `TemplateRef`, catalogue, six-language data module

**Files:**
- Create: `apps/api/src/domains/meetings/template_ref.py`
- Create: `apps/api/src/domains/meetings/template_catalogue.py`
- Create: `apps/api/src/core/i18n_meeting_templates.py`
- Modify: `apps/api/src/core/i18n_meetings.py` (remove `DEFAULT_SECTION_KEYS`, `_SECTION_LABELS`, `DEFAULT_SECTION_INSTRUCTIONS`, `_TEMPLATE_NAME`, `get_section_label`, `get_template_name`; keep everything else)
- Modify: `apps/api/src/domains/meetings/templates.py` (`DEFAULT_SECTION_KINDS`/`default_sections`/`default_template` become thin wrappers over the catalogue's `default_minutes`; keep `parse_sections`, `sections_to_json`)
- Test: `apps/api/tests/unit/domains/meetings/test_template_ref.py`, `test_template_catalogue.py`; update `test_templates_and_i18n.py` imports

**Interfaces:**
- Produces:
  ```python
  # template_ref.py
  class TemplateRef:  # frozen dataclass
      kind: Literal["builtin", "user"]; key: str | None; id: UUID | None
      @classmethod
      def parse(cls, value: str) -> TemplateRef   # ValueError on any other shape
      @classmethod
      def builtin(cls, key: str) -> TemplateRef
      @classmethod
      def user(cls, template_id: UUID) -> TemplateRef
      def __str__(self) -> str                     # "builtin:key" | "user:<uuid>"
  # template_catalogue.py
  class BuiltinSection(NamedTuple): key: str; kind: SectionKind; instruction: str
  class BuiltinTemplate(NamedTuple): key: str; category: TemplateCategory; auto_selectable: bool; sections: tuple[BuiltinSection, ...]
  BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...]; BUILTIN_BY_KEY: dict[str, BuiltinTemplate]
  def builtin_sections(key: str, language: str | None) -> list[TemplateSection]
  def builtin_template(key: str, language: str | None) -> MeetingTemplateResponse
  def builtin_summary(key: str, language: str | None) -> MeetingTemplateSummary
  # i18n_meeting_templates.py
  def get_template_name(key: str, language: str | None) -> str
  def get_template_description(key: str, language: str | None) -> str
  def get_section_label(key: str, language: str | None) -> str
  TEMPLATE_KEYS: tuple[str, ...]  # the 26 keys, the oracle of the completeness asserts
  ```

- [ ] **Step 1: Failing tests** — `TemplateRef.parse("builtin:default_minutes")`, `parse("user:<uuid>")`, refuses `"builtin:"`, `"user:not-a-uuid"`, `"x:y"`, round-trips through `str`. Catalogue: `len(BUILTIN_TEMPLATES) == 26`, keys unique and equal to `TEMPLATE_KEYS`, every template ≤ 12 sections with unique keys matching `SECTION_KEY_PATTERN`, every instruction 1..600 chars, every `transcript` category template has `auto_selectable is False` and at least one `SectionKind.TRANSCRIPT` section, no non-transcript template has one, `default_minutes` sections are exactly today's six keys/kinds (regression of `test_default_template_is_ordered_localized_and_complete`), `builtin_sections("medical_appointment", "fr")[0].label` is French, names/descriptions/labels exist in the six languages for every key (parametrized over `TEMPLATE_KEYS` × `SIX`).

- [ ] **Step 2: Implement `template_ref.py`** (40 lines; `parse` splits on the first `:`; `user` validates with `uuid.UUID(...)`).

- [ ] **Step 3: Implement the catalogue.** Section keys shared across templates reuse one label entry (`summary`, `decisions`, `action_items`, `risks`, `open_questions`, `topics`, `participants_roles`, `next_steps`, `key_quotes`, `milestones`, `follow_ups`, `sentiment`, `transcript`, …). Instructions are English, written for the model (the `DEFAULT_SECTION_INSTRUCTIONS` style). The two transcript templates:

```python
BuiltinTemplate(
    key="transcript_clean", category=TemplateCategory.TRANSCRIPT, auto_selectable=False,
    sections=(
        BuiltinSection(
            "transcript", SectionKind.TRANSCRIPT,
            "The complete exchange, turn by turn, in the speakers' own language, made clean and "
            "readable: remove hesitations, fillers, false starts and repetitions; apply the speaker's "
            "own self-corrections; fix punctuation and obvious slips of the tongue. Keep every idea, "
            "figure, name and nuance; never summarize, never add, never change the register.",
        ),
    ),
),
BuiltinTemplate(
    key="transcript_professional", category=TemplateCategory.TRANSCRIPT, auto_selectable=False,
    sections=(
        BuiltinSection(
            "transcript", SectionKind.TRANSCRIPT,
            "The complete exchange, turn by turn, in the speakers' own language, rewritten in a clear "
            "professional register: complete sentences, precise vocabulary, no fillers, no repetitions, "
            "the speaker's self-corrections applied. Keep every idea, figure, name and commitment; never "
            "summarize or add; keep who said what.",
        ),
    ),
),
BuiltinTemplate(
    key="transcript_with_summary", category=TemplateCategory.TRANSCRIPT, auto_selectable=False,
    sections=(
        BuiltinSection("summary", SectionKind.PARAGRAPH, DEFAULT_SUMMARY_INSTRUCTION),
        BuiltinSection("transcript", SectionKind.TRANSCRIPT, <the transcript_clean instruction>),
    ),
),
```

  The 23 others follow the section lists of the spec §E.3 (write each instruction from the corresponding modeles.txt paragraph, first person removed, ≤ 600 chars; `speaker_psychology` ends with « This is an observation from language, not a diagnosis. »).

- [ ] **Step 4: Implement `core/i18n_meeting_templates.py`** — dicts `_TEMPLATE_NAMES`, `_TEMPLATE_DESCRIPTIONS` (key → six languages), `_SECTION_LABELS` (section key → six), the three getters through `_lang()` (copy of the `i18n_meetings._lang` chokepoint), `TEMPLATE_KEYS = tuple(_TEMPLATE_NAMES)`. Move today's `_SECTION_LABELS`, `_TEMPLATE_NAME` (→ `_TEMPLATE_NAMES["default_minutes"]`) here. `templates.py` keeps `DEFAULT_SECTION_KEYS`/`DEFAULT_SECTION_KINDS`/`DEFAULT_SECTION_INSTRUCTIONS` DERIVED from `BUILTIN_BY_KEY["default_minutes"]` (the names other modules import survive). Boot-time asserts at the bottom of `template_catalogue.py`:

```python
assert set(BUILTIN_BY_KEY) == set(TEMPLATE_KEYS), "catalogue and i18n names disagree"
for _t in BUILTIN_TEMPLATES:
    for _s in _t.sections:
        assert _s.key in SECTION_LABEL_KEYS, f"{_t.key}.{_s.key} has no label"
        assert len(_s.instruction) <= MAX_INSTRUCTION_CHARS, f"{_t.key}.{_s.key} instruction too long"
```

- [ ] **Step 5: Run** the three test files → PASS. Gate: `pytest tests/unit/domains/meetings -q`; `python scripts/audit/measure_sloc.py apps/api/src/domains/meetings/template_catalogue.py` < 600 (instructions are strings, they count — if over, split the catalogue by category into `template_catalogue/{meeting,analysis,…}.py` re-exported by `template_catalogue/__init__.py`).

### Task B3: Template repository and service (CRUD, duplicate, resolve)

**Files:**
- Modify: `apps/api/src/domains/meetings/repository.py` (`MeetingTemplateRepository`: replace `get_default_for_user` by `list_for_user(user_id) -> list[MeetingTemplate]` ordered by `name`, `get_for_user(template_id, user_id)`, `count_for_user(user_id)`; `MeetingPreferenceRepository.clear_default_template_if(user_id, ref: str) -> None` (UPDATE … WHERE default_template_ref = :ref))
- Create: `apps/api/src/domains/meetings/template_service.py`
- Modify: `apps/api/src/domains/meetings/service.py` (delete `get_template`, `put_template`, `reset_template`; `put_preferences` validates `default_template_ref` through `MeetingTemplateService.resolve` and stores it; `_preferences_response` returns it)
- Modify: `apps/api/src/domains/meetings/router.py` (delete `/template` routes; add `/templates` GET, POST, and `/templates/{ref}` GET, PUT, DELETE — all BEFORE `/{meeting_id}`)
- Test: `apps/api/tests/unit/domains/meetings/test_template_service.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class ResolvedTemplate:
      ref: TemplateRef; name: str; category: TemplateCategory; sections: list[TemplateSection]; auto_selectable: bool

  class MeetingTemplateService:
      def __init__(self, db: AsyncSession) -> None
      async def list(self, user_id, language) -> MeetingTemplateListResponse
      async def get(self, user_id, ref: str, language) -> MeetingTemplateResponse
      async def create(self, user_id, request: MeetingTemplateCreate, language) -> MeetingTemplateResponse
      async def update(self, user_id, ref: str, request: MeetingTemplateUpdate) -> MeetingTemplateResponse
      async def delete(self, user_id, ref: str) -> None
      async def resolve(self, user_id, ref: str, language) -> ResolvedTemplate   # 404 template_not_found / 422 template_ref_invalid
      async def candidates(self, user_id, language) -> list[ResolvedTemplate]   # auto-selectable builtins + user rows
  ```
  Refusal helpers in the same module: `raise_template_not_found(ref)` 404, `raise_template_readonly(ref)` 409 `template_readonly`, `raise_template_limit(max)` 409 `template_limit_reached` with `{"max": max}`, `raise_template_ref_invalid(ref)` 422 `template_ref_invalid`.

- [ ] **Step 1: Failing tests** (repo as `AsyncMock`, db `MagicMock` with async `commit` — the `test_service_guards.py` fixture pattern): list returns builtins localized + user rows with `builtin=False`; get of a builtin has `id None`; create with `sections` stores `category` and returns `ref="user:<id>"`; create with `duplicate_of="builtin:bant_analysis"` copies its sections and category and sets `builtin_key`; create beyond `settings.meetings_max_user_templates` (read from settings, never hard-coded) → 409; update/delete of a builtin → 409 `template_readonly`; delete of a user row calls `clear_default_template_if(user_id, "user:<id>")`; resolve of a foreign id → 404; resolve of `"nope"` → 422; candidates excludes transcript builtins.

- [ ] **Step 2: Implement** (≈ 220 lines). `list` = `[builtin_summary(k, language) for k in TEMPLATE_KEYS] + [self._summary(row) for row in rows]` sorted: user rows first? No — the frontend groups by category; return builtins then user rows, plus `max_user_templates=settings.meetings_max_user_templates`. Router handlers are one-liners over the service; `PUT /meetings/preferences` calls `MeetingTemplateService(db).resolve(...)` when `default_template_ref` is not None (a bad ref never reaches the row).

- [ ] **Step 3: Run** → PASS. Gate: `pytest tests/unit/domains/meetings -q`; `task lint:backend`.

### Task B4: Prompts, metric, automatic selection

**Files:**
- Create: `apps/api/src/domains/agents/prompts/v1/meeting_template_selection_prompt.txt`, `apps/api/src/domains/agents/prompts/v1/meeting_transcript_rewrite_prompt.txt`
- Modify: `apps/api/src/domains/agents/prompts/prompt_loader.py:211` (`PromptName` Literal + two names), `apps/api/src/domains/meetings/prompts.py` (`MeetingPromptName` + two names)
- Modify: `apps/api/src/infrastructure/observability/metrics_meetings.py` (`meeting_template_selection_total = Counter("meeting_template_selection_total", "...", ["outcome"])`)
- Modify: `infrastructure/observability/grafana/dashboards/27-meetings.json` (a stat panel « Template selection » with `sum by (outcome) (increase(meeting_template_selection_total[24h])) or vector(0)`, `"noValue": "0"`)
- Create: `apps/api/src/domains/meetings/template_resolution.py`
- Test: `apps/api/tests/unit/domains/meetings/test_template_resolution.py`; `tests/unit/domains/agents/prompts/test_prompt_name_literal_sync.py` and `tests/unit/test_metric_coverage_ratchet_guard.py` must stay green

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class TemplateDecision:
      sections: list[TemplateSection]; ref: TemplateRef; name: str
      selection: TemplateSelection; reason: str | None

  class TemplateChoice(BaseModel):            # model-facing
      template_ref: str; confidence: float = Field(ge=0, le=1); reason: str

  def transcript_excerpt(text: str, max_chars: int) -> str        # head + evenly sampled middle slices, ≤ max_chars
  def render_candidates(candidates: Sequence[ResolvedTemplate], language: str) -> str  # "- ref | category | name: description"
  async def decide_template(db, *, meeting: Meeting, preference: MeetingPreference | None,
                            turns: Sequence[TranscriptTurn], calendar_title: str | None,
                            language: str, capture: TokenCaptureHandler) -> TemplateDecision
  async def template_for_regeneration(db, *, meeting: Meeting, language: str) -> TemplateDecision
  ```

- [ ] **Step 1: Prompt files.** Selection prompt (system):

```
You are LIA. A meeting was transcribed and its minutes are about to be written. Choose the ONE minutes template that best fits what was actually said.

You will receive CANDIDATES (one per line: ref | category | name: what it is for), an optional CALENDAR EVENT title (a hint, never a fact), and an EXCERPT of the transcript (its beginning and evenly spaced slices — the whole meeting is not shown).

Answer with:
- template_ref: exactly one ref copied from CANDIDATES;
- confidence: 0 to 1, how sure you are that this template fits better than the general-purpose one;
- reason: one short sentence, in the language given as LANGUAGE, explaining the choice to the user.

Rules: prefer the general-purpose meeting minutes when the exchange is an ordinary work meeting; choose a specialised template only when its subject is unmistakable in the excerpt (a doctor's appointment, a garage, a bank advisor, a sales qualification, a lecture, a hiring interview…); never choose by the calendar title alone; never invent a ref.
```

  Rewrite prompt (system):

```
You are LIA. You receive ONE part of a meeting transcript as numbered speaker turns, and an INSTRUCTION describing how the text must be rewritten. Rewrite every turn according to the INSTRUCTION, in the SAME language as the transcript (never translate), keeping the speaker of each turn and its index.

Answer with one entry per input turn: index (copied), text (the rewritten turn). Merge nothing, drop nothing, add nothing: a turn that needs no change is returned as it is. Figures, names, dates and amounts are copied exactly as spoken. No markdown syntax, no speaker label inside the text, no commentary.
```

- [ ] **Step 2: Failing tests** — `transcript_excerpt` returns ≤ `max_chars`, starts with the head, contains a slice from the last third; precedence matrix with a fake LLM (monkeypatch `template_resolution.get_structured_output_with_retry`): explicit `meeting.template_ref` → `selection=USER`, LLM never called; preference set → `PREFERENCE`, never called; neither, LLM answers `("builtin:medical_appointment", 0.9, "…")` → `AUTO`, sections = that template; confidence 0.3 → `builtin:default_minutes`, reason contains the fallback marker, counter `outcome=fallback` incremented (read `meeting_template_selection_total.labels(outcome="fallback")._value.get()` before/after); `StructuredOutputError` → fallback; LLM answers a ref outside candidates → fallback; `settings.meetings_template_auto_select_enabled=False` → default with `AUTO`… no: → `selection=PREFERENCE`? Decision: disabled auto ⇒ `default_minutes` with `selection=AUTO` and reason « automatic selection disabled on this instance » would lie about a choice; use `selection=PREFERENCE`, reason `None`. `template_for_regeneration`: meeting with `user:` ref whose row is gone → sections from `template_snapshot`, name kept, selection kept.

- [ ] **Step 3: Implement** — `decide_template` order: (1) `meeting.template_ref` → `MeetingTemplateService(db).resolve` (a dangling ref here → fall through to (2) with a logged warning); (2) `preference.default_template_ref` → resolve (dangling → fall through); (3) disabled → default builtin, `PREFERENCE`; (4) LLM: `candidates = await service.candidates(user_id, language)`; human message = `LANGUAGE: {language}\nCALENDAR EVENT: {title or 'none'}\n\nCANDIDATES:\n{render_candidates}\n\nEXCERPT:\n{transcript_excerpt(render_transcript(turns), MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS)}`; `get_structured_output_with_retry(get_llm(MEETINGS_LLM_TYPE), _messages(load_meeting_prompt("meeting_template_selection_prompt"), human), TemplateChoice, provider=provider, node_name=f"{MEETINGS_LLM_TYPE}_select", config=RunnableConfig(callbacks=[capture]))` inside `try/except StructuredOutputError`; accept iff `choice.template_ref in {str(c.ref) for c in candidates}` and `choice.confidence >= settings.meetings_template_auto_min_confidence`; outcome counter `auto|fallback|preference|user`; reason clipped to 300. `_messages` and `render_transcript` are imported from `synthesis.py` (no cycle: `synthesis` does not import this module).

- [ ] **Step 4: Run** → PASS; `pytest tests/unit/domains/agents/prompts/test_prompt_name_literal_sync.py tests/unit/test_metric_coverage_ratchet_guard.py -q` green.

### Task B5: The `transcript` kind — rewrite pipeline, repair, rendering

**Files:**
- Create: `apps/api/src/domains/meetings/transcript_rewrite.py`
- Modify: `apps/api/src/domains/meetings/synthesis.py` (`SynthesizedSection.transcript` NOT added — the model never fills transcript sections; `_REPAIRERS[TRANSCRIPT] = _repair_transcript` keeps whatever `rewritten` the caller injected; `synthesize_minutes(turns, template, context, *, rewritten: dict[str, list[TranscriptLine]] | None = None)`; `repair_report(..., rewritten=...)`)
- Modify: `apps/api/src/domains/meetings/render.py` (`_md_section`, `_blocks_for_section`, `_html_section`: `TRANSCRIPT` → one line/paragraph per turn `**{speaker} [{mm:ss}]** {text}`), `processing.py::_summary_text` (transcript → first 300 chars)
- Test: `apps/api/tests/unit/domains/meetings/test_transcript_rewrite.py`, extend `test_synthesis.py`, `test_render.py`

**Interfaces:**
- Produces:
  ```python
  class RewrittenTurn(BaseModel): index: int; text: str
  class RewrittenTurns(BaseModel): turns: list[RewrittenTurn]
  def split_turns(turns: Sequence[TranscriptTurn], *, part_chars: int | None = None) -> list[list[int]]  # indexes per part, cut at turn boundaries, a single oversize turn is its own part
  async def rewrite_transcript(turns: Sequence[TranscriptTurn], instruction: str, *, provider: str, capture: TokenCaptureHandler) -> list[TranscriptLine]
  async def rewrite_for_template(turns, template: Sequence[TemplateSection], *, provider, capture) -> dict[str, list[TranscriptLine]]  # one rewrite per TRANSCRIPT section (distinct instructions run separately, identical instructions share one pass)
  ```

- [ ] **Step 1: Failing tests** — `split_turns` never splits a turn, sums to every index once, respects `part_chars`; `rewrite_transcript` with a fake LLM: (a) answers every index → lines in order with the original speakers/starts; (b) omits index 2 → original text kept for it; (c) adds index 99 → dropped; (d) a part whose total output is below `MEETINGS_REWRITE_MIN_RATIO` of its input → the fake is called again for that part (call count +1) and the second answer is kept; (e) `StructuredOutputError` on a part → propagates (the job classifies it as `synthesis_failed`, transient); `repair_report(..., rewritten={"transcript": lines})` fills the section and `is_empty()` is False; `render_markdown` of a transcript section emits `**S1 [00:05]** …` lines; `_summary_text` returns the head of the transcript when no paragraph/bullets exist.

- [ ] **Step 2: Implement** (`transcript_rewrite.py` ≈ 140 lines): parts from `split_turns`; per part the human message `INSTRUCTION:\n{instruction}\n\nTURNS:\n` + `"{i} | {speaker}: {text}"` lines; validation as specified; ratio check on `sum(len(text))`; each call `node_name=f"{MEETINGS_LLM_TYPE}_rewrite"`. Two refinements settled while verifying the plan against the code:
  - **The part size is derived from the EFFECTIVE slot config, never from the default alone.** `get_llm_config_for_agent` resolves `LLM_DEFAULTS → DB override cache` (`core/llm_config_helper.py:51`), so an administrator can lower `max_tokens` below 8000 in `llm_config_overrides`. `part_chars = min(MEETINGS_REWRITE_PART_CHARS, int(config.max_tokens * MEETINGS_CHARS_PER_TOKEN_ESTIMATE * MEETINGS_REWRITE_OUTPUT_SAFETY))` with `MEETINGS_REWRITE_OUTPUT_SAFETY = 0.6` (constant; a rewrite is about as long as its input, 60 % keeps JSON framing and verbose runs under the cap). Test: with `max_tokens=2000` the parts are cut around 3 600 chars.
  - **A missing index is a truncation signal, not a gap to paper over.** `extract_json_payload` salvages truncated answers (`structured_output.py:548-560`), so a cut-off rewrite comes back VALID but short. Rule: when the answer omits any input index, the part is split in two and each half is rewritten once more; only after that do the still-missing turns keep their original text, with a `meeting_rewrite_turns_kept_original` warning carrying the count (never the text). Test (d) becomes: omitted index → two half-part calls follow → merged result complete. In `synthesize_minutes`: `rewritten = await rewrite_for_template(turns, template, provider=provider, capture=capture)` when any section kind is TRANSCRIPT (computed BEFORE the condense decision; the structured call receives the template WITHOUT its transcript sections in `render_template` — the model must not try to fill them — and `repair_report` re-inserts them from `rewritten` at their template position). `_repair_transcript(section, raw)` is a no-op (registry completeness only); the injection happens in `repair_report` by key.

- [ ] **Step 3: Run** → PASS. Gate: `pytest tests/unit/domains/meetings -q`; SLOC of `synthesis.py` (465 lines today) stays under 600 logical — if not, move `render_transcript/render_context/render_template` into `synthesis_render.py`.

### Task B6: Processing integration, reformat (replace / new), stale-regeneration reaper

**Files:**
- Modify: `apps/api/src/domains/meetings/processing.py` (`_run`: after transcription `decision = await decide_template(db, meeting=meeting, preference=preference, turns=outcome.turns, calendar_title=calendar.title if calendar else None, language=language, capture=capture)` — `capture` is a `TokenCaptureHandler` created in `_run` and passed to `synthesize_minutes(..., capture=capture)` so the selection tokens join the synthesis usage (add the optional `capture` parameter to `synthesize_minutes`); `_completion_values` gains `template_ref=str(decision.ref)`, `template_name`, `template_selection=decision.selection.value`, `template_selection_reason`; `regenerate_minutes` uses `template_for_regeneration`)
- Create: `apps/api/src/domains/meetings/reformat.py`
- Modify: `apps/api/src/domains/meetings/repository.py` (`begin_regenerate(meeting_id, *, values: dict | None = None)` adds the template columns to the same UPDATE; `create_from_transcript(source: Meeting, *, values) -> Meeting`; `count_derived(meeting_id) -> int`; `clear_stale_regenerations(older_than_seconds: int) -> int`)
- Modify: `apps/api/src/domains/meetings/service.py` (`regenerate` keeps the meeting's template; `to_detail`/`to_summary` new fields; `patch_report` accepts `template_ref` on live/stopped rows and refuses `template_locked` otherwise; `start` stores a validated `template_ref`)
- Modify: `apps/api/src/domains/meetings/reapers.py` (`meetings_job_reaper` calls `clear_stale_regenerations(settings.meetings_job_lease_ttl_seconds)`, outcome label `regeneration_cleared`)
- Modify: `apps/api/src/domains/meetings/router.py` (`POST /{meeting_id}/reformat` → 202 `MeetingReformatResponse`)
- Modify: `apps/api/src/core/i18n_meetings.py` no change; `processing._notify_ready` metadata `+ "template_name"`
- Test: extend `test_processing_flow.py`, `test_reapers.py`, `test_service_guards.py`; create `test_reformat.py`

**Interfaces:**
- Produces: `reformat.reformat_meeting(service: MeetingService, user_id, meeting_id, request: MeetingReformatRequest, language) -> Meeting` (the row to answer with: the same meeting for `replace`, the NEW one for `new`); `repository.create_from_transcript` copies: `user_id, audio_format, segment_count, audio_bytes, audio_duration_seconds, audio_gaps, started_at, stopped_at, client_timezone, location_*, calendar_event_id, calendar_provider, stt_provider, stt_model, stt_language_hint, stt_detected_language, stt_diarized, stt_audio_seconds, transcript_encrypted` and sets `status=READY, stage=SYNTHESIZING, audio_path=None, audio_purged_at=now, keep_audio_until=None, stt_cost_eur=None, source_meeting_id=source.id, index_state=PENDING if rag enabled else DISABLED, template_ref/name/selection=user`.

- [ ] **Step 1: Failing tests** — processing: the completion values carry the decision fields and `capture` tokens from the selection are in `synthesis_tokens_in`; regeneration uses the meeting's own ref (LLM receives the snapshot sections, never `MeetingTemplateRepository`); reformat: `replace` on a READY meeting → `begin_regenerate` called with the new ref/name/`user`, returns the same id; `new` → `create_from_transcript` called with the copied fields listed above and `launch_regenerate(new_id)`; `new` on a meeting without transcript → 409 `transcript_unavailable`; `replace` while `stage` set → 409 `regeneration_in_progress`; a `builtin:` ref outside the catalogue → 422; reaper: `clear_stale_regenerations` is invoked with the lease TTL and its count reaches the metric label `regeneration_cleared`; service: `patch_report({template_ref})` on `processing` → 409 `template_locked`.

- [ ] **Step 2: Implement.** `clear_stale_regenerations`:

```python
async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
    """``ready`` + ``stage`` older than the lease TTL → stage cleared, error recorded.

    A regeneration is a fire-and-forget without a lease: a hard kill leaves the
    stage set and every later attempt refused (``regeneration_in_progress``).
    """
    threshold = func.now() - text(":s * interval '1 second'").bindparams(s=older_than_seconds)
    stmt = (
        update(Meeting)
        .where(Meeting.status == MeetingStatus.READY, Meeting.stage.is_not(None), Meeting.updated_at < threshold)
        .values(stage=None, last_error_code="regeneration_interrupted", last_error_message="")
        .execution_options(synchronize_session=False)
    )
    result = await self.db.execute(stmt)
    await self.db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
```

  `regenerate_minutes` guard at the top stays `stage is not SYNTHESIZING → return`; when `meeting.report_current is None` (a new-minutes row) a failure must still leave the row explainable: `fail_regenerate` already records the code, and the page (Task C5) shows the pending/failed panel when `report is null`.

- [ ] **Step 3: Run** → PASS. Gate: `pytest tests/unit/domains/meetings -q`; `task lint:backend`; SLOC guard on `service.py` and `processing.py` (`pytest tests/unit/test_file_size_ratchet_guard.py -q`) — the new logic lives in `reformat.py`, `template_resolution.py`, `bulk.py`, `template_service.py`; if `service.py` still grows past its frozen cap, move `to_detail`/`to_summary` into `projections.py`.

### Task B7: Backend runtime proof (dev containers)

- [ ] **Step 0: Environment.** On 2026-09-03 `lia-api-dev` was NOT running and `lia-postgres-dev`/`lia-redis-dev` reported `unhealthy` (`docker ps`): start with `task dev:detach`, wait for `/health` 200, and check the two healthchecks before any proof. The dev `.env` points `ALERTMANAGER_SMTP_SMARTHOST` at Brevo with `APPLICATION_SMTP_FROM=lia@jeyswork.com`: the email proof is run **hermetically first** against a stdlib SMTP sink started inside the container (`asyncio.start_server` script in the scratchpad answering EHLO/MAIL/RCPT/DATA/QUIT and printing the `From:` header; `aiosmtpd` is not installed on either side), with `ALERTMANAGER_SMTP_SMARTHOST=127.0.0.1:1025` and empty credentials for that run; one real send through Brevo to the owner's own address is the optional last check, on the owner's word.
- [ ] **Step 1:** `docker restart lia-api-dev`, wait `/health` 200. Extend the session proof script (scratchpad, ADR-258's `meetings_e2e_proof.py` pattern): PCM 53 s → stop → READY with `template_ref`, `template_selection="auto"`, a non-empty `reason` → `POST /reformat {template_ref:"builtin:transcript_clean", mode:"new"}` → 202 with a new id → poll until `report` non-null → the transcript section holds ≥ 1 line and `synthesis_cost_eur > 0` → `GET /meetings` lists both with `source_meeting_id` on the new one → `POST /meetings/{id}/email` → 200 and the dev SMTP sink (`.env` `ALERTMANAGER_SMTP_SMARTHOST`) shows `From: <APPLICATION_SMTP_FROM>` → `POST /bulk-delete` both → 200, both `deleted`; `rag_documents` for both gone (SQL count = 0).
- [ ] **Step 2:** Record the measured timings in the spec §8 (a new « Proofs » section).

---

## Part C — Frontend template library

### Task C1: Types, API, hooks

**Files:**
- Modify: `apps/web/src/types/meetings.ts` (`SectionKind` + `'transcript'`, `SECTION_KINDS` + `'transcript'`, `TranscriptLine`, `ReportSection.transcript: TranscriptLine[]`, `TemplateCategory` union + `TEMPLATE_CATEGORIES` ordered array `['custom','meeting','transcript','analysis','business','technical','personal','learning']`, `TemplateSelection`, `MeetingTemplateSummary`, `MeetingTemplateListResponse`, `MeetingTemplate` (`ref`, `id`, `name`, `description`, `category`, `sections`, `builtin`, `builtin_key`), `MeetingTemplateCreate`, `MeetingTemplateUpdate` (+description/category), `MeetingReformatRequest`, `MeetingReformatResponse`, `MeetingPreferences.default_template_ref`, `MeetingSummary`/`MeetingDetail` new fields, `MeetingNotificationMetadata.template_name?`)
- Modify: `apps/web/src/lib/meetings/api.ts` (`templates`, `template(ref)`, `createTemplate`, `updateTemplate(ref, body)`, `deleteTemplate(ref)`, `reformat(id, body)`; remove `template/putTemplate/resetTemplate`)
- Delete: `apps/web/src/hooks/useMeetingTemplate.ts`; Create: `apps/web/src/hooks/useMeetingTemplates.ts` (`{ templates, maxUserTemplates, isLoading, isSaving, error, refetch, load(ref), create, update, remove }` — same `useStaleGuard` pattern as the deleted hook)
- Modify: `apps/web/src/hooks/useMeetings.ts` (`useMeeting.reformat(request) -> Promise<MeetingReformatResponse | null>`)
- Create: `apps/web/src/lib/meetings/templates.ts` (pure: `groupByCategory(items): Map<TemplateCategory, MeetingTemplateSummary[]>` in `TEMPLATE_CATEGORIES` order, `templateRefLabel(summary)`, `isTranscriptTemplate(summary)`)
- Test: `apps/web/src/lib/meetings/__tests__/templates.test.ts`, `apps/web/src/hooks/__tests__/useMeetingTemplates.test.ts` (mock `meetingsApi`)

- [ ] **Step 1: Failing tests** for the pure helpers (grouping order, empty categories omitted, `custom` first) and the hook (`create` appends to `templates` and returns the row; `remove` filters it out; a failed `load` sets `error`).
- [ ] **Step 2: Implement.** `pnpm exec tsc --noEmit --incremental false` will list every consumer of the deleted hook — Tasks C2–C5 fix them; this task ends with the hook tests green even if tsc is red on `MeetingsSettings.tsx` (fixed in C4).

### Task C2: Transcript kind in view and editor; chat card template line

**Files:**
- Modify: `apps/web/src/components/meetings/MeetingReportView.tsx` (`isSectionEmpty` + `SectionBody` case `'transcript'` → `<ol>` of `<li className="grid grid-cols-[3.5rem_4rem_1fr]">` like `TranscriptList`), `MeetingReportEditor.tsx` (case `'transcript'` → one `Textarea` per line with a read-only speaker label, `aria-label` = `meetings.detail.transcript_line` with `{speaker, time}`), `MeetingMinutesCard.tsx` (line `meetings.card.template` when `metadata.template_name`)
- Modify: six locales — `meetings.settings.kind_transcript`, `meetings.detail.transcript_line`, `meetings.card.template`
- Test: `MeetingReportView.test.tsx`, `MeetingReportEditor.test.tsx`, `MeetingMinutesCard.test.tsx`

- [ ] **Step 1: Failing tests** — view renders the lines with speaker and elapsed; editor edits the text of line 2 and emits the updated section; card shows the template line only when present.
- [ ] **Step 2: Implement** → PASS.

### Task C3: Template library page

**Files:**
- Create: `apps/web/src/app/[lng]/dashboard/meetings/templates/page.tsx`, `loading.tsx`
- Create: `apps/web/src/components/meetings/MeetingTemplateLibrary.tsx` (list by category), `MeetingTemplateForm.tsx` (name, description, category select, `MeetingTemplateEditor`, Save/Cancel), `MeetingTemplatePreview.tsx` (read-only sections: heading, kind badge, instruction)
- Modify: six locales — `meetings.templates.*` (`title`, `subtitle`, `new`, `count_one/_other`, `category.{custom,meeting,transcript,analysis,business,technical,personal,learning}`, `builtin_badge`, `transcript_badge` (« Full rewrite, paid like a whole meeting »), `sections_count_one/_other`, `preview`, `duplicate`, `edit`, `delete`, `row_actions` (« Actions — {{name}} »), `form.name`, `form.description`, `form.category`, `form.create_title`, `form.edit_title`, `form.duplicate_suffix` (« (copy) »), `saved`, `deleted`, `limit_reached`, `confirm_delete_title`, `confirm_delete_description`, `empty_custom`), `navigation`: none (the page is reached from the Meetings page toolbar and the settings link)
- Test: `apps/web/src/app/[lng]/dashboard/meetings/templates/__tests__/page.test.tsx`, `apps/web/src/components/meetings/__tests__/MeetingTemplateLibrary.test.tsx`

**Interfaces:**
- `MeetingTemplateLibrary({ lng, templates, maxUserTemplates, onPreview(ref), onDuplicate(ref), onEdit(ref), onDelete(ref) })`; `MeetingTemplateForm({ lng, initial: MeetingTemplateUpdate, title, onSubmit, onCancel, isSaving })`.

- [ ] **Step 1: Failing tests** — page: skeleton on first load; `SectionToolbar` primary « New template » opens the form; categories render as `Accordion` items in `TEMPLATE_CATEGORIES` order with `custom` first and empty ones omitted; a builtin row offers Preview and Duplicate only (RowActions names in en and fr), a user row also Edit and Delete; Duplicate opens the form prefilled with the sections and `name + ' (copy)'`; saving calls `create` with `duplicate_of` when nothing but the name changed, else with `sections`; Delete confirms then calls `remove`; when `templates.filter(t => !t.builtin).length >= maxUserTemplates` the primary is `aria-disabled` with the `limit_reached` hint; transcript templates show the `transcript_badge`.
- [ ] **Step 2: Implement.** Form and preview swap in place of the list (`mode: {kind:'list'} | {kind:'preview', ref} | {kind:'form', initial, ref?}` state). `MeetingTemplateForm` reuses `MeetingTemplateEditor` (Task A4). Category select lists `TEMPLATE_CATEGORIES` minus none. Keep each component under the CC cap: the page owns the mode machine, components are presentational.
- [ ] **Step 3: Run** → PASS; `task lint:frontend`.

### Task C4: Settings section and Meetings page toolbar

**Files:**
- Modify: `apps/web/src/components/settings/MeetingsSettings.tsx` (preferences: « Default minutes format » `Select` fed by `useMeetingTemplates` grouped with `SelectGroup`/`SelectLabel` per category, first option `auto`; `TemplateForm` removed; a short block « Templates » with count + `Button variant="outline"` « Manage my templates » → `/dashboard/meetings/templates`)
- Modify: `apps/web/src/app/[lng]/dashboard/meetings/page.tsx` (header → `SectionToolbar`: primary « Record a meeting » = `recorder.start()` from `useMeetingRecorderContext()` (hidden when the context is null), secondary « Templates » (pinned), count line; row meta shows `template_name`)
- Modify: `apps/web/src/lib/settings-search.ts` keywords ×6 (`settings.search.keywords.meetings` gains template words), six locales — `meetings.settings.default_template_label`, `default_template_auto`, `default_template_hint`, `templates_title`, `templates_count_one/_other`, `manage_templates`, `meetings.list.record`, `meetings.list.templates`, `meetings.list.format`
- Test: `MeetingsSettings.test.tsx` (rewrite the template block tests: select shows `auto` + grouped names, saving sends `default_template_ref`), `dashboard/meetings/__tests__/page.test.tsx` (toolbar names; « Record » calls `start`)

- [ ] **Step 1: Failing tests** as listed. - [ ] **Step 2: Implement.** - [ ] **Step 3: Run** → PASS; `pnpm exec tsc --noEmit --incremental false` clean (no consumer of the deleted hook remains).

### Task C5: Detail page — format fact, reformat dialog, pending panel, links

**Files:**
- Create: `apps/web/src/components/meetings/ReformatDialog.tsx` (`Dialog`; grouped `Select` of templates preselecting `meeting.template_ref`; radio group `mode` = `replace` | `new` (labels « Replace these minutes » / « New minutes from this transcript »); cost note; transcript warning when `isTranscriptTemplate`; primary « Reformat »)
- Create: `apps/web/src/components/meetings/MeetingPendingPanel.tsx` (`report === null && stage !== null` → progress « Writing the minutes »; `report === null && stage === null && last_error_code` → failed with « Try again » = `reformat({template_ref: meeting.template_ref, mode:'replace'})` and Delete)
- Modify: `apps/web/src/components/meetings/MeetingDetailPanels.tsx` (`MeetingFacts` + `Fact` « Format » = `template_name` + selection word, `title={template_selection_reason}`; toolbar: « Rebuild » (same template) and « Change the format… »; header: « From the same transcript as … » link when `source_meeting_id`, « N new minutes derived » when `derived_count > 0`)
- Modify: `apps/web/src/components/meetings/useMeetingActions.ts` (`reformat(request)`: on `new` → navigate to `/dashboard/meetings/${id}`; on `replace` → refetch), `apps/web/src/app/[lng]/dashboard/meetings/[id]/page.tsx` (renders `MeetingPendingPanel`, opens the dialog)
- Modify: six locales — `meetings.detail.format`, `format_selection.{auto,user,preference}`, `format_reason_title`, `rebuild`, `change_format`, `reformat.title/description/mode_replace/mode_new/cost_note/transcript_note/submit/started_new/started_replace`, `pending_title`, `pending_hint`, `pending_failed_title`, `try_again`, `derived_from`, `derived_count_one/_other`; `meetings.errors.template_locked`, `template_not_found`, `template_readonly`, `template_limit_reached`, `template_ref_invalid`, `regeneration_interrupted`
- Test: `ReformatDialog.test.tsx`, `MeetingPendingPanel.test.tsx`, `[id]/__tests__/page.test.tsx` (format fact text; dialog flow for both modes; pending panel; source link)

- [ ] **Step 1: Failing tests** as listed (dialog: keyboard focus lands on the select, Escape closes, submit disabled until a template differs or mode is `new`).
- [ ] **Step 2: Implement.** `MeetingDetailPanels.tsx` is a hotspot: the new `MeetingFormatFact` and the derived links go into `MeetingDetailLinks.tsx` rather than growing it.
- [ ] **Step 3: Run** → PASS; `pnpm cc:ratchet`.

### Task C6: Banner format select, i18n parity, frontend gates

**Files:**
- Modify: `apps/web/src/components/meetings/MeetingRecordingBanner.tsx` (`FormatSelect`: while `isLive`, a compact `Select` « Format: Automatic » fed by `useMeetingTemplates` (lazy: mounted only when the banner is) writing `meetingsApi.patch(recording.id, { template_ref })`; optimistic label; failure toast)
- Modify: six locales — `meetings.banner.format_label`, `format_auto`, `format_saved`
- Test: `MeetingRecordingBanner.test.tsx`

- [ ] **Step 1: Failing test** — the select appears only while live; choosing a template calls `patch` with the ref. - [ ] **Step 2: Implement.**
- [ ] **Step 3: Gates** — `task lint:i18n`; `task test:frontend:coverage` (thresholds hold); `task lint:frontend`; `pnpm a11y:ratchet && pnpm react-hooks:ratchet && pnpm cc:ratchet`.

---

## Part D — Knowledge spaces: download, archive, move, bulk delete

### Task D1: Backend document operations

**Files:**
- Modify: `apps/api/src/core/constants.py` (`RAG_SPACES_ARCHIVE_MAX_MB_DEFAULT = 200`, `RAG_SPACES_BULK_MAX = 100`), `apps/api/src/core/config/rag_spaces.py` (`rag_spaces_archive_max_mb`), `.env.example`
- Modify: `apps/api/src/domains/rag_spaces/schemas.py` (`RAGDocumentIdsRequest(ids: list[UUID] 1..100)`, `RAGDocumentMoveRequest(ids, target_space_id: UUID)`, `RAGBatchSkipped(id, code)`, `RAGDocumentBatchResponse(done: list[UUID], skipped: list[RAGBatchSkipped])`)
- Modify: `apps/api/src/domains/rag_spaces/repository.py` (`RAGChunkRepository.move_to_space(document_id, space_id) -> int`)
- Create: `apps/api/src/domains/rag_spaces/document_ops.py` (`document_file_path(document) -> Path`, `owned_document(service, space_id, document_id, user_id) -> RAGDocument`, `download_document(...) -> tuple[Path, RAGDocument]`, `build_archive(service, space_id, user_id, ids) -> tuple[Path, str]`, `move_documents(service, space_id, user_id, request) -> RAGDocumentBatchResponse`, `bulk_delete_documents(service, space_id, user_id, ids) -> RAGDocumentBatchResponse`)
- Modify: `apps/api/src/domains/rag_spaces/service.py` (`delete_document` and `get_document_status` use `owned_document` + `document_file_path`; the three duplicated checks go)
- Modify: `apps/api/src/domains/rag_spaces/router.py` (GET `/{space_id}/documents/archive` BEFORE `/{space_id}/documents/{document_id}/…`; GET `/{space_id}/documents/{document_id}/download`; POST `/{space_id}/documents/move`; POST `/{space_id}/documents/bulk-delete`)
- Test: `apps/api/tests/unit/domains/rag_spaces/test_document_ops.py`

**Interfaces:** refusal codes — `document_file_missing` (404), `archive_too_large` (413, `detail.max_mb`), `reindex_in_progress` (409), per-item skip codes `document_not_found`, `same_space`, `document_managed_by_drive`, `document_managed_by_meetings`, `document_busy`, `document_limit_exceeded`, `document_move_failed`, `delete_failed`.

- [ ] **Step 1: Failing tests** — `document_file_path` refuses a filename with `..` (RuntimeError) and builds `root/user/space/filename`; download 404 when the file is absent on disk; archive: names deduplicated `(2)`, a missing file listed in `_missing.txt`, total size over the setting → 413 with `max_mb`; move matrix (each skip code; `reindex_in_progress` refuses wholesale before any change; a happy move updates the row, calls `move_to_space`, commits, then renames the file — order asserted with a `MagicMock` call list; a rename `OSError` reverts `space_id` on row and chunks and reports `document_move_failed`); bulk delete reports per id.

- [ ] **Step 2: Implement** (`document_ops.py` ≈ 200 lines):

```python
def document_file_path(document: RAGDocument) -> Path:
    root = Path(settings.rag_spaces_storage_path).resolve()
    scope = (root / str(document.user_id) / str(document.space_id)).resolve()
    path = (scope / document.filename).resolve()
    if not path.is_relative_to(scope):
        raise RuntimeError("RAG storage path integrity violation")
    return path


async def move_documents(service, space_id, user_id, request) -> RAGDocumentBatchResponse:
    if (await get_reindex_status()).get("in_progress"):
        raise_reindex_in_progress()
    source = await service.get_space(space_id, user_id)
    target = await service.get_space(request.target_space_id, user_id)
    if target.is_system: raise_system_space_protected(target.id, "move")
    room = settings.rag_spaces_max_docs_per_space - await service.doc_repo.count_for_space(target.id)
    done, skipped = [], []
    for document_id in dict.fromkeys(request.ids):
        code = await _move_one(service, source, target, document_id, user_id, room_left=room - len(done))
        (done.append(document_id) if code is None else skipped.append(RAGBatchSkipped(id=document_id, code=code)))
    return RAGDocumentBatchResponse(done=done, skipped=skipped)
```

  `_move_one`: classify (`same_space`, `document_managed_by_drive`, `document_managed_by_meetings`, `document_busy` via `is_terminal_document_status`, `document_limit_exceeded` when `room_left <= 0`), then `old_path = document_file_path(document)`; `await doc_repo.update(document, {"space_id": target.id})`; `await chunk_repo.move_to_space(document.id, target.id)`; `await db.commit()`; `new_path = document_file_path(document)`; `await asyncio.to_thread(_rename, old_path, new_path)` (mkdir parents + `os.replace`); on `OSError` → revert both updates, commit, return `document_move_failed`. Archive: `tempfile.NamedTemporaryFile(delete=False, suffix=".zip")`, `asyncio.to_thread` of a sync builder writing `ZIP_DEFLATED` members named `original_filename` (dedup with ` (n)` before the suffix), `_missing.txt` when needed; response `FileResponse(path, media_type="application/zip", filename=f"{space.name}.zip", background=BackgroundTask(os.remove, path))` with the RFC 5987 header built like `meetings/router.py::download_pdf`.

- [ ] **Step 3: Run** → PASS. Gate: `pytest tests/unit/domains/rag_spaces -q`; `task lint:backend`; SLOC of `rag_spaces/service.py` must SHRINK (three checks removed).

### Task D2: Frontend — row actions, selection bar, move dialog

**Files:**
- Modify: `apps/web/src/types/rag-spaces.ts` (`RAGDocumentBatchResponse`, `RAGDocumentMoveRequest`), `apps/web/src/hooks/useSpaceDocuments.ts` (`moveDocuments(ids, targetSpaceId)`, `bulkDeleteDocuments(ids)`, `archiveHref(ids)`, `downloadHref(id)` via `apiEndpointUrl`)
- Modify: `apps/web/src/components/spaces/DocumentRow.tsx` (leading `Checkbox` with `spaces.documents.select_row`; `RowActions` menuLabel `spaces.documents.row_actions` with Download (an `<a>` — `RowActions` takes `onSelect`, so add an optional `href` to `RowAction` rendering `<Button asChild><a href download>` on `sm+` and `DropdownMenuItem asChild` below; both branches tested), Move… (only `source_type === 'upload'`), Delete)
- Create: `apps/web/src/components/spaces/DocumentSelectionBar.tsx`, `apps/web/src/components/spaces/MoveDocumentsDialog.tsx`
- Modify: `apps/web/src/app/[lng]/dashboard/spaces/[id]/page.tsx` (selection state keyed by document id, bar, dialog, toasts with done/skipped counts per code)
- Modify: `apps/web/src/components/ui/row-actions.tsx` (`href?: string` on `RowAction`)
- Modify: six locales — `spaces.documents.select_row`, `select_all`, `selected_count_one/_other`, `download`, `download_selected`, `move`, `move_selected`, `delete_selected`, `row_actions`, `move_dialog.title/description/target_label/submit/none_available`, `moved_one/_other`, `skipped_one/_other`, `skip.{same_space,document_managed_by_drive,document_managed_by_meetings,document_busy,document_limit_exceeded,document_move_failed,delete_failed,document_not_found}`, `errors.archive_too_large`, `errors.reindex_in_progress`, `errors.document_file_missing`
- Test: `DocumentRow.test.tsx` (create), `DocumentSelectionBar.test.tsx`, `MoveDocumentsDialog.test.tsx`, `apps/web/src/app/[lng]/dashboard/spaces/[id]/__tests__/page.test.tsx` (create), `ui/__tests__/row-actions.test.tsx` (extend for `href`)

- [ ] **Step 1: Failing tests** — row: names in en and fr for the three actions, Move absent on a drive row, Download `href` ends with `/documents/<id>/download`; bar: count, select all, archive link `href` carries `ids=` joined by commas, Move opens the dialog, Delete confirms; dialog: lists the other spaces with their document counts, submit disabled until a target is chosen, calls `moveDocuments`; page: after a move the toast states moved and skipped counts and the list refetches.
- [ ] **Step 2: Implement.** - [ ] **Step 3: Run** → PASS; `task lint:frontend`; `task lint:i18n`.

---

## Part E — Documentation, gates, review

### Task E1: ADR-259 and documentation

**Files:**
- Create: `docs/architecture/ADR-259-Meeting-Template-Library-And-Reformatting.md` (French, « Statut / Portée / Voisins », the measured facts of spec §1 first: no kind for a transcript, `max_tokens=8000`, sync SMTP in async, the stuck-regeneration gap, denormalized chunks)
- Modify: `docs/architecture/ADR_INDEX.md` (entry + count line), `docs/INDEX.md` (ADR count if quoted), `README.md` ADR count line (`task release:sync-counts`)
- Modify: `docs/technical/MEETINGS.md` (modules table + `template_catalogue`, `template_service`, `template_resolution`, `transcript_rewrite`, `reformat`, `bulk`; email paragraph; « Modèles » section: refs, categories, selection precedence, reformat replace/new; frontend table rows: library page, header control, mobile menu entry, sticky banner)
- Modify: `docs/guides/GUIDE_RAG_SPACES.md` (API table: download, archive, move, bulk-delete; frontend components)
- Modify: `docs/superpowers/specs/2026-09-02-meeting-recording-and-minutes-design.md` (§API table rows for `/template` → `/templates`, `/reformat`, `/bulk-delete`), link the new spec + ADR-259 from `MEETINGS.md`
- Modify: `.env.example` (§87 new keys with the ADR-258 comment style), `.env.prod.example`, `.env.min.prod` only if a key is mandatory (none is)

- [ ] **Step 1:** Write. - [ ] **Step 2: Gate** — `task lint:docs:preview` (0 broken link, 0 orphan, 0 fact drift), `task docs:sync-agents` if `CLAUDE.md` changed (it does not).

### Task E2: Full gates and review replay

- [ ] `task lint` (backend + frontend + i18n + docs + hygiene + ratchets).
- [ ] `task test:backend:unit:fast`; `task test:markers`; `pytest tests/unit/test_file_size_ratchet_guard.py tests/unit/test_metric_coverage_ratchet_guard.py tests/unit/test_no_hardcoded_timezone_guard.py tests/unit/test_jsonb_mutation_guard.py -q`.
- [ ] `task test:frontend:coverage` — thresholds unchanged or raised (owner rule: raise with ≥ 2 pts margin when the measurement allows).
- [ ] `task db:migrate:replay-check`.
- [ ] `tests/agents/` suite in the container (the runtime contract of `meetings` changed: `MeetingDetailResponse` fields).
- [ ] Runtime proofs (B7) plus the spaces proof: upload two files → archive → move one → `POST /chat` question answered from the target space only (retrieval log shows the target `space_id`).
- [ ] Replay the spec §5 test plan line by line; write the measured numbers into spec §8; update `MEMORY` (project file for this program).

---

## Self-review

- **Spec coverage**: A (A1), B (A2, A3), C (A4), D (A5), E.1–E.2 (B1, B2), E.3 (B2), E.4 (B3), E.5 (B4), E.6 (B6, C5, C6), E.7 (B5, C2), E.8 (C1–C6), F (D1, D2), §3 settings/metrics (B1, B4, D1), §4 edge cases (tests named in B3/B4/B6/D1), §5 (E2), §7 decisions (A5, B1 data step, B2 `auto_selectable`, C5 vocabulary « new minutes », D bulk delete included).
- **Placeholders**: none — every step names the code or the exact test assertions; the 23 remaining catalogue instructions are specified by source paragraph and bounds, checked by the completeness asserts of B2.
- **Type consistency**: `TemplateRef.parse/str`, `ResolvedTemplate`, `TemplateDecision`, `RAGDocumentBatchResponse`, `MeetingReformatRequest.mode = "replace" | "new"`, `RowAction.href` are used with the same names in every task that touches them.

---

## Execution log (2026-09-03, inline TDD)

- **Parts A, B, C, D and E1 delivered**, every task RED → GREEN with its named tests; gates green at the end of each part:
  `task lint:backend`, `task lint:frontend`, `task lint:i18n`, `task lint:docs:preview`, `task test:backend:unit:fast`
  (three guards adjusted deliberately: the demo public surface lists the four document routes, the derived counts were
  realigned by `task release:sync-counts`, `AGENTS.md` resynchronised), `task test:frontend:coverage` (the `stores/**` 100 %
  branch threshold required covering `setTemplateRef`), the a11y / react-hooks / CC ratchets, `task db:migrate:replay-check`.
- **Deviations from the plan, each for a measured reason**: `SectionToolbar` gained `blocked` (aria-disabled + handler guard)
  because `disabled` removes a focused control from the tab order and hides the reason with the click; the selection bar
  became a shared primitive (`ui/selection-bar.tsx`, `lib/selection.ts`) instead of a second copy; `document_access.py` holds
  the path builder and the ownership check so `service.py` shrank (7 insertions, 29 deletions) without an import cycle;
  the banner's format choice is persisted in the recorder store (`templateRef`) so a reload shows what the server holds.
- **E2 (runtime proof)**: `scratchpad/proof_adr259.py` + `smtp_sink.py`; the dev API container went zombie during the run
  (see the memory file for the recovery) — results recorded in spec §8.
- **`tests/agents/` in the container** (after the pyc fix and a Windows reboot): 1 130 passed, 1 skipped, **32 failed — every one
  a `401 Incorrect API key provided: NOT_CONFIGURED`** from `test_hitl_classifier.py` / `test_hitl_cache_integration.py`, which
  call OpenAI with the dev `.env` placeholder key (the real keys of this instance live in the database). Not touched by this
  program; the meetings runtime contract change broke nothing there.
- **Owner review of the library (2026-09-03, afternoon)** applied in TDD: header icon-only personality selector, the two-section
  library (folded categories, category glyphs, themed titles, per-section selection bars), template batches
  (`template_bulk.py`, `bulk-duplicate` / `bulk-delete`, numbered names, `preference_reset` surfaced), picker headings set apart,
  « Mes modèles personnalisés ». **Cold adversarial review afterwards** found and fixed four things: a second « add » could be
  fired while a batch ran (guard), the fetched row lost its spinner in the recomposition (`busyRef` back), the format dialog showed
  a blank trigger on a meeting recorded before ADR-259 (`placeholder`), a failed archive write left its temporary file
  (`document_ops._write_archive` cleans up) — plus a duplicated « skipped » sentence builder folded into `lib/batch-report.ts`, and
  a brand-new template's section keys now derived from the headings typed (`rederiveSectionKeys`). Gates after: 20 885 backend
  unit tests, full `task lint:frontend`, 180 meetings/spaces frontend tests, i18n parity.
- **Ratchets raised** (owner rule: ≥ 2 pts margin): frontend global floors 75/70/72/76 → **76/71/73/76** (measured
  78.07 / 73.38 / 75.25 / 78.82); backend `--cov-fail-under` 68 → **69** (measured 71.13 % on the CI command), quoted values
  realigned by `task docs:fix-facts` and `docs:sync-agents`. A lost file no longer blocks a document move (the index is what
  retrieval reads; the download says `document_file_missing` as before).

