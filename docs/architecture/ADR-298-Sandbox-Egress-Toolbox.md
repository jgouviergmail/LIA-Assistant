# ADR-298 — The sandbox reaches the network through one proxy, with tokens it cannot read and a question it cannot skip

**Date**: 2026-09-18
**Status**: Accepted
**Amends**: ADR-249 (ephemeral Python: the sandbox had no network), ADR-263 (the effect register: a `sandboxed` policy was pass-through), ADR-280 (one switch per capability), ADR-284 (a prompt states what the code enforces), ADR-288 (one draft at a time), ADR-149 / SEC-001 (the container sandbox's isolation flags), ADR-184 (a bound is published), ADR-185 (a count is exact)

## Context

ADR-249 gave the ReAct loop a way to write and run a short Python script, and
deliberately gave that script **no network** (`--network none`). The owner asked
for the opposite direction, measured first: a script that can reach a service
lets the assistant **diagnose** a tool failure (is the third party down, is the
key refused, is the fault ours — with a status code and a latency), **fill a
gap** by writing a temporary client where no tool exists and correcting its own
code from the traceback, and **transform** payloads a model reads badly. On dev
the tool did not even run: `SKILLS_SCRIPT_SANDBOX_IMAGE` named a tag that no
longer existed, so every run failed before the container started (fixed by
pinning `lia-api-dev:latest` in `docker-compose.dev.yml`, guarded by the
compose contract test).

Three constraints came from the code, not from preference. A network run with
the turn's data on stdin **is an exfiltration channel**, so what travels must
be decided by the person, not by the model. The person's API keys
(`get_api_key_credentials`, per account) are the only credentials that may
serve a script — never an OAuth token, never an instance key — and they must
**never enter the container**. And the `sandboxed` mutation policy is
pass-through in the effect gate: a network act would have left no row in the
register (ADR-263).

Hermes Agent's own hardening was read before designing (opaque tokens swapped
by a proxy, an allowlist, private-address refusal at connect time) and one of
its shapes rejected: interception through environment variables on a routed
network, which a raw socket walks around.

## Decision

- **One door: iron-proxy 0.49.0 as a sibling container, the only routed member
  of an `internal` Docker network** (`lia-sandbox`). The sandbox joins that
  network alone (`docker run --network lia-sandbox`): a raw socket, a DNS
  query of its own, an undeclared host, a private address — each refused by
  the topology or by the proxy (403), never by an environment variable the
  script could unset. The proxy is hardened like the sandbox (read-only,
  `cap_drop: ALL`, no new privileges, memory and pid caps), pinned by digest,
  and its **state is minted by its own entrypoint** into three tmpfs volumes
  (CA, key, config) owned by `LIA_RUNTIME_UID`: an init container was written
  first and measured wrong — Docker released the tmpfs when the init exited,
  and the proxy started empty. The CA is x509 v3 with `keyCertSign` (the proxy
  refused a plain self-signed one). The API mounts the config volume only;
  the key never leaves the proxy, the CA reaches the sandbox read-only.
- **A run declares its hosts, and every host has ONE of four statuses**
  (`egress/hosts.py`): `connector` (a host of the person's active API-key
  connectors, derived from the client classes — `derive_connector_hosts`, so
  the proxy's rule and the client's real call cannot disagree on the header),
  `operator` (`PYTHON_SANDBOX_EGRESS_HOSTS`), `grant` (what the person allowed
  before), `unknown`. Hostnames are validated to the exact ASCII form the proxy
  matches, bounded by `PYTHON_SANDBOX_MAX_HOSTS_PER_RUN`, and the bound is
  published on the manifest (ADR-184).
- **A credential is a per-run token the script reads from the environment and
  the proxy swaps** (`LIA_KEY_<CONNECTOR>` → `sbx_…`, `secrets` transform,
  match on the host AND the carrier the client class declares — header or
  query). The real key is written to a `0600` file the proxy reads; the
  ruleset is rendered from a **Redis registry of live runs** (four workers;
  claimed with an owner token, compare-and-delete release — `redis_claim.py`,
  extracted from `shared_flight`) and pushed through the management API;
  publishing fails CLOSED (a run whose ruleset the proxy did not accept never
  starts). Measured on dev (`task sandbox:egress:probe`, 11/11): a raw
  connection has nowhere to go, an undeclared host gets 403, a header AND a
  query token are swapped upstream while the sandbox never saw the key, and a
  withdrawn run's token is refused.
