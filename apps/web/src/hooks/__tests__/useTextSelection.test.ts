/**
 * readScopedSelection (C-02) — the selection reader's refusal rules.
 *
 * What must hold:
 *  - a selection INSIDE one assistant scope reads as its trimmed text;
 *  - collapsed, too-short, out-of-scope and CROSS-SCOPE selections read null
 *    (quoting across two answers would stitch unrelated sentences);
 *  - a selection starting in a scope but leaking outside reads null.
 */

import { describe, it, expect, beforeAll, beforeEach } from 'vitest';

import { readScopedSelection, SELECTION_MIN_LENGTH } from '../useTextSelection';

beforeAll(() => {
  // jsdom implements Range but not its geometry — every real browser does.
  if (typeof Range.prototype.getBoundingClientRect !== 'function') {
    Range.prototype.getBoundingClientRect = () =>
      ({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0, x: 0, y: 0 }) as DOMRect;
  }
});

function mount(html: string): void {
  document.body.innerHTML = html;
}

function selectAcross(
  startNode: Node,
  startOffset: number,
  endNode: Node,
  endOffset: number
): void {
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const selection = document.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

beforeEach(() => {
  document.getSelection()?.removeAllRanges();
  document.body.innerHTML = '';
});

describe('readScopedSelection', () => {
  it('reads a selection inside one assistant scope', () => {
    mount('<div data-selection-scope="assistant"><p id="p">La réponse utile.</p></div>');
    const text = document.getElementById('p')!.firstChild!;
    selectAcross(text, 3, text, 10);

    const snapshot = readScopedSelection(document);
    expect(snapshot?.text).toBe('réponse');
  });

  it('reads null outside any scope', () => {
    mount('<p id="p">Texte hors périmètre sélectionnable.</p>');
    const text = document.getElementById('p')!.firstChild!;
    selectAcross(text, 0, text, 10);
    expect(readScopedSelection(document)).toBeNull();
  });

  it('reads null across TWO assistant scopes (two answers)', () => {
    mount(
      '<div data-selection-scope="assistant"><p id="a">Première réponse.</p></div>' +
        '<div data-selection-scope="assistant"><p id="b">Seconde réponse.</p></div>'
    );
    selectAcross(
      document.getElementById('a')!.firstChild!,
      0,
      document.getElementById('b')!.firstChild!,
      7
    );
    expect(readScopedSelection(document)).toBeNull();
  });

  it('reads null when the selection leaks out of the scope', () => {
    mount(
      '<div data-selection-scope="assistant"><p id="in">Dedans.</p></div><p id="out">Dehors.</p>'
    );
    selectAcross(
      document.getElementById('in')!.firstChild!,
      0,
      document.getElementById('out')!.firstChild!,
      5
    );
    expect(readScopedSelection(document)).toBeNull();
  });

  it('reads null on a collapsed or too-short selection', () => {
    mount('<div data-selection-scope="assistant"><p id="p">abcdef</p></div>');
    const text = document.getElementById('p')!.firstChild!;

    selectAcross(text, 2, text, 2); // collapsed
    expect(readScopedSelection(document)).toBeNull();

    selectAcross(text, 0, text, SELECTION_MIN_LENGTH - 1); // below the floor
    expect(readScopedSelection(document)).toBeNull();
  });
});
