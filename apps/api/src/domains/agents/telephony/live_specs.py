"""Voice lookup contracts and native parameter declarations, shared by all hosts."""

from dataclasses import dataclass
from typing import Final

from src.domains.telephony.live_tools import LiveToolParameter


@dataclass(frozen=True)
class LiveToolSpec:
    """A catalogue reader or spoken adapter and the section its consultation opens.

    Attributes:
        name: The registry (and catalogue) name of the tool, which a native
            adapter keeps so capability filtering and vendor fingerprints agree.
        domain: The domain the tool reads (the register's vocabulary) — what
            the person's switches decide on.
        section: The ``phone_call`` surface section its consultation files under.
        parameters: The manifest parameters exposed to the voice agent, in
            order; empty for a native lookup, whose flat voice parameters are
            declared in :data:`NATIVE_PARAMETERS`.
        native: True for a lookup served by a spoken adapter, not the catalogue.
    """

    name: str
    domain: str
    section: str
    parameters: tuple[str, ...]
    native: bool = False


# A native adapter retains the catalogue name so capability filtering and vendor
# fingerprints use the same authority. SMS's object request has a flat voice form.
NATIVE_LOOKUPS: Final[tuple[LiveToolSpec, ...]] = (
    LiveToolSpec("recall_memories", "context", "memories", (), True),
    LiveToolSpec("list_sms_tool", "sms", "sms", (), True),
)
NATIVE_PARAMETERS: Final[dict[str, tuple[LiveToolParameter, ...]]] = {
    "recall_memories": (
        LiveToolParameter(
            name="query",
            type="string",
            description="What the person is asking about, in a few words.",
            required=True,
        ),
    ),
    "list_sms_tool": tuple(
        LiveToolParameter(name=name, type="string", description=description, required=False)
        for name, description in (
            (
                "query",
                "Optional literal words to search in SMS bodies; omit to list latest messages.",
            ),
            (
                "sender",
                "Exact raw sender name or phone number; resolve an unambiguous contact first.",
            ),
            ("from_ts", "Optional inclusive start as timezone-aware ISO 8601."),
            ("to_ts", "Optional exclusive end as timezone-aware ISO 8601."),
        )
    ),
}
