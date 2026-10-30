# World visual refinement

The owner approved the seven proposed improvements on 2026-10-28. Implement them
in the existing Canvas renderer; a tilt-shift experiment is deferred until the
owner validates this work.

## Direction and scope

Keep the inhabited isometric house, functional room identities and existing
navigation. Glazed teal `#249b93`, sage `#4b925d`, limestone `#f1e8d3`, oak
`#bb8a52`, copper `#d87753` and violet `#8665b5` form the common material
palette. Arcade screens and the diner retain their stronger accents. Existing
application typography and controls stay unchanged.
The owner rejected the first desaturated palette as faded; accents, wood and
foliage therefore retain a richer chroma while the surface detail stays restrained.

- Harmonize large surfaces, coping, wood and furniture materials.
- Soften selected tabletops, seats, pots and fountain edges inside their existing
  bounds; preserve orientation, seat elevation, picking and occlusion.
- Refine baked contact shadows and recesses without adding a live shadow pass.
- Distinguish marble, woven carpet, timber, glazed ceramic and metal.
- Refine the existing foliage families and shore/terrain transitions without
  changing collision or adding per-object texture identities.
- Give existing civil light phases distinct restrained tints and tighten lamp
  halos. Decorative windows remain non-emissive.
- Improve existing walking poses and ambient timing with the same frame and
  effect budgets. No new persistent simulation or independent timer.

## Detail review

The owner's screenshots require continuous fountain coping, joined bench
backrests, an unobstructed easel canvas, coaxial telescope sections with attached
finder brackets, planted foliage, and a phone stand resting on its table.
Arcade animation must remain inside the screen and must not appear on the rear
housing. Bottle shelves explicitly remain open behind: bottles must be visible
from either side. Ordering parts at sprite creation must preserve those openings.
Foreground wall tiles must consistently cover the base of long furniture: a
far-corner depth key must not interleave individual tiles with one shelf. Picking
must retain the same complete-scene ordering as rendering.
Further close-ups require coaxial barbell joints and rack supports clear of the
plates, a continuous bench arm/upright silhouette, wall faces without internal
anti-aliasing seams, and no grass inserted between indoor floors and the terrace.

## Verification

Capture comparable renderer views and cold/warm rendering measurements before
and after. Inspect normal/near/far zoom, all furniture facings, human headings,
day/dawn/evening/night, outdoor weather, reduced motion and mobile layouts.
Check texture memory, cache reuse, geometry/pose contracts and disposal. Run the
affected World tests, clean frontend static checks, frontend coverage and the
repository lint gates. Report physical-device and development-build limits
explicitly; automated checks do not substitute for owner visual acceptance.
