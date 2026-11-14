/**
 * SelectionBar — the bar above a list while rows are selected (ADR-259), and its compact form,
 * the one line a tool draws (ADR-369 amendment 2026-11-11): the way out of the selection is an
 * icon beside the count, named by the caller, and the acts follow at the end of the line.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

import { SelectionBar, type SelectionBarProps } from '../selection-bar';

function draw(over: Partial<SelectionBarProps> = {}) {
  const props: SelectionBarProps = {
    regionLabel: 'Selected messages',
    countLabel: '3 selected',
    selectAllLabel: 'Select every message of this page',
    clearLabel: 'Clear the selection',
    pageState: 'some',
    onSelectAll: vi.fn(),
    onClear: vi.fn(),
    children: <button type="button">Archive</button>,
    ...over,
  };
  return { ...renderWithProviders(<SelectionBar {...props} />), props };
}

describe('SelectionBar', () => {
  it('says its way out in words', () => {
    draw();

    const out = screen.getByRole('button', { name: 'Clear the selection' });
    expect(out).toHaveTextContent('Clear the selection');
    expect(out).not.toHaveAttribute('aria-label');
  });

  it('states a page ticked in part, and takes the whole of it', async () => {
    const { user, props } = draw();

    const page = screen.getByRole('checkbox', { name: 'Select every message of this page' });
    expect((page as HTMLInputElement).indeterminate).toBe(true);
    await user.click(page);

    expect(props.onSelectAll).toHaveBeenCalledTimes(1);
  });
});

describe('SelectionBar — compact', () => {
  it.each([['Clear the selection'], ['Effacer la sélection']])(
    'draws its way out as an icon named « %s », between the count and the acts',
    clearLabel => {
      draw({ compact: true, clearLabel });

      const bar = within(screen.getByRole('region', { name: 'Selected messages' }));
      const out = bar.getByRole('button', { name: clearLabel });
      expect(out).toHaveTextContent('');
      expect(out).toHaveAttribute('title', clearLabel);
      expect(bar.getByText('3 selected')).toBeInTheDocument();
      expect(bar.getAllByRole('button').map(button => button.textContent)).toEqual(['', 'Archive']);
    }
  );

  it('empties the selection from it', async () => {
    const { user, props } = draw({ compact: true });

    await user.click(screen.getByRole('button', { name: 'Clear the selection' }));

    expect(props.onClear).toHaveBeenCalledTimes(1);
  });

  it('keeps the page checkbox alone where a caller hides its actions, as the other form does', () => {
    draw({ compact: true, showActions: false });

    const bar = within(screen.getByRole('region', { name: 'Selected messages' }));
    expect(bar.getByRole('checkbox')).toBeInTheDocument();
    expect(bar.queryByRole('button')).toBeNull();
  });

  it('hands its element to whoever measures it', () => {
    const barRef = { current: null as HTMLDivElement | null };

    draw({ compact: true, barRef });

    expect(barRef.current).toBe(screen.getByRole('region', { name: 'Selected messages' }));
  });
});
