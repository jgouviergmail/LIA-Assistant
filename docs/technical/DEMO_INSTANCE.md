# Demo Instance — the free public demonstrator

> **Status:** runs end to end in development, audited by simulation, not yet
> deployed. Registration, verification email, streamed conversation, web
> search, speech synthesis, spend ceiling and nightly purge were all exercised
> against the real instance. A simulation-based security audit conducted on
> 2026-08-07 — every finding obtained by running something, never by reading
> code — found eight defects, five of them invisible to the green test suite;
> the corrections are in and remeasured, and the guards that recalculate them
> are described in [ADR-218](../architecture/ADR-218-Surface-Verifiee-Du-Demonstrateur.md).
> Two arbitrations remain: dedicated provider keys, and which machine hosts it.

The demonstrator is the **standard LIA image** running in an isolated Compose
envelope, not a stripped-down copy of the product. A visitor gets the real
assistant — free input, real agents — and the limits sit around it rather than
inside it. That was the owner's arbitration: what a stranger tries must be
what LIA actually does.

Everything below is a protection with a test that recalculates it; see
[ADR-218](../architecture/ADR-218-Surface-Verifiee-Du-Demonstrateur.md) for
why "recalculates" is the load-bearing word.

## What protects what

| Risk | Protection | Where |
|---|---|---|
| Unbounded spend | Daily ceiling on the whole instance, smallest of env and admin bound, fail-closed | [ADR-216](../architecture/ADR-216-Plafond-De-Depense-D-Instance.md), `usage_limits/instance_budget.py` |
| A ceiling that cannot SEE the spend | Provisioning refuses a model this database cannot price; `--verify` re-asks a running instance | `provisioning/demo_llm.py::unbillable_model` |
| Mass registration burning the mail quota | Instance-wide daily signup ceiling, counted from the accounts, plus relay-side rate limits | `auth/demo_signup_ceiling.py`, `docker-compose.demo-instance.yml` |
| A container pivoting to the LAN or the host | Every network internal except three single-member outbound ones; the edge reaches nothing but its two neighbours | `docker-compose.demo-instance.yml`, `tests/unit/test_demo_instance_envelope.py` |
| A capability offered that cannot work | Flags, egress allowlist and provider keys checked against each other | `tests/unit/test_demo_instance_capability_coherence.py` |
| A capability costing more than intended | 10 administrable capabilities, two composed bounds, three declared enforcement modes | [ADR-217](../architecture/ADR-217-Capacites-Administrables.md), `domains/feature_switches/` |
| A stranger's real account tied to a throwaway one | Connector linking AND federated sign-in refused, at the edge and in the app | `core/demo_mode.py` |
| A route reachable that nobody decided to expose | Edge allowlist + frozen census of the 53 reachable routes | `infrastructure/demo-instance/Caddyfile`, `tests/unit/test_demo_instance_exposed_routes.py` |
| Data surviving the night | Full nightly purge, guarded by a marker **in the database** | `infrastructure/scheduler/demo_account_purge.py` |
| A visitor not knowing any of this | Terms section 12 in all 6 languages, limits stated before the link | `apps/web/src/data/guides/terms.*.md`, `LiveDemoInvitation.tsx` |

## Getting in

One door: an email address and an explicit acceptance of the terms. The
verification email activates the account.

Federated sign-in (Google today, any provider tomorrow) is closed in three
layers, because closing it in one is how it comes back:

1. the edge refuses `^/api/v1/auth/[^/]+/(login|callback)/?$` **before** the
   allowlist opens `/auth/*` — order is load-bearing;
2. `forbid_federated_signin_in_demo` is a dependency of the auth router;
3. `/auth/features` publishes `federated_signin_enabled: false`, so the
   interface draws no button it would refuse.

The reason is not symmetry: the terms are enforced on the registration path,
and a provider sign-in creates the account without ever passing through it.

## The nightly purge

Runs at the configured hour, deletes every visitor account through
`AccountDeletionService` and then the `users` row itself — otherwise the
address stays taken and the visitor cannot come back tomorrow.

It requires **both** `DEMO_MODE_ENABLED` and a marker stored in the database,
read without cache. The flag alone never authorizes deleting accounts, and a
permanent test says so. That safeguard exists because a proof script once
forced the flag against the development database and destroyed real accounts.

## The public link

The URL is a deployment fact (`DEMO_INSTANCE_PUBLIC_URL`); the switch is an
operator fact, stored in the audited settings store and flipped from the
administration. When it is off, the URL is not served at all — hiding a link
whose address still answers only hides it from people who do not look.

## Operating it

```bash
# Local validation
task dev:all         # restart the application stack AND the demonstrator, then check both
task stop:all        # stop both
task demo:start      # the demonstrator alone: build, start, provision the marker
task demo:verify     # spend ceiling + host isolation + closed surface, all measured
task demo:status     # containers + what the instance reports
task demo:logs       # follow the API (CLI_ARGS picks another service)
task demo:down       # stop; the tmpfs database dies with it, by design

# Production, from a workstation. `task deploy:prod` SHIPS the demonstrator and
# does not start it: putting an instance in front of the Internet is a
# decision, not a side effect of a deployment.
task demo:prod:status
task demo:prod:up      # start WITH the tunnel — it becomes public (prompts)
task demo:prod:verify  # the same three protections, measured on the host
task demo:prod:harden  # (re)install the container->host firewall rules
task demo:prod:down
```

