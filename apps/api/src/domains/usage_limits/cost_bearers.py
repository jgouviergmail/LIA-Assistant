"""Whose key pays, and therefore whose quota may be charged.

The owner's rule: *« on ne compte pas les coûts des outils ou connecteurs avec
une clé de l'utilisateur »*. The code already obeyed it exactly when this
module was written (2026-09-07) — but nothing said so, and nothing enforced it.
The frontier held because several authors happened to have the same reflex,
which is not a guarantee: the audit that produced this file read it backwards
twice within ten minutes.

Verified in both directions before declaring anything:

- ``provider_api_keys`` has **no** ``user_id`` column, so every model call,
  image, speech and Maps request runs on the deployment's key;
- ``get_api_key_credentials(user_id, connector_type)`` is per-account, and
  ``ConnectorType`` itself records the distinction — the Maps family is
  annotated « global key, not per-user », telephony « per-user ElevenLabs
  account ».

Two opposite failures, equally bad, which is why the guard checks both
directions:

- an instance-paid family missing from the ceiling's sum: the self-hoster funds
  a spend no bound can see;
- a user-paid family present in it: the account is charged, against its own
  quota, for euros it already paid its own provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CostBearer(str, Enum):
    """Who actually pays the provider for a family of calls."""

    #: The deployment's own credential. Chargeable to the account that benefited.
    INSTANCE = "instance"
    #: The account holder's own credential, held in their connectors. Never
    #: chargeable: they already paid their provider directly.
    USER = "user"


@dataclass(frozen=True, slots=True)
class CostFamily:
    """One billable family, and the evidence for who bears it.

    Attributes:
        bearer: Whose credential the provider bills.
        reason: Why, in one sentence — the argument, not the conclusion.
        credential: For a user-borne family, the credential that proves it.
            ``None`` on the instance side, where the deployment's key is the
            only one there is.
    """

    bearer: CostBearer
    reason: str
    credential: str | None = None


#: Every family of external spend LIA can incur, and who pays for it.
COST_FAMILIES: dict[str, CostFamily] = {
    # --- The deployment's own credential ------------------------------------
    "llm": CostFamily(
        bearer=CostBearer.INSTANCE,
        reason=(
            "Model calls run on the keys in `provider_api_keys`, a table with "
            "no user_id: one credential per provider for the whole instance."
        ),
    ),
    "tts": CostFamily(
        bearer=CostBearer.INSTANCE,
        reason=(
            "Paid speech synthesis uses the deployment's provider key; the "
            "free local engine records nothing at all."
        ),
    ),
    "stt": CostFamily(
        bearer=CostBearer.INSTANCE,
        reason=(
            "Remote transcription uses the deployment's provider key. A local "
            "transcription costs nothing and writes no ledger entry."
        ),
    ),
    "google_maps_platform": CostFamily(
        bearer=CostBearer.INSTANCE,
        reason=(
            "Places, Routes and Geocoding are billed to `google_places_api_key`, "
            "a deployment setting — `ConnectorType` annotates this family "
            "'global key, not per-user'. Gmail, Calendar and Drive are NOT here: "
            "they run under the person's own OAuth token and cost nothing."
        ),
    ),
    "image_generation": CostFamily(
        bearer=CostBearer.INSTANCE,
        reason="Image generation runs on the deployment's provider key.",
    ),
    # --- The account holder's own credential --------------------------------
    "perplexity": CostFamily(
        bearer=CostBearer.USER,
        reason=(
            "An account-scoped connector: the person enters their own key and "
            "is billed by Perplexity directly. Counting it again here would "
            "charge them twice for one search."
        ),
        credential="ConnectorType.PERPLEXITY",
    ),
    "brave_search": CostFamily(
        bearer=CostBearer.USER,
        reason="Account-scoped connector key, same argument as Perplexity.",
        credential="ConnectorType.BRAVE_SEARCH",
    ),
    "openweathermap": CostFamily(
        bearer=CostBearer.USER,
        reason="Account-scoped connector key, same argument as Perplexity.",
        credential="ConnectorType.OPENWEATHERMAP",
    ),
    "elevenlabs_telephony": CostFamily(
        bearer=CostBearer.USER,
        reason=(
            "Outbound calls run on the person's own ElevenLabs account, as "
            "`ConnectorType` records. The LLM that writes what to say is a "
            "separate family and IS instance-borne."
        ),
        credential="ConnectorType.ELEVENLABS_TELEPHONY",
    ),
    "google_workspace": CostFamily(
        bearer=CostBearer.USER,
        reason=(
            "Gmail, Calendar, Drive, Contacts and Tasks are read under the "
            "person's own OAuth token and are not billed at all. Declared "
            "rather than omitted so that 'free' is a recorded decision instead "
            "of a family nobody classified."
        ),
        credential="OAuth token held by the account's connector",
    ),
}

#: The ``user_statistics`` column each family lands in, or ``None`` when the
#: family has no counter at all. ``llm``, ``tts`` and ``stt`` share one column:
#: they are merged upstream before the ceiling reads them, which is why the
#: mapping is many-to-one rather than a column per family.
QUOTA_COLUMN_OF: dict[str, str | None] = {
    "llm": "cycle_cost_eur",
    "tts": "cycle_cost_eur",
    "stt": "cycle_cost_eur",
    "google_maps_platform": "cycle_google_api_cost_eur",
    "image_generation": "cycle_image_generation_cost_eur",
    "perplexity": None,
    "brave_search": None,
    "openweathermap": None,
    "elevenlabs_telephony": None,
    "google_workspace": None,
}


__all__ = ["COST_FAMILIES", "QUOTA_COLUMN_OF", "CostBearer", "CostFamily"]
