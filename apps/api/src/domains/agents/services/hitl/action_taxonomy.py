"""Action-type taxonomy for HITL classification.

Maps a pending action to the ``ACTION_TYPE_*`` constant that the HITL
classifier announces in its prompt (``Action type: ...``) and uses to pick the
few-shot example block. Both uses make the mapping semantic, not cosmetic: the
announced type tells the classifying LLM what kind of operation the user is
confirming, and the example block tells it which parameter an EDIT may touch.

Why a verb-first taxonomy rather than a substring ladder
--------------------------------------------------------
The historical implementation walked an ``if/elif`` ladder of substrings in
which a domain NOUN sat inside a branch about a VERB::

    elif "send" in name or "envoi" in name or "email" in name:
        return ACTION_TYPE_SEND
    elif "delete" in name or "suppr" in name:
        return ACTION_TYPE_DELETE

``delete_email_tool`` therefore matched ``"email"`` and was announced as a
*send*: the prompt claimed the user was confirming an outgoing mail while they
were confirming a deletion, and the injected examples steered an EDIT toward
``{"to": ...}``. The prompt's own safety rule ("If *Delete* action and user says
*Wait*, default to REPLAN/REJECT, never APPROVE") could not fire, because the
prompt never said the action was a delete. ``get_emails_tool`` and
``get_email_details_tool`` — read-only — were announced as sends too.

Tool names in this codebase are ``<verb>_<domain>_tool``. Classifying on the
leading verb removes the noun/verb collision by construction. A substring pass
remains as a fallback for names that are not verb-prefixed
(``unified_web_search_tool``, MCP tools, user skills); it is ordered
destructive-first, so an ambiguous name degrades toward the conservative
reading, and it contains verbs only — never a domain noun.
"""

from __future__ import annotations

from typing import Final

from src.domains.agents.constants import (
    ACTION_TYPE_CREATE,
    ACTION_TYPE_DELETE,
    ACTION_TYPE_DRAFT_CRITIQUE,
    ACTION_TYPE_FOR_EACH_CONFIRMATION,
    ACTION_TYPE_FORWARD,
    ACTION_TYPE_GENERIC,
    ACTION_TYPE_GET,
    ACTION_TYPE_LIST,
    ACTION_TYPE_PLAN_APPROVAL,
    ACTION_TYPE_REPLY,
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
    ACTION_TYPE_UPDATE,
)
from src.domains.agents.services.hitl.validator import HitlValidator

#: Interrupt ``type`` values that decide the action type before any tool lookup.
_ACTION_TYPE_BY_INTERRUPT_TYPE: Final[dict[str, str]] = {
    "plan_approval": ACTION_TYPE_PLAN_APPROVAL,
    "draft_critique": ACTION_TYPE_DRAFT_CRITIQUE,
    "for_each_confirmation": ACTION_TYPE_FOR_EACH_CONFIRMATION,
}

#: Leading verb of a snake_case tool name -> action type.
#:
#: Only unambiguous CRUD-ish verbs are listed. A verb whose action type would be
#: a guess (``activate``, ``control``, ``run``, ``import``) is deliberately
#: absent: falling back to the generic type is honest, whereas a wrong announced
#: type actively misleads the classifier.
_ACTION_TYPE_BY_VERB: Final[dict[str, str]] = {
    # Read
    "get": ACTION_TYPE_GET,
    "read": ACTION_TYPE_GET,
    "fetch": ACTION_TYPE_GET,
    "list": ACTION_TYPE_LIST,
    "search": ACTION_TYPE_SEARCH,
    "find": ACTION_TYPE_SEARCH,
    "query": ACTION_TYPE_SEARCH,
    "recherche": ACTION_TYPE_SEARCH,
    # Write
    "create": ACTION_TYPE_CREATE,
    "add": ACTION_TYPE_CREATE,
    "generate": ACTION_TYPE_CREATE,
    "update": ACTION_TYPE_UPDATE,
    "edit": ACTION_TYPE_UPDATE,
    "set": ACTION_TYPE_UPDATE,
    "apply": ACTION_TYPE_UPDATE,
    "complete": ACTION_TYPE_UPDATE,
    "modifier": ACTION_TYPE_UPDATE,
    # Destructive
    "delete": ACTION_TYPE_DELETE,
    "remove": ACTION_TYPE_DELETE,
    "cancel": ACTION_TYPE_DELETE,
    "supprimer": ACTION_TYPE_DELETE,
    # Outbound
    "send": ACTION_TYPE_SEND,
    "envoyer": ACTION_TYPE_SEND,
    "forward": ACTION_TYPE_FORWARD,
    "reply": ACTION_TYPE_REPLY,
}

#: Ordered substring fallback for names that do not start with a known verb.
#:
#: Destructive first on purpose: for a name that mentions several verbs, the
#: conservative reading is the one whose example block steers toward REJECT.
#: Verbs only — a domain noun here is the defect this module exists to prevent.
_FALLBACK_RULES: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("delete", "remove", "cancel", "suppr"), ACTION_TYPE_DELETE),
    (("forward", "transfer"), ACTION_TYPE_FORWARD),
    (("reply", "repondre", "répondre"), ACTION_TYPE_REPLY),
    (("send", "envoi", "envoyer"), ACTION_TYPE_SEND),
    (("create", "add", "generate"), ACTION_TYPE_CREATE),
    (("update", "modif"), ACTION_TYPE_UPDATE),
    (("search", "recherche", "query", "find"), ACTION_TYPE_SEARCH),
    (("list",), ACTION_TYPE_LIST),
    (("get", "details", "read", "fetch"), ACTION_TYPE_GET),
)

