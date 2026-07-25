"""Every production container gets the secrets it needs, and no others (SEC-037).

The web container was declared with ``env_file: .env``, which handed a Next.js
process the entire production secret set — database credentials, the Fernet key,
the JWT secret, every LLM and OAuth secret — none of which it uses. One line,
and the blast radius of any server-side RCE in the frontend or its dependency
tree became the whole platform.

The failure mode is that `env_file` is *convenient*: it is what someone adds
when a variable turns out to be missing, and it silently re-grants everything.
This guard makes that specific regression visible instead of invisible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

# Services that legitimately need the full secret file. The API is the component
# that talks to PostgreSQL, Redis, the LLM providers and every OAuth issuer —
# narrowing it would be a list of nearly everything, maintained by hand.
SERVICES_ALLOWED_FULL_ENV_FILE = {"api"}

# Substrings that mark a variable as carrying a credential. Matched on the NAME
# only: the values here are `${...}` references, never literals.
SECRET_NAME_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "_KEY",
    "APIKEY",
    "CREDENTIAL",
    "PRIVATE",
    "DSN",
)

# Names that contain a marker but are not credentials.
SECRET_NAME_EXCEPTIONS = {
    # Published to the browser by design — it is in the client bundle already.
    "NEXT_PUBLIC_FIREBASE_API_KEY",
    "NEXT_PUBLIC_FIREBASE_VAPID_KEY",
}


def _compose() -> dict[str, Any]:
    """Parse the production compose file."""
    return yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))


def _service_names() -> list[str]:
    """Every service declared in the production compose file."""
    return sorted(_compose()["services"].keys())


def _env_names(service: dict[str, Any]) -> list[str]:
    """Variable names from a service's ``environment`` block.

    Handles both accepted forms: the ``- NAME=value`` list and the
    ``NAME: value`` mapping.

    Args:
        service: One service definition.

    Returns:
        Declared variable names.
    """
    environment = service.get("environment") or []
    if isinstance(environment, dict):
        return list(environment.keys())
    return [str(entry).split("=", 1)[0] for entry in environment]


class TestSecretsAreScopedToTheServicesThatNeedThem:
    """`env_file: .env` is the whole secret set — it needs a reason."""

    @pytest.mark.parametrize("name", _service_names())
    def test_service_does_not_take_the_full_env_file_without_reason(self, name: str):
        """Only explicitly allowed services may mount the complete .env."""
        service = _compose()["services"][name]

        if name in SERVICES_ALLOWED_FULL_ENV_FILE:
            pytest.skip(f"{name} legitimately needs the full secret set")

        assert "env_file" not in service, (
            f"service '{name}' takes env_file, granting it every production secret. "
            f"Declare the variables it actually needs under `environment:` instead, "
            f"or add it to SERVICES_ALLOWED_FULL_ENV_FILE with a written reason."
        )

    def test_the_web_container_receives_no_credential(self):
        """The frontend needs no secret at all — if it does, the design is wrong.

        Next.js talks to the API over the internal network and the API holds the
        credentials. A secret appearing here means the frontend started doing
        something it should be asking the API to do.
        """
        names = _env_names(_compose()["services"]["web"])

        leaked = [
            name
            for name in names
            if name not in SECRET_NAME_EXCEPTIONS
            and any(marker in name.upper() for marker in SECRET_NAME_MARKERS)
        ]

        assert leaked == [], f"the web container is handed credentials: {leaked}"

    def test_the_web_container_still_gets_what_it_reads_at_runtime(self):
        """Counterpart: locking it down must not starve it.

        These three are read while the server runs — the rest of next.config.ts
        is serialised into the build. Losing them would not fail loudly at
        startup; RAG uploads would just start rejecting legitimate files.
        """
        names = _env_names(_compose()["services"]["web"])

        for required in ("NODE_ENV", "API_URL_SERVER", "RAG_SPACES_MAX_FILE_SIZE_MB"):
            assert required in names, f"web container lost {required}"

    def test_the_api_still_receives_the_secret_file(self):
        """Guards the guard: an over-eager cleanup here would break the API."""
        assert "env_file" in _compose()["services"]["api"]


class TestNoServiceIsPublishedToTheWorld:
    """Published ports must bind to loopback (SEC-015).

    cloudflared runs under host systemd and reaches every service over
    127.0.0.1, so a port bound to 0.0.0.0 is reachable from the LAN without
    passing through Cloudflare — no WAF, no TLS termination, no access log.
    Fifteen of the sixteen published ports already did this; `web` was the lone
    exception, which is how the pattern got broken silently.
    """

    @pytest.mark.parametrize("name", _service_names())
    def test_service_publishes_only_on_loopback(self, name: str):
        """Every host-published port names an explicit loopback address."""
        ports = _compose()["services"][name].get("ports") or []

        exposed = [str(p) for p in ports if not str(p).startswith("127.0.0.1:")]

        assert exposed == [], (
            f"service '{name}' publishes {exposed} on every interface. "
            f"Bind it as 127.0.0.1:<host>:<container> — cloudflared reaches it there."
        )
