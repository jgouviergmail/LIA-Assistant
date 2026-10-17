"""Generate public capture fixtures through the production HTML renderer.

Run with the backend virtualenv. No provider, account, backend server or .env
is needed. All payloads below are fictional; socket connections are forbidden.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch

FIXTURE_TIME = "2026-10-12T07:30:00Z"


def event(title: str, start: str, end: str, location: str, description: str) -> dict:
    """A complete synthetic Calendar event in the real provider wire shape."""
    return {
        "id": title.lower().replace(" ", "-"),
        "summary": title,
        "start": {"dateTime": start, "timeZone": "Europe/Paris"},
        "end": {"dateTime": end, "timeZone": "Europe/Paris"},
        "location": location,
        "description": description,
        "status": "confirmed",
        "visibility": "private",
        "transparency": "opaque",
        "htmlLink": "https://example.test/calendar/" + title.lower().replace(" ", "-"),
        "organizer": {"displayName": "Morgan Demo", "email": "morgan@example.test"},
        "attendees": [
            {
                "displayName": "Alex Demo",
                "email": "alex@example.test",
                "self": True,
                "responseStatus": "accepted",
            },
            {
                "displayName": "Morgan Demo",
                "email": "morgan@example.test",
                "responseStatus": "accepted",
                "organizer": True,
            },
            {
                "displayName": "Sam Demo",
                "email": "sam@example.test",
                "responseStatus": "tentative",
            },
        ],
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 15}],
        },
        "guestsCanModify": False,
        "guestsCanInviteOthers": True,
        "guestsCanSeeOtherGuests": True,
    }


def payloads() -> dict:
    agenda = [
        event(
            "Design review",
            "2026-10-12T10:00:00+02:00",
            "2026-10-12T11:00:00+02:00",
            "Demo Studio — meeting room A",
            "Review the new concept, collect feedback and agree on the next design iteration. Bring the annotated prototype and the accessibility checklist.",
        ),
        event(
            "Project check-in",
            "2026-10-12T14:30:00+02:00",
            "2026-10-12T15:00:00+02:00",
            "Video call",
            "Share progress, surface blockers and confirm the owners of this week’s follow-ups. Demonstration meeting; no invitation has been sent.",
        ),
    ]
    files = [
        {
            "id": "proof-brief",
            "name": "Launch plan.pdf",
            "mimeType": "application/pdf",
            "size": 420000,
            "modifiedTime": "2026-10-09T12:00:00Z",
            "owners": [
                {"displayName": "Alex Demo", "emailAddress": "alex@example.test"}
            ],
            "shared": True,
            "webViewLink": "https://example.test/documents/launch-plan",
            "parentPath": "Project Atlas / Planning",
            "description": "Approved scope and launch checklist. Target delivery: 19 October. Supplier confirmation is still required.",
        },
    ]
    email = {
        "id": "proof-supplier-date",
        "_provider": "microsoft",
        "webLink": "https://example.test/mail/supplier-date",
        "from": {"name": "Atlas supplier · demo", "email": "supplier@example.test"},
        "to": [{"name": "Alex Demo", "email": "alex@example.test"}],
        "subject": "Atlas delivery date · 22 October proposed",
        "date": "2026-10-09T13:30:00Z",
        "snippet": "We can currently commit to 22 October. Please confirm whether the launch brief can be updated from 19 October.",
        "body": "Hello Alex,\n\nWe can currently commit to 22 October. Please confirm whether the launch brief can be updated from 19 October. The agreed scope and checklist remain unchanged.\n\nThank you,\nThe demo supplier team",
        "labelIds": ["INBOX"],
        "unread": False,
        "threadCount": 2,
    }
    review = event(
        "Atlas launch review",
        "2026-10-12T10:00:00+02:00",
        "2026-10-12T10:30:00+02:00",
        "Demo Studio — meeting room A",
        "Confirm the supplier delivery date: the brief targets 19 October; the supplier proposes 22 October. Review Morgan’s revised launch checklist before sharing a commitment.",
    )
    return {
        "publicAgenda": {"events": agenda},
        "dossier": {
            "files": {"files": files},
            "emails": {"emails": [email]},
        },
        "meetingContext": {"events": [review]},
    }


def render(repo: Path) -> dict:
    # Imports happen only after main() removed inherited credentials and moved
    # into an empty directory; settings cannot discover a workspace .env.
    from src.domains.agents.display.config import DisplayConfig
    from src.domains.agents.display.html_renderer import HtmlRenderer

    class CaptureDateTimeMeta(type):
        def __instancecheck__(cls, instance):
            # Provider parsing returns ordinary datetime objects. Keep the
            # renderer's real type checks valid while freezing only now().
            return isinstance(instance, datetime)

    class CaptureDateTime(datetime, metaclass=CaptureDateTimeMeta):
        @classmethod
        def now(cls, tz=None):
            frozen = datetime.fromisoformat(FIXTURE_TIME.replace("Z", "+00:00"))
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    inputs = payloads()
    renderer = HtmlRenderer()
    config = DisplayConfig(
        language="en", timezone="Europe/Paris", max_items_per_domain=5
    )
    with patch("src.domains.agents.display.components.base.datetime", CaptureDateTime):
        agenda = renderer.render("events", inputs["publicAgenda"], config)
        dossier = renderer.render_multi(inputs["dossier"], config)
    if "10:00 AM - 11:00 AM" not in agenda or "2:30 PM - 3:00 PM" not in agenda:
        raise RuntimeError(
            "Native appointment time formatting must match the real renderer"
        )
    sources = sorted((repo / "apps/api/src/domains/agents/display").rglob("*.py"))
    return {
        "fixtureTime": FIXTURE_TIME,
        "language": "en",
        "timezone": "Europe/Paris",
        "publicAgendaHtml": agenda,
        "dossierHtml": dossier,
        "payloads": inputs,
        "renderers": [
            {
                "source": source.relative_to(repo).as_posix(),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            for source in sources
        ],
        "policy": "Production HtmlRenderer.render(events) and HtmlRenderer.render_multi(files/emails), without editing their HTML. Fictional complete provider-shaped inputs. The capture clock is fixed; inherited environment removed; empty cwd; socket connections forbidden. No account, provider call, backend server, credential file or .env read.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed fixture without writing it",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    target = repo / "apps/web/e2e/fixtures/native-cards.json"
    sys.path.insert(0, str(repo / "apps/api"))
    retained = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    os.environ.clear()
    os.environ.update(retained)
    os.environ.update(
        SECRET_KEY="public-capture-placeholder-key-000000000000",
        FERNET_KEY=base64.urlsafe_b64encode(bytes(32)).decode(),
        DATABASE_URL="postgresql+asyncpg://capture:capture@127.0.0.1:1/capture",
        REDIS_URL="redis://127.0.0.1:1/0",
        ENVIRONMENT="test",
        OTEL_SDK_DISABLED="true",
    )

    def deny_connection(*_args, **_kwargs):
        raise RuntimeError(
            "Network connections are forbidden while rendering capture fixtures"
        )

    temporary_root = repo / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="lia-native-cards-", dir=temporary_root
    ) as empty:
        if not Path(empty).resolve().is_relative_to(temporary_root.resolve()):
            raise RuntimeError("Temporary renderer directory escaped the workspace")
        previous_cwd = Path.cwd()
        try:
            os.chdir(empty)
            with patch.object(socket.socket, "connect", deny_connection), patch.object(
                socket, "create_connection", deny_connection
            ):
                rendered = render(repo)
        finally:
            os.chdir(previous_cwd)
        encoded = json.dumps(rendered, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if target.read_text(encoding="utf-8") != encoded:
                raise SystemExit(
                    "Native card fixtures differ; rerun render_native_cards.py"
                )
            print("Native cards reproduce exactly through the production renderer.")
        else:
            target.write_text(encoded, encoding="utf-8", newline="\n")
            print(f"Generated {target}")


if __name__ == "__main__":
    main()
