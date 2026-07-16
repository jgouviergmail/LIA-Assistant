#!/usr/bin/env node
/**
 * Frontend cyclomatic-complexity ratchet — PER FILE fingerprint + max (audit F011).
 *
 * The eslint.config.mjs `complexity` rule is a single GLOBAL ceiling (96), so a
 * brand-new function just under that ceiling slips in undetected. This ratchet
 * adds the fingerprint the backend already has (scripts/audit/measure_cc.py):
 * the count of functions at/over CC 15, the single worst function, AND a
 * per-file frozen {count, max} pair — all shrink-only. Decompose a hotspot into
 * hooks/services/pure helpers to lower the baseline; never raise it.
 *
 * F044 hardening: the per-file map means a violation moved to a new location
 * fails even when the global total is flat.
 * F011 hardening: the per-file `max` means a function that GROWS inside an
 * already-offending file fails even when that file's count is flat (previously
 * only the single global max bounded it).
 *
 * Usage (from apps/web):
 *   node scripts/check-cc-ratchet.mjs           # check (CI)
 *   node scripts/check-cc-ratchet.mjs --update  # rewrite the baseline after a fix
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { relative } from 'node:path';

const THRESHOLD = 15;
const BASELINE_URL = new URL('../.cc-baseline.json', import.meta.url);

function measure() {
  let stdout;
  try {
    stdout = execFileSync(
      'pnpm',
      [
        'exec',
        'eslint',
        'src',
        '--rule',
        JSON.stringify({ complexity: ['error', THRESHOLD] }),
        '-f',
        'json',
      ],
      { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }
    );
  } catch (err) {
    // eslint exits non-zero when it reports errors; its JSON is still on stdout.
    stdout = err.stdout;
  }
  const perFile = {};
  let max = 0;
  for (const file of JSON.parse(stdout)) {
    const msgs = file.messages.filter(m => m.ruleId === 'complexity');
    if (!msgs.length) continue;
    let fileMax = 0;
    for (const m of msgs) {
      const mm = /complexity of (\d+)/.exec(m.message);
      if (mm) fileMax = Math.max(fileMax, Number(mm[1]));
    }
    perFile[relative(process.cwd(), file.filePath).replaceAll('\\', '/')] = {
      count: msgs.length,
      max: fileMax,
    };
    max = Math.max(max, fileMax);
  }
  return { perFile, max };
}

/** Baseline entries may be the legacy bare count — normalize to {count, max}. */
function normalizeEntry(entry, globalMax) {
  if (typeof entry === 'number') return { count: entry, max: globalMax };
  return entry || { count: 0, max: 0 };
}

const { perFile, max } = measure();
const over = Object.values(perFile).reduce((a, b) => a + b.count, 0);
const fileCount = Object.keys(perFile).length;

if (process.argv.includes('--update')) {
  const payload = {
    _comment:
      'Frontend cyclomatic-complexity ratchet (audit F011). Shrink-only: `over` ' +
      '(functions >= CC 15), `max` (worst function) and each per-file ' +
      '{count, max} fingerprint may only DECREASE; a regression, a new offending ' +
      'file, or a function growing inside an offending file fails CI. Regenerate ' +
      'with --update ONLY after decomposing a hotspot, never to absorb a regression.',
    over,
    max,
    threshold: THRESHOLD,
    perFile: Object.fromEntries(Object.entries(perFile).sort(([a], [b]) => a.localeCompare(b))),
  };
  writeFileSync(BASELINE_URL, JSON.stringify(payload, null, 2) + '\n');
  console.log(`frontend CC baseline written: over=${over} max=${max} across ${fileCount} files.`);
  process.exit(0);
}

const base = JSON.parse(readFileSync(BASELINE_URL, 'utf8'));
const baseFile = base.perFile || {};
const problems = [];
if (over > base.over)
  problems.push(`functions >= CC ${THRESHOLD}: ${over} > baseline ${base.over}`);
if (max > base.max) problems.push(`max CC: ${max} > baseline ${base.max}`);
for (const [file, entry] of Object.entries(perFile)) {
  const allowed = normalizeEntry(baseFile[file], base.max);
  if (entry.count > allowed.count)
    problems.push(`${file}: ${entry.count} hotspots > ${allowed.count}`);
  if (entry.max > allowed.max)
    problems.push(`${file}: worst function CC ${entry.max} > ${allowed.max}`);
}

console.log(`frontend CC >= ${THRESHOLD}: ${over} (max ${max}) across ${fileCount} files`);
if (problems.length > 0) {
  console.error(`\n❌ frontend CC ratchet regressed (F011):`);
  for (const p of problems) console.error(`   ${p}`);
  console.error(`\nDecompose into hooks/services/pure helpers — do not raise the caps.`);
  process.exit(1);
}
const improved =
  over < base.over ||
  max < base.max ||
  Object.entries(baseFile).some(([f, n]) => {
    const allowed = normalizeEntry(n, base.max);
    const cur = perFile[f] || { count: 0, max: 0 };
    return cur.count < allowed.count || cur.max < allowed.max;
  });
if (improved) {
  console.log(
    `\n✅ CC improved — run \`node scripts/check-cc-ratchet.mjs --update\` to lock the gain in.`
  );
}
console.log('✅ frontend CC ratchet holds (per-file + max).');