The host, port and user of those remote tasks come from
`scripts/deploy/deploy.local.ps1` — the same gitignored file the deploy driver
reads, so the address lives in one place and never in the repository.

A local validation reaches the edge at **http://localhost:8090** and the
administration at **http://localhost:8100** — both loopback-only, both from
`docker-compose.demo-instance.dev.yml` and both overridable
(`DEMO_INSTANCE_EDGE_PORT`, `DEMO_INSTANCE_API_PORT`) because a developer
machine is a crowded place — keep the edge port and `APP_URL_SERVER` in step. The production envelope publishes **no
host port at all**: the tunnel reaches the edge over the private network, so
the instance is reachable through Cloudflare or not at all.

The edge speaks plain HTTP on purpose. Public TLS is Cloudflare's job, and the
earlier `:443 { tls internal }` served nothing: with no site name Caddy has no
subject to issue a certificate for and refuses every handshake — measured, the
instance would have been unreachable.

`task demo:provision` writes the marker on a FRESH database and refuses a
populated one, exiting non-zero so a deploy script cannot mistake a refusal
for a success.

The instance holds ONE shared Brave key and lends it to each visitor account
at creation (`users/demo_search_provisioning.py`): Brave is a per-user
connector, so without that a visitor would meet a permanently broken search.
Perplexity is deliberately absent — it bills per call.

## The money, and how to know it is armed

The daily ceiling reads a ledger the pricing catalogue feeds. A model with no
ACTIVE per-1M-token price is billed by the provider and recorded at **zero**,
so the ceiling never fires. That is not hypothetical: on 2026-08-07 the
instance burned 59 344 real tokens and its ledger read 0,000025 EUR, because
every LLM type pointed at a model this database does not carry. One euro of
ledger would have been roughly four hundred euros of invoice.

Two things follow, and both are enforced rather than documented:

- `task demo:provision` **refuses** an instance whose `DEMO_INSTANCE_LLM_MODEL`
  has no active price, instead of arming a blind ceiling;
- `task demo:verify` asks a RUNNING instance the same question, and says so:

```
$ task demo:verify
Spend ceiling armed: the configured model is priced by this catalogue.
  404  /api/v1/connectors/gmail/authorize
  ...
surface OK
```

The catalogue comes from the **reference seed bundle**, applied at every boot
(the database is in tmpfs, so it is empty each time). That bundle is the
maintained source of truth; the migrations carry an older, partial copy — 91
prices against 224.

Getting it applied uncovered a defect that reached far beyond this instance:
the bundle could not be applied by **any** installation. The entrypoint vetoed
on "is the personalities table empty?", while the migrations insert fourteen
rows unconditionally just above it, so the answer was never yes. The veto now
asks what its own comment always claimed it asked — has anyone *chosen* a
personality? — and the seed files, which the API image does not carry, are
mounted read-only exactly as dev and prod already mount them.

## Networks — who can reach what

Every network is `internal` except three, each with exactly **one** member:

```
ingress (internal)   edge + tunnel
app     (internal)   edge, api, web, egress proxy
mail    (internal)   api + relay          <- nobody else may ask for mail
data    (internal)   api + postgres + redis
observability        api + collector + prometheus

egress-outbound      egress proxy   only
mail-outbound        mail relay     only
tunnel-outbound      cloudflared    only
```

The api and the web sit on no routed network at all: their only ways out are
the proxy's allowlist and the relay's smarthost. The **edge** — the container
that terminates every visitor request — reaches nothing but its two
neighbours; it does not even resolve a public name. It used to reach the local
network, the production host's SSH and the development stack on the same
machine, which inverted the whole intent.

### The one gap Compose cannot close, and what closes it

Docker's `internal` blocks routing outward, **not** the bridge gateway — and
that gateway is the host itself. A container on an internal network still
reaches anything the host listens for on `0.0.0.0`; measured 2026-08-07 with
disposable containers, a listener on `0.0.0.0` in the host namespace answered a
container whose only network was created with `--internal`, while the same
container reached neither `1.1.1.1` nor the local network. On the production
Raspberry that means sshd, and from there the production stack. The
countermeasure is `scripts/deploy/harden-demo-host.sh`: idempotent iptables
rules in `INPUT` and `DOCKER-USER`, over subnets **discovered** from Docker
rather than typed, run on every deployment (`deploy:prod`, step 9bis) and
re-runnable on demand (`task demo:prod:harden`). Rules in the built-in chains
are flushed when the daemon restarts; `DOCKER-USER` is the chain Docker
guarantees it will not touch.

