# JEV for semantic typing — measured qualification (2026-10-11)

This document records whether the native decision provider (JEV, [ADR-325](../architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md),
[integration guide](JEV_INTEGRATION.md)) can type values, classify requests into
the domain taxonomy and decide which ontology entities a request needs. It was
measured before any of it entered a plan, under a rule fixed before the first paid
call. The harness is `apps/api/scripts/jev_semantic/`; the evidence files are in
`docs/superpowers/qualification/jev-semantic-2026-10-11/`.

## The five decision points

| Id | Question | Where it would serve | Current mechanism |
|---|---|---|---|
| d1 | What is this resolved value: a person's name, a postal address, a place, a date, or something else? | the typed references (plan Lot B) | none: every resolved value is read as a person's name |
| d2 | Which semantic type of the registry describes this value? | registry checks (plan Lot D) | none |
| d3 | Which domain is the request mainly about, and which domains does it need? | the router | the query analyzer (generative) |
| d4 | Which entities (Contact, Place, CalendarEvent, EmailMessage) must be read first? | planner hints | Contact only, from the personal-reference extractor |
| d5 | Can this value fill this guarded parameter as-is? | the semantic parameter guard | refuse a value equal to any value the turn resolved |

## The rule (fixed before measuring)

A decision point enters the plan when, on the INDEPENDENT corpus, at the threshold
chosen on the CALIBRATION corpus, JEV's confident accuracy beats the current
mechanism (the generative slot where none exists) by at least 3 points — and
reaches 98 % for d1 and d5 — with at most 10 % abstention and a p95 latency under
600 ms. Multi-label decisions transpose it: the decision cut-point is chosen on
calibration, the exact-set accuracy on the independent corpus beats the reference
by 3 points, nothing abstains, p95 under 600 ms. The qualification's ceiling was
5 € (owner approval, 2026-10-11).

Every paid call is pinned to the database configuration of the deployment (the
decision model, key and tariff through `jev_settings.read_configuration`; the
generative slots through the semantic simulation runtime), refused BEFORE it is
sent when its pessimistic upper bound would cross the ceiling, settled in the
instance ledger after it (no account pays for a qualification), and every case's
row is saved as it lands.

## Two versions, and why

**Version 1** asked every question as a Choice through the application's transport
(Choice only). Read against the vendor's documentation afterwards, it departed from
the documented practice in five ways: yes/no and multi-label judgments were
two-option Choices instead of Nouls (one per label); d5 asked the model a POLICY
question ("can it fill this parameter") instead of letting the code keep the
policy; criteria were flat strings without `not_for`/`examples` and without a
no-match option; d3 was split into batches instead of the function-calling layout
(one Choice plus one Noul per domain in one request); and the first-option bias of
Choice was not measured.

**Version 2** follows the documentation (read 2026-10-11): Nouls for yes/no and
multi-label sets, structured criteria with a no-match option, d5 decomposed (the
model judges what the VALUE is, `ACCEPTED_KINDS` in code decides compatibility per
parameter, a direct Noul is measured beside it), d3 in one request, d1 run twice
with the options reversed. The documented request carries Noul questions, which
the application's client does not; the harness sends it through
`scripts/jev_semantic/native.py`.

## Integrity of the measurement

- Version 1's independent splits of d3, d4 and d5 were READ while version 2 was
  designed, so they cannot judge version 2. Three fresh independent corpora
  (`corpus_v2.py`: d3 46 cases, d4 50, d5 66; six languages, French majority)
  were written by three separate agents that read only each decision's published
  vocabulary — never the harness, its corpora, its questions or any result. Their
  labels were reviewed and kept as authored.
- d1 and d2 keep version 1's corpora: d1 because version 1 already passed and
  version 2 only adds the order check; d2 because version 2's design was frozen
  before version 1's d2 independent results were opened.
- Criteria examples were checked against every corpus: none appears in one.
- Disclosed adjustments made after READING the version 2 corpus labels (no result
  had been produced): an event's location accepts an online-meeting link
  (`ACCEPTED_KINDS["event_location"]`, both calendar providers store one there),
  and the `place` kind names an organisation's premises named with their town
  (calibration already held such cases).
- One probe of the documented request (1,155 input tokens, under 0.0001 €) ran
  before the ledger was wired; it is not in the instance ledger.
