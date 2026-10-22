# LIA isometric world: accepted V1 scope and extensible foundation

Date: 2026-10-09. Status: V1 scope concessions accepted by the owner; generic/evolvable design required. Detailed foundation contracts below remain design specifications to implement and qualify. The complete target is retained for later lots.

This addendum answers the owner's questions about execution with Codex in ultra mode and meaningful V1 concessions. It complements the [complete analysis](2026-10-09-lia-isometric-world-analysis.md) and [characterization report](2026-10-09-lia-isometric-world-validation.md). Work remains inline. The owner subsequently accepted the proposed V1 and progressive enrichment, explicitly requiring generic conception/design that facilitates future changes. This document now governs the first-release scope; deferred functions are not treated as implemented. No business code was written for this scope/conclusion update.

Implementation refinements and current evidence are consolidated in the [global architecture and game-quality review](2026-10-09-lia-isometric-world-global-review.md). That review governs strict owned translation attempts, existing quota limitations, first-frame world authentication, movement/camera/input mechanics, shell resource ownership and measurable quality gates without enlarging the accepted scope.

Visual-reference decision, 2026-10-20: use [MalinosLand's appearance and reviewed game concepts as the base](2026-10-20-lia-world-malinosland-reference.md), preserving the accepted V1 below. Selective reuse/Phaser integration is assessed before choosing a final renderer; optional discovery/social polish does not reinstate deferred features or create token-spend rewards.

## 1. Meaning of the previous estimate

The complete analysis's engineering/art ranges describe an indicative conventional specialist effort, not measured Codex execution throughput or a forecast of how long an agent turn takes. Translating those person-days directly into a Codex-assisted calendar forecast was too imprecise. No measured acceleration factor exists for this extension.

Code drafting, test construction, repeated source inspection, integration changes and mechanical documentation can advance much faster with the agent. The first representative scene, art export/animation, real-device behavior, provider fidelity, multi-account adversarial evidence, test runs and owner feedback still require actual work. Ultra mode does not itself establish a performance or delivery guarantee. Extensive concurrent checkout changes are a separate integration dependency.

For planning, a useful conditional working target is a representative playable prototype in roughly one to two weeks and a qualified smaller V1 in roughly four to six weeks of sustained assisted work. These are provisional planning objectives, not measured forecasts or commitments. They assume the proposed concessions, a stable integration snapshot, timely access to minimum devices, modest art scope and prompt feedback. Re-estimate after the first end-to-end slice; report elapsed work, remaining defects and real hardware outcomes rather than extrapolating a generic multiplier. The prototype is not the complete multiplayer/private/translation acceptance gate.

## 2. Product experience retained

Retain a spacious navigable world, auto-follow camera, zoom/pan/minimap/recenter, keyboard/mouse/touch, one common world capped at five, graceful waiting, direct text and translation before display, existing asynchronous peer relay, private LIA/BIP interaction, a personal home, functional stations and actual ordinary-LIA effects. Preserve user-specific interface language and atmosphere. No points, competitive loop or incentive to spend tokens is inferred.

Preserve authorization, quotas/cost receipts, existing approvals, reconnect behavior, keyboard/focus access, account lifecycle and modest-device qualification. They are not scope concessions. The user still needs meaningful activities and social interaction, not a decorative prototype with inactive stations.

## 3. Accepted concessions and visible consequences

| Accepted V1 scope | Complexity/art avoided | User-visible consequence | Relative gain |
|---|---|---|---|
| Five or six carefully dressed places with grouped functional stations, rather than a separately authored interior for every LIA feature | Many unique layouts, art sheets, colliders, station variants and journeys | Some features share a themed building; all selected existing functions remain accessible through their ordinary interface or private station panel. This explicitly relaxes the original one-place-per-feature requirement for V1 | High |
| Reuse existing owner panels/forms/cards and assistant presentation inside a coherent world dock; bespoke in-scene controls only for spatial actions | Duplicate validation, editing flows and per-feature UI design | Familiar controls and real effects, with less theatrical/custom presentation per feature | High |
| Personal home with a small motif catalogue, a few mapped interests and two or three explicitly selected memory motifs; palette and placement overrides | Broad automatic semantic classification, extensive mapping/art catalogue and elaborate continuous rebuilding | Genuine bounded personalization; unrepresented profile/memory/interest data remains fully manageable through existing owner interfaces | High |
| Private personal homes in V1; timed peer visits deferred | Grant acceptance/expiry/revocation, guest blueprint generation, compatible neutral replacements and visit race matrix | Invitations into the home are unavailable initially. People can meet and chat in the public places; this is an explicit feature deferral, not unchanged functionality | High |
| Shared scenery fixed; owner furniture moves only between declared valid anchors in the home | Cross-user grabs/leases, continuous arbitrary placement, changing public navigation and shared persistence conflicts | A modest but usable owner editor; public objects retain selected safe interactions. Shared furniture dragging is deferred | High |
| One reusable modular art kit; limited avatar/outfit choices and a small polished animation set | Many character rigs, custom source props and one-off directional exports | Visual cohesion and readable movement; less cosmetic variety at launch | High for art |
| BIP patrols defined walkable paths, comes when called and follows a small interaction state machine | Rich context-sensitive ambient behavior and many animation combinations | BIP remains present, autonomous and useful, with fewer ambient routines | Medium |
| Personal civil-time tint and a few light weather presets from authorized current/cached data, with honest neutral fallback | Extensive weather variants, expensive effects and custom lighting | Personal atmosphere remains; subtle effects rather than environmental simulation | Medium |
| Qualify five active accounts only for initial release, while retaining configurable bounded admission | Ten-account complete mixed-load campaign for this release | Capacity remains five with waiting; ten is a later measured upgrade | Low to medium |

Do not claim savings from human voice, federation or generative room decoration: those were already outside the initial release program. Likewise, the original recommendation already allowed 2.5D, deterministic BIP and restrained weather; additional savings come from reducing concrete variations and behaviors, not merely renaming those choices.

Reuse of an existing component is not assumed to make embedding free. Its context providers, owner authority, active-run/approval state, native continuation and responsive sizing still require the inspected integration boundaries and characterization tests from the complete dossier.

## 4. Five-to-six-place composition to refine with the art slice

- A generous central plaza for arrival, orientation and social conversation.
- A post office for communications and peer actions, retaining the distinction between direct human text and LIA-mediated asynchronous delivery.
- An organization atelier for calendar, reminders and scheduled/routine actions, through each existing authorized flow.
- A library for knowledge/document functions and their owner-only panels.
- An optional greenhouse for interests/habits; personal sensitive consultation remains private even when the station is public.
- A personal home for selected personal motifs, owner profile/memory/interest management and bounded furniture placement.

Transverse account/settings/cost/notification controls remain available in the HUD through current interfaces. Each function needs a concrete binding; unavailable/disabled functions have their existing honest availability, not a fictitious action. The exact station arrangement/art remains to refine against the inspected inventory and usage priorities. Grouped places are now accepted for V1. This does not create a replacement business registry or permission to omit an available feature silently.

## 5. Execution and acceptance order

1. Freeze the integration snapshot and choose one representative zone/art budget. Implement a small camera/navigation/BIP slice and measure real minimum devices before selecting one renderer for continued work.
2. Establish private owner interfaces, ordinary assistant/domain integration, persistence and account teardown with a small home. Use source-version/digest reconciliation on load and reconnect; invalidate deleted/unauthorized motifs while preserving manual choices.
3. Add authoritative one-world admission/presence, movement, recipient projection, reconnect and backpressure for five accounts. Independent workers must not control the same world/avatar. Keep queued clients outside the participant/private-state stream.
4. Add direct text, the separate translation slot, bounded unique-language attempts with strict ownership and existing accounting. Same-language messages require no translation call; pending/unavailable states precede deliberate original viewing. Uncertain external completion prohibits automatic duplicate retry. Fidelity/ordering/block/language-change tests remain mandatory.
5. Bind the remaining grouped stations and polish the modular scene. Exercise actual effects in ordinary LIA, both assistant modes where relevant, overlays, focus/IME, mobile input and resource cleanup.
6. Run the applicable full-boundary acceptance tests at five accounts, on the real Pi and minimum clients. Publish only the implemented scope and its evidence; retain deferred tests/lots as future requirements.

The existing source baseline and 443 targeted test passes are useful prerequisites, not passes of these new slices. The 72 scenarios in the complete analysis remain the program's director matrix. Explicitly label timed-visits, shared dragging and ten-account acceptance as deferred for this V1; run every applicable privacy, cost, data, localization, admission and mobile case.

## 6. Re-estimation and non-negotiable launch evidence

Estimate the smaller program after the representative slice, with code, art, device access, uncertainty and elapsed time reported separately. Use these evidence gates rather than a claimed ultra-mode multiplier:

- A detailed representative zone is attractive, readable and actually playable at the agreed minimum client budget, including thermal behavior and chat/panel use.
- Five independent accounts share one coherent world. Wire-level negative tests show no other owner's private data and no queue/unauthorized home stream.
- The Pi's ordinary LIA workloads remain within the agreed interference/resource budgets under combined world and translation activity.
- Functional station operations produce the same authorized results, approvals and accounting as the current application.
- Cross-language messages preserve authorship/meaning, display in the recipient's current language, survive bounded failures and record actual physical calls once.
- Owner layouts/motifs and temporary social data obey reset, deletion, export, versioning and expiry rules.

A coherent smaller V1 should be visibly finished in its delivered places and activities. Its reduction is breadth, customization and advanced interactions; core social/private usability and evidence quality remain launch requirements.

## 7. Required generic foundation and evolution contracts

The extension design follows inspected repository patterns: [stable settings identities](../../../apps/web/src/lib/settings-sections.ts), [typed component bindings](../../../apps/web/src/components/settings/settings-section-registry.tsx), [registry/default completeness](../../../apps/api/src/domains/llm_config/constants.py), [startup assembly](../../../apps/api/src/infrastructure/startup/registries.py) and [database model registration](../../../apps/api/src/infrastructure/database/registry.py). These are precedents, not an existing world engine. The following world contracts are new design work.

### 7.1 Separate responsibilities with narrow typed interfaces

The client separates input/camera, deterministic geometry/navigation, rendering, network state, owner personalization and functional DOM panels. React owns discrete UI transitions; the chosen renderer owns its frame/resources. The authoritative backend separates admission/presence, simulation/sequence, recipient projection, commands and existing LIA/domain adapters. Rendering consumes authorized typed state; it neither obtains business authority nor selects arbitrary tools/URLs. A narrow renderer boundary keeps asset/coordinate definitions independent of the selected engine; do not maintain two production engines.

The new world presentation registry references existing functional identities and existing capability checks. It maps them to station/panel placements; it is not a second business capability catalogue. The bootstrap is the authenticated source of effective availability, supported protocol/catalog versions and current owner language/preferences. Unknown/disabled interactions are refused at the server boundary even if a client shows an old station.

### 7.2 Trusted catalogue-driven composition

Use repository-authored, strictly typed catalogues. Illustrative future contract names are ZoneDefinition, PropDefinition, WorldFeatureBinding, PersonalizationRule and QualityProfile; they are not currently implemented API types.

| Definition | Minimum stable content | Evolution enabled |
|---|---|---|
| Zone definition | Stable ID, layout/asset version, neutral display label key, walkable footprint, entrances, approved anchors and station references | Add a themed place or split grouped stations without changing simulation/UI ownership |
| Prop definition | Stable asset ID, versioned bounds/occlusion metadata, allowed interaction class and placement rule | Expand furniture catalogue, then add richer manipulation under a new checked policy |
| Functional binding | Existing functional identity, localized label, trusted adapter/panel identity, placement and effective authority | Add/reposition a function or introduce a dedicated interface through the existing service boundary |
| Personalization rule | Eligible source type/category, bounded motif mapping, provenance, selector/version and private visibility | Enlarge the motif catalogue/selection while preserving owner choices and source deletion rules |
| Quality profile | Resolution/detail/animation/particle/atlas ceilings and accessibility constraints | Add optional richer detail without changing shared geometry or privacy |

Adding a catalogue item needs bounded metadata validation and relevant art/integration tests. A new business behavior also needs an explicit typed handler, authority, accounting and effect tests. A configuration entry alone never enables arbitrary code, private data, live URLs or new permissions. Catalogues do not embed account facts or personalized labels into globally shared assets. Do not hardcode the number/names of launch zones in the simulator or navigation menu; keep the account cap separately configured.

### 7.3 Stable layout and versioned persistence

Persist stable instance/object IDs and asset references rather than pixel coordinates, texture handles or array indexes. V1 anchored furniture uses floor coordinates/anchor references under a declared placement policy; later free placement may introduce another typed policy without discarding object identity/manual locks. Version the zone layout, asset manifest and owner layout/projection schema separately. Migrate old records with explicit validation, bounded neutral replacements for missing assets and preserved manual choices; do not rebuild every home after an art update.

Keep preferences/layout, derived personal motifs and runtime presence separate, as in the complete dossier. New visit grants and publication approvals will acquire actual models, export/purge declarations and tests when the visit lot is implemented. V1 does not create empty guest/history/voice persistence or dormant paid services merely to anticipate them.

### 7.4 Privacy is an extension boundary from V1

Server-side recipient projection already separates neutral shared geometry/presence from owner data. Personal data cannot enter a public event, catalogue, minimap or global snapshot. Future guest views will be produced through this projection boundary and require an explicit current grant; they will not reuse the owner payload with hidden controls. V1 accepts only its implemented audience/commands and denies future/unknown guest authority. Preserve compatible public/owner collision constraints without exposing private source identifiers. Source revocation/account deletion tears down derivatives and in-flight responses.

### 7.5 Versioned command/events and explicit capability evolution

Use declared discriminated command/event shapes, epochs/sequences, idempotency and negotiated protocol versions. Additive optional fields or new commands require compatibility tests; incompatible changes require an explicit version/migration path. Test old supported clients with new servers/catalogues and cached assets, as well as safe refusal of unsupported shapes. No unrestricted generic command dispatcher or accepted owner_id from the client. Authoritative server time, current session/scope and bounded message/rate limits remain invariant.

Feature availability gates deployed behavior. Deferred visits, voice, shared dragging and ten-account release do not expose fake controls or active services in V1. Each later feature gets its own necessary authority/runtime/cost lifecycle. Existing admin/configuration patterns are reused when that feature becomes real; no new public plugin SDK or federation infrastructure is implied.

### 7.6 Extension oracles included in V1

1. Add a neutral fixture zone/prop to the typed catalogue and have the existing map/navigation/asset loader consume it without simulator-specific branches.
2. Move a fixture function between grouped places without changing its existing API semantics, owner authority or translated identity.
3. Change catalogue/layout versions with saved anchored furniture; migrate/reconcile without losing manual locks or applying wrong-footprint geometry.
4. Expand a private motif mapping; invalidate deleted/blocked sources and keep it absent from public snapshots/minimap/network frames.
5. Run supported old protocol/asset fixtures through compatibility paths; reject unknown/incompatible commands safely.
6. Leave future guest/voice/shared-manipulation capabilities absent and deny forged commands without side effects or paid calls.

These are meaningful evolution tests for boundaries actually delivered in V1. They do not implement deferred features or reproduce every internal helper in a test.

## 8. Revised conclusions after owner acceptance

| Dimension | Revised conclusion | Practical consequence |
|---|---|---|
| Alignment | Accepted V1 preserves core spatial/social/private LIA value with explicit deferred breadth | Implement this scope first; enrich through later lots without silently enlarging launch |
| Complexity | Medium to high for V1; substantial reduction in art variety, guest rights and shared manipulation | Keep the real-time/privacy/cost foundation rigorous and the launch content bounded |
| Risk | More bounded and controllable; critical privacy and quotas plus unresolved modest-device/fidelity evidence remain | Gate each slice with actual effect, wire-level, device and provider-boundary tests |
| Delivery | The one-to-two-week prototype and four-to-six-week assisted-work objectives remain conditional | Generic contracts belong in foundation work, not a separate platform program; re-estimate from the measured slice |
| Result confidence | Higher confidence in reaching a coherent useful initial product, without a runtime/pleasure guarantee | Preserve polish, navigation, social communication and useful stations; collect real owner/client feedback |
| Evolvability | Stable typed catalogues, adapters, projection and versioning localize later changes | New places/variants are mostly content/bindings; visits/manipulation/voice still need their own code and acceptance evidence |

The genericity requirement is now an explicit acceptance criterion. It justifies narrow reusable seams and compatibility tests, not speculative implementation of every future feature. Do not claim future enrichments are free or that no code will ever change. The desired guarantee is that routine expansion does not require rebuilding the existing world foundation or discarding users' layouts.

The refreshed acceptance-update task lint:docs:preview found zero broken living links, stale living paths, living orphans and quoted-fact drift. It still fails on the same six pre-existing technical-map gaps recorded in the characterization report. No business-code tests were rerun for this documentation-only scope update.
