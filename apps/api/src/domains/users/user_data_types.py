"""Shared lifecycle classifications; the table and column maps remain their authorities."""

from dataclasses import dataclass
from enum import Enum


class TableDataClass(str, Enum):
    """How a table relates to a user's personal data lifecycle."""

    USER_PURGED = "user_purged"
    """User-scoped rows explicitly deleted by the account-deletion purge."""
    USER_CASCADE = "user_cascade"
    """Deleted through a CASCADE chain from a USER_PURGED table."""
    USER_ROW_SCRUBBED = "user_row_scrubbed"
    """The users row is retained with its personal columns scrubbed."""
    BILLING_RETAINED = "billing_retained"
    """Kept for dispute resolution after account deletion."""
    GLOBAL = "global"
    """Instance configuration, catalogues and administrative records."""


class ExportPolicy(str, Enum):
    """Whether the GDPR export includes a table's rows."""

    FULL = "full"
    """Exported, with secret-column redaction where needed."""
    EXCLUDED = "excluded"
    """Never exported: secret, derived or non-user data."""


@dataclass(frozen=True)
class TableRule:
    """Lifecycle class, export policy and audited rationale for one table."""

    data_class: TableDataClass
    export: ExportPolicy
    reason: str
