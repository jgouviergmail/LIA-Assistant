"""The domains the phone channel may READ for the person (lot 8, ADR-290).

During a call with the account holder the voice agent may look things up in
LIA through webhook tools. Which tools? Every read-only tool of the catalogue
whose domain is listed HERE — the rule is derived in
``domains/agents/telephony/live_tools.py`` — and the person may switch any of
these domains off for their own calls (``users.phone_disabled_domains``).

This module lives in ``shared`` because two halves read the same vocabulary
and neither may import the other: the identity service (``telephony``)
validates the person's switches against it, the live-tools rule (``agents``)
derives the tool set from it. The rule names no domain outside this list by
construction, and the unit test over the full catalogue checks that every
domain listed here is served by at least one tool — a switch nobody can flip
is a switch nobody watches (the boot guard cannot hold that line: a domain's
only read tool may register behind a feature flag).

Domains deliberately absent, with the reason:

- ``context`` tools of the catalogue answer only inside a turn (``system``
  category) — the phone's own ``recall_memories`` lookup files under
  ``context`` instead, the domain the briefing's memories already read as;
- ``devops`` administers the platform; ``skill`` and ``python_sandbox`` run
  code; ``sub_agent`` runs a whole agent; ``browser`` drives a browser;
  ``query`` is executor-injected (pipeline only); ``mcp`` speaks a third
  party's vocabulary; ``document_generation`` and ``image_generation`` act;
  ``interest`` has no read tool; ``memory`` has one (``search_memories_tool``,
  ADR-313) but the voice reaches the same memories through its own native
  ``recall_memories`` lookup, ranked through the same lookup door — listing the
  domain would offer the voice two tools for one question;
  ``generated_file`` (ADR-318) SHOWS what it finds as chat cards, which no voice
  surface draws — and a file cannot be heard.

The ADR-318 lookups that answer in words join it: ``calculation`` (a voice
model computes no better than a chat model), ``journal`` (whose tool reads the
person's preference from their row, since a voice runtime carries none) and
``activity``.
"""

from __future__ import annotations

from typing import Final

#: The domains the phone may read, in the register's own vocabulary
#: (``DOMAIN_REGISTRY`` / ``TREATMENT_DOMAIN_LABELS`` keys).
PHONE_DOMAINS: Final[tuple[str, ...]] = (
    "activity",
    "automation",
    "brave",
    "calculation",
    "contact",
    "context",
    "document",
    "email",
    "event",
    "file",
    "health",
    "hue",
    "journal",
    "peer",
    "perplexity",
    "place",
    "reminder",
    "route",
    "task",
    "telephony",
    "ticket",
    "weather",
    "web_fetch",
    "web_search",
    "wikipedia",
)

_PHONE_DOMAIN_SET: Final = frozenset(PHONE_DOMAINS)


def is_phone_domain(domain: str) -> bool:
    """Whether a domain key is one the phone channel offers.

    Args:
        domain: A domain key.

    Returns:
        True when the phone may read it.
    """
    return domain in _PHONE_DOMAIN_SET


def unknown_phone_domains(domains: object) -> list[str]:
    """The entries of a switch list that name no phone domain.

    Args:
        domains: What a client sent — anything; only a list of strings passes.

    Returns:
        The offending entries (every entry when the shape is wrong).
    """
    if not isinstance(domains, list | tuple):
        return [str(domains)]
    return [str(d) for d in domains if not isinstance(d, str) or not is_phone_domain(d)]


__all__ = ["PHONE_DOMAINS", "is_phone_domain", "unknown_phone_domains"]
