# Native avatar visual qualification

This local fixture mounts the product's `EyesFace` component for every selectable style and both variants. The native rig, frame scheduler, DOM writer, WebGL renderer, textures and context-loss fallback remain the production implementations. The fixture makes no backend calls. The capture scripts refuse requests outside their exact loopback origin and refuse to overwrite an existing evidence directory.

From `apps/web/e2e`:

```powershell
$env:AVATAR_BENCH_PORT='5188'
node fixtures/avatar-limbs/server.mjs
```

The existing limb bench defaults to port 5187. Each nondefault port has its own Vite cache. HMR and file watching are disabled: restart the server after product source changes to capture one source generation.

## Scarf evidence

```powershell
node capture/avatar-scarves.mjs --output=../../../output/playwright/avatar-artistry/new-fronts
node capture/avatar-scarves.mjs --output=../../../output/playwright/avatar-artistry/new-diagnostics --styles=bip,oscar,cozmo,orbit,nimbo --diagnostics
```

The cold control publishes a dated 5 °C observation through `useCompanionEnvironmentStore`, with the native life/context path enabled. Gaze and expressions use component props. No pose is injected through CSS.

The raster observer forwards untouched native WebGL calls. It identifies scarf textures from actual uploads and compares the body framebuffer with the result of all subsequent scarf passes. Native depth testing excludes hidden back cloth. The measurement counts pixels whose RGBA channels changed by at least eight and records each texture, depth state, the final draw serial, native `u_pose` and `u_drape`, mouth bounds, visible cloth bounds and buffer-upload counts. It arms before a transition and retains its final actual draw, because a settled expression may legitimately stop repainting. Context loss uses `WEBGL_lose_context`, followed by native fallback rotations.

`--closeup` enlarges the fixture's XL font size while preserving native em geometry, poses and materials. Other size presets retain their native size. Its larger viewport keeps the whole inspection layout visible without a screenshot-induced viewport resize.

`--fade` captures the settled cloth, same-pose context loss, the native cold spring crossing partial opacity, and both yaw/pitch signs. Wrapped BIP, Oscar and Nimbo must retain both variants and all 32 facets. `scarf-projection.mjs` independently imports the original garment geometry and projects it through the native head matrix, including source depth. It measures the actual painted patch corners separately; the full-frame facet box is not the painted patch. Absolute positions, patch dimensions and the four front/rear boundary pairs must agree within 0.05 CSS pixels. Non-painting measurement points are removed before screenshots and never replace a pose. A transformed head marker is not the expected position: a browser can flatten that marker and lose the depth being tested.

`--trail` cues opposing native head turns on wrapped BIP, Oscar and Nimbo. It reads the separate WebGL band and knot uniforms, then verifies the fallback attachment after real context loss. Both corners where the stationary knot meets the free end must agree within the same 0.05 CSS pixel bound in settled and moving poses.

`avatar-scarf-occlusion.mjs` captures the same paused image with only its rear cloth temporarily hidden. An independently decoded, eroded body-alpha mask bounds the physically possible transmission in central body pixels, excluding eyes and mouth. Fully opaque pixels allow no change. Unchanged and restored frames are compared exactly, after a bounded compositor settling interval. `--diagnose` preserves failed measurements without asserting a successful qualification; `--visible-control` performs an explicitly labeled unchanged-visibility repaint control. These diagnostic mutations are not product behavior.

`avatar-scarf-loading.mjs` delays or fails only the real scarf texture response. It verifies that warm/static avatars do not request that texture, an already uploaded body uses a coherent fallback camera while cold cloth is unavailable, delayed cloth restores native rendering, and warm recovery retains the uploaded body texture. Its intentional failed resource is recorded separately from unexpected errors.

`avatar-overview.mjs` saves one untouched browser screenshot of BIP, Oscar and Nimbo in both variants at the product's XL size through the fixture's `contact=true` view. `--styles=oscar,nimbo` selects a four-avatar row. The screenshot contains only the native matrix, without the bench controls, image composition or retouching. Scarf captures accept `--theme=light` or `--theme=dark` for independent native theme comparisons.

