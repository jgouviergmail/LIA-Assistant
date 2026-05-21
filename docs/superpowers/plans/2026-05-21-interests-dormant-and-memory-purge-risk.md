# Interests Dormant Visibility & Memory Purge-Risk Exposure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project git rule (overrides skill default):** Do NOT run any `git` command. Where a task ends with a "Checkpoint", run the verification and then *propose* a commit to the user — never commit/push without explicit approval.
>
> **Validation rule:** Never validate via a local `pnpm`/`pytest` server outside Docker for the frontend; backend unit tests run via the host `.venv` as the pre-commit hook does. Always verify Docker app startup before declaring done.

**Goal:** Make dormant interests visible/controllable (with a Reactivate action) and surface memory purge-risk (read-only), with strictly zero regression on existing behavior.

**Architecture:** Two independent phases. Phase A (Interests) is backend + frontend + i18n, no new pure-logic module. Phase B (Memories) extracts the existing retention scoring into a pure domain module reused by both the scheduler and the API, then exposes a computed `purge_risk` on the read model. No database migration in either phase — all columns already exist.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest (`asyncio_mode = "auto"`), Next.js 16 / React 19 / TypeScript, react-i18next, structlog.

**Spec:** `docs/superpowers/specs/2026-05-21-interests-dormant-and-memory-purge-risk-design.md`

---

## Scope Note

Phases A and B are independent and each produces working, testable software on its own. They may be executed/committed separately. Within each phase, backend tasks precede the frontend tasks that consume them.

## File Structure

### Phase A — Interests
- `apps/api/src/core/constants.py` — **modify**: add initial-signal constants.
- `apps/api/src/domains/interests/repository.py` — **modify**: `reactivate()`; `create()` uses constants.
- `apps/api/src/domains/interests/schemas.py` — **modify**: `dormant_count` on `InterestListResponse`.
- `apps/api/src/core/i18n_api_messages.py` — **modify**: two new error messages.
- `apps/api/src/domains/interests/router.py` — **modify**: `dormant_count` in list; `POST /{id}/reactivate`.
- `apps/api/tests/unit/domains/interests/test_repository_reactivate.py` — **create**: repo unit test.
- `apps/api/tests/unit/domains/interests/test_router_reactivate.py` — **create**: route guard unit test.
- `apps/web/src/hooks/useInterests.ts` — **modify**: `dormantCount`, `reactivateInterest`.
- `apps/web/src/components/settings/InterestsSettings.tsx` — **modify**: dormant section, counter.
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — **modify**: `interests.*` keys.

### Phase B — Memories
- `apps/api/src/core/constants.py` — **modify**: `MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT`.
- `apps/api/src/core/config/agents.py` — **modify**: `memory_purge_at_risk_margin` setting + import.
- `apps/api/src/domains/memories/models.py` — **modify**: add `PurgeRiskLevel` str-Enum (risk states).
- `apps/api/src/domains/memories/retention.py` — **create**: pure scoring module (`calculate_retention_score`, `should_purge` moved verbatim; `RetentionConfig`, `classify_purge_risk` new).
- `apps/api/src/infrastructure/scheduler/memory_cleanup.py` — **modify**: import from `retention.py`, delete local defs.
- `apps/api/src/domains/memories/schemas.py` — **modify**: `retention_score`, `purge_risk` on `MemoryResponse`.
- `apps/api/src/domains/memories/router.py` — **modify**: build config, thread `(now, config)` into `_memory_to_response`.
- `apps/api/tests/unit/domains/memories/test_retention.py` — **create** (moved from `tests/unit/infrastructure/scheduler/test_memory_cleanup.py`, which is deleted) + `classify_purge_risk` tests.
- `apps/api/.env.example`, `apps/api/.env.prod.example` — **modify**: `MEMORY_PURGE_AT_RISK_MARGIN`.
- `apps/web/src/hooks/useMemories.ts` — **modify**: `Memory` type fields.
- `apps/web/src/components/settings/MemorySettings.tsx` — **modify**: risk badge/tooltip.
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — **modify**: `memories.*` keys.

---

# PHASE A — Interests Dormant Section

## Task A1: Initial-signal constants

**Files:**
- Modify: `apps/api/src/core/constants.py` (near line 1386, the interest priors)

- [ ] **Step 1: Add constants**

In `apps/api/src/core/constants.py`, immediately after the existing
`INTEREST_PRIOR_BETA = 1` line (line 1387), add:

```python
# Initial signal counters for a new (or reactivated) interest.
# A reactivated interest is reset to these values so it behaves as brand-new.
INTEREST_INITIAL_POSITIVE_SIGNALS = 1
INTEREST_INITIAL_NEGATIVE_SIGNALS = 0
```

- [ ] **Step 2: Checkpoint**

Run: `cd apps/api && .venv/Scripts/python -c "from src.core.constants import INTEREST_INITIAL_POSITIVE_SIGNALS, INTEREST_INITIAL_NEGATIVE_SIGNALS; print(INTEREST_INITIAL_POSITIVE_SIGNALS, INTEREST_INITIAL_NEGATIVE_SIGNALS)"`
Expected: `1 0`. Then propose a commit to the user.

---

## Task A2: `InterestRepository.reactivate()`

**Files:**
- Modify: `apps/api/src/domains/interests/repository.py`
- Test: `apps/api/tests/unit/domains/interests/test_repository_reactivate.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/domains/interests/test_repository_reactivate.py`:

