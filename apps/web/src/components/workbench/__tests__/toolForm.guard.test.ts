/**
 * One way to open and end a form in the Tools (owner, 2026-11-06).
 *
 * Each tool used to write its own: « Cancel » came in three styles, a head stood centred on a
 * phone in one dialog and at the left in another, a list was drawn four ways. What a tool may no
 * longer reach for is held here, read from its sources, so the next form cannot drift.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

const TOOLS = join(process.cwd(), 'src/components/workbench');

/** The one door. */
const DOOR = 'ToolForm.tsx';

/** An icon with no word: nothing to draw as a button, its colour says the same thing. */
const WORDLESS_CANCEL = new Set(['mail/LabelsManager.tsx']);

const FORBIDDEN: readonly { what: string; pattern: RegExp; except?: ReadonlySet<string> }[] = [
  { what: 'a head of its own', pattern: /\bDialogHeader\b(?<!ToolDialogHeader)/ },
  { what: 'an end of its own', pattern: /\bDialogFooter\b/ },
  { what: 'a question of its own', pattern: /\buseConfirm\(/ },
  { what: 'a list of its own', pattern: /<select\b/ },
  { what: 'a « Cancel » of its own', pattern: /t\('common\.cancel'\)/, except: WORDLESS_CANCEL },
];

function sources(folder: string): string[] {
  return readdirSync(folder).flatMap(name => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return name === '__tests__' ? [] : sources(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

describe('the forms of the Tools', () => {
  const files = sources(TOOLS)
    .map(path => ({
      name: relative(TOOLS, path).split(sep).join('/'),
      text: readFileSync(path, 'utf-8'),
    }))
    .filter(file => file.name !== DOOR);

  it('reads the sources it guards', () => {
    expect(files.length).toBeGreaterThan(100);
    expect(files.some(file => file.text.includes('CancelButton'))).toBe(true);
  });

  it.each(FORBIDDEN)('draw $what nowhere but through the door', ({ pattern, except }) => {
    const offenders = files
      .filter(file => pattern.test(file.text) && !except?.has(file.name))
      .map(file => file.name);

    expect(offenders).toEqual([]);
  });

  it('keeps its exceptions true', () => {
    for (const name of WORDLESS_CANCEL) {
      expect(files.find(file => file.name === name)?.text).toContain("aria-label={t('common.cancel')}");
    }
  });
});
