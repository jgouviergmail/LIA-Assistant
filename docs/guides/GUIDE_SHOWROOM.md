# Guide: The public showroom — explain, build, configure, deploy, operate

> **Audience:** anyone who maintains, configures, ships, or measures the
> public `/demo` experience.
> **Scope:** what the showroom is and is not, how it is built, every setting,
> how a release enables it, and how to run it day to day.
>
> The launch-day campaign checklist (positioning, assets, publication order,
> rollback) lives in `docs/marketing/PUBLIC_SHOWROOM_LAUNCH_PLAYBOOK.md` and
> is not repeated here.

---

## 1. What the showroom is

`/demo` answers one question for a visitor who has no account: **what does
this thing actually do?**

The guided showroom is a set of **deterministic, client-only storyboards** —
one mission per differentiating mechanism — played over the **real** approval,
trace and rich-reply components of the product. The visitor picks a mission,
watches LIA read its sources, then **approves, edits, or refuses each
proposal** through the same UI a logged-in user sees, and finally reads LIA's
reply rendered by the production rich-HTML pipeline.

### The six missions

| Mission id           | Title (en)                        | Differentiator shown              | Decisions |
| -------------------- | --------------------------------- | --------------------------------- | --------- |
| `overloaded_morning` | An overloaded morning             | Orchestration + approvals         | 2         |
| `proactive_alert`    | LIA gets there first              | Proactivity (LIA initiates)       | 2         |
| `memory_dinner`      | It remembers for you              | Persistent memory + habits        | 2         |
| `phone_booking`      | It makes the call                 | Outbound calls, HITL-gated        | 1         |
| `daily_briefing`     | Your morning, already digested    | Rich replies (briefing)           | 1         |
| `config_tour`        | Yours to shape, in a few clicks   | In-app, non-technical settings    | 2         |

The registry lives in `src/components/showroom/missions/` (one deep-frozen
definition per file, `missions/index.ts` as the ordered picker source). The
mission ids mirror the backend telemetry vocabulary — a mission cannot exist
without its two bounded per-mission funnel events (§5), enforced on both
sides by tests.

### The honesty contract

This is the part that must never drift:

| The showroom **is**                                   | The showroom **is not**                        |
| ----------------------------------------------------- | ---------------------------------------------- |
| A guided, synthetic demonstration                      | Live inference                                 |
| The real HITL and trace UI contracts                   | A mockup of them                               |
| Deterministic, replayable, identical for every visitor | A model call, an agent run, or a real decision |
| Zero external action, zero account, zero model call    | Connected to any provider or any real inbox    |

The labels *Guided demonstration*, *Synthetic data*, *No external action* are
visible at **every** phase and are asserted by the end-to-end suite. Copy that
would blur this — "live AI", "real inference" — is checked against by the
launch gates.

Why guided rather than live: a public live agent needs isolation, budgets,
abuse control, and purge. That is a separate, heavier surface (§7). The
guided mission gives an honest answer to the visitor's question today, with
no runtime risk at all.

### A mission, phase by phase

Every mission walks the same generic machine (the picker fronts it all):

| Phase              | What the visitor sees                                | How it advances                     |
| ------------------ | ---------------------------------------------------- | ----------------------------------- |
| *picker*           | Six mission cards + the honesty strip                 | Visitor picks a mission             |
| `ready`            | The mission framing and a start control               | Visitor presses start               |
| `reading_sources`  | The mission's 3–4 sources revealed one by one         | Paced, or explicit Continue         |
| `planning`         | The findings and what LIA intends to do               | Paced, or explicit Continue         |
| `decision` (×1..3) | Each prepared proposal — **approve, edit* or refuse** | The visitor decides, in order       |
| `receipt`          | **LIA's rich reply**, the simulation receipt, proof links | Restart, another mission, or a CTA |

\* *edit* exists only on draft (email-like) decisions; tool confirmations are
approve/refuse, exactly like the product's cards.

Three properties are deliberate:

- **A decision can never be skipped.** The advance event is ignored in every
  decision step; only an explicit decision moves the mission forward.
- **A refusal is shown as respected.** The receipt states what was *not* done.
  Refusing is a first-class outcome, not an error path.
