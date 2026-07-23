#!/usr/bin/env node
/**
 * PWA icon generation (UXR Lot 9, A6) — reproducible source of the committed
 * PNGs in public/. Run from apps/web:
 *
 *   node scripts/generate-pwa-icons.mjs
 *
 * Outputs: icon-192.png, icon-512.png, icon-maskable-192.png,
 * icon-maskable-512.png (20% safe-zone padding on the brand blue so the
 * rounded-corner/circle masks of launchers never clip the glyph),
 * apple-touch-icon.png (180, opaque background — iOS composits no alpha).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const SVG = readFileSync(new URL("../public/icon.svg", import.meta.url));
const BRAND_BLUE = { r: 29, g: 78, b: 216, alpha: 1 }; // #1d4ed8 (icon gradient)
const out = (file) => fileURLToPath(new URL(`../public/${file}`, import.meta.url));

async function plain(size, file) {
  await sharp(SVG).resize(size, size).png().toFile(out(file));
  console.log(`✓ ${file}`);
}

async function maskable(size, file) {
  // 20% total padding: glyph occupies the central 80% (maskable safe zone).
  const inner = Math.round(size * 0.8);
  const glyph = await sharp(SVG).resize(inner, inner).png().toBuffer();
  await sharp({
    create: { width: size, height: size, channels: 4, background: BRAND_BLUE },
  })
    .composite([{ input: glyph, gravity: "center" }])
    .png()
    .toFile(out(file));
  console.log(`✓ ${file}`);
}

async function apple(size, file) {
  const inner = Math.round(size * 0.86);
  const glyph = await sharp(SVG).resize(inner, inner).png().toBuffer();
  await sharp({
    create: { width: size, height: size, channels: 4, background: BRAND_BLUE },
  })
    .composite([{ input: glyph, gravity: "center" }])
    .flatten({ background: BRAND_BLUE })
    .png()
    .toFile(out(file));
  console.log(`✓ ${file}`);
}

await plain(192, "icon-192.png");
await plain(512, "icon-512.png");
await maskable(192, "icon-maskable-192.png");
await maskable(512, "icon-maskable-512.png");
await apple(180, "apple-touch-icon.png");
