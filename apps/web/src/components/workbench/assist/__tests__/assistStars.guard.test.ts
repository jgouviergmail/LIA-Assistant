/**
 * One mark for what LIA can do in the Tools (ADR-372): a star that does not go through
 * `AssistStars` would keep the person's accent, and the sign would stop meaning anything.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const WORKBENCH = resolve(__dirname, '../..');

/** The stars that are no sign of LIA, each with why. */
const NOT_THE_MARK: Readonly<Record<string, string>> = {
  'assist/AssistStars.tsx': 'the mark itself',
  'lights/ScenePicker.tsx': 'a Hue scene that moves by itself: an effect of the lamps, no model',
};

function sources(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

describe('the assist mark', () => {
  it('is the only star of the Tools', () => {
    const offenders = sources(WORKBENCH)
      .map(path => relative(WORKBENCH, path).replaceAll('\\', '/'))
      .filter(name => !(name in NOT_THE_MARK))
      .filter(name => /\bSparkles\b/.test(readFileSync(join(WORKBENCH, name), 'utf-8')));

    expect(offenders).toEqual([]);
  });

  it('holds no exception that outlived its star', () => {
    const stale = Object.keys(NOT_THE_MARK).filter(
      name => !/\bSparkles\b/.test(readFileSync(join(WORKBENCH, name), 'utf-8'))
    );

    expect(stale).toEqual([]);
  });
});
