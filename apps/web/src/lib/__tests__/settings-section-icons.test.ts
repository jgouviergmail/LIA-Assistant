/**
 * Section icon registry — the rail cannot drift from the sections.
 *
 * The master-detail rail and the overview cards show each section's icon
 * WITHOUT mounting the section, so the icon exists twice: passed to
 * `<SettingsSection icon={…}>` by the component, and declared in
 * `SETTINGS_SECTION_ICONS` for the shell. Two declarations drift; this test
 * makes the registry a mirror the compiler and the source both hold:
 * completeness comes from the `Record` type, agreement comes from reading the
 * icon identifier out of each component's `<SettingsSection>` tag and
 * resolving it through that file's own lucide import aliases.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import * as lucide from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { SETTINGS_SECTION_ICONS } from '../settings-section-icons';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '../settings-sections';
import { SRC } from './helpers/settings-page-source';

const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

/**
 * Tokens whose `declaredIn` is a thin wrapper with no `<SettingsSection>` tag
 * of its own — the icon (like the accordion value) lives in the wrapped file.
 */
const WRAPPED: Readonly<Partial<Record<SettingsSectionToken, string>>> = {
  'admin-consumption-export': 'components/settings/ConsumptionExportSection.tsx',
};

/** lucide local name → canonical export name, from the file's own imports. */
function lucideAliases(source: string): Map<string, string> {
  const aliases = new Map<string, string>();
  for (const importMatch of source.matchAll(
    /import\s*\{([^}]+)\}\s*from\s*'lucide-react'/gs
  )) {
    for (const spec of importMatch[1].split(',')) {
      const [name, alias] = spec.split(/\s+as\s+/).map(part => part.trim());
      if (name) aliases.set(alias ?? name, name);
    }
  }
  return aliases;
}

describe('SETTINGS_SECTION_ICONS', () => {
  it('declares an icon for every token', () => {
    // The `Record` type already forces this at compile time; restated here so
    // a `Partial`-weakening refactor fails a test instead of only a review.
    for (const token of TOKENS) {
      expect(SETTINGS_SECTION_ICONS[token], `${token} has no icon`).toBeDefined();
    }
  });

  it.each(TOKENS)('%s carries the icon its component passes to SettingsSection', token => {
    const file = WRAPPED[token] ?? SETTINGS_SECTIONS[token].declaredIn;
    const source = readFileSync(join(SRC, file), 'utf8');

    const identifiers = new Set(
      [...source.matchAll(/<SettingsSection\b([^>]*?)>/gs)]
        .map(tag => /icon=\{(\w+)\}/.exec(tag[1])?.[1])
        .filter((name): name is string => Boolean(name))
    );
    expect(
      identifiers.size,
      `${file}: expected exactly one distinct SettingsSection icon, found [${[...identifiers].join(', ')}]`
    ).toBe(1);

    const [identifier] = identifiers;
    const canonical = lucideAliases(source).get(identifier);
    expect(canonical, `${file}: ${identifier} is not imported from lucide-react`).toBeDefined();

    const expected = (lucide as unknown as Record<string, unknown>)[canonical as string];
    expect(expected, `lucide-react has no export named ${canonical}`).toBeDefined();
    expect(
      SETTINGS_SECTION_ICONS[token],
      `${token}: registry icon differs from the ${canonical} the component renders`
    ).toBe(expected);
  });
});
