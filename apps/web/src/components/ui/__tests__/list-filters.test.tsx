/**
 * `ListFilters` — on a phone the list's controls wait behind « Filters ».
 *
 * The width is the only thing that decides the shape, so the tests answer the
 * media query themselves: the suite's default `matchMedia` says « not a
 * phone », which is also what the server renders.
 */
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import en from '@/../locales/en/translation.json';
import fr from '@/../locales/fr/translation.json';
import { Star } from '@/lib/icons';

const language = vi.hoisted(() => ({ value: 'en' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const common = (language.value === 'fr' ? fr : en).common;
      if (key === 'common.filters') return common.filters;
      if (key === 'common.filters_none') return common.filters_none;
      return key;
    },
  }),
}));

import { FilterChip } from '../filter-chip';
import { LIST_FILTERS_FOLD, ListToolbar } from '../list-toolbar';

type Sort = 'recent' | 'name';

/** Answer the fold's own query, and only it, as a phone or a wider screen would. */
function onScreen(kind: 'phone' | 'wide') {
  vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
    matches: kind === 'phone' && query === LIST_FILTERS_FOLD,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function People({ initiallyFavourites = false }: { initiallyFavourites?: boolean }) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<Sort>('recent');
  const [favourites, setFavourites] = useState(initiallyFavourites);
  return (
    <>
      <ListToolbar<Sort>
        query={query}
        onQuery={setQuery}
        searchLabel="Search people"
        sort={sort}
        onSort={setSort}
        sortLabel="Sort by"
        sortOptions={[
          { value: 'recent', label: 'Most recent' },
          { value: 'name', label: 'Name' },
        ]}
        active={favourites ? ['Favourites only'] : []}
        chips={
          <FilterChip
            active={favourites}
            label="Favourites only"
            icon={Star}
            onToggle={() => setFavourites(value => !value)}
          />
        }
      />
      <output aria-label="Applied order">{sort}</output>
    </>
  );
}

/** The fold's toggle, found by the words a reader sees on it. */
function fold(title: string) {
  const summary = screen.getByText(title, { selector: 'summary span' }).closest('summary');
  if (!summary) throw new Error(`no fold titled "${title}"`);
  return summary;
}

afterEach(() => {
  language.value = 'en';
  vi.mocked(window.matchMedia).mockReset();
});

describe('ListFilters', () => {
  it('leaves every control in the open from the `sm` width up', () => {
    onScreen('wide');
    renderWithProviders(<People />);
    expect(screen.getByRole('combobox', { name: 'Sort by' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Favourites only' })).toBeVisible();
    expect(screen.queryByText(en.common.filters)).not.toBeInTheDocument();
  });

  it.each([
    ['en', en.common.filters, en.common.filters_none],
    ['fr', fr.common.filters, fr.common.filters_none],
  ])(
    'folds them on a phone behind a named summary saying nothing is filtered (%s)',
    (lng, title, none) => {
      language.value = lng;
      onScreen('phone');
      renderWithProviders(<People />);

      // The search is not a filter to fold: the reader types at once.
      expect(screen.getByRole('searchbox', { name: 'Search people' })).toBeVisible();
      // Folded means unmounted: nothing to tab through before the list.
      expect(screen.queryByRole('combobox', { name: 'Sort by' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Favourites only' })).not.toBeInTheDocument();

      const summary = fold(title);
      expect(summary.closest('details')).not.toHaveAttribute('open');
      expect(within(summary).getByText(none)).toBeVisible();
    }
  );

  it('opens on the summary and keeps the controls working', async () => {
    onScreen('phone');
    const { user } = renderWithProviders(<People />);
    const summary = fold(en.common.filters);

    await user.click(summary);
    expect(summary.closest('details')).toHaveAttribute('open');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort by' }), 'name');
    expect(screen.getByLabelText('Applied order')).toHaveTextContent('name');

    await user.click(screen.getByRole('button', { name: 'Favourites only' }));
    expect(screen.getByRole('button', { name: 'Favourites only' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    // Still open: a choice does not close the block under the reader's finger.
    expect(summary.closest('details')).toHaveAttribute('open');
    expect(screen.getByRole('combobox', { name: 'Sort by' })).toHaveValue('name');
  });

  it('says how many narrowings apply, and names them, while folded', async () => {
    onScreen('phone');
    const { user } = renderWithProviders(<People initiallyFavourites />);
    const summary = fold(en.common.filters);

    // Folded: the chip itself is unmounted, the summary carries its words.
    expect(screen.queryByRole('button', { name: 'Favourites only' })).not.toBeInTheDocument();
    expect(within(summary).getByText('Favourites only')).toBeVisible();
    expect(within(summary).getByText('1')).toBeVisible();
    expect(within(summary).queryByText(en.common.filters_none)).not.toBeInTheDocument();

    // Lifting the narrowing brings the summary back to « no filter ».
    await user.click(summary);
    await user.click(screen.getByRole('button', { name: 'Favourites only' }));
    expect(within(summary).getByText(en.common.filters_none)).toBeVisible();
    expect(within(summary).queryByText('1')).not.toBeInTheDocument();
  });
});
