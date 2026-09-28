/**
 * MarkdownContent — tables (B2).
 *
 * What the pipeline hands to a table must reach the page: the column names
 * written by `rehype-table-labels` (the stacked-card layout prints them), the
 * explicit roles, the spans a model wrote, and a Markdown column's alignment.
 * What must NOT reach it: a model's inline style on a cell — `nowrap` there is
 * the defect this rendering fixes.
 */
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/__tests__/test-utils';

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

const MARKDOWN_TABLE = [
  '| Restaurant | Prix |',
  '| :--- | :---: |',
  '| Chez Marcel | 30 € |',
  '| Le Petit Bistrot | 25 € |',
].join('\n');

describe('MarkdownContent tables', () => {
  it('names every Markdown cell after its column and keeps the column alignment', () => {
    const { container } = render(MARKDOWN_TABLE);
    const cells = [...container.querySelectorAll('tbody td')];
    expect(cells.map(cell => cell.getAttribute('data-label'))).toEqual([
      'Restaurant',
      'Prix',
      'Restaurant',
      'Prix',
    ]);
    // As an attribute, not an inline style: a card must be able to undo it.
    expect(cells[1].getAttribute('data-align')).toBe('center');
    expect((cells[1] as HTMLElement).style.textAlign).toBe('');
    expect(container.querySelector('table')?.getAttribute('role')).toBe('table');
  });

  it('draws a table inside its frame and scroll box', () => {
    const { container } = render(MARKDOWN_TABLE);
    const frame = container.querySelector('.table-frame');
    expect(frame?.querySelector(':scope > .table-wrapper > table')).not.toBeNull();
    expect(frame?.getAttribute('data-stacked')).toBe('false');
  });

  it('forwards the spans a model wrote, which the cells used to drop', () => {
    const { container } = render(
      '<div class="lia-response"><table><thead><tr><th>Nom</th><th colspan="2">Horaires</th>' +
        '</tr></thead><tbody><tr><td>A</td><td>9h</td><td>18h</td></tr>' +
        '<tr><td rowspan="2">B</td><td colspan="2">fermé</td></tr></tbody></table></div>'
    );
    const header = container.querySelector('thead th:nth-child(2)');
    expect(header?.getAttribute('colspan')).toBe('2');
    const spanned = [...container.querySelectorAll('tbody td')].find(
      cell => cell.textContent === 'B'
    );
    expect(spanned?.getAttribute('rowspan')).toBe('2');
    const closed = [...container.querySelectorAll('tbody td')].find(
      cell => cell.textContent === 'fermé'
    );
    expect(closed?.getAttribute('data-label')).toBe('Horaires');
  });

  it("refuses a model's inline style on a cell, keeping only its alignment", () => {
    const { container } = render(
      '<div class="lia-response"><table><thead><tr><th>Avis</th></tr></thead><tbody><tr>' +
        '<td style="white-space: nowrap; width: 900px; text-align: right">Très bon</td>' +
        '</tr></tbody></table></div>'
    );
    const cell = container.querySelector<HTMLElement>('tbody td');
    expect(cell?.getAttribute('style')).toBeNull();
    expect(cell?.getAttribute('data-align')).toBe('right');
  });

  it("keeps a model's class on a cell next to the chat's own", () => {
    const { container } = render(
      '<div class="lia-response"><table><thead><tr><th>A</th></tr></thead><tbody><tr>' +
        '<td class="lia-numeric">42</td></tr></tbody></table></div>'
    );
    const cell = container.querySelector('tbody td');
    expect(cell?.classList.contains('lia-numeric')).toBe(true);
    expect(cell?.classList.contains('text-foreground')).toBe(true);
  });
});
