/**
 * GuideTable — cell accessible names (audit F012).
 *
 * Guide table cells render repo-compiled HTML via dangerouslySetInnerHTML,
 * which static analysis (and the accessible-name computation on some AT
 * paths) cannot see. Each cell therefore carries aria-label = its own plain
 * text, so the programmatic name always equals the visible content.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { GuideTable } from '../GuideLayout';

describe('GuideTable cell names (F012)', () => {
  it('names every cell with the plain text of its compiled HTML', () => {
    render(
      <GuideTable
        headers={['Feature', 'Status']}
        rows={[
          ['<code>pipeline</code> mode', '<strong>shipped</strong>'],
          ['plain text', 'also plain'],
        ]}
      />
    );

    // Accessible name == visible text, markup stripped (label-in-name).
    expect(screen.getByRole('cell', { name: 'pipeline mode' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'shipped' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'plain text' })).toBeTruthy();

    // The rendered markup itself is preserved (name does not replace content).
    expect(document.querySelector('td code')?.textContent).toBe('pipeline');
  });

  it('collapses whitespace in the derived name', () => {
    render(<GuideTable headers={['H']} rows={[['a   <em>b</em>\n c']]} />);
    expect(screen.getByRole('cell', { name: 'a b c' })).toBeTruthy();
  });
});
