# JEV — remaining lots

Status: implementation and cold reviews complete, inline on `codex/jev-lot-1`.
The owner authorized continuing all remaining lots on 2026-09-29. The three lots
are staged for review; no commit, push or production deployment was performed.
Lot 1 is preserved. Each deployment still requires the owner's dev acceptance.

## Lot 2 — collection qualification and radio verification

- Extend the native transport to bounded independent Choice questions in one call,
  preserving actual usage on malformed responses and one accounting entry per call.
- Qualify email, event, task and document results independently, with a hot switch
  per collection. Preserve ownership, source limits, incomplete evidence and exact
  rules. Distinguish matches, non-matches and unknowns. No record mutation.
- Make qualified results available before the final synthesis; the original data
  remain available to that synthesis, and uncertain/excluded candidates remain
  inspectable. A provider failure retains the existing path.
- Qualify the radio verifier on complete scripts, retaining deterministic checks,
  the existing evidence contract and fallback. An unqualified shortcut cannot be
  presented as a validated replacement.
- Extend the existing admin, pricing, accounting, diagnostics and six locales.

## Lot 3 — bounded consultation paths and initiative

- Select among known read-only paths without bypassing access, input validation,
  the English query analysis, state bookkeeping or the final response contract.
- Evaluate the complete utility of initiative (actions, suggestions and chips),
  retaining the existing path on uncertainty and every mutation approval.
- Provide independent switches, debug decisions, accounting and fallback.

## Evidence required for each lot

Write behavioral tests before production changes and observe their failures.
Exercise HTTP faults, malformed distributions, counters, cancellation, OFF,
concurrent configuration, owner isolation, stale state and checkpoint round-trips.
Use real disposable PostgreSQL/Redis when testing persistence semantics, hermetic
browser journeys for visible behavior, and measured native plus fallback latency.
Paid replays use only synthetic annotated data and the authorized provider.

After each lot, inventory and read every changed file, trace each caller and
consumer independently of its tests, reproduce findings, correct them, then run
the relevant repository gates and shrink-only ratchets before starting the next.
Record measurements and limits here; no assertion of semantic perfection follows
from a confidence threshold or a small passing corpus.

## Lot 2 measured qualification (2026-09-29)

The replay uses only labelled synthetic objects and scripts; no mailbox or production
record was sent to TypeSafe. Reproducible entry points:
[collection replay](../../../apps/api/scripts/measure_jev_collections.py),
[native radio replay](../../../apps/api/scripts/measure_jev_radio.py), and
[configured radio baseline](../../../apps/api/scripts/measure_jev_radio_baseline.py).
Run from `apps/api` with `PYTHONPATH=.` and the normal application settings; native
scripts read a hidden console key. The baseline runs explicitly in the dev container,
reads only configuration and calls its configured verifier (gpt-6-luna on this run).
Both paths incur actual provider charges. No measurement writes an account ledger.

| Corpus | Native accepted | Wrong accepted | Existing correct | Hybrid correct |
| --- | ---: | ---: | ---: | ---: |
| Radio calibration: 30 scripts, twice | 49/60 | 0 | 56/60 | 60/60 |
| Independent radio holdout: 24 longer stories, twice | 35/48 | 0 | 47/48 | 47/48 |
| Collections: 43 objects, twice | 56/86 | 0 | Not compared | Not substituted |

Radio uses a calibrated concentration threshold of 0.95. Holdout stories contain
five sourced lines plus transitions; the calibration spans six languages, the
independent holdout English and French. One holdout answer was structurally invalid
and fell back. The original measurement did not preserve its reported usage, so
the saved native token totals are a lower bound; the runtime always preserves
valid counters on invalid answers and the replay script now does too.

Radio native median: 216 ms calibration, 217 ms holdout. Existing verifier medians:
1,700 ms and 2,081 ms. Composing the separately measured native and fallback calls
gives median 223/229 ms and mean 553/752 ms, against baseline means 1,863/2,181 ms.
These are NOT measured end-to-end radio durations. The unit integration separately
exercises the actual deterministic editor with native verdicts; audio generation
and playback are outside this measurement. A finite synthetic corpus cannot prove
zero semantic loss in production; the new usages remain OFF for owner acceptance.

Collection median: 221 ms, 30 abstentions out of 86. The corpus covers email reply
requests, event/task/file relevance, generated files, nested constraints, missing
evidence and hostile source instructions. Classification uses the shipped full
projection and prompt. It changes only an ephemeral, inspectable preview, not the
final selection. This adds cost for earlier readable information; no total-token
saving or faster final answer is claimed.

## Lot 2 cold adversarial review

Reviewed the transport/envelope/usage paths, cancellation ownership, configuration
and concurrent switches, every preview producer/consumer and reducer lifecycle,
radio caller/editor, debug encryption/permissions/batch display, localized UI,
replay scripts and their test oracles. No source record is written by these usages.
Queries and provider bodies are absent from logs and metric labels. The number of
database reads depends on configured usages, never the number of candidate objects.
Independent collection HTTP calls own separate configuration sessions and join the
same lock-protected tracker; no AsyncSession is shared between tasks.

Findings reproduced and corrected: cancellation while waiting for the accounting
lock could lose known spend; a missing stream writer could interrupt an otherwise
normal answer; a channel without a browser would pay for an invisible preview;
activating the master switch incorrectly required inactive slots to be ready;
one broken registry item could suppress other valid previews. Oversized inputs,
uncertainty, wrong answer identities, late SSE events and unsafe HTML are covered.

