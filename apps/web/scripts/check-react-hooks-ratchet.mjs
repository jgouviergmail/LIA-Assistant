#!/usr/bin/env node
/**
 * React 19 strict-mode ratchet — PER FILE (audit F021 / F044).
 *
 * The 2026-07 audit found `react-hooks/set-state-in-effect` and
 * `react-hooks/immutability` switched OFF with a "fix later" TODO — masking 34
 * real violations across 29 files. Each fix is delicate (derived state →
 * useMemo, sync-to-prop patterns), so this ratchet FREEZES the debt shrink-only
 * while the components are remediated. Flip the rules to "error" in
 * eslint.config.mjs once this hits 0.
 *
 * F044 hardening: freezes a PER-FILE count, not a substitutable global total —
 * a violation moved to a new location fails even when the total is flat.
 *
 * Usage (from apps/web):
 *   node scripts/check-react-hooks-ratchet.mjs            # check
 *   node scripts/check-react-hooks-ratchet.mjs --update   # rewrite the baseline
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { relative } from "node:path";

const RULES = {
  "react-hooks/set-state-in-effect": "error",
  "react-hooks/immutability": "error",
};
const RULE_PREFIX = "react-hooks/";
const BASELINE_URL = new URL("../.react-hooks-baseline.json", import.meta.url);
const FIX_HINT =
  "Do not call setState directly in an effect (derive with useMemo, or guard the " +
  "update); never mutate state/props.";

function measurePerFile() {
  let stdout;
  try {
    stdout = execFileSync(
      "pnpm",
      ["exec", "eslint", "src", "--rule", JSON.stringify(RULES), "-f", "json"],
      { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 },
    );
  } catch (err) {
    stdout = err.stdout;
  }
  const perFile = {};
  for (const file of JSON.parse(stdout)) {
    const n = file.messages.filter((m) => m.ruleId && m.ruleId.startsWith(RULE_PREFIX)).length;
    if (n > 0) perFile[relative(process.cwd(), file.filePath).replaceAll("\\", "/")] = n;
  }
  return perFile;
}

const current = measurePerFile();
const total = Object.values(current).reduce((a, b) => a + b, 0);

if (process.argv.includes("--update")) {
  const payload = {
    _comment:
      "React 19 strict-mode ratchet (audit F021/F044). PER-FILE frozen counts for " +
      "react-hooks/set-state-in-effect + react-hooks/immutability. A file may only " +
      "DECREASE; new offending files fail CI. Flip the rules to error in " +
      "eslint.config.mjs at 0. Regenerate with --update after fixing, never to absorb " +
      "a regression.",
    total,
    perFile: Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b))),
  };
  writeFileSync(BASELINE_URL, JSON.stringify(payload, null, 2) + "\n");
  console.log(`react-hooks baseline written: ${total} violations across ${Object.keys(current).length} files.`);
  process.exit(0);
}

const baseline = JSON.parse(readFileSync(BASELINE_URL, "utf8")).perFile || {};
const regressions = [];
for (const [file, count] of Object.entries(current)) {
  const allowed = baseline[file] || 0;
  if (count > allowed) regressions.push(`${file}: ${count} > ${allowed}`);
}
const improved = Object.entries(baseline).filter(([f, n]) => (current[f] || 0) < n);

console.log(`react-hooks strict violations: ${total} across ${Object.keys(current).length} files`);
if (regressions.length > 0) {
  console.error(`\n❌ react-hooks ratchet: ${regressions.length} file(s) regressed:`);
  for (const r of regressions) console.error(`   ${r}`);
  console.error(`\n${FIX_HINT}`);
  process.exit(1);
}
if (improved.length > 0) {
  console.log(
    `\n✅ ${improved.length} file(s) improved — run \`node scripts/check-react-hooks-ratchet.mjs --update\` ` +
      `to lock in the gain.`,
  );
}
console.log("✅ react-hooks ratchet holds (per-file).");