- **An unknown host is ASKED, never refused in silence, with three answers**:
  the tool hands the call back as a `SANDBOX_EGRESS` draft — the CARD the
  draft-critique interaction already draws — naming the hosts, the model's
  stated purpose and a COUNT of the turn's data (never the data), and the
  person allows **with the data**, **without the data** (stdin then carries
  no items — `confirm_without_data`, the third action the web normaliser used
  to discard) or refuses. The answer is remembered as a grant
  (`sandbox_egress_grants`, unique per account and host, `share_turn_data`,
  `last_used_at`); past `PYTHON_SANDBOX_MAX_GRANTS_PER_USER` an approval holds
  for its run alone and says so (`one_shot`). The data scope of a run is the
  MINIMUM over its hosts.
- **A permission is settled IN the loop, never dispatched as an action**
  (`nodes/react_egress_question.py`). The first delivery handed the draft to
  the dispatch every mutation draft takes, and it was measured wrong on
  2026-09-18: the dispatch EXECUTES a draft and answers from its result — it
  never resumes the loop — so « count the attachments of my last mails, and
  check httpbin.org » ended on the httpbin result alone. The node now raises
  the interrupt itself, exactly like a mutation tool's pre-execution
  confirmation (same payload shape, same card, same three buttons); on resume
  the node re-runs, the grant is recorded, and the SAME call is re-invoked
  with the answer bound to that one invocation (`tool_path.approved_for_call`,
  a context the node opens and closes) under a scope derived as approved by
  the card — then the model goes on. Two facts the measurement forced: a
  question costs none of the turn's runs (a container is charged, a card is
  not), and the script never leaves the loop — no replay in the draft, nothing
  on the wire (the first delivery carried the script AND the items to the
  browser under `replay`). And `interrupt()` is a bubble-up raised from INSIDE
  the call: the node's « any tool error becomes a message » net swallowed it
  once (the person read « the measurement is suspended »), so it is re-raised
  ahead of that net. Measured after: the question asked, answered with the
  data, the call re-invoked, the model correcting its own `Accept` header on
  a 415 and answering BOTH halves in four iterations.
- **A network run is an action: claimed before the container starts, closed
  from the result** (`effects/in_turn_effects.py`, the in-turn sibling of the
  out-of-turn seam), under the capability name `python_sandbox_network` with
  the hosts and the data scope on its label; under an approved draft it
  carries the approval (`draft_critique`, the card id). A run without hosts
  stays what ADR-249 made it: pass-through.
- **The switch is its own capability** (`PYTHON_SANDBOX_EGRESS`, service
  enforced, read AT THE ACT and again at the prompt), off by default, and
  the deployment ceiling `PYTHON_SANDBOX_EGRESS_ENABLED` gates the settings
  section through `/config`. The four demonstrator env files keep it off.
- **The prompt is the living contract, measured before it was trusted.** The
  manifest and `<Computation>` state four jobs (calculate, diagnose, fill a
  gap, transform), the libraries a script may import from ONE table
  (`python_sandbox/libraries.py`, 22 names, every distribution pinned
  DIRECTLY in `requirements.txt` — six were transitive — and imported by the
  CI on the lockfile and by `task sandbox:libraries:check` inside the built
  image, offline), every bound from the setting that enforces it, and — only
  under an offer read from the ACCOUNT at turn start (`network_available`,
  the active connectors plus the operator's list, ONE derivation shared with
  the settings page) — the reachable hosts with their token variable and
  carrier, and the rule for any other host. On the first real turn the model
  sent the variable's NAME as the header value (422 from Brave, twice, no
  self-correction): the line now spells the read, `os.environ["LIA_KEY_…"]`,
  and the next turn reached Brave with the swapped key (200, one run). The
  block costs 439 tokens without network and 692 with four hosts (o200k,
  measured), against about 140 before — each sentence states a role or an
  enforced rule.
