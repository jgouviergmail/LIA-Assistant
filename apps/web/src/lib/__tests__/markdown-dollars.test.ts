/**
 * A referenced dollar is a literal dollar in the chat (ADR-323 review 14).
 *
 * The string step turns each referenced dollar outside code into a marker no
 * math rule reads; the rehype step writes it back — escaped inside a formula,
 * as itself everywhere else, attribute values included. The chat's whole
 * pipeline is pinned by the data-literal corpus (`dollars`, `escaped-dollar`);
 * these cases pin the two steps alone.
 */

import { describe, expect, it } from 'vitest';

import rehypeRestoreDollars, { DOLLAR_MARKER, protectReferencedDollars } from '../markdown-dollars';

interface Node {
  type: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: Node[];
}

const BACKSLASH = String.fromCodePoint(92);

describe('protectReferencedDollars', () => {
  it('marks every spelling of a referenced dollar outside code', () => {
    expect(protectReferencedDollars('&#36;5 &#x24;6 &#0036;7 &#X024;8')).toBe(
      `${DOLLAR_MARKER}5 ${DOLLAR_MARKER}6 ${DOLLAR_MARKER}7 ${DOLLAR_MARKER}8`
    );
  });

  it('leaves code, raw dollars and other references alone', () => {
    const text = 'x `&#36;` y\n```\n&#36;\n```\n$raw &#35;';

    expect(protectReferencedDollars(text)).toBe(text);
  });

  it('returns a text holding no reference unchanged', () => {
    expect(protectReferencedDollars('$a$ et $b$')).toBe('$a$ et $b$');
  });
});

describe('rehypeRestoreDollars', () => {
  it('writes each marker back as its surroundings read it', () => {
    const tree: Node = {
      type: 'root',
      children: [
        { type: 'text', value: `prix ${DOLLAR_MARKER}5` },
        {
          type: 'element',
          properties: { className: ['math-inline'] },
          children: [{ type: 'text', value: `a${DOLLAR_MARKER}b` }],
        },
        {
          type: 'element',
          properties: {
            href: `https://e.example/${encodeURIComponent(DOLLAR_MARKER)}x`,
            title: `t${DOLLAR_MARKER}`,
          },
          children: [],
        },
      ],
    };

    rehypeRestoreDollars()(tree);

    const [text, math, link] = tree.children ?? [];
    expect(text.value).toBe('prix $5');
    expect(math.children?.[0].value).toBe(`a${BACKSLASH}$b`);
    expect(link.properties).toEqual({ href: 'https://e.example/$x', title: 't$' });
  });
});
