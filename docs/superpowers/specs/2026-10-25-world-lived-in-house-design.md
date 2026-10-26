# Lived-in LIA house

This specification applies the owner's detailed room and interaction brief of 2026-10-25. The owner accepted the improved visual direction of the connected-house iteration. Preserve its warm isometric style, shared authoritative world, local private interfaces, modest-device rendering and inline worktree execution. The [initial analysis](2026-10-09-lia-isometric-world-analysis.md) and [connected-house revision](2026-10-24-world-connected-house.md) remain the broader context.

## Authored experience

| Place | Required composition | Private application access |
|---|---|---|
| Central hall | Larger than standard; white marble, indoor plants, central fountain and inward-facing three-person benches | Social meeting point |
| Meeting room | Carpet; professional decoration; long table with three chairs on each long side and an end chair; paper and pen at each place; wall display and corner plants | Meetings from the table |
| Multimedia | Larger, vivid; billiards, three animated arcade cabinets, posters, plants, opposing sofas and coffee table; four distinct easels with chairs; drawing table with brushes and two chairs | Generated images, documents, screenshots or bookmarks by easel/associated seat; drawing table/seat opens a localized unsent image-generation draft |
| Phone booth | Small; wall phone and chair, side table with call book, plant | Phone/seat opens a localized unsent call draft; book opens recent calls |
| Memory archive | Large; six writing desks with book, pen and chair; archival cabinets along walls | Memories from cabinets or desk seats |
| American cafeteria | Large; black/white floor, jukebox, bar, bottle shelving, plants, two pairs of red opposing booths and tables with drinks/plates | Existing radio control from jukebox |
| Engineering lab | Inventive machinery; three distinct work tables, two chairs each | Skills, personal MCP servers, plugins from tables or their seats |
| Gym | Mirrors, assorted exercise benches and dumbbells | Health from exercise benches |
| Divination room | Dark, mystical floor; crystal table with four chairs; black cat wandering inside | Scheduled actions from crystal/table or seats |
| Library | Full bookcases along walls; three reading tables and chairs | Knowledge spaces from shelves or seats |
| Restroom | Toilet with usable seat | SMS after confirmed sitting |
| Outside | Garden, kitchen garden, furnished front terrace/bar, loungers, parasols, pond, three tree families; daytime birds and sunny daytime butterflies | Existing contextual weather and other compatible outdoor accesses |
| Private studio | Adolescent bedroom; bed, digital alarm clock, computer desk and chair, plants, posters, secretary and chair, animated wall TV | Relations from computer/seat; workboard from secretary/seat; reminders from alarm; commitments from a promise board |

The promise board is an implementation choice: a recognisable cork board with pinned promise cards next to the secretary. Room geometry is authored once; semantic object keys and seat links are independent of coordinates.

## Interaction contracts

An object's hovered label must identify the exact function, including the generated-file family. The interactive cursor, approach distance, pathfinding and keyboard/touch equivalents remain shared. A seat may have a linked activity, but the activity opens only after the server acknowledges that exact requested pose. A refused/occupied seat, cancellation, takeover, reconnect or an old acknowledgment cannot launch it. Reconnecting while already seated does not reopen a panel.

Native data, edits, history, costs, quotas and HITL remain the application's existing contracts. Opening a draft never sends it. No LLM calls occur for navigation, animations or room personalization. File-family initialization is explicit component input; changing it does not rewrite the browser URL or contaminate later application navigation.

## LIA and transverse interface

Clicking LIA opens four clearly named choices: conversation, LIA journal, alerts and LIA psyche. Reuse the existing owned components; remain inside the world.

Widgets provide the existing radio start/stop command, smartphone, local date/time and weather, plus isolated settings. The smartphone distinguishes SMS from fired reminders with separate icons and counts. Opening it lists arrivals and offers a call draft. A reminder arrival is not inferred from a count of future reminders. Signals are account-owned, bounded, deduplicated, ephemeral and cleared on account change. Incoming content stays out of shared world state. Reduced motion replaces blinking with a static badge.

## Verified integration seams and work

- Native section identities already exist for skills, plugins, personal MCP, memories, scheduled actions, health, knowledge spaces, generated assets, recent calls, reminders and commitments.
- Generated assets currently read the initial tab from the URL. Add a typed optional initial tab for embedded use and retain normal page behaviour.
- Relations currently owns business UI inside its route. Extract a shared workspace and keep a thin route wrapper.
- Workboard already has a shared component, but writes navigation to its route. Add an embedded local-navigation mode with the same board/actions.
- Meetings settings contain preferences and templates, not the meeting workspace. The table must open the actual reusable meeting workspace.
- Alerts and the LIA journal already have reusable components. Embedded navigation must retain the world.
- Existing notification transport provides owner-qualified SMS signals and real reminder arrivals. Reuse it without inferring arrivals from upcoming counts.
- Existing radio command already owns start/stop and playback state.

## Quality and acceptance

Meaningful tests must cover every required object/seat binding, file filters, unsent localized prefixes, authoritative seat-trigger state, account change, availability gates, retained embedded navigation, malformed/duplicate notification signals and concurrent arrival types. Geometry checks cover room connectivity, clear approaches, distinct object identities, wall openings, seven meeting chairs and prescribed room inventories.

Real browser journeys must exercise object hover/click, linked seats, native panels, social conversation delivery, keyboard/mobile controls, three rendering engines, day/night/weather and reduced motion. Visual review includes close wall joints, chair orientation, object modeling, readable symbols, furnishings and outdoor life. Test counts do not certify artistic quality. Physical Raspberry Pi and phone measurements remain separately reported.

The qualification history, including earlier incomplete runs and their diagnoses, is retained in the [refinement report](../qualification/2026-10-25-world-house-refinement.md). Do not substitute a historical green count for qualification of the current source.


## Subsequent owner refinement

Keep a single connected building with useful room proportions rather than separated oversized halls. The central marble hall reaches the front terrace. Remove exterior left entrances and the left terrace. Move the restroom into the visible foreground, separate the studio by more planting and connect it with a short path.

Doors and approaches stay clear of furniture. Indoor lamps use small table supports; street lights belong outside. Plants occupy useful corners. Posters and wall-mounted objects require a visible full supporting wall, enough separation from windows and correct depth ordering. Avoid broad furniture overlaps.

The studio sofa faces the bed; omit its wardrobe; mount its television on the left wall and its commitments board on a wall. Place multimedia easels on the left wall and the telephone chair nearer the handset. Give the meeting screen a full wall opposite the head chair. Diner seats are red, checker squares larger and booths shifted clear of circulation; remove the unneeded divination cupboard.

Refine bars, jukebox, foliage, ground, vegetable beds and pond geometry. Keep the pond wholly in grass with no path through it. Each terrace table has two opposite chairs and a tall parasol beside it. Expand the green area for later activities; arrange benches and path lights deliberately.

Habits, news and weather belong respectively in the gym, cafeteria and engineering space. At night the exterior darkens and shows warm local lighting; interiors stay normally lit. Precipitation respects covered rooms. Double click/tap runs under the same authoritative movement rules as walking. Vary recurring models through bounded reusable families, and animate only with explicit quality/reduced-motion budgets.
