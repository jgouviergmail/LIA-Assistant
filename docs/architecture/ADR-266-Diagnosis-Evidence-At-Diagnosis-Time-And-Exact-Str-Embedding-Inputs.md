# ADR-266 — The diagnostician reads its evidence at diagnosis time, and a provider SDK receives an exact `str`

**Date**: 2026-09-05
**Status**: Accepted
**Amends**: ADR-254 (§ "Insufficient evidence, every time"), ADR-247 (pillar 4)
**Context**: On 2026-09-05 the self-check `embedding_failure_rate` went critical
(25 %, threshold 20 %) and the stored diagnosis said, in substance, *"the
detail field is empty and no error log is provided; consult the logs"*. The
owner's complaint was not about that incident: it was that **every** automatic
diagnosis ended the same way. Both halves of the complaint were measured, and
both were true.

## What was measured

### The incident: a deterministic `500` on one path

| # | Fact | Where it was read |
|---|---|---|
| 1 | Five turns out of five since 03:45 UTC lost their RAG context (`rag_injection_failed`), on messages of 84 to 405 characters. | `agent_decisions` × `conversation_messages`, `lia-api-prod` logs |
| 2 | On every turn: the memory embedding of the message succeeded at T, the RAG embedding of the **same text** answered `500 INTERNAL` at T+0.3 s and again at T+1.3 s (the retry). | Loki timeline, 3, 4 and 5 September |
| 3 | Loki over 7 days: 35 `429` failures (1–2 September, the quota incident of ADR-254) then **23 `500 INTERNAL`** failures, all on `embed_query`, all on `rag_injection_failed` or `system_rag_injection_failed`. | Loki |
| 4 | The exact text of the five messages, re-embedded from a fresh process through the application's own RAG client: 5/5 OK. Texts of 64 000 characters: OK. Trace headers, concurrency, a pinned generation: all refuted. | probes run inside `lia-api-prod` |
| 5 | `HumanMessage.text` is a `TextAccessor`, a **`str` subclass** langchain-core keeps so the deprecated `.text()` still works. Passed to `aembed_query`: `500`. A bare `class S(str)`: `500`. A plain `str`: OK. | probe |
| 6 | Captured HTTP body (aiohttp): plain `str` → `{"content":{"parts":[{"text":"…"}]}}`; subclass → `{"content":{}}`. The text is lost **at the pydantic validation of the SDK's request model**: `types.Content` has `from_attributes=True`, so `Content.model_validate(S("hi"))` yields an empty `Content()` (attribute-less object, every field `None`) while `Content.model_validate("hi")` raises — and in the union of the `contents` field, `Content` is declared BEFORE `str`, so smart-union validation keeps it for a subclass. Identical on google-genai 1.67.0 and 2.10.0 under pydantic 2.13.4: present at least since the first lock (2026-07-08). | offline probe, both SDK versions |
| 7 | The memory path only survived because it slices the text (`message[:N]` yields a plain `str`); the RAG path passes the object raw. `aembed_documents` (dict path) and the LangChain chat path are sound; no code in `src/` calls the SDK directly. | code |

### The diagnosis: four out of four without a cause

| # | Fact | Where it was read |
|---|---|---|
| 8 | The four stored diagnoses (3 × `EmbeddingOperationsFailing`, 1 × `SSELatencyP95High`) all conclude "insufficient evidence". The pack handed to the model: `{check_id, value, detail: "", status, unit, warn, crit}`. | `incidents` table |
| 9 | `had_runbook = false` on **every** diagnosis ever stored: `prepare-prod.ps1` staged `docs/knowledge` and never `docs/runbooks`; the compose mount `./docs/runbooks:/app/docs/runbooks:ro` pointed at a directory Docker had created empty. | `ls /app/docs/runbooks`, `prepare-prod.ps1` |
| 10 | A test described a `recent_errors` key in the evidence that nothing in `src/` produced. | grep |
| 11 | The check told the truth: 25 % was 2 failed operations out of 8 in 30 minutes, and the failure was deterministic (100 % of RAG queries). The Prometheus alert (≥ 3 failures in 30 min) did not fire: 2 < 3. | Prometheus |

## Decision

### 1. The funnel normalises the type; the callers do not

`GeminiRetrievalEmbeddings` — the one class every Gemini embedding goes through
— coerces its inputs to an **exact** `str` (`_exact_str`: the same object when
it already is one, a plain copy otherwise), in the four public methods. The
chokepoint that names "the user's message" (`extract_last_user_message`) does
the same, so its five readers receive the type they expect. Both are pinned by
tests that feed the real `TextAccessor` and a bare subclass and assert on the
type the fake SDK received.

*Rejected: fixing the RAG caller only.* Twenty-eight callers reach the funnel;
three already slice, one already wraps in `str(...)`, and the next one would
forget. A structural guarantee at the boundary is the only fix that cannot be
undone by a caller.

*Rejected: reclassifying the `500` as permanent.* The code cannot tell a `500`
caused by an empty request from a provider outage; the fix removes the cause
instead of teaching the retry to give up sooner.

### 2. The NATURE of a provider refusal is a metric

`embedding_provider_errors_total{model, reason}` counts every refused attempt
under the reason the retry already computed (`embedding_retry_reason`:
`http_<code>`, `message:<marker>`, an exception class name, or `permanent`).
One classification, two readers: a dashboard and a diagnosis can never
disagree with the retry about what the provider said. Wired in dashboard 05.

