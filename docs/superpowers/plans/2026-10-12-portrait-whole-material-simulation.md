# Portrait simulation — whole material, real brief (2026-10-12)

Measured on the dev stack with `task journals:portrait:measure` (`apps/api/scripts/journals/measure_portrait.py`),
on the PROOF account only, seeded with the invented persona of `apps/api/scripts/journals/portrait_corpus.json`
(60 memories, 20 interests, a rhythm profile and 2 recurring habits, 45 journal entries across every
eligibility class, 3 relationship debriefs, 4 open loops, 4 workboard tickets, 3 routines, 3 reminders,
3 kept answers). The consolidation slot is `deepseek-flash` (never Anthropic). Each run is the real
`consolidate_journals_for_user(manual=True)`: one generation call, one review call, the settlement.

## What the baseline (the code before this lot) published on that material

| Run | Status | Proposed | Cut by budget before review | Rejected by review | Published | Full | Brief | Sources cited | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|
| sources-blind 1 (harness defect: no source installed) | success | 5 | 0 | 3 | 2 | 388 chars / 88 tokens | 1 claim, 175 chars | journal | 0.026 € | 248 s |
| sources-blind 2 | success | 6 | 0 | 0 | 6 | 871 chars / 198 tokens | 2 claims, 189 chars | journal | 0.015 € | 123 s |
| with the four sources, 1 | **failed: server timeout at 300 s** | — | — | — | 0 | — | — | — | 0.016 € | 300 s |
| with the four sources, 2 | success | 9 | 2 | 3 | 4 | 619 chars / 139 tokens | 2 claims, 286 chars | journal | 0.021 € | 195 s |

What the baseline handed the prompt in run « with the four sources, 2 »: memories 40 of 62 (the item cap),
interests 20 of 20, habits 2, relationship debriefs 0 of 3 (the bodies the harness seeded lacked the
version stamp, so the reader read them as absent — fixed for the candidate runs; on the owner's
production account the three debriefs were all « omitted as incomplete » by the 200-character clamp).

Two findings the baseline makes plain, beyond the owner's two complaints:

1. **The model never cites a source item**: four runs, every support is a journal entry, with 40
   memories and 20 interests offered. The prompt's rule said « Only current L1/L2/L3 rules … may
   support a claim », so the sources were material the model could read but never use as proof.
2. **The 300-second server bound is already reached** on a 10-30 k-character prompt with a thinking
   model: one baseline run of four died on it, its generation call paid.

## What the candidate published — first attempt, with the review as it was

Three runs, the nine sources read whole (62 memories, 20 interests, 2 habits, 3 debriefs, 5 open
loops, 4 tickets, 3 routines, 3 reminders, 3 kept answers — every `used`, nothing cut). The three
runs ended `invalid_output` on ONE structural rule: « provisional syntheses require an uncertainty
facet » — one claim citing an L2 rule of medium confidence under another facet refused the whole
batch, three paid generations for nothing (0.042 €). The facet is metadata and the review already
judges the words (`uncertainty_preserved`), so the rule became a REPAIR (ADR-184), and a claim whose
reference cannot be resolved in the snapshot is now DROPPED and counted rather than fatal to the
batch — the maintenance actions keep their all-or-nothing contract.

## What the candidate published — second attempt (repair and drop in place, review unchanged)

| Run | Status | Proposed | Dropped (unprovable) | Rejected by review | Approved | Cut by the 300-token budget | Published | Full | Brief | Sources cited | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | success | 14 | 0 | 11 | 3 | 0 | 3 | 751 chars / 166 tokens | **none** (every brief claim rejected) | interests, journal, memories | 0.021 € | 180 s |
| 2 | success | 14 | 0 | 7 | 7 | 2 | 5 (3 full + 2 brief) | 1 080 chars / 239 tokens | 2 sentences, 294 chars / 66 tokens | journal, memories | 0.030 € | 254 s |
| 3 | success | 14 | 0 | 12 | 2 | 0 | 2 | 480 chars / 100 tokens | **none** | journal, memories | 0.023 € | 186 s |

What run 2 published for the invented persona:

> **Full.** Chez cette personne, l'équité et la preuve forment le socle du jugement : un planning se lit à sa répartition entre les personnes, une affirmation à sa mesure vérifiée. Avant de relayer un chiffre à l'équipe, il faut pouvoir dire d'où il vient et l'avoir contrôlé soi-même. J'en tire une règle pour moi : traiter chaque recommandation comme une affirmation à sourcer, et chaque arbitrage de planning comme une question de justice.
>
> La communication attendue est directe et sans détour : le verdict technique énoncé sans adoucissement, la source citée, aucune digression sur du contexte non demandé. Les mots de transition comme « bon » ou « bref » ferment le sujet précédent, et quand une question se termine par « enfin surtout », c'est la seconde partie qu'il faut traiter d'abord.
>
> L'atelier de restauration est un ancrage personnel : le travail du bois occupe les matinées de week-end, la finition au tampon est préférée aux vernis modernes malgré sa lenteur, et la pratique s'accompagne d'une collection de vieux outils de menuisier et d'écoutes de jazz des années cinquante.
>
> **Brief.** Cette personne juge d'abord à l'équité et à la mesure : chiffre sourcé avant explication, planning jugé sur sa répartition.
>
> Interagir court et direct : chiffres d'abord, verdict sans adoucissement, deux options au plus, et la seconde partie d'une question « enfin surtout » traitée en premier.

Three facts this attempt establishes:

1. **The input goal is met**: every record is read whole, and the model now cites memories and
   interests beside the journal (the old rule told it only journal rules could support a claim).
