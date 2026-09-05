"""Effect ledger repository: claim before effect, close from result (ADR-263).

Every write is ONE conditional statement, so two workers can never both win:

- ``claim`` is ``INSERT ... ON CONFLICT DO NOTHING RETURNING`` on the unique
  ``(thread_id, idempotency_key)``. A lost race returns the row that already
  holds the key, and the caller decides what that means — serve its result,
  retry a failure, or take over a stale claim.
- every close is ``UPDATE ... WHERE id = :id AND claim_token = :token AND
  status = 'claimed'``. A stale owner, or a second close, updates zero rows and
  is told so by the return value rather than by an exception nobody expects.

Nothing here decides WHETHER an effect may happen — that is the gate of lot 2.
This module only makes "it happened, exactly once, and here is what came back"
a durable fact.

Two contracts the caller owns, because no repository can enforce them:

1. **The claim must be COMMITTED before the effect is performed.** An email is
   not transactional: if the caller keeps the claim in an open transaction,
   sends the mail and then rolls back, the mail is gone from the world's point
   of view and absent from the ledger — the exact dual-write hole this ledger
   exists to close. Claim, commit, act, then close.
2. **A retry claims a NEW key.** ``abandon_stale`` closes the old row but does
   not free its key: the unique constraint is what makes "exactly once" true,
   so releasing it would let the original claim be replayed. A retry uses a
   derived key (``<key>:retry-<n>``) and points at its predecessor through
   ``retry_of``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.repository import BaseRepository
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.models import AgentEffect, EffectSource, EffectStatus
from src.domains.agents.effects.period import period_conditions
from src.domains.agents.effects.schemas import ClaimRequest
from src.infrastructure.database.export_window import newest_window

logger = structlog.get_logger(__name__)

#: Suffix marking the idempotency key of a REFUSED row. A refusal must not
#: occupy the key of the operation it refused: the user may fix the authority
#: and ask again, and that legitimate second attempt has to be claimable.
_REFUSED_KEY_SUFFIX = "#refused:"


@dataclass(frozen=True)
class ClaimOutcome:
    """The result of claiming the right to perform one effect.

    Attributes:
        effect: The row — freshly inserted, or the one that already held the key.
        claimed: True when THIS call inserted the row and may perform the effect.
        claim_token: The owner token needed to close the row; None when the
            claim was lost, because a caller that did not claim must not be
            able to close.
    """

    effect: AgentEffect
    claimed: bool
    claim_token: uuid.UUID | None


class EffectLedgerRepository(BaseRepository[AgentEffect]):
    """Atomic primitives over ``agent_effects``."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session.

        Args:
            db: Session owning the transaction the claim and its close share.
        """
        super().__init__(db, AgentEffect)

    async def claim(self, req: ClaimRequest) -> ClaimOutcome:
        """Claim the right to perform one effect, exactly once per key.

        Args:
            req: What the effect is, and under which authority.

        Returns:
            ``claimed=True`` with a token when this call won the key; otherwise
            the existing row with no token.
        """
        token = uuid.uuid4()
        statement = (
            pg_insert(AgentEffect)
            .values(
                id=uuid.uuid4(),
                user_id=req.user_id,
                thread_id=req.thread_id,
                run_id=req.run_id,
                source=EffectSource(req.source),
                execution_mode=req.execution_mode,
                tool_name=req.tool_name,
                mutation_policy=req.mutation_policy,
                idempotency_key=req.idempotency_key,
                args_digest=req.args_digest,
                approval_kind=req.approval_kind,
                approval_ref=req.approval_ref,
                draft_digest=req.draft_digest,
                catalogue_fingerprint=req.catalogue_fingerprint,
                retry_of=req.retry_of,
                label=self._encrypted(req.label),
                status=EffectStatus.CLAIMED,
                claim_token=token,
                claimed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_agent_effects_thread_idempotency")
            .returning(AgentEffect.id)
        )
        inserted_id = (await self.db.execute(statement)).scalar_one_or_none()
        if inserted_id is not None:
            await self.db.flush()
            effect = await self.db.get(AgentEffect, inserted_id)
            if effect is None:  # pragma: no cover - the row was just inserted here
                raise RuntimeError("claimed effect row vanished within its own transaction")
            return ClaimOutcome(effect=effect, claimed=True, claim_token=token)

        existing = (
            await self.db.execute(
                select(AgentEffect).where(
                    AgentEffect.thread_id == req.thread_id,
                    AgentEffect.idempotency_key == req.idempotency_key,
                )
            )
        ).scalar_one()
        # No PII: the tool and the status, never the arguments.
        logger.info(
            "effect_claim_lost",
            tool_name=req.tool_name,
            existing_status=existing.status.value,
            run_id=req.run_id,
        )
        return ClaimOutcome(effect=existing, claimed=False, claim_token=None)

    async def close_success(
        self,
        effect_id: uuid.UUID,
        claim_token: uuid.UUID,
        *,
        provider_ref: str | None = None,
        result_payload: Any = None,
    ) -> bool:
        """Mark the effect SUCCEEDED from an explicit result.

        Args:
            effect_id: Row id returned by :meth:`claim`.
            claim_token: Owner token returned by :meth:`claim`.
            provider_ref: Provider-side identifier, when the tool returns one.
            result_payload: The result to keep (encrypted, capped) so a resume
                can be served without re-executing the effect.

        Returns:
            True when this call closed the row; False for a stale owner, or a
            row that is no longer CLAIMED.
        """
        encrypted, truncated = self._encrypted_result(result_payload)
        return await self._close(
            effect_id,
            claim_token,
            status=EffectStatus.SUCCEEDED,
            provider_ref=provider_ref,
            result_digest=None if result_payload is None else payload_digest(result_payload),
            result_payload=encrypted,
            result_truncated=truncated,
        )

    async def close_failure(
        self, effect_id: uuid.UUID, claim_token: uuid.UUID, *, error_code: str
    ) -> bool:
        """Mark the effect FAILED: it did not happen, or is not known to have.

        Args:
            effect_id: Row id returned by :meth:`claim`.
            claim_token: Owner token returned by :meth:`claim`.
            error_code: Stable, non-free-text code.

        Returns:
            True when this call closed the row.
        """
        return await self._close(
            effect_id, claim_token, status=EffectStatus.FAILED, error_code=error_code[:50]
        )

    async def refuse(self, req: ClaimRequest, *, error_code: str) -> AgentEffect:
        """Record an effect REFUSED for want of authority — no claim, no effect.

        A refusal is a fact worth keeping: it is what the answer will say and
        what the operator will count. Its key is suffixed so it does not occupy
        the key of the operation it refused — the user may grant the authority
        and ask again.

        Args:
            req: The effect that was not performed.
            error_code: Why the authority was missing.

        Returns:
            The recorded row.
        """
        now = datetime.now(UTC)
        row = AgentEffect(
            id=uuid.uuid4(),
            user_id=req.user_id,
            thread_id=req.thread_id,
            run_id=req.run_id,
            source=EffectSource(req.source),
            execution_mode=req.execution_mode,
            tool_name=req.tool_name,
            mutation_policy=req.mutation_policy,
            idempotency_key=f"{req.idempotency_key}{_REFUSED_KEY_SUFFIX}{uuid.uuid4().hex[:8]}",
            args_digest=req.args_digest,
            approval_kind=req.approval_kind,
            approval_ref=req.approval_ref,
            draft_digest=req.draft_digest,
            catalogue_fingerprint=req.catalogue_fingerprint,
            label=self._encrypted(req.label),
            status=EffectStatus.REFUSED,
            claim_token=uuid.uuid4(),
            error_code=error_code[:50],
            claimed_at=now,
            closed_at=now,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def abandon_stale(self, effect_id: uuid.UUID, *, older_than: datetime) -> bool:
        """Mark a CLAIMED row ABANDONED when its owner never closed it.

        Conditioned on ``claimed_at < older_than`` so a live claim — its owner
        still inside the tool's own timeout — is never abandoned by a concurrent
        caller. The caller then claims again with ``retry_of``.

        Args:
            effect_id: The row to abandon.
            older_than: Cutoff; a claim younger than this is left alone.

        Returns:
            True when this call abandoned the row.
        """
        statement = (
            update(AgentEffect)
            .where(
                AgentEffect.id == effect_id,
                AgentEffect.status == EffectStatus.CLAIMED,
                AgentEffect.claimed_at < older_than,
            )
            .values(status=EffectStatus.ABANDONED, closed_at=datetime.now(UTC))
        )
        result = await self.db.execute(statement)
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    async def list_for_export(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        user_id: uuid.UUID | None = None,
        user_ids: Sequence[uuid.UUID] | None = None,
        tool_name: str | None = None,
        mutation_policy: str | None = None,
        status: EffectStatus | None = None,
        source: EffectSource | None = None,
        execution_mode: str | None = None,
        limit: int,
    ) -> list[AgentEffect]:
        """Rows matching an operator's filters, oldest first, capped.

        Every filter is optional and combined with AND. The cap is applied
        here and PUBLISHED by the caller in the file's header: an export that
        stops early must say so, or its reader draws conclusions from a
        truncation nobody mentioned.

        Args:
            since: Lower bound on ``claimed_at`` (inclusive).
            until: Upper bound on ``claimed_at`` (exclusive).
            user_id: One account, when the question is about one account.
            user_ids: SEVERAL accounts, when it is about several. Given both,
                the narrower one wins — an operator who named an account has
                asked a narrower question than the one who named a group.
            tool_name: One capability.
            mutation_policy: One declared policy.
            status: One outcome.
            source: One authority source.
            execution_mode: ``pipeline`` or ``react``.
            limit: Row ceiling.

        Returns:
            The matching rows, oldest first.
        """
        query = select(AgentEffect)
        if since is not None:
            query = query.where(AgentEffect.claimed_at >= since)
        if until is not None:
            query = query.where(AgentEffect.claimed_at < until)
        if user_id is not None:
            query = query.where(AgentEffect.user_id == user_id)
        elif user_ids is not None:
            query = query.where(AgentEffect.user_id.in_(list(user_ids)))
        if tool_name:
            query = query.where(AgentEffect.tool_name == tool_name)
        if mutation_policy:
            query = query.where(AgentEffect.mutation_policy == mutation_policy)
        if status is not None:
            query = query.where(AgentEffect.status == status)
        if source is not None:
            query = query.where(AgentEffect.source == source)
        if execution_mode:
            query = query.where(AgentEffect.execution_mode == execution_mode)

        # The most RECENT rows, returned oldest first: ordering ascending and
        # then capping gave the BEGINNING of history — measured 2026-09-05, an
        # export covered the first five weeks of an eight-month register.
        return await newest_window(
            self.db,
            query,
            newest_first=(AgentEffect.claimed_at.desc(), AgentEffect.id.desc()),
            limit=limit,
        )

    async def count_claimed_orphans(self, older_than: datetime) -> int:
        """How many effects are still CLAIMED past the staleness threshold.

        A row stuck in ``CLAIMED`` means a turn died between claiming an effect
        and recording its outcome: the action may or may not have happened, and
        nothing else in the system would ever say which. Prometheus cannot see
        rows, so this exact count is transported to a gauge (ADR-263).

        Args:
            older_than: Only rows claimed before this instant count — a claim
                that is merely in flight is not an orphan.

        Returns:
            The exact number of stale claims.
        """
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(AgentEffect)
                .where(
                    AgentEffect.status == EffectStatus.CLAIMED,
                    AgentEffect.claimed_at < older_than,
                )
            )
        ).scalar_one()
        return int(total)

    async def list_for_run(self, run_id: str) -> list[AgentEffect]:
        """Every effect of one run, oldest first — the facts a response may state.

        Args:
            run_id: The run.

        Returns:
            The rows, in the order they were claimed.
        """
        rows = await self.db.execute(
            select(AgentEffect).where(AgentEffect.run_id == run_id).order_by(AgentEffect.claimed_at)
        )
        return list(rows.scalars().all())

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        status: EffectStatus | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[AgentEffect], int]:
        """One page of a user's effects, newest first, with the EXACT total.

        The total is an aggregate over the whole set, never the length of the
        page: a count shown to the user is exact or it does not exist (ADR-185).

        Args:
            user_id: Whose ledger.
            limit: Page size.
            offset: Page offset.
            status: One outcome, when the reader is filtering. Applied to the
                count as well as to the page.
            since: Inclusive lower bound on the claim time.
            until: Exclusive upper bound on the claim time.

        Returns:
            The page and the exact total.
        """
        # The filter belongs to BOTH queries or the count describes a different
        # set from the page — a total above a filtered list is a lie the reader
        # has no way to detect.
        conditions = [AgentEffect.user_id == user_id]
        if status is not None:
            conditions.append(AgentEffect.status == status)
        conditions.extend(period_conditions(AgentEffect.claimed_at, since, until))

        total = (
            await self.db.execute(select(func.count()).select_from(AgentEffect).where(*conditions))
        ).scalar_one()
        rows = await self.db.execute(
            select(AgentEffect)
            .where(*conditions)
            .order_by(AgentEffect.claimed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total)

    @staticmethod
    def decrypted_result(effect: AgentEffect) -> Any | None:
        """Decrypt the kept result, or None when none was kept.

        A truncated payload is no longer valid JSON, so it comes back as
        ``{"truncated": True, "text": ...}``: a caller can show it but can never
        mistake it for the whole result and serve a resume from half a value.

        Args:
            effect: The row.

        Returns:
            The result, the truncation envelope, or None.
        """
        if effect.result_payload is None:
            return None
        text = decrypt_data(effect.result_payload)
        if effect.result_truncated:
            return {"truncated": True, "text": text}
        return json.loads(text)

    @staticmethod
    def decrypted_label(effect: AgentEffect) -> dict[str, Any] | None:
        """Decrypt the stored ``{i18n_key, values}``, or None when there is none.

        Never raises: this feeds a register the user asked for, and a row
        written by an older version — or with a key that has since rotated —
        must cost that row its wording, never the whole export.

        Args:
            effect: The row.

        Returns:
            The label, or None when absent or unreadable.
        """
        if effect.label is None:
            return None
        try:
            label = json.loads(decrypt_data(effect.label))
        except Exception:  # noqa: BLE001 - an unreadable wording is not a failure
            return None
        return label if isinstance(label, dict) else None

    # -- internals ---------------------------------------------------------

    async def _close(
        self,
        effect_id: uuid.UUID,
        claim_token: uuid.UUID,
        *,
        status: EffectStatus,
        **values: Any,
    ) -> bool:
        """Close a row, conditioned on ownership and on it still being open."""
        statement = (
            update(AgentEffect)
            .where(
                AgentEffect.id == effect_id,
                AgentEffect.claim_token == claim_token,
                AgentEffect.status == EffectStatus.CLAIMED,
            )
            .values(status=status, closed_at=datetime.now(UTC), **values)
        )
        result = await self.db.execute(statement)
        # ``execute`` is typed ``Result``; an UPDATE always yields a
        # ``CursorResult``, which is what carries ``rowcount`` (same idiom as
        # ``diagnostics/repository.py``). Exactly one row means WE closed it.
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    @staticmethod
    def _render(value: Any) -> str:
        """Canonical JSON rendering shared by every stored payload.

        One definition of "how a value is written": ``default=str`` so a UUID or
        a datetime never sinks a claim, and ``ensure_ascii=False`` so an accented
        label is stored as itself rather than as escapes.
        """
        return json.dumps(value, default=str, ensure_ascii=False)

    @classmethod
    def _encrypted(cls, value: Any) -> str | None:
        """Render a small structure as encrypted JSON, or None."""
        if value is None:
            return None
        return encrypt_data(cls._render(value))

    @classmethod
    def _encrypted_result(cls, result_payload: Any) -> tuple[str | None, bool]:
        """Render the result as encrypted JSON, capped, saying whether it was cut."""
        if result_payload is None:
            return None, False
        rendered = cls._render(result_payload)
        raw = rendered.encode("utf-8")
        cap = settings.effect_result_payload_max_bytes
        if len(raw) > cap:
            # Cut on a character boundary: a half-encoded character would make
            # the stored text undecodable, which is worse than a shorter one.
            rendered = raw[:cap].decode("utf-8", errors="ignore")
            return encrypt_data(rendered), True
        return encrypt_data(rendered), False
