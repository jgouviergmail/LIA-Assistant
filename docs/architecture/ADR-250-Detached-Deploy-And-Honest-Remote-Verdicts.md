# ADR-250 — A lost connection is not a failed deployment: the remote verdict is read, never deduced

- **Status**: Accepted
- **Date**: 2026-08-29
- **Related**: ADR-215 (qualified release pipeline), SEC-013 (production secret
  permissions), SEC-040 (the decrypted secret must not outlive the run),
  ADR-182 / ADR-184 (never report an invented diagnosis), ADR-151 (the workflow
  orchestrates, the Taskfile implements)

## Context

The production deploy driver ended on an error message that the operator had
been taught to ignore. The `lia-deploy-prod` skill said so in writing, under the
heading *"the exit code lies"*: `task deploy:prod` finishes on a reset SSH
session **even when the deployment succeeds**.

A written instruction telling a human to disregard an error message is not a
workaround. It is the defect, relocated into prose — and it had two independent
causes.

### 1. `ssh` reuses one exit code for two unrelated events

Measured on the real host on 2026-08-29:

| What happened remotely | What `ssh` returned |
|---|---|
| remote command `exit 7` | `7` |
| remote command `exit 1` | `1` |
| remote command `exit 255` | `255` |
| host unreachable | `255` |
| broken `ProxyCommand` | `255` |

`ssh` propagates the remote exit code faithfully for **every value except
255**, which it also uses for every transport failure of its own. On 255, and
on 255 alone, the caller knows strictly nothing about what happened on the
server. The driver was calling that "Echec du deploiement".

### 2. The deployment could not survive its own connection

The remote work ran inside a blocking `ssh` session, so the survival of an
eleven-minute deployment (measured on v1.37.0: build at 08:38:18Z, readiness at
08:49:12Z) depended on the survival of a TCP connection across a home network,
a Cloudflare tunnel and a Raspberry Pi.

It did not survive. Measured 2026-08-29: killing the ssh client makes the remote
script die of **SIGPIPE (exit 141) within about six seconds** — as soon as it
next writes to the channel, not after the 6 min 15 s of keepalive one would
expect. On one of the two attempts, **no verdict was written at all**: the
wrapper died with the script.

So both readings were wrong. Announcing a failure was false most of the time,
because the deployment usually succeeded. Announcing a success would have been
false the rest of the time, because a lost connection really can kill a
deployment in mid-`up`.

### 3. The false failure made a secret leak systematic

`PROD/.env` is the production environment file **in clear** — step 4 renames the
decrypted `.env.prod` into it. Step 10 deletes the whole bundle, but step 10
only runs on the happy path, and the driver has 14 early exits (11 `exit`,
3 `throw`).

Because the nominal path *ended on a false failure*, the failure path **was** the
nominal path. The leak was not an edge case: measured on 2026-07-28, **434 MB of
bundle survived a deployment that had actually succeeded**, carrying every
production credential on the developer's machine.

## Decision

### 1. The rule about 255 lives in exactly one library

`scripts/deploy/lib/RemoteExit.ps1` classifies an ssh exit code as
`Success` / `ContactLost` / `RemoteFailure`, and is the only place where that
rule is written. Both drivers consume it — `deploy-prod.ps1` and
`demo-prod.ps1` — because two copies would have diverged, and an operator would
have had to learn a lost connection twice.

Out-of-range codes (negative, > 255) are classified as **remote failures**: they
cannot be ssh's 255, and calling them "a lost connection" would be the invented
diagnosis this ADR exists to remove.

The prose an operator reads on a lost contact also comes from the library
(`Get-ContactLostExplanation`), rendered as lines so each driver prints it with
its own display palette. Its order is deliberate — what happened, what is
unknown, then the warning — because an operator skimming three lines must have
seen **"do not re-run"** before deciding anything.

### 2. The deployment runs detached, and its verdict is a file

Step 9 no longer holds a session open. It launches the remote deployment
detached, then polls for a verdict the remote **wrote**. The same work that died
of SIGPIPE in six seconds survives the destruction of every ssh client and
returns its exact exit code.

Detachment is not obtained naively. **Four forms failed** (`nohup`, `+disown`,
`setsid`, `setsid` without `&`) because `&` backgrounds the *entire list* in a
subshell that keeps the channel, while the redirection only covers the last
command. The form that works prepares synchronously, then launches one isolated
command whose **three** streams are redirected — `>/dev/null 2>&1 </dev/null`.
A single descriptor left open on the channel holds `ssh` until the work
finishes, which cancels the entire benefit.

Three further properties, each paid for by a measurement:

