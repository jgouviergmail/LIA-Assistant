# Deterministic HTML cards in assistant answers

The assistant renders received data as domain cards in the HTML-card and rich-HTML-with-cards display modes. The shared presentation makes the first useful facts easy to scan and keeps complete supplied detail reachable through native disclosures. Existing action approvals, source ownership and provider capabilities remain authoritative.

This guide describes the current chat contract; the decisions behind it are recorded in [ADR-332](../architecture/ADR-332-Deterministic-Cards-Received-Facts-And-Message-Owned-Actions.md). [CARD_SYSTEM.md](CARD_SYSTEM.md) also documents the general React cards and historical CSS vocabulary.

## Architecture and extension points

The response path is tool output → typed registry → selected card payload → deterministic renderer → persisted assistant answer → SSE → Markdown sanitizer → small React enhancements. The same archived answer uses the same sanitizer and enhancement layer when opened again.

| Responsibility | Authority |
|---|---|
| Registry types, metadata and JSON persistence | [data_registry/models.py](../../apps/api/src/domains/agents/data_registry/models.py) |
| Restoring display-only fields for a card | [card_payload.py](../../apps/api/src/domains/agents/data_registry/card_payload.py) |
| Domain aliases and renderer coverage | [component_registry.py](../../apps/api/src/domains/agents/display/component_registry.py) |
| Shared collection disclosures | [card_collection.py](../../apps/api/src/domains/agents/display/card_collection.py) |
| Safe titles, full text and known Yes/No facts | [card_content.py](../../apps/api/src/domains/agents/display/components/card_content.py) |
| Presence-aware measurements | [values.py](../../apps/api/src/domains/agents/display/values.py) |
| HTML and URL escaping | [escaping.py](../../apps/api/src/domains/agents/display/escaping.py), [urls.py](../../apps/api/src/domains/agents/display/urls.py) |
| Shared appearance, motion and touch targets | [lia-cards.css](../../apps/web/src/styles/lia-cards.css) |
| Chat markup allowlist | [markdown-sanitize-schema.ts](../../apps/web/src/lib/markdown-sanitize-schema.ts) |
| Frontend enhancement entry point | [MarkdownContent.tsx](../../apps/web/src/components/chat/MarkdownContent.tsx) |

Cards inherit the application's foreground, surfaces, borders and font through the versioned response wrapper. Their domain colors retain their semantic role. The stylesheet isolates the new presentation from historical markup and HITL/widget surfaces. It supports light, dark and OLED themes, narrow phones, long untranslated source strings and enlarged text. Motion communicates disclosure or image state, respects reduced-motion preferences and does not cause cards to shift on hover. Native details retain keyboard operation and readable fallback content without JavaScript. Labels use the shared locale separator, including French no-break spacing and Chinese full-width punctuation.

When adding a domain, register its aliases once, use the shared title/text/detail primitives and test the actual producer through registry JSON serialization. Do not add a generic dump of provider transport objects to a domain card. Rich optional fields belong in a cohesive details helper; the recurring canonical context remains intentional.

## Data fidelity and interaction policy

A missing measurement, zero and false are different states. A renderer does not infer an unavailable fact from absence, fabricate a default time, collapse zero costs, or use a technical provider identifier as a human name. External text is escaped; third-party HTML is read as text. Complete received prose remains accessible behind the same disclosure affordance rather than silently truncated.

| Domain | Presentation and useful detail |
|---|---|
| Email | Complete body, parties, attachments and source link; authorized reply/forward composition where the source account can be verified |
| Contacts | Received names and pronunciation, every organization with supplied civil employment dates/current state, phones, addresses, birthdays, notes and source links |
| Calendars/events | Visible calendar alias and original name, access including restricted private details, received owner/location/notification preferences, known selection/hidden states, reminder methods, source-aware clocks, civil all-day dates, attendees, every supported conference join point and recurrence facts |
| Tasks/reminders | Full notes, received subtasks and completion, explicit provider state, stored reminder recurrence and owner's source timezone |
| Files | Full description, owners, permission roles/identities, supplied availability/sharing/version/download facts and supplied thumbnail previews |
| Places | Received photos with attribution, keyboard/touch gallery and fullscreen, full reviews, service flags, opening periods and source timezone |
| Routes | Whole journey, legs, steps, transit and supplied alternatives, tolls/waypoints and complete Maps destinations |
| Weather | Received forecast slots, comparison controls, finite measurements and source time; attribution is preserved |
| Research | Complete received extracts, article sections/categories, sources and citation ordinals tied to their original valid destinations |
| Hue | Read-only state and brightness meter, valid supplied color temperature/device range and exact CIE coordinates |
| Tickets | Shared status/priority/assignment summary; full reads retain description, steps, comments and known run outcome/cost/token usage |
| MCP | Bounded public JSON snapshots, source-authored server identity, binary metadata and explicit redaction/limit indicators |

