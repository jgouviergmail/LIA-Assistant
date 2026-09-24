"""Keyless connectors belong to the instance: drop their per-account rows (ADR-307).

Revision ID: b2e6d0f4a8c1
Revises: d5f8b2a6c9e3
Create Date: 2026-09-23 22:00:00.000000

Wikipedia, the browser, Google Places, Google Weather and Google Environment ask
nothing of the person. Whether one of them serves an account is now decided by
the instance alone (``connectors/keyless.py``): the administrator's global
switch, the platform key, the browser flag. A per-account row of those types is
read by nothing any more, and the settings no longer offer them.

Deleting the rows is what makes « always active » true for the accounts that
had switched one off, never received one (created before sign-up
provisioning), or kept a ``REVOKED`` row after an administrator re-enabled the
type: from this revision on, none of them has anything left that could say no.

The stored values are the enum NAMES (``native_enum=False`` stores the member
name, measured on the dev database), which is why they are upper case here.

The downgrade gives the previous code the rows it reads: one ``ACTIVE`` row per
type and non-deleted account, except for a type the administrator disabled —
the previous sign-up step skipped those too. It cannot read the instance's
``GOOGLE_API_KEY`` or ``BROWSER_ENABLED``, so it may re-create a row the
previous step would have skipped; the previous settings screen lets the person
switch it off.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e6d0f4a8c1"
down_revision: str | None = "d5f8b2a6c9e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: ``ConnectorType`` members the instance provides, as STORED (member names),
#: frozen here so a later rename of the enum cannot change what this revision did.
KEYLESS_STORED_TYPES: tuple[str, ...] = (
    "BROWSER",
    "GOOGLE_ENVIRONMENT",
    "GOOGLE_PLACES",
    "GOOGLE_WEATHER",
    "WIKIPEDIA",
)

#: The platform-key members among them (their previous rows said so).
PLATFORM_KEY_STORED_TYPES: tuple[str, ...] = (
    "GOOGLE_ENVIRONMENT",
    "GOOGLE_PLACES",
    "GOOGLE_WEATHER",
)


#: The upgrade: every per-account row of a keyless type goes.
DELETE_KEYLESS_ROWS = sa.text("DELETE FROM connectors WHERE connector_type IN :types").bindparams(
    sa.bindparam("types", expanding=True)
)

#: The downgrade: one ACTIVE row per keyless type and non-deleted account that
#: holds none, except for a type the administrator disabled.
RECREATE_KEYLESS_ROWS = sa.text("""
    INSERT INTO connectors (
        id, user_id, connector_type, status, scopes,
        credentials_encrypted, metadata, created_at, updated_at
    )
    SELECT
        gen_random_uuid(), u.id, t.connector_type, 'ACTIVE', '[]'::jsonb,
        '{}',
        jsonb_build_object(
            'auth_type',
            CASE WHEN t.connector_type IN :platform_key_types
                 THEN 'global_api_key' ELSE 'none' END,
            'functionally_verified', false,
            'provisioned_by', 'migration_downgrade'
        ),
        now(), now()
    FROM users AS u
    CROSS JOIN unnest(CAST(:types AS varchar[])) AS t (connector_type)
    WHERE u.deleted_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM connector_global_config AS g
          WHERE g.connector_type = t.connector_type AND NOT g.is_enabled
      )
      AND NOT EXISTS (
          SELECT 1 FROM connectors AS c
          WHERE c.user_id = u.id AND c.connector_type = t.connector_type
      )
    """).bindparams(sa.bindparam("platform_key_types", expanding=True))


def statement_params() -> dict[str, list[str]]:
    """The bound values both statements read (each statement takes what it names)."""
    return {
        "types": list(KEYLESS_STORED_TYPES),
        "platform_key_types": list(PLATFORM_KEY_STORED_TYPES),
    }


def upgrade() -> None:
    """Delete every per-account row of a keyless connector type."""
    deleted = op.get_bind().execute(DELETE_KEYLESS_ROWS, statement_params()).rowcount
    logger.info("keyless connector rows deleted: %s", deleted)


def downgrade() -> None:
    """Re-create one ACTIVE row per keyless type and non-deleted account."""
    inserted = op.get_bind().execute(RECREATE_KEYLESS_ROWS, statement_params()).rowcount
    logger.info("keyless connector rows re-created: %s", inserted)
