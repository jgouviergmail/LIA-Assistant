# JEV audit — what reached the model, and what came back used (2026-10-25)

Trigger: the owner observed that JEV's categorisations, choices and arbitrations
were rarely usable. This record is the evidence behind the
[ADR-325 amendment of 2026-10-25](../../../architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md):
production and dev telemetry first, then paid measurements on fictional corpora, then
the shipped code path. The vendor documentation was read in full beforehand
(introduction, concepts, primitives, confidence, models, jaggedness, API, SDK and every
cookbook of docs.typesafe.ai, read 2026-10-25).

Everything sent to the provider during this audit was fictional (`*.test` domains). No
mailbox, calendar or conversation of any account was read; the production traces below
were reduced to probabilities and sizes before leaving the host.

## What production showed (read-only, seven days)

| Signal | Source | Finding |
|---|---|---|
| 792 native decisions | Loki, `jev_decision_completed` | 34 timeouts, **all at 2 011 ms** (the then 2 s deadline); after the deadline was raised to 5 s, successes at 3.9-5 s |
| Appointment classification | Prometheus, `jev_decisions_total` | 106 batches with **no** accepted label against 17 with one |
| Email classification | idem | 290 batches with a label, 103 without, 22 timeouts |
| Collection previews | Loki, `jev_collection_qualification_completed` | 66 of 69 operations "uncertain" |
| A retained trace (probabilities only) | debug store | appointments read `personal` at 0.90-0.98, under the 0.95 confidence floor; one 12-event filter state of 40 071 characters split 0.44 / 0.44 on half its items |
| Initiative utility (dev, switch on) | Loki | **40 of 40** `request_too_large`, refused locally before any call |

Eleven usages switched on in dev made no call in seven days; most are path-gated
(pipeline-only consultation, FOR_EACH confirmations, meetings, radio). The collection
previews have no consumer since the intermediate panel was hidden (2026-10-04).

## Root causes

1. **A local request cap the vendor does not have.** The transport refused any body over
   32 000 bytes and any batch over 24 questions. The vendor documents 64k tokens per
   request and 32k per question (state plus one question), with no limit on the number of
   questions. A real calendar turn built an initiative state of 108.6 kB (~29.5k local
   tokens), 83 kB of it the full contracts of 23 adjacent tools.
2. **Acceptance floors chosen where they could not be tested.** On jev-1.14.0 the shipped
   email/appointment questions accept **no wrong label on the three frozen corpora at any
   level from 0.50 to 0.99** (both layouts, both model versions; only one-request-per-item
   at 0.50-0.60 erred). The 0.95 / 0.99 floors bought no measured safety and rejected the
   answers production needed: on a production-shaped corpus the model's first choice was
   phishing for 6 of 6 phishing messages, the 0.99 alert floor kept 2.
3. **Facts the provider asserted never reached the judgment.** The spam criterion cited a
   provider spam label that was never sent (`labelIds` was not in the projected fields);
   the reply-to field was looked up as `replyTo`, a name no provider publishes (the unified
   vocabulary says `reply_to`); a calendar entry's own type (birthday, focus time, working
   location), its video link and its recurrence were dropped.
4. **A fresh connection per decision.** Each decision opened its own HTTP client: DNS, TCP
   and TLS every time, which on the production host includes a ~4 s resolver failover —
   the signature of every timeout above.
5. **Corpora unlike production.** Classification cases are explicit sentences; the
   initiative calibration states were 100-250 bytes while the product builds 23-109 kB.

## Measurements (paid, fictional, `jev-1.14.0` unless stated)

### Classification

Layout (frozen corpora, shipped questions and thresholds): one request per item is **not**
better than the shipped shared batch (coverage 0.812 / 0.885 / 0.833 against 0.875 /
0.906 / 0.889); moving `unknown` last changes nothing measurable. jev-1.13.0 and 1.14.0
agree within one case.

