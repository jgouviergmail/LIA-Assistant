"""Read-only diagnostic: would a moment be produced for this account, right now?

Reads the calendar exactly as the detector does, and prints what it WOULD file.
Nothing is written: no row, no notification, no consultation record — the
product path (``_detect_for``) is deliberately not used, so running this leaves
the person's register untouched.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Run as `python scripts/moments/preflight.py` from apps/api, exactly like the
# catalogue preflight beside it: Python puts the SCRIPT's directory on the path,
# never the package root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.infrastructure.database.registry import import_all_models  # noqa: E402

import_all_models()

from sqlalchemy import select  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.core.time_utils import resolve_user_timezone  # noqa: E402
from src.domains.connectors.calendar_access import (  # noqa: E402
    CalendarAccess,
    open_active_calendar,
)
from src.domains.moments.calendar_reading import event_instant  # noqa: E402
from src.domains.moments.detectors.event_followup import (  # noqa: E402
    _EVENT_FIELDS,
    _local_context,
    detect,
    is_chained,
)
from src.domains.moments.importance import score_event  # noqa: E402
from src.domains.moments.models import ProactiveMoment  # noqa: E402
from src.domains.moments.preferences import disabled_kinds_for  # noqa: E402
from src.domains.users.models import User  # noqa: E402
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.proactive.eligibility import is_within_hour_window  # noqa: E402


async def main() -> None:
    now = datetime.now(UTC)
    print(f"== Instant de la passe : {now.isoformat()} ==\n")

    async with get_db_context() as db:
        users = (
            (
                await db.execute(
                    select(User).where(User.is_active.is_(True), User.heartbeat_enabled.is_(True))
                )
            )
            .scalars()
            .all()
        )

    if not users:
        print("Aucun compte avec le battement activé : le balayage ne fera rien.")
        return

    for user in users:
        tz = resolve_user_timezone(user)
        local = now.astimezone(tz)
        in_window = is_within_hour_window(
            local.hour, user.heartbeat_notify_start_hour, user.heartbeat_notify_end_hour
        )
        print(f"--- compte {str(user.id)[:8]} ---")
        print(f"  heure locale     : {local:%H:%M} ({tz})")
        print(
            f"  fenetre          : {user.heartbeat_notify_start_hour}-"
            f"{user.heartbeat_notify_end_hour} -> {'DANS' if in_window else 'HORS'} fenetre"
        )
        print(f"  genres refuses   : {sorted(disabled_kinds_for(user)) or 'aucun'}")

        # The calendar, read exactly as the detector reads it.
        lookback = timedelta(minutes=settings.moments_detect_lookback_minutes)
        gap = timedelta(minutes=settings.moments_event_chain_gap_minutes)
        try:
            async with get_db_context() as db, open_active_calendar(db, user.id) as access:
                if not isinstance(access, CalendarAccess):
                    print(f"  calendrier       : INDISPONIBLE ({access})\n")
                    continue
                result = await access.client.list_events(
                    time_min=(now - lookback).isoformat(),
                    time_max=(now + gap).isoformat(),
                    max_results=25,
                    calendar_id=access.calendar_id,
                    fields=_EVENT_FIELDS,
                )
        except Exception as exc:
            print(f"  calendrier       : ILLISIBLE ({type(exc).__name__}: {exc})\n")
            continue

        events = [e for e in (result.get("items") or []) if isinstance(e, dict)]
        print(
            f"  fenetre lue      : -{settings.moments_detect_lookback_minutes} min "
            f"a +{settings.moments_event_chain_gap_minutes} min -> {len(events)} evenement(s)"
        )

        local_ctx = await _local_context(user.id, since=now - lookback)
        for event in events:
            end = event_instant(event.get("end"), tz)
            title = str(event.get("summary") or "(sans titre)")[:48]
            if end is None:
                print(f"    . {title:<48} date illisible")
                continue
            if end > now:
                print(f"    . {title:<48} pas encore terminee (brise-bloc)")
                continue
            verdict = score_event(
                event,
                user_email=user.email,
                favorite_keys=local_ctx.favorites,
                linked_keys=local_ctx.linked,
                user_tz=tz,
            )
            chained = is_chained(
                event,
                events,
                user_tz=tz,
                gap_minutes=settings.moments_event_chain_gap_minutes,
            )
            if chained:
                why = "enchainee (le bloc continue)"
            elif str(event.get("id")) in local_ctx.recorded:
                why = "deja enregistree par LIA"
            elif not verdict.worthy:
                why = f"score {verdict.score} < {settings.moments_event_followup_min_score}"
                if verdict.blocked_by:
                    why = f"ecartee : {verdict.blocked_by.value}"
            else:
                due = end + timedelta(minutes=settings.moments_event_followup_delay_minutes)
                why = f"RETENUE score={verdict.score} due a {due.astimezone(tz):%H:%M}"
            print(f"    . {title:<48} {why}")

        candidates = await detect(user, now)
        print(f"  => le detecteur deposerait : {len(candidates)} moment(s)")
        for candidate in candidates:
            print(
                f"     {candidate.source_ref[:24]} due={candidate.due_at.astimezone(tz):%H:%M} "
                f"jusqu_a={candidate.not_after.astimezone(tz):%H:%M} "
                f"score={candidate.payload.get('score')}"
            )

        async with get_db_context() as db:
            rows = (
                (
                    await db.execute(
                        select(ProactiveMoment).where(ProactiveMoment.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )
        print(f"  moments en base  : {len(rows)}")
        for row in rows:
            print(
                f"     {row.kind} {row.state} due={row.due_at.astimezone(tz):%d/%m %H:%M} "
                f"skip={row.skip_reason or '-'}"
            )
        print()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