- **The person sees and edits what they allowed** (`/settings?section=
  sandbox-egress`): the reachable hosts with their origin, every grant with
  its scope switch and a revoke, the exact total against the published cap,
  a cut stated when a page cannot hold them all. Three e2e journeys, 320 px
  included.
- **Observability**: `python_sandbox_egress_runs_total{outcome}`,
  `python_sandbox_egress_grants_total{decision}`, the gauge
  `python_sandbox_egress_enabled`; the proxy exposes no Prometheus series in
  0.49 (measured: 404), so the alert `SandboxEgressProxyDown` reads a
  blackbox probe of `/healthz`; a runbook and an evidence recipe. The two
  counters are drawn as COUNTS — runs per interval, answers over the range —
  because a `rate()` of a few human decisions a day reads as an empty panel
  (reported 2026-09-18 with two answers in Prometheus and nothing on screen).

## Consequences

- `react_scripts` — the admin-visible list of a turn's scripts — was appended
  to for the life of the thread (the thread is the conversation) and never
  reset: the debug panel of one turn showed the scripts of every earlier one.
  It joined `react_turn_reset()`, the one declaration (measured 2026-09-18).
- `PYTHON_SANDBOX_MAX_RUNS_PER_TURN` moves from 3 to 5: an attempt, three
  corrections, a verification.
- Every `python_sandbox_egress_*` value is published in `.env.example`,
  `.env.prod.example` and the demonstrator's four files; `.env.min.prod.example`
  carries nothing (off by default, nothing required).
- Residuals, stated rather than hidden: « without the data » bounds what the
  code reads in bulk, not what the model retypes from its context (source
  ≤ 256 KB); exfiltration to an ALLOWED host is logged by the proxy, not
  prevented — the residual of any ordinary Brave call; a run token survives a
  crash for at most the registry TTL, worthless outside the sandbox network
  and its (host, carrier) pair; the management (256-bit bearer) and health
  listeners are visible from the sandbox network; two sandboxes share
  `lia-sandbox` and neither listens; the proxy sees the clear text (it is our
  container, `path` is logged, query and bodies are not); the third party's
  quota is the person's own key, never counted (directive 2026-09-16);
  `require: False` on the secret rule so a run without a key still reaches
  its host without a credential.
- **The allowlist is the UNION of the live runs** (iron-proxy 0.49 has one
  allowlist, not one per client): while two runs overlap, each sandbox may
  CONNECT to the other's hosts — never with the other's token, which is
  bound to its own (host, carrier) pair. What widens for those seconds is the
  set of hosts a script could send data to, already an allowed-host residual
  above; a per-run allowlist needs a proxy feature the version does not have.
- **The deny list is the guard for a permitted NAME resolving inward**
  (rebinding, an operator entry pointing at a service): loopback and
  ``0.0.0.0/8`` (routed to loopback by Linux), link-local, RFC 1918, CGNAT,
  the benchmark range, IPv6 loopback/unspecified/link-local/ULA, the
  IPv4-mapped and the NAT64 prefixes — a test holds the list against every
  family (measured 2026-09-18 from the sandbox network: the management API
  answers 401 to every endpoint without the bearer, and `CONNECT 0.0.0.0`
  is refused).

## Rejected

- **Environment-variable interception** (`HTTPS_PROXY` on a routed network):
  a `socket.connect` ignores it. The topology is the guard, the variables are
  a convenience for `requests`, `httpx` and `urllib`.
- **OAuth tokens or the instance's keys for a script**: a script the model
  wrote after reading an e-mail runs with the narrowest credential that
  exists, the person's own per-account key, or none.
- **A declared allowlist typed by hand**: hosts are DERIVED from the client
  classes and the operator's list, and grown by the person's answers.
- **A silent refusal of an unknown host**: refusing teaches the model to stop
  declaring hosts; asking makes the person the authority and remembers it.
- **The init container for the proxy's state**: measured wrong (see above).
- **Proxy metrics from iron-proxy**: none in 0.49; a blackbox probe instead.
