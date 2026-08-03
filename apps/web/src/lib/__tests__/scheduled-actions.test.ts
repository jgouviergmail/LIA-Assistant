/**
 * `duplicateTitle` — marking a copy without breaking the column bound.
 *
 * `title` is `max_length=200` server-side. Appending a copy marker to an
 * already-long title would produce a form that looks valid and a create the
 * API refuses, so the bound is respected here, before the reader ever presses
 * save.
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { SCHEDULED_ACTION_TITLE_MAX_LENGTH } from '../constants';
import { duplicateTitle } from '../scheduled-actions';

describe('duplicateTitle', () => {
  it('appends the marker when there is room', () => {
    expect(duplicateTitle('Morning brief', '(copy)')).toBe('Morning brief (copy)');
  });

  it('trims the TITLE, never the marker, when the pair overflows', () => {
    // Losing the marker would leave two identically-named routines — precisely
    // what the reader is duplicating to avoid.
    const result = duplicateTitle('x'.repeat(SCHEDULED_ACTION_TITLE_MAX_LENGTH), '(copy)');

    expect(result).toHaveLength(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
    expect(result.endsWith('(copy)')).toBe(true);
  });

  it('degrades to the marker alone rather than overflowing on an absurd marker', () => {
    const result = duplicateTitle('anything', 'y'.repeat(250));

    expect(result.length).toBeLessThanOrEqual(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
  });

  it('leaves an empty title usable', () => {
    expect(duplicateTitle('', '(copy)')).toBe(' (copy)');
  });
});

describe('truncating a title that contains characters wider than one code unit', () => {
  // `slice` counts UTF-16 code units. An emoji is two of them, so a cut that
  // lands between them leaves half a character — a lone surrogate, which
  // renders as the replacement glyph and is not valid text to send anywhere.
  // Reproduced with a title whose emoji start at an odd offset.
  const suffix = '(copie)';

  function loneSurrogate(value: string): boolean {
    return /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(value);
  }

  it('never cuts a surrogate pair in half', () => {
    const title = `A${'🏃'.repeat(120)}`;

    const result = duplicateTitle(title, suffix);

    expect(loneSurrogate(result)).toBe(false);
  });

  it('still respects the column bound', () => {
    const title = `A${'🏃'.repeat(120)}`;

    expect(duplicateTitle(title, suffix).length).toBeLessThanOrEqual(
      SCHEDULED_ACTION_TITLE_MAX_LENGTH
    );
  });

  it('keeps the copy marker, which is the whole point of the trim', () => {
    const title = `A${'🏃'.repeat(120)}`;

    expect(duplicateTitle(title, suffix).endsWith(suffix)).toBe(true);
  });

  it('leaves a title that fits exactly alone, emoji included', () => {
    const title = '🏃 Course';

    expect(duplicateTitle(title, suffix)).toBe(`${title} ${suffix}`);
  });
});

describe('the title bound against the schema that enforces it', () => {
  // `SCHEDULED_ACTION_TITLE_MAX_LENGTH` is a hand-copied mirror of a bound the
  // BACKEND owns. If the column grows and this stays at 200, duplicates get
  // trimmed for no reason; if the column SHRINKS and this stays, the API
  // refuses a create the form declared valid — the failure this constant was
  // introduced to prevent, pointing the other way.
  //
  // Same mechanism as the SSE contract-symmetry test: re-parse the source when
  // the checkout exposes it. Skipped inside the web dev container, which
  // mounts only apps/web; enforced on host checkouts and in CI.
  const schemaPath = path.resolve(
    process.cwd(),
    '../api/src/domains/scheduled_actions/schemas.py'
  );

  it.skipIf(!fs.existsSync(schemaPath))('matches the Pydantic max_length', () => {
    const source = fs.readFileSync(schemaPath, 'utf-8');
    // Every `title` Field in that module, with its bound.
    const bounds = [...source.matchAll(/title:[^=]*=\s*Field\((?:[^()]|\([^()]*\))*?max_length=(\d+)/gs)].map(
      match => Number(match[1])
    );

    expect(bounds.length, 'no title bound found — the regex or the schema moved').toBeGreaterThan(0);
    for (const bound of bounds) {
      expect(bound).toBe(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
    }
  });
});
