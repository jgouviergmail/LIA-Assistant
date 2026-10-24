#!/usr/bin/env node
/**
 * Double-assertion ratchet — PER FILE (audit AC-037).
 *
 * The rule « test code obeys production contracts » (CLAUDE.md) could not be
 * checked: 119 `as unknown as` existed on 2026-10-23 — 107 in tests, 4 end to
 * end, 8 in production — and nothing counted them. This ratchet freezes each
 * file's count over `src` and `e2e`; a file may only go DOWN, and a new file
 * starts at zero. Replace a double assertion with a typed builder or a type
 * guard; a cast is only admitted at an external boundary nobody can construct.
 *
 * Usage (from apps/web):
 *   node scripts/check-double-cast-ratchet.mjs            # check (CI)
 *   node scripts/check-double-cast-ratchet.mjs --update   # lower the baseline after a fix
 *
 * `--update` lowers counts and drops cleared files; it never raises a count and
 * never adds a file, so it cannot absorb a regression.
 */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { compare, countDoubleCasts, shrink } from './double-cast.mjs';

const WEB_DIR = fileURLToPath(new URL('..', import.meta.url));
const ROOTS = ['src', 'e2e'];
const SKIPPED = new Set(['node_modules', 'coverage', 'dist']);
const BASELINE_URL = new URL('../.double-cast-baseline.json', import.meta.url);
const COMMENT =
  'Double-assertion ratchet (audit AC-037). PER-FILE frozen counts of `as unknown as` / ' +
  '`as any as` over src and e2e. A file may only DECREASE; a new file starts at zero. ' +
  '--update lowers counts and never raises or adds one.';

/** @returns {string[]} Every TypeScript source under the scanned roots. */
function sources(dir = WEB_DIR, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (SKIPPED.has(entry.name) || entry.name.startsWith('.next')) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) sources(full, out);
    else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) out.push(full);
  }
  return out;
}

/** @returns {Record<string, number>} The count of every file that holds one. */
function measure() {
  /** @type {Record<string, number>} */
  const perFile = {};
  for (const root of ROOTS) {
    for (const file of sources(join(WEB_DIR, root))) {
      const count = countDoubleCasts(readFileSync(file, 'utf8'), file);
      if (count > 0) perFile[relative(WEB_DIR, file).split(sep).join('/')] = count;
    }
  }
  return perFile;
}

const current = measure();
const total = Object.values(current).reduce((a, b) => a + b, 0);
const baseline = JSON.parse(readFileSync(BASELINE_URL, 'utf8')).perFile || {};

if (process.argv.includes('--update')) {
  const lowered = shrink(current, baseline);
  const loweredTotal = Object.values(lowered).reduce((a, b) => a + b, 0);
  writeFileSync(
    BASELINE_URL,
    JSON.stringify({ _comment: COMMENT, total: loweredTotal, perFile: lowered }, null, 2) + '\n'
  );
  console.log(`double-cast baseline lowered to ${loweredTotal} across ${Object.keys(lowered).length} files.`);
}

const { regressions, improved } = compare(current, baseline);
console.log(`double assertions: ${total} across ${Object.keys(current).length} files`);
if (regressions.length > 0) {
  console.error(`\n❌ double-cast ratchet: ${regressions.length} file(s) regressed:`);
  for (const line of regressions) console.error(`   ${line}`);
  console.error(
    '\nBuild the value with a typed builder (Partial<T> in, T out) or narrow it with a ' +
      'type guard; a cast belongs only at an external boundary nobody can construct.'
  );
  process.exit(1);
}
if (improved.length > 0 && !process.argv.includes('--update')) {
  console.log(
    `\n✅ ${improved.length} file(s) improved — run \`node scripts/check-double-cast-ratchet.mjs --update\` to lock in the gain.`
  );
}
console.log('✅ double-cast ratchet holds (per-file).');