## Named native scenes

```powershell
node capture/avatar-scenes.mjs --output=../../../output/playwright/avatar-artistry/new-scenes
node capture/avatar-scenes.mjs --output=../../../output/playwright/avatar-artistry/new-video --styles=bip --scenes=body-hops --video
```

The server redirects only `useEyesRig`'s factory import through `native-scenes.ts`. The wrapper returns the exact native rig and retains the two latest live instances for the Play control. Play remounts the pair and calls their existing `playScene` method. The production hook owns visibility, wake-up, the single scheduler, the writer and cleanup.

By default the script discovers every style and body scene from the native selectors, using a deterministic browser clock and fixed entropy. Every sampled instant records native channels, joint uniforms, contact/shadow transforms and renderer readiness. One native screenshot contains both variants; the individual crops are derived from those exact pixels without scaling or retouching, and the crop bounds are recorded.

`--video` uses the browser's unmodified wall clock and requestAnimationFrame. Its metadata records actual elapsed timestamps; it never installs or advances a fake clock. `--lifecycle` additionally verifies a fixed native image under reduced motion and a resumed native surface afterward.

`--cold` waits for the native weather context and scarf to settle, then calls `playScene` on the already mounted pair through the fixture's Play on settled context control. It does not remount the rig, replace a pose, or introduce another clock. Combine it with `--closeup` to inspect cloth attachment during native gestures.

## Real-time comparison takes

```powershell
node capture/avatar-finishing.mjs --origin=http://127.0.0.1:5192 --output=../../../output/playwright/avatar-finishing-20261108/after
node capture/avatar-finishing.mjs --origin=http://127.0.0.1:5192 --styles=bip,oscar,nimbo --cold --size=sm --interrupt --output=../../../output/playwright/avatar-finishing-20261108/compact
```

Each video records both variants through the native resting, attentive, thinking and speaking expressions, followed by a bow and release. `--scene=body-hops` captures just a named performance and its recovery. `--interrupt` repeats the common bow and returns to speech while it is in progress. `--size` uses the selected product size. The default inspection view enlarges the XL em to 160 CSS pixels. `--cold` waits for the native scarf on every selected identity before starting.

Only this take fixes both entropy inputs and records the native `step` calls through the fixture wrapper. Each call forwards the original delta once and records the resulting rig channels and monotonic timestamp. The video uses the native browser clock. Its timestamps measure recording playback, while the JSON measures scheduler steps and the actual elapsed time between them. The coloured corner cue anchors each phase to a recorded frame. Speech is the product's speaking expression with the audio path idle.

## Source material evidence

```powershell
node capture/avatar-materials.mjs --output=../../../output/playwright/avatar-artistry/new-material --styles=spirit,moss,lumen,nimbo,orbit,bip,boulon,oscar
```

This audit measures the actual GPU alpha histogram and captures light/dark fronts, turns, reduced motion and context-loss fallback. It also rasterizes the exact mounted SVG alpha filter against the exact source image, alongside unfiltered SVG and identity-filter controls. The normalization must clear the source matte and leave opaque RGBA identical to the identity filter. Generic engine filter rounding is recorded separately; this comparison does not claim that all browser compositors preserve source RGB bit for bit. `--baseline` records the original material without claiming corrected-alpha assertions.

`--warm-only` restricts the material audit to the light-theme static front, reduced motion, context loss and a fallback turn. It refuses any scarf texture request and records document width and scroll width.

The material, scarf and scene capture scripts accept `--browser=chromium`, `--browser=firefox` or `--browser=webkit` and use already installed Playwright runtimes. The TypeScript check includes this fixture's TSX entry and Vite's declared CSS types. Its library policy matches the product's ESNext declarations; the compilation target remains unchanged.
