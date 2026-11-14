"""A workboard refusal reaches the model as its stable code (ADR-276).

The ticket tools that ask before they act — the update, the comment, the
deletion — prepare their confirmation through the native tools' shared
preparation (``prepare_native_tool``), whose answer to a refused validation is
one sentence that names no cause. That is the right default for thirty tools
whose validations may quote anything — and the wrong answer for the workboard,
whose refusals are a FINITE vocabulary (:class:`WorkboardError`) the model can
act on: « no category called that » sends it to the list of categories, « two
tickets carry that title » makes it ask which, « this ticket is not yours to
delete » does neither.

So a workboard code travels, through the door that preparation already keeps
for a finite refusal (``CommandRejected``): the error code stays the one a
refused constraint always had, and the message becomes the ``workboard_*``
code — what ``create_ticket`` and the readers have always answered. Anything
that is NOT one of the workboard's own codes keeps the shared sentence: a
validation that carries somebody's words must never reach a prompt.

One door, :func:`workboard_refusals`, wrapped around each tool's source
preparation: a refusal has one spelling whichever tool met it.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from src.core.exceptions import ValidationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.workboard.constants import WorkboardError

#: The refusals the workboard itself can give — the only texts that travel.
_WORKBOARD_CODES = frozenset(member.value for member in WorkboardError)

#: The error code the shared preparation gives a refused validation.
_REFUSED_CONSTRAINT = "CONSTRAINT_VIOLATION"


class WorkboardRefused(CommandRejected):
    """A workboard validation refusal, said by its stable code.

    Attributes:
        model_message: The ``workboard_*`` code — what the model reads.
    """

    def __init__(self, workboard_code: str) -> None:
        super().__init__(_REFUSED_CONSTRAINT)
        self.model_message = workboard_code


def workboard_code_of(error: ValidationError) -> str | None:
    """The workboard's own code a validation refusal carries, if it is one.

    Args:
        error: What the service raised.

    Returns:
        The stable ``workboard_*`` code, or None for any other validation —
        whose text stays out of the tool's answer.
    """
    detail = error.detail
    return detail if isinstance(detail, str) and detail in _WORKBOARD_CODES else None


@contextmanager
def workboard_refusals() -> Iterator[None]:
    """Let a refusal of the workboard out as its stable code.

    Wrapped around the source preparation of a tool that goes through the
    shared one. A validation whose detail is one of the workboard's codes
    leaves as :class:`WorkboardRefused`; any other passes untouched, to the
    shared sentence that names no cause.

    Yields:
        Nothing: the block runs the preparation.

    Raises:
        WorkboardRefused: The workboard itself refused, by a stable code.
    """
    try:
        yield
    except ValidationError as refused:
        code = workboard_code_of(refused)
        if code is None:
            raise
        raise WorkboardRefused(code) from refused


__all__ = ["WorkboardRefused", "workboard_code_of", "workboard_refusals"]
