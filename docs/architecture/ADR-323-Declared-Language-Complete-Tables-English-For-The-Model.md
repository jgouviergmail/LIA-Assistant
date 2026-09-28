# ADR-323 — One declared language, complete tables, and English for the model

**Status**: accepted — 2026-09-25 (owner request: « Sortir vers l'i18n le français encore écrit en dur dans le Python », scope chosen: the language defaults, the user-visible strings and the model-facing text together)
**Amends**: [ADR-015](ADR-015-ConnectorTool-Base-Class-Pattern.md) (its unused hook), [ADR-023](ADR-023-Error-Handling-Strategy.md) (SSE error messages), [ADR-024](ADR-024-i18n-Architecture.md) (i18n architecture), [ADR-036](ADR-036-Personality-System-Architecture.md) (the default personality), [ADR-256](ADR-256-React-Budget-Conservation-And-Declared-Tool-Safety.md) (tool payloads in technical English), [ADR-284](ADR-284-Prompt-States-What-The-Code-Enforces.md) (prose never lives in a `.py`), [ADR-312](ADR-312-A-Broadcast-Says-Who-It-Was-Addressed-To.md) (broadcasts)

## Context

CLAUDE.md has long said « never inline French (or any language) in Python,
including fallbacks, parameter defaults, and LLM scaffolding ». The rule had no
instrument. Every figure of this Context was measured on the last release
before the change (4f19469b): the three censuses a guard now enforces (the
language defaults, the tables keyed by language, the gettext catalogs) with
that guard's own code, the others — the bound tool schemas and the agent
descriptions — with a census run for this change and not committed. A fourth
guard's baseline (the prompts told a language) is stated with its decision;
the Consequences' figures describe what the change leaves.

**A language nobody declared.** 670 sites in 195 files decided a language on
their own: 456 parameters defaulting to a fixed language, 55 `x or <fixed>`,
44 `.get(key, <fixed>)` (a fixed language: a code literal, or a name holding the
instance default), 55 fields, constants, pinned entries, local assignments or
entries under a language-named key (`_DEFAULT = "en"` in six data modules,
`locale = settings.default_language` in three tools, two constants pinned to
the French entry of a table, and — legitimate then as now — the
`DEFAULT_LANGUAGE` setting with its own constant, two constants naming the
language the prompt files are written in and the pricing sheet's key set), 16
conditional fallbacks, 6 `getattr` fallbacks, 3 call arguments, 34 other reads
of the instance default (`TABLE.get(lang, TABLE[DEFAULT_LANGUAGE])` in the i18n
tables, a `(settings.default_language, "en")` fallback chain among them) and 1
tuple returning it. Each one writes that language to everybody who is not passed
explicitly, and nothing fails — a German reader simply reads French.

**Tables keyed on the wrong code.** 835 dict literals were keyed by language, 790
of them on the six canonical codes. 28 were keyed on `zh`, the frontend's code:
the Telegram bot's messages and approval buttons (15 tables) were read with the
canonical `zh-CN` and a French fallback, so every Chinese account read the bot in
French; the 13 others held only because a private mapper (`split("-")[0]`,
telephony's `_iso`, the interests' `normalize_language_code`) cut the code first —
each one a second authority on the spelling. Fifteen « SKOS » label tables carried
`en` and `fr` only, two provider tables no Chinese at all. Broadcasts assumed
their text was written in French (a module constant), whatever the administrator
wrote.

**Catalogs nobody checked.** `_()` answers an unknown msgid with the msgid itself,
so an untranslated sentence goes out in English and fails nothing. The code named
112 msgids; 21 were translated in no catalog, 14 more — the whole e-mail
verification and password-reset e-mails — in French alone (German, Spanish,
Italian and Chinese readers received them in English), every catalog carried 76
entries nothing read, and the French, German, Spanish and Chinese e-mails
addressed their reader formally (vous, Sie, usted, 您) while the application says
tu, du, tú, 你 (the Italian ones already said tu).

**French — or English — for everyone.** The connector-disabled and
new-registration e-mails, the password-policy violations of a 422, the
memory-category catalogue, the reference resolver's hints, the deactivation
e-mail's missing reason (« Non spécifiée », a French value under a translated
label) and the unknown-date placeholder of the date formatter were French
whatever the reader's language; the failure message an administrator gets after
deactivating an account was written in the language of the account acted upon.
The 429, 413 and 500 bodies of the middleware stack — which the web client shows
to the person — were English for everyone. The e-mails assembled the greeting and
every `label: value` line with English grammar, and inserted the name a person
typed at registration raw into the HTML sent to the administrator. The Telegram
bot answered a voice message too long to transcribe with « I could not
understand you » and a chat blocked after too many code attempts with « invalid
code » — the two sentences written for those cases were sent by nothing — and
its refusals to a person it knows (busy, account inactive, a link that failed)
spoke French whatever the instance's default — its message table defaulted to
French. The administrator's auto-translation of a
personality required a text in the instance default's language and answered a
500 without one.

**French for the model.** Tool messages and directive lines, the three markers of
the conversation history, five agents' context block, the rejected plan's
notice, a six-language inline copy of the default personality in the HITL
module (which had drifted from its versioned file), and French in the
descriptions of 27 tools as LangChain binds them (54 spans, measured
with `convert_to_openai_tool`, the exact schema the model receives — instructions
and example utterances alike) — one language of six presented to the model as THE
way people speak. French place names and addresses in examples stay: they are
data. Three more families were French without reaching the model: the sixteen
agent descriptions and `peer_agent`'s example utterances (the planner's export
carries an agent's name and tools, never its description), a planner output schema that turned out to be dead code, and
the nine French semantic keywords of the health manifests (embedding inputs the
English-pivoted query is compared against).

## Decision

1. **A sentence is written in the DECLARED language.** `core.i18n` holds a context
   variable declared where the person becomes known — the request's
   `Accept-Language` (`RequestLanguageMiddleware`, HTTP and WebSocket; an entry
   with `q=0` is a refusal, a weight outside [0, 1] is malformed, the highest
   weight wins), the authenticated account's
   own language (`_authenticate`, and `get_optional_session` when it recognises
   the account), the person an out-of-turn run, a proactive sweep, a Telegram
   message or a voice lookup serves (`language_scope`). `resolve_language(x)`
   returns an explicit `x` normalised, else the declared language, else the
   instance's `DEFAULT_LANGUAGE` read at call time; a KNOWN person's stored
   language is read through `normalize_language` — an empty one is the instance
   default, never the requester's. No parameter, field or constant defaults to a
   language, and the instance default is read by the resolver and by the
   readers the guard declares, each with its reason (guard
   `test_no_language_default_guard.py`, eleven shapes — defaults and factories,
   as a value or inside an `Annotated`, a column's DDL default, keyword
   arguments in snake or camel case (`language_hint`, `languageCode`),
   constants named after a language, table entries pinned at any depth, a
   `.get("fr")` included, any other read of the instance default and a fallback
   chain mixing a fixed language with a value —, each allowance stating how many
   sites it covers; widened by the fourth, fifth and sixth reviews — every
   operand of an `or`, a code in any case, a constant or a local holding the
   instance default however it is spelled, a pin anywhere in a constant's
   value, a module-level `Annotated` alias, `PrivateAttr`/`ContextVar`/`Depends`
   defaults, a subscript target or a dict entry under a language-named key — it
   measures 670 sites in 195 files on 4f19469b, forty-nine more than the first
   four versions saw).
   `DEFAULT_LANGUAGE` and
   every entry of `SUPPORTED_LANGUAGES` are canonicalised at boot (`zh` →
   `zh-CN`), a value naming no supported language refuses to start, and so does a
   default the instance does not offer. `_()` accepts any spelling and normalises
   it. A code bound for a PROVIDER keeps an explicit value verbatim and resolves
   only its absence (`language or resolve_language()` — `zh-TW` is not `zh-CN`),
   then is mapped at the client boundary (Wikipedia edition, Brave `search_lang`,
   OpenWeatherMap `lang`), because a provider speaks codes of its own — and a
   Wikipedia edition must be ONE subdomain label, since a model writes it and it
   names the host (anything else reads the declared language's edition). The
   text a WEATHER or PLACE provider shows on the person's card follows the person
   (a Wikipedia article keeps its edition's language): the weather tools and the
   place search publish no language parameter — the place search never forwarded
   the one it published, the weather tools read theirs only when the person's
   preferences could not be read and overrode it otherwise, and the weather
   tool's own example taught the model to pass `ja` for Tokyo.
2. **A table keyed by language holds the six canonical codes** — `fr`, `en`, `es`,
   `de`, `it`, `zh-CN`, never `zh` (guard `test_language_table_completeness_guard.py`,
   no exception: the one code map it first declared now derives from the
   `Language` literal instead of restating it). The fifteen `en`/`fr`
   « SKOS » label tables were read by no code: deleted with their field, not
   completed.
3. **The gettext catalogs hold exactly what the code names, translated.** Every
   `_()` call names its msgid literally; each of the six `.po`, the template and
   the compiled `.mo` hold exactly the named msgids, every translation non-empty,
   never marked fuzzy, with its msgid's placeholders, the Chinese one addressing
   the reader as 你, and no sentence reaching gettext outside the census — a
   `def _` or `class _`, a module's `._` or a translator lookup read uncalled or
   through `getattr` — every `*gettext` name the `gettext` module defines, read
   from the module itself —, a lookup imported from `gettext` included (guard
   `test_gettext_catalog_guard.py`). ONE tool keeps them equal to the code,
   `apps/api/scripts/i18n/sync_catalogs.py`, whose census the guard imports and
   whose languages are the application's own table — a language added there gets
   its catalog created, with its plural rule, which `PLURAL_FORMS` must list
   (a missing rule stops the run): it keeps a kept entry
   whole
   (comments and flags; an obsolete `#~` entry is never read back), dates a
   catalog only when its entries change — or when a translation edited by hand
   differs from what was last compiled —, and replaces the pybabel Makefile —
   whose `i18n-init` knew five languages —, its Babel configuration and two stale
   scripts. The catalogs were rebuilt entry by entry in the application's
   register, with French typography (a no-break space before `:` `?` `!`),
   Chinese full-width punctuation, and each language's own marks around a quoted
   value: « X » in French (no-break spaces inside), „X“ in German, «X» in Spanish
   and Italian, “X” in Chinese (most Chinese entries of the `core/i18n_*` tables
   write 「X」, a second convention left as found). The backend's own tables moved
   to the application's register with them: lines addressing the reader as 您
   in `apps/api/src` went from 77 to 2 (the greeting of a call to a third
   party, and of the call verifying a number the person declared — whoever
   answers is not known yet), single-line German entries in Sie/Ihr from 56 to
   2 (both the third person), and the French tables no longer say vous to their reader. The
   `Language` literal is THE declaration of the supported languages:
   `SUPPORTED_LANGUAGES` and the base codes derive from it (`core.i18n_types`
   imports nothing from `src`, so no import order can matter), `LANGUAGE_NAMES`
   and `LANGUAGE_TO_LOCALE` are checked against it at import — a
   `RuntimeError`, which `python -O` keeps —, and the SSE error messages'
   private copy of the literal is gone.
4. **An e-mail's grammar belongs to its language.** The greeting is one msgid
   carrying the name (« Hola, Ana: », « Ana，你好！ »); a label joins its value
   through the reader's punctuation (decision 8); every value a person wrote is
   escaped in the HTML part. The two French-only e-mails speak
   their reader's language; the administrator's notification speaks the
   administrator's.
5. **What a person reads is theirs, what the acting administrator reads is the
   administrator's**: the deactivation e-mail follows the account's language, and
   a deactivation states its reason (checked on the whole request — a field
   validator never ran on an omitted field — and refused in the administrator's
   language) — and so does disabling a connector type for the whole instance;
   the connector e-mail prints no reason line when none was given; the
   failure returned to the administrator follows the declared language, and so
   does an auto-translation's refusal — which starts from a text an administrator
   WROTE (named or not, a machine translation is never a source) and reports the
   source it used. The readable account archive frames the person's words in
   the account's language — its section headings and who spoke
   (`core/i18n_account_export.py`), beside the registers already translated.
   Password violations, the
   memory-category catalogue, the middleware's 429, 413 and 500 bodies, the date
   formatter's placeholders and the resolver's hints follow the declared language;
   the hints name the keywords the resolver ACCEPTS in that language
   (`test_resolver_hint_messages.py` checks each against `KEYWORD_MAPS`). A
   payload carries a TYPE, never a sentence written for the reader: a binary
   Drive file is named by the card that renders it. The Telegram bot sends the
   two sentences written for its two refusals, and reads the person with the
   binding, so every refusal to someone it knows speaks their language; a failed
   read of either is answered, in the declared language, never dropped. A
   deactivated account is read too (`include_inactive`) and TOLD its account is
   deactivated, in its own language — a link code never binds one —, and so is
   a binding its owner switched off (the settings section that switches it back
   on is named, never the link hint); its approval buttons read the binding and
   the person the same way and never resume either; the person is the account
   ROW, so the turn carries the account's journal and psyche choices (the
   profile it used to read carried neither: every Telegram turn ran with both
   off); a person the bot does not know yet is answered in the language their
   Telegram client declares (`from.language_code`); and the reply to a link
   leaves once its session has closed (ADR-304), as do the connector-disabled
   e-mails once the revocation is committed.
6. **What only the model reads is technical English or a versioned prompt**
   (ADR-256, ADR-284): tool messages written in French and directive lines,
   history markers, tool and parameter descriptions, manifest examples and
   semantic keywords — and, in the route tools, the messages telling the model
   how to call them again, which `_()` used to translate. The five
   agents' context block is ONE prompt, `agent_context_domain_instructions`,
   rendered for the agent's registry domain; the rejected plan's notice is
   `response_plan_rejection_notice` (the system directive
   `response_directive_plan_rejection` injected beside it is unchanged); the
   default personality is its versioned
   file and nothing else — read by `default_personality_prompt()` outside the
   agents domain and by `load_prompt` inside it (the personalities domain imports
   the agents one, so the accessor cannot be imported back) — and the HITL
   module's inline copy is gone, the HITL prompts carrying the informal register
   themselves. A language a model is told is its NAME (`get_language_name`): a
   census of every prompt the code formats found sixteen told a code (the
   semantic validator, the compaction, the draft critique, three response
   directives, the skill runner, the initiative, the journal's extraction and
   consolidation, the relationship debrief, the reminder, the meetings'
   synthesis and template selection, and the briefing's greeting and
   synthesis), and a guard keeps it (`test_language_name_to_model_guard.py`: a
   language-named keyword of a `.format` call or of any template call
   (`.partial`, `.format_messages`…) or a key splatted into one, a
   `{…language}` placeholder a `.replace` fills, an f-string interpolating a
   language-named value — a constant-key subscript included — right after a
   language instruction (`Respond in`, `Translate to`…) — four of the sixteen
   were f-strings — and a language-named key of a mapping handed to a template
   or a model (`prompt_vars=`, `.invoke`, `.format_map`, a `%` template)
   receive `get_language_name(...)` or a name holding one; re-run on 4f19469b,
   it flags 24 sites — the sixteen prompts (the validator's line twice), two
   that held no code, and the Wikipedia EDITION codes of five tool messages,
   declared). A guard keeps an `Annotated` out of a union — `Optional` and
   `Union` spellings, unions nested in one another, aliases of `Annotated` or of
   a union holding one, an alias of an alias, an alias defined in a module-level
   block, aliases imported from another module (relatively or not, re-exports
   included) or read through it (`types.Lang`), and `*args`/`**kwargs`
   (`test_annotated_metadata_guard.py`). The three guards that read a language
   NAME — the language-default, locale-normalisation and language-name-to-model
   guards — share ONE reading (`tests/_language_names.py`: snake, camel or kebab
   case, a `_code`/`_codes`/`_hint`/`_tag` suffix, plural). The code's own documentation is English:
   the French prose and illustrative examples of the backend's docstrings and
   comments were translated; what stays French is data or evidence — French-locale
   output samples, the French lexicons a parser reads, and dated quotes of what a
   person or a model actually wrote, which a translation would falsify.
7. **Broadcasts store the language they are translated from**
   (`admin_broadcasts.source_language`, NOT NULL, migration `343c834a3a07`) —
   the sending administrator's account language, the one this change can know
   (a text written in another language is a gap named below); existing rows
   backfilled `fr`, the only value the constant ever produced, a backfill
   proven on PostgreSQL by `test_broadcast_source_language_db.py`.
8. **A label and its value are joined by the reader's punctuation**, read
   through ONE door, `label_separator(language)` (`core/i18n_drafts.py`, the
   drafts' own separator): a French colon takes a no-break space before it, a
   Chinese one is full-width. Written in the code, a `": "` published English
   punctuation in six languages and a `" : "` French punctuation — both ways on
   the cards (contact, event, file, reminder, route, task, weather, the
   air-quality and pollen rows), in the FOR_EACH and destructive confirmation
   dialogs, in the minutes' header and the meeting notification's transcript
   head, in an interest notification's sources line, on the HITL item rows (the
   FOR_EACH previews and the draft batch), in a routine's push title, a repaired
   minutes line and the readable account export; the Chinese draft summaries
   wrote an ASCII colon on 15 rows (a table check now), and a streamed HITL text
   re-spaced every no-break space it carried (one token stream,
   `text_tokens`; one one-line fold for every HITL and draft preview,
   `core.text_clip.one_line` — a tool call's arguments, a program's values,
   through `clip_data`, which folds every space, spells out what nobody sees,
   one marker per run, and cuts inside a token —, and one word-boundary
   clip, `clip_on_word`). The
   e-mails' msgid of their own is retired for the door. A
   guard reads every DECLARED surface — f-strings, concatenations, `%` and
   `.format` templates, `.join`, `re.sub`, a compiled pattern's `.sub` and
   `str.replace` alike (`test_label_separator_guard.py`;
   a tool's raw argument names, an MCP server's identifier, the minutes'
   model-facing transcript and an interest search query declared). One surface
   is left, and named: `html_to_text` flattens a definition list with « : » for
   every reader, byte for byte like the browser's projection
   (`apps/web/src/lib/html-plain-text.ts`) under one shared corpus — both sides
   change together or not at all (a proposal).

## Consequences

- A German, Spanish, Italian or Chinese account receives its e-mails, its bot
  messages, its password-policy refusals, its other refusals and its category
  names in its language (a request-validation 422 still wraps the translated
  sentence in Pydantic's English « Value error, »); the e-mails use the
  application's register.
- The agent descriptions changed content as well as words: a provider's name gave
  way to its category (e-mail, calendar, contacts, tasks — the connectors also
  serve Apple and Microsoft), and the weather agent names the provider in use
  (Google Weather by default, OpenWeatherMap when configured).
- Dead code went with the change: `_n`, `get_ordinal_label_for_index`,
  `ExecutionStepLLM` and two plan helpers left without a caller
  (`dict_to_parameters`, `ParameterValue.from_python_value`), the tools' `labels`
  module and `ResolvedReferences.format_for_response` (French-only possessives
  nobody called), the Wikipedia client's `set_language` and
  `get_supported_languages`, the Places client's `set_language` and
  `get_common_place_types`, two `HITL_*_MESSAGE`
  constants pinned to French, `get_password_requirements_message` and
  `PASSWORD_REGEX_PATTERN`, `APIMessages.email_read_more` and its alias (the
  e-mail card draws the link), the Perplexity tools' client factory (never called)
  and the client's `user_timezone`, the e-mail, event and task branches of the
  disambiguation line (no candidate carries their fields), the semantic types'
  `labels`, eight `SSEErrorMessages` methods and two prompt helpers no production
  code called, the streaming service's `format_error_chunk` (tests alone called
  it), the `entity_resolution_tool` module nothing imported and the four
  `APIMessages` methods it alone called, the tools' base `create_client_factory`
  hook (never called), the replanner context's `user_language`, the draft
  critique's pre-generated-summary branch (no producer ever set `draft_summary`)
  with the context field, `format_draft_critique_actions` and the action labels,
  prompts and descriptions only it read, and language parameters nobody read. Replaced rather than dead — each a second authority on
  a language: the stream route's `Accept-Language` parameter, with
  `get_user_language` and `get_language_from_header` behind it (the middleware
  declares the request's language), the interests' `normalize_language_code`
  and the Wikipedia source's `LANGUAGE_MAP`, and the private normalisers of four
  i18n modules (the chokepoint). A personality's translation no longer falls
  back through English on its way to the first one written — the translations
  are ordered by creation, an administrator's text first among those written
  together (an unordered collection returned whatever the heap held).
- **Deliberately left, and why.** The demonstrator's daily report stays French (an
  owner decision: one operator address). Parsing lexicons stay multilingual input
  tables (quoted-reply markers, acknowledgement words, route modes, location
  phrases, the resolver's ordinals). Four versioned prompt files are still written
  in French (`memory_danger_directive`, `memory_normal_directive`,
  `memory_profile_template`, `peer_context_template`) and two more hold French
  section headers (`memory_profile_section_headers`, `peer_context_section_headers`);
  the memory emotional labels (`[NÉGATIF]`, …) are French literals of
  `memories/emotional_state.py`, named by the danger directive and reaching the
  model through the profile template's `{profile_sections}` and the portrait's
  `memories_item` line; the HITL classifier's action types (`ACTION_TYPE_*`:
  « recherche », « envoi », « suppression »…) are French values its prompt reads
  and its example sections are keyed by. Some thirty English prompts carry French
  lines — few-shot examples and phrasings, some multilingual on purpose (the Hue
  dimming synonyms) — measured by a line census. Text only a model reads stays
  translated inline in six languages wherever a census of every i18n method and
  table (several hundred, each followed to its reader) found it: four tables
  (`NEUTRAL_PERSONA` of the reminder notification, `agent_error_line`, the
  attachment hint appended to the person's own message for the router, the
  domain labels of the text summaries the response model reads,
  `formatters/text_summary.py`); the tool results written through `APIMessages`
  (reminders, labels, e-mail, places and environment, contact groups,
  availability, URL screening, connector activation, reference resolution) and
  the weather summaries of `V3Messages`; the location fallbacks
  (`agents/utils/i18n_location.py`); the HITL reformulations that replace the
  person's message in the graph state (`get_reformulation`); the reminder
  prompt's elapsed-time wording and memory header; the recurrence suggestion's
  directive; the voice agent's context headings, availability phrases and the
  phrases its tools return to it (`i18n_telephony.py`, `TOOL_PHRASES`); the period of day, season, day and month names of the
  prompts' temporal context (`agents/prompts/__init__.py`); and the interest
  queries' diversity angles and locality suffixes, which a search engine or a
  model reads. Tool messages also go through
  `_()` in six languages at 68 call sites — 58 sentences in six modules (context,
  Hue, weather, Wikipedia, web search, routes): ADR-256 asks for technical
  English, and which of them a person also reads was not settled here (the
  seven memory categories' names and descriptions translated beside them —
  fourteen msgids — are read by people: the memories router serves them). Inline
  English scaffolds around versioned prompts (the semantic validator's request
  block, the compaction request, the draft critique's user turn) are ADR-284's
  business, English already — the validator's cardinality line named French and
  English quantifiers and now names the English ones « in whatever language it
  is written », an edit to model-facing text this change made without measuring
  it. Translating what
  the model reads changes what it does, so each is measured before it ships —
  proposals, not part of this decision.
- **Found, not fixed**: the weather card chooses its icon from the LOCALISED
  description against an English and French lexicon, so German, Spanish, Italian
  and Chinese accounts always see the default icon — the provider's condition code
  is language-independent and should decide instead. The Wikipedia tools and the
  unified web search are plain tools that never read the instance switch of a
  keyless connector (ADR-307): an administrator who turns Wikipedia off does not
  stop them. A broadcast's source language is the sending administrator's
  account language — nobody can state it, so a broadcast written in another
  language is translated from the wrong one. The diagnostician's prompt asks for
  a synthesis in `{language}` under French headings: whether a non-French
  administrator reads them is unmeasured. The entity-disambiguation HITL chain —
  the task orchestrator's routing branch, the dispatch node's, the graph's route,
  its state keys and `HitlMessageType.ENTITY_DISAMBIGUATION` — has no producer
  since its only one, imported by no production module, was deleted; so has the
  service behind it, `EntityResolutionService`/`get_entity_resolution_service`,
  and the four `APIMessages` methods only that service calls (`entity_not_found`,
  `entity_missing_field`, `invalid_choice`, `choice_out_of_bounds`) — one chain,
  to delete together. So is the destructive-confirmation dialog: its interaction
  is registered, but no node emits it, and no production code calls what was meant to raise
  it — its own `should_trigger_destructive_confirm`, or the scope detector's
  `should_escalate_to_destructive_confirm`, the one caller of
  `detect_dangerous_scope` in `src/` — with the two keys of its table only it
  reads (`and_more`, `unnamed_item`); its title and three keys are read by the
  live draft critique. `core/partial_error_handler.py` and the interests'
  `WikipediaContentSource` (documented as deprecated) are imported by no
  production module (tests only). No production code reads (an AST census over
  `src/`; a name that merely equals another's — `dict.get` — is no read) 47 of
  the 208 methods of `APIMessages` nor its `EMPTY_RESULT_MESSAGES`, 29 methods
  of `V3Messages` (30 with the one only an unread method calls), three of
  `HitlMessages` (four with the one only two of them call) — the
  model-facing `get_reject_enriched_message` and its table,
  `format_for_each_items_excluded` and `format_for_each_filtered_header`
  (`get_field_type_label` and `get_domain_label`, which no production code
  called, were deleted with their tables — the field labels had lost their
  last reader when the disambiguation question came to speak whole
  sentences) — and
  nine module functions (`get_day_name_short`, `format_date`,
  `get_speaker_label`, the `get_section_label`, `get_template_name` and
  `supported_languages` of `i18n_meetings`, `get_all_ordinal_words`,
  `get_all_keywords`, and `i18n_meeting_templates.supported_languages`, which
  only tests call). Two more chains have no producer:
  nothing records a `planner_error` (the initial state writes `None`, and the
  response node's planner-error block — five `APIMessages` methods — and the
  orchestrator's check read it), and nothing sets a result's `user_rejected`
  (the refused-action line and `HitlMessages.get_user_refused_action`) — one
  deletion each, the state key's after a checkpoint-compatibility check. No code
  acts on a phone draft's
  `date_window` — the availability pre-fetch and the call ignore it, the card
  does not show it; only the model writing the confirmation question sees it —,
  and its descriptions now say so. The notifications device column's database
  comment still says French: a column comment changes with a migration. Outside
  i18n, the fifth review found three older defects: `auto_approve_plan` is inert
  since v1.0.0 (the router resets, at every turn start, the flag the service
  sets) — so,
  the validator's verdict read again (below), a run nobody attends meets its
  clarifications like a typed turn: a routine stops on the question, counted a
  failure, and the question waits in the conversation, where the executor's
  guard defers the next routines (HITL.md and SCHEDULED_ACTIONS.md say so; from
  2026-09-05 to this change nobody was asked anything) —, an account deletion
  holds its row lock across its network calls (ADR-304), and
  `with_user_preferences` lets a value the model passes for `locale` or
  `user_timezone` override the person's. Each is a proposal — the first one a
  POLICY to decide for the runs nobody attends.
- **Found during the change**: one mechanical pass wrapped seven tool parameters'
  `Annotated` in a union, which silently drops their description from the schema
  the model binds — caught by the schema census, fixed, and guarded. And removing
  an attribute the Perplexity tools read broke both tools while every gate stayed
  green: MyPy's `attr-defined` is off for the tools package and a test fake carried
  the attribute by hand. The tools now read the person's clock and language from
  the typed runtime context (ADR-231), and the fake has exactly the real client's
  surface. The third review found French still in runtime tool messages (the
  Perplexity sources and related questions, the web search's related questions,
  the calendar's untitled event, primary marker and unnamed calendar, the e-mail
  client's invalid-address error, the serializer's unnamed item) and in the
  e-mail card's « Non lu » title, all fixed; and a deactivation's reason — an
  administrator's words about a person — logged at WARNING, now logged by its
  length (ADR-317; the audit log keeps it). The fourth review found a deactivated
  Telegram account read as unbound (the person was read without deactivated
  accounts, so the lookup failed and logged an ERROR), the typed reasons of an
  account deletion, a manual usage block and a disabled connector in INFO and
  WARNING lines too — now lengths, and the ADR-317 guard reads such fields by
  name (`TYPED_TEXT_FIELDS`, a field-name constant resolved) and pins the two
  modules where a bare `reason` is an administrator's words, whatever the
  event —, an
  approval gate with no plan writing a USER rejection the answer then attributed
  to the person (no plan is now no verdict), a connector disabled without a
  reason when the field was omitted, a transaction held open across the
  deactivation e-mail and the session invalidation, the label punctuation above,
  tests of a language fallback that passed with French hard-coded (now pinned off
  the default), and the guards' own blind spots (text-method chains before a
  locale cut, `Annotated` defaults, `def _`, alias chains) — all fixed. The
  fifth found the routing after the semantic validator reading the `None` the
  router writes at every turn start as an approval (ADR-263), so every
  clarification and auto-replan verdict had been computed and ignored since
  2026-09-05 — the validator node's own skip had lost the same reading on
  2026-09-19, its twin had not; every Telegram turn running with journals and
  psyche off (above); the connector-disabled e-mails and a personality's model
  translations running with a transaction open (ADR-304); a manual usage block,
  new limits and an account deletion invalidating the usage cache BEFORE
  committing, so a check in between re-cached the old verdict; the per-user
  Telegram lock released by whoever finished (`SET NX` then `DELETE`, now an
  owner token); the knowledge enrichment keeping one Brave client per person
  for the life of the process, a rotated key included; the label punctuation
  of decision 8 on five more surfaces; a dead branch of the draft critique; and
  the guards' blind spots again — f-strings and template mappings told a code,
  `or` operands, constants holding the instance default, relative imports and
  module-qualified aliases, `dpgettext`, `.get("language")` and
  `accept-language` — all fixed, the language-default census re-measured on
  4f19469b (633). The census of model-facing translations then found the
  conversation outcome reading the PRESENCE of `planner_error`, which every
  state carries (`None`): `agent_success_rate_total` counted every conversation
  as a failure since v1.0.0 (349 on dev over fifteen days, not one success), so
  the SLO rule `agent:slo:success_rate:1h` had no series at all (no
  `outcome="success"` sample ever existed: « No data », not 0) and the critical
  `ProductE2ESuccessDrop` could never fire. The outcome then read the current
  turn's agents alone — `agent_results` keeps every turn
  of the thread under `turn:agent` keys — and a turn that ran no agent is
  `no_agent`, outside the success rate (`agents/services/business_metrics.py`,
  tested on the state the graph builds, over several turns). The sixth review
  found the clarification's answer and field surviving into the next turn — a
  stale answer turned a new request into a replan of the previous plan, a path
  the verdict fix had made reachable again — (the router's per-turn reset now
  clears them, and `needs_replan`); a Telegram link that failed OPEN when the
  account could not be read (now one short session, refused inside it); a HITL
  button resuming the graph without the person's turn claim, a claim never
  renewed while a turn outlived its TTL (now HELD: re-armed, the turn stopped
  if another holds it — `held_claim` in `infrastructure/locks/redis_claim.py`)
  and a cache failure dropping the message in silence; a cancelled Brave search
  recorded as a success, its record written after the close; the validator
  validating a plan the person's answer had made stale; the debug panel drawing
  the gate's automatic approval as the person's decision (the value now travels
  with its three states); a personality code taken while the model translated
  answered 500 (now 409); the readable archive's headings and speakers in
  English for every reader; French typography in the HITL and effects tables;
  the stream's fallback flattening no-break spaces; and the guards' blind spots
  again (any other read of the instance default, a fallback chain, subscript
  targets and entries under a language-named key, `.get` on a field constant, a
  reason through a local alias, a `_tag` name, `re.split` and `getattr` locale
  cuts, `dict(...)` tables, keywords of every template call) — all fixed, the
  language-default census re-measured on 4f19469b (670). The seventh review
  found the per-turn outcome still judging a ReAct turn by its answer — a turn
  whose every call failed was a success —, and a turn cut by its budget, a
  planner that produced no plan and a draft the person confirmed not at all:
  the outcome now reads each turn's own evidence — the planner's verdict
  (`planning_result`, reset by the router with the plan and its step results),
  the agents' results of the turn alone (a key with no turn judges nothing),
  the loop's tool results counted from the end of the thread and its budget
  cut, and the confirmed draft's execution —, a metrics failure judges no
  agent, the agent label is the turn's execution mode, and a successful turn
  records its run's own cost, never the thread's running total; the honesty
  directive restating an earlier turn's failures as the current one's
  (measured: a « thanks » was told the previous turn's 403) — it reads this
  turn's messages, and a plan's step results no longer outlive their turn; the
  debug panel's draft rows, null in production because the response node
  clears the decision it executed; an empty answer to an early detection
  looping planner and validator to the recursion limit; a held turn claim
  that could not tell its own stop from a caller's cancellation, had no bound
  and released a claim another held; a Telegram button failing silently on
  every error path, resuming a conversation no longer the person's; an OTP
  check that crashed unanswered, and the rate limit read after the refusals
  it precedes; a Brave search the client refused recorded as a success; a
  personality conflict read from any integrity error, and answered in
  English; an administrator's change reason logged above DEBUG; a one-line
  preview flattening no-break spaces; and the guards' blind spots again (a
  locale held by a local alias, the Chinese prefix tested by hand, a split fed
  through a variable or `enumerate`) — all fixed. The eighth review found the confirmed draft's verdict still never reaching
  the metrics — its fast path returned before them —, a batch that failed whole
  counted half a success, a call the person declined in ReAct counted a
  success, a failure the loop got past counted a partial one (a ReAct turn is
  now judged on its result, ADR-310: its calls, what its answer declares
  unresolved, its budget cut), the initiative's own lookups judged as the
  request, and a turn resumed after a question costed from its second half
  alone; a Telegram refusal still answered once per message (now once per
  rate window, the account's state read and named before the rate), a held
  claim's release skipped by
  a cancellation arriving during the unwind, the client language filtered on
  the fixed list rather than the instance's, a failed conversation read
  answered as an expired question, a concurrent personality rename answered
  500; a disambiguation question pluralising its label by appending « s »
  (« Telefonnummers ») under a field named after a provider's key; the debug
  panel drawing the previous turn's draft decision, a one-line preview keeping
  a line separator, the FOR_EACH preview's English fallbacks, ASCII ellipses
  and breakable spaces inside « z. B. » and « p. ej. »; and the guards'
  complexity, their alias shapes and a clock read as a label's colon — all
  fixed. The ninth review found the turn's metrics still able to fail the
  response node — on the fast path after the draft was sent — through a
  connection that would not open or a commit the database refused (the
  metrics are now best-effort, a cancellation excepted), the eighth round's
  button fix pinned by no test that could fail, a held claim's release
  leaving the keeper's cancellation counted when the caller's arrived during
  it, a Telegram refusal silenced by an unreachable cache and a refused
  button answered on every press (both doors now share one notice per
  window, which answers when it cannot be recorded), a network access the
  person refused counted as a failed call, a colon before a line break no
  longer read by the label guard, the Chinese organizer label written as a
  frame with a hole, two more mid-word clips and the drafts' own preview
  still folding no-break spaces (`one_line` moved to `core.text_clip`), and
  — on the way — a field's choice question closed on « ? (… » in every
  language — all fixed; the two label helpers no reader was left for were
  deleted. The tenth review found a successful turn still losing its other
  samples when its run's cost could not be read (the cost is now read last,
  on a session of its own, whatever the driver raises), the button door's
  claim refusals a second implementation (both doors now claim through one),
  the card title and a result's label and excerpt folding or clipping unlike
  the rows beside them, the field question's choices pinned by no test, the
  census sentence wrong about history, and seven functions of this lot's guards
  over the complexity bound — the three it named and four more the same
  measure found (split, their findings diffed identical) — all fixed. The
  eleventh review found the metrics path holding its first session open across
  the currency lookup's network call (the thread's answers are now priced by the
  in-memory pricing cache — the ledger's own tariffs, cache writes included —, a
  successful turn's cost is its run's accounting — its ledger row and what the
  tracker has not filed yet — and the calculation holds no session), a tool
  call's arguments able to hide behind typographic or invisible characters on
  the card that asks for them (a program's value is now drawn by
  `one_line_of_data`: every space folded, every format character spelled out), a
  bold label broken by a space touching its markers, three copies of the loop
  that names a draft (now one, `item_label`), a result's detail rows still cut
  inside a word, an organizer line joining its label outside `label_separator`,
  an off-keyboard Telegram action reaching the person's message and turn, the
  label guard reading a pattern named `regex` as the module, predicates the
  default-read shape masked in the guards' oracles, the dead post-hoc reasoning
  snippet rewritten instead of deleted, and a failed call still counted as
  productive — all fixed; the destructive-confirmation dialog, emitted by no
  node, joins the chains to delete.
  The twelfth review found the Telegram buttons reading the pending question in
  the session database while the engine writes it in the cache one (every press
  was told its question had expired), the keyboard keyed by a type no
  interaction writes and reading one nobody writes (Approve / Reject under every
  question), the demonstrator's grace period shorter than the drain it waits for
  (now held by the guard that held production's alone), the business metric
  counting a pricing miss for every answer of the thread at every turn (it now
  reads the tariff through a quiet door sharing the ledger's arithmetic, the
  ledger counting a miss once), a call that failed after its answer still
  handing on its registry items, seventy zero-width spaces, Hangul fillers or
  stacked marks still filling a card's bound (every run of characters nobody
  sees is now one marker with its count, in brackets no surface strips) and a
  value read as markup on the plain surfaces — a link reading one host and going
  to another, an argument's name writing a row of its own (every value of a card
  is now drawn as itself, the ticket and Telegram render the references it
  carries, and the arguments a card leaves out are counted) —, a blank title
  quoted into a header that never closed, the event description's tag pattern
  gone quadratic on a third party's HTML on the event loop (linear now, its
  entities decoded, its style dropped), the destructive chain still described as
  live in docstrings, CLAUDE.md and the HOW guide, the web reading a `detail` no
  writer writes, and the guards' docstrings claiming readings they did not make
  and predicates no probe held — all fixed, each change of behaviour its
  author's mutants exercised pinned by a test the mutant fails (the next
  review's benches found some twenty-five more behaviours unpinned). The
  thirteenth review found the Telegram keyboard declaring an answer for three
  interaction types of eight, the others answered in words by a fallback (every
  type now declares a pair of buttons or free text — a draft and a tool
  confirmation take the two main answers of the chat's card — checked at boot),
  a typed answer said to open a new turn (the checkpoint resumed it; it lost its
  run and left the question's record behind), a program's value cut on a word —
  « GET » kept and a URL's host dropped, two zero-width spaces showing only
  their marker (such a value is now cut inside its token, a marker never cut,
  and read only as far as the bound needs) — and interleaved spaces filling the
  bound marker by marker (a run of what nobody sees, the spaces between
  included, is one marker), the rows of a FOR_EACH, a draft sequence and a batch
  drawing a subject as markup (a link and a tracking image in the question),
  emphasis still drawing italics in a card's values, a body's images and a
  spreadsheet cell's links drawn before the person approved anything (every
  value, block and note of a card is now data, and the one link LIA builds is
  described as a link, for a URL that cannot end it early), a ticket beside HTML
  decoding a value's references before the tags were stripped and the voice
  reading them out (both flatteners and the browser's twin keep them out of
  their reach and decode last only the references a value is drawn with), a line
  break in a row value writing a row of its own, a title of nothing visible or
  reordered by an override (spelled now), the event description's style ending
  at the first « < » it held and a no-break space lost beside a tag, the
  typography census weakened to one string per module (an exact fixture now),
  the label guard reading an unpacked or looped pattern as the module, stale
  store, timeout and metric documentation, « nothing calls » where tests do, the
  quiet pricing door's docstring, a declared failure's registry comment, the
  books, cold-cache and time-of-day paths no test pinned and the tests' typing,
  the ARCHITECTURE box, ADR-018's detail block and the language guard's
  docstrings — all fixed, each change of behaviour its author's 65 mutants
  exercised pinned by a test the mutant fails (the next review's benches found
  eighteen more survivors, pinned since).
  The fourteenth review found that no question asked on Telegram had ever been
  saved — the channel's reader left the stream at the question, before its tail
  saved the question, committed the turn's tokens and closed its clients (the
  stream is read to its end now) — a question the stream left empty sent as
  nothing, a press answering whatever question waited (a button carries its
  question's fingerprint and a press is the chat card's own decision; an expired
  one is answered « expired », its keyboard taken off), a split question's
  keyboard on every part and lost at Telegram's retry; a value drawn as itself
  that the chat linked to another address (`jean&#95;dupont@example.com` linked
  `dupont@example.com`: a value now references what could delimit and the three
  characters that start a link, and what the chat still links reads as its whole
  address), the references of a card read as typed where the chat decodes them
  (ONE reader, `read_as_markdown`, and its browser twin read them as the chat
  does — outside code every valid reference once, an `&` that opens none an `&`,
  a code span as typed, a bare URL's marks kept, the reserved characters
  one-to-one — for the ticket, the voice, Telegram, the push, the channel
  notification, the toast and the model's history), the HTML stripper decoding a
  card's `&lt;` before its tags were stripped (the phone read a reply's
  recipient without its address), a value's `$` or `\` drawing a formula in ANY
  `lia-card` (`escape_html` references them, and the chat takes a referenced
  dollar as a literal one), a bare carriage return ending a card's HTML so that
  the rest was read as Markdown and its images loaded, a recipient's display
  name pushing its address out of the row (a recipient is never cut now), a
  result's headline and an executor's error drawing the draft's values as
  markup, a URL in any detail field drawn as a link reading its label (only a
  field declared a link draws one), a stack of marks joined by what nobody sees
  escaping the smear rule, a label spelled after it was cut past its bound, a
  step's tool name drawn raw, the model's history stripping a draft card's
  values as Markdown and its summary decoding a raw title, an event description
  reading a layout run's no-break space as typography and a stray `</script>`
  closing a block that had not opened, the FOR_EACH thresholds published
  inverted (described as the code uses them; swapping them is the owner's call),
  the HOW guide describing a plan-approval interruption and a `MODIFIER_REVIEW`
  type no code has, and every HTML reader of an e-mail quadratic on unclosed
  tags (20 000 `<h1>` cost 4.6 s on the event loop; a tag never holds a « < »
  now, and a heading or a link is read tag by tag, the browser's twin alike) —
  all fixed; 82 mutants over this round's changes and the survivors it found,
  all killed but one equivalent (an excerpt is spelled where it is cut).
  `one_line_of_data`, which no code called, is gone: the data drawing is
  `clip_data`'s. Left to the owner: the WHY guide, the landing page and the blog
  still describe a plan-approval interruption and a destructive confirmation no
  node raises, and the README lists that destructive confirmation among the
  interruptions (it states the plan approval as auto-approved) — public texts,
  while another change edits the same locale files; and the radio's two readers
  (`newsroom/fulltext.py`, `newsroom/parse.py`), in another change's files, keep
  the quadratic tag pattern.
