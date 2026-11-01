# ADR-367 — A shown item designated by what it is is resolved by code, and asked about when several fit

**Status**: Accepted, 2026-10-30. Amended 2026-10-31 (below).
**Date**: 2026-10-30

**Amends**:
[ADR-287](ADR-287-Email-Content-First-Detail-Levels-Digests-And-Neutral-Message.md) (an e-mail's `from`/`to` carry the
sender's NAME on every provider), [ADR-344](ADR-344-Mailbox-Drafts-Kept-Freely-Sent-After-One-Confirmation.md)
(a reply draft's register line names the message it answers),
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) (a label built at claim time
names the item an id designates), [ADR-248](ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md) invariant 3 (the
loop reads the item the turn designates, as the planner does).

## Context

Production, 2026-10-29, the owner's account, pipeline mode. After « my last 5 received e-mails »,
the request « reply to <first name>'s e-mail that all is well … » saved a reply draft in a Gmail
thread that was NOT among the five e-mails just listed (nothing was sent; the draft was deleted by
hand). The chain, proven from the logs and measured on the provider:

1. The query analyzer could only say a shown item was designated by position, by pointing or by
   a pronoun. Designated by WHO it came from, the request read as no reference at all
   (`has_reference=false`), so nothing tied it to the list on screen.
2. The planner searched the mailbox anew — `from:<first name>`, one result — and took `[0]`.
   Gmail's `from:` does not fold accents: the unaccented spelling and the accented one return
   DISJOINT sets (measured), so the « newest » result was another person's message.
3. The register line under the answer said « a reply draft was saved » — the call named the
   message by its provider id, so nobody could see WHICH message was answered.

The systemic review found the same failure class elsewhere:
- the context list the ordinal path reads (`ToolContextManager`) was REPLACED by any intermediate
  lookup and dated turn 0 (no tool config carried the turn), and every parallel step wrote its
  `node_name` into the ONE metadata dict the wave shared;
- the « last list domain » fallback keyed on tool-name prefixes no unified tool carries;
- the ReAct loop never received the turn's resolved items (invariant 3 violated, even for « the
  first one »);
- the entity-disambiguation HITL was dead in four places (a producer never loaded, no web card,
  every answer read as a cancellation, no reader of the choice);
- Outlook encoded accented names as RFC 2047 words, Apple kept the address only, CalDAV dropped
  the organiser — a description could not find a sender the other provider named.

## Decision

