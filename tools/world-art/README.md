# World artwork source

The original directional BIP artwork and its generation manifest live in
`source/bip-v1/`. They are offline authoring inputs, outside Next.js public assets.
The renderer loads only the repacked atlas under `apps/web/public/world/bip/v2/`.

From the repository root, reproduce the atlas and verify exact source RGBA pixels:

```sh
node scripts/pack-world-lia-atlas.cjs
```

The repacker records both hashes and frame bounds in the runtime provenance file.
Original content credentials remain attached to the offline source; they do not
attest the repacked derivative. See the [World guide](../../docs/technical/WORLD_PROTOTYPE.md).
