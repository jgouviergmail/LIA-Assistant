/**
 * Refresh-in-place guard — a re-read never empties the screen first.
 *
 * A view that re-reads after a change (`useApplicationResourceSync`) used to
 * empty its data BEFORE reading again: deleting one SMS turned the archive into
 * « loading », closed every open sender and dropped the focus the deletion
 * meant to give back (owner report 2026-10-21, « never a visible reload, on any
 * screen »). What is on screen stays until its successor lands; only a reread
 * that FAILED may withdraw it — after its `await`, because a failed read cannot
 * vouch for data an erasure may have removed.
 *
 * Clearing bookkeeping is not clearing data: a failure, an error, a cursor or a
 * pagination trail, a busy flag may be reset up front.
 */

import { describe, it, expect } from 'vitest';

import { readSources } from './source-scan';

const SYNC = /useApplicationResourceSync\(\s*[^,]+,\s*[^,]+,\s*([A-Za-z_][A-Za-z0-9_]*)/g;
const CLEAR = /\b(acceptData|set[A-Z][A-Za-z0-9]*)\(\s*(?:null|undefined|\[\])\s*\)/g;
const BOOKKEEPING = /failure|error|cursor|trail|busy|refreshing/i;

/** The body of `const name = useCallback(…)`, or null when it is not one. */
function callbackBody(text: string, name: string): string | null {
  const start = new RegExp(`const ${name}\\s*=\\s*useCallback\\(`).exec(text);
  if (!start) return null;
  let depth = 1;
  let index = start.index + start[0].length;
  while (index < text.length && depth > 0) {
    if (text[index] === '(') depth += 1;
    else if (text[index] === ')') depth -= 1;
    index += 1;
  }
  return text.slice(start.index + start[0].length, index);
}

const SOURCES = readSources(file => /\.(ts|tsx)$/.test(file.relative) && !file.isTest).filter(
  file => file.text.includes('useApplicationResourceSync(')
);

describe('a resource re-read keeps the screen until its answer lands', () => {
  it('finds the views it guards', () => {
    expect(SOURCES.length).toBeGreaterThan(10);
  });

  it('never empties data before the first await of a refresh', () => {
    const offenders: string[] = [];
    for (const file of SOURCES) {
      for (const sync of file.text.matchAll(SYNC)) {
        const body = callbackBody(file.text, sync[1]);
        if (body === null) continue;
        const beforeRead = body.split('await')[0];
        for (const clear of beforeRead.matchAll(CLEAR)) {
          if (!BOOKKEEPING.test(clear[1])) offenders.push(`${file.relative}: ${clear[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
