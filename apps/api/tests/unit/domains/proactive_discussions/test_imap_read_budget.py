"""Each IMAP command is admitted before it can reach a socket; cleanup remains local."""

from imaplib import IMAP4_SSL
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.core.read_budget import ReadCallBudget, ReadCallLimit, read_call_budget
from src.domains.connectors.clients.bounded_imap import BoundedIMAP4SSL

pytestmark = pytest.mark.unit


def test_command_budget_and_socket_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []

    def send(_self, data):
        sent.append(data)

    monkeypatch.setattr(IMAP4_SSL, "send", send)
    client = object.__new__(BoundedIMAP4SSL)
    client.shutdown = MagicMock()
    budget = ReadCallBudget(owner=UUID(int=1), limit=1)
    with read_call_budget(budget):
        client.send(b"tag CAPABILITY\r\n")
        with pytest.raises(ReadCallLimit):
            client.send(b"tag LOGIN fictional fictional\r\n")
        client.logout()
    assert sent == [b"tag CAPABILITY\r\n"] and budget.calls == 1
    client.shutdown.assert_called_once_with()
