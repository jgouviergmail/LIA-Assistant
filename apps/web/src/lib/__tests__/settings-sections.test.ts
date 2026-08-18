/**
 * Deep-linkable settings sections (W2) — the table cannot lie.
 *
 * `?section=` used to understand two tokens while the getting-started
 * checklist pointed six of its seven items at the bare settings page. The fix
 * is a table; the risk of a table is that it drifts from the components it
 * describes. Every entry is therefore checked against the source: the file must
 * exist AND declare the accordion value the table claims.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import {
  SETTINGS_SECTIONS,
  isSettingsSectionToken,
  settingsSectionHref,
  type SettingsSectionToken,
} from '../settings-sections';
import { SRC } from './helpers/settings-page-source';

const ENTRIES = Object.entries(SETTINGS_SECTIONS);

/**
 * Sections whose component picks its accordion value at RUNTIME.
 *
 * `ConsumptionExportSection` serves the user and the admin export from one
 * file and selects `'user-consumption-export'` / `'admin-consumption-export'`
 * from its `mode` prop, so the source never contains the `value="…"` prop form
 * the strict check looks for. Enumerated rather than auto-detected: a
 * `value={…}`-shaped fallback would relax the guard for every future section
 * that happens to interpolate, which is exactly how a guard stops guarding.
 *
 * The map value names the file that holds the QUOTED LITERAL when it is not
 * `declaredIn` itself: the admin token's `declaredIn` is the thin
 * `AdminConsumptionExportSection` wrapper (which is what the administration
 * panel renders, so the tab check needs it), while the literal
 * `'admin-consumption-export'` lives in the wrapped component. `null` means
 * the literal sits in `declaredIn`.
 *
 * Shrink-only in spirit — an entry leaves this map when its component declares
 * a literal value, never the reverse without a written reason.
 */
const COMPUTED_VALUE_TOKENS: ReadonlyMap<string, string | null> = new Map([
  ['user-consumption-export', null],
  ['admin-consumption-export', 'components/settings/ConsumptionExportSection.tsx'],
]);

/** `Object.keys` widens to `string`; the repo idiom is to narrow it back
 *  (cf. `TodayBriefing`, `AdminConnectorsSection`). */
const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

describe('SETTINGS_SECTIONS — the table matches the components', () => {
  it.each(ENTRIES)('%s points at a file that exists', (_token, target) => {
    expect(existsSync(join(SRC, target.declaredIn)), `${target.declaredIn} not found`).toBe(true);
  });

  it.each(ENTRIES)('%s declares the accordion value it claims', (token, target) => {
    if (COMPUTED_VALUE_TOKENS.has(token)) {
      // Relaxed to a quoted literal, and ONLY for the enumerated tokens above:
      // a blanket fallback would silently weaken the check for every future
      // section. A rename still breaks it, which is what the guard is for.
      const literalFile = COMPUTED_VALUE_TOKENS.get(token) ?? target.declaredIn;
      const source = readFileSync(join(SRC, literalFile), 'utf8');
      expect(
        source.includes(`'${target.accordionValue}'`) ||
          source.includes(`"${target.accordionValue}"`),
        `${token}: ${literalFile} never mentions the literal '${target.accordionValue}'`
      ).toBe(true);
      return;
    }
    const source = readFileSync(join(SRC, target.declaredIn), 'utf8');
    expect(
      source.includes(`value="${target.accordionValue}"`),
      `${token}: ${target.declaredIn} does not declare value="${target.accordionValue}"`
    ).toBe(true);
  });

  it('keeps the computed-value escape hatch honest', () => {
    // The escape hatch may only name tokens that really do compute their value.
    // Left unchecked it would rot into a place to park any entry that fails the
    // strict form.
    for (const token of COMPUTED_VALUE_TOKENS.keys()) {
      const target = SETTINGS_SECTIONS[token as SettingsSectionToken];
      expect(target, `${token} is allowlisted but not declared`).toBeDefined();
      const source = readFileSync(join(SRC, target.declaredIn), 'utf8');
      expect(
        source.includes(`value="${target.accordionValue}"`),
        `${token} is allowlisted as computed, but ${target.declaredIn} declares value="${target.accordionValue}" literally — drop it from the allowlist`
      ).toBe(false);
    }
  });

  it('uses only real tabs', () => {
    for (const [token, target] of ENTRIES) {
      expect(
        ['preferences', 'features', 'administration'],
        `${token} has an unknown tab`
      ).toContain(target.tab);
    }
  });

  it('keeps tokens URL-safe and stable-looking', () => {
    for (const [token] of ENTRIES) {
      expect(token, `${token} is not a plain URL token`).toMatch(/^[a-z][a-z0-9-]*$/);
    }
  });

  it('never maps two tokens to the same target', () => {
    const seen = ENTRIES.map(([, t]) => `${t.tab}/${t.accordionValue}`);
    expect(new Set(seen).size, `duplicate targets: ${seen.join(', ')}`).toBe(seen.length);
  });

  /**
   * The master-detail page renders FROM this table (rail order, tab and group
   * headings, pane resolution through the registry), so "the page and the
   * table disagree" is no longer a reachable state — the former source-parsing
   * checks died with the hand-written layouts. What remains table-level is
   * that all three audiences are covered: losing the administration entries
   * would silently un-index the admin surface again.
   */
  it('spans all three tabs — the administration deferral is over', () => {
    const tabsInUse = new Set(ENTRIES.map(([, target]) => String(target.tab)));
    expect([...tabsInUse].sort()).toEqual(['administration', 'features', 'preferences']);
  });
});

describe('settingsSectionHref', () => {
  it('builds a localized deep link', () => {
    expect(settingsSectionHref('fr', 'personality')).toBe(
      '/fr/dashboard/settings?section=personality'
    );
  });

  it('produces a link the page understands, back to the same target', () => {
    // Round trip: every href the app can build must survive the URL and resolve
    // to the section it was built from. The page narrows the raw parameter with
    // `isSettingsSectionToken` and indexes the table itself — this mirrors that
    // exact pair rather than a helper nothing calls.
    for (const token of TOKENS) {
      const href = settingsSectionHref('en', token);
      const parsed = new URL(href, 'https://example.test').searchParams.get('section');
      expect(parsed).not.toBeNull();
      expect(isSettingsSectionToken(parsed as string)).toBe(true);
      expect(SETTINGS_SECTIONS[parsed as SettingsSectionToken]).toEqual(SETTINGS_SECTIONS[token]);
    }
  });
});

describe('isSettingsSectionToken — the runtime half of the contract', () => {
  /**
   * The compile-time half is enforced by `tsc` itself: `SETTINGS_SECTIONS` is
   * declared with `satisfies` so `SettingsSectionToken` is the union of its
   * keys. Annotating it `Readonly<Record<string, …>>` instead made the type
   * degrade to `string`, and a typo'd deep link in `StarterChecklistCard` or
   * `briefing-setup` compiled cleanly all the way to a dead link.
   */
  it('accepts every declared token', () => {
    for (const token of TOKENS) expect(isSettingsSectionToken(token)).toBe(true);
  });

  it('rejects an unknown token', () => {
    expect(isSettingsSectionToken('does-not-exist')).toBe(false);
  });

  it('rejects an inherited property', () => {
    // The guard is what stops `?section=constructor` resolving to a truthy
    // object whose `.tab` is undefined.
    expect(isSettingsSectionToken('constructor')).toBe(false);
    expect(isSettingsSectionToken('toString')).toBe(false);
  });
});
