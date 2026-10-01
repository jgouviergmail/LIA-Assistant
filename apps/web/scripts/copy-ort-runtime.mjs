#!/usr/bin/env node
/**
 * Serve ONNX Runtime Web's WASM binary and its loader from the app itself (ADR-329).
 *
 * The wake-word detector runs `onnxruntime-web/wasm`, whose JavaScript is
 * bundled with the app but which fetches at run time, from `/ort/<version>/`,
 * BOTH its 14 MB WebAssembly binary and the module that loads it
 * (`ort-wasm-simd-threaded.mjs`): with `wasmPaths` set to a prefix, the
 * runtime imports its loader from there rather than the copy in the bundle.
 * Measured 2026-10-01 in Chromium against dev: the binary alone was copied,
 * the loader answered 404, and the detector never started — on every page.
 * A self-hosted install calls no third party, so both files are copied from
 * the installed package into `public/ort/<version>/` — the exact version the
 * lockfile pins — before `next dev` and `next build` (pnpm runs no `pre*`
 * script, so the package scripts call this one).
 *
 * The version is in the PATH because the binary is served as immutable: an
 * upgrade is a new URL, never a cached binary of the previous release under
 * the new release's JavaScript. Other versions' directories are removed.
 *
 * Idempotent: a copy already identical in size is left alone. `public/ort/` is
 * ignored by git — it is derived from the lockfile, never committed.
 */
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
} from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FILES = [
  'onnxruntime-web/ort-wasm-simd-threaded.wasm',
  'onnxruntime-web/ort-wasm-simd-threaded.mjs',
];

const require = createRequire(import.meta.url);
// The package exports no `package.json`: read the one beside its `dist/`.
const manifest = join(dirname(require.resolve(FILES[0])), '..', 'package.json');
const { version } = JSON.parse(readFileSync(manifest, 'utf-8'));
const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'ort');
const target = join(root, version);
mkdirSync(target, { recursive: true });

for (const entry of readdirSync(root)) {
  if (entry !== version) rmSync(join(root, entry), { recursive: true, force: true });
}

for (const specifier of FILES) {
  const source = require.resolve(specifier);
  const destination = join(target, basename(source));
  if (existsSync(destination) && statSync(destination).size === statSync(source).size) continue;
  copyFileSync(source, destination);
  console.log(`copied ${specifier} -> public/ort/${version}/${basename(source)}`);
}
