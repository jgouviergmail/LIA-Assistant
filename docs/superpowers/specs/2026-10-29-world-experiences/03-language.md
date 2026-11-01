# Workstream 3 — Language immersion quarter

[Master plan](README.md) · [Contracts](contracts.md) ·
[Decisions](decisions.md) · [Launch prompt](prompts/03-language.md)

**Status:** proposed; written and Live required.
**Dependencies:** qualified training contracts from theatre, not theatre content
or its feature switch. **Blocking choices:** D01, D03–D07, D09–D11.

## Job and useful result

“Let me accomplish something in another language at a level I can handle,
understand what blocked me, and practise that difficulty again.”

Example: ask for a change to a booking, clarify an ambiguous reply, then revisit
the difficult phrase in another scene. Success is communicating the intended
request; perfectly reproducing a model sentence is not the goal.

## Proposed first-release scope

- A small authored set of practical scenes: a shop, a journey, a social
  introduction or a work interaction. Places represent situations and objectives.
- Explicit target language, preferred explanation language and user-selected
  starting difficulty. UI language and learning language remain separate.
- Written and true Live practice using the shared isolated training lifecycle.
- Two correction behaviors: uninterrupted immersion with a later debrief, or
  opt-in coaching at meaningful pauses. Avoid interrupting every sentence.
- Hints, reformulation and a brief debrief with selected examples.
- Explicit saving of practice targets and a deterministic revisit schedule.
  The scheduler need not buy LLM work to decide that something is due.
- Optional entry from a saved goal or project; no automatic real-world bookings,
  purchases or messages.

Deferred under D01: formal proficiency certification, broad course authoring,
a public ranking, automatic peer matching and pronunciation grading without
qualified audio evidence. Human peer practice may be added through explicit
consent and its own privacy contract; peer translation does not silently run.

## Pedagogical distinctions

The language rubric extends the training contract with communicative objective,
target language, acceptable variants, selected correction mode and practice
targets. It must recognize valid alternative phrasing and separate a failure to
communicate from a harmless accent or stylistic choice.

A difficulty recommendation is a suggestion the user can override. Text
transcripts can support vocabulary and phrasing feedback; they do not prove
pronunciation or acoustic fluency. Only offer audio-specific feedback when the
actual provider pathway supplies adequate evidence and that rubric is qualified.

Saved learning data stays in an explicit pedagogical store. “Practised ordering
a meal” is a learning event, not evidence that the user travelled, bought a meal
or has the preferences spoken by a fictional character.

## Reuse and adaptations

Reuse theatre's scenario identity/version, phases, isolation, paid attempts,
checkpoint recovery, transcript policy, explicit export and provider qualification
machinery. Add the language-specific rubric and progress model, not a second
actor/session engine. Unsupported target languages or provider features must be
published by server availability rather than guessed from the UI locale list.

Native World text translation is a separate consenting paid action; it is not a
free pedagogical correction service. If exposed during peer practice, retain its
existing payer and attempt contract.

A saved progress view can be deterministic and cached. Fresh personalized
feedback is an explicit accounted call. A reminder should use a native scheduling
mechanism only after user opt-in; project/session creation does not subscribe a
person to notifications.

## Acceptance criteria

| ID | Observable pass condition |
|---|---|
| LNG-01 | A person completes a practical communicative task in both written and qualified Live modes, receiving feedback linked to the stated objective. |
| LNG-02 | The same training lifecycle and billing/isolation contract serves theatre and language; disabling theatre does not disable language. |
| LNG-03 | Target language, explanation language and UI locale can differ; available options match actual supported policy. |
| LNG-04 | Immersion mode does not interrupt each turn with corrections; coached mode provides requested help without losing the exercise checkpoint. |
| LNG-05 | A fixed evaluation corpus includes valid paraphrases, partial success, ambiguity and no usable input; feedback distinguishes those outcomes and does not invent evidence. |
| LNG-06 | No pronunciation score is produced from a text-only transcript. Unsupported audio assessment is clearly unavailable. |
| LNG-07 | Each new actor/correction/debrief call has owner-attributed platform accounting and native decision provenance; personal Live bills remain separate. |
| LNG-08 | Revisit scheduling and saved progress views generate no hidden LLM calls; retries and provider failures obey native uncertain-outcome rules. |
| LNG-09 | A fictional scenario statement does not become personal memory or trigger a real action; saved goals remain explicitly pedagogical and owner-scoped. |
| LNG-10 | Saved learning targets can be inspected, exported and deleted; expiring transcripts and account deletion fence late writes. |
| LNG-11 | Quota exhaustion preserves review/stop controls; input methods, keyboard/touch and reduced-motion behavior retain the common training guarantees. |
| LNG-12 | Any offered peer interaction uses explicit consent and native visibility; it does not grant access to private proficiency records or subsidize translation without payer consent. |

## Validation and useful signals

Extend the theatre corpus with language-specific evidence and representative
difficulty levels. Qualify each offered target-language/provider pairing to the
degree required by the promised behavior; publish the supported pilot subset.
Real speaking comfort, comprehension and turn-taking need human and device
evaluation, not only snapshots or LLM self-grading.

Measure task accomplishment, voluntary revisits and whether users can reuse a
practice target later. Do not infer learning from minutes connected, number of
tokens or a streak. The required corpus, supported pilot languages and thresholds
are deliverables of this workstream, to be agreed before release.
