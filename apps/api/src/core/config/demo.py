"""
Public demonstrator configuration.

An instance either IS a demonstrator or it is not: this is a DEPLOYMENT
property, never a runtime toggle. Defaulting it on would auto-approve
accounts on a private instance, so every value here is inert until an
operator sets it explicitly.

The demonstrator runs the REAL application. Only four behaviours differ,
each gated on ``DEMO_MODE_ENABLED``:
- verifying the email activates the account (no administrator is watching a
  demo at 2am);
- registration requires accepting the terms, and records which version;
- registration stops for the day once the instance has enrolled its ceiling,
  because every account costs one email against the operator's quota;
- a nightly job wipes every visitor account so the next day starts clean.

Created: 2026-08-06 (live-demonstrator programme, lot 2)
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DEMO_ACCOUNT_PURGE_HOUR_DEFAULT,
    DEMO_ACCOUNT_PURGE_MINUTE_DEFAULT,
    DEMO_DAILY_REPORT_HOUR_DEFAULT,
    DEMO_DAILY_REPORT_MINUTE_DEFAULT,
    DEMO_DAILY_SIGNUP_LIMIT_DEFAULT,
    DEMO_TERMS_VERSION_DEFAULT,
)


class DemoSettings(BaseSettings):
    """Settings for the public demonstrator mode."""

    demo_mode_enabled: bool = Field(
        default=False,
        description=(
            "Whether this instance is a public demonstrator. When true, "
            "verifying an email activates the account, registration requires "
            "accepting the terms, and the nightly purge wipes visitor "
            "accounts. Never enable it on a private instance."
        ),
    )

    demo_terms_version: str = Field(
        default=DEMO_TERMS_VERSION_DEFAULT,
        min_length=1,
        description=(
            "Identifier of the terms a visitor accepts at registration, "
            "recorded on the account. A consent with no version cannot be "
            "defended later: bump it whenever the terms change."
        ),
    )

    demo_instance_public_url: str = Field(
        default="",
        description=(
            "Public URL of the demonstrator, advertised on THIS instance's "
            "landing page when an administrator switches the link on. A "
            "deployment fact: it changes when the domain does. Empty = no "
            "link can be shown, whatever the switch says."
        ),
    )

    demo_instance_llm_provider: str = Field(
        default="",
        description=(
            "Provider every LLM type is pointed at on a demonstrator. The "
            "registry ships one provider per type, chosen for the full "
            "product; an instance holding a single key must override them "
            "all or the graph calls providers it has no key for. Empty "
            "leaves the registry untouched."
        ),
    )
    demo_instance_llm_model: str = Field(
        default="",
        description="Model used for every LLM type on a demonstrator.",
    )
    demo_shared_search_api_key: str = Field(
        default="",
        description=(
            "Search API key the instance LENDS to every visitor account. Brave "
            "Search is a per-user connector, so without this a visitor would "
            "see the search agent and never be able to use it. Empty = no "
            "search connector is provisioned. Only read in demo mode."
        ),
    )

    demo_daily_signup_limit: int | None = Field(
        default=DEMO_DAILY_SIGNUP_LIMIT_DEFAULT,
        ge=1,
        description=(
            "Accounts this instance may create per UTC day, in demo mode. "
            "Per-address rate limiting bounds one caller, never an instance: "
            "the identity it keys on comes from a header the caller supplies, "
            "and thirty accounts were created in 6,4 seconds when that was "
            "the only bound (measured 2026-08-07). Each account costs one "
            "verification email against the operator's smarthost quota, which "
            "the daily SPEND ceiling does not see. None = unlimited."
        ),
    )

    demo_daily_report_recipient: str = Field(
        default="",
        description=(
            "Operator address for the demonstrator's daily report. Empty disables "
            "the report; the instance keeps running unchanged."
        ),
    )
    demo_daily_report_hour: int = Field(
        default=DEMO_DAILY_REPORT_HOUR_DEFAULT,
        ge=0,
        le=23,
        description="UTC hour of the daily report — must precede the purge.",
    )
    demo_daily_report_minute: int = Field(
        default=DEMO_DAILY_REPORT_MINUTE_DEFAULT,
        ge=0,
        le=59,
        description="UTC minute of the daily report.",
    )
    demo_account_purge_hour: int = Field(
        default=DEMO_ACCOUNT_PURGE_HOUR_DEFAULT,
        ge=0,
        le=23,
        description="UTC hour of the nightly visitor-account purge.",
    )

    demo_account_purge_minute: int = Field(
        default=DEMO_ACCOUNT_PURGE_MINUTE_DEFAULT,
        ge=0,
        le=59,
        description="UTC minute of the nightly visitor-account purge.",
    )
