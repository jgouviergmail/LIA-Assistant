"""Fresh native delivery authority; dispatch can never start paid source work."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import TypeAdapter

from src.core.config import settings
from src.core.constants import DISCUSSION_OPENING_PROOFS_MAX
from src.core.read_budget import ReadCallBudget, ReadCallLimit
from src.domains.connectors.discussion_authority import (
    is_selected_discussion_connector,
    read_connector_scope,
)
from src.domains.connectors.discussion_weather import open_discussion_weather
from src.domains.connectors.models import ConnectorType
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import (
    RESEARCH_FUTURE_DAYS_MAX,
    RESEARCH_HISTORY_DAYS_MAX,
    DiscussionEvidence,
    SourceKey,
    SourceSnapshot,
    semantic_version,
)
from src.domains.users.discussion_location import read_location_focus
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.discussion_proofs import hydrate_proofs
from src.infrastructure.proactive.discussion_sources import discussion_readers

_PROOFS = TypeAdapter(tuple[ContextEvidenceLink, ...])
_CONNECTORS = frozenset({SourceKey.CALENDAR, SourceKey.EMAILS, SourceKey.CONTACTS, SourceKey.TASKS})


class NoExternalCalls(ReadCallBudget):
    """A read budget refusing every physical request: delivery reads native rows only."""

    def claim(self, owner: UUID) -> None:
        """Refuse the request.

        Raises:
            ReadCallLimit: Always; delivery never starts a provider request.
        """
        raise ReadCallLimit("delivery cannot initiate provider requests")


async def delivery_sources_permitted(owner: UUID, run: UUID, raw: object) -> bool:
    """Whether an opening's proofs still authorise its delivery now.

    Every proof must be current and come from a source still allowed with
    consented topics; native proofs are read again without any provider request
    and must all still exist; connector and weather proofs must be recent and
    from the connector still selected, the same account or the same place; and
    every proof must pass the person's current controls.

    Args:
        owner: The account.
        run: The run that published the opening.
        raw: The opening's recorded proofs.

    Returns:
        True when the delivery may go out.
    """
    proofs = _PROOFS.validate_python(raw)
    now = datetime.now(UTC)
    if not current_proofs(proofs, now):
        return False

    policy = await delivery_policy(owner)
    allowed = effective_sources(policy, frozenset(SourceKey))
    if not sources_allowed(policy, proofs):
        return False
    native = tuple(
        proof
        for proof in proofs
        if proof.source not in _CONNECTORS and proof.source != SourceKey.WEATHER
    )
    gateway = SourceGateway(
        discussion_readers(), delivery_policy, call_budget=NoExternalCalls(owner=owner, limit=1)
    )
    claim = RunClaim(
        owner_id=owner,
        run_id=run,
        policy_revision=policy.revision,
        context_epoch=0,
        fence=1,
        lease_until=now + timedelta(minutes=1),
    )
    pages = await hydrate_proofs(claim, native, gateway, now=now)
    if len({item.reference for page in pages for item in page.items}) != len(native):
        return False
    if not await connector_proofs_permitted(owner, proofs, now):
        return False
    checks = tuple(_admission_evidence(proof) for proof in proofs)
    synthetic = tuple(
        SourceSnapshot(
            source=item.source,
            owner_id=owner,
            status="ok",
            read_at=now,
            window_start=now - timedelta(days=RESEARCH_HISTORY_DAYS_MAX),
            window_end=now + timedelta(days=RESEARCH_FUTURE_DAYS_MAX),
            complete=False,
            items=(item,),
        )
        for item in checks
    )
    async with get_db_context() as db:
        admitted = await ContextRepository(db).filter_inputs(
            owner,
            synthetic,
            allowed_sources=allowed,
            allowed_topics=frozenset(policy.sensitive_topics),
            now=now,
        )
    return len(admitted) == len(proofs)


def current_proofs(proofs: tuple[ContextEvidenceLink, ...], now: datetime) -> bool:
    """Whether there are one to ``DISCUSSION_OPENING_PROOFS_MAX`` proofs, none expired."""
    return (
        bool(proofs)
        and len(proofs) <= DISCUSSION_OPENING_PROOFS_MAX
        and all(proof.expires_at > now for proof in proofs)
    )


async def delivery_policy(identity: UUID) -> DiscussionPolicy:
    """Read the account's current policy in a short session of its own."""
    async with get_db_context() as db:
        return await DiscussionRepository(db).get_policy(identity)


def sources_allowed(policy: DiscussionPolicy, proofs: tuple[ContextEvidenceLink, ...]) -> bool:
    """Whether every proof's source, dependencies and topics are still allowed."""
    allowed = effective_sources(policy, frozenset(SourceKey))
    return not any(
        proof.source not in allowed
        or not set(proof.required_sources) <= allowed
        or not set(proof.sensitive_topics) <= set(policy.sensitive_topics)
        for proof in proofs
    )


def _admission_evidence(proof: ContextEvidenceLink) -> DiscussionEvidence:
    values = {
        key: value
        for key, value in proof.model_dump().items()
        if key in DiscussionEvidence.model_fields
    }
    return DiscussionEvidence.model_validate(
        {**values, "excerpt": "Native delivery authority check"}
    )


async def _weather_permitted(owner: UUID, proof: ContextEvidenceLink, now: datetime) -> bool:
    if proof.observed_at < now - timedelta(
        minutes=settings.discussion_delivery_proof_max_age_minutes
    ):
        return False
    focus = await read_location_focus(owner, now=now)
    if focus is None:
        return False
    async with open_discussion_weather(owner) as client:
        return client is not None and proof.source_account == semantic_version(
            (type(client).__name__, f"{focus.lat:.5f}", f"{focus.lon:.5f}")
        )


async def connector_proofs_permitted(
    owner: UUID, proofs: tuple[ContextEvidenceLink, ...], now: datetime
) -> bool:
    """Whether the connector and weather proofs still hold now.

    A connector proof must be younger than ``discussion_delivery_proof_max_age_minutes``
    and come through the connector still selected for its source, on the same account;
    a weather proof must be as recent and for the same place.

    Args:
        owner: The account.
        proofs: The opening's proofs.
        now: The current instant.

    Returns:
        True when none of them fails.
    """
    for proof in proofs:
        if proof.source in _CONNECTORS:
            if proof.observed_at < now - timedelta(
                minutes=settings.discussion_delivery_proof_max_age_minutes
            ):
                return False
            kind = ConnectorType(proof.source_account.split(":", 1)[0])
            if not await is_selected_discussion_connector(owner, proof.source, kind):
                return False
            if not proof.source_account.startswith(await read_connector_scope(owner, kind) + ":"):
                return False
        elif proof.source == SourceKey.WEATHER:
            if not await _weather_permitted(owner, proof, now):
                return False
    return True