**1. The analyzer says HOW an item is designated; code decides WHICH.** `ContextReferenceOutput`
gains `reference_type="descriptive"`, a `descriptor` (the words that single the item out, in the
person's own spelling) and a `selection` (`one`, or `latest` only when asked). The analyzer is
shown the items of the last answers — one bounded line each, data never instructions — and never
chooses among them (`services/descriptive_reference.py`, `query_analyzer_prompt.txt`). The branch
runs only when the analyzer says a shown item is designated at all (`has_reference`), the rule the
measurement ran.

**2. The words are matched by ONE pure matcher** (`context/descriptor_match.py`): folded words
(`fold_name`), EVERY word carried by the item (a word nobody carries is never dropped — « Marc
Dupont » must not find « Marc Dubois »), a word of six letters or more also heading a compound,
a Chinese run as a substring, identity fields (`reference_fields`) before content fields, an item
one of whose fields IS the description preferred. What was shown is read from the checkpointed
registry, stamped by its turn in both execution modes, within `ENTITY_RESOLUTION_MAX_TURN_AGE`
turns — never from the context list — and only in a turn the person follows
(`effects/gate.turn_follows_the_conversation`: not a routine, a ticket or a relayed call).

**3. One fit is resolved, several are ASKED about, none is a new lookup.** The
`reference_disambiguation` node runs between the router and the planner (both modes; the recorded
route stays the planning node). Its question is a template in six languages: the descriptor, then
numbered options described by what tells them apart (`ContextTypeDefinition.candidate_fields` —
sender, subject, date), then how to answer. The answer is read WITHOUT a model
(`context/choice_answer.py`): a position of the person's language (« 2 », « le deuxième »,
« the last one », « 第二个 »), the words that tell ONE option apart, « none of them » (a new lookup),
a refusal (the workboard's six-language lexicon, now `shared/answer_lexicon.py`). An answer naming
no single option is asked about ONCE more, then the turn ends with nothing done — never guessed.
A single fit is acted upon and NAMED (§7).

**4. A click carries its position** (`HitlDecisionRequest.selected_index`, bounded by
`ENTITY_RESOLUTION_MAX_CANDIDATES_CAP`; `services/orchestration/structured_decision.py`, one
builder per interrupt kind). The visible message a click sends names the position (« Le numéro 2 »),
never the option's label: a label quotes a third party, and the person's bubble renders Markdown
(ADR-316). The web card (`HitlActionCard`, kind `entity_disambiguation`) lists the options as
buttons of a named group; a busy option keeps its focus (`aria-disabled` + guard).

**5. The loop reads what the planner reads** (`nodes/react_context.build_designated_items_block`):
the planner's own rendering of the designated item (`ResolvedContext.to_llm_context`), under a
directive from `react_context_lines.txt`, quoted as external content, read from the state the SMS
policy guarded — only when an item is designated.

**6. The context list keeps what was shown.** A step another step depends on is a means: its
results never replace the shown list (`FIELD_INTERMEDIATE_STEP`, LIST read as CURRENT) — unless a
FOR_EACH iterates over it, the list being then what the turn shows (« my next three events, and
the weather for each »; `ExecutionPlan.consumed_step_ids`). Each step
runs under a metadata dict of its own carrying the real turn. The « last list domain » is the last
list a step no other step consumed SHOWED (two items or more in the turn's registry), never a
tool-name prefix.

**7. The register names the target.** Labels are built at claim time, before the chain seals the
row; whoever runs the tools publishes the turn's registry for the length of the call
(`effects/label_targets.py`), and a builder names the item an id designates by the words it was
shown with — `create_mailbox_reply_draft_tool_named`, a task completed by id named by its title.

**8. Provider parity.** One `name_addr` renders a mailbox for Graph, IMAP and outgoing mail
(names decoded and kept); the CalDAV organiser is kept; a guard builds every provider's payload
with the REAL normaliser and builder and asserts every declared identity, content and candidate
field carries text.

**9. The dead disambiguation path is deleted**: `EntityResolutionService`,
`resolve_entity_for_action`, the `hitl_dispatch` branch, three state keys,
`ENTITY_RESOLUTION_AUTO_THRESHOLD`. `ENTITY_RESOLUTION_ENABLED` became the kill switch it was
documented to be.

## Measured before shipping

A bench of 6 languages × 19 cases (descriptive, ordinal, demonstrative, new searches, bulk
operations, creations) ran the analyzer with the candidate prompt on four model families:
three reached 98–100 % end-to-end with 0 % harmful outcomes; the fourth's misses were
pre-existing timeouts (40 of 114 on the baseline prompt, 30 on the candidate). All 252
descriptive outputs carried the right domain; all 114 ordinal/demonstrative/pronoun outputs
carried a domain (the « last list » fallback never served). Spend ≈ 0.67 USD.

## Consequences

- One more question when several shown items fit — the owner's arbitration (2026-10-30):
  asking costs a turn, a wrong target costs an action nobody wanted.
- The analyzer reads at most `ENTITY_RESOLUTION_SHOWN_ITEMS_MAX` lines (≈25 tokens each) after a
  listing; the loop's block exists only on a turn that designates an item.
- `context_descriptive_reference_total{outcome}` and `context_disambiguation_answers_total{outcome}`
  are drawn on dashboard 07.

## What this does NOT solve

- A new lookup still depends on the provider's search: Gmail's `from:` does not fold accents,
  so an unaccented name can find another person's message — or none. When it finds one, the
  action names it (§7); when it finds several, the person is asked (amendment, §C).
- A timed-out analyzer call records no spend — a separate finding of the bench.
- What « shown » means is what the answer DECLARED it presented (`<relevant_ids>`): an answer
  that omits the declaration outside the card modes records its whole turn registry.

## Amendment 2026-10-31 — one record of what was shown, and a choice before any guess

Four gaps the first version wrote down, closed; each measured on Docker dev with the proof
account and real models (≈ 0.29 USD).

**A. Every act on an item named by an id names it.** `labels._NAMED_VARIANTS` gives a `_named`
wording to a forward draft (the message and its recipient), an edited draft (its subject as
shown), trashed drafts (named only when EVERY one is known — naming the known half of a
deletion would read as the whole) and a confirmed reply or forward (the subject the draft copied,
else the message the turn showed). Six languages, backend and web.

**B. One record of what was shown, read by both paths.** The response declares the records its
answer presents; `context/shown_items.py` keeps that declaration per turn (`shown_items`, the
cards' order where cards are drawn, the answer's order otherwise, the turns
`ENTITY_RESOLUTION_MAX_TURN_AGE` reaches). A description reads every item shown; an ordinal reads
the newest list of its domain — one item opened alone after a list holding it is that list's
item (« open the first », then « and the second? »), one no list holds is a list of its own. The
context list serves only a list beyond that reach. Measured: an item a turn fetched but its
answer left out is no candidate; « the second » counted in the order shown, not the registry's.
The planner was then seen to apply « the second » to a NEW lookup of the domain while holding the
resolved item: its rule now says a position counts in the list the user saw, and
`orchestration/designation_repair.py` binds a plan that ignores the designated item and acts on a
position of exactly one fresh lookup of its domain to that item (a plan naming the item, reading
two lookups or iterating one is left as written).

**C. A lookup an act takes the first result of asks when it finds several.** « Reply to Marc's
email » with nothing shown is planned as a lookup and an act on `[0]`
(`orchestration/choice_points.py` finds it; a list the plan iterates, passes whole or reads at
another position is the person's subject, never narrowed). Before any act runs, the orchestrator
runs those lookups (`orchestration/pre_execution.py`, shared with the FOR_EACH confirmation) and,
when one found several, the reference-disambiguation node asks « I found several items that
could be the one you mean »; the answer narrows the lookup to the chosen item and the plan
resumes on it, nothing run twice (`nodes/plan_choice.py`, `plan_choice` keyed by plan and turn).
« None of them » or a refusal run the plan WITHOUT the act and what depends on it, said through
the not-run directive as « not chosen » — never the plan-rejection directive, whose « nothing was
read » would be false. A lookup the planner capped at one result is widened first, within the
tool's published bound, unless words give the item's POSITION (« Marc's latest email »,
`REQUEST_POSITION_WORDS`, six languages) — they keep that cap, and never silence a question on
several found: « last » is also in « last week ». Measured on four model families: the planner rule alone
held on three, the fourth capped « reply to Marc's email » at one three times in four — the code
decides. The ReAct loop has the same rule in its prompt (it asked, never picked, on a fresh
lookup; it acted on the chosen item 3 times in 3 once told `<DesignatedItems>` is a choice made).

**D. The answer is read in every language, and a new request is never lost.** A Chinese free
answer is read for the longest stretch of it only some options carry (`_cjk_carried`). Asked
twice and still naming no option, the message is the person's new request
(`approval_decision._read_disambiguation` → `NEW_REQUEST`, the question dropped,
`drop_replaced_question`). Running it found a defect older than this ADR: LangGraph RESUMES the
last checkpoint when a run's `run_id` equals the checkpoint's — its stream re-entry rule — even
for a new input, and the chat reuses the run id of the question it answers; the stale-question
path of 2026-01-11 had the same flaw. A normal turn is now declared fresh
(`turn_input.fresh_run_config`, pinned on a real graph).

## Verification

- `apps/api/tests/unit/domains/agents/context/` (`test_descriptor_match.py`, `test_choice_answer.py`,
  `test_reference_fields_carried.py`, `test_auto_save_current_mode.py`),
  `services/test_descriptive_reference.py`, `nodes/test_reference_disambiguation_node.py`,
  `nodes/test_react_designated_items.py`, `nodes/test_shown_list_domain.py`,
  `orchestration/test_step_config_isolation.py`, `effects/test_effect_label_targets.py`,
  `services/orchestration/test_structured_decision.py`, `test_parse_approval_decision.py`.
- Web: `hitl-payload.test.ts`, `HitlActionCard.test.tsx`, `useChat.test.ts`; e2e
  `smoke/chat-hitl-card.spec.ts` (choice by keyboard at 1280 and 390 px, axe).
- Amendment: `context/test_shown_items.py`, `orchestration/test_choice_points.py`,
  `orchestration/test_designation_repair.py`, `orchestration/test_pre_execution.py`,
  `nodes/test_plan_choice.py`,
  `services/orchestration/test_new_input_never_resumes.py`,
  `services/orchestration/test_drop_replaced_question.py`, the Chinese cases of
  `context/test_choice_answer.py`, `test_response_display_modes.py` (the record).

## Implementation references

`apps/api/src/domains/agents/services/descriptive_reference.py`,
`apps/api/src/domains/agents/context/descriptor_match.py`, `context/choice_answer.py`,
`apps/api/src/domains/agents/nodes/reference_disambiguation_node.py`,
`apps/api/src/domains/agents/services/orchestration/structured_decision.py`,
`apps/api/src/domains/agents/effects/label_targets.py`,
`apps/api/src/domains/agents/nodes/react_context.py`,
`apps/api/src/domains/shared/answer_lexicon.py`, `apps/api/src/infrastructure/email/recipients.py`,
`apps/web/src/lib/hitl-payload.ts`, `apps/web/src/components/chat/HitlActionCard.tsx`;
amendment: `apps/api/src/domains/agents/context/shown_items.py`,
`apps/api/src/domains/agents/orchestration/choice_points.py`,
`apps/api/src/domains/agents/orchestration/designation_repair.py`,
`apps/api/src/domains/agents/orchestration/pre_execution.py`,
`apps/api/src/domains/agents/nodes/plan_choice.py`,
`apps/api/src/domains/agents/services/reference_fallbacks.py`,
`apps/api/src/domains/agents/services/orchestration/turn_input.py`.
