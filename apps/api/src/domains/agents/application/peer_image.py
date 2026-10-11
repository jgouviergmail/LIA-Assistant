"""Source copy/quota/ledger reuse with exact consent and acknowledged durability."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    BaseAPIException,
    ResourceConflictError,
    raise_not_found_or_unauthorized,
)
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_image_schemas import (
    PeerImageInput,
    PeerImagePatch,
    PeerImageSelection,
)
from src.domains.agents.application.peer_image_spec import PEER_IMAGE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.image_share import (
    ImageShareCommitUnknown,
    _clean_comment,
    _shareable_source,
    _source_file,
    deliver_shared_image,
    share_image,
)
from src.domains.peers.models import PeerConnection, PeerImageShare
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.users.preference_cas import PreferenceWriteReceipt


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


async def _image_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _image_selection(
    db: AsyncSession, actor_id: UUID, request: PeerImageInput, *, lock: bool = False
) -> PeerImageSelection:
    card = next(
        (
            row
            for row in await PeersService(db).get_connections(actor_id)
            if row.id == request.connection_id
        ),
        None,
    )
    if card is None:
        raise_not_found_or_unauthorized("peer", request.connection_id)
    assert card is not None
    pair_query = select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
        PeerConnection.id == card.id
    )
    image_query = select(func.to_jsonb(Attachment.__table__.table_valued())).where(
        Attachment.id == request.attachment_id, Attachment.user_id == actor_id
    )
    if lock:
        pair_query = pair_query.with_for_update()
        image_query = image_query.with_for_update()
    pair = await db.scalar(pair_query)
    image = await db.scalar(image_query)
    await db.execute(
        select(Attachment)
        .where(Attachment.id == request.attachment_id)
        .execution_options(populate_existing=True)
    )
    source = await _shareable_source(db, actor_id, request.attachment_id, datetime.now(UTC))
    digest = await asyncio.to_thread(_file_digest, _source_file(source))
    return PeerImageSelection(
        request=request,
        peer_id=card.peer_id,
        display_name=card.peer_display_name,
        email_hint=card.peer_email_hint,
        title=source.title,
        state_digest=payload_digest({"pair": pair, "image": image}),
        file_digest=digest,
    )


async def prepare_peer_image(
    db: AsyncSession, actor_id: UUID, request: PeerImageInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerImageInput.model_validate(request.model_dump())
    selected = selected.model_copy(update={"comment": _clean_comment(selected.comment)})
    await _image_access(db, actor_id)
    scope = await _image_selection(db, actor_id, selected)
    await _image_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_IMAGE_OPERATION,
        PeerImagePatch(peer_image=scope),
        {"peer_image": scope.public_scope()},
        {"peer_image": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_image(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerImagePatch.model_validate(draft.intent).peer_image
    return draft.before == {"peer_image": scope.public_scope()} and draft.after == {
        "peer_image": scope.public_scope(after=True)
    }


async def _verify_image_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerImageSelection
) -> None:
    try:
        current = await _image_selection(db, actor_id, expected.request, lock=True)
    except (BaseAPIException, OSError) as exc:
        raise ResourceConflictError("peer_image", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_image", detail={"error_code": "STALE_STATE"})


async def _verify_saved_copy(
    db: AsyncSession,
    actor_id: UUID,
    expected: PeerImageSelection,
    copy: Attachment,
    share: PeerImageShare,
    target: Path,
) -> None:
    stored_copy = await db.scalar(
        select(func.to_jsonb(Attachment.__table__.table_valued())).where(Attachment.id == copy.id)
    )
    stored_share = await db.scalar(
        select(func.to_jsonb(PeerImageShare.__table__.table_valued())).where(
            PeerImageShare.id == share.id
        )
    )
    if stored_copy is None or stored_share is None:
        raise ValueError("Source image and ledger must actually be persisted")
    source = await db.get(Attachment, expected.request.attachment_id, populate_existing=True)
    if source is None:
        raise ValueError("Approved source image must still exist")
    approved_share = {
        "sender_id": str(actor_id),
        "recipient_id": str(expected.peer_id),
        "connection_id": str(expected.request.connection_id),
        "attachment_id": str(copy.id),
    }
    if any(stored_share[key] != value for key, value in approved_share.items()):
        raise ValueError("Source copied image differs from the approved recipient")
    approved_copy = {
        "user_id": str(expected.peer_id),
        "title": expected.title,
        "origin": AttachmentOrigin.GENERATED_IMAGE.value,
        "status": AttachmentStatus.READY,
        "file_size": source.file_size,
        "mime_type": source.mime_type,
    }
    if any(stored_copy[key] != value for key, value in approved_copy.items()):
        raise ValueError("Source recipient gallery differs from approved image")
    actual_copy = await db.scalar(
        select(Attachment).where(Attachment.id == copy.id).execution_options(populate_existing=True)
    )
    if actual_copy is None or _source_file(actual_copy) != target.resolve():
        raise ValueError("Source gallery must point to the copied file")
    if actual_copy.expires_at is None or actual_copy.expires_at <= datetime.now(UTC):
        raise ValueError("The recipient copy must have its own live expiry")
    if await asyncio.to_thread(_file_digest, target) != expected.file_digest:
        raise ValueError("Source copied bytes differ from the approved image")


async def execute_peer_image(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if actor_id != draft.actor_id or draft.operation_id != "peer_image.share":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_image(draft):
        raise ValueError("Sharing requires exact recipient, image and comment approval")
    expected = PeerImagePatch.model_validate(draft.intent).peer_image

    async def check() -> None:
        await _image_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.peer_id)
    await check()
    await _verify_image_selection(db, actor_id, expected)

    async def commit(
        session: AsyncSession, copy: Attachment, share: PeerImageShare, target: Path
    ) -> None:
        await _verify_image_selection(session, actor_id, expected)
        await _verify_saved_copy(session, actor_id, expected, copy, share, target)
        await check()
        try:
            await session.commit()
        except (Exception, asyncio.CancelledError) as exc:
            raise ImageShareCommitUnknown("Image share commit was not acknowledged") from exc
        receipt.committed = True

    try:
        shared = await share_image(
            db,
            sender_id=actor_id,
            connection_id=expected.request.connection_id,
            attachment_id=expected.request.attachment_id,
            comment=expected.request.comment,
            commit=commit,
            record_user_action=False,
        )
    except ImageShareCommitUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    public = {
        **expected.public_scope(after=True),
        "share_id": str(shared.share_id),
        "recipient_attachment_id": str(shared.attachment_id),
        "delivered": False,
    }
    receipt.values = {"peer_image": public}
    public["delivered"] = await deliver_shared_image(shared)
