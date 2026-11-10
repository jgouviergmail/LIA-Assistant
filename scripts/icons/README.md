# Application icon catalogue

The application imports icons from `@/lib/icons`. The facade uses the account's
style while retaining the existing icon names, SVG props and accessible labels.
Its generated modules are production source inputs, not build outputs or a copy
of the complete vendor packages. Named exports and pure factory calls allow
unused artwork to be removed by the bundler.

Run from the repository root:

```sh
node scripts/icons/generate.mjs
node scripts/icons/generate.mjs --check
node --test scripts/icons/source-inventory.test.mjs
```

`catalogue.mjs` declares every native correspondence. `manifest.json` records the
exact vendor source or the authored LIA complement, its source geometry, recipe,
color treatment and reason the native artwork cannot express that concept.
The generator refuses an undeclared import, missing artwork or duplicate declaration.
Check mode also refuses direct runtime imports from `lucide-react` outside the
facade. The frontend catalogue test runs this check and the negative fixtures.

The pinned vendor inputs in `vendor/` include their package coordinates and
SHA-512 archive digests in `provenance.json`. They are read at generation time
only; the application never downloads an icon at runtime. To update a collection,
verify the archive against its published integrity, review the vendor diff,
replace the corresponding vendored input, regenerate and run the catalogue test.

## Correspondence policy

Fluent Color has fewer concepts than the full Fluent System Icons collection;
Flex Flat is also a finite subset. An unavailable illustration receives an
explicit LIA Soft or LIA Flat complement; colored modes have no monochrome fallback.
Controls and explicit states must retain their meaning: an unmarked calendar
cannot replace a cancelled calendar, and a sun cannot replace rain. The manifest
makes these choices visible instead of silently substituting an unrelated icon.

Every selected SVG is reviewed visually. A filename is not evidence of its
shape: the vendor's `voice-mail-flat` is a microphone, while `play-list-4-flat`
is only a play button. A nearby family concept is not accepted: an approval
checkmark is not a thumbs-up, and a satellite dish is not a podcast control.
The manifest identifies both concepts for accepted artwork and records per-pack
reasons for complements, including rejected substitutions.

`vendor/lucide.json` retains the canonical source geometry, checked against the
lockfile-pinned installed package on each generation. `lia-recipes.json` declares
every part's palette, fill and surface/detail layer. `lia-artwork.mjs` paints
surfaces first, then details and contours, preserving visible keys, eyes and
operation marks. `lia-special-artwork.mjs` owns composed objects and inherited
fill states; `lia-control-artwork.mjs` owns filled directional command glyphs.
The authored complements are derivatives of Lucide, explicitly attributed as
LIA artwork, and are not claimed to be official Fluent or Streamline designs.

The shared palettes distinguish chromatic surfaces from their contrasting ink.
Star, Heart, Pin, Circle and Square keep caller-controlled interiors through
`fill="inherit"`, including rules applied by an ancestor. StarHalf retains its
half boundary and half fill. Bookmark is open until the checked variant is used.
Disc and CircleDot retain caller-controlled ring colors and colored centers,
including the recording state of Disc.

`native-chromatic.mjs` preserves native silhouettes. Native Flex receives a
contrasting surface/ink palette, or two visible inks for separate exposed parts.
Single-tone native shapes use two-hue paint; gear hubs are colored within the
original silhouette. Fluent single-hue artwork receives color while preserving
the luminance of each native paint and its contrasting foreground marks.
Original multicolor Fluent artwork keeps its palette. Colors remain explicit
and legible in both themes without CSS color-function compatibility requirements.
The runtime renderer namespaces SVG paint-server IDs for each instance.

## Verification

The catalogue tests validate reachable chromatic paints, self-contained SVG,
contrast of representative detail/surface pairs, source geometry and import
completeness. Negative fixtures reject unused gradients, invisible colors and
neutral shading. `native-chromatic.test.mjs` verifies native tonal separation
against independently measured luminance. The browser checks inherited fill
states and reviews the complete catalogue at small sizes in both themes.
Forced-colors mode intentionally uses the Lucide geometry with system colors;
this accessibility override is separate from the normal colored styles.

## Attribution

- Fluent System Icons by Microsoft, MIT. Source: <https://github.com/microsoft/fluentui-system-icons>.
  The full notice is in `vendor/Fluent-LICENSE.txt`.
- Flex Flat by Streamline, distributed through Iconify, CC BY 4.0.
  Source: <https://github.com/webalys-hq/streamline-vectors>.
  License: <https://creativecommons.org/licenses/by/4.0/>.
  Changes: the chromatic surfaces, ink and single-tone adaptations described above.
- Lucide Icons and Contributors, ISC with Feather-derived MIT icons.
  Source: <https://github.com/lucide-icons/lucide>.
  LIA Soft/Flat complements add surfaces, paint layers and filled control shapes.

The public application ships the same attribution at `/icon-licenses.txt`,
linked from the icon selector. The existing Lucide package retains its ISC
license; its exact installed notice accompanies the public attribution.
