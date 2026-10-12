# ADR-340 — Native avatar volume from reviewed offline art

**Status:** Accepted — implemented; real-device performance remains a measured runtime property.
**Date:** 2026-10-12
**Scope:** Native hybrid avatar body volume, facial projection and graphics lifetime.

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
   pose/lifetime and retains its declared fallback until its material is ready.
   The authored front scarf deliberately draws with `depthFunc(ALWAYS)` and
   depth writes disabled, then restores `LEQUAL` and depth writes in `finally`.
   This avoids holes from coarse body triangles. It is front compositing, not
   general cloth collision or depth-correct garment occlusion.

## Consequences and limits

The application keeps its reviewed character identities and native reactions
while gaining bounded head depth. Resource and channel ownership remain visible
in the existing renderer architecture. Each new character requires calibrated
geometry, alpha material and landmarks rather than a generic sphere substitution.

Proxy geometry cannot reveal artwork that was never authored. Unit geometry and
graphics lifetime tests do not establish smoothness on every mobile GPU or a
television-quality enlarged render. Download size, decoded memory, context
behavior and frame cost must be qualified on the actual delivery and devices.
The low-power context preference and bounded geometry are implementation choices,
not measured performance guarantees. Source-owned bounds, dimensions, asset
versions and thresholds remain declared by their renderer modules.

## Sources and qualification

- [Geometry/profiles](../../apps/web/src/components/eyes/volume/volume-geometry.ts)
- [Normals](../../apps/web/src/components/eyes/volume/volume-normals.ts),
  [coverage](../../apps/web/src/components/eyes/volume/volume-coverage.ts) and
  [fringe](../../apps/web/src/components/eyes/volume/volume-fringe.ts)
- [Native writer](../../apps/web/src/components/eyes/volume/volume-writer.ts)
- [Rig frame writer](../../apps/web/src/components/eyes/rig/apply.ts) and
  [native motion/visibility owner](../../apps/web/src/components/eyes/useEyesRig.ts)
- [Body binding/lifetime](../../apps/web/src/components/eyes/volume/volume-binding.ts)
- [Component](../../apps/web/src/components/eyes/volume/BodyVolume.tsx)
- [Shared scarf material](../../apps/web/src/components/eyes/volume/cloth-gpu.ts)
- [Behavior and geometry suites](../../apps/web/src/components/eyes/volume/__tests__)

The existing suites exercise projection, calibrated geometry, real alpha masks,
coverage/fringe behavior and graphics lifecycle/fallback. Their measured release
results are recorded separately; this decision does not certify production GPU
performance from source inspection.
The contour suite uses an independent analytic alpha oracle; the coverage suite
uses independent UV geometry with holes and shared edges. Mocked WebGL checks
establish requested operations and resource contracts, not actual GPU raster
output or real-device frame rate.
