# LIA isometric world: hypothesis validation and visual review

Date: 2026-10-09. Status: characterization evidence and proposed design, before business implementation.

This report complements the [functional and technical analysis](2026-10-09-lia-isometric-world-analysis.md). Work remained strictly inline. No world feature, paid translator slot, dependency, migration, deployment, or application configuration was implemented. Standalone disposable probes were written outside application source. Existing tests, real development Redis primitives, a browser renderer comparison, read-only Pi observations and a small bounded CPU-only Pi subprocess were exercised. Generated artwork is a design deliverable, not an implementation screenshot.

Subsequent authority: the [global architecture and game-quality review](2026-10-09-lia-isometric-world-global-review.md) preserves these historical observations but corrects translation deduplication/quota assumptions and specifies first-frame socket authentication, game mechanics, integration lifetimes and fresh scoped checks. The accepted V1 now resolves first-release grouping; future guest/shared-manipulation requirements remain deferred.

Visual-reference update, 2026-10-20: the owner selected [MalinosLand's appearance and useful game concepts](2026-10-20-lia-world-malinosland-reference.md). It now guides visual acceptance; the generated gallery below remains a historical concept study. This update does not recertify the dated probes or claim that the upstream game supplies LIA's authority/privacy/translation implementation.

The [five-view visual gallery](assets/2026-10-09-lia-world/index.html), [exact image prompts](assets/2026-10-09-lia-world/prompts.json), [measurement record](assets/2026-10-09-lia-world/evidence/observations.json) and [reproduction notes](assets/2026-10-09-lia-world/evidence/README.md) make the result reviewable. All images contain illustrative data; displayed prices and token counts are not measured provider prices.

## 1. Conclusion and confirmed owner scope

The architecture is feasible enough to start a representative vertical prototype. The available evidence supports a Pi-hosted authority with browser rendering, bounded attendance and strict separation between public spatial state and private LIA operations. It does not establish complete-world fluency on modest phones, ten-user mixed-load capacity, network privacy correctness, final animation quality, or the new translator's fidelity. Those are explicit acceptance gates, not hidden assumptions.

The owner resolved the following product choices:

- One common world for all users of an instance; thematic places and private homes are physical areas, not multiplayer shards.
- Pi hosts LIA. Browser rendering is accepted, with modest desktop and phone capability as a design constraint.
- Start at five admitted accounts; target ten after qualification, with a queue when full. Proxies and BIP consume no account slot.
- The world extends outside the viewport. Camera follow/scroll, zoom, free exploration, upper-right minimap and recenter are required.
- This is a social game using LIA functions, with generous spaces and a considered art direction. Simulated isometric 2.5D is acceptable.
- Text first, human voice later. Federation/meta-LIA remains outside this program.
- Each interface uses the user's stored LIA language. Human exchanges between different configured languages are translated into the receiving language before display through a dedicated LLM configuration slot.

Proposed defaults still open to owner refinement are ephemeral direct-text retention, neutral/explicitly published guest decor, the physical feature placement taxonomy, and sender attribution for cross-language translation. They are documented implementation inputs. No renewed question about already settled hosting, language, attendance, or mobile scope is required.

## 2. Hypothesis ledger: confirmation is scoped

"Source-confirmed" means an existing contract was read and counter-checked; it does not mean the future world implementation passed. "Primitive exercised" means an isolated algorithm or engine path worked within the stated fixture. A future security or performance hypothesis remains unqualified until the corresponding complete boundary exists.

| Hypothesis or design dependency | Current verdict and evidence | Implementation consequence / remaining oracle |
|---|---|---|
| The Pi must render and stream every frame | Rejected as the chosen topology; owner accepts browser rendering | Pi owns authority, account operations and synchronization. No game-video encoding service |
| All Pi RAM is available for the extension | Rejected by real host observation: existing services use substantial memory | Bound state/Redis/queue bytes and measure combined load; no allocation based on total RAM alone |
| Five and ten floor actors impose a large CPU cost by themselves | Narrow synthetic counter-evidence on the real Pi | Low floor-update/JSON cost is encouraging; full auth, projection, Redis, sockets and LIA interference still need profiling |
| Current infrastructure supports atomic bounded admission | Primitive exercised on real development Redis with four clients and concurrent requests | Keep atomic admission/FIFO and stale-controller fences; production ticket/reservation/auth protocol still needs tests |
| A tab equals a player, or invitations need a second slot | Rejected by confirmed scope; duplicate-account primitive exercised | Account admission shared across tabs/devices, one controller, no extra world instance for a home |
| Existing peers supply durable online/app/world presence | Not source-supported; peer connections and relay permissions are different contracts | Add bounded app/world leases, consent and unknown/away states; do not infer presence from a last message |
| Everyone in the world is automatically an accepted peer | Rejected | Common-world admission and eligible direct social text have their own authority; relays/shares/visits retain existing peer checks |
| Several API workers may independently simulate the same public world | Unsafe; current Pi API runs multiple workers | One fenced authority/epoch for the shared world; test two-process takeover and stale delivery |
| Existing SSE can be treated as a bidirectional movement transport | Rejected by transport semantics | Keep existing assistant SSE; add dedicated bounded world WebSocket and REST bootstrap/tickets |
| A 2.5D sprite engine is automatically cheaper than simple 3D | Not established; both synthetic browser probes were viable | Provisional Pixi 2.5D direction, equivalent-art modest-device comparison before final selection |
| Desktop RTX measurements prove phone fluency | Rejected | Real Android, iPhone/Safari and integrated-GPU desktop qualification required |
| A larger scrolling map requires loading/rendering everything | Not required by the design | Chunk/atlas ownership, bounded nearby assets, explicit occlusion and recipient visibility; minimap uses authorized neutral data |
| Camera exploration gives authority to move/interact anywhere | Rejected; camera transforms exercised independently | Server interaction-distance and grant checks remain mandatory, including beyond the visible scene |
| Current BIP supplies a ready-to-use game walk rig | Not source-supported: existing body WebP and facial/acting rig are a reuse identity | Author directional walking/interaction animation and budgets; autonomous navigation must not call a model |
| Current room personalization can directly consume every profile/memory fact | Rejected | Eligible curated motifs with provenance, explicit selection and neutral omissions; no invented exhaustive biography |
| Opening decor may reinforce memory usage or interests | Rejected as a required behavior; existing active-set predicates passed targeted tests | Projection has no read reinforcement/extraction/habit side effect; assert counters across repeated load |
| Source-change hints cover every mutation and background producer | Not established by current invalidation code | Recompute current selector/digest on load/reconnect; reconcile visible owners and preserve manual locks |
| Denying private buttons is sufficient for guest privacy | Rejected: decor itself may reveal sensitive facts | Separate server-authored neutral guest blueprint with compatible collision geometry, not a hidden owner payload |
| Existing calendar/memory/other APIs may be bypassed by game objects | Rejected | Stations compose current owner hooks/services and existing assistant/approval flows; prove actual app side effects per station |
| A source inventory proves every pending application-tool binding is released | Rejected by extensively modified checkout | Freeze integration snapshot in L0; qualify each binding rather than trusting filenames/HEAD alone |
| Weather/day-night must be globally identical to avoid positional desync | Rejected | Personal visual atmosphere over shared geometry; cached genuine weather or honest neutral state |
| Existing cached weather guarantees fresh weather forever | Rejected; targeted companion tests passed their narrower contract | Keep freshness/permission checks, no paid refresh loop; explicit refresh uses ordinary cost policy |
| Walking, NPC behavior and personal decor need LLM calls | Not required; deterministic architecture retained | Zero ambient model calls and zero learning ingestion, except explicit assistant acts/paid weather requests |
| All human chat is necessarily model-free | Revised after owner language requirement | Same-language transport is model-free; differing configured languages trigger dedicated accounted translation |
| UI URL/cookie and persisted language are always identical | Rejected by header selector failure path | Canonical account preference and failed-save reconciliation; invalidate pending variants on language revision |
| Existing translation mechanisms remove the need for a new independent slot | Patterns exist, but not the required world contract | Add world-message translator vocabulary/registry/defaults/config UI; reuse infrastructure, not an unrelated service wholesale |
| Radio or broadcast fallback to original meets before-display translation | Rejected for the new default | Pending/unavailable localized state; explicit original access only. Preserve original and never fabricate a translation |
| Translation quality, latency and costs are already proven by precedent tests | Not established | New faithful corpus, configured model window/timeout, actual accounting and all supported directions must be qualified |
| One target language per recipient requires separate paid calls | Rejected by proposed batching scope | Reuse one variant per message/unique target language; strict owned attempts are required. Existing shared_flight does not guarantee paid deduplication, and uncertain external completion must not trigger an automatic repeat |
| A translation cache may be shared beyond the authorized recipients | Rejected | Owner/scope/version/language keys, bounded lifetime, no private text in telemetry, authority recheck before delivery |
| Existing account export/delete automatically includes new world data | Rejected until registration exists | Register persistence/derivatives/runtime teardown explicitly; real database deletion/export tests |
| A canvas alone supplies accessible functional use | Rejected | Existing localized DOM controls, non-spatial equivalent, focus/IME handling and real screen-reader qualification |
| Written scenarios and generated art count as passed world tests | Rejected | Existing test passes and isolated proofs are separately labeled; no new world-feature test has passed yet |

All reuse assertions in this ledger are tied to the source map in the analysis. No future hypothesis is labeled fully proved by inference alone. Privacy, asset and retention limits, lease/timeout values and quality ceilings are proposed contracts until their explicit oracles pass.

## 3. Existing regression tests exercised

All following targeted runs completed successfully. No live paid application LLM was invoked. Provider tests use their existing doubles. Initial tokenizer initialization required a public encoding download; that is distinct from a paid model request. No full CI/coverage or implemented-world certification is claimed.

| Existing family | Execution boundary | Result |
|---|---|---|
| Companion environment, companion context, application state synchronization, CSP and settings sections | Five Vitest files inside Docker dev web, effective API URL blanked | 201 passed |
| Companion environment, peer models/service/connection release, active-memory predicates, cost-bearer declaration and instance budget enforcement | Seven backend files, current host venv, no coverage | 124 passed |
| Language settings, selector and language matching | Three Vitest files inside Docker dev web | 12 passed |
| Radio article translation, language naming and canonical declared languages | Three backend files, current host venv, no coverage | 106 passed; collection independently confirms the count |
| Total existing targeted tests | Different existing boundaries, not a world suite | 443 passed |

Exact file selections and commands are in the reproduction notes. These passes confirm useful prerequisites and regression baselines. They do not prove that a world route is mounted, that a translator slot exists, or that a guest cannot receive private bytes in an unimplemented protocol.

## 4. Admission and fairness: real Redis primitive

The [standalone admission probe](assets/2026-10-09-lia-world/evidence/admission_probe.py) used four independent Redis clients against development Redis database 15. Each run created only four exact UUID-prefixed keys, bounded them with TTL, and deleted its own keys in `finally`. It did not flush a database, modify application key families, or contact production Redis.

Seven assertions passed:

1. Five slots under 100 concurrent admission requests.
2. Ten slots under 100 concurrent admission requests.
3. One account making 100 requests consumes one slot.
4. A queued account retains FIFO position; retries/newcomers do not jump the head.
5. An old controller fence cannot release a newer admission.
6. Expired entries are pruned atomically, without relying on key-expiry events.
7. Reducing the cap pauses new admissions without ejecting current accounts arbitrarily.

This proves these Lua primitives under the fixture. It omits expiring offers/reservations, authentication, visibility consent, queue disconnect cleanup, cancellation, real independently running world owners, socket recovery and Redis failover. The probe passes a trusted test clock; the production authority must own time. L4/L5 keep the complete oracles, including malformed/replayed tickets and two-process stale ownership.

## 5. Real Pi observations and synthetic CPU measurement

A bounded SSH observation of the configured host found an ARM64 machine with approximately 16 GB installed and 7 GB currently available. Existing production, demo and observability services are co-hosted. The API reports four workers. The observation captured 47.2 degrees Celsius and a zero throttling flag. The two short interval samples were mostly idle and showed no swap-in/out; allocated swap was about 1.2 GB. Swap occupancy alone does not prove present memory pressure. These are a quiet snapshot, not peak capacity.

The [CPU-only probe](assets/2026-10-09-lia-world/evidence/server_tick_probe.py) then ran as one short subprocess inside the actual production API container. It read no application data and created no files, network connections, provider calls, Redis keys, or database writes. It was bounded by a three-second limit and completed in under one second. It calculated a simple floor update and per-recipient JSON for 2,000 iterations per population.

| Synthetic population | Median / p95 work per tick | Mean aggregate JSON per tick | Estimated one-core work at 10 ticks/s |
|---|---|---|---|
| Five | 0.089 / 0.095 ms | About 1.6 kB | About 0.09% |
| Ten | 0.311 / 0.322 ms | About 6.6 kB | About 0.31% |

Maximum subprocess RSS was about 15 MB. Exact observations are recorded in the measurement JSON. This narrowly supports the feasibility of small deterministic state updates. The estimate excludes actual authorization, Redis, fan-out transport, encryption, snapshot/interest logic, scenery editing, assistant traffic, translation traffic and concurrent LIA load. It is not a capacity pass for ten users, a measured WebSocket latency, or an argument to consume all available memory.

The launch recommendation remains five, with ten gated by a realistic combined workload and reserve. Test ordinary API/SSE latency and resource budgets alongside translation and world activity, including slow clients, queue storms, restart and radio/voice interference. No production deployment/restart occurred during characterization.

## 6. Browser renderer, navigation and input probes

The [Pixi probe](assets/2026-10-09-lia-world/evidence/probe.html) and [Three probe](assets/2026-10-09-lia-world/evidence/three-probe.html) were separate localhost pages, outside Next application source. Pinned browser distribution files were downloaded only into ignored scratch space. No renderer package was added to LIA manifests/lockfiles. The available Chrome reported ANGLE on an NVIDIA RTX 4090: this is a powerful desktop client, not the minimum target.

The Pixi fixture used 1,024 floor sprites, 200 simple props, ten avatars and the current BIP body illustration, approximately 1,235 objects and four textures. The Three fixture used instanced floor/prop boxes, an orthographic camera and simple avatar/BIP meshes. Neither used the detailed generated scene, production animated atlases, expensive shadows, a physics engine, authenticated accounts, WebSockets, or real application panels. Their visual complexity is not equivalent enough to rank engines conclusively.

Short `requestAnimationFrame` samples were observed, not long thermal soaks:

| Observation | Median / p95 frame interval | Interpretation |
|---|---|---|
| Initial Pixi, five avatars | 51.5 / 52.8 ms | Slow, about 19 FPS; retained as an unresolved observation |
| Initial Pixi, ten avatars | 52.0 / 53.2 ms | Similar slow observation; not silently discarded |
| Later stopped-render baseline | 16.7 / 16.8 ms | Available scheduler/display reference |
| Later Pixi, ten avatars after reload | 16.7 / 16.8 ms | About 60 FPS on this desktop only |
| Three, five avatars | 16.7 / 16.8 ms | 13 draw calls, about 15k triangles on this simple fixture |
| Three, ten avatars | 16.7 / 16.8 ms | 23 draw calls, about 16k triangles on this simple fixture |
| Pixi at a 390 x 844 desktop viewport | 16.7 / 16.8 ms | Layout exercise on the same RTX; not phone performance |

The cause of initial Pixi slowdown was not established. This forbids a claim of stable fluency or a measured 2.5D advantage. The samples show that both approaches can produce a basic scene, while the real choice requires equivalent authored detail, cold/warm behavior and real modest devices.

Functional checks within the disposable Pixi fixture also passed:

- Isometric projection/unprojection of 1,000 grid points had zero error for this transform.
- The narrow viewport had no horizontal page overflow; canvas resized to the available space.
- Held-arrow input advanced the probe input counter; focusing the text input cleared keys and stopped input advancement.
- Zoom changed from one to 1.2; minimap exploration selected a free camera at the map center; recenter restored follow mode.
- The scene is larger than the viewport and follow tracks a synthetic moving avatar. Camera exploration is independent of that avatar.

The input counter is not complete avatar movement physics. Touch pinch, mobile keyboard/visual viewport, walls/stairs/occlusion, context-loss recovery, actual screen readers, long memory soak, the Next/WebView lifecycle and device thermals were not exercised. A favicon 404 on the scratch server had no bearing on the engine resources.

The modest-device proposal is pixel ratio one, 30 FPS, authored lighting, limited ambient effects, nearby assets and a decoded texture budget around 64 MB; desktop may raise resolution/detail and target around 128 MB. These are tuning ceilings to characterize, not universal guarantees. Renderer guidance supports batching, measured texture ownership and limiting expensive effects: [Pixi performance guidance](https://pixijs.com/8.x/guides/concepts/performance-tips), [Three instancing](https://threejs.org/docs/pages/InstancedMesh.html) and [WebGL best practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices).

## 7. Localization and translation: inspected reuse and hidden limits

The canonical user preference is stored in [users/models.py](../../../apps/api/src/domains/users/models.py). [Core i18n](../../../apps/api/src/core/i18n.py) supplies normalization, canonical language names and task-local language context. [LanguageSettings](../../../apps/web/src/components/settings/LanguageSettings.tsx) persists the preference. The [header selector](../../../apps/web/src/components/LanguageSelector.tsx) can continue a URL/cookie language change after a failed persistence request; therefore a foreign request/URL is not a safe canonical translator routing authority. This is a characterized limitation to reconcile, not a fix made during this analysis. The [frontend language matcher](../../../apps/web/src/lib/language-match.ts) handles language equivalence but treats absence permissively; missing language must be resolved explicitly for a translation job.

Existing mechanisms provide two useful precedents:

- [Radio articles](../../../apps/api/src/domains/radio/articles.py): a dedicated structured translator, owned call context and token/cost tracking, plus shared article flights. Its recipient billing, article schema, long timeout and original-text fallback are not the world chat contract.
- [Administrative broadcasts](../../../apps/api/src/domains/notifications/broadcast_service.py): one translation variant per target language for multiple recipients, versioned prompt and actual deployment-spend recording. It is deployment-funded administrative distribution with free-form output/original fallback, not an account-initiated social message. Do not reuse its billing or disclosure rules by accident.

The world should reuse configuration/factory/tracking and underlying owned-claim infrastructure, with a dedicated strict attempt lifecycle rather than shared_flight's permissive build-on-failure policy. Introduce a separate `world_message_translator` slot through the [registry/defaults](../../../apps/api/src/domains/llm_config/constants.py) and [factory type vocabulary](../../../apps/api/src/infrastructure/llm/factory.py), with six-locale admin metadata and a versioned faithful-translation prompt. Resolve the actual instance model/configuration snapshot; a repository default is not the deployed model. No provider/model choice was silently hardcoded or added here.

Before-display flow: authorize immutable original and recipients; obtain canonical language revisions; create one owned flight per needed unique target language; check sender and instance spend ceilings; call the dedicated structured translator; validate bounded output; record actual call usage including paid failures; recheck authority/language; then publish the eligible variant in order. Translation waits do not freeze movement. Same-language messages incur no translation call. Source text is untrusted human content and supplies neither model instructions, tools, personality, assistant conversation history, nor automatic memory extraction.

Pending/unavailable state is localized. The original is available by deliberate action and is retained according to the chosen message lifecycle. No automatic wrong-language fallback, invented delivery receipt or fabricated translation. Revised provisional target: immediate pending indication, translated-display p95 around three seconds, total hard deadline around eight seconds, one paid attempt per request with bounded concurrency and explicit UTF-8/token/window caps. An unresolved external outcome prohibits automatic repeat. These values need the configured-model probe. Reject oversized input before spending; do not silently trim people's words. Grouping variants reduces physical calls but does not make them free.

Proposed sender billing reflects who initiated the exchange and avoids arbitrary recipient charges. Record one receipt per physical translation; a shared cache result does not incur duplicate spend. This policy must cover language changes/retries and block mid-flight without hiding already-paid failures. If the owner chooses deployment billing, change the declared spend road and gates explicitly before L7b. Pricing comes from actual usage and the captured configuration, not the illustrative images.

When sending through the existing asynchronous LIA peer relay, retain that distinct assistant-mediated path and its normal rules; the inspected [peer tool manifest](../../../apps/api/src/domains/agents/peer/catalogue_manifests.py) already distinguishes the recipient assistant's voice/language. Do not replace relay prose or charge a redundant world-chat translation by default. Add a delivery-language characterization to its actual recipient boundary during L10; the new direct human chat keeps faithful authorship instead of assistant mediation.

The 106 existing radio/i18n tests validate prerequisites, not the new live translator. New fidelity tests must include negation, names, dates, numbers, links, code, mixed-language text, hostile instructions, truncation, malformed structure and every supported language direction. Real quality and latency remain unqualified until a bounded model-specific corpus is exercised.

## 8. Five representative visuals and art decisions

The [gallery](assets/2026-10-09-lia-world/index.html) preserves full-resolution images and explains their intended contracts:

| View | Intended validation | Material limitation |
|---|---|---|
| [01 — Spacious gameplay](assets/2026-10-09-lia-world/01-world-gameplay.png) | Normal game scale, room to walk/meet, only part of the world visible, minimap and neutral LIA shell | Asset direction, not a runtime draw-cost or complete map |
| [02 — Private calendar station](assets/2026-10-09-lia-world/02-calendar-private.png) | Thematic setting and real-function/private interface composition | Example values; actual domain/HITL/API behavior remains to implement |
| [03 — Owner and guest home](assets/2026-10-09-lia-world/03-personal-home-guest.png) | Owner personalization versus neutral timed-visit visibility | Network projection and collision compatibility need complete tests |
| [04 — Mobile gameplay](assets/2026-10-09-lia-world/04-mobile-gameplay.png) | Partial-world framing, upper-right map, touch commands, personal night/weather | Static illustration, not a native-device performance result |
| [05 — Multilingual exchange](assets/2026-10-09-lia-world/05-multilingual-chat.png) | Per-user localization and translation/original affordance | Generated bubble/identity/marker correspondence is illustrative and must be normalized in actual UI |

Earlier dense world/mobile compositions were superseded after the owner's spacious-game feedback; they are not the final gallery direction. Preserve the attractive architectural volumes, warm materials, restrained animations and clear paths; avoid encoding a whole city into one screen. Artwork is intentionally friendly and authored, with voxel/block inspiration and finer forms, not photorealism. The owner can still refine how cubical versus rounded characters/props should be. BIP remains masculine, identifiable and privately responsive to the owner.

Some concept signs contain readable lettering. Production localized labels must be DOM/renderer text over language-independent artwork, not permanently baked French textures. Generated UI and illustrative message alignments are not authoritative specifications. The established app conventions, accessible controls and source-backed contracts govern implementation.

## 9. Remaining qualification and final self-assessment

The next concrete work is L0/L1: freeze source/art scope, build one representative playable zone with directional BIP, and measure on a modest Android, an older supported iPhone/Safari and an integrated-GPU desktop. Compare equivalent Pixi/Three detail. Then qualify the small multi-account vertical slice for admissions, authority, direct/translated delivery and protected homes before filling out the map. Follow the main dossier's atomic lots and 72 mandatory scenarios.

| Requested assurance | Verdict after characterization |
|---|---|
| Existing reuse claims confronted and counter-checked | Yes for the claims documented in the source map; newly found language/broadcast limits are explicit |
| Hosting and product scope coherent | Yes; browser rendering, one world, spacious navigation, five-to-ten and multilingual text are integrated |
| Tokens, costs, registries and responsive constraints framed | Yes at proposed-contract level; actual new translator and hardware budgets still need their oracles |
| Foundation/prototype development can begin immediately | Yes, with the main dossier's explicit dependencies, proposed defaults and first failing tests |
| All future behavior, privacy and performance empirically validated | No; future code/art boundaries and physical devices cannot be certified by source inspection or generated images |
| Complete solution guaranteed at 100% | No; such a claim would overstate the evidence |

The refreshed task lint:docs:preview found no broken living links, stale living paths, living orphans or quoted-fact drift. It still fails on the same six pre-existing unrelated technical-map coverage gaps, detailed in the reproduction notes. This is a qualified documentation result, not an all-green repository gate; concurrent source changes are preserved.
