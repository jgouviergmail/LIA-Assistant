"""IMAP's actual outgoing frames share the context read budget, including authentication."""

from collections.abc import Buffer
from imaplib import IMAP4, IMAP4_SSL

from imap_tools import MailBox

from src.core.read_budget import claim_read_call, current_read_owner


class BoundedIMAP4SSL(IMAP4_SSL):
    """An IMAP transport whose every outgoing frame claims the current read budget."""

    def send(self, data: Buffer) -> None:
        """Claim one physical call from the read budget, then send the frame.

        Raises:
            ValueError: The transport runs outside a bounded read.
            ReadCallLimit: The read budget is spent.
        """
        owner = current_read_owner()
        if owner is None:
            raise ValueError("bounded IMAP transport lost its read owner")
        claim_read_call(owner)
        super().send(data)

    def logout(self) -> tuple[str, list[bytes | tuple[bytes, bytes]]]:
        """Close the session locally: no command escapes the cap, nothing is marked seen."""
        # No network command can escape the cap during cleanup. Closing a read
        # session locally is sufficient and never marks a message as seen.
        self.shutdown()
        return "BYE", [b"bounded read session closed"]


class BoundedMailBox(MailBox):
    """A mailbox opened on the bounded IMAP transport."""

    def _get_mailbox_client(self) -> IMAP4:
        return BoundedIMAP4SSL(
            host=self._host, port=self._port, timeout=self._timeout, ssl_context=self._ssl_context
        )
