"""What each registered domain allows a recurring need to become (ADR-375).

One decision per domain of the agents' registry, declared here and held
complete at boot (``assert_need_domains_complete``, ADR-085): a domain added
later without a decision refuses to boot rather than silently never proposing.

- ``automatable``: a recurring need on this domain may become a proposal to
  automate it. Only STATE READS qualify — the person's agenda, mail, tasks,
  weather, health, SMS — because their routine is a fixed sentence about
  « today » that needs no parameter the person would have to choose. A search,
  a place or a route needs its subject: proposing it blind would be a guess.
- ``connector_category``: the connector category a need on this domain
  depends on, so a need asked with no active connector becomes a proposal to
  connect one. Weather has none: the keyless instance default answers it
  (ADR-307).

``habits`` imports nothing from ``agents`` (the coupling ratchet): the registry
is handed to the guard by the boot step, never imported here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True, slots=True)
class NeedDomain:
    """One domain's decision.

    Attributes:
        automatable: Whether a recurring need on it may be proposed as a routine.
        connector_category: The connector category its asks depend on, if any.
    """

    automatable: bool = False
    connector_category: str | None = None


_NOTHING = NeedDomain()

NEED_DOMAINS: Final[Mapping[str, NeedDomain]] = MappingProxyType(
    {
        # State reads: a fixed sentence about today, nothing to choose.
        "event": NeedDomain(automatable=True, connector_category="calendar"),
        "email": NeedDomain(automatable=True, connector_category="email"),
        "task": NeedDomain(automatable=True, connector_category="tasks"),
        "weather": NeedDomain(automatable=True),
        "health": NeedDomain(automatable=True),
        "sms": NeedDomain(automatable=True),
        # A connector serves them, but their asks carry a subject.
        "contact": NeedDomain(connector_category="contacts"),
        "file": NeedDomain(connector_category="files"),
        "hue": NeedDomain(connector_category="smart_home"),
        "telephony": NeedDomain(connector_category="telephony"),
        # Everything else: learned and shown, never proposed.
        "activity": _NOTHING,
        "automation": _NOTHING,
        "brave": _NOTHING,
        "browser": _NOTHING,
        "calculation": _NOTHING,
        "context": _NOTHING,
        "devops": _NOTHING,
        "document": _NOTHING,
        "document_generation": _NOTHING,
        "generated_file": _NOTHING,
        "image_generation": _NOTHING,
        "interactive_page": _NOTHING,
        "journal": _NOTHING,
        "mcp": _NOTHING,
        "memory": _NOTHING,
        "peer": _NOTHING,
        "perplexity": _NOTHING,
        "place": _NOTHING,
        "query": _NOTHING,
        # Reminders push themselves at their own time: a routine listing them
        # would repeat what already arrives.
        "reminder": _NOTHING,
        "route": _NOTHING,
        "setting": _NOTHING,
        "sub_agent": _NOTHING,
        "ticket": _NOTHING,
        "web_fetch": _NOTHING,
        "web_search": _NOTHING,
        "wikipedia": _NOTHING,
    }
)


def automatable_domains() -> frozenset[str]:
    """The domains whose recurring needs may be proposed as routines.

    Returns:
        The automatable domain names.
    """
    return frozenset(name for name, decision in NEED_DOMAINS.items() if decision.automatable)


def connector_category_of(domain: str) -> str | None:
    """The connector category a domain's asks depend on.

    Args:
        domain: A domain name (an unregistered one has none).

    Returns:
        The category, or None.
    """
    return NEED_DOMAINS.get(domain, _NOTHING).connector_category


def assert_need_domains_complete(registered: Iterable[str]) -> None:
    """Refuse a registry and a declaration that disagree (ADR-085).

    Args:
        registered: Every domain name of the agents' registry.

    Raises:
        AssertionError: Naming the undecided and the stale domains.
    """
    names = set(registered)
    undecided = sorted(names - set(NEED_DOMAINS))
    stale = sorted(set(NEED_DOMAINS) - names)
    # Raised, never ``assert``-ed: an optimised interpreter strips assertions.
    if undecided or stale:
        raise AssertionError(
            "habits.need_domains disagrees with the domain registry — "
            f"undecided: {undecided}, no longer registered: {stale}"
        )
