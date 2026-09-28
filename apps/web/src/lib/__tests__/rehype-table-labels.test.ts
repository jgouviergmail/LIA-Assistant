/**
 * rehype-table-labels — every body cell names its column (B2).
 *
 * A table drawn as stacked cards on a narrow screen loses its header row, so
 * each cell must carry the name of the column it belongs to. The names are
 * computed on the hast tree, AFTER the sanitize boundary, from text that was
 * already sanitized — the same posture as `rehype-search-highlight`.
 */
import { describe, expect, it } from 'vitest';

import rehypeTableLabels, {
  TABLE_LABEL_MAX_CHARS,
  type HastParent,
  type HastNodeLike,
} from '../rehype-table-labels';

function text(value: string): HastNodeLike {
  return { type: 'text', value };
}

function el(
  tagName: string,
  children: HastNodeLike[],
  properties: Record<string, unknown> = {}
): HastNodeLike {
  return { type: 'element', tagName, properties, children };
}

function run(...children: HastNodeLike[]): HastParent {
  const tree: HastParent = { type: 'root', children };
  rehypeTableLabels()(tree);
  return tree;
}

function row(tag: 'td' | 'th', ...cells: (string | HastNodeLike)[]): HastNodeLike {
  return el(
    'tr',
    cells.map(cell => (typeof cell === 'string' ? el(tag, [text(cell)]) : cell))
  );
}

/** The `dataLabel` of every cell of every body row, row by row. */
function bodyLabels(tree: HastParent): (string | undefined)[][] {
  const table = tree.children[0] as HastParent;
  const tbody = table.children.find(
    child => (child as { tagName?: string }).tagName === 'tbody'
  ) as HastParent;
  return tbody.children.map(tr =>
    (tr as HastParent).children.map(
      cell =>
        (cell as { properties?: Record<string, unknown> }).properties?.dataLabel as
          | string
          | undefined
    )
  );
}

