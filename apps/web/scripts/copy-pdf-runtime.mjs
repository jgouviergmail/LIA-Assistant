#!/usr/bin/env node
/**
 * Serve PDF.js's worker and the data it reads at run time from the app itself (ADR-369, lot 14).
 *
 * A PDF is read in the page (`components/workbench/viewers/PdfViewer.tsx`) and a self-hosted
 * install calls no third party, so what PDF.js asks for while it reads comes from here: its
 * worker, the character maps of a CJK text, the fourteen standard fonts a PDF may name without
 * embedding them, and the WebAssembly decoders of a scanned page (JPEG 2000, JBIG2). Without
 * those three a document still opens, with wrong letters and blank scans: nothing would say so.
 *
 * All of it is copied from the installed package into `public/pdfjs/<version>/`, the exact
 * version the lockfile pins, before `next dev` and `next build` (pnpm runs no `pre*` script, so
 * the package scripts call this one). The version is in the PATH because these files are served
 * as immutable: an upgrade is a new URL. Other versions' directories are removed.
 *
 * Idempotent: a copy already identical in size is left alone. `public/pdfjs/` is ignored by git:
 * it is derived from the lockfile, never committed.
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
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIRECTORIES = ['cmaps', 'standard_fonts', 'wasm'];
const WORKER = join('legacy', 'build', 'pdf.worker.min.mjs');

const require = createRequire(import.meta.url);
const packageRoot = dirname(require.resolve('pdfjs-dist/package.json'));
const { version } = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf-8'));
const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'pdfjs');
const target = join(root, version);
mkdirSync(target, { recursive: true });

for (const entry of readdirSync(root)) {
  if (entry !== version) rmSync(join(root, entry), { recursive: true, force: true });
}

function copied(source, destination) {
  if (existsSync(destination) && statSync(destination).size === statSync(source).size) return 0;
  copyFileSync(source, destination);
  return 1;
}

let count = copied(join(packageRoot, WORKER), join(target, 'pdf.worker.min.mjs'));
for (const directory of DIRECTORIES) {
  const destination = join(target, directory);
  mkdirSync(destination, { recursive: true });
  for (const name of readdirSync(join(packageRoot, directory))) {
    count += copied(join(packageRoot, directory, name), join(destination, name));
  }
}
if (count > 0) console.log(`copied ${count} files -> public/pdfjs/${version}/`);