- The current mechanism of d5 is replayed exactly (it only needs the turn's
  resolved values). The planned typed guard (Lot B) is replayed as an ORACLE —
  perfect typing, read from the case family — so its figure is an upper bound.

## Results

Accuracy is on the independent corpus; `forced` answers every case, `selective`
only the cases at or above the threshold chosen on calibration. Latencies are the
harness's, over one reused connection (see *Limits*).

### Verdicts

| Decision | JEV | Current mechanism | Generative slot | Verdict |
|---|---|---|---|---|
| d1 — what a resolved value is (v1, 91 cases) | 100 % forced, no abstention, p95 531 ms | 24.2 % | 100 % (p95 1 097 ms) | **passes** |
| d1 — options reversed (v2) | 100 % both orders, 100 % agreement | — | — | no order bias |
| d5 — value kind, compatibility in code (v2, 66 fresh cases) | 98.5 %, no abstention, p95 281 ms | 54.5 % | 98.5 % | **passes** |
| d5 — direct "can it fill" Noul (v2) | 87.9 % forced, 95.0 % at 9.1 % abstention | 54.5 % | 95.5 % | fails (98 % floor) |
| d5 — kind and Noul must agree (v2) | 98.3 % at 12.1 % abstention | 54.5 % | — | fails (abstention) |
| d5 — v1 (policy asked of the model) | 98.3 % at 10.8 % abstention | 73.8 % | 95.4 % | fails (abstention) |
| d3 — primary domain (v2, 46 fresh cases) | 94.1 % forced; no calibrated threshold | 100 % (query analyzer) | — | fails |
| d3 — every needed domain (v2) | 78.3 % exact sets | 91.3 % | — | fails |
| d4 — entities to read first (v2, 50 fresh cases) | 86 % exact sets | Contact only | 93.8 % | fails |
| d2 — semantic type of a value (v2) | 98.1 % forced, 75.5 % coverage at the target | — | 99.0 % | fails (no headroom) |

**d5 against the planned guard.** The typed guard of the plan's Lot B, replayed
with PERFECT typing, reaches 62.1 % on the same 66 cases: it can only refuse a
value a producer RESOLVED as a person's name this turn, so a name the person typed
into a location (`person_unresolved`), a person's name mixed with a place, a phone
number or a date in an address slot, or an injected instruction all pass it. The
value-kind decision catches them. Its one miss: « Comment je vais chez Florence ce
soir ? » with `Florence` as the destination — read as the city (confidence 0.98),
where « chez » makes it a person. A homonym typed by the person stays the known
limit.

