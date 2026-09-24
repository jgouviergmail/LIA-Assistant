# ADR-307 — A connector that asks nothing of the person belongs to the instance

**Status**: accepted — 2026-09-23
**Amends**: ADR-126 (account provisioning — the keyless step is gone), ADR-134 (the « Reconnect » banner), ADR-184 (what the settings offer is what the API accepts), and the 2026-09-12 sign-up provisioning recorded in `docs/technical/CONNECTORS_PATTERNS.md`

## Context

Five connectors need no OAuth consent and no personal key: **Wikipedia**, **page
browsing**, **Google Places**, **Google Weather** and **Google Environment** (the
platform `GOOGLE_API_KEY`, or no key at all). Since 2026-09-12 every new account received
them as `ACTIVE` rows at sign-up, and « My connectors » listed them with a switch.

Owner decision, 2026-09-23: a connector that needs no key and no configuration has no
business in « My connectors », nobody should be able to switch it off, and the accounts
that did switch one off in production must have it back.

What the code showed before anything was decided:

| Fact | Consequence of merely hiding the screen |
|---|---|
| Only Places, Google Weather and Google Environment were gated by a row (`ConnectorService.is_connector_active`, the weather category resolver). Wikipedia and the browser never read theirs. | Their settings switch had never done anything. |
| Accounts created before 2026-09-12 never received the rows, and nothing backfilled them. | They could never get them back. |
| An administrator disabling a type sets every row `REVOKED`; re-enabling it restores nothing. | The rows would stay revoked for good. |
| `DELETE` and `PATCH /connectors/{id}` accept any type; the demonstrator refuses every activation path. | A row removed through the API, or by a demonstrator visitor, has no way back. |
| The « weather » category holds OpenWeatherMap (personal key) and Google Weather. Adding OpenWeatherMap left BOTH active, and the resolver's « should not happen » fallback picked the most recently updated row. | Reactivating Google Weather in bulk would have silently taken the weather away from every person who chose OpenWeatherMap. |
| `connector_type` and `status` store the enum NAMES (`native_enum=False`, measured on the dev database). | A data migration written with the lower-case values matches nothing. |

## Decision

1. **The instance decides, in one place.** `connectors/keyless.py` answers whether a
   keyless type serves the instance — the administrator's global switch, the platform key
   for a platform-key type, `BROWSER_ENABLED` for the browser — and
   `ConnectorService.is_connector_active` returns that answer for every keyless type
   without reading the account's rows.
2. **No per-account row exists.** Migration `b2e6d0f4a8c1` deletes every row of the five
   types, whatever its status: the accounts that had switched one off, never received one
   or kept a revoked one are all served again, with no reconciliation job. The sign-up step
   (`users/keyless_connectors_provisioning.py`), `POST /connectors/google-places/activate`
   and `activate_places_connector` are deleted, and `APIKeyActivationRequest` refuses a
   keyless type, which closes activation and rotation alike.
3. **In the weather category, the person's choice wins.** The resolver reads the rows of
   the providers a person configures; when none is active it answers with the category's
   keyless member the instance provides — Google Weather is the DEFAULT, never a rival
   (`provider_resolver._instance_default`). A leftover keyless row is never read, so it can
   neither outrank OpenWeatherMap nor switch the default on.
4. **The settings neither list nor mention them** (owner decision: no explanatory line).
   `API_KEY_CONNECTOR_TYPES` and `API_KEY_CONNECTORS` hold only the connectors that take the
   person's key, the onboarding no longer asks to activate the other three, and
   `test_keyless_connectors_not_offered_by_frontend.py` refuses a keyless type in either
   frontend list — it replaces the parity test that pinned the opposite.
5. **A refusal says who can act.** A keyless service the instance withholds returns
   `CONFIGURATION_ERROR` with « not available on this instance; only its administrator can
   make it available » (`APIMessages.connector_unavailable_on_instance`), never « go to
   Settings > Connectors »; and a 401/403 from a keyless service raises no « Reconnect »
   banner, because the key that failed is the operator's.
6. **The heartbeat's weather probe reads the category**, not OpenWeatherMap alone — it
   reported the weather source « not connected » on every account the default served.

## Consequences

- « Always active » is true by construction, now and later: a type the administrator
  re-enables, or a platform key configured after the fact, serves every account at once.
- An administrator disabling a keyless type no longer emails each account: there is no
  row to revoke (accepted by the owner, 2026-09-23).
- The counts that read connector rows stop counting five rows nobody chose: the
  capability map's connectors node, the starter checklist's « connect a service » item
  (which the sign-up rows ticked on their own), the admin users list and the Prometheus
  gauge of active connectors by type.
- The downgrade re-creates one `ACTIVE` row per keyless type and live account, except for
  a type the administrator disabled. It cannot read the instance's `GOOGLE_API_KEY` or
  `BROWSER_ENABLED`, so it may re-create a row the previous sign-up step would have
  skipped; the previous settings screen lets the person switch it off.

## Rejected alternative

Keeping one row per account and repairing it: a backfill at boot, a second one when an
administrator re-enables a type, `DELETE`/`PATCH` locked for the five types, a precedence
rule in the weather resolver, and an exclusion in every count that reads rows. Five repairs,
each one a place for the rows and the intent to drift apart, where one predicate over the
instance has nothing to drift from.
