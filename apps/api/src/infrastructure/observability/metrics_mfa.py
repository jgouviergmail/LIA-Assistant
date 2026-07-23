"""Prometheus metrics for strong authentication (security program D1).

Tracks WebAuthn passkey ceremonies (and, from Lot 2 on, TOTP verifications).
Counters carry no PII: ceremony kind and outcome only.
"""

from prometheus_client import Counter

# ============================================================================
# WEBAUTHN CEREMONY METRICS
# ============================================================================

webauthn_ceremonies_total = Counter(
    "webauthn_ceremonies_total",
    "Completed WebAuthn ceremonies by kind and outcome",
    ["ceremony", "status"],  # ceremony: register, authenticate — status: success, failure
)


def track_webauthn_ceremony(ceremony: str, status: str) -> None:
    """Count one completed WebAuthn ceremony.

    Args:
        ceremony: ``register`` or ``authenticate``.
        status: ``success`` or ``failure``.
    """
    webauthn_ceremonies_total.labels(ceremony=ceremony, status=status).inc()


# ============================================================================
# DEVICE SESSION METRICS (D2)
# ============================================================================

session_revocations_total = Counter(
    "session_revocations_total",
    "User-initiated session revocations from the device list",
    ["scope"],  # scope: one, others
)

login_notifications_total = Counter(
    "login_notifications_total",
    "New-login FCM notifications by outcome",
    ["status"],  # status: sent, skipped_known, skipped_pref, failed
)

# ============================================================================
# ACCOUNT EXPORT METRICS (D3)
# ============================================================================

account_export_jobs_total = Counter(
    "account_export_jobs_total",
    "Account export lifecycle events",
    ["status"],  # status: requested, downloaded (build outcomes live in job rows)
)

# ============================================================================
# TOTP METRICS
# ============================================================================

totp_verifications_total = Counter(
    "totp_verifications_total",
    "TOTP/backup-code verifications by context and outcome",
    ["context", "status"],  # context: login, confirm — status: success, failure
)


def track_totp_verification(context: str, status: str) -> None:
    """Count one TOTP (or backup code) verification.

    Args:
        context: ``login`` or ``confirm``.
        status: ``success`` or ``failure``.
    """
    totp_verifications_total.labels(context=context, status=status).inc()
