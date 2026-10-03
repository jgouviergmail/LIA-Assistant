"""Keep authenticated source identity in display-only metadata, outside model data."""

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import ConnectorCredentials

EMAIL_ACCOUNT_DISPLAY_KEY = "_lia_email_account"


def bind_email_card_accounts(
    client: object, emails: list[dict[str, object]]
) -> list[dict[str, object]]:
    credentials = (
        client.credentials
        if isinstance(client, GoogleGmailClient | MicrosoftOutlookClient)
        else None
    )
    binding = credentials.account_binding if isinstance(credentials, ConnectorCredentials) else None
    bound = []
    for email in emails:
        display = email.get(FIELD_DISPLAY_ONLY)
        safe = (
            {key: value for key, value in display.items() if key != EMAIL_ACCOUNT_DISPLAY_KEY}
            if isinstance(display, dict)
            else {}
        )
        # Gmail's cache namespace includes this exact grant; Graph reads are live.
        if binding:
            safe[EMAIL_ACCOUNT_DISPLAY_KEY] = binding
        bound.append({**email, FIELD_DISPLAY_ONLY: safe})
    return bound
