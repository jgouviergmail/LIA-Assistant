"""Account export configuration module (security program D3).

Full-account GDPR-portability exports: flag, storage location, size cap
(arbitration A5), retention, and executor cadence.
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    ACCOUNT_EXPORT_MAX_BYTES_DEFAULT,
    ACCOUNT_EXPORT_RETENTION_HOURS_DEFAULT,
    ACCOUNT_EXPORT_STALE_RUNNING_MINUTES_DEFAULT,
    EXPORTS_STORAGE_PATH_DEFAULT,
)


class AccountExportSettings(BaseSettings):
    """Full-account export settings."""

    account_export_enabled: bool = Field(
        default=False,
        description="Master switch for full-account exports (router + executor).",
    )

    exports_storage_path: str = Field(
        default=EXPORTS_STORAGE_PATH_DEFAULT,
        description="Directory holding built archives ({path}/{user_id}/{job_id}.zip).",
    )

    account_export_max_bytes: int = Field(
        default=ACCOUNT_EXPORT_MAX_BYTES_DEFAULT,
        gt=0,
        description="Hard cap on archive size (A5); larger builds fail with export_too_large.",
    )

    account_export_retention_hours: int = Field(
        default=ACCOUNT_EXPORT_RETENTION_HOURS_DEFAULT,
        gt=0,
        description="Download window after completion; the sweep purges past it.",
    )

    account_export_stale_running_minutes: int = Field(
        default=ACCOUNT_EXPORT_STALE_RUNNING_MINUTES_DEFAULT,
        gt=0,
        description="A RUNNING job older than this is considered crashed and failed.",
    )
