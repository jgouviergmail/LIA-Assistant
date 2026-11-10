# ADR-340 — Native avatar volume from reviewed offline art

**Status:** Accepted — implemented; real-device performance remains a measured runtime property.
**Date:** 2026-10-12
**Scope:** Native hybrid avatar body volume, limb articulation, facial projection and graphics lifetime.

**Related:** [ADR-294](ADR-294-A-Face-That-Never-Plays-The-Same-Twice.md)
and [Spirit/avatar technical guide](../technical/SPIRIT_AVATAR.md).
The [native volume guide](../technical/NATIVE_AVATAR_VOLUME.md) maps source
ownership, runtime gates and verification limits.

## Context

The approved companion catalogue consists of original offline artwork and one
native facial rig. Turning a complete character requires more than rotating its
frontal image, while replacing it with an unrelated downloaded mesh would lose
its reviewed identity. Compact UI avatars must retain the same motion ownership,
reduced-motion behavior and fallback when graphics resources are unavailable.

## Decision

1. **Retain reviewed art with bounded anatomical relief.** Character/variant
   profiles build shallow front/back proxy meshes with alpha-derived outlines,
   body depth and collar landmarks. The approved body image textures the surface.
   Hidden anatomy remains an approximation; this is not a reconstructed original
   full sculpt with independently authored side views.
2. **Preserve silhouette coverage.** Alpha coverage, boundary normals, distance
   fields and fringe handling retain fine frontal material behind the relief.
   Character-specific lobes and silhouette-derived depth inform projection.
   Indexed physical front triangles determine covered solid alpha in source UV
   space; rear and marked planar triangles cannot conceal missing frontal detail.
   Covered solid pixels are excluded from the fringe, while soft and uncovered
   source alpha remains. The monitor explicitly enables opaque casing; organic
   normals do not implicitly enable that material. The sampled hull is still an
   approximation. Changes need independent alpha/contour oracles.
   The measured companion background-alpha floor is removed by one continuous
   transfer shared by live material and SVG bake fallback. The delivered files
   remain immutable; neither RGB nor opaque alpha is changed by that transfer.
   Driver/compositor rounding is qualified separately from this numeric contract.
3. **Project the existing native face.** Head channels drive volume yaw/pitch;
   eye, eyebrow, mouth and clipping layers project onto the same surface.
   Native pupils, blinks, contour shapes and expression behavior remain active.
   Oscar uses fixed cranial eye-socket projection and separate mouth articulation.
   Monitor screen and brow layers share their declared projection.
   These are projected DOM/SVG layers, not a general facial mesh in the body's
   depth buffer; arbitrary face/prop occlusion is not guaranteed.
4. **Keep one motion owner.** The existing rig writer supplies pose and material
   channels. The body binding receives its visibility and reduced-motion gates;
   it adds no independent animation clock or viewport observer. Offline texture
   and prop preparation needs no runtime Blender, image generator or provider API.
5. **Fail back to the original body.** The bounded native WebGL drawing buffer
   becomes ready only with usable resources. Failed texture/context creation,
   lost context, hidden or reduced-motion state retain the fixed bake. Canvas
   replacement and unmount release graphics/listener resources and reset readiness.
   Historical/static portraits do not allocate the live body canvas.
   Temporary stops dispose programs, buffers and textures but retain CPU mask
   and mesh data for resume; they do not explicitly release the browser context.
   Permanent detach also attempts context release through the optional native
   extension. A latched binding failure is not retried automatically; context
   restoration can resume only when the native gates permit it.
6. **Share attachment landmarks.** Crown, face and neck landmarks position native
   emotes and context props consistently. Worn props project with the body's
   surface; environmental motifs keep their stage anchors. Cloth uses the same
   pose/lifetime. When cold requires cloth, body and garment readiness switch
   together, retaining a coherent full-avatar fallback until both are ready.
   Prepared body resources remain available for warming or successful cloth load.
   Authored front scarf patches deliberately use `depthFunc(ALWAYS)` with depth
   writes disabled to avoid subdivision holes. Closed collars instead use
   `LEQUAL` against the body to occlude their rear returns. Both restore `LEQUAL`
   and depth writes in `finally`. These calibrated garments do not provide
   general cloth collision or unrestricted garment occlusion.
7. **Articulate the anatomy the source actually shows.** Per-character/variant
   [limb profiles](../../apps/web/src/components/eyes/volume/limb-profiles.ts)
   declare pivots, influence regions and limits. Spirit and Nimbo have side
   appendages; Moss and Lumen have arms and feet; BIP, Boulon and Oscar have
   arm/wrist and leg/foot chains. Orbit's ring, the monitor and eye-only styles
   stay rigid. The existing rig owns quiet settling, occasional resting beats,
   contextual poses, speech-phrase accents and body-scene follow-through on its
   single clock. Prepared source-space weights deform the physical surface and
   tessellated alpha fringe together. Normals follow the inverse-transpose
   spatial Jacobian; material sentinels and original texture coordinates remain
   separate. Limb changes participate in redraw invalidation even when the head
   is still, under the same graphics lifetime and motion gates.
