"""One admission for every voice lookup, whichever door asked (ADR-301, the named seam).

A DIRECT voice — the owner call under its direct mandate (ADR-290 lot 7),
a browser session in direct mode (ADR-300 wave 4) — reads LIA's tools
itself, and two doors let it in: the vendor's call-back on the phone
(``live_tools_router.live_tool_callback``, authenticated by a derived token)
and the person's own session in the browser (``live/tool_door.
run_session_tool``, authenticated by their cookie). Each door authenticates
its caller its own way, resolves what the voice was OFFERED under its own
gate, keeps its own budget and says a refusal in its own transport — a
vendor call-back answers « not found », a person's own session a sentence.
What both then owe is the SAME sequence, and the order is the contract:

1. the tool must be one the voice was offered — derived from the catalogue,
   not hidden by a capability switch, not in a domain the person switched
   off; a tool the model invented is « not offered » like any other;
2. the host's budget admits one more — AFTER the offer, so a refused tool
   spends nothing of it;
3. the lookup runs on the shared runner (``run_live_tool``) and is filed
   under the host (``VoiceToolHost``): the surface, the run id, the node.

Written twice before this module — once per door, in the same order by
coincidence rather than by construction. A MUTABLE tool with a spoken
confirmation (not built, ADR-301) adds its step between 2 and 3 — the draft,
the question the voice asks, the answer that resumes — HERE and in the
runner, never in a door.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from src.domains.agents.telephony.live_tools import (
    LiveToolSpec,
    VoiceToolHost,
    run_live_tool,
    spec_for,
)


class LookupRefusal(str, Enum):
    """Why a lookup did not run — the metric outcome each door counts under."""

    #: Not derived, hidden by a capability, or in a domain the person switched off.
    NOT_OFFERED = "refused_tool"
    #: The host's budget of lookups is spent.
    BUDGET = "budget_exceeded"


@dataclass(frozen=True, slots=True)
class LookupVerdict:
    """What the admission decided, and the text when the lookup ran.

    Attributes:
        refusal: Why the lookup did not run; None when it ran.
        spec: The derived entry, when the name resolved to one the voice was
            offered (a refused BUDGET still names it — the door counts the tool).
        text: The runner's text (a result, a cut stated, a sentence for a
            failure); "" on a refusal, whose sentence is the door's.
    """

    refusal: LookupRefusal | None
    spec: LiveToolSpec | None
    text: str

    @property
    def admitted(self) -> bool:
        """Whether the lookup ran."""
        return self.refusal is None


async def serve_voice_lookup(
    name: str,
    args: Mapping[str, Any],
    *,
    offered: Iterable[LiveToolSpec],
    consume_budget: Callable[[], Awaitable[bool]],
    user_id: UUID,
    language: str,
    timezone: str,
    display_name: str,
    host: VoiceToolHost,
) -> LookupVerdict:
    """Admit one lookup in the contract's order, and run it when admitted.

    Args:
        name: The tool the voice asked for, as it named it.
        args: What the voice passed, minus the door's own fields (a call id).
        offered: The specs the voice holds right now — the door resolved them
            under ITS gate (the telephony flag, the live capability) and the
            person's domain switches.
        consume_budget: Counts one lookup against the host's budget; True
            when this one is within it. Called only once the tool is offered.
        user_id: The person.
        language: Their backend-canonical language.
        timezone: Their IANA zone.
        display_name: What the tools may sign as.
        host: Where the lookup is filed.

    Returns:
        The verdict — refused with its reason, or admitted with the text.
    """
    spec = spec_for(name)
    if spec is None or spec not in tuple(offered):
        return LookupVerdict(refusal=LookupRefusal.NOT_OFFERED, spec=None, text="")
    if not await consume_budget():
        return LookupVerdict(refusal=LookupRefusal.BUDGET, spec=spec, text="")
    text = await run_live_tool(
        spec,
        dict(args),
        user_id=user_id,
        language=language,
        timezone=timezone,
        display_name=display_name,
        host=host,
    )
    return LookupVerdict(refusal=None, spec=spec, text=text)


__all__ = ["LookupRefusal", "LookupVerdict", "serve_voice_lookup"]
