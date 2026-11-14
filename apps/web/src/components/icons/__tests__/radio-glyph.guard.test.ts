/**
 * The radio is drawn as a set; the broadcast glyph is another meaning.
 *
 * `Radio` is Lucide's broadcast. In the colored styles the radio itself is
 * `RadioSet` (ADR-377, amendment 2026-11-11), and in the line style the two
 * names draw the same glyph: a radio surface importing `Radio` looks right in
 * one style and wrong in the two others, and the obvious name is the wrong one.
 *
 * Neither `tsc` nor a rendering test of one style can see it. Only a rule about
 * WHICH name a module imports does, so every module showing the broadcast
 * declares here what it means by it.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';
import { globSync } from 'tinyglobby';

const SRC = join(process.cwd(), 'src');

/** Who shows the broadcast, and what it stands for there. Never the radio. */
const BROADCAST_MEANINGS: Readonly<Record<string, string>> = {
  'components/faq/FAQContent.tsx': 'the messaging channels',
  'components/landing/TechSection.tsx': 'real-time streaming',
  'components/landing/more/more-data.ts': 'an answer that carries on in the background',
  'components/radio/settings/RadioSourceFields.tsx': "the source reading LIA's own actions",
  'components/settings/CallModeField.tsx': 'the Live direct call mode',
  'components/settings/connectors/HueBridgePairingForm.tsx': 'pairing a bridge remotely',
  'components/voice-toggle.tsx': 'the Live direct voice session',
};

/** The names a module imports from the icon facade, whatever it calls them locally. */
function facadeImports(source: string): string[] {
  const names: string[] = [];
  for (const match of source.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]@\/lib\/icons['"]/g)) {
    for (const binding of match[1].split(',')) {
      const name = binding
        .trim()
        .replace(/^type\s+/, '')
        .split(/\s+as\s+/)[0];
      if (name) names.push(name);
    }
  }
  return names;
}

function importersOf(icon: string): string[] {
  const files = globSync(['**/*.{ts,tsx}'], {
    cwd: SRC,
    ignore: ['**/__tests__/**', '**/*.test.*', 'lib/icons/**'],
  });
  // A silent glob miss would make this guard pass by measuring nothing.
  expect(files.length).toBeGreaterThan(500);
  return files
    .filter(relative => facadeImports(readFileSync(join(SRC, relative), 'utf8')).includes(icon))
    .map(relative => relative.split('\\').join('/'))
    .sort();
}

describe('the radio glyph', () => {
  it('reads an import by the facade name, through aliases and inline types', () => {
    expect(
      facadeImports(
        "import { Bell, Radio as Broadcast, type LucideIcon } from '@/lib/icons';\n" +
          "import type { LucideProps } from '@/lib/icons';\n" +
          "import { Radio } from 'elsewhere';"
      )
    ).toEqual(['Bell', 'Radio', 'LucideIcon']);
    expect(facadeImports("import { RadioSet } from '@/lib/icons';")).not.toContain('Radio');
  });

  it('shows the broadcast only where a module declares what it means by it', () => {
    expect(
      importersOf('Radio'),
      'the radio is `RadioSet`; a module showing the broadcast declares its meaning in BROADCAST_MEANINGS'
    ).toEqual(Object.keys(BROADCAST_MEANINGS).sort());
  });

  it('draws the radio as a set on every surface that names it', () => {
    const surfaces = importersOf('RadioSet');
    // The command, the page, the banner, the card, the settings, the FAQ, the
    // landing, the maps and the showroom: a collapse to a handful is a regression.
    expect(surfaces.length).toBeGreaterThanOrEqual(15);
    for (const surface of [
      'components/radio/RadioControl.tsx',
      'components/radio/RadioPage.tsx',
      'components/radio/RadioBanner.tsx',
      'components/radio/RadioDashboardCard.tsx',
      'components/radio/settings/RadioSettings.tsx',
      'lib/settings-section-icons.ts',
    ]) {
      expect(surfaces).toContain(surface);
    }
  });
});
