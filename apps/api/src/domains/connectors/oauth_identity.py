"""Verify the provider account behind a grouped connector authorization."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from jose import JWTError, jwt

_JWKS_URLS = {
    "google": "https://www.googleapis.com/oauth2/v3/certs",
    "microsoft": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
}


@dataclass(frozen=True)
class ProviderIdentity:
    """Account identifier that cannot change when a display email changes."""

    subject: str
    email: str | None


async def fetch_provider_keys(provider: str) -> dict[str, Any]:
    """Fetch public signing keys only from the provider's fixed endpoint."""
    url = _JWKS_URLS.get(provider)
    if url is None:
        raise ValueError("Unsupported OAuth provider")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        keys: dict[str, Any] = response.json()
    if not isinstance(keys, dict) or not isinstance(keys.get("keys"), list):
        raise ValueError("Invalid provider signing keys")
    return keys


def _expected_issuer(provider: str, unverified: dict[str, Any]) -> str:
    if provider == "google":
        issuer = unverified.get("iss")
        if issuer not in ("https://accounts.google.com", "accounts.google.com"):
            raise ValueError("Invalid Google token issuer")
        return str(issuer)
    if provider == "microsoft":
        tenant = unverified.get("tid")
        if not isinstance(tenant, str):
            raise ValueError("Missing Microsoft tenant")
        try:
            tenant_id = UUID(tenant)
        except ValueError as error:
            raise ValueError("Invalid Microsoft tenant") from error
        if str(tenant_id) != tenant:
            raise ValueError("Noncanonical Microsoft tenant")
        return f"https://login.microsoftonline.com/{tenant}/v2.0"
    raise ValueError("Unsupported OAuth provider")


def _matching_key(
    provider: str, jwks: dict[str, Any], kid: str, issuer: str, tenant: str | None
) -> dict[str, Any]:
    for candidate in jwks.get("keys", []):
        if not isinstance(candidate, dict) or candidate.get("kid") != kid:
            continue
        if candidate.get("kty") != "RSA":
            continue
        if provider == "microsoft":
            key_issuer = candidate.get("issuer")
            if not isinstance(key_issuer, str) or not tenant:
                continue
            if key_issuer.replace("{tenantid}", tenant) != issuer:
                continue
        return candidate
    raise ValueError("Unknown identity token signing key")


def _account_from_claims(provider: str, claims: dict[str, Any]) -> ProviderIdentity:
    if provider == "google":
        subject = claims.get("sub")
        email = claims.get("email")
    else:
        object_id = claims.get("oid")
        tenant_id = claims.get("tid")
        if not isinstance(object_id, str) or not isinstance(tenant_id, str):
            raise ValueError("Microsoft identity is incomplete")
        subject = f"{tenant_id}:{UUID(object_id)}"
        email = claims.get("preferred_username") or claims.get("email")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError("Identity subject is missing")
    if email is not None and (not isinstance(email, str) or len(email) > 320):
        raise ValueError("Identity email is malformed")
    return ProviderIdentity(subject=subject, email=email)


def verify_provider_identity(
    provider: str,
    id_token: str,
    jwks: dict[str, Any],
    *,
    client_id: str,
    nonce: str,
    access_token: str,
) -> ProviderIdentity:
    """Validate signature, claims and the access token hash before accepting an account."""
    try:
        header = jwt.get_unverified_header(id_token)
        unverified = jwt.get_unverified_claims(id_token)
        issuer = _expected_issuer(provider, unverified)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str):
            raise ValueError("Unsupported identity token algorithm")
        key = _matching_key(provider, jwks, kid, issuer, unverified.get("tid"))
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            access_token=access_token,
        )
        authorized_party = claims.get("azp")
        audiences = claims.get("aud")
        if authorized_party is not None and authorized_party != client_id:
            raise ValueError("Identity token belongs to another OAuth client")
        if isinstance(audiences, list) and len(audiences) > 1 and authorized_party != client_id:
            raise ValueError("Identity token has no authorized party for this client")
        if claims.get("nonce") != nonce:
            raise ValueError("Identity token nonce mismatch")
        return _account_from_claims(provider, claims)
    except (JWTError, KeyError, TypeError) as error:
        raise ValueError("Invalid provider identity token") from error