This is a policy for **received** information, not a promise that every list endpoint requests every provider field. Provider masks and detail operations keep their established scope. Internal credentials, raw binary bodies, private orchestration fields and unsupported technical records are deliberately excluded. No new light command, ticket action, provider fetch or model call is caused by opening a disclosure. Google conference identifiers and signatures do not serve as join information; only the supplied public entry points and their access codes do.

Microsoft native recurrence patterns remain native facts instead of a lossy invented RRULE. The [source recurrence renderer](../../apps/api/src/domains/agents/display/components/source_recurrence.py) uses the shared recurrence vocabulary when a faithful description is supported and a bounded source view otherwise. Source clocks pass through [time_parsing.py](../../apps/api/src/core/time_parsing.py); explicit offsets are authoritative and ambiguous/unknown zones are not silently interpreted as UTC. An all-day provider date remains a civil date even when the registry adds a clock alias for cross-domain binding.

### Document previews

Drive cards display an actually supplied thumbnail for every supported file family, with the existing image proxy/authentication path and a link to the source. A missing thumbnail does not cause another provider query.

Generated documents use a small read-only preview through the attachment owner/status/expiry checks. PDF previews contain the first page and can expand in the shared keyboard-accessible lightbox. CSV shows a bounded table excerpt and Excel the opening rows of its first sheet; text and Markdown show literal source text; Word shows opening paragraphs and PowerPoint its cover slide. Excerpts are explicitly named as such, and the original opening/download actions remain available. Preview errors never remove those actions.

The preview service reads only known generated formats, confines disk paths to the storage root, limits source/output/XML/archive sizes, caps parser concurrency and applies the existing per-user HTTP limiter. Text reads begin near the viewport and abort on unmount or timeout. Office XML uses the existing protected parser without evaluating formulas or external entities. MuPDF runs in a separate process with a hard timeout and resource bounds because [PyMuPDF does not support threaded use](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html). Preview responses are private and not cached; preview bytes never enter model history, registries or prompts. No model or paid provider call is introduced.

Preview reads follow the original document's access even when uploads are disabled, including the demonstrator. They do not enable uploads or document generation. Credentialed text reads use the shared API client and its error/cancellation rules; only the truncation boolean is exposed across origins. A late thumbnail failure keeps an open PDF lightbox and preserves focus on its retry control when the reader closes it.

### Interactive route maps

The provider's exact polylines and original route identities travel only in the
bounded `meta.display.route_map` projection, never in planner bindings or model
history. The versioned HTML marker is decoded and validated again in the browser.
Malformed, excessive or incomplete geometries retain the ordinary source facts
and static preview; omitted siblings are stated explicitly. The computed primary
may occupy any provider slot. Alternatives use the existing computed geometry:
selection never calls Directions, Places or geocoding.

