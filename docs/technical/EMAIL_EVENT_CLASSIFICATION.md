# Native JEV email and appointment annotations

The independently switchable `email_classification` and `event_classification`
usages are registered in [the native JEV registry](../../apps/api/src/domains/llm_config/jev_registry.py).
Both default off. This is native decisioning, with ordinary platform quotas,
actual token accounting and paid failure accounting; there is no generative
fallback. See [the integration guide](JEV_INTEGRATION.md).

Emails carry a category (professional, personal, spam or phishing/scam) and an
independent single priority (normal, urgent or critical). Appointments carry a
professional/personal category. Unknown values produce no badge; normal produces
no priority badge. The closed [annotation types](../../apps/api/src/core/content_classification.py)
carry evidence scope and validity. The same accepted annotations reach the UI
and assistant; prompts explicitly forbid treating a missing badge as safety or
an advisory phishing label as proven fraud.
Accepted normal priority still reaches the model; its quiet UI treatment does
not turn a defined qualification into an unknown one.

## Publication, evidence and cache boundaries

Qualification follows source authorization, selection, detail shaping and email
formatting. It reads only the fields that survived those boundaries, never a
hidden MIME body, attachment or URL. Snippet, metadata, digest and partial body
remain named scopes. The qualification can abstain independently on category
and priority. It never archives, moves, labels, deletes or acts on a message.

The normal tool publication seam covers pipeline, ReAct and their voice callers.
Briefing and relationship cards qualify their selected rows; the latter use the
typed shared port wired at startup rather than importing agent orchestration.
Condition polling and other background contextual reads do not create independent
paid display qualification. Historical HTML/bookmarks keep captured labels and
do not reclassify on replay. Live DTO/cache readers remove expired labels while
preserving source facts.

Cache identity includes owner, actual account binding, provider/container/item,
revision/occurrence, evidence, model, prompt/policy, native probability-contract
revision and time context. Redis stores
only closed annotations. Overlapping workers coalesce under bounded claims;
cache failure, cancellation, native errors, quota/price/key absence and oversized
evidence preserve the source result without inventing a label. There is no new
LangGraph state field. Operation bounds and confidence policies belong to
[constants](../../apps/api/src/core/constants.py), [batches](../../apps/api/src/domains/agents/services/qualification/batches.py)
and [policy](../../apps/api/src/domains/agents/services/qualification/policy.py).

The phishing badge has a stable red ground and readable text. Only its outer
halo pulses briefly; reduced motion is static. Its wall-clock anchor prevents
archive/remount attention replay. UI strings exist in every supported locale.

## DEV qualification status — 2026-10-18

The [frozen fictional corpora](../../apps/api/tests/fixtures/jev_classification_cases.json)
and [disjoint execution holdout](../../apps/api/tests/fixtures/jev_classification_holdout.json)
cover six languages, ambiguous observations, legitimate banking/security/training
negatives, malicious solicitations and independent priorities. They were authored
together: this is a bounded regression experiment, not population accuracy.
The scorer rejects wrong accepted labels and insufficient per-class coverage;
all-unknown cannot pass. Hashes are pinned by
[the corpus guard](../../apps/api/tests/unit/domains/agents/services/test_classification_corpus.py).

The first paid calibration abstained excessively on priorities. Clarifying the
priority question, without lowering confidence thresholds, passed calibration.
The policy was then frozen. Holdout execution and one unchanged protocol replay
both stopped on native `probability_sum` invalid responses. Charges were retained
and no malformed batch was published. **The holdout was not qualified; the
campaign left both new usages off.** No model/key/setting was changed and no real mailbox or
calendar was read. The total measured platform spend was about EUR 0.008417,
within the authorized cumulative budget.

The [DEV replay command](../../scripts/analysis/jev_classification_replay.py)
defaults dry, requires an active accounting user for live calls, reserves budget,
creates a new report exclusively and checkpoints actual bills. `--previous-report`
carries cumulative cost; there are no automatic paid retries. Reports and their
policy hashes are preserved in [the qualification record](../superpowers/qualification/email-event-2026-10-18/README.md).
Do not enable these usages on the strength of mocked transport tests or the
calibration result; fresh independent qualification is required after any later
policy change.

## Numerical protocol correction — 2026-10-19

The [root-cause report](../superpowers/qualification/jev-probability-sum-2026-10-19/README.md)
reproduces a received cent-rounded distribution summing to `0.99`, which the
official HTTP contract permits as an approximate sum. Transport and publication
now share precision-aware validation and conservative concentration. Raw values,
business thresholds and prompts are unchanged. Cached annotations include the
numerical contract revision in their policy identity.

The complete frozen replay now finishes without a native protocol failure. Its
semantic coverage gate still fails for some classes; the report keeps that limit
explicit. The DEV switches were enabled administratively after the initial
campaign and remain unchanged by this fix. Enabling a switch does not certify
semantic quality.
