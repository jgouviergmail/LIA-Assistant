#!/usr/bin/env python
"""Read-only pre-deployment check for the ADR-244/245 catalogue changes.

The real per-agent configuration lives in ``llm_config_overrides``, in the
DATABASE, and it differs between deployments -- dev and prod do not run the
same models. Every figure quoted in the ADR was measured on the dev instance,
so it describes dev and nothing else.

This script answers the seven questions that are instance-specific, against
whatever database ``DATABASE_URL`` points at. It writes nothing.

1. **Would the correction deactivate a model this instance uses?**
   The migration already refuses to (it keeps a referenced model active and
   reports it), but knowing beforehand is better than reading it in a
   deployment log.
2. **Does any configured model fail its slot's declared capabilities?**
   Never fatal -- a human chose that model and the gate only reports -- but it
   is the discrepancy the admin card will show.
3. **Would any model lose strict structured output?**
   Only a ``verified`` row can, and only on OpenAI. Zero on dev; a prod
   instance whose admin curated rows through the Excel round-trip may differ.
4. **What would the reasoning migration rewrite?** Every stored shape becomes
   one intent, and this says how many rows and from which shape.
5. **Does any declared ladder speak a vocabulary the ladder does not have?**
   ``off`` was one; the narrowing is an intersection, so an unrecognised level
   is dropped silently and can leave a ladder with no off switch.
6. **Would any slot's reasoning depth CHANGE?** The runtime coerces a level a
   model does not offer, and counts it. This answers the question beforehand,
   per slot, which is the one an operator actually cares about.
7. **What would the column drop discard?** ``reasoning_budget_range`` is
   removed; if an admin curated values through the Excel round-trip, they go.

Usage:
    task llm:catalogue:preflight

``DATABASE_URL`` decides which instance is examined, and it must resolve from
wherever the script runs. The repository's own ``.env`` names the Compose
service (``postgres:5432``), which resolves inside the network and nowhere
else, so a run from the host supplies its own -- an explicit environment
variable wins over the value the Taskfile loads::

    # dev, from the host (Compose publishes it on the loopback)
    DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/<db> task llm:catalogue:preflight

    # production, through the tunnel docker-compose.prod.yml documents
    ssh -p 2222 -L 15432:127.0.0.1:5432 <user>@<host> -N     # keep it open
    DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:15432/<db> task llm:catalogue:preflight

Run it from a checkout of the code being DEPLOYED, against the database that
has NOT been migrated yet: that pairing is what makes checks 4 to 7 predictive
rather than a description of a change already applied.

One limit, stated because it cannot be removed: only the DATABASE is the
target's. Per-slot models, the summarisation model and the failover chain are
settings, they live in the instance's ``.env``, and this process reads its own.
The report prints the three it assumed so a reader can tell whether they are
the ones being checked -- supply the target's values alongside
``DATABASE_URL`` when they differ.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402

from src.core.constants import CAPABILITY_PROVENANCE_VERIFIED  # noqa: E402
from src.infrastructure.llm.catalogue.field_mapping import is_retired, registry_facts  # noqa: E402


def _unreachable_message(host: str | None, port: int | None, exc: OSError) -> str:
    """Explain an unreachable instance without quoting the credentials.

    The report is meant to be aimed at an instance that is not this machine's,
    so "wrong address" is its most likely failure and deserves a sentence
    rather than an asyncio traceback. The repository's own ``.env`` names the
    Compose service ``postgres``, which resolves inside the network and
    nowhere else -- reason enough to say where the address came from.

    Args:
        host: The host the connection was attempted against.
        port: Its port.
        exc: What the connection raised.

    Returns:
        The message to print. It never contains user or password.
    """
    return (
        f"cannot reach the instance at {host}:{port} -- {exc}\n"
        "    DATABASE_URL must resolve from HERE, and the repository's .env names\n"
        "    the Compose service (postgres:5432), which resolves in the network only.\n"
        "    dev, from the host: DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/<db>\n"
        "    prod: open the tunnel docker-compose.prod.yml documents, then aim at it"
    )


def _models_named_in_the_environment() -> set[str]:
    """Model names pinned by an environment variable, whatever domain owns it.

    Slots, summarisation and failover are read through their settings, but a
    domain can pin a model of its own -- production pins the telephony agent's
    that way -- and enumerating them by hand would go stale the day the next
    one is added. Reading every ``*_MODEL`` variable is generic, and a value
    that matches no catalogue row simply widens a set used for membership.

    Returns:
        Every value of an environment variable whose name ends in ``_MODEL``.
    """
    return {
        value.strip()
        for name, value in os.environ.items()
        if name.endswith("_MODEL") and value.strip()
    }


async def _run() -> int:
    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.domains.llm.models import LLMModel
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
    from src.domains.llm_config.models import LLMConfigOverride
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.capability_gate import evaluate_slot_fit
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    today = datetime.now(UTC).date()
    try:
        async with get_db_context() as db:
            await ModelCapabilitiesCache.load_from_db(db)
            await LLMConfigOverrideCache.load_from_db(db)
            active = select(LLMModel).where(LLMModel.is_active)
            rows = list((await db.execute(active)).scalars().all())
            overrides = list((await db.execute(select(LLMConfigOverride))).scalars().all())
            curated_ranges = await _curated_budget_ranges(db)
    except OSError as exc:
        # PostgresDsn is a MultiHostUrl: it has hosts(), not host. Only the
        # address is read -- the same object carries the credentials.
        hosts = settings.database_url.hosts()
        address = hosts[0] if hosts else None
        host = address["host"] if address else None
        port = address["port"] if address else None
        print(_unreachable_message(host, port, exc))
        return 1

    # Every model this instance can reach for. The per-slot models already
    # came from settings; summarisation and the failover chain are settings
    # too, and reading their code defaults here answered for the CODE on the
    # one question the whole report exists to ask of an INSTANCE.
    referenced = {o.model for o in overrides if o.model}
    referenced.add(settings.summarization_model)
    referenced.update(p.strip() for p in settings.fallback_models.split(",") if p.strip())
    for slot in LLM_TYPES_REGISTRY:
        config = get_llm_config_for_agent(settings, slot)
        if config.model:
            referenced.add(config.model)
    referenced.update(_models_named_in_the_environment())

    print(f"instance check at {today} -- {len(rows)} active models, {len(overrides)} DB overrides")
    # The database is the target's; everything else is this process's
    # environment. Printing what it assumed is what lets a reader tell the two
    # apart -- these three lines must match the instance being checked.
    print(f"    env: summarisation={settings.summarization_model}")
    print(f"    env: failover={settings.fallback_models}")
    print(f"    env: {len(LLM_TYPES_REGISTRY)} slots, {len(referenced)} models referenced in all")
    problems = 0

    print("\n[1] models the correction would deactivate")
    retired: list[str] = []
    kept: list[str] = []
    for row in rows:
        facts = registry_facts(row.provider.value, row.model_name, kind=row.kind.value)
        if facts is not None and is_retired(facts, today=today):
            (kept if row.model_name in referenced else retired).append(row.model_name)
    print(f"    deactivated : {len(retired)} {sorted(retired)}")
    print(f"    KEPT because this instance references them: {len(kept)} {sorted(kept)}")
    if kept:
        problems += 1
        print("    -> retarget those slots before deploying (the migration keeps them active)")

    print("\n[2] configured models that fail their slot's declared capabilities")
    mismatches = []
    for slot in sorted(LLM_TYPES_REGISTRY):
        config = get_llm_config_for_agent(settings, slot)
        if not config.model:
            continue
        verdict = evaluate_slot_fit(slot, config.model)
        if verdict is not None and not verdict.satisfied:
            mismatches.append((slot, config.model, verdict))
    for slot, model, verdict in mismatches:
        print(
            f"    {slot:30s} {model:24s} missing={list(verdict.missing)} wrong_kind={verdict.wrong_kind}"
        )
    print(f"    total: {len(mismatches)} (reported, never blocking -- a human chose these)")

    print("\n[3] models that would lose strict structured output")
    losing = [
        row.model_name
        for row in rows
        if row.provider.value == "openai"
        and row.capability_provenance.value == CAPABILITY_PROVENANCE_VERIFIED
        and not row.supports_strict_mode
    ]
    print(f"    {len(losing)} {sorted(losing)}")
    if losing:
        problems += 1
        print("    -> a human marked these verified with strict mode off; confirm that is intended")

    problems += _report_reasoning(rows, overrides, curated_ranges)

    print(f"\nverdict: {problems} item(s) need attention")
    return problems


async def _curated_budget_ranges(db: Any) -> list[str]:
    """Models still carrying a curated budget range, read from the DATABASE.

    Raw SQL on purpose: on an instance that has not migrated yet the column is
    still there, and the ORM of the code doing the asking no longer declares
    it. On a migrated instance the column is gone and the answer is an empty
    list rather than an error.

    Args:
        db: An open session.

    Returns:
        The model names whose ``reasoning_budget_range`` is not NULL.
    """
    from sqlalchemy import text as sql

    exists = await db.execute(
        sql(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'llm_models' "
            "AND column_name = 'reasoning_budget_range'"
        )
    )
    if exists.first() is None:
        return []
    found = await db.execute(
        sql(
            "SELECT model_name FROM llm_models WHERE reasoning_budget_range IS NOT NULL "
            "ORDER BY model_name"
        )
    )
    return [row[0] for row in found]


def _report_reasoning(rows: list, overrides: list, curated_ranges: list[str]) -> int:
    """Report what the ADR-245 migrations and the new runtime would do here.

    Args:
        rows: The active ``llm_models`` rows.
        overrides: Every ``llm_config_overrides`` row.
        curated_ranges: Models still carrying a curated budget range.

    Returns:
        How many items need a human decision before deploying.
    """
    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.reasoning_intent import LEVELS, intent_from_legacy, is_intent_shape
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
    from src.infrastructure.llm.reasoning.coerce import coerce
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    problems = 0

    print("\n[4] stored reasoning values the migration would rewrite")
    shapes: dict[str, int] = {}
    for override in overrides:
        stored = override.reasoning_effort
        if not isinstance(stored, dict) or is_intent_shape(stored):
            continue
        key = f"{sorted(stored)} -> {intent_from_legacy(stored).level}"
        shapes[key] = shapes.get(key, 0) + 1
    for key, count in sorted(shapes.items(), key=lambda kv: -kv[1]):
        print(f"    x{count:<3} {key}")
    print(f"    total: {sum(shapes.values())} row(s) rewritten, {len(overrides)} examined")

    print("\n[5] declared ladders that speak a vocabulary the ladder does not have")
    off_ladder = []
    for row in rows:
        declared = row.reasoning_enum_values or []
        unknown = [level for level in declared if level not in LEVELS]
        if unknown:
            mapped = [intent_from_legacy({"effort": level}).level for level in declared]
            off_ladder.append((row.model_name, declared, mapped, unknown))
    for name, declared, mapped, unknown in off_ladder:
        print(f"    {name:30s} {declared} -> {mapped}  (unknown: {unknown})")
    print(f"    total: {len(off_ladder)} (migration e4f5a6b7c8d9 normalises them)")

    print("\n[6] slots whose reasoning depth the runtime would COERCE")
    coerced = []
    for slot in sorted(LLM_TYPES_REGISTRY):
        config = get_llm_config_for_agent(settings, slot)
        intent = config.reasoning_effort
        if intent is None or not config.model:
            continue
        row = next((r for r in rows if r.model_name == config.model), None)
        declared = (row.reasoning_enum_values or None) if row is not None else None
        profile = resolve_reasoning_profile(
            config.provider,
            config.model,
            model_levels=tuple(declared) if declared else None,
        )
        applied, moved = coerce(intent.level, profile)
        if moved:
            coerced.append((slot, config.model, intent.level, applied))
    for slot, model, requested, applied in coerced:
        print(f"    {slot:30s} {model:24s} {requested} -> {applied}")
    print(f"    total: {len(coerced)}")
    if coerced:
        problems += 1
        print("    -> the model will not do what the admin asked; retarget or accept the move")

    print("\n[7] curated budget ranges the column drop would discard")
    shown = curated_ranges[:8]
    suffix = " ..." if len(curated_ranges) > 8 else ""
    print(f"    {len(curated_ranges)} {shown}{suffix}")
    if curated_ranges:
        print("    -> the runtime reads the FAMILY's range; these values are already unused")

    return problems


def main() -> None:
    """Entry point."""
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