2. **The semantic review is the bottleneck**: 14 claims proposed per run, 7 to 12 rejected — on
   `supported` and `scope_preserved`, the two criteria written for strict ENTAILMENT. A synthesis
   that generalises over several passages is exactly what entailment refuses, so the richer the
   material, the more the review rejects. The brief dies with it in two runs of three.
3. **The full budget now binds in the good runs**: run 2 approved four full paragraphs and 300
   tokens held three.

## What the candidate published — third attempt (the review calibrated for grounded synthesis)

`supported` now reads « every assertion is GROUNDED: stated by a linked passage, or a fair
generalisation of several of them read together; fail a contradiction or an assertion no passage
states and no group of them shows », the invention guards kept (a job title alone, a single
example, sentiment labels); `scope_preserved` keeps conditions and domain but accepts a class whose
cases are each shown by a linked passage. The brief guidance says a brief claim restates only what
the full claims establish and cites the same items.

| Run | Status | Proposed | Dropped (unprovable) | Rejected by review | Approved | Cut by the 300-token budget | Published | Full | Brief | Sources cited | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | success | 15 | 0 | 2 (`supported`) | 13 | 7 | 6 (4 full + 2 brief) | 1 342 chars / 294 tokens | 2 sentences, 206 chars / 46 tokens | journal, memories, open loops, workboard | 0.020 € | 156 s |
| 2 | success | 15 | 0 | 2 (`supported`, `scope_preserved`) | 13 | 6 | 7 (6 full + 1 brief) | 1 263 chars / 280 tokens | 1 sentence, 107 chars / 26 tokens | journal, memories, workboard | 0.030 € | 259 s |
| 3 | **stale** (the settle refused: a source moved during the run) | — | — | — | — | — | 0 | — | — | — | 0.019 € | 146 s |

Run 3's refusal is the designed one, not a defect of this lot: the dev scheduler's proactive
INTEREST sweep served the proof account at 13:41 (the seeded interests triggered a real
notification, 0.0008 €) and wrote on it between the claim and the settle; `current_snapshot` saw
the source state move and the paid generation was discarded. It is the same mechanism that makes
the owner's portrait go stale after every conversation (spec D4).

What run 1 published for the invented persona:

> **Full.** Mon portrait de cette personne commence par ses critères de jugement : un planning se juge d'abord à son équité, une affirmation à sa mesure. Elle attend qu'on lui présente les faits mesurés avant la lecture qu'on en fait, qu'on nomme la source d'un chiffre dans la même phrase, et elle vérifie elle-même une mesure avant de la répéter à son équipe. C'est une posture de fond, pas une préférence de circonstance.
>
> Sa période actuelle est tournée vers la rotation des astreintes de novembre, qu'il veut équitable et présentée en deux options, vers la réduction des tickets ouverts depuis longtemps, et vers la présentation trimestrielle des indicateurs de son équipe de support.
>
> Dans nos échanges, il récompense la sobriété : un verdict énoncé sans adoucissement, une réponse courte et sans digression, la source citée dans la phrase qui porte le chiffre. Une demande de résumé doit tenir en trois points, et mes détours de contexte le font décrocher.
>
> Son rythme est fait de créneaux qu'il protège : une heure sans interruption le matin pour les dossiers difficiles, les premières heures de certains matins pour courir, la lecture du soir à son enfant, un après-midi hebdomadaire consacré à l'accompagner à la natation, le dimanche après-midi sans écran, et les matins de week-end à l'atelier. Je ne propose rien qui tombe dans ces fenêtres.
>
> **Brief.** Quelqu'un qui juge un planning à son équité et une affirmation à sa mesure.
>
> En ce moment, il prépare une rotation d'astreintes équitable en deux options et la présentation trimestrielle de ses indicateurs.

And run 2's six paragraphs read the person's relation to proof, fairness, two-option decisions,
direct exchange, protected family slots and the workshop; its brief: « Elle mène de front une
équipe de support et son atelier de bois, en gardant intacts ses créneaux familiaux. »

(The corpus is written without a stated gender; the model alternates « il » and « elle ». A real
account carries `full_name`; the prompt does not state a gender today — a point for the owner.)

## The one question left for the owner: the full budget (spec D3)

The review now approves eleven to thirteen claims of fifteen; the 300-token publication budget
holds four to six paragraphs and omits six or seven approved ones whole. Measured paragraph
weight: 62 to 73 proxy tokens each (335 characters on average), so:

| `JOURNAL_PORTRAIT_FULL_MAX_TOKENS` | Paragraphs published | Approximate size |
|---|---|---|
| 300 (today) | 4 to 6 | 1 300 chars |
| 400 (ADR-292's measured overshoot of the former prose) | 5 to 6 | 1 700 chars |
| 600 | 8 to 9 | 2 600 chars |
| 800 | every approved paragraph | 3 400 chars |

The full portrait is injected into every response and planner prompt (`format="full"`), the brief
into eleven secondary flows; the brief is unaffected (26 to 66 of its 70 tokens used).

## Spend

| Phase | Runs | Cost |
|---|---|---|
| Baseline (two sources-blind, two with the four sources) | 4 | 0.078 € |
| Candidate, first attempt (three refused for one facet label) | 3 | 0.043 € |
| Candidate, strict review | 3 | 0.074 € |
| Candidate, calibrated review (one stale) | 3 | 0.069 € |
| Proactive interest sweep triggered by the seeded interests | 1 | 0.001 € |
| **Total** | 14 | **0.265 €** of the 0.50 € announced |

Everything seeded was removed (`--teardown`); the proof account is back to its two memories and
one open loop, its habit profile recomputed by the next habits pass.