Those two hooks carry **two different rules**, and merging them is how the
first version of the script left the host open. It used one chain for both,
opening with "the demonstrator's own subnets are allowed" — indispensable
between containers, since the API, squid, postfix and the tunnel are peers.
But a bridge gateway *belongs to the subnet it serves*, so on the `INPUT` path
that permission also covered the host, and it came first. The Raspberry
answered accordingly on 2026-08-07: `HOST REACHABLE ... 172.24.0.1:2222 (ssh)`,
four gateways, sshd on each. So `INPUT` now jumps to `LIA-DEMO-HOSTGUARD`,
which drops everything the demonstrator addresses to this machine — its own
gateways included, keeping only replies to connections the host itself opened —
while `DOCKER-USER` keeps `LIA-DEMO-ISOLATION` and its peer permission for
forwarded traffic. Upgrading a host also **deletes** the previous version's
`INPUT` jump: rebuilding a chain does not remove a jump to it, and leaving it
would keep the offending permission one insert away from applying again.

Two operational notes earned the same way. `iptables-nft -C` is not a reliable
way to ask whether a rule exists: it denied two of three DROP rules that `-S`
printed verbatim in the same shell, so `--check` reads the printed ruleset
instead — a check that cries wolf gets ignored, and then the real alarm is
ignored too. And `iptables` lives in `/usr/sbin`, which is *not* on the PATH an
ssh command receives, so the script resolves it by absolute path and escalates
with `sudo -n` (no terminal on the other end means a password prompt would hang
until timeout). And because a protection nobody measures is a
protection nobody has, `task demo:verify` opens real connections from inside
the API container to every host address on its routes and **fails if one
answers** — proven in both directions: silent host → `host isolation OK`, host
listening on `0.0.0.0:2375` → `HOST REACHABLE`, exit 1.

Two caveats an operator must hold: the rules do not survive a host reboot
unless the distribution persists iptables — re-run the deployment, or
`task demo:prod:harden` — and they can only be installed once the
demonstrator's networks exist, so a deployment that ships the instance without
starting it reports a warning rather than a failure. The application path is
independently closed: the SSRF validator refuses the gateway address
explicitly, so this is the residual "arbitrary code execution inside the
container" path, not the first line.

## Capabilities: on means reachable

Three declarations have to agree — the capability flag, the egress allowlist,
and the provider key — and nobody edits them together. On 2026-08-07 dictation
and speech were advertised ON while the proxy answered `403` to both of their
hosts: the microphone button was there and did nothing.

`tests/unit/test_demo_instance_capability_coherence.py` now recalculates the
requirement from the flags. Switching a capability on without opening its host
fails there; so does leaving a host open that no enabled capability needs.

Today: speech synthesis works (Edge, free, no key — the client passes the
egress proxy to its WebSocket, which aiohttp does not discover on its own);
dictation is off because it needs an ElevenLabs key.

## Incidents — the four questions worth asking

```bash
# 1. Is the money protection armed?
docker compose --env-file .env.demo-instance -f docker-compose.demo-instance.yml \
  exec -T -w /app demo-instance-api python -m src.infrastructure.provisioning.cli --verify

# 2. Is the closed surface still closed?
task demo:verify

# 3. What has the instance spent today, and how many visitors did it enrol?
docker compose --env-file .env.demo-instance -f docker-compose.demo-instance.yml \
  exec -T demo-instance-postgres psql -U demo -d lia_demo -c \
  "SELECT utc_day, spent_cost_eur, run_count FROM instance_daily_budget ORDER BY utc_day DESC LIMIT 3;
   SELECT count(*) FROM users;"

# 4. Did the nightly purge run?
task demo:logs | grep demo_account_purge
```

Recreating the postgres container drops the tmpfs database: the marker, the
settings and the LLM configuration go with it. The LLM configuration returns
on its own at boot; the marker needs `task demo:provision` (or
`:force` when accounts already exist), and **without it the nightly purge
never runs** — which is the one promise the terms make.

## Before it can run

- provider keys in `.env.demo-instance.prod` (never in git) — prefer keys
  **dedicated** to this instance with a provider-side cap: the daily ceiling is
  LIA's accounting, not the provider's, and today the Gemini key is shared with
  production;
- the Cloudflare tunnel token for the public hostname;
- a first bring-up on a disposable host, then the public-link switch.

## Changing it

Seven guards will stop a change that widens the surface, or narrows it into
uselessness, without a decision:

- a new `*_cost_eur` field must be counted or excluded **with a reason**;
- a new route under an allowed prefix must be added to
  `EXPECTED_EXPOSED_ROUTES` after review;
- a new connector route must be a linking path (refused) or classified in
  `READ_ONLY_ROUTES` with why it may stay open;
- a new container with a route to the Internet must be declared in
  `OUTBOUND_SERVICES`, and it may not share that route with another;
- a host port in the production envelope fails outright — two protections
  depend on the tunnel being the only way in;
- a capability switched on without its egress host fails, and a host opened
  without a capability that needs it fails too;
- a variable the Compose files interpolate must exist in the env template, and
  a variable in the template must be one the code reads.

None of them is a formality: each one found a real hole the day it was
written, and the last four were written the day the audit measured the holes
the first three could not see.