#: Action types that intentionally reuse the ``default`` example block.
#:
#: These are low-risk reads plus the catch-all: the generic block ("yes" ->
#: APPROVE, "no cancel" -> REJECT, "no <value>" -> EDIT) already describes them.
#: Membership here is a decision, not an omission — :func:`assert_examples_coverage`
#: fails on any emitted type that is neither sectioned nor listed here.
EXAMPLES_INTENTIONAL_DEFAULT: Final[frozenset[str]] = frozenset(
    {
        ACTION_TYPE_CREATE,
        ACTION_TYPE_LIST,
        ACTION_TYPE_GET,
        ACTION_TYPE_GENERIC,
    }
)


def classify_tool_name(tool_name: str) -> str:
    """Resolve the action type announced for a tool name.

    Args:
        tool_name: Raw tool name from the interrupt (any case, may be empty).

    Returns:
        An ``ACTION_TYPE_*`` value; :data:`ACTION_TYPE_GENERIC` when neither the
        verb map nor the fallback rules recognise the name.
    """
    normalized = tool_name.strip().lower()
    if not normalized:
        return ACTION_TYPE_GENERIC

    verb = normalized.split("_", 1)[0]
    mapped = _ACTION_TYPE_BY_VERB.get(verb)
    if mapped is not None:
        return mapped

    for needles, action_type in _FALLBACK_RULES:
        if any(needle in normalized for needle in needles):
            return action_type

    return ACTION_TYPE_GENERIC


def classify_action_type(context: list[dict]) -> str:
    """Resolve the action type for a HITL interrupt context.

    Args:
        context: ``action_requests`` list carried by the interrupt. Only a
            single pending action can be announced precisely; anything else is
            generic.

    Returns:
        An ``ACTION_TYPE_*`` value.
    """
    if not context or len(context) != 1:
        return ACTION_TYPE_GENERIC

    action = context[0]

    # Interrupt-level types win over the tool name: a draft critique or a bulk
    # confirmation is about the interaction, not about the tool behind it.
    by_interrupt_type = _ACTION_TYPE_BY_INTERRUPT_TYPE.get(str(action.get("type", "")))
    if by_interrupt_type is not None:
        return by_interrupt_type

    try:
        tool_name = HitlValidator.extract_tool_name(action)
    except ValueError:
        return ACTION_TYPE_GENERIC

    return classify_tool_name(tool_name)


def emittable_action_types() -> frozenset[str]:
    """Every action type :func:`classify_action_type` can return.

    Returns:
        The union of the interrupt-type map, the verb map, the fallback rules
        and the generic catch-all.
    """
    return frozenset(
        {ACTION_TYPE_GENERIC}
        | set(_ACTION_TYPE_BY_INTERRUPT_TYPE.values())
        | set(_ACTION_TYPE_BY_VERB.values())
        | {action_type for _, action_type in _FALLBACK_RULES}
    )


def assert_examples_coverage(sections: dict[str, str]) -> None:
    """Assert every emittable action type resolves to a deliberate example block.

    Called from the lifespan startup so a new action type without examples
    refuses to boot, and from a unit test so CI catches it before merge. A type
    that silently falls back to ``default`` is how a classifier stops being
    contextual without anyone noticing.

    Args:
        sections: Parsed ``hitl_classifier_examples.txt`` sections, keyed by
            action type, as returned by the classifier's section loader.

    Raises:
        AssertionError: If the ``default`` section is missing, if a declared
            section is empty (same silent failure as a missing one), or if an
            emittable action type has neither its own section nor an entry in
            :data:`EXAMPLES_INTENTIONAL_DEFAULT`.
    """
    if "default" not in sections:
        raise AssertionError(
            "hitl_classifier_examples.txt has no '=== default ===' section: "
            "every unlisted action type would resolve to nothing."
        )

    empty = sorted(key for key, block in sections.items() if not block.strip())
    if empty:
        raise AssertionError(
            f"{len(empty)} HITL example section(s) are empty: {', '.join(empty)}. "
            "An empty block injects nothing and is indistinguishable from a missing one."
        )

    uncovered = sorted(
        action_type
        for action_type in emittable_action_types()
        if action_type not in sections and action_type not in EXAMPLES_INTENTIONAL_DEFAULT
    )
    if uncovered:
        raise AssertionError(
            f"{len(uncovered)} HITL action type(s) have no example section and are not "
            f"declared as intentional default: {', '.join(uncovered)}. Add a "
            "'=== <type> ===' block to hitl_classifier_examples.txt or list the type in "
            "EXAMPLES_INTENTIONAL_DEFAULT (src/domains/agents/services/hitl/action_taxonomy.py)."
        )


__all__ = [
    "EXAMPLES_INTENTIONAL_DEFAULT",
    "assert_examples_coverage",
    "classify_action_type",
    "classify_tool_name",
    "emittable_action_types",
]
