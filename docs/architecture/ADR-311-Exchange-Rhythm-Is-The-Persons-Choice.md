# ADR-311 — The exchange rhythm is the person's choice: one value, read once per turn, decides the tools, the context's place and the history blocks

**Status**: accepted — 2026-09-24 (owner decision: a « Preferences » settings menu whose first setting is frequent or occasional exchanges)
**Amends**: ADR-308 (`REACT_CROSS_TURN_CACHE_ENABLED` becomes the default of an account that never chose), ADR-309 (the history blocks follow the turn's rhythm), ADR-293 (the relevance selection is the occasional rhythm)

## Context

ADR-308 made one operator flag bind every tool and move the turn's context after
the question; ADR-309 added the history blocks under the same flag. Its benchmark
(396 real turns, weighted by the production gaps between ReAct turns) measured the
pair at −18 % (Claude) to −42 % (DeepSeek) per turn. It also measured the price:
once the provider's cache has expired, a turn writes the whole catalogue again, and
a model with no prompt cache pays 18 % more. Who gains depends on how a PERSON uses
LIA — turns close together read the previous one back, turns hours apart pay the
heavier first call every time — and one instance flag decided it for everyone.

The owner asked whether the context move and the history blocks pay in every case,
in which case only the tools would be worth a choice. Measured, they do not:

- **The context after the question pays only when the tools before it stay the same.**
  With every tool bound: DeepSeek −42 % instead of +44 %, Claude −18 % either way,
  GPT-5.6 −34 % instead of −37 %, qwen3.7-plus −18 % instead of −25 %. Under the
  relevance selection, two consecutive turns share about two thirds of their tools
  (Jaccard 0.67): the prefix breaks before the context, and there is nothing left to
  gain.
- **The history blocks keep up to `block − 1` more turns so that the next turn reads
  the history back.** When the tools before them change, nothing is read back, and
  that fifth of history is paid at full price (ADR-309's own consequence).

And three modules read the flag, each on its own: the selector at the turn's setup,
the layout and the history on every call. Changed in the middle of a turn, a choice
read that way would have mixed two layouts inside one turn.

## Decision

1. **The account holds the choice**: `users.exchange_rhythm` — `frequent` or
   `occasional`, NULL when never chosen. An account that never chose follows
   `REACT_CROSS_TURN_CACHE_ENABLED`, which keeps its name and becomes the operator's
   DEFAULT: no deployment's `.env` changes, and migration `402dd18bbf2a` adds the
   nullable column without filling it, so nothing behaves differently when it
   appears.
2. **One value decides the three effects together.** Frequent: every tool bound, the
   turn's context after the question, the history dropped by blocks (ADR-308,
   ADR-309). Occasional: the relevance selection (ADR-293), the context in the system
   prompt, the sliding window.
3. **Read once per turn.** The stream service reads the account's row; the single
   runtime-context builder resolves the effective rhythm
   (`core/exchange_rhythm.effective_exchange_rhythm`, the one reader of the setting —
   guarded); the router publishes it into the turn's state (`exchange_rhythm`, a
   declared `MessagesState` key). The setup binds with `every_tool`, and each call
   reads `frequent_exchanges(state)` for the layout and the blocks. A HITL resumption
   re-enters the interrupted node rather than the router, so a turn keeps the rhythm
   it started with. The sub-agents run LangGraph's prebuilt loop and are not
   concerned.
4. **Written through the generic profile update** (`PATCH /users/{user_id}`, the door
   the theme and the font already use). Writes are strict: two values, stored as exact
   strings. Reads are forgiving: the profile publishes the EFFECTIVE rhythm, so the
   screen always shows the one a turn runs with, and an unreadable value follows the
   default.
5. **Settings › Preferences › Personalization › « Usage preferences »**, a section
   meant to receive more settings:
   - a native radio group, each option described;
   - the fallback stated: when the configured model cannot hold every tool, a frequent
     turn keeps the relevance selection for that message (ADR-308's counted fallback);
   - searchable (ADR-172) and pinnable to the dock (ADR-277), in six languages.

   It is not titled « Préférences »: the tab already is.
6. **The runs LIA makes on the person's behalf follow the account's rhythm** —
   scheduled actions, Workboard tickets, relayed voice turns — because they go through
   the same stream service.

## Consequences

- **Nothing changes at deployment.** Production keeps frequent exchanges for every
  account (its flag is on). Self-hosters and the demonstrator keep occasional exchanges
  (off by default). This holds until a person chooses.
- **Held by tests**:
  - only the resolution reads the setting;
  - the router publishes the run's rhythm into the state and overwrites the previous
    turn's;
  - the setup binds by the state's rhythm whatever the setting says;
  - the call's layout and history blocks follow the state;
  - the profile publishes the effective value;
  - the web list and the backend vocabulary are the same;
  - the settings screen's own guards cover the section's table, search entry, icon and
    component.
- **One more settings section**: 63 sections, searchable and pinnable.
- **Not measured**: how the gains split between the two rhythms on real accounts. The
  chat meter shows the cost of every turn, and the choice can be changed at any time.

## Rejected

- **Keeping the context move and the history blocks always on, and letting the choice
  decide the tools alone**: measured not worth having alone (above).
- **An automatic choice per model or per account**: the owner's rule is to never
  reason on one model, and ADR-308 rejected a per-model `auto` mode. The gap between a
  person's turns is theirs to know.
- **A dedicated `PATCH /auth/me/exchange-rhythm-preference`**: the auth router is at its
  size cap, and the generic profile update is the door the display preferences
  already use. It adds no route to the demonstrator's exposed surface either.
- **Deleting the operator's setting**, following ADR-276's « one authority » rule: kept
  as the default of an account that never chose, with the person's choice always
  winning. Deleting it would have changed every deployment's behaviour at upgrade.

## References

- `apps/api/src/core/exchange_rhythm.py` — the vocabulary and the one resolution
- `apps/api/src/domains/agents/nodes/react_turn_layout.py` — `frequent_exchanges`
- `apps/api/src/domains/agents/nodes/router_node_v3.py` — `_resolve_exchange_rhythm`
- `apps/api/src/domains/agents/services/react_tool_selector.py` — `select(..., every_tool=...)`
- `apps/api/alembic/versions/2026_09_24_1500-402dd18bbf2a_users_exchange_rhythm.py`
- `apps/web/src/components/settings/UsagePreferencesSettings.tsx`, `apps/web/src/lib/exchange-rhythm.ts`
- `apps/api/tests/unit/core/test_exchange_rhythm.py`,
  `apps/api/tests/unit/domains/agents/nodes/test_react_exchange_rhythm_wiring.py`,
  `apps/api/tests/unit/domains/users/test_exchange_rhythm_preference.py`
- [ADR-308](ADR-308-ReAct-Cross-Turn-Prompt-Cache.md), [ADR-309](ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md), [ADR-293](ADR-293-React-Tools-Bound-By-Relevance.md), [ADR-172](ADR-172-Settings-Quick-Search.md), [ADR-277](ADR-277-Settings-Shortcuts-Dock.md)
