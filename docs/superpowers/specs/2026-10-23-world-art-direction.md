# World V1 — professional visual acceptance

The POC validates feasibility only. Its warehouse-like repeated interiors,
monotonous floor grid, frontal walking actors, scattered controls and overflowing
preview viewport are defects, not an accepted final direction.

Use an inhabited garden campus: a generous social courtyard, distinct cutaway
buildings, purposeful furniture clusters, readable entrances and material detail
visible at normal play zoom. Preserve open walking paths and a world larger than
the viewport. Do not shrink the whole map into one screen.

World materials: shaded teal `#274f4d`, glazed blue-green `#4b8886`, limestone
`#ece4cf`, oak `#b5845f`, foliage `#8b9f73`, copper `#be7961`. This fixed art palette
does not override LIA's user-selected chrome/theme tokens. Existing app fonts and
native accessible controls remain authoritative. World text is a separate
localized presentation layer, never baked into feature textures.

Composition: compact place/status at upper left, correctly oriented map at upper
right, quiet grouped camera/LIA controls below. Mobile keeps the walking thumb
area clear. Secondary quality options belong in help/settings, not permanent
scene clutter. The canvas fits its container without document scroll; camera
scrolling is independent. Every essential action keeps a DOM/keyboard route.

Review real running scenes at normal/near/far zoom, all eight human movement headings,
entrances and occluding furniture, portrait/landscape and 320 CSS-pixel panels.
Require a clean silhouette, coherent scale, purposeful decoration, no accidental
click from a gesture and no hidden control. A screenshot and green tests do not
establish final owner visual acceptance or physical-phone performance.

The live preview is refreshed after each qualified lot. The original Canvas
implementation and artwork remain independently authored; no MalinosLand assets
or implementation are copied.

## Owner review after F12: professional acceptance remains open

The owner rejects the current scene as a final visual and interaction result.
The next slice must address connected and completed walls, readable thematic
layout, coherent furniture orientation and scale, detailed objects, consistent
shadows and visible lighting. Weather must relate to outdoor surfaces and shelter;
a few bounded ambient animations (fountain, screens, exterior life) should give
the campus presence without adding continuous expensive work on modest clients.

Demonstrate natural movement along the isometric floor axes and diagonals,
credible facing/transitions, usable seats and beds, and integrated conversations
with LIA and people. Review these together with one real contextual LIA activity
in a representative finished space before generalizing the treatment. Settings
belong in a separate menu; restrained transverse widgets support activities.
The [native-function contract](2026-10-23-world-native-functions.md) and
[conversation contract](2026-10-23-world-direct-text.md) define those boundaries.
Technical qualification alone does not close visual or experiential acceptance.


## Owner's visual reference and locomotion correction

The owner's quick mock-up establishes a quality direction, not a layout or asset
specification to copy: connected architecture, purposeful furniture groupings,
warm local light, readable circulation, garden life and discreet controls. The
finished campus must be original and materially more considered than this quick
reference. Keep this distinction explicit in visual reviews.

Human facing follows actual displacement in world coordinates, then projects to
the scene; it is not inferred from a screen arrow or approximated by four frontal
sprites. Eight genuine orientations, a distance-driven gait and an orientation
retained at rest address sideways walking without accelerating diagonals. Cached
orthographic meshes use the existing Canvas renderer; no WebGL renderer or server
frame generation is introduced. This matches the separation of movement and
animation direction in the [Godot movement guide](https://docs.godotengine.org/en/latest/tutorials/2d/2d_movement.html)
and [directional animation documentation](https://github.com/godotengine/godot-docs/blob/master/tutorials/animation/animation_tree.rst).
These references inform mechanics only; the implementation remains native LIA.