**What the decomposition shows.** Asked the policy ("can this value fill this
parameter?"), the model scores 87.9 %; asked what the value IS, with the policy in
`ACCEPTED_KINDS`, 98.5 % on the same cases. This is the vendor's own advice — keep
known rules in code — measured.

**d4, one label.** Not a decision point on its own, so not judged by the rule: for
Contact, JEV's Noul reaches precision 0.94 / recall 1.00 where the current
personal-reference extraction reaches 0.44 / 0.57 on the same 50 cases.

### Cost

| Decision | JEV per decision | Generative per decision |
|---|---|---|
| d1 | 0.00002 € | 0.00005 € |
| d5 (v2) | 0.00004 € | 0.00005 € |
| d3 (v2, 32 questions) | 0.00024 € | 0.00036 € (v1) |

Total spent: 0.58 € (version 1) + 0.25 € (version 2), under the 5 € ceiling.

## Realignment of the shipped questions (same day)

The same documented practice was applied to the questions LIA already ships, each
measured on its usage's own calibration and holdout corpora (`scripts/jev_alignment/`).
Every state was CAPTURED from the product function that builds it; three variants
were asked on it, twice: the shipped question at its shipped threshold, the same
question with its options reversed, and an aligned candidate (Noul for a
condition, structured criteria, conservative option first, backticked paths, the
consultation state reduced to the fields its instruction reads). Rule, fixed
before any call: the candidate's threshold is chosen on calibration without more
wrong shortcuts than the shipped question there; on the holdout it replaces the
shipped question only if it takes no more wrong shortcuts AND covers at least as
many cases. A shortcut is the branch that skips or replaces the existing path.

| Usage | Shipped (holdout coverage, wrong) | Aligned candidate | Decision |
|---|---|---|---|
| Initiative utility | 7.1 %, 0 wrong — and 0 % on the production-shape states | Noul « something useful remains », skip at p ≤ 0.11: 85.7 %, 0 wrong; 92.3 % on the production-shape states, 0 wrong | **adopted** |
| Consultation (both selectors) | 73.5 %, 0 wrong | structured, `other` first, request fields only, threshold 0.97: 88.2 %, 0 wrong, 20 % fewer input tokens | **adopted** |
| Radio verification | 77.1 %, 0 wrong | one Noul per line, decided at p ≤ 0.16 or ≥ 0.84: 93.8 %, 0 wrong | **adopted** |
| Collection qualification | 91.7 %, 0 wrong | structured, `unknown` first, threshold 0.94: 100 %, 0 wrong (24 judgments only) | **adopted** |
| Memory reference presence | 75.0 %, 0 wrong | Noul: 62.5 %, 0 wrong | kept |
| HITL total refusal | 66.7 %, 0 wrong | Noul: 16.7 %, 0 wrong | kept |
| HITL exclusion | 55.6 %, 0 wrong | 86.1 %, **5 wrong** | kept |

**Order bias.** Reversing the options changed 0 to 3.8 % of the answers; one
reversed HITL exclusion took a wrong shortcut. The bias exists and is small at the
shipped thresholds.

**Proof through the runtime** (Docker dev, proof account): the four adopted usages
ran unpatched down to the native call — initiative empty (p 0.08, evaluator
skipped) and useful (p 0.79), a radio script fully decided, a listing selected and
a constrained request left to the planner, a collection judged as labelled — each
recorded once under its own usage in `token_usage_logs` (0.000344 € for the
six calls), in 253 to 410 ms.

The alignment cost 0.10 €.

## Shipped: the usage `parameter_kind`

Decision d5 passed and ships as an ADR-325 usage, off by default
(`semantic/jev_value_kind.py`, ADR-120 amendment 2026-10-11). The question is the
measured version 2 wording, byte for byte (`jev_parameter_kind_question.txt`).
The CODE's rule differs from the harness's in three ways decided for the
product. Compatibility is keyed by the parameter's semantic type rather than by
the corpus's parameter families, so a physical address accepts an online-meeting
link everywhere (an event's location may be one) and a locality accepts a postal
address. And a location refuses only a value positively identified as another
kind: `other` is accepted there, because a calendar's location is free text
(« Visio », a room name) and no case of either corpus measured such a value — the
harness's rule would have refused it unmeasured.

Replayed on the measured answers, the shipped rule decides 58 of the 66
independent cases and 62 of the 65 calibration cases, refusing no compatible value
in either. On the independent cases it lets 8 of the 30 incompatible values
through, all of which pass today: four names mixed with a place and two injected
instructions (judged `other`), the « chez Florence » homonym above, and a meeting
link given as a route destination. Refusing `other` would have caught six more on
those cases (64 of 66) at the price of that unmeasured risk. The judgment runs only
after the deterministic guard let the call through, so it can add refusals and
never lift one.

## Limits

- **Latency.** The harness reuses one HTTP connection; the application's runtime
  opens a new client — a new TLS connection — for every decision (`jev_runtime.py`).
  Six calls through the runtime took 253 to 410 ms (the slowest the first, cold):
  close to the harness, but a sample of six, not a percentile.
- **Every corpus is synthetic** and written by a person or an agent, never read
  from an account. The independent corpora were written without sight of the
  questions, but by authors who knew the decision's vocabulary.
- **The planned guard's figure is an upper bound** (perfect typing, read from the
  case family), so the gap to the value-kind decision is a lower bound.
- **Small samples**: 46 to 91 independent cases per decision; one case is 1.1 to
  2.2 points. Two repetitions gave identical answers for d5 (stability 1.0).
- **Request capacity.** Structured questions are repeated per question. Measured
  against the local 32 000-byte bound: the radio question shrank (1 326 bytes
  against 1 515), so a request carries 22 checked lines instead of 19; the
  collection question grew (1 034 against 858), so a batch of 500-byte items holds
  20 instead of 23 — 160 items over the 8 batches, above the 100-item preview.
- **A locality was replaced after measuring.** The incident's town is on the
  repository's denylist of personal information; in the 5 corpus cases that named
  it, it was replaced by a neutral town after the runs. The evidence files were
  measured on the original wording.