Production-shaped corpus ([`production_shaped_corpus.json`](production_shaped_corpus.json),
40 Google Calendar events and 40 Gmail metadata messages, six languages, labels from the
product's own category definitions, an undecidable purpose labelled `unknown`):

| Configuration | Wrong labels | Coverage | Phishing | Appointments (pers. / prof.) |
|---|---:|---:|---:|---:|
| Shipped (0.95 / 0.99) | 2 | 0.62 | 2 / 6 | 10 / 17, 11 / 17 |
| + provider facts, spam criterion, provider rules, 0.80 / 0.80 | **0** | **0.86** | 5 / 6 | 16 / 17, 14 / 17 |
| Same, through the shipped service path (after the change) | **0** | **0.86** | **6 / 6** | 16 / 17, 14 / 17 |

The only wrong labels left before the rules were commercial or social notifications read
as spam (a promotion, a social-network digest, a travel offer); Gmail had filed each under
`CATEGORY_PROMOTIONS` / `CATEGORY_SOCIAL`. The level rule, fixed before reading the
production-shaped results: the first level with no wrong label on every frozen corpus,
layout and model version is 0.70; one 0.10 step of margin gives 0.80.

Official replays under the shipped policy (`scripts/analysis/jev_classification_replay.py
--live`, proof account, 0.0074 € in all), now the qualified records the guard reads:

| Corpus | Coverage before (1.13, 0.95 / 0.99) | Coverage now (1.14, new policy) | Wrong |
|---|---:|---:|---:|
| Calibration (64) | 0.865 | 0.927 | 0 |
| Holdout (70) | 0.906 | 0.917 | 0 |
| Adversarial (36) | 0.889 | 0.889 | 0 |

Requalified on 2026-10-26, when the spam criterion was found naming three of the four
commercial labels the code rule reads (`CATEGORY_FORUMS` was missing): the question now
names all four, a guard holds it equal to the rule (ADR-284), and the replay cost 0.0074 €
(calibration 0.917 → 0.927, the other two unchanged, no wrong label).

### Collection previews

On the frozen collection corpora the shipped three-way Choice (match / non-match /
unknown — the vendor's citation-check shape) is right; a single relevance Noul per record,
the RAG-cookbook shape, confused "absent" with "contradicts" and took up to 11 wrong
verdicts. The question was kept. The production failure is the absence of a consumer —
and, measured the next day on production-shaped collections, the uncertainty itself:
dated requests could not be decided (see « Every usage on the model it runs » below).

### Initiative utility

The 36 labelled gate cases rebuilt through the product's own state builder (policy, tool
list, results), lean tool list, real runtime: 36 of 36 calls succeed (≤ 23.2 kB). The
probability that something useful remains reads 0.08-0.25 on the empty cases and
0.31-0.92 on the useful ones. At the former 0.11, 2 of 8 calibration and 0 of 7 holdout
empty cases were skipped; at 0.20 (chosen on calibration) 8 of 8 and 6 of 7, no useful
case skipped.

### Transport

Billed against local tokens (201 requests, six languages): billed = 270 + 1.10 × local +
49 per question; the estimate 1.25 × local + 300 + 60 per question was never exceeded by
more than 87 %. A pooled client gained 0-18 ms p50 on the dev workstation (wired); its
target is the production host's per-connection resolver delay, not measurable from dev.

Total spent: 0.079 € — 0.060 € on the instance ledger (surface `jev_audit_bench`) and
0.019 € on the proof account (77 calls through the runtime: the gate cases, the service
path and the official replays) — under the 1 € envelope set for the audit.

## Every usage on the model it runs (2026-10-26)

The owner asked for every usage, not the email path alone. Dev and production run
`jev-1.14.0` since 2026-10-25, while most thresholds were calibrated on 1.13. Each usage
was replayed on 1.14 with its shipped question: on its committed corpora through the
existing tools (`scripts/jev_alignment/compare.py`, `scripts/jev_semantic/run_v2.py`,
`scripts/analysis/jev_lot1_replay.py`, now `--model`-aware), or on fresh corpora kept here
where the 2026-10-11 ones were generated into a scratch directory and never versioned. Rule,
fixed before reading: the first level with no wrong decision on every corpus, one step of
margin, the stricter of a tie. The vendor documentation index was re-checked first
(unchanged; the 61 JavaScript SDK reference pages read too).

### Collection previews

[`collection_corpus.json`](collection_corpus.json): 12 search requests (6 calendar, 6 mail)
over 122 retrieved items re-dated around Wednesday 2026-10-28 09:00 Europe/Paris, built
through the product's own output builders; structured gold derived from the raw fields,
semantic gold by hand.

| Variant | Coverage at 0.80 | Coverage at 0.94 | Wrong at 0.94 |
|---|---:|---:|---:|
| Shipped | 0.521 | 0.252 | 0 |
| Computed day facts, shared batch | 0.840 | 0.580 | 0 |
| Computed day facts, one item per request | 0.622 | 0.521 | 0 |
| **Shipped code after the change** | 0.824 | **0.647** | **0** |

Dated calendar requests at 0.94: 1 → 35 of 51; dated mail: 5 → 13 of 18; undated: 24 → 29
of 50. A relative day needed date arithmetic the question forbids, so every « tomorrow »,
« this week » or « this weekend » ended unknown; the code now states each item's own day in
the person's timezone setting. The three committed collection corpora give the shipped
result at 0.94 (one debatable item, wrong for both). One item per request takes no wrong
verdict but abstains on contrasts the shared batch decides; the shared batch is kept.

### Thresholds re-measured

| Usage | Corpus | Shipped level on 1.14 | Decision |
|---|---|---|---|
| HITL total refusal | [`rejection_corpora.json`](rejection_corpora.json), 26 + 24 replies | 0.99: 4 of 20 refusals, no wrong shortcut at any level | 0.80: 19 of 20 |
| HITL exclusion | `jev_hitl_cases` / `_holdout` | 0.99: 6 of 12 and 5 of 11, no wrong exclusion from 0.80 | 0.90: 10 of 12 and 8 of 11 |
| Meeting template | `jev_meeting_cases` | 0.95: 9 of 19, no wrong template from 0.70 | 0.85: 17 of 19 |
| Consultation | `jev_gate_cases`, `jev_bounded_*` | 0.97: one wrong shortcut (an injection case) on calibration | 0.98: no wrong path on either split |
| Memory reference presence | [`presence_corpus.json`](presence_corpus.json), 52 requests | 0.99: 25 of 26 absences, no false skip at any level | kept |
| Radio verification | `jev_radio_cases` / `_holdout` | margin 0.16: 28 of 30 and 23 of 24, no wrong | kept |
| Parameter kind | `corpus_v2` d5, 66 cases | 98.5 % selective accuracy, no wrong refusal | kept |

The extraction observers are unchanged: shadow by design and off in production; making
them skip an extractor would suppress writes (ADR-325), and no labelled extraction corpus
exists. The HITL reference-scope corpus of 2026-10-11 was never versioned, so the scope
composition was not re-measured; the scope keeps its own 0.80.

Spent in this pass: about 0.089 € (bench 0.024, alignment replays 0.052, parameter kind
0.012, meeting 0.001) on the instance ledger, and 0.0074 € requalifying the classification
records on the proof account; about 0.18 € for the whole audit.

## Limits

- Every corpus is synthetic and labelled by its author; the production-shaped corpus was
  written for this audit and has not been labelled by a second person.
- The computed day facts cover calendar events and mail; tasks, reminders, files and
  tickets state no day yet, so a dated request on them still ends unknown.
- The initiative gate cases are short synthetic results; real turns carry larger
  registries (measured: a 10-event turn is ~30 kB with the lean tool list).
- The latency effect of the pooled client must be read on production after deployment
  (`jev_decision_duration_seconds`, timeout share), not inferred from dev.
- A dev restart during the audit hit the Docker Desktop D: mount stall already recorded
  that morning (a migration process in uninterruptible sleep); unrelated to the change.
