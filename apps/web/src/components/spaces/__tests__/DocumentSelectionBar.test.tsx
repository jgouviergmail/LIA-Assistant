/**
 * The bar above the documents while rows are selected (ADR-259): exact count,
 * a select-all that states the partial state, a download of the selection as
 * one archive (a link carrying the ids), move, and a solid red delete.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { DocumentSelectionBar } from '../DocumentSelectionBar';

function render(over: Partial<React.ComponentProps<typeof DocumentSelectionBar>> = {}) {
  const handlers = { onSelectAll: vi.fn(), onClear: vi.fn(), onMove: vi.fn(), onDelete: vi.fn() };
  const utils = renderWithProviders(
    <DocumentSelectionBar
      count={2}
      pageState="some"
      archiveHref="https://api.test/rag-spaces/s1/documents/archive?ids=d1,d2"
      deleting={false}
      {...handlers}
      {...over}
    />
  );
  return { ...utils, ...handlers };
}

describe('DocumentSelectionBar', () => {
  it('states the count, the partial select-all, and links the archive of the selection', () => {
    render();
    expect(
      screen.getByRole('region', { name: 'spaces.documents.selection_region' })
    ).toBeInTheDocument();
    expect(screen.getByText('spaces.documents.selected_count')).toBeInTheDocument();
    const all = screen.getByRole('checkbox', { name: 'spaces.documents.select_all' });
    expect(all).not.toBeChecked();
    expect((all as HTMLInputElement).indeterminate).toBe(true);
    expect(
      screen.getByRole('link', { name: 'spaces.documents.download_selected' })
    ).toHaveAttribute('href', 'https://api.test/rag-spaces/s1/documents/archive?ids=d1,d2');
  });

  it('selects the whole page, clears, moves and deletes', async () => {
    const { user, onSelectAll, onClear, onMove, onDelete } = render();
    await user.click(screen.getByRole('checkbox', { name: 'spaces.documents.select_all' }));
    expect(onSelectAll).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.clear_selection' }));
    expect(onClear).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.move_selected' }));
    expect(onMove).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.delete_selected' }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('clears when every row is already selected and the select-all is clicked', async () => {
    const { user, onClear, onSelectAll } = render({ pageState: 'all' });
    const all = screen.getByRole('checkbox', { name: 'spaces.documents.select_all' });
    expect(all).toBeChecked();
    await user.click(all);
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onSelectAll).not.toHaveBeenCalled();
  });
});