8. **Fit garments and direct gestures through shared declarations.**
   [Scarf fitting](../../apps/web/src/components/eyes/volume/scarf-fit.ts) separates
   collar width, band thickness and tail length, mapping the same source artwork
   into the live mesh and CSS fallback. Closed collars share prepared facets
   and remain attached to the body; the free knot/end alone sways on the native
   channel. [Scene phases](../../apps/web/src/components/eyes/rig/body-scene.ts)
   author body, limbs and facial intent together; interpolated targets remain
   subordinate to the existing springs and interruption rules. Registered
   [support points](../../apps/web/src/components/eyes/body-support.ts) compensate
   stage scale and rotation before viewport containment. This is a grounded
   stage transform, not inverse kinematics or a new skeletal simulation.

## Consequences and limits

### Catalogue retirement — 2026-11-08

The owner withdrew Smiley from the avatar catalogue. Its dedicated sphere
renderer, delivery assets and authoring script are removed; shared facial
contours remain with the companion renderer that consumes them. Persisted
retired selections pass through the existing validated style-preference reader
to the current default. No database rewrite is required. This decision concerns
the selectable companion, not the separate mood emoji in chat messages.

### Rendering limits

The application keeps its reviewed character identities and native reactions
while gaining bounded head depth and local limb motion. Resource and channel
ownership remain visible in the existing renderer architecture. Each new character
requires calibrated geometry, alpha material and landmarks rather than a generic
sphere substitution.

Proxy geometry cannot reveal artwork that was never authored. Unit geometry and
graphics lifetime tests do not establish smoothness on every mobile GPU or a
television-quality enlarged render. Download size, decoded memory, context
behavior and frame cost must be qualified on the actual delivery and devices.
The low-power context preference and bounded geometry are implementation choices,
not measured performance guarantees. Source-owned bounds, dimensions, asset
versions and thresholds remain declared by their renderer modules.
Articulation retains the reviewed assets and material response; it adds neither
texture detail nor independent fingers, grasping or unrestricted occluding poses.

## Sources and qualification

- [Geometry/profiles](../../apps/web/src/components/eyes/volume/volume-geometry.ts)
- [Normals](../../apps/web/src/components/eyes/volume/volume-normals.ts),
  [coverage](../../apps/web/src/components/eyes/volume/volume-coverage.ts) and
  [fringe](../../apps/web/src/components/eyes/volume/volume-fringe.ts)
- [Native writer](../../apps/web/src/components/eyes/volume/volume-writer.ts)
- [Limb acting](../../apps/web/src/components/eyes/rig/limbs.ts),
  [speech phrases](../../apps/web/src/components/eyes/rig/limb-speech.ts),
  [prepared skin](../../apps/web/src/components/eyes/volume/limb-skin.ts) and
  [GPU deformation](../../apps/web/src/components/eyes/volume/limb-shader.ts)
- [Rig frame writer](../../apps/web/src/components/eyes/rig/apply.ts) and
  [native motion/visibility owner](../../apps/web/src/components/eyes/useEyesRig.ts)
- [Body binding/lifetime](../../apps/web/src/components/eyes/volume/volume-binding.ts)
- [Component](../../apps/web/src/components/eyes/volume/BodyVolume.tsx)
- [Shared scarf material](../../apps/web/src/components/eyes/volume/cloth-gpu.ts)
- [Behavior and geometry suites](../../apps/web/src/components/eyes/volume/__tests__)

The existing suites exercise projection, calibrated geometry, real alpha masks,
coverage/fringe behavior, joint motion and graphics lifecycle/fallback. Their
measured release results are recorded separately; this decision does not certify
production GPU performance from source inspection.
The contour suite uses an independent analytic alpha oracle; the coverage suite
uses independent UV geometry with holes and shared edges. Mocked WebGL checks
establish requested operations and resource contracts, not actual GPU raster
output or real-device frame rate.
The [limb runtime tests](../../apps/web/src/components/eyes/rig/__tests__/limbs.test.ts)
cover phrase pauses, interruptions, reduced-motion resume and drift. The
[anatomical tests](../../apps/web/src/components/eyes/volume/__tests__/limb-deformation.test.ts)
use source-alpha evidence and independent deformation checks; the
[browser journey](../../apps/web/e2e/smoke/avatar-limbs.spec.ts) exercises the
native surface. Their existence does not replace current execution results or
visual qualification of both variants.
