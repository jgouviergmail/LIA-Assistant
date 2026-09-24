"""What this turn actually did, for the message that reports it (ADR-263).

The source of truth is the REGISTER, read back by ``run_id`` — not the graph
state, and not a counter kept along the way. That is the whole point of the
programme: the answer states what was recorded, so a reader does not have to
trust the executor that produced it.

Two rules the shape follows:

- **only what was performed.** A refusal changed nothing and the answer already
  says so in prose; a claim still open at archive time is an effect nobody can
  describe yet, and guessing would be exactly the invented diagnosis this
  register exists to remove.
- **keys and values, never a sentence.** The frontend resolves the wording in
  the reader's current language (``apps/web`` conventions), so a message
  archived in French still reads in German after the user switches.

One reader does get sentences: the response model of a ReAct turn
(:func:`succeeded_effect_sentences`, ADR-263 §23). They are rendered at answer
time, in the person's language, handed to the prompt and never stored — the
archived entries stay keys and values.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.agents.effects.models import EffectStatus

logger = structlog.get_logger(__name__)

#: Statuses that describe something that HAPPENED. ``refused`` and ``claimed``
#: are deliberately absent — see the module docstring.
REPORTED_STATUSES: frozenset[EffectStatus] = frozenset(
    {EffectStatus.SUCCEEDED, EffectStatus.FAILED}
)


async def performed_effects(run_id: str) -> list[dict[str, Any]]:
    """The effects of one run, shaped for the message metadata.

    Best-effort by contract: the answer is already written by the time this
    runs, and failing to describe what happened must never cost the user their
    answer. A failure is logged and the message simply carries no effect list.

    Args:
        run_id: The run whose effects to report.

    Returns:
        One entry per performed effect, oldest first, each carrying
        ``label_key``, ``values``, ``status`` and ``tool_name``. Empty for a
        turn that performed nothing — the common case.
    """
    if not run_id:
        return []

    from src.domains.agents.effects.repository import EffectLedgerRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            repository = EffectLedgerRepository(db)
            rows = await repository.list_for_run(run_id)
            return [_entry(row) for row in rows if row.status in REPORTED_STATUSES]
    except Exception as exc:  # noqa: BLE001 - the answer must survive this
        logger.warning(
            "performed_effects_unavailable",
            run_id=run_id,
            error_type=type(exc).__name__,
        )
        return []


def _entry(row: Any) -> dict[str, Any]:
    """One display entry from one row.

    Args:
        row: The ledger row.

    Returns:
        The entry the frontend renders.
    """
    from src.domains.agents.effects.labels import readable_label

    label_key, values = readable_label(row)
    return {
        "label_key": label_key,
        "values": values,
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "tool_name": row.tool_name,
    }


def succeeded_effect_sentences(effects: list[dict[str, Any]], language: str) -> list[str]:
    """What the turn DID for the person, as sentences a model reads as its own acts.

    The ReAct answer reaches the response synthesis as PROSE, and prose can be
    misread: measured 2026-09-23 on Docker dev, an image generated in 48 s, the
    loop answering « Voilà : un chat tigré … », and the response model — which
    never sees a tool result — telling the person it cannot generate images
    (ADR-263 §23). The register is what makes the act a fact rather than a
    reading, and each row already carries its sentence in the person's language.

    Two kinds of rows are not stated. A failure: the honesty directive states
    it, once (ADR-303). An act on LIA's OWN conversation context — a skill
    activated, an item chosen as the reference, declared ``REASON_INTERNAL_CONTEXT``
    by its manifest: the model is told to say its acts are done, and plumbing is
    not an answer (the skill activation is the second most frequent effect on
    Docker dev, 24 rows).

    Args:
        effects: Entries from :func:`performed_effects`.
        language: The person's language, any spelling.

    Returns:
        One sentence per succeeded effect the person would recognise, oldest first.
    """
    from src.core.i18n_effects import render_effect_label

    return [
        render_effect_label({"i18n_key": effect["label_key"], "values": effect["values"]}, language)
        for effect in effects
        if effect["status"] == EffectStatus.SUCCEEDED.value
        and not _changes_only_lia_context(effect["tool_name"])
    ]


def _changes_only_lia_context(tool_name: str) -> bool:
    """Whether the capability's manifest declares it touches LIA's context only.

    Args:
        tool_name: The registered name, or ``draft:<type>`` for an executor.

    Returns:
        True only for a manifest declaring ``REASON_INTERNAL_CONTEXT``. A name no
        manifest carries (a draft executor, a tool since removed) is False: an
        act nobody can classify is stated rather than hidden.
    """
    from src.domains.agents.registry.catalogue import REASON_INTERNAL_CONTEXT
    from src.domains.agents.registry.manifest_resolution import resolve_tool_manifest

    manifest = resolve_tool_manifest(tool_name)
    return manifest is not None and manifest.mutation_policy_reason == REASON_INTERNAL_CONTEXT
