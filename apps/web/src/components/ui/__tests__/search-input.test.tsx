/**
 * SearchInput — debounced search box with a clear button, Escape-to-clear and a
 * loading indicator.
 *
 * Exemplar (chantier couverture frontend, Lot 0): the interaction pattern —
 * `userEvent` typing, `useDebounce` mocked to identity (established convention,
 * see ConsumptionExportSection) so the debounced callback fires synchronously
 * and the tests drive behaviour without timer juggling. The debounce *timing*
 * itself is covered by `hooks/__tests__/useDebounce.test.ts`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('@/hooks/useDebounce', () => ({ useDebounce: (value: unknown) => value }));

import { SearchInput } from '../search-input';

describe('SearchInput — structure', () => {
  it('renders a searchbox labelled by its placeholder', () => {
    renderWithProviders(<SearchInput placeholder="Search users..." onSearchChange={vi.fn()} />);
    expect(screen.getByRole('searchbox', { name: 'Search users...' })).toBeInTheDocument();
  });
});

describe('SearchInput — typing', () => {
  it('reflects typed characters and reports the debounced value', async () => {
    const onSearchChange = vi.fn();
    const { user } = renderWithProviders(<SearchInput onSearchChange={onSearchChange} />);
    const box = screen.getByRole('searchbox');

    await user.type(box, 'alice');

    expect(box).toHaveValue('alice');
    expect(onSearchChange).toHaveBeenLastCalledWith('alice');
  });
});

describe('SearchInput — clear affordances', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a clear button only once there is text, and clearing empties the box', async () => {
    const onSearchChange = vi.fn();
    const { user } = renderWithProviders(<SearchInput onSearchChange={onSearchChange} />);
    const box = screen.getByRole('searchbox');

    expect(screen.queryByRole('button', { name: 'settings.search.clear' })).not.toBeInTheDocument();

    await user.type(box, 'abc');
    const clear = screen.getByRole('button', { name: 'settings.search.clear' });
    await user.click(clear);

    expect(box).toHaveValue('');
    expect(onSearchChange).toHaveBeenLastCalledWith('');
  });

  it('clears the box when Escape is pressed while it has content', async () => {
    const onSearchChange = vi.fn();
    const { user } = renderWithProviders(<SearchInput onSearchChange={onSearchChange} />);
    const box = screen.getByRole('searchbox');

    await user.type(box, 'abc');
    await user.type(box, '{Escape}');

    expect(box).toHaveValue('');
    expect(onSearchChange).toHaveBeenLastCalledWith('');
  });

  it('hides the clear button and does not render it when clearable is false', async () => {
    const { user } = renderWithProviders(
      <SearchInput onSearchChange={vi.fn()} clearable={false} />
    );
    await user.type(screen.getByRole('searchbox'), 'abc');
    expect(screen.queryByRole('button', { name: 'settings.search.clear' })).not.toBeInTheDocument();
  });
});

describe('SearchInput — loading', () => {
  it('shows a loading indicator and suppresses the clear button while loading', () => {
    renderWithProviders(<SearchInput onSearchChange={vi.fn()} value="abc" loading />);
    expect(screen.getByRole('status', { name: 'common.loading' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'settings.search.clear' })).not.toBeInTheDocument();
  });
});

describe('SearchInput — controlled value', () => {
  it('adopts an externally provided value', () => {
    renderWithProviders(<SearchInput onSearchChange={vi.fn()} value="preset" />);
    expect(screen.getByRole('searchbox')).toHaveValue('preset');
  });
});
