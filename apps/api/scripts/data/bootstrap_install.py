"""Atomic stdin-only install bootstrap (ADR-215, B10/B11).

Invoked as ``python -m scripts.data.bootstrap_install`` from the API
container workdir (same convention as ``create_admin``). Reads EXACTLY one
JSON document from stdin:

    {"admin": {"email": ..., "password": ..., "full_name": ...},
     "provider_keys": {"<provider>": ..., ...}}

where the required ``provider_keys`` set is DERIVED at runtime by
``required_current_core_provider_ids()`` (post-seed effective core,
B10-bis — currently openai + deepseek), and, in ONE database transaction: creates/promotes the admin (through the
strict backend password policy) and upserts every required provider key
(encrypted rows — B10-bis owner arbitration: the seeded LLM overrides are
read-only here, the questionnaire collects one key per provider the
POST-SEED effective core resolves to). After the commit, the cross-worker
LLM cache invalidation is published; its failure returns a stable non-secret
code and an idempotent resume republishes without duplicating rows.

Output is non-secret only: admin id/email, provider ids, unkeyed optional
capabilities, status. No secret ever appears in argv, logs, or exceptions.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class BootstrapPayload:
    """Validated stdin document (never echoed)."""

    admin_email: str
    admin_password: str
    admin_full_name: str
    provider_keys: dict[str, str]


@dataclass(frozen=True)
class BootstrapResult:
    """Non-secret outcome for the installer report."""

    admin_id: uuid.UUID
    admin_email: str
    providers: tuple[str, ...]
    optional_unkeyed: dict[str, str]
    status: str


class BootstrapInputError(ValueError):
    """Malformed or incomplete stdin payload (non-secret message only)."""


def parse_payload(raw: str) -> BootstrapPayload:
    """Validate the stdin JSON without ever echoing its values.

    Args:
        raw: The single stdin document.

    Returns:
        The validated payload.

    Raises:
        BootstrapInputError: With a stable, value-free code.
    """
    from src.domains.llm_config.install_contract import (
        required_current_core_provider_ids,
    )

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BootstrapInputError("invalid_json") from exc
    admin = document.get("admin")
    keys = document.get("provider_keys")
    if not isinstance(admin, dict) or not isinstance(keys, dict):
        raise BootstrapInputError("missing_sections")
    email = admin.get("email")
    password = admin.get("password")
    full_name = admin.get("full_name") or "Admin"
    if not email or not password:
        raise BootstrapInputError("missing_admin_fields")
    required = required_current_core_provider_ids()
    missing = [p for p in required if not keys.get(p)]
    if missing:
        raise BootstrapInputError(f"missing_provider_keys:{','.join(missing)}")
    extra = [p for p in keys if p not in required]
    if extra:
        raise BootstrapInputError(f"unexpected_provider_keys:{','.join(sorted(extra))}")
    return BootstrapPayload(
        admin_email=str(email),
        admin_password=str(password),
        admin_full_name=str(full_name),
        provider_keys={p: str(keys[p]) for p in required},
    )


async def bootstrap(payload: BootstrapPayload, db: AsyncSession) -> BootstrapResult:
    """Admin + every provider key in ONE transaction; publish after commit."""
    from scripts.data.create_admin import ensure_admin
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.install_contract import (
        OPTIONAL_SEEDED_CAPABILITIES,
    )
    from src.domains.llm_config.service import upsert_provider_key_uncommitted

    async with db.begin():
        admin_id = await ensure_admin(
            db,
            email=payload.admin_email,
            password=payload.admin_password,
            full_name=payload.admin_full_name,
        )
        for provider, key in payload.provider_keys.items():
            await upsert_provider_key_uncommitted(
                db, provider=provider, key=key, updated_by=admin_id
            )

    # Post-commit publication (hot-update contract). The installer's real
    # worker barrier is the forced API recreation; this keeps live workers
    # coherent when bootstrap re-runs against a running stack.
    try:
        await LLMConfigOverrideCache.invalidate_and_reload(db)
        status = "bootstrapped"
    except Exception as exc:  # stable non-secret failure; resume republishes
        # Exception TYPE only (value-free): stdout stays pure result JSON.
        print(f"publication_failed:{type(exc).__name__}", file=sys.stderr)
        status = "bootstrapped_publication_failed"

    return BootstrapResult(
        admin_id=admin_id,
        admin_email=payload.admin_email,
        providers=tuple(sorted(payload.provider_keys)),
        optional_unkeyed=dict(OPTIONAL_SEEDED_CAPABILITIES),
        status=status,
    )


async def _run() -> int:
    # The ORM path (provider-key upsert, cache reload) configures the full
    # mapper graph: without the complete registry, User's relationships
    # (e.g. UserSkillState) fail to resolve at first flush.
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.database.session import AsyncSessionLocal

    import_all_models()

    try:
        payload = parse_payload(sys.stdin.read())
    except BootstrapInputError as exc:
        print(json.dumps({"status": "input_error", "code": str(exc)}))
        return 2
    async with AsyncSessionLocal() as session:
        result = await bootstrap(payload, session)
    print(
        json.dumps(
            {
                "status": result.status,
                "admin_id": str(result.admin_id),
                "admin_email": result.admin_email,
                "providers": list(result.providers),
                "optional_unkeyed": result.optional_unkeyed,
            }
        )
    )
    return 0 if result.status == "bootstrapped" else 3


def main() -> int:
    """Entry point: one stdin JSON document, non-secret JSON on stdout."""
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
