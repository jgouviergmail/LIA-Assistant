# Fictional email/event native qualification — 2026-10-18

Follow-up: [the numerical protocol fix and complete replay](../jev-probability-sum-2026-10-19/README.md)
resolved `probability_sum` and exposed a separate semantic coverage limit.
The [subsequent semantic qualification](../jev-classification-2026-10-19/README.md)
passes the fixed calibration, validation and fresh adversarial corpora without
lowering thresholds. The historical reports below remain unchanged and retain
their original failure outcomes.

Platform-paid DEV calls were explicitly authorized under a cumulative budget.
Only original fictional evidence was submitted; no real mailbox/calendar read,
credential/configuration write or activation was performed. The ordinary native
runtime charged every attempt, including invalid responses, to the authorized
account. Reports contain fictional observations' answers and accounting counters,
not vendor keys or real mailbox contents.

| Report | Interpretation |
|---|---|
| [Initial calibration](calibration-initial.json) | No wrong accepted label, insufficient priority coverage |
| [Final calibration](calibration-final.json) | Clarified priority prompt; unchanged thresholds; scorer passes |
| [Frozen holdout](holdout-initial.json) | Native probability-sum rejection interrupts execution; scorer fails |
| [Unchanged protocol replay](holdout-protocol-replay.json) | Same frozen policy hash; another native probability-sum rejection; scorer fails |

The two holdout attempts are both disclosed; the second does not erase the first.
No prompt, threshold or expected answer changed after opening the holdout. The
final report carries all preceding spend. Its total is the cumulative experiment
cost, not the final attempt alone. The campaign left both classification usages
disabled. The later DEV activation observed without any agent setting write is
recorded in the [delivery report](../2026-10-18-evolutions-delivery.md); it does not
change this failed qualification result.

Reproduce using [the dry-by-default DEV command](../../../../scripts/analysis/jev_classification_replay.py)
and its pinned [corpus/scorer](../../../../apps/api/tests/fixtures/classification_corpus.py).
Use new report paths, carry prior spend and obtain a new bounded authorization
for a later experiment. This record establishes fail-closed behavior and paid
failure accounting; it does **not** establish deployment readiness or broad model
accuracy. See [the current contract and limitations](../../../technical/EMAIL_EVENT_CLASSIFICATION.md).
