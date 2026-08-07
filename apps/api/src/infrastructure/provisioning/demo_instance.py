"""Mark a database as a public demonstrator's.

Two switches decide whether an instance behaves as a demonstrator, and they
live in different places on purpose:

- ``DEMO_MODE_ENABLED`` describes the PROCESS. It can be set by a script, a
  shell, or a harness pointed at the wrong database.
- ``DEMO_INSTANCE_MARKER`` — written here — lives in the DATABASE the nightly
  purge would empty. Without it the purge refuses, whatever the process
  believes about itself.

That separation exists because of a real incident (2026-08-06): a proof script
forced the process flag against the development database and the sweep deleted
seven real accounts. The marker is the condition that travels with the data.

Provisioning is therefore deliberate, idempotent, and refuses a database that
already holds accounts — marking a populated database would arm a nightly
purge on somebody's real data.

Created: 2026-08-06 (live-demonstrator programme, lot 4)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.registry import invalidate_setting_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.provisioning.demo_defaults import apply_demo_setting_defaults
from src.infrastructure.provisioning.demo_llm import (
    apply_demo_llm_configuration,
    unbillable_model,
)

logger = structlog.get_logger(__name__)

#: Refusal reason for a model this database cannot price. Named because two
#: refusals now exist and they read nothing alike to an operator.
_REASON_MODEL_NOT_BILLABLE = "model_not_billable"


@dataclass(frozen=True)
class ProvisionReport:
    """What the provisioning did — a silent step leaves an operator guessing."""

    marker_written: bool = False
    already_provisioned: bool = False
    refused_reason: str | None = None
    account_count: int = 0
    unbillable_model: str | None = None

    def summary(self) -> str:
        """One line an operator can read in a deploy log."""
        if self.refused_reason == _REASON_MODEL_NOT_BILLABLE:
            return (
                f"REFUSED ({self.refused_reason}): '{self.unbillable_model}' has no active "
                "per-1M-token price in this database, so every call would be recorded at "
                "0 EUR and the daily spend ceiling would never fire. Point "
                "DEMO_INSTANCE_LLM_MODEL at a model this catalogue prices — the "
                "migrations build it, the reference seed bundle is refused here "
                "because they already inserted the personalities (ADR-215)."
            )
        if self.refused_reason:
            return (
                f"REFUSED ({self.refused_reason}): the database holds "
                f"{self.account_count} account(s). Use --force only if this "
                "really is a throwaway demonstrator database."
            )
        if self.already_provisioned:
            return "Already provisioned: the demonstrator marker is present."
        return "Demonstrator marker written: the nightly purge is now armed."


async def verify_spend_ceiling() -> str | None:
    """Ask a RUNNING instance whether it can measure what it spends.

    Read-only on purpose: this runs against a live demonstrator, next to the
    network-surface check of ``task demo:verify`` and during an incident. It
    answers the one question the ceiling depends on — is the configured model
    priced by the catalogue this instance actually queries.

    Returns:
        The model name when the ledger would stay flat whatever is spent,
        ``None`` when the ceiling can see the money.
    """
    async with get_db_context() as db:
        return await unbillable_model(
            db,
            provider=(getattr(settings, "demo_instance_llm_provider", "") or "").strip(),
            model=(getattr(settings, "demo_instance_llm_model", "") or "").strip(),
        )


async def provision_demo_instance(*, force: bool = False) -> ProvisionReport:
    """Write the demonstrator marker into this database.

    Args:
        force: Write the marker even when the database already holds
            accounts. Deliberate, explicit and loud — never a default.

    Returns:
        What happened, including why nothing did.
    """
    async with get_db_context() as db:
        # Before anything is written: can this instance MEASURE what it
        # spends? A marker arms a nightly purge, and the LLM configuration
        # points every type at one model — both are pointless, and the second
        # is dangerous, if the ceiling that bounds the bill reads a ledger the
        # catalogue leaves at zero (measured 2026-08-07, see demo_llm.py).
        blind_on = await unbillable_model(
            db,
            provider=(getattr(settings, "demo_instance_llm_provider", "") or "").strip(),
            model=(getattr(settings, "demo_instance_llm_model", "") or "").strip(),
        )
        if blind_on is not None:
            logger.error(
                "demo_instance_provisioning_refused",
                reason=_REASON_MODEL_NOT_BILLABLE,
                model=blind_on,
            )
            return ProvisionReport(
                refused_reason=_REASON_MODEL_NOT_BILLABLE, unbillable_model=blind_on
            )

        existing = (
            await db.execute(
                select(SystemSetting).where(
                    SystemSetting.key == SystemSettingKey.DEMO_INSTANCE_MARKER
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.value == "true":
            # The marker is written once; the LLM configuration is what an
            # operator revisits — a new key, a cheaper model. Returning here
            # without applying it would make re-provisioning a no-op exactly
            # when it is being run to change something.
            llm_types = await apply_demo_llm_configuration(db)
            defaults = await apply_demo_setting_defaults(db)
            await db.commit()
            logger.info(
                "demo_instance_already_provisioned",
                llm_types_configured=llm_types,
                settings_defaulted=defaults,
            )
            return ProvisionReport(already_provisioned=True)

        from src.domains.users.models import User

        account_count = int(
            (await db.execute(select(func.count()).select_from(User))).scalar_one() or 0
        )
        if account_count > 0 and not force:
            # Marking a populated database arms a nightly purge on real
            # accounts. This is the guard the 2026-08-06 incident earned.
            logger.error(
                "demo_instance_provisioning_refused",
                reason="database_not_empty",
                account_count=account_count,
            )
            return ProvisionReport(refused_reason="database_not_empty", account_count=account_count)

        if existing is not None:
            existing.value = "true"
        else:
            db.add(
                SystemSetting(
                    key=SystemSettingKey.DEMO_INSTANCE_MARKER,
                    value="true",
                    change_reason="demo instance provisioning",
                )
            )

        # A marked instance that cannot answer is not provisioned. The
        # registry points each LLM type at the provider the full product
        # uses; a demonstrator holds one key, so every type is repointed at
        # it — see demo_llm.py for what the first bring-up measured.
        llm_types = await apply_demo_llm_configuration(db)
        # What a visitor should see differs from a private instance: the
        # debug panel is the demonstration, not a support burden.
        await apply_demo_setting_defaults(db)

        await db.commit()

    await invalidate_setting_cache(SystemSettingKey.DEMO_INSTANCE_MARKER)
    logger.warning(
        "demo_instance_provisioned",
        forced=force,
        account_count=account_count,
        detail="the nightly visitor-account purge is now armed on this database",
        llm_types_configured=llm_types,
    )
    return ProvisionReport(marker_written=True, account_count=account_count)