- **The reply reflects the decisions.** LIA's closing answer — rendered by the
  REAL chat rich-HTML pipeline (`MarkdownContent` → sanitize, the ADR-177
  component vocabulary: `lia-kv`, `lia-chip`, `lia-callout`, `lia-steps`,
  `lia-stats`, `lia-collapsible`) — never describes a refused effect as
  applied. The markup is composed once in `response-html.ts`; locales carry
  only text, and every interpolation is HTML-escaped.
- **Two voices, never mixed** (owner arbitration 2026-08-06). The reply
  speaks as the assistant would in a REAL exchange — **written, natural,
  fluent prose with a touch of sarcasm** ("the weather decided to sabotage
  your 18:00 run, and Marc is still waiting — since Tuesday, but who's
  counting?"), opened by a real paragraph and closed by a character line.
  Everything meta or pedagogical ("nothing was asked — the scan caught this
  on its own", "memory is editable in settings", "calls are always gated")
  lives in the visually distinct **demo note** bubble (`MissionDemoNote`,
  `def.noteKey`) rendered beside the reply. A callout is allowed inside the
  reply only when it is task content (the 10:00 deadline, the agenda
  overlap). Intros and closings stay decision-neutral — they describe what
  LIA analyzed and prepared, never an effect the visitor may have refused;
  the chips carry the applied/refused truth.

### The two Web variants

| Variant  | What `/demo` renders                                     | Default |
| -------- | -------------------------------------------------------- | ------- |
| `legacy` | The four-act passive mockup inside the planetarium        | **Yes** |
| `guided` | The interactive mission described above                   | No      |

The variant is a **build-time** choice (§3). Anything other than `guided`
falls back to `legacy` silently — a typo in a deployment variable must never
break the public page.

The variant also drives the **landing-page call to action**: under `guided`
the hero shows a *Guided demo* button linking to `/demo`; under
`legacy` that button is absent from the DOM entirely — advertising the
passive mockup as a demo would overpromise. Same honesty rule, same
build-time switch, no runtime branch.

---

## 2. How it is built

### Shape of the code

Everything lives under `apps/web/src/components/showroom/`, with one
responsibility per file:

| File                       | Responsibility                                                    |
| -------------------------- | ----------------------------------------------------------------- |
| `types.ts`                 | The closed unions: phases, decision kinds, state, events, and the mission-definition contract |
| `reducer.ts`               | The **pure** machine factory (`makeShowroomReducer(def)`) — no timers, no `Date`, no i18n, no telemetry |
| `useShowroomMission.ts`    | The controller: pacing, at-most-once event emission (aggregate **and** per-mission), the `send()` guard |
| `missions/*.ts`            | One versioned, deep-frozen definition per mission + the ordered registry |
| `hitl-adapter.ts`          | Builds real approval-card state from any decision spec             |
| `response-html.ts`         | Composes LIA's rich reply (ADR-177 vocabulary, decision-aware, escaped) |
| `ShowroomRichResponse.tsx` | Renders the reply through the REAL chat pipeline (dynamic import)  |
| `ShowroomMission.tsx`      | The view, decomposed one component per phase                       |
| `MissionPicker.tsx`        | The six mission cards fronting `/demo`                             |
| `MissionActions.tsx`       | Receipt actions, owner-arbitrated order: install guide (solid) → releases → source → proofs, then replay + all-missions (ghost). No beta CTA — the demo funnels to self-hosting |
| `MissionDemoNote.tsx`      | The pedagogical bubble — SEPARATE from LIA's reply (voice contract below) |
| `HonestyStrip.tsx`         | The three honesty statements, on the picker and in every mission   |
| `ExecutionReceipt.tsx`     | The final receipt, one row per decided step, including refusals    |
| `ProofDrawer.tsx`          | The "show me the source" drawer                                    |
| `proof-links.ts`           | The code-owned proof registry and its immutability rule            |
| `GuidedShowroom.tsx`       | Mission selection + the only place missions meet telemetry         |

### The state machine is pure, and small on purpose

The mission state holds **only** a phase, a run counter, a source counter, and
two decision enums. It contains no free text, no timestamps, and no
identifiers. The email draft the visitor may edit lives transiently in the
view layer and **never enters the state** — which is what makes the whole
mission trivially safe to reason about, and why no visitor text can ever reach
telemetry.

Any out-of-order event returns the **same state reference**, so React never
re-renders on a no-op.

### One design decision worth knowing: `send()`

The controller never dispatches blindly. It first runs the reducer against an
event-phase copy of the state, and only if the state actually changed does it
dispatch **and** emit telemetry:

```ts
const next = showroomReducer(pendingRef.current, event);
if (next === current) return null;   // rejected → no dispatch, no event
```

This is what makes a double-click, a rejected decision, or an out-of-order
advance produce **no phantom analytics**. It also removes an entire class of
React-hook bugs: nothing is written during render.

### Definitions are versioned and i18n-keyed

Every mission definition under `missions/` is deep-frozen at module load and
contains **no literal prose** — only i18n keys, bounded `HH:MM` times,
`example.invalid` addresses, and structure. That is why the same missions
play in six languages with no translation of code, and why a content change
is a reviewable, testable diff rather than a copy edit.

### It reuses the real product components

The approval cards, the trace disclosure and the rich-reply renderer are the
**same components** the authenticated chat uses. The adapter builds card
state from each decision spec; `ShowroomRichResponse` feeds the composed
reply through the chat's `MarkdownContent` sanitize pipeline. This is the
whole point: what the visitor manipulates is not a drawing of the approval
flow — it is the approval flow, and the reply they read is rendered by the
exact production pipeline.

### The proof drawer, and its honesty rule

At the end of the mission the visitor can open a drawer that says, in effect:
*here is the actual code behind what you just watched*. It links eight
repository paths — the routing node, the planner, the orchestrator, the HITL
classifier, the approval card, the trace capture, the fixture itself, and the
mission tests.

That claim is only honest if the links point at the code **that produced this
exact build**. A link to a branch would show whatever the branch contains
*tomorrow*, which may be different from what the visitor saw — the drawer
would then be quietly lying. So the links are pinned to an immutable commit,
supplied at build time through `NEXT_PUBLIC_SHOWROOM_PROOF_SHA` — see
*Setting the proof SHA* in §3 for the exact commands.

The rule is binary, with no middle ground:

| The value is…                              | Result                                                          |
| ------------------------------------------ | --------------------------------------------------------------- |
| A full 40-character hex commit SHA          | Links go to `…/blob/<sha>/<path>` — permanent, exact, immutable  |
| Anything else (unset, a tag, a branch, a short SHA) | **Every link falls back to the repository root**, and the drawer is flagged non-immutable so the UI does not claim "exact source" |

There is no way for a caller to inject a URL or a path: the registry of eight
paths is code-owned, and the only external input is that one SHA.

### Telemetry is a separate, credential-less path

The showroom does **not** use the ordinary product-telemetry route. It has its
own, for one reason: the ordinary route attaches the session cookie.

| Ordinary product events                    | Showroom funnel                                    |
| ------------------------------------------ | -------------------------------------------------- |
| `POST /api/v1/product/events`               | `POST /api/v1/product/showroom-events`             |
| `credentials: 'include'`                    | `credentials: 'omit'` — never carries a cookie     |
| `sendBeacon` used for page-hide flush       | **Never** `sendBeacon` (its same-origin credential behavior would break the contract) |
| Session-attributed                          | No identity, no network metadata, no free text     |

The two event vocabularies are **disjoint at the schema level**: a showroom
event posted to the ordinary route is rejected with 422, and vice versa. That
is a structural guarantee, not a convention.

---

## 3. Configuration

### Web build-time variables

`NEXT_PUBLIC_*` values are **inlined into the JavaScript bundle at build
time**. Changing any of them requires a Web rebuild — they are not runtime
settings.

| Variable                              | Values                | Default  | Effect                                                        |
| ------------------------------------- | --------------------- | -------- | ------------------------------------------------------------- |
| `NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT` | `legacy` \| `guided`  | `legacy` | Selects what `/demo` renders                                   |
| `NEXT_PUBLIC_SHOWROOM_PROOF_SHA`      | full 40-hex commit SHA | *(unset)* | Makes proof links immutable; anything else degrades honestly |
| `NEXT_PUBLIC_PRODUCT_TELEMETRY`       | `true` \| `false`     | `false`  | Enables the funnel attempts (mission behavior is identical either way) |
| `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE`  | `0`–`1`               | *(deployed value)* | Unrelated stream — set to `0` in test builds so it cannot blur the network oracle |

### Setting the proof SHA

**What it is:** the full commit SHA of the source you are building, used to
build permanent links in the proof drawer. Nothing else. It is not a secret,
not a credential, and it changes on every release.

**Why a full SHA and not a tag or a branch:**

| Reference        | Why it is refused                                                         |
| ---------------- | ------------------------------------------------------------------------- |
| A branch (`main`)| Moves. Tomorrow the link shows different code than the visitor saw.        |
| A tag (`v1.28.0`)| Can be re-pointed, and an *annotated* tag's own object SHA is **not** the commit SHA — a classic way to bake the wrong value. |
| A short SHA      | A prefix, not an identity; ambiguous by construction.                      |
| A full 40-hex SHA| Immutable and unambiguous. This is the only accepted form.                 |

**How to set it, by build path:**

*Release CI — nothing to do.* The release workflow passes
`NEXT_PUBLIC_SHOWROOM_PROOF_SHA=${{ github.sha }}`. On a tag push that value
is already the commit the tag points at, so the links are automatically
correct and the annotated-tag trap cannot happen.

*Building the image yourself with Compose* — put it in your `.env` next to the
variant, then build:

```bash
# .env
NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided
NEXT_PUBLIC_SHOWROOM_PROOF_SHA=<paste the output of the command below>
```

```bash
git rev-parse HEAD                      # the commit you are building
docker compose -f docker-compose.prod.yml build web
```

*Building the image directly:*

```bash
docker build -f apps/web/Dockerfile.prod \
  --build-arg NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided \
  --build-arg NEXT_PUBLIC_SHOWROOM_PROOF_SHA="$(git rev-parse HEAD)" \
  -t lia-web:local .
```

*Running the Web app locally, without Docker:*

```bash
cd apps/web
NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided \
NEXT_PUBLIC_SHOWROOM_PROOF_SHA="$(git rev-parse HEAD)" \
pnpm build && pnpm start
```

**If you are building from a tag**, dereference it to its commit — never use
the tag object:

```bash
git rev-parse "v1.28.0^{commit}"        # correct
git rev-parse "v1.28.0"                 # WRONG for an annotated tag
```

**How to check it worked:** open `/demo`, run the mission to the receipt, open
the proof drawer, and click any link. It must land on a `/blob/<40-hex>/…`
URL showing the file. If it lands on the repository home page instead, the
value was absent or malformed — and the drawer will not be claiming exact
source, which is the intended safe behavior, not a crash.

**Committing a fake or placeholder value is forbidden.** An empty value is
honest (links degrade); an invented one is not.

### API-side settings

| Setting                       | Env variable                    | Default  | Effect                                              |
| ----------------------------- | ------------------------------- | -------- | --------------------------------------------------- |
| `product_analytics_enabled`   | `PRODUCT_ANALYTICS_ENABLED`     | `false`  | **Mounts the collector route.** Off → every funnel attempt 404s |
| `product_showroom_minute_cap` | `PRODUCT_SHOWROOM_MINUTE_CAP`   | `600`    | Global per-minute request ceiling                    |
| `product_showroom_day_cap`    | `PRODUCT_SHOWROOM_DAY_CAP`      | `50000`  | Global per-UTC-day request ceiling                   |

The two caps are **global**, not per-visitor — the collector has no identity
to key on, by design. They are fail-closed: if the quota backend is
unreachable, the collector refuses rather than accepting unbounded traffic.

> **The dependency that is easiest to miss:** the mission works perfectly with
> `PRODUCT_ANALYTICS_ENABLED=false`. Nothing breaks, nothing is visible to the
> visitor — you simply measure nothing. Check this before concluding the
> funnel is broken.

### Internationalization

The showroom owns **72 keys** under the `showroom.` namespace, present in all
six locales (`en`, `fr`, `de`, `es`, `it`, `zh`). Strict key parity is
enforced by the pre-commit hook and by `task lint:i18n`. The fixture carries
keys only, so adding a language is a translation task with no code change.

### Accessibility and motion

Under `prefers-reduced-motion`, pacing is disabled and every automatic
transition becomes an explicit **Continue** control. The mission is fully
keyboard-operable in both modes, and the accessibility suite runs it in dark
and light themes.

### Pacing

| Step                              | Delay    |
| --------------------------------- | -------- |
| Between two source reveals        | 900 ms   |
| Last source → planning            | 1100 ms  |
| Planning → the first decision     | 1600 ms  |

This is storyboard rhythm, not inference latency, and the code says so.

---

## 4. Deploying it

### Enabling the guided variant

A release that publishes the showroom builds the Web image with:

```bash
NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided
NEXT_PUBLIC_PRODUCT_TELEMETRY=true
NEXT_PUBLIC_SHOWROOM_PROOF_SHA=<full 40-hex commit SHA of this build>
```

and an API running with `PRODUCT_ANALYTICS_ENABLED=true`.

Rules that matter:

- **The proof SHA is automatic in release CI.** The workflow passes
  `github.sha`, which on a tag push is already the commit the tag points at.
  You never type it, and a fake or placeholder value is never committed.
- **The variant is baked, not toggled.** Switching between `legacy` and
  `guided` is a Web rebuild and redeploy. There is no runtime switch, and that
  is deliberate: the public page must not depend on a runtime lookup.
- **A stale build tests the wrong thing.** Because the flags are baked, any
  verification must run against a build made with those exact flags — which is
  why the test targets below force a clean rebuild.

### Gates before publishing

Run these; all must be green:

```bash
task test:frontend            # unit suites incl. showroom, telemetry, demo page
task test:e2e:showroom        # clean telemetry-OFF build: zero API call + axe
task test:e2e:showroom:telemetry  # clean telemetry-ON build: the funnel contract
task lint:i18n                # six-locale parity
```

| Target                          | What it actually proves                                                             |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `test:e2e:showroom`             | With telemetry off, **not a single `/api/v1` call** occurs across every decision path; no accessibility violation in dark and light; no horizontal overflow from 320 px to 1280 px; all six locales |
| `test:e2e:showroom:telemetry`   | With telemetry on, the **only** API traffic is the credential-less collector call, carrying no `Cookie` and no `Authorization`, answered `202` |
| `test:e2e:showroom:capture`     | Produces the launch video and stills reproducibly                                    |

Each target forces a fresh build (`E2E_FORCE_FRESH`) and pins
`NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0`, because the layout's own vitals stream
would otherwise add API traffic and blur the zero-call oracle.

> **Once the repository `.env` sets the guided variant**, remember that
> `task test:frontend` loads that file: a unit test asserting a *default*
> (`legacy`, or an unset proof SHA) must stub the variable away explicitly
> (`vi.stubEnv(..., undefined)`) rather than rely on ambient absence —
> otherwise it passes on a fresh clone and fails on any configured machine.

The full launch-day checklist — including infrastructure log policy for the
collector route and the honesty gates — is in the launch playbook.

### Rolling back

Rebuild and redeploy the Web image with
`NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=legacy`. The API side needs no change:
the collector simply stops receiving traffic. No data migration, no cleanup.

---

## 5. Operating it

### Reading the funnel

Twenty-three bounded events, each an enum value with no payload — the eleven
aggregate events below plus **two per mission** (`demo_mission_started_<id>`
and `demo_completed_<id>`, one pair for each of the six mission ids). The
per-mission variants answer *which mission engages and which converts*
without any free-text property: start and completion emit the aggregate event
**and** the mission-tagged one.

| Event                        | Emitted when                                    | Cardinality        |
| ---------------------------- | ----------------------------------------------- | ------------------ |
| `demo_viewed`                | The page mounts                                  | Once per page load |
| `demo_mission_started`       | The visitor starts the mission                   | Once per run       |
| `demo_first_hitl_decided`    | The first decision of a run, whatever it is      | Once per run       |
| `demo_hitl_confirm`          | An approval                                      | Per decision       |
| `demo_hitl_edit`             | An edit (email only)                             | Per decision       |
| `demo_hitl_cancel`           | A refusal                                        | Per decision       |
| `demo_completed`             | The receipt is reached                           | Once per run       |
| `demo_first_proof_opened`    | The proof drawer is opened from the receipt      | Once per run       |
| `demo_source_clicked`        | The "view source" call to action                 | Once per run       |
| `demo_release_clicked`       | The release call to action                       | Once per run       |
| `demo_install_guide_clicked` | The install-guide call to action                 | Once per run       |

Semantics you need when interpreting the numbers:

- **Per-run guards reset on start.** A visitor who restarts produces a second
  `demo_mission_started`, a second `demo_completed`, and so on — but only ever
  one `demo_viewed` per page load, however many missions they try.
- **`demo_viewed` is page-level, not mission-level.** Divide
  `demo_mission_started_<id>` by `demo_viewed` for the picker's pull, and
  `demo_completed_<id>` by `demo_mission_started_<id>` for each mission's
  hold.
- **A rejected interaction emits nothing.** Double-clicks and out-of-order
  actions produce no event at all, so decision counts are real decisions.
- **Call-to-action and proof events only fire from the receipt.** They measure
  intent *after* the visitor has seen the outcome.

**Where to watch it**: the Grafana product dashboard (`26-product-value`)
carries a dedicated row — *11 · Showroom funnel (/demo)* — with three
panels over `product_client_events_total{channel="web_showroom"}`: the
aggregate funnel, starts/completions per mission, and the decision mix.

The natural funnel to watch:

```text
demo_viewed  →  demo_mission_started  →  demo_first_hitl_decided  →  demo_completed
                                                                          ↓
                                              demo_first_proof_opened / *_clicked
```

The decision mix (`confirm` / `edit` / `cancel`) is the interesting signal: it
tells you whether visitors understand that refusing is a supported outcome.

### What is never collected

No identity, no session, no cookie, no IP, no user agent, no free text, no
timestamps beyond the server's own, and no email draft. The request body is a
list of enum values — nothing else can be expressed. If you need to justify
this to a reviewer, the schema is the argument: the endpoint accepts a bounded
vocabulary and rejects anything outside it.

Two things to inventory on your infrastructure, because they sit **outside**
the application: your CDN, tunnel, or reverse proxy may log the collector
route's requests with client addresses. Disable or redact where supported, and
never join those logs to the funnel.

### Interpreting a failure

| Symptom                                | Most likely cause                                                        |
| -------------------------------------- | ------------------------------------------------------------------------ |
| Mission works, funnel is empty          | `PRODUCT_ANALYTICS_ENABLED=false` on the API — the route is not mounted (404) |
| Funnel empty, API flag is on            | The Web build has `NEXT_PUBLIC_PRODUCT_TELEMETRY=false` — rebuild required |
| `/demo` shows the old mockup            | The Web build has the default `legacy` variant — rebuild required         |
| The landing has no demo button          | Same cause: the button only exists in a `guided` build                    |
| `auth/me` shows up in the zero-API oracle | `/demo` lost its entry in the `initAuth` skip list (`lib/auth.tsx`) — the page renders no header and consumes no auth state, so that call must never fire |
| Dev container ignores an `.env` change  | `docker restart` does not re-read `env_file` — recreate it (`docker compose -f docker-compose.dev.yml up -d --force-recreate web`) |
| Proof links point at the repository root | `NEXT_PUBLIC_SHOWROOM_PROOF_SHA` is absent or not a full 40-hex SHA       |
| Collector answers 429                   | A global cap was reached — expected under load; raise the cap deliberately or accept the loss |
| Events counted but decisions look odd   | Remember the per-run reset: restarts inflate run-scoped events            |

A failing collector **never** degrades the mission: every telemetry failure is
swallowed by design, and the visitor sees nothing.

### Changing mission content — or adding a mission

Definitions are versioned. Treat a content change as a product change:

1. Edit the mission file under `missions/` — bump its `fixtureVersion` if the
   storyboard itself changes.
2. Add or update the i18n keys in all six locales.
3. Run `task test:frontend` (every definition has its own contract test).
4. Re-run `task test:e2e:showroom` — the end-to-end suite asserts the visible
   labels and the decision paths.
5. If you added a proof-worthy file, add it to the registry in
   `proof-links.ts` so the drawer stays complete.

**Adding a mission** touches BOTH sides of the bounded-vocabulary contract,
in this order (each step is guarded by a test that fails if skipped):

1. Backend: add the id to `SHOWROOM_MISSION_IDS` and the two enum members
   (`demo_mission_started_<id>`, `demo_completed_<id>`) with descriptions in
   `src/domains/product/constants.py` — the frozenset derivation refuses to
   import otherwise.
2. Frontend: mirror the id in `SHOWROOM_MISSION_IDS`
   (`lib/product-telemetry.ts`).
3. Write the deep-frozen definition in `missions/<id>.ts` and register it in
   `missions/index.ts` (picker order).
4. Write its rich reply in `response-html.ts` (the `BUILDERS` record is
   keyed by the id union — the compiler refuses a missing entry).
5. i18n ×6, unit walk, e2e if the journey shape changed.

Never inline prose in a definition, and never let visitor-derived text into
the mission state.

### Producing launch assets

```bash
task test:e2e:showroom:capture
```

This records the canonical mission at 1440×900 with real pacing (approve the
email, refuse the calendar change) plus two stills — the receipt proving the
refusal, and the proof drawer. Artifacts land in Playwright's output directory
and are never committed.

---

## 6. Test inventory

| Layer            | What it covers                                                              |
| ---------------- | --------------------------------------------------------------------------- |
| Unit (reducer)   | Every transition and rejected event, for EVERY registered mission            |
| Unit (fixtures)  | Deep-freeze, structure, i18n-key-only content, registry ↔ telemetry mirror   |
| Unit (adapter)   | Real approval-card state built from any decision spec                        |
| Unit (reply)     | `lia-response` envelope, decision honesty (refusal ≠ applied), escaping      |
| Unit (proof)     | Immutable vs degraded link building, 40-hex validation                       |
| Unit (view)      | Phase rendering, decision wiring, per-mission funnel, accessible names       |
| Unit (picker)    | Six cards, keyed remount, page-level `demo_viewed`, fresh state per pick     |
| E2E smoke        | Six viewports, six locales, zero-API oracle (picker included)                |
| E2E telemetry    | The credential-less contract on a telemetry-ON build, per-mission events     |
| E2E accessibility| axe on picker + mission states, dark and light                               |
| E2E capture      | Reproducible launch assets                                                   |
| Backend          | Vocabulary disjointness, quota fail-closed behavior, the `202` contract      |

---

## 7. The live extension, and where it stops

Letting a visitor talk to a real agent is a fundamentally different risk
surface from a storyboard: it needs an isolated process, an isolated database,
a spend ceiling, abuse control and complete purge of every visitor trace.

That is a **separate deployment**, not a mode of this page: the public
demonstrator, documented in
[DEMO_INSTANCE.md](../technical/DEMO_INSTANCE.md). It runs the standard LIA
image inside its own Compose envelope and shares no resource with the hosted
site's API or with a self-hosted installation.

The two are complementary rather than exclusive. This page shows both: when an
operator switches the public link on, `LiveDemoInvitation` introduces the
demonstrator ABOVE the guided missions, stating every limitation before
offering the link. When the link is off, the guided missions are the whole
page — they are the socle and the fallback.

An earlier attempt embedded a live mission INSIDE this page, proxied through
the web server to a second backend. It was removed in 2026-08: a demonstrator
that shows the real product is better served by running the real product in an
envelope than by a second, reduced implementation of it that has to be kept
true to the first.

For a self-hoster, none of this is relevant: the showroom is a public-site
surface, and a self-hosted installation does not need it. See
[GUIDE_SELF_HOSTING.md](./GUIDE_SELF_HOSTING.md).

---

## Current status

- The guided showroom is implemented and covered end to end: unit suites, a
  zero-API end-to-end oracle, the credential-less telemetry contract, an
  accessibility pass in both themes, and a reproducible capture run.
- The default variant is `legacy`. Publishing the guided mission is a
  deliberate release decision, gated by the launch playbook's checklist.
- The live extension exists but stays behind its own qualification.
