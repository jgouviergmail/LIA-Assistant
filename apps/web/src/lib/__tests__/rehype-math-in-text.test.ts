/**
 * Unit tests for the rehypeMathInText plugin, exercised directly on hast trees
 * (no react-markdown / KaTeX layer). Focuses on the tokenizer edge cases that
 * are awkward to pin down through the full pipeline: currency vs math, unclosed
 * `$$` during streaming, escaped `\$`, adjacency, and skip regions.
 */
import { describe, it, expect } from 'vitest';

import rehypeMathInText from '../rehype-math-in-text';

// Minimal structural hast helpers (mirror the plugin's local types).
interface TNode {
  type: 'text';
  value: string;
}
interface ENode {
  type: 'element';
  tagName: string;
  properties?: Record<string, unknown>;
  children: Node[];
}
type Node = TNode | ENode;

const text = (value: string): TNode => ({ type: 'text', value });
const el = (tagName: string, children: Node[], properties: Record<string, unknown> = {}): ENode => ({
  type: 'element',
  tagName,
  properties,
  children,
});
const root = (children: Node[]) => ({ type: 'root' as const, children });

/** Run the plugin on a tree wrapping a single node and return that node's children. */
function runOn(node: ENode): Node[] {
  const tree = root([node]);
  rehypeMathInText()(tree);
  return (tree.children[0] as ENode).children;
}

/** Class of an element child, or null. */
const classOf = (n: Node): string | null => {
  if (n.type !== 'element') return null;
  const cn = n.properties?.className;
  return Array.isArray(cn) ? String(cn[0]) : null;
};
/** Flattened text of a node. */
const textOf = (n: Node): string =>
  n.type === 'text' ? n.value : n.children.map(textOf).join('');

describe('rehypeMathInText — tokenizer via hast', () => {
  it('turns $$…$$ into a math-display span with trimmed TeX', () => {
    const out = runOn(el('p', [text('avant $$ a + b $$ après')]));
    const span = out.find(n => classOf(n) === 'math-display');
    expect(span).toBeDefined();
    expect(textOf(span!)).toBe('a + b');
    expect(out.map(textOf).join('')).toContain('avant ');
    expect(out.map(textOf).join('')).toContain(' après');
  });

  it('turns $…$ into a math-inline span under MathJax rules', () => {
    const out = runOn(el('p', [text('la valeur $x^2$ ici')]));
    const span = out.find(n => classOf(n) === 'math-inline');
    expect(span).toBeDefined();
    expect(textOf(span!)).toBe('x^2');
  });

  it('leaves currency $ as literal text (no span)', () => {
    const out = runOn(el('p', [text('tarif 1,50$ puis 9$ en sortie')]));
    expect(out.every(n => classOf(n) === null)).toBe(true);
    expect(textOf({ type: 'element', tagName: 'p', children: out } as ENode)).toContain('9$ en sortie');
  });

  it('does not treat "$5 and $6" as math', () => {
    const out = runOn(el('p', [text('coûte $5 and $6 total')]));
    expect(out.some(n => classOf(n)?.startsWith('math'))).toBe(false);
  });

  it('keeps an unclosed $$ literal (streaming) — never an empty inline', () => {
    const out = runOn(el('p', [text('mesure par $$ P(G) = \\frac{1')]));
    expect(out.some(n => classOf(n)?.startsWith('math'))).toBe(false);
    expect(out.map(textOf).join('')).toContain('$$ P(G)');
  });

  it('renders escaped \\$ as a literal dollar (outside math)', () => {
    const out = runOn(el('p', [text('prix \\$5 net')]));
    expect(out.some(n => classOf(n)?.startsWith('math'))).toBe(false);
    expect(out.map(textOf).join('')).toBe('prix $5 net');
  });

  it('closes adjacent inline runs correctly ($a$$b$ → a, b)', () => {
    // Regression guard for the removed `$$`-guard in findClosingSingle.
    const out = runOn(el('p', [text('$a$$b$')]));
    const spans = out.filter(n => classOf(n) === 'math-inline');
    expect(spans.map(textOf)).toEqual(['a', 'b']);
  });

  it('skips $ inside <code>', () => {
    const out = runOn(el('p', [text('lance '), el('code', [text('echo $PATH')]), text(' now')]));
    // The <code> element is preserved untouched; no math span inside it.
    const code = out.find(n => n.type === 'element' && (n as ENode).tagName === 'code') as ENode;
    expect(code.children).toEqual([text('echo $PATH')]);
  });

  it('does not double-process text already inside a math element', () => {
    const out = runOn(
      el('p', [el('span', [text('x^2')], { className: ['math-inline'] }), text(' and $y$')])
    );
    // The pre-existing math-inline span keeps its single text child (untouched)...
    const existing = out[0] as ENode;
    expect(existing.children).toEqual([text('x^2')]);
    // ...while the new `$y$` is converted.
    expect(out.some(n => classOf(n) === 'math-inline' && textOf(n) === 'y')).toBe(true);
  });

  it('handles mixed inline math + currency on the same line', () => {
    const out = runOn(el('p', [text('valeur $x^2$ coûte 9$ en sortie')]));
    expect(out.some(n => classOf(n) === 'math-inline' && textOf(n) === 'x^2')).toBe(true);
    expect(out.map(textOf).join('')).toContain('9$ en sortie');
  });
});