Validation so far: 2,312 scoped backend tests; 291 frontend regressions; 19 real
PostgreSQL/Redis tests (including six OFF/ON/OFF usages); six browser journeys with
keyboard, mobile/desktop overflow and axe checks. Backend lint/type checking and
CC/cycle/i18n/marker gates pass. Final aggregate gates and measured shrink-only
ratchets are recorded at delivery, after the remaining lot. No production deploy.

## Lot 3 measured qualification (2026-09-29)

[The gate replay](../../../apps/api/scripts/measure_jev_gates.py) exercises the
shipped consultation selector and initiative prompt. The native mode reads a
hidden key; `--baseline-initiative` runs in the configured dev container with a
read-only configuration transaction. Access filtering is tested independently;
the replay supplies eligible paths, not a live account or mailbox. The two corpora
contain English synthetic queries/contexts and are not a multilingual end-to-end
evaluation of the upstream translator.

Consultation calibration: 25 requests, five accepted with no wrong accepted path.
The first prompt abstained on all queries; its unnecessarily literal default-list
wording was corrected. A lower threshold admitted a count-constrained query, so
the shipped threshold stays at 0.99. The independent holdout contains 24 new
requests run twice: 10/48 accepted, no wrong accepted path, native median 205 ms.
The remaining requests retain the entire generative planner. This proves bounded
call avoidance, not a measured saving on the full conversation duration.

Initiative calibration contains 19 contexts, including useful write suggestions
and follow-up chips without tool calls. Its independently calibrated threshold is
0.85. The independent holdout has 17 new contexts run twice: 8/34 empty decisions,
no useful labelled output suppressed, native median 219 ms. The actual dev model
(`deepseek-flash`) also produced no useful output in all eight skipped cases.
Comparing matching cases and composing separately measured calls gives mean
3,121 ms versus 3,327 ms (about 6% improvement), median 2,787 versus 3,159 ms.
The modest improvement includes JEV overhead on every fallback. These figures
describe this initiative corpus and are not end-to-end chat measurements.

## Lot 3 cold adversarial review

Reviewed both new callers, complete prompts, fixed tool contracts, catalogue and
operator exclusions, the standard plan validator/executor, initiative suggestions
and chips, per-turn reset, cancellation/accounting, every registry/type/settings
consumer, all six translations and the eight-switch browser journey. Read paths
validate against the actual executable tool schemas. No new checkpoint field or
destructive execution path is introduced. The initiative's existing turn reset
clears its iteration, suggestions and follow-ups before another conversation turn.

Findings corrected: low-confidence upstream query analysis could reach a shortcut;
an invalid JSON state containing NaN escaped the safe transport failure contract;
new decision slots were absent from the shared LLMType vocabulary. Regression
tests reproduce these cases. A final cancellation drill also reproduced a known
bill being lost if closing the HTTP client failed or was cancelled. Accounting
now completes before that awaited cleanup, still exactly once; both failure modes
have regression tests. The full frontend coverage gate also required real
stream lifecycle cases for successive collections and incomplete/late events;
these were added without lowering thresholds. The document audit deliberately
requires staging newly linked files, as a clean clone must contain them.

The new optional shortcuts remain OFF. Empirical concentration is not a proof of
truth; dev acceptance must evaluate real user scenarios before each deployment.

## Final delivery validation

All implementation work and the planned automated checks are complete. No known
blocking finding remains from the lot reviews. The following results come from
the final files, including the HTTP-close accounting correction:

| Gate | Result |
| --- | --- |
| Full backend unit coverage task | 34,237 passed, 27 skipped; 79.05% coverage |
| Full frontend coverage task | 9,712 passed in 787 files; all scoped thresholds pass |
| JEV PostgreSQL/Redis integration | 30 passed, including all eight OFF/ON/OFF usages |
| JEV browser journeys | Six passed: mobile/desktop previews, eight switches, English/French diagnostics, keyboard and axe |
| Backend / frontend types and lint | Passed, including browser test types |
| Documentation, i18n, hygiene, lockfiles, CI parity | Passed |
| Complexity, cycles, MyPy debt, observability | Passed; no baseline increase |
| Marker coverage | 36,855 collected; no new orphan outside CI jobs |
| Deployment / installer hermetic gates | Passed, including 157 PowerShell tests and 24 Compose scenarios |

The components of `ci:fast` were executed separately. The complete service and
security matrix of `task ci`, a production image build and real user end-to-end
provider journeys were not run for this delivery. Native benchmarks are real
paid HTTP calls over synthetic data; browser API responses and external HTTP in
integration tests are controlled fixtures. These scopes are intentionally distinct.

Backend coverage now enforces 77%, raised from 76% with more than two points of
measured margin. Frontend coverage is 82.78/77.82/80.49/83.64% for statements,
branches, functions and lines; its existing floors remain because no axis earns
another integer step with the required margin. Reducer and SSE scoped floors stay
at 100%. The file-size ratchet was recalculated and its 45 caps are unchanged.
Platform-dependent/flag-gated skips remain visible; no test was disabled to pass.

The first final browser pass hit the dev server's cold page-load deadline at
390px. The same test and timeout passed once the page was compiled (4.6 seconds),
as did the 1280px journey. No timeout or assertion was relaxed. Screenshots of the
320px administration controls and the provisional results were visually inspected.

A final read-only dev probe reports eight configured and ready usages. The
TypeSafe key and global/meeting switches are already present and active; those
settings were preserved. All seven newly added usages remain OFF. API, PostgreSQL
and Redis are healthy; the dev web service is running. The operator can now use
the [dev acceptance guide](../../technical/JEV_INTEGRATION.md) to compare each
usage independently before its production deployment.
