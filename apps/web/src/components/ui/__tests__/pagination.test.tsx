/**
 * Pagination — page navigation logic, boundary disabling, the optional page-size
 * selector and the two layout variants.
 *
 * Exemplar (chantier couverture frontend, Lot 0): a pure presentational
 * component with real branching — no hooks to mock, rendered through the shared
 * `renderWithProviders` harness, assertions on observable behaviour (ARIA
 * landmark, disabled boundaries, callback arguments) rather than markup.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Pagination } from '../pagination';

describe('Pagination — rendering guards', () => {
  it('renders nothing when there is a single page and no page-size selector', () => {
    renderWithProviders(<Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('still renders when there is a single page but a page-size selector is wired', () => {
    renderWithProviders(
      <Pagination
        currentPage={1}
        totalPages={1}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />
    );
    expect(screen.getByRole('navigation', { name: 'common.pagination.label' })).toBeInTheDocument();
  });

  it('exposes a navigation landmark named from the active locale', () => {
    renderWithProviders(<Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.getByRole('navigation', { name: 'common.pagination.label' })).toBeInTheDocument();
  });
});

describe('Pagination — boundary disabling', () => {
  it('disables Previous on the first page', () => {
    renderWithProviders(<Pagination currentPage={1} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /common.previous/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /common.next/ })).toBeEnabled();
  });

  it('disables Next on the last page', () => {
    renderWithProviders(<Pagination currentPage={5} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /common.next/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /common.previous/ })).toBeEnabled();
  });

  it('disables both navigation buttons while loading', () => {
    renderWithProviders(
      <Pagination currentPage={3} totalPages={5} onPageChange={vi.fn()} loading />
    );
    expect(screen.getByRole('button', { name: /common.previous/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /common.next/ })).toBeDisabled();
  });
});

describe('Pagination — navigation callbacks', () => {
  it('moves to the previous page on Previous click', async () => {
    const onPageChange = vi.fn();
    const { user } = renderWithProviders(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    );
    await user.click(screen.getByRole('button', { name: /common.previous/ }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('moves to the next page on Next click', async () => {
    const onPageChange = vi.fn();
    const { user } = renderWithProviders(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    );
    await user.click(screen.getByRole('button', { name: /common.next/ }));
    expect(onPageChange).toHaveBeenCalledWith(4);
  });

  it('does not fire onPageChange when Previous is clicked on the first page', async () => {
    const onPageChange = vi.fn();
    const { user } = renderWithProviders(
      <Pagination currentPage={1} totalPages={5} onPageChange={onPageChange} />
    );
    await user.click(screen.getByRole('button', { name: /common.previous/ }));
    expect(onPageChange).not.toHaveBeenCalled();
  });
});

describe('Pagination — page-size selector', () => {
  it('is absent when no onPageSizeChange handler is provided', () => {
    renderWithProviders(<Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('changing the page size reports the new size and resets to page 1', async () => {
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    const { user } = renderWithProviders(
      <Pagination
        currentPage={3}
        totalPages={5}
        pageSize={20}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />
    );
    await user.selectOptions(screen.getByRole('combobox'), '50');
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});

describe('Pagination — labels and variants', () => {
  it('renders custom i18n labels for the buttons and page info', () => {
    renderWithProviders(
      <Pagination
        currentPage={2}
        totalPages={4}
        onPageChange={vi.fn()}
        labels={{
          previous: 'Prev',
          next: 'Next',
          pageInfo: (current, total) => `Seite ${current} von ${total}`,
        }}
      />
    );
    expect(screen.getByText('Seite 2 von 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Prev/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next/ })).toBeInTheDocument();
  });

  it('shows the total-items suffix when totalItems is provided', () => {
    renderWithProviders(
      <Pagination
        currentPage={1}
        totalPages={3}
        totalItems={42}
        onPageChange={vi.fn()}
        labels={{ totalItems: count => `(${count} résultats)` }}
      />
    );
    expect(screen.getByText('(42 résultats)')).toBeInTheDocument();
  });

  it('renders the navigation landmark in the centered variant', () => {
    renderWithProviders(
      <Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} variant="centered" />
    );
    expect(screen.getByRole('navigation', { name: 'common.pagination.label' })).toBeInTheDocument();
  });
});
