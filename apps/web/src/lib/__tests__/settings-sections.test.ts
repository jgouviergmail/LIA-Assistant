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
import { exportedComponentOf, settingsPageBlocks, SRC } from './helpers/settings-page-source';

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
 * Shrink-only in spirit — an entry leaves this set when its component declares
 * a literal value, never the reverse without a written reason.
 */
const COMPUTED_VALUE_TOKENS: ReadonlySet<string> = new Set(['user-consumption-export']);

/** `Object.keys` widens to `string`; the repo idiom is to narrow it back
 *  (cf. `TodayBriefing`, `AdminConnectorsSection`). */
const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

describe('SETTINGS_SECTIONS — the table matches the components', () => {
  it.each(ENTRIES)('%s points at a file that exists', (_token, target) => {
    expect(existsSync(join(SRC, target.declaredIn)), `${target.declaredIn} not found`).toBe(true);
  });

  it.each(ENTRIES)('%s declares the accordion value it claims', (token, target) => {
    const source = readFileSync(join(SRC, target.declaredIn), 'utf8');
    if (COMPUTED_VALUE_TOKENS.has(token)) {
      // Relaxed to a quoted literal, and ONLY for the enumerated tokens above:
      // a blanket fallback would silently weaken the check for every future
      // section. A rename still breaks it, which is what the guard is for.
      expect(
        source.includes(`'${target.accordionValue}'`) ||
          source.includes(`"${target.accordionValue}"`),
        `${token}: ${target.declaredIn} never mentions the literal '${target.accordionValue}'`
      ).toBe(true);
      return;
    }
    expect(
      source.includes(`value="${target.accordionValue}"`),
      `${token}: ${target.declaredIn} does not declare value="${target.accordionValue}"`
    ).toBe(true);
  });

  it('keeps the computed-value escape hatch honest', () => {
    // The escape hatch may only name tokens that really do compute their value.
    // Left unchecked it would rot into a place to park any entry that fails the
    // strict form.
    for (const token of COMPUTED_VALUE_TOKENS) {
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
   * The declared TAB must be the tab the component is actually rendered in.
   *
   * `accordionValue` was already checked against the component; the tab was
   * not, and it is the half that decides where the deep link LANDS. A section
   * moved from Features to Preferences would leave every link to it opening the
   * wrong tab and expanding nothing — silently, since the accordion value would
   * still match. Read from the page rather than declared twice.
   */
  it('places every section in the tab the table claims', () => {
    // The page renders TWO layouts (superuser gets a third tab), so a component
    // legitimately appears in several blocks — of the SAME tab. Each block is
    // sliced to its own closing tag by the shared reader, so the `</Tabs>` +
    // second `<Tabs>` preamble sitting between two panels is never attributed
    // to the preceding one.
    const blocks = settingsPageBlocks();
    expect(
      blocks.length,
      'no TabsContent block found — the scan would pass vacuously'
    ).toBeGreaterThanOrEqual(4);

    for (const [token, target] of ENTRIES) {
      const component = exportedComponentOf(target.declaredIn);
      const tabsRenderingIt = [
        ...new Set(
          blocks.filter(block => block.body.includes(`<${component} `)).map(block => block.tab)
        ),
      ];
      // No early `continue` on an empty set. The page renders every section
      // UNCONDITIONALLY in its JSX — a capability-gated one returns null at
      // RUNTIME, which source scanning cannot observe. An empty set therefore
      // means the component is absent from the page entirely, which is the
      // defect this test exists to catch; skipping it is how a table entry
      // could point at a section nobody renders.
      expect(
        tabsRenderingIt,
        tabsRenderingIt.length === 0
          ? `${token}: the page renders no <${component}> at all — the table points at a section that is not on the page`
          : `${token}: declared in the "${target.tab}" tab but rendered in ${tabsRenderingIt.join(', ')}`
      ).toEqual([target.tab]);
    }
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
