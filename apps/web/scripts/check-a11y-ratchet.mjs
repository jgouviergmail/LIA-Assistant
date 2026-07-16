#!/usr/bin/env node
/**
 * jsx-a11y accessibility ratchet — PER FILE (audit F012 / F013 / F021 / F044).
 *
 * The 2026-07 audit found ~50 accessibility violations across the admin screens
 * (icon buttons with no accessible name, `<th onClick>` sorts with no keyboard
 * handler, `div role="dialog"` fake modals). Fixing them all is a multi-screen
 * campaign; this ratchet FREEZES the debt so it cannot GROW while the screens
 * are remediated one by one.
 *
 * F044 hardening: a single global total is *substitutable* — fix one violation,
 * add another elsewhere, and the total is unchanged so CI stays green. This
 * ratchet instead freezes a PER-FILE count. A file may never exceed its frozen
 * count, and a file absent from the baseline must have zero — so a violation
 * moved to a new location fails even when the global total is flat.
 *
 * Usage (from apps/web):
 *   node scripts/check-a11y-ratchet.mjs            # check
 *   node scripts/check-a11y-ratchet.mjs --update   # rewrite the per-file baseline
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { relative } from "node:path";

const RULES = {
  "jsx-a11y/control-has-associated-label": "error",
  "jsx-a11y/label-has-associated-control": "error",
  "jsx-a11y/click-events-have-key-events": "error",
  "jsx-a11y/no-static-element-interactions": "error",
  "jsx-a11y/interactive-supports-focus": "error",
};
const RULE_PREFIX = "jsx-a11y/";
const BASELINE_URL = new URL("../.jsx-a11y-baseline.json", import.meta.url);
const FIX_HINT =
  "Give controls an accessible name (aria-label / associated <label htmlFor>), " +
  "add keyboard handlers to click targets, or use a real Radix Dialog instead of " +
  "a div[role=dialog].";

function measurePerFile() {
  let stdout;
  try {
    stdout = execFileSync(
      "pnpm",
      ["exec", "eslint", "src", "--rule", JSON.stringify(RULES), "-f", "json"],
      { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 },
    );
  } catch (err) {
    stdout = err.stdout; // eslint exits non-zero when it reports errors
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
      "jsx-a11y accessibility debt ratchet (audit F012/F013/F021/F044). PER-FILE " +
      "frozen counts for the keyboard/label rule set in check-a11y-ratchet.mjs. A file " +
      "may only DECREASE; new offending files fail CI. Regenerate with --update after " +
      "remediating, never to absorb a regression.",
    total,
    perFile: Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b))),
  };
  writeFileSync(BASELINE_URL, JSON.stringify(payload, null, 2) + "\n");
  console.log(`jsx-a11y baseline written: ${total} violations across ${Object.keys(current).length} files.`);
  process.exit(0);
}

const baseline = JSON.parse(readFileSync(BASELINE_URL, "utf8")).perFile || {};
const regressions = [];
for (const [file, count] of Object.entries(current)) {
  const allowed = baseline[file] || 0;
  if (count > allowed) regressions.push(`${file}: ${count} > ${allowed}`);
}
const improved = Object.entries(baseline).filter(([f, n]) => (current[f] || 0) < n);

console.log(`jsx-a11y violations: ${total} across ${Object.keys(current).length} files`);
if (regressions.length > 0) {
  console.error(`\n❌ jsx-a11y ratchet: ${regressions.length} file(s) regressed:`);
  for (const r of regressions) console.error(`   ${r}`);
  console.error(`\n${FIX_HINT}`);
  process.exit(1);
}
if (improved.length > 0) {
  console.log(
    `\n✅ ${improved.length} file(s) improved — run \`node scripts/check-a11y-ratchet.mjs --update\` ` +
      `to lock in the gain.`,
  );
}
console.log("✅ jsx-a11y ratchet holds (per-file).");
