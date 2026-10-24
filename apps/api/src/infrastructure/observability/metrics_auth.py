"""Account-security metrics: password resets (ADR-363) and the bot check (ADR-364).

What each reset request did, what each reset link gave when it was used, and
what each Turnstile check concluded. The labels are bounded — never an
account, an address or an IP: a burst aimed at one account reads as
``throttled`` without naming it, and an attempt on an administrator as
``refused_superuser``. Read by dashboard 09 and the ``PasswordResetAbuse`` and
``TurnstileUnavailable`` core alerts.
"""

from prometheus_client import Counter

password_reset_requests_total = Counter(
    "password_reset_requests_total",
    "Password-reset requests by what was done with them (ADR-363)",
    ["outcome"],
)

password_reset_confirmations_total = Counter(
    "password_reset_confirmations_total",
    "Password-reset link uses by their result (ADR-363)",
    ["outcome"],
)

# The Turnstile bot check at each password door (ADR-364): `unavailable` is
# Cloudflare not answering — the sign-in then proceeds, a sign-up or a reset
# request is refused. Read by dashboard 09 and the `TurnstileUnavailable` alert.
turnstile_verifications_total = Counter(
    "turnstile_verifications_total",
    "Turnstile bot checks by door and outcome (ADR-364)",
    ["action", "outcome"],
)