### 3. The evidence pack is collected AT DIAGNOSIS time, per declared recipe, fail-open

ADR-254 decided that `evidence_for` — run by the self-check tick — would not
fetch a log excerpt, because a scheduler tick must not depend on Loki being up
to produce a diagnosis. That constraint stands. What changes is WHERE the
evidence is gathered: the diagnosis pump, which already tolerates a broken LLM,
now collects a pack per incident **before** the model call, and every source
degrades on its own:

- **A recipe per correlation key** (`evidence_recipes.py`): the catalogue
  queries and the log events worth reading for that incident, keyed by the
  alertname a check mirrors or its check id, so an alert-sourced and a
  self-check-sourced incident share one recipe. Nothing free-form ever reaches
  a backend (ADR-247 pillar 1). A boot assert refuses a registry that leaves a
  check's key without a recipe, names a catalogue query that does not exist,
  or fetches nothing without a written reason; a CI test asserts every alert
  Prometheus actually loads (`alerts-core.yml`, the only rule file in
  `prometheus.yml`) has one, and that every declared log event is emitted
  somewhere in `src/`.
- **Four breakdown queries** join the catalogue: outcomes, provider statuses,
  shaper verdicts and refusal reasons, all grouped increases over the recipe
  window. 25 % said nothing about the two operations behind it; a breakdown
  does.
- **The collector** (`context_collector.py`) renders each query, reads the
  Loki stream of the recipe's service through the constrained LogQL builder,
  filters client-side on the recipe's events and levels (the builder offers
  one event at most, and is not widened), counts lines by `(event, level,
  head)` and keeps a few samples. Every field of a log line goes through a
  **closed allowlist**, a length cap and the PII sanitizer — a register of what
  the model saw is the last place a user's message should land. Lines read,
  samples, distinct counts, series and field lengths are capped by constants.
- **The runtime block** — version, short commit, build date, uptime from a
  stamp taken when `main` imports (`core/process_info.py`) — answers the one
  question three of four diagnoses asked without being able to: "was there a
  recent deployment?"
- **Fail-open by source**: Prometheus unavailable → each query says so with
  its reason; Loki unavailable → the log section says so; a collector that
  raises → `{"status": "unavailable"}` and the diagnosis is still written. A
  tick whose budget is spent reads no telemetry to decide nothing: the pack is
  collected after the budget gate, once per incident whatever the number of
  admin languages.
- **The prompt reads the pack**: the diagnostician is told what the three
  sections are, to read them before saying evidence is missing, and that a
  section marked unavailable is a source it could not read — never silence.
- **What the model saw is stored with what it said** (`diagnosis.context`) and
  rendered to the administrator under the diagnosis ("What the diagnostician
  read"): series as label chips with exact values, log counts with the head of
  the failure, the build and its uptime; a blind source is stated with its
  reason, never drawn as a reassuring zero.

*Rejected: fetching the pack at the self-check tick.* That is what ADR-254
refused, for a reason that still holds: the tick's verdict must not wait on
Loki. The pump is the right host — it already pays an LLM call and already
tolerates its failure.

*Rejected: free-form LogQL from the model.* Unchanged from ADR-247: the
catalogue and the builder are the only producers of query languages.

*Rejected: a minimum sample size on `embedding_failure_rate`.* The check was
right on eight operations, and a floor would have delayed the detection of a
defect that hit 100 % of RAG queries. The denominator becomes visible (the
window is now part of the evidence, the breakdown is in the pack) instead of
becoming one more threshold.

### 4. The runbooks reach production, and their absence is visible

`prepare-prod.ps1` stages `docs/runbooks` next to `docs/knowledge`, pinned by
a Pester test on the bundle. Because the mount stayed empty for weeks with
nothing saying so: the overview publishes `runbooks_available`, the admin
panel states a zero next to the incidents, and the boot validation logs a
WARNING — never a refusal, a diagnosis without its runbook is weaker, not
wrong, and a self-hoster must not be locked out for a missing mount.

### 5. Small repairs on the way

- `evidence_for` omits an empty `detail` (an empty string was quoted back as
  "the detail field is empty") and states the measurement window of a
  Prometheus check.
- The test describing the phantom `recent_errors` key is replaced by the
  real contract of the pack.
- The five diagnostics metrics that had been blind since ADR-247 are wired in
  a "Self-Diagnostics" row of dashboard 16; the coverage baseline shrinks by
  five entries.

## Consequences

- One diagnosis now costs one call per admin language on a prompt roughly
  three times longer (measured ≈ 0.001 $ → ≈ 0.003 $ per call), under the
  unchanged daily cap.
- The self-check tick hosts up to `batch_size` × (queries + 1) bounded HTTP
  reads per pump; each is under the telemetry clients' timeout and circuit
  breaker, so a dead source costs one timeout then nothing. Its duration is
  charted (`diagnostics_self_check_duration_seconds`, now wired).
- A new alert needs a recipe, or CI reds; a recipe naming an event nobody
  emits reds too.
- `diagnosis.context` is a new JSONB key on existing rows' shape; rows older
  than this ADR simply have none, and the panel shows no evidence block for
  them.

## What this ADR does not prove

The end-to-end runtime proof (a real turn regaining its RAG context, a real
incident diagnosed with a pack) is taken after deployment, as recorded in the
implementation plan (`docs/superpowers/plans/2026-09-05-embedding-500-and-diagnosis-evidence.md`);
the local Docker engine was unavailable the day this was written.
