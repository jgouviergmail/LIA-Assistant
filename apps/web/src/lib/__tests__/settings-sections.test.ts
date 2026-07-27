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
  resolveSettingsSection,
  settingsSectionHref,
  type SettingsSectionToken,
} from '../settings-sections';

const SRC = join(process.cwd(), 'src');
const ENTRIES = Object.entries(SETTINGS_SECTIONS);
/** `Object.keys` widens to `string`; the repo idiom is to narrow it back
 *  (cf. `TodayBriefing`, `AdminConnectorsSection`). */
const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

describe('SETTINGS_SECTIONS — the table matches the components', () => {
  it.each(ENTRIES)('%s points at a file that exists', (_token, target) => {
    expect(existsSync(join(SRC, target.declaredIn)), `${target.declaredIn} not found`).toBe(true);
  });

  it.each(ENTRIES)('%s declares the accordion value it claims', (token, target) => {
    const source = readFileSync(join(SRC, target.declaredIn), 'utf8');
    expect(
      source.includes(`value="${target.accordionValue}"`),
      `${token}: ${target.declaredIn} does not declare value="${target.accordionValue}"`
    ).toBe(true);
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
    const page = readFileSync(join(SRC, 'app/[lng]/dashboard/settings/page.tsx'), 'utf8');

    // The page renders TWO layouts (superuser gets a third tab), so a component
    // legitimately appears in several blocks — of the SAME tab.
    const blocks: Array<{ tab: string; body: string }> = [];
    const opener = /<TabsContent value="(preferences|features|administration)">/g;
    const starts = [...page.matchAll(opener)];
    starts.forEach((match, index) => {
      const from = match.index + match[0].length;
      const to = index + 1 < starts.length ? starts[index + 1].index : page.length;
      blocks.push({ tab: match[1], body: page.slice(from, to) });
    });
    expect(
      blocks.length,
      'no TabsContent block found — the scan would pass vacuously'
    ).toBeGreaterThanOrEqual(4);

    for (const [token, target] of ENTRIES) {
      const component =
        target.declaredIn
          .split('/')
          .pop()
          ?.replace(/\.tsx?$/, '') ?? '';
      const tabsRenderingIt = new Set(
        blocks.filter(block => block.body.includes(`<${component} `)).map(block => block.tab)
      );
      // A capability-gated section may not be rendered at all (telephony off):
      // only assert when the page does render it.
      if (tabsRenderingIt.size === 0) continue;
      expect(
        [...tabsRenderingIt],
        `${token}: declared in the "${target.tab}" tab but rendered in ${[...tabsRenderingIt].join(', ')}`
      ).toEqual([target.tab]);
    }
  });
});

describe('resolveSettingsSection', () => {
  it('resolves every declared token', () => {
    for (const [token, target] of ENTRIES) {
      expect(resolveSettingsSection(token)).toEqual(target);
    }
  });

  it('returns null for an absent parameter', () => {
    expect(resolveSettingsSection(null)).toBeNull();
    expect(resolveSettingsSection('')).toBeNull();
  });

  it('returns null for an unknown token rather than guessing', () => {
    // A stale bookmark must land on the default tab, not throw and not open a
    // section the user did not ask for.
    expect(resolveSettingsSection('does-not-exist')).toBeNull();
  });

  it('does not resolve a prototype key', () => {
    // `Record` lookups are attacker-visible through the URL; `constructor`
    // and `__proto__` must not resolve to anything.
    expect(resolveSettingsSection('constructor')).toBeNull();
    expect(resolveSettingsSection('__proto__')).toBeNull();
    expect(resolveSettingsSection('toString')).toBeNull();
  });
});

describe('settingsSectionHref', () => {
  it('builds a localized deep link', () => {
    expect(settingsSectionHref('fr', 'personality')).toBe(
      '/fr/dashboard/settings?section=personality'
    );
  });

  it('produces a link that resolves back to the same target', () => {
    // Round trip: every href the app can build must be understood by the page.
    for (const token of TOKENS) {
      const href = settingsSectionHref('en', token);
      const parsed = new URL(href, 'https://example.test').searchParams.get('section');
      expect(resolveSettingsSection(parsed)).toEqual(SETTINGS_SECTIONS[token]);
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