```python
"""Unit tests for InterestRepository.reactivate (reset-to-fresh)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository


def _dormant_interest() -> UserInterest:
    interest = UserInterest(
        user_id=uuid.uuid4(),
        topic="machine learning",
        category="technology",
        positive_signals=7,
        negative_signals=4,
        status=InterestStatus.DORMANT.value,
        last_mentioned_at=datetime.now(UTC) - timedelta(days=60),
    )
    interest.id = uuid.uuid4()
    interest.dormant_since = datetime.now(UTC) - timedelta(days=30)
    interest.last_notified_at = datetime.now(UTC) - timedelta(days=40)
    return interest


@pytest.mark.unit
async def test_reactivate_resets_to_fresh_state():
    db = AsyncMock()
    repo = InterestRepository(db)
    interest = _dormant_interest()

    await repo.reactivate(interest)

    assert interest.status == InterestStatus.ACTIVE.value
    assert interest.positive_signals == 1
    assert interest.negative_signals == 0
    assert interest.dormant_since is None
    assert interest.last_notified_at is None
    assert (datetime.now(UTC) - interest.last_mentioned_at).total_seconds() < 5
    db.flush.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/test_repository_reactivate.py -v`
Expected: FAIL — `AttributeError: 'InterestRepository' object has no attribute 'reactivate'`.

- [ ] **Step 3: Implement `reactivate` and refactor `create`**

In `apps/api/src/domains/interests/repository.py`, update the imports from constants
(the block currently importing `INTEREST_ACTIVE_LIST_LIMIT`, `INTEREST_USER_LIST_LIMIT`):

```python
from src.core.constants import (
    INTEREST_ACTIVE_LIST_LIMIT,
    INTEREST_INITIAL_NEGATIVE_SIGNALS,
    INTEREST_INITIAL_POSITIVE_SIGNALS,
    INTEREST_USER_LIST_LIMIT,
)
```

In `create()`, replace the literal signal values:

```python
        interest = UserInterest(
            user_id=user_id,
            topic=topic,
            category=category,
            positive_signals=INTEREST_INITIAL_POSITIVE_SIGNALS,
            negative_signals=INTEREST_INITIAL_NEGATIVE_SIGNALS,
            status=InterestStatus.ACTIVE.value,
            last_mentioned_at=datetime.now(UTC),
            embedding=embedding,
        )
```

Add the `reactivate` method (place it right after `mark_dormant`):

```python
    async def reactivate(
        self,
        interest: UserInterest,
        now: datetime | None = None,
    ) -> UserInterest:
        """Reactivate a dormant interest by resetting it to a fresh state.

        Mirrors the initial state set by ``create()``: signal counters reset,
        status returns to ACTIVE, and ``last_mentioned_at`` is refreshed so the
        nightly cleanup will not immediately re-dormant it (a fresh interest's
        effective weight is ~0.75, above the 0.5 dormancy threshold). The topic,
        category, and embedding are preserved.

        Args:
            interest: UserInterest to reactivate.
            now: Current datetime (defaults to UTC now).

        Returns:
            The reactivated UserInterest.
        """
        now = now or datetime.now(UTC)
        interest.positive_signals = INTEREST_INITIAL_POSITIVE_SIGNALS
        interest.negative_signals = INTEREST_INITIAL_NEGATIVE_SIGNALS
        interest.status = InterestStatus.ACTIVE.value
        interest.last_mentioned_at = now
        interest.last_notified_at = None
        interest.dormant_since = None

        await self.db.flush()

        logger.info(
            "interest_reactivated",
            interest_id=str(interest.id),
            user_id=str(interest.user_id),
        )
        return interest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/test_repository_reactivate.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/ -v`
Expected: all green (existing interest tests unaffected). Propose a commit to the user.

---

## Task A3: `dormant_count` on the list schema

**Files:**
- Modify: `apps/api/src/domains/interests/schemas.py`

- [ ] **Step 1: Add the field**

In `InterestListResponse`, add `dormant_count` (default `0` for backward compatibility):

```python
class InterestListResponse(BaseModel):
    """List of interests with metadata."""

    interests: list[InterestResponse]
    total: int
    active_count: int
    blocked_count: int
    dormant_count: int = 0
```