Activation is explicit and shows the configured unit estimate before loading.
One shared Maps JavaScript SDK serves the page. Each activated map draws all valid
alternatives, highlights the selected path and names its own distance/duration;
the existing detailed primary summary remains identified as such. Controls use
native buttons, preserve focus while pending and dispose overlays/listeners on
unmount. A late admission or SDK reply cannot attach to a replaced message.
The official compact map-type menu offers roadmap, satellite, hybrid and terrain
backgrounds. It retains the existing route overlays and selection; changing the
background does not reconstruct the map or recalculate an itinerary. This follows
the [Maps JavaScript controls contract](https://developers.google.com/maps/documentation/javascript/controls).

Maps JavaScript reuses `GOOGLE_API_KEY`, as explicitly chosen for this deployment.
`GOOGLE_MAPS_BROWSER_API_KEY` is an optional override for deployments using a
separate browser key. The selected key is necessarily visible in the browser's
SDK request; it is released only through authenticated, budget-gated admission,
never in public configuration or a `NEXT_PUBLIC_*` variable. Enable Maps JavaScript
API on its Google project and use restrictions compatible with the selected key.
The pricing catalogue must also contain the active `maps_javascript` / `/dynamicmap`
entry. The pricing seed declares it for a fresh install; migration `ef46f93d7745`
adds it to an existing installation where the endpoint has no active price, and
never over one an administrator set. An administrator edits it in the Google API
pricing manager, whose Reload Cache action invalidates all worker caches; saving a
price alone does not reload them. Until the key and the price are both present, the
public configuration offers no activation.

Admission uses the authenticated account, existing instance/account budget checks
and a per-user rate limit. A short-lived signed grant binds the report to that
account. Retried or simultaneous reports share a PostgreSQL transaction lock and
one durable tracking run. Strict persistence withholds acknowledgement on failure;
the browser retries the same grant with keepalive and offers recovery without
constructing another map. This uses the existing cost ledgers and adds no schema.

These records measure **browser-observed Map construction**, not a Google invoice.
A killed/offline browser can lose its report, and a public SDK key cannot impose
the application's per-account limits at Google. Restrict the key and configure
Cloud quotas; reconcile Cloud consumption when enabling the feature. The estimate
uses the configured unit price, not Google's account-specific free tiers or volume
discounts. SDK authentication, real Cloud restrictions and invoicing still require
deployment acceptance; hermetic tests do not claim to verify those external facts.
The CSP adds only the exact Maps SDK script/connect hosts to the app policy.
Deployment acceptance must run the real SDK under the production CSP too;
mocked SDK journeys do not validate Google's entire resource graph.

### Glass overlays and notifications

Dialogs, confirmations, menus, selects, tooltips and viewer controls use the
shared material in [lia-overlays.css](../../apps/web/src/styles/lia-overlays.css).
The surface uses existing theme tokens, a static reflection, a tinted border and
a bounded backdrop filter. The screen dimmer has no filter. Opaque paint is the
default; supported browsers add transparency. Reduced transparency and forced
colors restore an opaque surface, and reduced motion removes decorative
transitions. OLED follows the application's dark tokens.

Notifications use Sonner's supported `unstyled` boundary so its unlayered native
paint cannot override this material. Sonner still owns lifetime, stacking,
announcements, swipe and actions. Semantic accents tint the icon, border and
surface; titles and descriptions retain readable theme foregrounds. The previous
fixed minimum width is removed, and close/actions have touch-sized targets.

Manual modal openers return focus to the previously focused control when it
still exists. Explicit caller focus callbacks take precedence. Non-modal
outside-click focus retains Radix's existing contract. Select viewports are
keyboard-focusable option groups, and menus use Radix's available-height bound.
The image viewer keeps download controls focusable while unavailable and guards
duplicate activation synchronously; neither preview retries nor download retries
regenerate an assistant response.

No provider call, prompt, state schema or persistence change belongs to this
presentation layer. Browser qualification checks actual loaded paint, contrast,
geometry, keyboard return, narrow viewports and supported system preferences;
CSS class assertions alone do not establish a working visual result.

## Model context, persistence and budgets

Display-only fields live in registry metadata. [model_history.py](../../apps/api/src/domains/agents/display/model_history.py) attaches a versioned semantic view to the assistant message; subsequent provider/history/compaction paths use [message_view.py](../../apps/api/src/infrastructure/llm/message_view.py). They preserve selected canonical facts without replaying card HTML, images, private action context or display-only trees as recurring prompt content. External facts retain their trust wrapper. The HTML answer remains available to the person and to existing copy/export flows.

Consequently presentation changes do not buy another synthesis call or expand the prompt with decorative markup. Existing token counting, slot context windows, tool-result budgets, quota accounting and provider rate limits stay in their owning services. Actual compact facts that enter canonical context, such as the supported native recurrence pattern or a calendar's visible name, continue through those budgets.

Media enrichment remains on the authorized proxy path. Shared admission is checked before provider work; owner/turn/source binding and private caching are retained. Gallery opening does not preload an entire collection. Its received-photo cap and loading behavior are defined in [place-photos.ts](../../apps/web/src/lib/place-photos.ts) and [use-place-gallery.ts](../../apps/web/src/components/ui/use-place-gallery.ts). Image-load hints are bounded metadata in [image-cache.ts](../../apps/web/src/lib/image-cache.ts), not a new store of image bytes.

MCP snapshot budgets and credential exclusions are defined in [mcp_details.py](../../apps/api/src/domains/agents/display/components/mcp_details.py) and [credential_fields.py](../../apps/api/src/core/credential_fields.py). They bound tree depth, node/character work and parse size. Named-field redaction does not claim to detect every secret embedded in arbitrary prose. MCP App frames continue through their existing sandboxed widget path rather than the Markdown allowlist.

## Message-owned composition

A composition affordance is server-selected and tied to the assistant answer that displayed the source. [card_actions.py](../../apps/api/src/domains/agents/display/card_actions.py) creates the action contract; [card_composition_service.py](../../apps/api/src/domains/agents/services/card_composition_service.py) verifies answer ownership, current conversation/run, canonical source and account grant. The request uses the typed chat context envelope; transient composition state is cleared after the request.

The frontend stores draft text and its composition context together for the current account. A pending retry retains its original immutable target. Replacing an existing composition requires the established explicit confirmation. Reply/forward or reminder adjustment prepares a request/draft; it does not send or execute automatically. HITL, modification, resume and provider refresh/retry paths recheck the same binding. Disconnected or changed accounts cannot silently act through another grant. Gmail cache namespaces follow the verified grant. Sources without a sufficient structural account/mailbox binding do not offer the action.

The model sees the versioned [composition directive](../../apps/api/src/domains/agents/prompts/v1/card_composition_context.txt) with the verified target and provider, not an arbitrary instruction extracted from card HTML. Private transport metadata does not become user prose or persist as a future instruction.

## Regression strategy and operational limits

| Risk | Evidence required |
|---|---|
| A fixture bypasses a real producer omission | Real tool/mixin → registry → JSON round-trip → renderer fixtures |
| Facts disappear, zeros become absent or malformed siblings hide valid data | Fidelity tests with explicit false/zero, empty/missing, nonfinite/huge values and hostile nested fields |
| XSS, unsafe URLs or private context escape | Backend escaping/projection witnesses plus the real frontend sanitizer; source ownership and grant refresh/retry tests |
| Wrong date, recurrence, source ordinal or user target | Source-clock/all-day/DST tests, recurrence contracts, citation ordinal tests and immutable composition retry/HITL tests |
| Unbounded rendering, cache growth or provider costs | Existing linear-growth tests, bounded MCP snapshots/cache tests and pre-provider quota/media tests |
| Visual or keyboard/touch regression | Docker-served hermetic browser journeys, all themes, narrow viewports, enlarged text, reduced motion, disclosure/gallery controls and scoped axe checks |
| State or prompt contamination | JSON/msgpack round-trip, SSE/archive, semantic-history, compaction, ReAct, source trust and draft-context tests |

The shared [reference fixtures](../../apps/api/tests/helpers/card_reference_cases.py) generate the checked-in corpus used by frontend and browser tests. [test_card_reference_corpus.py](../../apps/api/tests/unit/domains/agents/display/test_card_reference_corpus.py) refuses drift between that corpus and real backend output. Additional composition fixtures exercise the separate authorized-action contract. The directory [display tests](../../apps/api/tests/unit/domains/agents/display) contains domain-specific fidelity and degraded-input witnesses; [chat-native-details.spec.ts](../../apps/web/e2e/smoke/chat-native-details.spec.ts) exemplifies stored-answer validation through the actual UI.

Run the repository's Taskfile gates, including lint, i18n, shrink-only complexity/file-size checks, marker coverage, backend/frontend coverage and documentation preview for unindexed files. Do not raise a threshold to clear a regression. Preserve independent working-tree changes when qualifying the branch. Browser suites use mocked API/SSE/media boundaries and do not authorize paid calls or writes to the owner's data. Database integration requires an explicitly disposable test database.

Automated checks support the delivery; they do not replace the owner's visual acceptance on Docker dev.

## Provider references

- [Microsoft Graph recurrence pattern](https://learn.microsoft.com/en-us/graph/api/resources/recurrencepattern?view=graph-rest-1.0)
- [Google Calendar event reminder and conference fields](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Google Calendar reminder behavior](https://developers.google.com/workspace/calendar/api/concepts/reminders)
- [Google Calendar list fields](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList)
- [Google People organizations](https://developers.google.com/people/api/rest/v1/people#Organization)
- [Hue API](https://developers.meethue.com/)
