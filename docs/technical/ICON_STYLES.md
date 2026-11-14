# Account icon styles

Decision record: [ADR-377](../architecture/ADR-377-The-Account-Chooses-How-The-Interface-Is-Drawn.md).

Settings → Appearance offers Lucide, Fluent Color and Streamline Flex. The
account's `icon_style` follows the existing profile read/update path. The default
is Fluent Color, including existing accounts when the additive migration runs.
The database rejects null or unknown styles; the API validates the same closed
vocabulary. The assistant's native application-setting catalogue exposes this
ordinary appearance preference too.

## Rendering contract

Application components import icons and their compatible types from
`apps/web/src/lib/icons/index.ts`. Only this facade imports Lucide artwork.
`createAppIcon` preserves SVG dimensions, refs, accessible labels and events;
the account context selects the artwork immediately. Gradient and mask IDs are
unique to each mounted instance. Forced-colour environments use the original
Lucide glyph to retain system contrast.

Compact colour drawings with generous source margins use a tighter optical
viewBox inside the same SVG dimensions. The artwork's fine edge follows the
local foreground colour, including on buttons with a solid fill. Compact chat
and mobile controls give the colour drawings more room within the existing
targets. Lucide continues to use its original drawing and sizing.

Both colour styles provide multicoloured artwork for every registered interface
symbol. They combine faithful vendor SVGs with reviewed LIA complements where
the collection lacks the matching object or state. These complements preserve
normalized geometry and apply distinct colours to surfaces, details and action
marks; their provenance identifies the Lucide-derived geometry and LIA colour
adaptation. They are not represented as official vendor artwork. Neutral or
single-colour vendor symbols also receive a documented colour adaptation.
Brands, flags, user images and World canvas artwork are not interface icon styles.

Correspondence preserves the depicted object, action, direction and state.
A related illustration is insufficient: an approval badge is not a thumbs-up,
a globe is not a map, and repeating one item is not refreshing a view. Accessible
labels complement the drawing; they never justify replacing it with a different
meaning. The manifest records the source and adaptation of each style's artwork.
Feedback thumbs retain their familiar up/down shapes, now with coloured surfaces
in both colour styles. A missing vendor concept never silently returns the
monochrome renderer.

Where no collection draws the object at all, the line set included, the colour
styles show a drawing LIA authored outright under a name of its own, and the line
style keeps the glyph it already used. The radio is a radio set in colour and
Lucide's broadcast in line, on every surface that names it; the broadcast glyph
stays the mark of the live and signal controls, each of which declares what it
means by it (guard `radio-glyph.guard.test.ts`). The recorder shows the recording
dot, red at rest as well as live, inside a ring whose colour and pulse say that a
recording is running.

Selection and fill remain semantic states. Stars, hearts, pins, circles and
squares use an interior layer inheriting the effective SVG fill, while their contour and accents retain
their colours. This preserves explicit `fill` props, utility classes and a fill
applied by a parent button. Empty and filled symbols, half ratings and unchecked
versus checked bookmarks remain distinct. The runtime does not infer state by
parsing class names.

An icon's own colours must not erase a control's selected or busy state. Such
controls expose the appropriate ARIA state and retain a visible indicator without
animation. The cost, radio and briefing-refresh buttons share
`ACTIVE_ICON_BUTTON_CLASS` in the [button styles](../../apps/web/src/components/ui/button-variants.ts).
Its dark surface uses a neutral shade of the card so that selection preserves
the glyph's contrast. Contrast checks read the actual SVG paints and theme tokens;
browser journeys verify the rendered surface, reduced motion, focus and actions.

Known Material Symbols markers in new and archived chat cards pass through
`MaterialSymbol` and the same facade. The sanitizer still rejects arbitrary SVG
from message content. Unknown historical ligatures retain their font shape and
receive the selected colour palette; plain-text exports continue to remove the
markers. See [HTML cards](HTML_CARDS.md).

The historical Material Symbols variable font is self-hosted, with its
[pinned provenance and Apache 2.0 license](../../apps/web/public/fonts/material-symbols/README.md).
The global stylesheet imports its local CSS; neither the stylesheet nor its font
needs a Google Fonts connection. The full font preserves every ligature and
variation axis, while public pages keep their existing subset. Browser tests use
the real app server's assets, as do autonomous captures.

## Persistence and isolation

`IconStyleProvider` owns one preference controller per authenticated account.
Writes are serialized and rapid selections coalesce to the newest choice. A
confirmed PATCH response updates only the icon field in the account context and
releases the optimistic override. Older profile reads preserve that confirmed
field while still publishing unrelated preferences. A failed save
restores the last confirmed value and exposes a retry. Signing out or changing
accounts aborts the old request and discards its queue; no global local-storage
preference can leak between accounts. Anonymous pages use the default.

## Assets and maintenance

The pinned source versions, exact correspondences, colour complements and
adaptation provenance live in [the manifest](../../scripts/icons/manifest.json).
The generator reads checked-in vendor inputs and requires no network:

```sh
node scripts/icons/generate.mjs
node scripts/icons/generate.mjs --check
```

Generated TypeScript constants are application build inputs, not a generated
application tree. Named exports allow unused artwork to be removed from a
production bundle. Adding an icon requires reviewed coloured artwork for both
styles; the completeness guard refuses unregistered imports or missing variants.

Fluent vendor artwork retains its original colours where already multicoloured.
LIA complements use soft shading for Fluent and flat surfaces for Streamline
Flex. The approved palettes preserve visible detail in light and dark themes. The
[bundled attribution](../../apps/web/public/icon-licenses.txt) identifies the
authors, licences and adaptations and is linked from Appearance.

Validation covers account isolation and the PostgreSQL migration, API value
validation, save ordering and retry, SVG namespace safety, the HTML sanitization
boundary, native radio keyboard interaction, light/dark rendering and reload
persistence through hermetic browser fixtures.
