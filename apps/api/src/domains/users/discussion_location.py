"""The native location cascade, with coordinates confined to mechanical provider parameters."""

import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import load_only

from src.core.read_budget import mark_read_opened
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.active_reader import require_active_owner_read
from src.domains.users.models import User
from src.domains.users.user_location_service import NoLocationAvailableError, UserLocationService
from src.infrastructure.database.session import get_db_context


class LocationFocus(DiscussionValue):
    """The place LIA may use now, where it comes from, and until when it holds."""

    lat: float
    lon: float
    origin: str
    expires_at: datetime


async def read_location_focus(owner: UUID, *, now: datetime) -> LocationFocus | None:
    """Return the person's effective place for proactive use, valid fifteen minutes.

    Args:
        owner: The account.
        now: The current instant.

    Returns:
        The place, or None when no location is available.

    Raises:
        AuthorizationError: The account is inactive or deleted.
    """
    async with get_db_context() as db:
        await require_active_owner_read(db, owner)
        user = await db.scalar(
            select(User)
            .where(User.id == owner)
            .options(
                load_only(
                    User.id,
                    User.home_location_encrypted,
                    User.last_known_location_encrypted,
                    User.last_known_location_updated_at,
                    User.use_last_known_location,
                )
            )
        )
        if user is None:
            return None
        mark_read_opened(owner)
        try:
            location = await UserLocationService(db).get_effective_location_for_proactive(user)
        except NoLocationAvailableError:
            return None
        return LocationFocus(
            lat=location.lat,
            lon=location.lon,
            origin=location.source,
            expires_at=now + timedelta(minutes=15),
        )


class LocationDiscussionSource:
    """Whether the person's place is a configured home or a recent consented position."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read the qualification of the person's current place, never its coordinates.

        Args:
            request: The bounded read.

        Returns:
            The page; empty without a place, closed when location is not consented.

        Raises:
            ValueError: The request is for another source.
        """
        if request.request.source != SourceKey.LOCATION:
            raise ValueError("location source mismatch")
        if SourceKey.LOCATION not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        focus = await read_location_focus(request.owner_id, now=request.now)
        if focus is None:
            return source_snapshot(request, status="empty", total=0, coverage_kind="signal")
        # A configured domicile is not evidence of present whereabouts. No address or GPS in model inputs.
        text = json.dumps(
            {
                "qualification": (
                    "configured_home" if focus.origin == "home" else "recent_consented_location"
                ),
                "city": None,
            },
            separators=(",", ":"),
        )
        item = DiscussionEvidence(
            reference="location:effective",
            source=SourceKey.LOCATION,
            object_id="effective",
            version=semantic_version((focus.origin, f"{focus.lat:.2f}", f"{focus.lon:.2f}")),
            observed_at=request.now,
            expires_at=focus.expires_at,
            assertion="reported" if focus.origin == "home" else "observed",
            excerpt=text,
        )
        return source_snapshot(request, status="ok", items=(item,), total=1, coverage_kind="signal")