- **Single quotes around the detached body, and it is structural.** In double
  quotes the *outer* shell expands `$?` before handing the string to the inner
  one, which then receives `echo 0 > run.rc`. The verdict was **always 0** —
  including for a deployment that had failed. Measured on a real run: script
  exited 23, `.rc` carried 0. No amount of inspection would have caught it; it
  had to be executed. The payload builder now refuses a body containing a single
  quote rather than emitting something subtly wrong.
- **Per-run artifacts, therefore no purge.** The earlier form purged a shared
  `.rc`/`.log` before attempting the lock. A second concurrent launch destroyed
  the log of the deployment **in flight** (3 lines → 0, the first process still
  writing into an unlinked inode) and wrote a marker into the `.rc` the first
  was about to overwrite. Naming artifacts after the run removes the whole class:
  there is no shared file left to destroy.
- **The log goes to a file, never to the channel.** Writing to the channel is
  precisely what kills the remote by SIGPIPE when the client disappears. The
  driver relays the file to the operator by tailing it on each poll, so nothing
  is lost in readability.

One deployment at a time is enforced by `flock` taken **by the detached process**
and held for its whole life. The lock is kernel-managed, so it is released even
if the process is killed: there is no ghost lock to clean up by hand.

Liveness is probed **through the lock**, not with `pgrep -f`, which matches its
own command line — measured 2026-08-29: two diagnostics counted themselves, and
a cleanup command killed itself.

### 3. Six outcomes, because six different things must be done

| Outcome | What is known | What the operator must do |
|---|---|---|
| `Success` | the `.rc` carries 0 | nothing |
| `RemoteFailure` | the `.rc` carries a non-zero code **written by the server** | read the remote log; this is the one state where "the deployment failed" is a true sentence |
| `Busy` | another deployment held the lock; **this one did not happen** | wait — nothing was changed remotely |
| `Interrupted` | no `.rc`, process gone — killed in mid-flight | investigate; **do not re-run** |
| `Unknown` | the polling budget ran out while it was still running | wait, or re-run with a larger `-DeployBudgetSeconds`; **do not re-run the deployment** |
| `LaunchFailed` | the launch call itself failed | if the code is unambiguous, nothing started and re-running is safe; if it is **255**, the host may have forked the work before the channel died |

`Interrupted` and `Unknown` are **not failures** and must never be presented as
such: in the first the work stopped somewhere, in the second we stopped
watching. `Busy` is not a failure either — a refused deployment did not happen.

Two rules make the machine honest rather than merely detailed:

- **A poll that does not connect is retried, never converted into a verdict.**
  A cut during polling says nothing about the work. Turning it into an outcome
  would reproduce the exact defect being removed.
- **The `.rc` outranks the observed process state.** At the end of the work the
  verdict is written a fraction of a second before the wrapper disappears, and a
  poll in that same second still sees it alive. What was written wins over what
  was observed.
- **An unreadable `.rc` is not a zero.** A truncated or polluted verdict file is
  an unknown, and is reported as `Interrupted`.

Every path where the driver cannot conclude prints the same three commands —
the remote log, `docker compose ps`, and the release manifest — so the operator
is handed the means to decide instead of a guess. And every one of them says
**do not re-run**, because step 7 would wipe the staging directory under a build
still in flight.

The watching budget is a **parameter** (`-DeployBudgetSeconds`, default 2700 s),
not a constant. A loaded Pi exceeds the eleven measured minutes, and a cautious
verdict that cannot be adjusted is a verdict operators learn to read as a
breakage.

### 4. `SEC-040` — the decrypted secret does not outlive the run

Every exit path of the driver now passes through a `finally` that removes the
secret-bearing artifacts from `PROD/`. PowerShell runs `finally` on `exit` as on
an uncaught `throw`, preserving the return code — verified on both Windows
PowerShell 5.1 and pwsh 7.

Three properties, each of which was a defect first:

- **The list is exact, never a glob.** `provenance.env` lives in the same
  directory, is not a secret, and four tests read it.
- **Two sets, and their difference is the point.** The pre-transfer purge (step
  3) deliberately excludes `.env.prod`, because step 4 still has to rename it
  into `.env`. Conflating them deletes the source before its rename, the bundle
  ships **without an environment file**, and the deployment fails remotely on a
  missing `.env`. That exact error red-lit the test *"renamed .env.prod to .env
  inside the bundle"* on the first pass.
- **The cleanup is surgical.** A blanket `Remove-Item PROD` would destroy the
  bundle an operator inspects after a failure. A failed deployment is something
  one debugs.

It reports with `Write-Success`, not `Write-Warning`: nothing went wrong *here*.
On a failure path this line is often the only good news — it tells the operator
their production credentials are not lying around.

