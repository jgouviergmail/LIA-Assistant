"""Reading what a tool actually returned, for the ledger (ADR-263).

The gate wraps the RAW coroutine, so it reads the tool's own return value — a
``ToolResponse`` dict, a ``UnifiedToolOutput``, or whatever a legacy tool hands
back. Two readings, each with a deliberate default:

- **Succeeded**: only an EXPLICIT ``success is False`` closes the row as failed.
  Defaulting the other way would mark every legacy tool's effect as a failure
  and make the ledger lie in the direction that merely LOOKS safe.
- **Provider reference**: the identifier the world gave back, when there is one.
  Absent is a normal answer; inventing one would be a fabricated fact, which is
  exactly what this ledger exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

#: Identifiers a provider hands back, most specific first, so a result carrying
#: both ``id`` and ``message_id`` records the one that names the operation.
#: A superset of the per-domain keys the draft executor already knows
#: (``draft_executor._DOMAIN_ID_KEYS``), pinned by a test so the two cannot
#: drift into two different ideas of what an identifier is.
PROVIDER_REF_ORDER: Final[tuple[str, ...]] = (
    "message_id",
    "thread_id",
    "event_id",
    "task_id",
    "resource_name",
    "file_id",
    "label_id",
    "call_id",
    "document_id",
    "spreadsheet_id",
    "id",
)

PROVIDER_REF_KEYS: Final[frozenset[str]] = frozenset(PROVIDER_REF_ORDER)


@dataclass(frozen=True)
class ToolOutcome:
    """What the ledger records about a returned call.

    Attributes:
        succeeded: False only when the tool explicitly said so.
        provider_ref: The provider-side identifier, when the result names one.
        payload: The result rendered as data, to be kept encrypted and capped.
    """

    succeeded: bool
    provider_ref: str | None
    payload: Any


def _as_data(result: Any) -> Any:
    """Render a result as plain data, whatever shape the tool used.

    Args:
        result: The tool's return value.

    Returns:
        A dict for anything that knows how to render itself (Pydantic,
        dataclass-like), the value itself otherwise.
    """
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:  # noqa: BLE001 - a result that cannot render is kept as-is
            return result
    return result


def _find_provider_ref(data: Any) -> str | None:
    """Find the provider identifier in a rendered result.

    Args:
        data: The rendered result.

    Returns:
        The first known identifier found, at the top level or under ``data``,
        or None — which is a normal answer, not a failure.
    """
    if not isinstance(data, dict):
        return None
    scopes = [data]
    nested = data.get("data")
    if isinstance(nested, dict):
        scopes.append(nested)
    for key in PROVIDER_REF_ORDER:
        for scope in scopes:
            value = scope.get(key)
            # A scalar only: a dict under ``id`` names a structure, not an id.
            if isinstance(value, str | int) and not isinstance(value, bool):
                return str(value)
    return None


def _explicit_success(data: Any, result: Any) -> bool:
    """The one reading of « did this call succeed », shared by both registers.

    Args:
        data: The rendered result, when one was produced.
        result: The raw return value, read when the rendering is not a mapping.

    Returns:
        False only when the tool explicitly said so.
    """
    explicit = data.get("success") if isinstance(data, dict) else getattr(result, "success", None)
    return explicit is not False


def succeeded_only(result: Any) -> bool:
    """Read success WITHOUT rendering the payload (the consultation register).

    A treatment row keeps no payload and no provider reference, and it is
    written on every read a turn performs — so it must not pay for the
    ``model_dump`` and the identifier scan :func:`read_outcome` does for a row
    that keeps both.

    Args:
        result: Whatever the tool coroutine returned.

    Returns:
        False only when the tool explicitly said so.
    """
    return _explicit_success(result, result)


def read_outcome(result: Any) -> ToolOutcome:
    """Read a tool's return value the way the ledger needs it.

    Args:
        result: Whatever the tool coroutine returned.

    Returns:
        The outcome: succeeded, provider reference, and the payload to keep.
    """
    data = _as_data(result)
    return ToolOutcome(
        succeeded=_explicit_success(data, result),
        provider_ref=_find_provider_ref(data),
        payload=data,
    )