- [ ] **Step 2: Checkpoint**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/test_schemas.py -v`
Expected: PASS (additive field with default does not break existing schema tests). Propose a commit.

---

## Task A4: Reactivate endpoint + `dormant_count` in list

**Files:**
- Modify: `apps/api/src/core/i18n_api_messages.py`
- Modify: `apps/api/src/domains/interests/router.py`
- Test: `apps/api/tests/unit/domains/interests/test_router_reactivate.py`

- [ ] **Step 1: Add backend i18n messages**

In `apps/api/src/core/i18n_api_messages.py`, add two static methods next to the other
interest messages (after `failed_to_delete_interest`), mirroring the existing pattern
(note the `zh-CN` key):

```python
    @staticmethod
    def interest_not_dormant(language: SupportedLanguage = "fr") -> str:
        """Error - interest is not dormant (cannot reactivate)."""
        messages = {
            "fr": "Ce centre d'intérêt n'est pas en sommeil",
            "en": "This interest is not dormant",
            "es": "Este interés no está inactivo",
            "de": "Dieses Interesse ist nicht im Ruhezustand",
            "it": "Questo interesse non è in pausa",
            "zh-CN": "此兴趣未处于休眠状态",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_reactivate_interest(language: SupportedLanguage = "fr") -> str:
        """Error - failed to reactivate interest."""
        messages = {
            "fr": "Échec de la réactivation du centre d'intérêt",
            "en": "Failed to reactivate interest",
            "es": "Error al reactivar el interés",
            "de": "Interesse konnte nicht reaktiviert werden",
            "it": "Impossibile riattivare l'interesse",
            "zh-CN": "重新激活兴趣失败",
        }
        return messages.get(language, messages["en"])
```

- [ ] **Step 2: Add `dormant_count` to `list_interests`**

In `apps/api/src/domains/interests/router.py`, inside `list_interests`, add the dormant
count next to the existing counts and pass it to the response:

```python
        active_count = sum(1 for i in items if i.status == InterestStatus.ACTIVE)
        blocked_count = sum(1 for i in items if i.status == InterestStatus.BLOCKED)
        dormant_count = sum(1 for i in items if i.status == InterestStatus.DORMANT)
```

```python
        return InterestListResponse(
            interests=items,
            total=len(items),
            active_count=active_count,
            blocked_count=blocked_count,
            dormant_count=dormant_count,
        )
```

- [ ] **Step 3: Write the failing route-guard test**

Create `apps/api/tests/unit/domains/interests/test_router_reactivate.py`:

```python
"""Unit tests for the reactivate route guards (ownership + status)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.router import reactivate_interest


def _interest(status: str, owner_id: uuid.UUID) -> UserInterest:
    interest = UserInterest(
        user_id=owner_id,
        topic="ml",
        category="technology",
        positive_signals=1,
        negative_signals=0,
        status=status,
        last_mentioned_at=datetime.now(UTC),
    )
    interest.id = uuid.uuid4()
    return interest


@pytest.mark.unit
async def test_reactivate_rejects_non_dormant_with_conflict():
    user = MagicMock()
    user.id = uuid.uuid4()
    db = AsyncMock()
    interest = _interest(InterestStatus.ACTIVE.value, user.id)

    with patch("src.domains.interests.router.InterestRepository") as mock_repo_cls:
        repo = mock_repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=interest)
        with pytest.raises(ResourceConflictError):
            await reactivate_interest(interest_id=interest.id, user=user, db=db)


@pytest.mark.unit
async def test_reactivate_rejects_foreign_interest_with_not_found():
    user = MagicMock()
    user.id = uuid.uuid4()
    db = AsyncMock()
    interest = _interest(InterestStatus.DORMANT.value, owner_id=uuid.uuid4())

    with patch("src.domains.interests.router.InterestRepository") as mock_repo_cls:
        repo = mock_repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=interest)
        with pytest.raises(ResourceNotFoundError):
            await reactivate_interest(interest_id=interest.id, user=user, db=db)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/test_router_reactivate.py -v`
Expected: FAIL — `ImportError: cannot import name 'reactivate_interest'`.

- [ ] **Step 5: Implement the endpoint**

In `apps/api/src/domains/interests/router.py`, add this route after `submit_feedback`
(`ResourceConflictError`, `ResourceNotFoundError`, `raise_interest_not_found`,
`raise_interest_store_error`, and `APIMessages` are already imported):

```python
@router.post(
    "/{interest_id}/reactivate",
    response_model=InterestResponse,
    status_code=status.HTTP_200_OK,
    summary="Reactivate a dormant interest",
    description="Reactivate a dormant interest, resetting its signals to a fresh state.",
)
async def reactivate_interest(
    interest_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestResponse:
    """Reactivate a dormant interest (reset counters to a fresh state).

    Args:
        interest_id: UUID of the interest to reactivate.
        user: Authenticated owner (injected).
        db: Database session (injected).

    Returns:
        The reactivated interest as an ``InterestResponse``.

    Raises:
        ResourceNotFoundError: If the interest is missing or not owned by the user.
        ResourceConflictError: If the interest is not in the ``dormant`` status.
    """
    try:
        repo = InterestRepository(db)
        interest = await repo.get_by_id(interest_id)

        if not interest or interest.user_id != user.id:
            raise_interest_not_found(interest_id)

        if interest.status != InterestStatus.DORMANT.value:
            raise ResourceConflictError(
                resource_type="interest",
                detail=APIMessages.interest_not_dormant(),
            )

        await repo.reactivate(interest)
        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_reactivated",
            user_id=str(user.id),
            interest_id=str(interest_id),
        )

        return _interest_to_response(interest, repo)

    except (ResourceNotFoundError, ResourceConflictError):
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_reactivate_failed",
            user_id=str(user.id),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="reactivate",
            detail=APIMessages.failed_to_reactivate_interest(),
            interest_id=str(interest_id),
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/test_router_reactivate.py -v`
Expected: PASS (both guards).

- [ ] **Step 7: Checkpoint**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/interests/ -v`
Expected: all green. Propose a commit.

---

## Task A5: Interests i18n keys (6 languages)

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`

- [ ] **Step 1: Add keys under the `interests` namespace in each locale**

Add the following keys (values per language). Keep alphabetical/section ordering consistent
with the surrounding keys in each file.

| key | en | fr | de | es | it | zh |
|-----|----|----|----|----|----|----|
| `interests.dormant_section` | Dormant | En sommeil | Im Ruhezustand | Inactivos | In pausa | 休眠 |
| `interests.dormant_badge` | Dormant | En sommeil | Ruhend | Inactivo | In pausa | 休眠 |
| `interests.reactivate` | Reactivate | Réactiver | Reaktivieren | Reactivar | Riattiva | 重新激活 |
| `interests.reactivate_success` | Interest reactivated | Centre d'intérêt réactivé | Interesse reaktiviert | Interés reactivado | Interesse riattivato | 兴趣已重新激活 |
| `interests.reactivate_error` | Failed to reactivate | Échec de la réactivation | Reaktivierung fehlgeschlagen | Error al reactivar | Riattivazione non riuscita | 重新激活失败 |
| `interests.active` | active | actifs | aktiv | activos | attivi | 活跃 |
| `interests.dormant` | dormant | en sommeil | ruhend | inactivos | in pausa | 休眠 |

- [ ] **Step 2: Checkpoint (i18n parity)**

Run the i18n parity check (the pre-commit hook script). From repo root:
`task lint:frontend` (or the i18n parity script invoked by `task pre-commit`).
Expected: no missing/extra keys reported. Propose a commit.

---

## Task A6: `useInterests` hook — dormantCount + reactivate

**Files:**
- Modify: `apps/web/src/hooks/useInterests.ts`

- [ ] **Step 1: Add `dormant_count` to the response type**

In `InterestListResponse`:

```typescript
export interface InterestListResponse {
  interests: Interest[];
  total: number;
  active_count: number;
  blocked_count: number;
  dormant_count: number;
}
```

Update the `useApiQuery` `initialData` to include `dormant_count: 0`:

```typescript
    initialData: { interests: [], total: 0, active_count: 0, blocked_count: 0, dormant_count: 0 },
```

- [ ] **Step 2: Add the reactivate mutation and action**

After the feedback mutation block, add:

```typescript
  // Reactivate mutation
  const { mutate: reactivateMutate, loading: reactivating } = useApiMutation<
    Record<string, never>,
    Interest
  >({
    method: 'POST',
    componentName: 'useInterests',
  });
```

After `submitFeedback`, add the action:

```typescript
  /**
   * Reactivate a dormant interest (reset to a fresh active state).
   */
  const reactivateInterest = useCallback(
    async (interestId: string) => {
      const result = await reactivateMutate(`/interests/${interestId}/reactivate`, {});

      setData(prev => {
        if (!prev) return prev;
        const newInterests = prev.interests.map(i =>
          i.id === interestId && result ? result : i
        );
        return {
          ...prev,
          interests: newInterests,
          active_count: newInterests.filter(i => i.status === 'active').length,
          dormant_count: newInterests.filter(i => i.status === 'dormant').length,
        };
      });
    },
    [reactivateMutate, setData]
  );
```

- [ ] **Step 3: Expose `dormantCount`, `reactivateInterest`, `reactivating` in the return**

In the returned object add:

```typescript
    dormantCount: interestsData?.dormant_count ?? 0,
    reactivating,
    reactivateInterest,
```

- [ ] **Step 4: Checkpoint (typecheck in Docker)**

Verify TypeScript compiles in the dev container:
`docker exec lia-web-dev pnpm tsc --noEmit`
Expected: no errors. Propose a commit.

---

## Task A7: `InterestsSettings.tsx` — dormant section + counter

**Files:**
- Modify: `apps/web/src/components/settings/InterestsSettings.tsx`

- [ ] **Step 1: Import the `Moon` and `RotateCcw` icons**

Extend the lucide import line:

```typescript
import { Sparkles, Trash2, Plus, Ban, Clock, Pencil, Download, Moon, RotateCcw } from 'lucide-react';
```

- [ ] **Step 2: Pull the new hook values**

In the `useInterests()` destructure, add `dormantCount`, `reactivating`, `reactivateInterest`:

```typescript
  const {
    interests,
    total,
    blockedCount,
    dormantCount,
    categories,
    settings,
    loading,
    settingsLoading,
    creating,
    deleting,
    deletingAll,
    submittingFeedback,
    updatingSettings,
    updating,
    reactivating,
    createInterest,
    deleteInterest,
    deleteAllInterests,
    submitFeedback,
    updateSettings,
    updateInterest,
    reactivateInterest,
  } = useInterests();
```

- [ ] **Step 3: Compute the dormant list and a reactivate handler**

After the `blockedInterests` memo, add:

```typescript
  // Dormant interests (separate section, distinct style)
  const dormantInterests = useMemo(
    () => sortedInterests.filter(i => i.status === 'dormant'),
    [sortedInterests]
  );
```

Near the other handlers (after `handleFeedback`), add:

```typescript
  const handleReactivate = async (interest: Interest) => {
    try {
      await reactivateInterest(interest.id);
      toast.success(t('interests.reactivate_success'));
    } catch {
      toast.error(t('interests.reactivate_error'));
    }
  };
```

- [ ] **Step 4: Update the counter line**

Replace the stats block content (the `<div className="text-sm text-muted-foreground">` that
currently shows `total` + blocked) with the active/dormant/blocked breakdown:

```tsx
            <div className="text-sm text-muted-foreground">
              {total} {t('interests.count', { count: total })}
              <span className="ml-2 text-xs">
                ({total - dormantCount - blockedCount} {t('interests.active')}
                {dormantCount > 0 && (
                  <>
                    {' · '}
                    {dormantCount} {t('interests.dormant')}
                  </>
                )}
                {blockedCount > 0 && (
                  <>
                    {' · '}
                    {blockedCount} {t('interests.blocked')}
                  </>
                )}
                )
              </span>
            </div>
```

- [ ] **Step 5: Add the dormant `AccordionItem`**

Inside the `<Accordion>`, **between** the `groupedByCategory` map and the blocked section,
insert:

```tsx
              {/* Dormant Interests */}
              {dormantInterests.length > 0 && (
                <AccordionItem value="dormant" className="border rounded-lg px-3">
                  <AccordionTrigger className="py-3 hover:no-underline">
                    <div className="flex items-center gap-2">
                      <Moon className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium text-muted-foreground">
                        {t('interests.dormant_section')}
                      </span>
                      <span className="text-muted-foreground text-sm">
                        ({dormantInterests.length})
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 opacity-70">
                      {dormantInterests.map(interest => (
                        <div
                          key={interest.id}
                          className="group flex items-center gap-3 rounded-lg border border-dashed p-3 bg-muted/20"
                        >
                          <span className="text-lg shrink-0">
                            {INTEREST_CATEGORY_ICONS[interest.category]}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{interest.topic}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <Badge variant="outline" className="text-xs">
                                <Moon className="h-3 w-3 mr-1" />
                                {t('interests.dormant_badge')}
                              </Badge>
                            </div>
                          </div>
                          <div className="flex gap-1 shrink-0">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleReactivate(interest)}
                              disabled={reactivating}
                              title={t('interests.reactivate')}
                            >
                              <RotateCcw className="h-4 w-4 text-primary" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleOpenEdit(interest)}
                              disabled={updating}
                              title={t('interests.edit')}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setPendingDelete(interest)}
                              disabled={deleting}
                              title={t('interests.delete')}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              )}
```

- [ ] **Step 6: Checkpoint (typecheck + frontend unit suite in Docker)**

Run: `docker exec lia-web-dev pnpm tsc --noEmit`
Then: `docker exec lia-web-dev pnpm test`
Expected: typecheck clean, existing vitest suite green. Propose a commit.

---

## Task A8: Phase A runtime verification

- [ ] **Step 1: Backend fast unit + agents suites**

Run: `cd apps/api && .venv/Scripts/pytest -m "unit and not integration" -q`
Then: `task test:backend:agents`
Expected: all green, **no pre-existing assertions modified**.

- [ ] **Step 2: Verify Docker app startup**

Restart the API container and confirm clean startup (router wiring picks up the new route):
`docker compose restart api` then check logs for a clean boot and the route registered.
Expected: no startup errors; `POST /api/v1/interests/{id}/reactivate` available.

- [ ] **Step 3: Checkpoint** — propose a commit for Phase A.

---

# PHASE B — Memory Purge-Risk Exposure

## Task B1: Margin constant + setting

**Files:**
- Modify: `apps/api/src/core/constants.py` (near `MEMORY_PURGE_THRESHOLD_DEFAULT`, line 1838)
- Modify: `apps/api/src/core/config/agents.py`
- Modify: `apps/api/.env.example`, `apps/api/.env.prod.example`

- [ ] **Step 1: Add the constant**

In `apps/api/src/core/constants.py`, right after `MEMORY_PURGE_THRESHOLD_DEFAULT = 0.5`:

```python
MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT = 0.1  # Score band above purge threshold flagged "at risk" (UI hint only)
```

- [ ] **Step 2: Import it in the config module**

In `apps/api/src/core/config/agents.py`, add `MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT` to the
existing constants import block (alongside `MEMORY_PURGE_THRESHOLD_DEFAULT`).

- [ ] **Step 3: Add the setting**

Immediately after the `memory_purge_threshold` field (ends line 1743), add:

```python
    memory_purge_at_risk_margin: float = Field(
        default=MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Score band above the purge threshold within which a memory is flagged "
            "'at_risk' in the API (read-only UI hint). Does not affect purge decisions."
        ),
    )
```

- [ ] **Step 4: Document the env var**

In `apps/api/.env.example` and `apps/api/.env.prod.example`, near the other `MEMORY_PURGE_*`
entries, add:

```
MEMORY_PURGE_AT_RISK_MARGIN=0.1
```

- [ ] **Step 5: Checkpoint**

Run: `cd apps/api && .venv/Scripts/python -c "from src.core.config import settings; print(settings.memory_purge_at_risk_margin)"`
Expected: `0.1`. Propose a commit.

---

## Task B2: Pure retention module + moved tests + classify

**Files:**
- Create: `apps/api/src/domains/memories/retention.py`
- Modify: `apps/api/src/infrastructure/scheduler/memory_cleanup.py`
- Create: `apps/api/tests/unit/domains/memories/test_retention.py`
- Delete: `apps/api/tests/unit/infrastructure/scheduler/test_memory_cleanup.py`

- [ ] **Step 1: Add the `PurgeRiskLevel` enum, then create `retention.py`**

First, in `apps/api/src/domains/memories/models.py`, next to `MemoryCategory`, add (mirrors the
existing str-Enum pattern; `Enum` is already imported in that file):

```python
class PurgeRiskLevel(str, Enum):
    """Auto-purge risk classification for a memory (read-only, computed).

    Not persisted — derived at request time from the retention score. Mirrors
    the str-Enum pattern used by ``MemoryCategory`` so it serializes to its
    value in API responses.
    """

    PROTECTED = "protected"  # pinned: never auto-purged
    SAFE = "safe"  # not eligible (grace) or comfortably above threshold
    AT_RISK = "at_risk"  # eligible and close to the purge threshold
    IMMINENT = "imminent"  # eligible and below threshold (purged next run)
```

Then create `apps/api/src/domains/memories/retention.py` with the full content below. The two
functions `calculate_retention_score` and `should_purge` are unchanged from `memory_cleanup.py`
(verify arithmetic matches the current implementation); `RetentionConfig` and
`classify_purge_risk` are new:

```python
"""Pure retention-scoring logic for memories.

These functions are I/O-free and shared by:
- the daily cleanup scheduler (purge decision), and
- the memories API (read-only purge-risk exposure).

Moved out of infrastructure/scheduler/memory_cleanup.py so the domain/API can
reuse them without an infrastructure dependency.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domains.memories.models import Memory, PurgeRiskLevel


def calculate_retention_score(
    memory: Memory,
    now: datetime,
    recency_decay_days: int,
    usage_penalty_age_days: int,
    usage_penalty_factor: float,
    weight_importance: float,
    weight_recency: float,
) -> float:
    """Calculate retention score for a memory (0-1).

    Higher score = higher chance of being kept.

    Formula:
        score = weight_importance * importance + weight_recency * recency_factor
        recency_factor = max(0, 1 - age_days / recency_decay_days)

    Negative penalty:
        if usage_count == 0 and age_days > usage_penalty_age_days:
            score *= usage_penalty_factor
    """
    importance_boost = memory.importance or 0.7

    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        recency_boost = max(0.0, 1.0 - age_days / max(1, recency_decay_days))
    else:
        age_days = 0
        recency_boost = 0.5  # Default if no date

    score = weight_importance * importance_boost + weight_recency * recency_boost

    # Negative penalty for never-activated memories past grace period
    if age_days > usage_penalty_age_days and (memory.usage_count or 0) == 0:
        score *= usage_penalty_factor

    return float(score)


def should_purge(
    memory: Memory,
    now: datetime,
    min_age_for_cleanup_days: int,
    recency_decay_days: int,
    usage_penalty_age_days: int,
    usage_penalty_factor: float,
    purge_threshold: float,
    weight_importance: float,
    weight_recency: float,
) -> tuple[bool, float]:
    """Determine if a memory should be purged.

    Protection rules (never purged):
    1. pinned = True (user-locked)
    2. Age < min_age_for_cleanup_days (grace period)

    If none of the above, purge if retention_score < purge_threshold.

    Returns:
        Tuple of (should_purge, retention_score).
    """
    # Protection 1: Pinned
    if memory.pinned:
        return False, 1.0

    # Protection 2: Grace period not yet elapsed
    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        if age_days < min_age_for_cleanup_days:
            return False, 1.0  # Not yet eligible

    retention_score = calculate_retention_score(
        memory,
        now,
        recency_decay_days,
        usage_penalty_age_days,
        usage_penalty_factor,
        weight_importance,
        weight_recency,
    )

    return retention_score < purge_threshold, retention_score


@dataclass(frozen=True)
class RetentionConfig:
    """Frozen snapshot of retention settings for a single request or job.

    Attributes:
        min_age_for_cleanup_days: Grace period before a memory is purge-eligible.
        recency_decay_days: Horizon over which the recency factor decays to 0.
        usage_penalty_age_days: Age past which a zero-usage memory is penalized.
        usage_penalty_factor: Multiplier applied when the zero-usage penalty triggers.
        purge_threshold: Score below which an eligible memory is purged.
        at_risk_margin: Band above the threshold flagged as ``at_risk`` (UI hint only).
        weight_importance: Weight of the importance component in the score.
        weight_recency: Weight of the recency component in the score.
    """

    min_age_for_cleanup_days: int
    recency_decay_days: int
    usage_penalty_age_days: int
    usage_penalty_factor: float
    purge_threshold: float
    at_risk_margin: float
    weight_importance: float
    weight_recency: float


def classify_purge_risk(
    memory: Memory,
    now: datetime,
    config: RetentionConfig,
) -> tuple[PurgeRiskLevel, float | None]:
    """Classify a memory's purge risk and return (risk, retention_score).

    States (evaluated in order):
    - PROTECTED: pinned (never auto-purged) — score None.
    - SAFE (grace): age < min_age_for_cleanup_days — score None (not yet eligible).
    - IMMINENT: eligible and score < purge_threshold (would be deleted next run).
    - AT_RISK: eligible and purge_threshold <= score < purge_threshold + at_risk_margin.
    - SAFE: eligible and score >= purge_threshold + at_risk_margin.

    Does NOT call should_purge (which short-circuits the score to 1.0 for
    pinned/grace); computes the real score directly so it can be exposed.

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        config: Retention configuration snapshot.

    Returns:
        Tuple of (purge_risk, retention_score). retention_score is None for
        pinned memories and for memories still within the grace period.
    """
    if memory.pinned:
        return PurgeRiskLevel.PROTECTED, None

    created_at = memory.created_at
    age_days = (now - created_at).days if created_at else 0
    if age_days < config.min_age_for_cleanup_days:
        return PurgeRiskLevel.SAFE, None

    score = calculate_retention_score(
        memory,
        now,
        config.recency_decay_days,
        config.usage_penalty_age_days,
        config.usage_penalty_factor,
        config.weight_importance,
        config.weight_recency,
    )

    if score < config.purge_threshold:
        return PurgeRiskLevel.IMMINENT, score
    if score < config.purge_threshold + config.at_risk_margin:
        return PurgeRiskLevel.AT_RISK, score
    return PurgeRiskLevel.SAFE, score
```

After creating the module, diff the two moved functions against the originals in
`memory_cleanup.py` to confirm the arithmetic (importance/recency/penalty and the pinned/grace
short-circuits) is identical — this is what guarantees zero behavioral change.

- [ ] **Step 2: Update `memory_cleanup.py` to import from the new module**

In `apps/api/src/infrastructure/scheduler/memory_cleanup.py`:
- Delete the local `calculate_retention_score` and `should_purge` definitions (lines 42-153).
- Add the import near the other domain imports:

```python
from src.domains.memories.retention import should_purge
```

(`cleanup_memories` only calls `should_purge`; `calculate_retention_score` is used internally
by `should_purge` inside `retention.py`, so it is not imported here — avoids an unused import.)

- [ ] **Step 3: Move the test file and add classify tests**

Delete `apps/api/tests/unit/infrastructure/scheduler/test_memory_cleanup.py`.
Create `apps/api/tests/unit/domains/memories/test_retention.py` with the **same** scoring tests
(only the import line changes) plus the new classify tests:

```python
"""Unit tests for the pure memory retention logic (moved from test_memory_cleanup)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.domains.memories.models import PurgeRiskLevel
from src.domains.memories.retention import (
    RetentionConfig,
    calculate_retention_score,
    classify_purge_risk,
    should_purge,
)

# Calibrated defaults matching .env.example (Lot 2bis)
RECENCY_DECAY_DAYS = 45
USAGE_PENALTY_AGE_DAYS = 30
USAGE_PENALTY_FACTOR = 0.5
MIN_AGE_FOR_CLEANUP_DAYS = 7
WEIGHT_IMPORTANCE = 0.7
WEIGHT_RECENCY = 0.3
PURGE_THRESHOLD = 0.5
AT_RISK_MARGIN = 0.1


def _make_memory(
    *,
    importance: float = 0.7,
    age_days: int = 0,
    usage_count: int = 0,
    pinned: bool = False,
):
    """Build a minimal Memory-like object for scoring tests."""
    return SimpleNamespace(
        importance=importance,
        usage_count=usage_count,
        pinned=pinned,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
    )


def _config(**overrides) -> RetentionConfig:
    base = dict(
        min_age_for_cleanup_days=MIN_AGE_FOR_CLEANUP_DAYS,
        recency_decay_days=RECENCY_DECAY_DAYS,
        usage_penalty_age_days=USAGE_PENALTY_AGE_DAYS,
        usage_penalty_factor=USAGE_PENALTY_FACTOR,
        purge_threshold=PURGE_THRESHOLD,
        at_risk_margin=AT_RISK_MARGIN,
        weight_importance=WEIGHT_IMPORTANCE,
        weight_recency=WEIGHT_RECENCY,
    )
    base.update(overrides)
    return RetentionConfig(**base)


# --- Paste TestCalculateRetentionScore and TestShouldPurge verbatim from the
# --- old test_memory_cleanup.py (assertions unchanged). ---


@pytest.mark.unit
class TestClassifyPurgeRisk:
    def test_pinned_is_protected(self):
        mem = _make_memory(importance=0.1, age_days=365, usage_count=0, pinned=True)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.PROTECTED
        assert score is None

    def test_within_grace_is_safe(self):
        mem = _make_memory(importance=0.1, age_days=3, usage_count=0)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.SAFE
        assert score is None

    def test_low_score_is_imminent(self):
        # 0.7*0.5 + 0.3*(1-30/45) = 0.45 < 0.5
        mem = _make_memory(importance=0.5, age_days=30, usage_count=1)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.IMMINENT
        assert score is not None and score < PURGE_THRESHOLD

    def test_near_threshold_is_at_risk(self):
        # 0.7*0.6 + 0.3*(1-25/45) = 0.42 + 0.133 = 0.553 -> [0.5, 0.6)
        mem = _make_memory(importance=0.6, age_days=25, usage_count=1)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.AT_RISK
        assert score is not None and PURGE_THRESHOLD <= score < PURGE_THRESHOLD + AT_RISK_MARGIN

    def test_high_score_is_safe(self):
        # 0.7*0.9 + 0.3*(1-20/45) = 0.63 + 0.167 = 0.797 >= 0.6
        mem = _make_memory(importance=0.9, age_days=20, usage_count=2)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.SAFE
        assert score is not None and score >= PURGE_THRESHOLD + AT_RISK_MARGIN
```

- [ ] **Step 4: Run the retention tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/memories/test_retention.py -v`
Expected: PASS — moved scoring tests + 5 classify tests.

- [ ] **Step 5: Confirm no broken imports of the moved functions**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/scheduler/ -q`
Expected: PASS (no remaining import of the deleted local defs).
Also run: `cd apps/api && .venv/Scripts/python -c "import src.infrastructure.scheduler.memory_cleanup"`
Expected: imports cleanly.

- [ ] **Step 6: Checkpoint** — propose a commit.

---

## Task B3: `MemoryResponse` fields

**Files:**
- Modify: `apps/api/src/domains/memories/schemas.py`

- [ ] **Step 1: Add imports and fields**

In `apps/api/src/domains/memories/schemas.py`, add the import
`from src.domains.memories.models import PurgeRiskLevel`, then add to `MemoryResponse`
(after `context_biometric`):

```python
    purge_risk: PurgeRiskLevel = Field(
        default=PurgeRiskLevel.SAFE,
        description="Auto-purge risk state (read-only, computed). Does not affect the purge job.",
    )
    retention_score: float | None = Field(
        default=None,
        description="Computed retention score (0-1); None when pinned or within grace period.",
    )
```

- [ ] **Step 2: Checkpoint**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/memories/test_schemas.py -v`
Expected: PASS (additive fields with defaults). Propose a commit.

---

## Task B4: Router computes purge risk

**Files:**
- Modify: `apps/api/src/domains/memories/router.py`

- [ ] **Step 1: Add imports and a config builder**

Add imports at the top of `apps/api/src/domains/memories/router.py`:

```python
from datetime import UTC, datetime

from src.core.config import settings
from src.domains.memories.retention import RetentionConfig, classify_purge_risk
```

(`datetime`/`UTC` are already imported — keep a single import line; add only what is missing.)

Add a module-level helper (after the imports, before `_memory_to_response`):

```python
def _build_retention_config() -> RetentionConfig:
    """Snapshot the current retention settings for risk classification."""
    return RetentionConfig(
        min_age_for_cleanup_days=settings.memory_min_age_for_cleanup_days,
        recency_decay_days=settings.memory_recency_decay_days,
        usage_penalty_age_days=settings.memory_usage_penalty_age_days,
        usage_penalty_factor=settings.memory_usage_penalty_factor,
        purge_threshold=settings.memory_purge_threshold,
        at_risk_margin=settings.memory_purge_at_risk_margin,
        weight_importance=settings.memory_retention_weight_importance,
        weight_recency=settings.memory_retention_weight_recency,
    )
```

- [ ] **Step 2: Change `_memory_to_response` signature**

Replace the `_memory_to_response` definition so it computes and sets the new fields:

```python
def _memory_to_response(
    memory: Memory,
    now: datetime,
    config: RetentionConfig,
) -> MemoryResponse:
    """Convert a Memory ORM object to MemoryResponse (with computed purge risk).

    Args:
        memory: Memory ORM instance.
        now: Current datetime (one snapshot per request).
        config: Retention configuration snapshot.

    Returns:
        MemoryResponse with all fields, including read-only purge-risk data.
    """
    purge_risk, retention_score = classify_purge_risk(memory, now, config)
    return MemoryResponse(
        id=str(memory.id),
        content=memory.content or "",
        category=memory.category or "personal",
        emotional_weight=memory.emotional_weight or 0,
        trigger_topic=memory.trigger_topic or "",
        usage_nuance=memory.usage_nuance or "",
        importance=memory.importance or 0.7,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        pinned=memory.pinned or False,
        usage_count=memory.usage_count or 0,
        last_accessed_at=memory.last_accessed_at,
        purge_risk=purge_risk,
        retention_score=retention_score,
    )
```

- [ ] **Step 3: Update every call site**

There are five call sites (`export_memories`, `list_memories`, `get_memory`, `create_memory`,
`update_memory`). In each, build `now`/`config` once and pass them. Examples:

`list_memories` (and `export_memories`, which both map a list):

```python
        now = datetime.now(UTC)
        config = _build_retention_config()
        items = [_memory_to_response(m, now, config) for m in filtered]
```

For `export_memories`:

```python
        now = datetime.now(UTC)
        config = _build_retention_config()
        memories = [_memory_to_response(m, now, config) for m in all_memories]
```

Single-item endpoints (`get_memory`, `create_memory`, `update_memory`):

```python
        return _memory_to_response(memory, datetime.now(UTC), _build_retention_config())
```

(For `update_memory` the variable holding the saved memory is `updated`; pass that one.)

- [ ] **Step 4: Checkpoint (imports + module load)**

Run: `cd apps/api && .venv/Scripts/python -c "import src.domains.memories.router"`
Expected: imports cleanly (all call sites updated; no `TypeError` at import).
Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/memories/ -q`
Expected: green. Propose a commit.

---

## Task B5: Memories i18n keys (6 languages)

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`

- [ ] **Step 1: Add keys under the `memories` namespace**

| key | en | fr | de | es | it | zh |
|-----|----|----|----|----|----|----|
| `memories.purge_risk_badge_at_risk` | May be forgotten | Risque d'oubli | Könnte vergessen werden | Puede olvidarse | Rischio di oblio | 可能被遗忘 |
| `memories.purge_risk_badge_imminent` | About to be forgotten | Bientôt oublié | Wird bald vergessen | A punto de olvidarse | Sta per essere dimenticato | 即将被遗忘 |
| `memories.purge_risk_tooltip` | This memory may be forgotten — pin it to keep it. | Ce souvenir risque d'être oublié — épinglez-le pour le conserver. | Diese Erinnerung könnte vergessen werden – heften Sie sie an, um sie zu behalten. | Este recuerdo puede olvidarse: fíjalo para conservarlo. | Questo ricordo potrebbe essere dimenticato: fissalo per conservarlo. | 这条记忆可能会被遗忘——置顶以保留它。 |

- [ ] **Step 2: Checkpoint (i18n parity)** — run the parity check; expected no missing/extra keys. Propose a commit.

---

## Task B6: `useMemories` type fields

**Files:**
- Modify: `apps/web/src/hooks/useMemories.ts`

- [ ] **Step 1: Extend the `Memory` interface**

Add to the `Memory` interface (after `last_accessed_at`):

```typescript
  // Purge-risk exposure (read-only, computed by the API)
  purge_risk?: 'protected' | 'safe' | 'at_risk' | 'imminent';
  retention_score?: number | null;
```

- [ ] **Step 2: Checkpoint** — `docker exec lia-web-dev pnpm tsc --noEmit`; expected clean. Propose a commit.

---

## Task B7: `MemorySettings.tsx` — risk badge

**Files:**
- Modify: `apps/web/src/components/settings/MemorySettings.tsx`

- [ ] **Step 1: Import `AlertTriangle` (already imported) — add a helper**

`AlertTriangle` is already imported. Add a small helper above the component (after
`sortMemoriesByDate`):

```typescript
/**
 * Whether a memory should show a purge-risk warning.
 */
function isAtPurgeRisk(memory: Memory): boolean {
  return memory.purge_risk === 'at_risk' || memory.purge_risk === 'imminent';
}
```

- [ ] **Step 2: Render the badge on at-risk cards**

Inside the memory card metadata row (the `flex flex-wrap items-center ...` block that holds
dates/usage/importance), append a conditional badge:

```tsx
                              {isAtPurgeRisk(memory) && !memory.pinned && (
                                <span
                                  className={
                                    'text-xs flex items-center gap-1 ' +
                                    (memory.purge_risk === 'imminent'
                                      ? 'text-destructive'
                                      : 'text-amber-600 dark:text-amber-500')
                                  }
                                  title={t('memories.purge_risk_tooltip')}
                                >
                                  <AlertTriangle className="h-3 w-3" />
                                  {memory.purge_risk === 'imminent'
                                    ? t('memories.purge_risk_badge_imminent')
                                    : t('memories.purge_risk_badge_at_risk')}
                                </span>
                              )}
```

- [ ] **Step 3: Checkpoint** — `docker exec lia-web-dev pnpm tsc --noEmit` then `docker exec lia-web-dev pnpm test`; expected clean + green. Propose a commit.

---

## Task B8: Phase B runtime verification

- [ ] **Step 1: Backend fast unit + agents suites**

Run: `cd apps/api && .venv/Scripts/pytest -m "unit and not integration" -q`
Then: `task test:backend:agents`
Expected: all green; the moved scoring assertions are byte-for-byte identical.

- [ ] **Step 2: Verify Docker app startup**

`docker compose restart api` — confirm clean boot (settings composition picks up
`memory_purge_at_risk_margin`; memory list endpoint serves the new fields).

- [ ] **Step 3: Checkpoint** — propose a commit for Phase B.

---

# Final Non-Regression Gate (both phases)

- [ ] **Step 1: Full pre-commit**

Run from repo root: `task pre-commit`
Expected: format + lint + fast unit + i18n parity all clean. Do NOT use `--no-verify`.

- [ ] **Step 2: Frontend suite + typecheck**

Run: `docker exec lia-web-dev pnpm tsc --noEmit` and `docker exec lia-web-dev pnpm test`
Expected: clean + green.

- [ ] **Step 3: Docker startup smoke**

`task dev:detach` (or restart api + web). Confirm: API boots, `/api/v1/interests` returns
`dormant_count`, `POST /api/v1/interests/{id}/reactivate` exists, `/api/v1/memories` returns
`purge_risk` + `retention_score`, and the Settings UI renders the Dormant section and risk badges.

- [ ] **Step 4: Documentation**

Update the technical docs of both domains (Interests lifecycle: dormant visibility +
reactivation; Memories: purge-risk exposure + `memory_purge_at_risk_margin`). No ADR. Update
`docs/INDEX.md` cross-references if any touched doc title changes.

- [ ] **Step 5: Final checkpoint** — propose the final commit(s) to the user.

---

## Spec Coverage Check

- Interests dormant visible section → Tasks A3, A7.
- Reactivate (reset to fresh) → A1, A2, A4 (endpoint), A6/A7 (UI).
- 409 guard on non-dormant → A4.
- Counter breakdown → A3, A7.
- Memory 4-state purge risk → B2 (`classify_purge_risk`), B3, B4.
- On-the-fly recompute, centralized `retention.py` → B2, B4.
- `should_purge`/`calculate_retention_score` kept intact → B2.
- New margin setting (parameterizable) → B1.
- Risk UI → B6, B7.
- i18n (both) → A5, B5.
- Zero regression → moved-test parity (B2), additive schema fields (A3, B3), Final Gate.
- No DB migration → confirmed (no migration task).
