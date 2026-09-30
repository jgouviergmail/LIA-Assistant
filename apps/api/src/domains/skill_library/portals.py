"""The portals a person searches for skills (ADR-327): skills.sh today.

A portal is an INDEX: it names a skill, the source it lives at and how often
it was installed, and it publishes audits. It never serves the files — those
are read from the origin (``github.py``) at an exact commit. A second portal is
one more :class:`Portal` in :data:`PORTALS`; nothing else branches on a name.

What a portal says is a stranger's text: every field is type-checked and
bounded here, a malformed entry is dropped rather than repaired, and nothing
of it is ever sent to a model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final, Protocol
from urllib.parse import urlencode

import httpx
import structlog

from src.core.config import settings
from src.domains.skill_library import cache
from src.domains.skill_library.errors import RATE_LIMITED, UNREACHABLE, LibraryRefusal
from src.domains.skill_library.github import valid_repository
from src.domains.skill_library.http import FetchOutcome, fetch

logger = structlog.get_logger(__name__)

#: The key stored with a skill found on skills.sh.
PORTAL_SKILLS_SH: Final = "skills_sh"
#: The audit risks, least to most severe; ``unknown`` is no verdict at all.
RISKS: Final = ("safe", "low", "medium", "high", "critical")
UNKNOWN_RISK: Final = "unknown"
#: Bounds on what a portal may say (display fields, not identities).
_TEXT_MAX: Final = 200
_ID_MAX: Final = 300


@dataclass(frozen=True)
class PortalEntry:
    """One skill a portal listed.

    Attributes:
        registry_id: The portal's own identifier.
        name: The name it shows.
        source: Where it says the skill lives (``owner/repo`` or a site's host).
        skill_id: The skill's identifier inside its source.
        installs: How often the portal counted it installed.
        repository: The GitHub repository, when the source is one (else None:
            an origin LIA does not read).
    """

    registry_id: str
    name: str
    source: str
    skill_id: str
    installs: int
    repository: str | None


@dataclass(frozen=True)
class AuditVerdict:
    """What one audit provider said about one skill."""

    provider: str
    risk: str
    alerts: int


class Portal(Protocol):
    """What the library asks of a portal."""

    async def search(
        self, client: httpx.AsyncClient, query: str, limit: int
    ) -> list[PortalEntry]: ...

    async def audit(
        self, client: httpx.AsyncClient, repository: str, skill_ids: list[str]
    ) -> dict[str, list[AuditVerdict]] | None: ...


def _text(value: Any, limit: int = _TEXT_MAX) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    return value.strip()


def _entry(raw: Any) -> PortalEntry | None:
    """One search result, or None when any field is not what it must be."""
    if not isinstance(raw, dict):
        return None
    registry_id, source = _text(raw.get("id"), _ID_MAX), _text(raw.get("source"))
    skill_id, name = _text(raw.get("skillId")), _text(raw.get("name"))
    installs = raw.get("installs", 0)
    if not (registry_id and source and skill_id and name) or not isinstance(installs, int):
        return None
    repository = source if valid_repository(source) else None
    return PortalEntry(registry_id, name, source, skill_id, max(installs, 0), repository)


def _verdicts(raw: Any) -> list[AuditVerdict]:
    """The providers' verdicts on one skill; an unknown risk word reads as unknown."""
    if not isinstance(raw, dict):
        return []
    verdicts = []
    for provider, report in raw.items():
        if not isinstance(provider, str) or not isinstance(report, dict):
            continue
        risk = report.get("risk")
        alerts = report.get("alerts")
        verdicts.append(
            AuditVerdict(
                provider=provider[:_TEXT_MAX],
                risk=risk if risk in RISKS else UNKNOWN_RISK,
                alerts=len(alerts) if isinstance(alerts, list) else 0,
            )
        )
    return verdicts


def blocking_risk(verdicts: list[AuditVerdict], level: str) -> str | None:
    """The most severe risk at or above ``level``, or None when nothing blocks.

    Args:
        verdicts: What the providers said.
        level: The instance's refusal level (``none`` never refuses).

    Returns:
        The risk that refuses the install, or None.
    """
    if level not in RISKS:
        return None
    floor = RISKS.index(level)
    found = [RISKS.index(v.risk) for v in verdicts if v.risk in RISKS]
    worst = max(found, default=-1)
    return RISKS[worst] if worst >= floor else None


class SkillsShPortal:
    """skills.sh: an anonymous search route and the CLI's audit service."""

    async def search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[PortalEntry]:
        """The portal's answer to ``query`` (cached briefly, shared by every account).

        Raises:
            LibraryRefusal: When the portal cannot be read.
        """
        base = settings.skill_library_portal_url.rstrip("/")
        key = cache.cache_key("search", base, query.casefold(), str(limit))
        answer_json = await cache.cached(key)
        if answer_json is None:
            answer = await fetch(
                client, f"{base}/api/search?{urlencode({'q': query, 'limit': limit})}"
            )
            if answer.outcome is FetchOutcome.RATE_LIMITED:
                raise LibraryRefusal(RATE_LIMITED, reset_at=answer.reset_at)
            if answer.outcome is not FetchOutcome.OK:
                raise LibraryRefusal(UNREACHABLE)
            try:
                answer_json = json.loads(answer.body)
            except ValueError as exc:
                raise LibraryRefusal(UNREACHABLE) from exc
            await cache.store(key, answer_json, settings.skill_library_cache_ttl_seconds)
        skills = answer_json.get("skills") if isinstance(answer_json, dict) else None
        entries = [e for e in (_entry(raw) for raw in skills or []) if e is not None]
        return entries[:limit]

    async def audit(
        self, client: httpx.AsyncClient, repository: str, skill_ids: list[str]
    ) -> dict[str, list[AuditVerdict]] | None:
        """The audits of ``skill_ids`` in ``repository``; None when none could be read.

        An audit service that cannot be read refuses nothing: its verdicts are
        advice, the isolation of a third-party skill is the protection.
        """
        base = settings.skill_library_audit_url.strip()
        if not base or not skill_ids:
            return None
        url = f"{base}?{urlencode({'source': repository, 'skills': ','.join(skill_ids)})}"
        answer = await fetch(client, url)
        if answer.outcome is not FetchOutcome.OK:
            logger.info("skill_library_audit_unavailable", outcome=answer.outcome.value)
            return None
        try:
            raw = json.loads(answer.body)
        except ValueError:
            return None
        if not isinstance(raw, dict):
            return None
        return {skill: _verdicts(raw.get(skill)) for skill in skill_ids}


#: Every portal the library searches, by the key stored with what it installed.
PORTALS: Final[dict[str, Portal]] = {PORTAL_SKILLS_SH: SkillsShPortal()}
DEFAULT_PORTAL: Final = PORTAL_SKILLS_SH
