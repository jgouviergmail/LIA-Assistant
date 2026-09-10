"""Building and reading one relationship's debrief.

The rules this service owns, and why each exists:

- **once per user LOCAL day.** "Once a day" is a promise about the reader's
  day; a UTC boundary would rebuild at 2 a.m. for half of Europe.
- **three legitimate rebuilds.** A language change, a scope change and an
  explicit ask. The first two would otherwise leave a stored text contradicting
  the reader's own settings; the third is the reader's call.
- **the evidence digest is compared only with the evidence in hand.** A passive
  "the data moved" flag would state a negative nobody verified (ADR-184) — the
  digest is meaningful at BUILD time, and there it earns its keep: a forced
  rebuild over unchanged evidence skips the LLM call and carries the day
  forward, which is exact because it was just checked.
- **nothing invented.** No evidence at all settles ``empty``: no call, no
  generic paragraph. A failure keeps whatever the reader already had.

Every read is cheap and never builds. Building is an explicit act, capped per
account and claimed atomically, so two tabs never spend two calls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    RELATION_DEBRIEF_BODY_VERSION,
    RELATION_DEBRIEF_LLM_TYPE,
    RELATION_DEBRIEF_PROACTIVE_TASK_TYPE,
)
from src.core.i18n import normalize_language
from src.core.llm_usage import LLMUsage
from src.core.time_utils import resolve_user_timezone
from src.domains.relations.debrief.llm import DebriefAuthor, write_debrief
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.debrief.repository import RelationDebriefRepository
from src.domains.relations.debrief.schemas import (
    DebriefBody,
    DebriefStatus,
    RelationDebriefRead,
    StoredDebriefBody,
)
from src.domains.relations.identity import IdentityResolver
from src.domains.relations.overview import (
    OverviewEvidenceUnavailable,
    build_overview_evidence,
    overview_payload,
)
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.repository import RelationAliasRepository
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_relation_debrief import (
    relation_debrief_build_duration_seconds,
    relation_debrief_builds_total,
)
from src.infrastructure.proactive.tracking import generate_proactive_run_id

if TYPE_CHECKING:
    from src.domains.relations.overview import OverviewEvidence

logger = structlog.get_logger(__name__)

#: Payload keys that carry no evidence — identity and caveats, not content.
#: A relationship whose payload holds nothing else has nothing to synthesise.
_NON_EVIDENCE_KEYS = frozenset({"person", "identity_confidence", "is_peer", "unavailable"})


def _digest(payload: object) -> str:
    """A stable digest of any JSON-able structure.

    ``sort_keys`` is what makes it stable: two payloads differing only in
    dictionary order describe the same evidence, and rebuilding on that would
    make the "nothing changed" shortcut fire at random.
    """
    material = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _has_evidence(payload: dict[str, Any]) -> bool:
    """Whether the payload carries anything a synthesis could be written from.

    Identity and caveats are not evidence: a card with a name, a confidence and
    an empty ``unavailable`` describes a relationship nothing is known about.
    An empty LIST is not evidence either — "no open commitments" is a fact, but
    a debrief made only of such facts is a paragraph about nothing.

    Args:
        payload: The assembled 360° payload.

    Returns:
        True when at least one block holds an item.
    """
    for key, value in payload.items():
        if key in _NON_EVIDENCE_KEYS or key.endswith("_total") or key.endswith("_window_days"):
            continue
        if isinstance(value, list | dict) and value:
            return True
        if isinstance(value, str) and value:
            return True
    return False


def _sections_of(payload: dict[str, Any]) -> list[str]:
    """The blocks the debrief actually read, for the honesty footer."""
    return sorted(
        key
        for key, value in payload.items()
        if key not in _NON_EVIDENCE_KEYS
        and not key.endswith(("_total", "_window_days", "_matched_by_name"))
        and value
    )


def _body_of(row: RelationDebrief) -> DebriefBody | None:
    """Rebuild the stored body, or None when this version cannot read it.

    A shape written by a newer version is not an error the reader can act on:
    answering "not built yet" makes the next open rebuild it, which is exactly
    the repair. Rendering half of it would not be.
    """
    if not isinstance(row.body, dict):
        return None
    if row.body.get("version") != RELATION_DEBRIEF_BODY_VERSION:
        logger.info("relation_debrief_body_version_unreadable", stored=row.body.get("version"))
        return None
    try:
        return DebriefBody.model_validate(row.body)
    except ValueError:
        logger.warning("relation_debrief_body_unreadable")
        return None


@dataclass(frozen=True, slots=True)
class _Previous:
    """What stood before this build, and whether it may simply be reused.

    Reuse is NOT a question about the evidence alone. A debrief written in
    French is worthless in an English turn however unchanged the underlying
    facts are, and one written under another scope was allowed to look at
    different things. Comparing only the evidence digest made a language change
    a no-op — the rebuild was claimed, then skipped, and the text stayed in the
    old language for good (caught by the freshness suite, never by a reader).
    """

    state: DebriefState | None
    digest: str | None
    same_settings: bool

    @classmethod
    def of(cls, row: RelationDebrief | None, *, language: str, scope_digest: str) -> _Previous:
        """Snapshot the stored row against the settings this build applies."""
        if row is None:
            return cls(state=None, digest=None, same_settings=False)
        return cls(
            state=row.state,
            digest=row.evidence_digest,
            same_settings=row.language == language and row.scope_digest == scope_digest,
        )

    def reusable_state(self, digest: str) -> DebriefState | None:
        """The state to carry forward, or None when a rewrite is owed.

        Returning the STATE rather than a boolean is what keeps the carry
        honest: an empty relationship that is still empty stays empty, and
        promoting it to ``ready`` would promise a body nobody wrote.

        Args:
            digest: Digest of the evidence just assembled.

        Returns:
            The settled state to carry, or None.
        """
        if not (self.same_settings and self.digest is not None and self.digest == digest):
            return None
        if self.state in (DebriefState.READY, DebriefState.EMPTY):
            return self.state
        return None


def read_of(row: RelationDebrief) -> RelationDebriefRead:
    """Project a stored row onto the API contract.

    Module-level, because the chat injection projects the same row and reaching
    into a service's private method from another module is not a contract — it
    is a coupling nobody declared.

    A FAILED row keeps whatever body it had: "I could not refresh this" and
    "there is nothing" are different answers, and only the first is true.

    Args:
        row: The stored debrief.

    Returns:
        The debrief and everything that makes it honest.
    """
    body = _body_of(row)
    status = DebriefStatus(row.state.value)
    # A body this version cannot read is not a debrief — say so, so the next
    # open rebuilds instead of rendering an empty panel as ready.
    if status is DebriefStatus.READY and body is None:
        status = DebriefStatus.ABSENT
    return RelationDebriefRead(
        status=status,
        person=row.display_name,
        body=body,
        generated_at=row.generated_at,
        generated_for=row.generated_for,
        sections_used=[str(item) for item in (row.sections_used or [])],
        unavailable=[str(item) for item in (row.unavailable or [])],
        usage=_stored_usage(row),
        can_rebuild=_can_rebuild(row),
    )


def _stored_usage(row: RelationDebrief) -> LLMUsage | None:
    """What the stored body cost, when the row can still say.

    Degrades to None rather than to zeros: a cost of 0,00 € is a CLAIM, and a
    row written before this column existed made none.

    Args:
        row: The stored debrief.

    Returns:
        The usage summary, or None when there is none to read.
    """
    if not isinstance(row.usage, dict):
        return None
    try:
        return LLMUsage.model_validate(row.usage)
    except ValueError:
        logger.warning("relation_debrief_usage_unreadable", state=row.state.value)
        return None


def _can_rebuild(row: RelationDebrief) -> bool:
    """Whether asking again would do anything right now.

    Offering a control for an action the claim would refuse is a promise the
    system cannot keep — the button would simply do nothing.

    Args:
        row: The stored debrief.

    Returns:
        True when a claim would be granted.
    """
    if row.state is DebriefState.BUILDING:
        return row.held_until is not None and row.held_until < datetime.now(UTC)
    if row.state is DebriefState.FAILED:
        return row.held_until is None or row.held_until < datetime.now(UTC)
    return True


class RelationDebriefService:
    """Reads and builds the debrief of one user's relationships."""

    def __init__(self, user_id: UUID) -> None:
        """Bind the owner (the service holds no session — each read opens one)."""
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Reads — cheap, and they never build
    # ------------------------------------------------------------------

    async def read(self, name: str) -> RelationDebriefRead:
        """The stored debrief of one relationship. Never builds, never calls out.

        Args:
            name: The relationship, as the user says it.

        Returns:
            The debrief and its provenance, or a stated absence.
        """
        async with get_db_context() as db:
            user = await db.get(User, self.user_id)
            if user is None:
                # Unreachable through the API (the session dependency resolved
                # them), and NOT "disabled": that would offer a switch which
                # could not do anything. Nothing is known, so say nothing.
                return RelationDebriefRead(status=DebriefStatus.ABSENT, person=name.strip())
            if not await self._enabled(user):
                return RelationDebriefRead(status=DebriefStatus.DISABLED, person=name.strip())
            key = await self._identity_key(db, name)
            row = await RelationDebriefRepository(db).get(self.user_id, key) if key else None
        if row is None:
            return RelationDebriefRead(status=DebriefStatus.ABSENT, person=name.strip())
        return self._to_read(row)

    @staticmethod
    async def _enabled(user: User) -> bool:
        """Every switch: the deployment ceiling, the operator's, the account's.

        Async since B7: the operator's switch lives in the settings store, and
        reading the raw environment flag would announce a capability an
        administrator turned off an hour ago.
        """
        from src.domains.feature_switches.registry import (
            PlatformCapability,
            is_capability_enabled,
        )

        return bool(
            await is_capability_enabled(PlatformCapability.RELATION_DEBRIEF)
            and getattr(user, "relation_debrief_enabled", True)
        )

    def _to_read(self, row: RelationDebrief) -> RelationDebriefRead:
        """Project a stored row onto the API contract (see :func:`read_of`)."""
        return read_of(row)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    async def build(self, name: str, *, force: bool = False) -> RelationDebriefRead:
        """Build today's debrief for one relationship, or return what stands.

        Args:
            name: The relationship, as the user says it.
            force: Whether the reader explicitly asked for a rebuild.

        Returns:
            The debrief after the attempt — the fresh one when this call built
            it, the stored one when somebody else owns the build or today's is
            already there.
        """
        async with get_db_context() as db:
            user = await db.get(User, self.user_id)
            if user is None:
                return RelationDebriefRead(status=DebriefStatus.ABSENT, person=name.strip())
            if not await self._enabled(user):
                return RelationDebriefRead(status=DebriefStatus.DISABLED, person=name.strip())
            key = await self._identity_key(db, name)
            if not key:
                return RelationDebriefRead(status=DebriefStatus.ABSENT, person=name.strip())
            scope = RelationOverviewScope.from_stored(user.relation_overview_scope)
            language = normalize_language(user.language)
            local_date = datetime.now(resolve_user_timezone(user)).date()
            # A snapshot, taken while the session is open: the build spans
            # an LLM round-trip, and a detached ORM instance carried across
            # it is a lazy load waiting to happen.
            author = DebriefAuthor(
                user_id=self.user_id,
                full_name=user.full_name,
                email=user.email,
                journals_enabled=bool(getattr(user, "journals_enabled", False)),
            )
            scope_digest = _digest(scope.model_dump(mode="json"))
            previous = await RelationDebriefRepository(db).get(self.user_id, key)
            owner = await RelationDebriefRepository(db).claim(
                self.user_id,
                name_key=key,
                display_name=name.strip(),
                local_date=local_date,
                language=language,
                scope_digest=scope_digest,
                lease_seconds=settings.relation_debrief_lease_seconds,
                force=force,
            )
            await db.commit()

        if owner is None:
            # Somebody else owns this build, or today's is already settled.
            relation_debrief_builds_total.labels(outcome="declined").inc()
            return await self.read(name)

        return await self._run_build(
            author=author,
            name=name,
            key=key,
            owner=owner,
            scope=scope,
            language=language,
            local_date=local_date,
            # The shortcut below may only reuse a text written under the SAME
            # settings, so the claim's own comparison keys travel with it.
            previous=_Previous.of(previous, language=language, scope_digest=scope_digest),
        )

    async def _run_build(
        self,
        *,
        author: DebriefAuthor,
        name: str,
        key: str,
        owner: UUID,
        scope: RelationOverviewScope,
        language: str,
        local_date: date,
        previous: _Previous,
    ) -> RelationDebriefRead:
        """Publish the consultation collector, then build.

        The collector is a context the build's sources append to, and the flush
        happens on EVERY exit — the shortcut, the refusals and the paid path
        alike — because each of them opened the reader's sources.

        Args:
            author: Who the debrief is written for.
            name: The person, as the reader says it.
            key: The relationship's stable key.
            owner: The claim's owner token.
            scope: What the reader allows a point on this person to read.
            language: The reader's language.
            local_date: The reader's local day.
            previous: What the previous debrief said, for the shortcut.

        Returns:
            The debrief as the reader will see it.
        """
        # Generated HERE, not inside the tracker: the consultations are filed
        # under it, and a run id minted later would leave what the debrief READ
        # pointing at nothing (the reader who reported this found a briefing
        # card at the top of the register and took it for their debrief, which
        # had left no row at all).
        run_id = generate_proactive_run_id(
            RELATION_DEBRIEF_PROACTIVE_TASK_TYPE, hashlib.sha256(key.encode()).hexdigest()[:16]
        )
        async with consultation_collector(run_id):
            return await self._build_within(
                run_id,
                author=author,
                name=name,
                key=key,
                owner=owner,
                scope=scope,
                language=language,
                local_date=local_date,
                previous=previous,
            )

    async def _build_within(
        self,
        run_id: str,
        *,
        author: DebriefAuthor,
        name: str,
        key: str,
        owner: UUID,
        scope: RelationOverviewScope,
        language: str,
        local_date: date,
        previous: _Previous,
    ) -> RelationDebriefRead:
        """Assemble the evidence, write the debrief, settle the claim.

        Every exit settles: a build that raises without closing its own books
        would leave the row ``building`` until its lease expires, and the
        reader staring at a spinner that outlives the request.

        Args:
            run_id: The build's correlation key, shared by what it READ and
                what it COST.
            author: Who the debrief is written for.
            name: The person, as the reader says it.
            key: The relationship's stable key.
            owner: The claim's owner token.
            scope: What the reader allows to be read.
            language: The reader's language.
            local_date: The reader's local day.
            previous: What the previous debrief said, for the shortcut.

        Returns:
            The debrief as the reader will see it.
        """
        started = perf_counter()
        try:
            evidence = await build_overview_evidence(self.user_id, name, scope)
        except OverviewEvidenceUnavailable:
            await self._settle_failed(key, owner)
            relation_debrief_builds_total.labels(outcome="failed").inc()
            return await self.read(name)

        self._record_consultations(run_id, scope, evidence, started)

        payload = overview_payload(evidence)
        if not _has_evidence(payload):
            await self._settle_empty(key, owner, evidence)
            relation_debrief_builds_total.labels(outcome="empty").inc()
            return await self.read(name)

        digest = _digest(payload)
        if (carried := previous.reusable_state(digest)) is not None:
            # Verified, just now, against the whole evidence: nothing changed.
            # The DAY moves; the words keep the date they were written on.
            await self._carry_forward(key, owner, local_date, carried)
            relation_debrief_builds_total.labels(outcome="unchanged").inc()
            return await self.read(name)

        # ONE resolution of the spelling, used for the prompt AND stored: the
        # card's own "properest" name, never whatever the request carried.
        person = evidence.detail.display_name or name.strip()
        try:
            body, usage = await write_debrief(
                author=author,
                person_name=person,
                evidence=payload,
                language=language,
                local_date=local_date,
            )
        except Exception as exc:  # noqa: BLE001 — a failed build is a state, not a crash
            logger.warning(
                "relation_debrief_build_failed",
                user_id=str(self.user_id),
                error_type=type(exc).__name__,
            )
            await self._settle_failed(key, owner)
            relation_debrief_builds_total.labels(outcome="failed").inc()
            return await self.read(name)

        await self._settle_ready(key, owner, evidence, payload, body, digest, person, usage)
        await self._track(usage, key, run_id)
        # Timed on the paid path only: the shortcut and the refusals above cost
        # no model call, and folding them in would flatter the histogram the
        # lease is sized against.
        relation_debrief_build_duration_seconds.observe(perf_counter() - started)
        relation_debrief_builds_total.labels(outcome="ready").inc()
        return await self.read(name)

    def _record_consultations(
        self,
        run_id: str,
        scope: RelationOverviewScope,
        evidence: OverviewEvidence,
        started: float,
    ) -> None:
        """Say which sources this build opened, and which refused.

        Best-effort in full: the debrief is the reader's, and a register that
        can take it down is worse than the gap it closes.

        Args:
            run_id: The build's correlation key.
            scope: What the reader allowed to be read.
            evidence: What came back, including the gaps it names.
            started: ``perf_counter()`` taken before the assembly.
        """
        try:
            from src.domains.relations.overview.consultations import (
                record_evidence_consultations,
            )

            record_evidence_consultations(
                user_id=self.user_id,
                run_id=run_id,
                requested=[section.value for section in OverviewSection if scope.includes(section)],
                unavailable=evidence.unavailable,
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 — observing never breaks the observed
            logger.debug(
                "relation_debrief_consultations_not_recorded",
                run_id=run_id,
                error_type=type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Settling — each opens its own short session
    # ------------------------------------------------------------------

    async def _settle_ready(
        self,
        key: str,
        owner: UUID,
        evidence: OverviewEvidence,
        payload: dict[str, Any],
        body: DebriefBody,
        digest: str,
        person: str,
        usage: LLMUsage,
    ) -> None:
        stored = StoredDebriefBody(**body.model_dump())
        async with get_db_context() as db:
            await RelationDebriefRepository(db).settle_ready(
                self.user_id,
                name_key=key,
                owner=owner,
                display_name=person,
                body=stored.model_dump(mode="json"),
                usage=usage.model_dump(mode="json"),
                evidence_digest=digest,
                sections_used=_sections_of(payload),
                unavailable=list(evidence.unavailable),
                generated_at=datetime.now(UTC),
            )
            await db.commit()

    async def _settle_empty(self, key: str, owner: UUID, evidence: OverviewEvidence) -> None:
        async with get_db_context() as db:
            await RelationDebriefRepository(db).settle_empty(
                self.user_id,
                name_key=key,
                owner=owner,
                sections_used=[],
                unavailable=list(evidence.unavailable),
            )
            await db.commit()

    async def _settle_failed(self, key: str, owner: UUID) -> None:
        cooldown = datetime.now(UTC) + timedelta(
            seconds=settings.relation_debrief_failure_cooldown_seconds
        )
        async with get_db_context() as db:
            await RelationDebriefRepository(db).settle_failed(
                self.user_id, name_key=key, owner=owner, held_until=cooldown
            )
            await db.commit()

    async def _carry_forward(
        self, key: str, owner: UUID, local_date: date, state: DebriefState
    ) -> None:
        async with get_db_context() as db:
            await RelationDebriefRepository(db).carry_forward(
                self.user_id, name_key=key, owner=owner, local_date=local_date, state=state
            )
            await db.commit()

    async def _track(self, usage: Any, key: str, run_id: str) -> None:
        """Bill the call through the SAME path as every other non-chat call.

        A parallel accounting would be one nobody thinks to open. The target is
        the folded identity, never the display name: a target id lands in
        ``token_usage_logs``, and a person's name does not belong there.
        """
        if not (usage.tokens_in or usage.tokens_out):
            return
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        await track_proactive_tokens(
            # The run id the build already filed its consultations under: the
            # cost and what was READ must point at each other, or the register
            # shows a debrief that consulted nothing.
            run_id=run_id,
            user_id=self.user_id,
            task_type=RELATION_DEBRIEF_PROACTIVE_TASK_TYPE,
            target_id=digest,
            conversation_id=None,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache=usage.tokens_cache,
            model_name=usage.model_name,
            # The SLOT, not only the task: an operator reading the usage log can
            # then attribute a cost to the configuration that produced it, and
            # the Article-12 export reads this column (ADR-263 lot 7).
            llm_type=RELATION_DEBRIEF_LLM_TYPE,
            source="user",
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    async def _identity_key(self, db: Any, name: str) -> str:
        """The canonical folded identity, merges applied.

        The SAME resolution the card and the tools use: a debrief keyed on
        anything else would describe a person the CRM does not have.
        """
        rows = await RelationAliasRepository(db).list_for_user(self.user_id)
        resolver = IdentityResolver.from_pairs([(row.alias_key, row.canonical_key) for row in rows])
        return resolver.key(name)