describe('rehype-table-labels', () => {
  it('names each body cell after its header', () => {
    const tree = run(
      el('table', [
        el('thead', [row('th', 'Restaurant', 'Adresse', 'Prix')]),
        el('tbody', [row('td', 'Chez Marcel', '4 rue Mercière', '30 €')]),
      ])
    );
    expect(bodyLabels(tree)).toEqual([['Restaurant', 'Adresse', 'Prix']]);
  });

  it('follows colspan in the header and in the body', () => {
    const tree = run(
      el('table', [
        el('thead', [
          el('tr', [
            el('th', [text('Nom')]),
            el('th', [text('Horaires')], { colSpan: 2 }),
            el('th', [text('Note')]),
          ]),
        ]),
        el('tbody', [
          el('tr', [
            el('td', [text('A')]),
            el('td', [text('9h')]),
            el('td', [text('18h')]),
            el('td', [text('4,5')]),
          ]),
          el('tr', [el('td', [text('B')], { colSpan: 3 }), el('td', [text('3')])]),
        ]),
      ])
    );
    expect(bodyLabels(tree)).toEqual([
      ['Nom', 'Horaires', 'Horaires', 'Note'],
      ['Nom', 'Note'],
    ]);
  });

  it('skips the columns a rowspan above still occupies', () => {
    const tree = run(
      el('table', [
        el('thead', [row('th', 'Jour', 'Heure', 'Lieu')]),
        el('tbody', [
          el('tr', [
            el('td', [text('Lundi')], { rowSpan: 2 }),
            el('td', [text('9h')]),
            el('td', [text('Paris')]),
          ]),
          row('td', '14h', 'Lyon'),
        ]),
      ])
    );
    expect(bodyLabels(tree)).toEqual([
      ['Jour', 'Heure', 'Lieu'],
      ['Heure', 'Lieu'],
    ]);
  });

  it('keeps a header rowspan inside the header, as the HTML layout does', () => {
    const tree = run(
      el('table', [
        el('thead', [el('tr', [el('th', [text('Nom')], { rowSpan: 3 }), el('th', [text('Âge')])])]),
        el('tbody', [row('td', 'Ada', '36')]),
      ])
    );
    expect(bodyLabels(tree)).toEqual([['Nom', 'Âge']]);
  });

  it('uses a first row made only of <th> as the header when there is no <thead>', () => {
    const tree = run(
      el('table', [el('tbody', [row('th', 'Clé', 'Valeur'), row('td', 'Durée', '2 h')])])
    );
    expect(bodyLabels(tree)).toEqual([
      [undefined, undefined],
      ['Clé', 'Valeur'],
    ]);
  });

  it('labels nothing when the table has no header at all', () => {
    const tree = run(el('table', [el('tbody', [row('td', 'a', 'b'), row('td', 'c', 'd')])]));
    expect(bodyLabels(tree)).toEqual([
      [undefined, undefined],
      [undefined, undefined],
    ]);
  });

  it('keeps an icon ligature out of the label and reads a formula as its source', () => {
    const tree = run(
      el('table', [
        el('thead', [
          el('tr', [
            el('th', [
              el('span', [text('event')], { className: ['material-symbols-outlined'] }),
              text(' Date'),
            ]),
            el('th', [
              el(
                'span',
                [
                  el('span', [el('annotation', [text('x^2')])], { className: ['katex-mathml'] }),
                  el('span', [text('x2')], { className: ['katex-html'] }),
                ],
                { className: ['katex'] }
              ),
            ]),
          ]),
        ]),
        el('tbody', [row('td', '12 août', '4')]),
      ])
    );
    expect(bodyLabels(tree)).toEqual([['Date', 'x^2']]);
  });

  it('collapses whitespace and bounds a very long header', () => {
    const long = 'Colonne '.repeat(40);
    const tree = run(
      el('table', [
        el('thead', [row('th', '  Nom\n  complet ', long)]),
        el('tbody', [row('td', 'x', 'y')]),
      ])
    );
    const [[first, second]] = bodyLabels(tree);
    expect(first).toBe('Nom complet');
    expect(second?.length).toBe(TABLE_LABEL_MAX_CHARS);
    expect(second?.endsWith('…')).toBe(true);
  });

  it('bounds a hostile rowspan/colspan instead of allocating for it', () => {
    const tree = run(
      el('table', [
        el('thead', [row('th', 'A', 'B')]),
        el('tbody', [
          el('tr', [
            el('td', [text('x')], { rowSpan: 65534, colSpan: 1000 }),
            el('td', [text('y')]),
          ]),
          row('td', 'z'),
        ]),
      ])
    );
    // It does not hang, and every cell still gets a verdict.
    expect(bodyLabels(tree)).toHaveLength(2);
  });

  it('states table semantics explicitly, so a stacked (display:block) table keeps them', () => {
    const tree = run(
      el('table', [
        el('thead', [row('th', 'A', 'B')]),
        el('tbody', [el('tr', [el('th', [text('r1')]), el('td', [text('v')])])]),
      ])
    );
    const table = tree.children[0] as HastParent & { properties: Record<string, unknown> };
    expect(table.properties.role).toBe('table');
    const [thead, tbody] = table.children as (HastParent & {
      properties: Record<string, unknown>;
    })[];
    expect(thead.properties.role).toBe('rowgroup');
    const headerCell = (thead.children[0] as HastParent).children[0] as {
      properties: Record<string, unknown>;
    };
    expect(headerCell.properties.role).toBe('columnheader');
    const bodyRow = tbody.children[0] as HastParent & { properties: Record<string, unknown> };
    expect(bodyRow.properties.role).toBe('row');
    const [rowHeader, cell] = bodyRow.children as { properties: Record<string, unknown> }[];
    expect(rowHeader.properties.role).toBe('rowheader');
    expect(cell.properties.role).toBe('cell');
  });

  it('labels a nested table on its own terms, never with the outer headers', () => {
    const inner = el('table', [
      el('thead', [row('th', 'Sous-col')]),
      el('tbody', [row('td', 'v')]),
    ]);
    const tree = run(
      el('table', [
        el('thead', [row('th', 'Externe')]),
        el('tbody', [el('tr', [el('td', [inner])])]),
      ])
    );
    const innerBody = (inner as HastParent).children[1] as HastParent;
    const innerCell = (innerBody.children[0] as HastParent).children[0] as {
      properties: Record<string, unknown>;
    };
    expect(innerCell.properties.dataLabel).toBe('Sous-col');
    expect(bodyLabels(tree)).toEqual([['Externe']]);
  });

  it('leaves everything that is not a table untouched', () => {
    const paragraph = el('p', [text('Pas de tableau')]);
    const tree = run(paragraph);
    expect(tree.children[0]).toEqual(el('p', [text('Pas de tableau')]));
  });
});