`-DryRun` is exempt by contract: a simulation must leave a pre-existing `PROD/`
strictly intact, keys included.

## Consequences

- **`task deploy:prod` no longer lies**, and the "disregard this error"
  instruction is deleted from the skill rather than reworded.
- **A deployment survives the operator's laptop.** Closing the terminal, losing
  Wi-Fi or suspending the machine no longer kills a production build.
- **The hermetic Pester suite grew a protocol.** The ssh shim now answers two
  extra phases; the deploy command travels base64-encoded, so the assertions
  **decode the payload** instead of matching a shim line that no longer carries
  it. Asserting on the marker alone would have proved the driver called
  *something*.
- **The phase travels in clear beside the encoded payload**
  (`lia-deploy-launch` / `lia-deploy-poll`). Encoding is the anti-quoting parade
  — the command crosses PowerShell, ssh's argument reassembly and the remote
  shell, each of which claims the quote — but it also makes the driver's own
  trace, the shim log and the host's process table show nothing but 400
  characters of base64.
- **A trap recorded rather than merely fixed**: `GetNewClosure()` copies every
  variable visible at creation into the closure's scope, **`$LASTEXITCODE`
  included**. Reading it bare inside the closure returns the value frozen at
  that moment, not the one `ssh` just set. Measured 2026-08-29: bare read `0`,
  `$global:` read `255`, for the same call. The test harness surfaced it in
  silence — a launch whose connection dropped was reported as successful, which
  is exactly the verdict-read-from-the-wrong-place this whole ADR removes.

## What the first real deployment found

Two defects that no test could have produced, both found by running the thing
on 2026-08-29 — and the second is the one this ADR would have been wrong
without.

### A library must not make its loader strict

`Set-StrictMode` is scope-based, and dot-sourcing runs a file's statements in
the CALLER's scope. Both libraries opened with `Set-StrictMode -Version Latest`,
which therefore rewrote the semantics of the thousand-line driver that loads
them. The deployment died at step 5 on `Impossible d'extraire la variable
«$IsWindows»` — the driver's own Windows PowerShell 5.1 compatibility idiom,
since `$IsWindows` does not exist there.

The Pester suite could not have caught it: it runs under `pwsh` 7, where
`$IsWindows` IS defined. The guard added is therefore written against the
CLASS — from an explicitly non-strict scope, dot-source the library and read a
name undefined by construction — which fails on every edition.

Production was untouched (the remote step was never reached), and **SEC-040
scrubbed the decrypted secret on the way out**: the safety net introduced in the
same change did its job on its first real failure.

### The verdict must not live in a directory the job renames

The second run deployed successfully — `.rc` = 0, seventeen containers up,
the intended commit running — and the driver saw none of it.

`deploy.sh` ends on ADR-215's atomic swap, `mv "$STAGING_DIR" "$LIVE_DIR"`. The
verdict file, the log and the lock were written **inside the staging
directory**, so they moved at the exact moment the work succeeded. From there
the poll's `cd ~/lia.staging 2>/dev/null || exit 0` found nothing and exited
**silently**, and an empty response is indistinguishable from "no verdict yet,
still running". A fully successful deployment would have been reported `Unknown`
forty-five minutes later.

Two independent faults, and the second is the more general one:

- **The artifacts were inside the blast radius.** They now live in
  `$HOME/.lia-deploy/`, which the deployment never renames, wipes or swaps —
  the lock included, so mutual exclusion survives the swap too.
- **A poll that found nothing said nothing.** `|| exit 0` is the same defect as
  the exit code this ADR set out to stop trusting, one layer down: an absent
  answer was read as a state. The poll no longer changes directory at all, reads
  absolute paths, and always prints its two lines — "the file is not there" is a
  report, not a silence.

The lesson generalises past this driver: **a watcher must not keep its evidence
inside the thing it watches**, and every branch of a probe must produce an
answer. The poll payload had no test of its own until this incident, which is
exactly how a `cd` into a directory the job renames survived review.

## Alternatives considered

- **Keep the blocking session and raise the keepalive.** Refused: measured, the
  remote dies of SIGPIPE in ~6 s, long before any keepalive negotiation matters.
  The coupling is the problem, not its timing.
- **Treat 255 as success.** Refused: it is right most of the time and
  catastrophic the rest, since a cut during `up` really does interrupt a
  deployment.
- **Re-run automatically on an ambiguous verdict.** Refused: step 7 wipes the
  staging directory, which would destroy a build still in flight. Ambiguity must
  reach a human.
- **A remote agent/daemon owning deployments.** Refused as disproportionate: one
  host, one operator, and a `flock` plus a verdict file answer the same question
  with no service to run, secure and supervise.
