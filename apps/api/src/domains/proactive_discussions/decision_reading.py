"""Read a decision as its schema publishes it: repair what is mechanical, never its intent.

A decision is one structured answer, and a free text one character past its published
length refused all of it: measured on 2026-10-21, an opening run on one configured
model failed at its decision over a skip reason longer than the schema allows, with no
second chance on a model that refuses a forced tool call. Whatever model a slot runs, a
free text past its published length is cut at it and an engagement's reference listed
twice is read once; the action, the references and the delay stay as strict as the
schema says. The lengths are read from the schema, never restated here.
"""

from pydantic import BaseModel

from src.domains.proactive_discussions.schemas import DeferDecision, EngageDecision, SkipDecision

_DECISIONS: dict[str, type[BaseModel]] = {
    "skip": SkipDecision,
    "defer": DeferDecision,
    "engage": EngageDecision,
}
#: The free texts of a decision a cut cannot change the meaning of.
_FREE_TEXTS = ("reason", "topic")


def repaired_decision(raw: dict[str, object]) -> dict[str, object]:
    """Return the decision with its mechanical defects repaired.

    Args:
        raw: The decision as the call returned it.

    Returns:
        The same decision, its free texts within their published lengths and its
        references listed once each; an unknown action is returned untouched, for
        the schema to refuse.
    """
    action = raw.get("action")
    model = _DECISIONS.get(action) if isinstance(action, str) else None
    if model is None:
        return raw
    repaired = dict(raw)
    for name in _FREE_TEXTS:
        value, limit = repaired.get(name), _max_length(model, name)
        if isinstance(value, str) and limit is not None and len(value.strip()) > limit:
            repaired[name] = value.strip()[:limit].rstrip()
    references = repaired.get("references")
    if isinstance(references, list | tuple) and all(isinstance(ref, str) for ref in references):
        repaired["references"] = list(
            dict.fromkeys(ref.strip() for ref in references if ref.strip())
        )
    return repaired


def _max_length(model: type[BaseModel], name: str) -> int | None:
    """The length a decision field publishes, read from its schema."""
    field = model.model_fields.get(name)
    if field is None:
        return None
    for constraint in field.metadata:
        limit = getattr(constraint, "max_length", None)
        if isinstance(limit, int):
            return limit
    return None
