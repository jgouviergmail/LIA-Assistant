"""Native authorization failures keep their actual cause; no private detail is logged."""

from src.core.exceptions import AuthorizationError
from src.core.tool_outcome import error_code_of
from src.domains.shared.discussion_sources import SourceReadRequest, SourceSnapshot, closed_source

# Refusals the person made. Every other refusal — a connection that is not active, an
# account that cannot be identified or changed during the read — is a source that
# could not be read: told « consent », the context model read a refusal the person
# never made (a legacy calendar connector on production, 2026-10-21).
_PERSON_REFUSALS = frozenset({"SMS_CONSENT_REQUIRED"})


def authorization_failure(request: SourceReadRequest, error: AuthorizationError) -> SourceSnapshot:
    """Map a native authorization refusal to the closed source state naming its cause.

    Args:
        request: The source read that was refused.
        error: The refusal.

    Returns:
        A closed snapshot: switched off by the operator, refused by the person, or
        unavailable — the default, because only a refusal the person made may be
        stated as theirs.
    """
    code = error_code_of(error.detail)
    if code == "CAPABILITY_DISABLED":
        return closed_source(request, disabled=True, reason="feature")
    if code in _PERSON_REFUSALS:
        return closed_source(request, disabled=True, reason="consent")
    return closed_source(request, disabled=False, reason="provider")
