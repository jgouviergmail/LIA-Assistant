# ADR-249 — Ephemeral Python: the agent's calculator, in the sandbox that already exists

- **Status**: Accepted
- **Date**: 2026-08-29
- **Related**: SEC-001 (skills script sandbox), ADR-070 (dual execution modes),
  ADR-184 (publish what you enforce), ADR-231 (typed runtime context),
  ADR-248 (ReAct budget earned by progress), ADR-118 (skills)

## Context

A language model answers arithmetic over many rows, joins on a key, durations
across timezones and deduplication *plausibly*, and the user has no way to see
that it is wrong. Those are exactly the tasks where a five-line script produces
a verifiable answer.

The capability this needs was already built and hardened, for a different
purpose: **SEC-001's skill-script sandbox**. One throwaway container per run, no
Docker socket, `--network none`, read-only rootfs plus a small tmpfs, uid 65534,
all capabilities dropped, memory/pids/CPU/file-size bounded, source passed
inline (`python -c`) so nothing is mounted, stdin left free for a JSON payload,
and an unreachable daemon fails the run instead of silently downgrading.

Measured on the production Raspberry Pi before deciding anything: a cold
sandbox spawn costs **279 ms**, 357 ms with the standard library, **459 ms**
with numpy — under 2 % of the 30 s budget. The sandbox is cheap.

So the question was never "build an execution sandbox". It was "may the MODEL
write what runs in it, and under what rules".

## Decision

### 1. The agent decides, the tool is a complement

`run_python_tool` is offered, never imposed. The ReAct prompt tells the model
what it is bad at and to reach for a script *there*, and tells it just as
explicitly not to: not for a single lookup, not for a two-number calculation,
not for anything it can answer directly. A capable tool without that second
sentence becomes a hammer.

### 2. ReAct only — the pipeline uses skills and plugins

Owner arbitration. The pipeline is deterministic and plans ahead: it cannot read
a traceback and repair a script, which is precisely what makes model-authored
code workable. Two enforcements, because one would be a trap:

- the **manifest** declares `execution_modes={"react"}`, and every reader of the
  manifest list applies `manifests_for_mode` — so the planner never SEES the
  tool. A planner that saw it would emit a step, be refused at execution, and
  hand the user an invented dead end;
- the **tool** re-checks `LiaRuntimeContext.execution_mode` at call time (the
  typed runtime of ADR-231 already carried the mode — no new plumbing).

### 3. Model-authored code never runs in the legacy sandbox

The in-process mode only isolates when the API runs as root. That trade-off was
accepted for code the user installed deliberately; it is not acceptable for code
a model wrote *while reading an email*. `execute_source` refuses any sandbox mode
other than `container`. Fail closed, never downgrade.

### 4. The data is handed over, not re-typed

Whatever the turn's tools already collected reaches the script on **stdin** as
JSON (`json.load(sys.stdin)["items"]`). Re-typing the data into the source would
pay the tokens twice and truncate exactly the large cases that justify the
feature. The ReAct execute node publishes the turn's registry; the setup node
resets both the data and the budget each turn.

### 5. Everything enforced is published (ADR-184)

The manifest description states the bounds the model cannot otherwise discover:
**no network** (so it never writes `requests.get` and burns an iteration), no
database, no filesystem beyond `/tmp`, a fresh container per run, the exact
library set, and the budgets — 30 s, 512 MB, 50 KB of stdout, a few runs per
turn.

### 6. Budgets, and what a hostile email can do

Three bounds: the per-turn run cap (a repair loop cannot spin), the per-user
rate limit, and the sandbox's own CPU/memory/time limits. A prompt injection
that reaches the interpreter gets a container with no network, no credentials,
no database and no writable filesystem; the most it can do is print text to the
model — which the hostile email could already do. The script's stdout is
therefore marked `content_trust: "untrusted"` before re-entering the context,
like every other third-party payload.

One residual exposure is recorded rather than hidden: the sandbox image is the
API's own (`lia-api:local`), which is what gives numpy and openpyxl. A script can
therefore read the application's source — an open-source repository, so the
disclosure is nil, but it is a fact and not an oversight.

### 7. pandas is added; numpy is finally declared

Decided on measurement, against the initial instinct: the API image is 3.76 GB,
so pandas adds ~1.5 %, and **every one of its hard dependencies (numpy,
dateutil, pytz, tzdata) is already present** — the dependency graph does not
grow. Data combination is the stated purpose of this feature and is what models
write pandas for, so withholding it would trade first-try correctness for
negligible disk. The lock resolved with **no numpy bump** (2.4.3 unchanged).

While declaring it: `numpy` is imported by four application modules (tool
selection, embeddings, STT, query analysis) and was only ever present
transitively — a real build-input violation, now fixed.

### 8. The code is admin-visible, and only admin-visible

Owner arbitration. The scripts of a turn travel in state to the **debug panel**,
never to the answer surface. Hiding them entirely would buy no security — the
model authored them, so they are already in its context — and would cost all the
verifiability, which is the whole reason to prefer a script to mental
arithmetic.

## Consequences

- A turn that uses the tool costs one container (~0.3–1.5 s) plus the model's
  tokens for writing the script. Most turns never touch it.
- A failing script returns its traceback so the model can repair it; ADR-248's
  productivity rule already prevents that loop from buying iterations, because a
  failed run brings nothing back.
- `PYTHON_SANDBOX_TOOL_ENABLED` defaults to **true** (owner: active for
  everyone) and is the emergency switch; there is deliberately no per-user
  toggle.
- The pipeline is unchanged and keeps its own extension path: skills and plugins.
- Adding a mode restriction to a manifest is now a supported contract, not a
  special case — the filter fails OPEN for manifests that declare nothing.
