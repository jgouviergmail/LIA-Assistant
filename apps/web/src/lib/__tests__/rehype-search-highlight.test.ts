/**
 * rehype-search-highlight — hast-level transform tests (QW-2).
 *
 * The plugin is the only XSS-conformant way to highlight search matches in
 * LLM bubbles: it must wrap ORIGINAL characters on accent/case-insensitive
 * matches, never touch code/KaTeX regions, and treat the user's term as a
 * literal (never a pattern).
 */
import { describe, expect, it } from 'vitest';

import rehypeSearchHighlight, { SEARCH_MARK_CLASS } from '../rehype-search-highlight';

interface TestNode {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: TestNode[];
  value?: string;
}

function text(value: string): TestNode {
  return { type: 'text', value };
}

function el(tagName: string, children: TestNode[], properties?: Record<string, unknown>): TestNode {
  return { type: 'element', tagName, properties, children };
}

function root(...children: TestNode[]): { type: string; children: TestNode[] } {
  return { type: 'root', children };
}

function run(tree: { type: string; children: TestNode[] }, query: string) {
  rehypeSearchHighlight({ query })(tree as never);
  return tree;
}

/** Flatten a node to `text` / `[marked]` segments for compact assertions. */
function flatten(node: TestNode): string {
  if (node.type === 'text') return node.value ?? '';
  const inner = (node.children ?? []).map(flatten).join('');
  if (node.tagName === 'mark') return `[${inner}]`;
  return inner;
}

describe('rehypeSearchHighlight', () => {
  it('wraps an accent-insensitive match while keeping the original characters', () => {
    const tree = root(el('p', [text('Note la RÉUNION de demain')]));

    run(tree, 'reunion');

    expect(flatten(tree.children[0])).toBe('Note la [RÉUNION] de demain');
    const mark = tree.children[0].children![1];
    expect(mark.tagName).toBe('mark');
    expect(mark.properties).toEqual({ className: [SEARCH_MARK_CLASS] });
  });

  it('matches the accented direction too (query café, text cafe)', () => {
    const tree = root(el('p', [text('un cafe serré')]));

    run(tree, 'Café');

    expect(flatten(tree.children[0])).toBe('un [cafe] serré');
  });

  it('marks every occurrence in a text node', () => {
    const tree = root(el('p', [text('pizza et re-pizza')]));

    run(tree, 'pizza');

    expect(flatten(tree.children[0])).toBe('[pizza] et re-[pizza]');
  });

  it('maps multi-codepoint characters correctly (match containing é)', () => {
    const tree = root(el('p', [text('un café au lait')]));

    run(tree, 'cafe au');

    expect(flatten(tree.children[0])).toBe('un [café au] lait');
  });

  it('leaves non-matching nodes untouched', () => {
    const paragraph = el('p', [text('rien à voir')]);
    const tree = root(paragraph);

    run(tree, 'pizza');

    expect(paragraph.children).toHaveLength(1);
    expect(paragraph.children![0].value).toBe('rien à voir');
  });

  it('treats the query as a literal, never a pattern', () => {
    const tree = root(el('p', [text('code c++ et remise 50% ce soir')]));

    run(tree, 'c++');
    expect(flatten(tree.children[0])).toBe('code [c++] et remise 50% ce soir');

    const tree2 = root(el('p', [text('remise 50% ce soir')]));
    run(tree2, '50%');
    expect(flatten(tree2.children[0])).toBe('remise [50%] ce soir');
  });

  it('skips code, pre and existing mark regions', () => {
    const tree = root(
      el('p', [
        el('code', [text('pizza in code')]),
        el('pre', [el('code', [text('pizza in pre')])]),
        el('mark', [text('pizza already marked')]),
        text(' pizza outside'),
      ])
    );

    run(tree, 'pizza');

    expect(flatten(tree.children[0])).toBe(
      'pizza in codepizza in pre[pizza already marked] [pizza] outside'
    );
  });

  it('skips KaTeX and math marker output', () => {
    const tree = root(
      el('p', [
        el('span', [text('pizza formula')], { className: ['katex'] }),
        el('span', [text('pizza inline')], { className: ['math-inline'] }),
        text(' pizza plain'),
      ])
    );

    run(tree, 'pizza');

    expect(flatten(tree.children[0])).toBe('pizza formulapizza inline [pizza] plain');
  });

  it('is a no-op for empty or whitespace queries', () => {
    const paragraph = el('p', [text('pizza')]);
    const tree = root(paragraph);

    run(tree, '   ');

    expect(paragraph.children).toHaveLength(1);
    expect(paragraph.children![0].type).toBe('text');
  });
});
