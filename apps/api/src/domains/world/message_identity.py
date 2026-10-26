"""An immutable owned request identity; text never appears in a SQL tombstone."""

import hashlib
import hmac

from src.domains.world.messages import TimedMessageRequest


def message_fingerprint(
    secret: str, account: str, payload: TimedMessageRequest, extra: str = ""
) -> str:
    """HMAC the account, immutable request and audience discriminator without persisting text."""
    return hmac.new(
        secret.encode(),
        (account + "\n" + payload.model_dump_json() + "\n" + extra).encode(),
        hashlib.sha256,
    ).hexdigest()
