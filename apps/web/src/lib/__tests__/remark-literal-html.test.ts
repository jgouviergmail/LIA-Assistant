/**
 * A person's message is read as they wrote it: what looks like a tag is text.
 *
 * `pas </script>, </body> et </html>` used to reach the bubble as `pas ,  et `,
 * and `if a<b and c>d` as `if ad`: the parser read the tags, the sanitizer
 * dropped them, and the words were gone.
 */
import { describe, expect, it } from 'vitest';

import remarkLiteralHtml from '../remark-literal-html';

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hChildren: Node[] };
}

const root = (...children: Node[]): Node => ({ type: 'root', children });

function transform(tree: Node): Node {
  remarkLiteralHtml()(tree);
  return tree;
}

describe('remarkLiteralHtml', () => {
  it('turns inline HTML into text, in place', () => {
    const tree = transform(
      root({
        type: 'paragraph',
        children: [
          { type: 'text', value: 'pas ' },
          { type: 'html', value: '</script>' },
          { type: 'text', value: ' ici' },
        ],
      })
    );
    expect(tree.children?.[0].children).toEqual([
      { type: 'text', value: 'pas ' },
      { type: 'text', value: '</script>' },
      { type: 'text', value: ' ici' },
    ]);
  });

  it('gives block HTML a paragraph, which keeps its line breaks and indentation', () => {
    const text = { type: 'text', value: '<div>\n  a\n</div>' };
    const tree = transform(root({ type: 'html', value: text.value }));
    expect(tree.children).toEqual([
      { type: 'paragraph', children: [text], data: { hChildren: [text] } },
    ]);
  });

  it.each(['blockquote', 'listItem', 'footnoteDefinition'])(
    'treats HTML directly under a %s as a block',
    type => {
      const tree = transform(root({ type, children: [{ type: 'html', value: '<b>' }] }));
      expect(tree.children?.[0].children?.[0].type).toBe('paragraph');
    }
  );

  it('reaches inline HTML nested under emphasis and links', () => {
    const tree = transform(
      root({
        type: 'paragraph',
        children: [{ type: 'emphasis', children: [{ type: 'html', value: '<i>' }] }],
      })
    );
    expect(tree.children?.[0].children?.[0].children).toEqual([{ type: 'text', value: '<i>' }]);
  });

  it('leaves every other node alone', () => {
    const code = { type: 'code', value: '<b>' };
    const tree = transform(root(code));
    expect(tree.children).toEqual([code]);
  });
});
