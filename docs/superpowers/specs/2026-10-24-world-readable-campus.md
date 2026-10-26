# Readable campus: revised world experience

The owner's later correction to the initial [world analysis](2026-10-09-lia-isometric-world-analysis.md) rejects the compact layout and repeated terminals as a finished experience. The world is one continuous instance; a place is a spatial district, never a separate multiplayer shard. Canvas 2D, isometric projection, cached art and bounded animation remain browser-side.

## Player-facing vocabulary

| Place | Recognizable object | Owned activity |
|---|---|---|
| Knowledge library | Open bookcase | Knowledge spaces |
| Connected workshop | Workstation and project board | Workboard, tasks, open loops |
| Personal retreat | Memory library, personal desk, bed | Memories, profile, lying down |
| Creative studio | Easel | Generated assets |
| Observatory | Brass telescope, news board | Weather and news |
| Post office | Letter box, telephone booth, message board | Email, telephone history, SMS |
| Planning pavilion | Calendar, clock, reminder board | Agenda, routines, reminders |
| Curiosity greenhouse | Herbarium, habits board, wellness table | Interests, habits, health |
| Writing room | Open journal on a writing desk | Personal journal |
| Meeting lounge | Conference table and connection board | Meetings and peer connections |
| Radio studio | Receiver and speakers | Native Radio, under its existing flag |
| Meeting garden | Fountain, shared seating and present people | Social approach and conversation |

This is a discovery vocabulary, not permissions. Existing native capabilities and the current account determine availability. A decorative duplicate never silently triggers an action.

Hover reveals the action and pointer cursor on the same solid pixels used by rendering. Sampling is bounded, including camera movement under a stationary pointer. Touch/keyboard retain a nearby action. Clicking a distant object walks to a collision-safe approach point, then rechecks authority. Selecting a person approaches a short walkable conversational distance, cancels on departure or lost authority, and stops pursuing after a bounded delay. Opening an existing inbox remains distinct from approaching someone in the scene.

The minimap and keyboard-accessible place directory move the camera, not the avatar. Directory selection restores focus to its trigger. A small minimap provides coarse navigation; exact object selection uses scene pixels.

## Implementation boundaries

Districts, objects, interaction bindings, poses and art have separate modules. The common world definition compiles collision vocabulary into the backend catalogue. Private content never becomes a public mesh, label or texture key.

Pose slots have stable authored keys. The server owns controller/epoch/sequence checks and occupancy. The client waits for movement acknowledgments before requesting a pose. Standing releases the slot to a valid approach point. Runtime storage is namespaced by compiled scene identity: a geometry upgrade cannot restore occupied seats into different walls. Old ephemeral state expires normally; there is no global flush or database migration.

Settings remain separate from activities. Native panels retain account lifetime, suspension, HITL, quotas and rate limits. Conversational entry prepares an unsent localized draft; discovery spends no tokens. Radio opens its native interface without starting playback.

Art uses bounded procedural families. Fountain motion reuses a fixed small set of arcs/droplets, respects reduced motion and follows foreground drawing order. No art loading path invokes an LLM.

## Reviewed practice

[Phaser input](https://docs.phaser.io/phaser/concepts/input) informs explicit hit areas, pointer feedback and unified input. [Godot tilemaps](https://docs.godotengine.org/en/4.5/tutorials/2d/using_tilemaps.html) inform separation of presentation, collision and drawing order. Neither engine is a new dependency.

[Xbox contextual information](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/114), [navigation](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/112) and [objective clarity](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/109) inform pre-activation labels, keyboard alternatives and named places. They are design inputs; actual LIA behavior remains the acceptance proof.

## Acceptance

Tests do not certify professional art. Inspect play/near zoom, joins, silhouettes, seat contact, small-screen overlays and object/function coherence. Continue under the [iterative plan](../plans/2026-10-24-world-art-completion.md). Physical low-end phone/Pi capacity, supplier translation quality and accepted later features remain separate acceptance items.
