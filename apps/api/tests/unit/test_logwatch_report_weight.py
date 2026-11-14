"""The daily report stays readable: two sections are summarised, not enumerated.

Measured on production for the report of 2026-11-09: 2,053 lines, of which the
sudo section took 1,695 (every command, 684 of them the demonstrator's iptables
rules) and the systemd section listed the id of each of 1,191 sessions. At
detail 5 the same day reads in 29 and 28 lines. The reading that followed took
the report for six problems; four were not there.

logwatch merges ``default.conf``, ``dist.conf`` and the deployed directory for a
service, so an override carries the detail and nothing else: a ``LogFile``
declared again would make the service read its log twice.
"""

from __future__ import annotations

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

SERVICES = repo_root_or_skip() / "infrastructure" / "logwatch" / "conf" / "services"
SUMMARISED = ("sudo", "systemd")


def _settings(name: str) -> dict[str, str]:
    """The ``key = value`` lines of a service override, comments left out."""
    lines = (SERVICES / f"{name}.conf").read_text(encoding="utf-8").splitlines()
    pairs = (line.split("=", 1) for line in lines if line.strip() and not line.startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


@pytest.mark.parametrize("service", SUMMARISED)
def test_the_section_is_summarised_below_the_reports_global_detail(service: str) -> None:
    assert _settings(service) == {"Detail": "5"}


@pytest.mark.parametrize("service", SUMMARISED)
def test_the_override_reaches_the_host_with_unix_line_endings(service: str) -> None:
    """deploy.sh copies ``conf/services/*.conf``; a CR would end the value."""
    assert b"\r" not in (SERVICES / f"{service}.conf").read_bytes()
