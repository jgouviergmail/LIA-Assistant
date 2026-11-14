# Routines started by a signed call

**Decision**: [ADR-386](../architecture/ADR-386-A-Signed-Call-Starts-A-Routine.md) — a routine's third clock.
**Related**: [SCHEDULED_ACTIONS.md](SCHEDULED_ACTIONS.md) (the routines and their two other clocks).

A routine runs on ONE clock: a schedule, a condition the system checks, or — here — another
system's call to the routine's own address. A home automation box, a code forge, a form service:
anything that can send an HTTP request signed with a shared secret can start a routine, and the
routine reads what the call sent.

## The person's side

1. In the routine form, the trigger **When another system calls it** (offered where the
   `ROUTINE_WEBHOOKS` capability is open; kept on a routine already running on it).
2. On save, the server draws the routine's address and its secret. The answer carries the secret
   ONCE; the form shows it in a dialog with the address, a copy button for each and a signed-call
   example. The list never holds it, and no later answer carries it.
3. Lost the secret? Open the routine and **Draw a new secret** (confirmed first): the previous one
   stops working at once. A routine created by the assistant has a secret nobody saw: its owner
   draws one the same way.
4. Switching the routine to another clock erases its address, its secret and the calls still
   waiting. Pausing it makes its address answer 404; the calls already kept wait for it.
5. A routine started by calls is never run by hand (« Run now » is absent): it has nothing to run
   without a call. It cannot propose first either.

## The sender's side

```text
POST {address}
Content-Type: application/json            # any type; the run is told what was declared
X-LIA-Signature-256: sha256=<hex>         # HMAC-SHA256 of the EXACT body, under the secret
X-LIA-Delivery: <your id for this call>   # optional: a retry with the same id is kept once
```

`X-Hub-Signature-256` and `X-GitHub-Delivery` — the names code forges send for the same scheme —
are read alike, so a forge's webhook can point at a routine with no adapter in between.

```bash
URL='https://…/api/v1/hooks/routines/<key>'
SECRET='<secret>'
BODY='{"event": "door_opened"}'
SIGNATURE="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')"
curl -X POST "$URL" -H 'Content-Type: application/json' -H "X-LIA-Signature-256: $SIGNATURE" -d "$BODY"
```

Sign the bytes you send: `printf '%s'`, never `echo`, which would sign a newline the body does not
carry.

| Answer | Meaning |
|---|---|
| 202 `{"status": "accepted"}` | Kept; served at the scheduler's next pass (within a minute). |
| 202 `{"status": "duplicate"}` | This delivery id was already kept for this routine. |
| 403 | No valid signature — or the capability is closed on this instance. |
| 404 | No routine answers at this address (unknown, or paused): the same answer either way. |
| 413 | The body is over `ROUTINE_WEBHOOK_MAX_BODY_BYTES`. |
| 422 | The address key is not a key (characters, length). |
| 429 | Too many calls from your address, too many to this routine this minute, or too many waiting — retry after `Retry-After`. |

## What the run reads

The run's request is the routine's own instruction, followed by a note
(`prompts/v1/routine_webhook_lines.txt`): how many calls started it, then each call — when it
arrived in the routine's zone, its size, its declared type — its body wrapped as external content
(`wrap_external_content`, an untrusted-data envelope), cut at `ROUTINE_WEBHOOK_PROMPT_CHARS` with
the cut stated. An empty body and one that cannot be decrypted are said, not wrapped. The note
tells the model the bodies are data: what a caller writes can be read, never obeyed.

## The mechanism

- **The door** (`webhook_router.py` → `webhook_service.py`): the capability guard and a per-client
  window first; the body bounded from its declared length, then while it streams; the routine READ
  by its key (the read ends before Redis is asked — ADR-304); the signature checked in constant
  time; the address's own window; then, under the routine's row lock, the duplicate check, the
  backlog bound, the insert (body encrypted) and the arming — committed before the 202. The
  arming wakes a routine that sleeps; an instant already armed stands, so a call arriving during
  a failed run's back-off waits for it. A routine leaving this clock forgets its calls under the
  same row lock: a call landing meanwhile waits, then finds no address.
- **The tick** (`routine_webhook_gate.py`, called by the scheduled-action executor): with the
  capability open, the routine's oldest waiting calls (`ROUTINE_WEBHOOK_MAX_PER_RUN`) become the
  run's note; with none, the tick rests under the routine's lock, where a call that arrived since
  its read re-arms it at once. The switch it rests on is the one the tick read BEFORE taking that
  lock: nothing is asked of a store while the row is held (ADR-304), and calls waiting behind a
  closed switch are looked at again after the back-off. A run that answered marks its calls
  served in its settle's transaction (body erased); a failed run leaves them waiting and backs
  off `ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS`; a stand-aside writes no run row.
- **Retention**: a served call's row stays `ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS` (its body
  erased) so the same delivery id is recognised, then the executor's step zero purges it.
- **Never finished**: a webhook routine's NULL trigger is a sleep. The closing of finished
  routines skips it, and every reader that announces a next run reads a SCHEDULE only.

## Settings

| Setting | Default | What it bounds |
|---|---|---|
| `ROUTINE_WEBHOOKS_ENABLED` | `true` | The capability's deployment ceiling (the operator's switch acts inside it). Nothing is exposed until a person creates such a routine. |
| `ROUTINE_WEBHOOK_MAX_BODY_BYTES` | `65536` | Largest body accepted. |
| `ROUTINE_WEBHOOK_MAX_PENDING` | `20` | Calls one routine keeps waiting. |
| `ROUTINE_WEBHOOK_RATE_PER_MINUTE` | `30` | Calls one address accepts a minute. |
| `ROUTINE_WEBHOOK_MAX_PER_RUN` | `5` | Calls one run serves. |

Constants (`core/constants.py`): `RATE_LIMIT_ROUTINE_WEBHOOK_PER_IP_PER_MINUTE` (a client, across
every address), `ROUTINE_WEBHOOK_PROMPT_CHARS`, `ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS`,
`ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS`. The demonstrator keeps the capability off.

## Observability

- `routine_webhook_calls_total{outcome}` — `accepted`, `duplicate`, `unknown`, `bad_signature`,
  `rate_limited`, `full`, `too_large`; `routine_webhook_calls_served_total` — calls a run served.
  Both on the « Routines started by a call » row of the proactive dashboard.
- One log line per call a routine was found for, `routine_webhook_call`: the routine's id, the
  outcome, the body's size — never a body, a key, a secret or a sender's words.

## Privacy

- The secret is stored encrypted and shown once; the key and the secret are redacted from the
  account export.
- The calls are not exported: transient inputs of a run, erased once served, purged a week later.
  The runs they started (`scheduled_action_runs`) and the answers (the conversation) are.
- Deleting the routine or the account deletes its calls (cascade).
