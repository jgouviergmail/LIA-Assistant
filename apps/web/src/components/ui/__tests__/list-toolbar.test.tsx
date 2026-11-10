import { useState } from 'react';
import { expect, it } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ListSearch } from '../list-toolbar';

function ControlledSearch() {
  const [query, setQuery] = useState('');
  return (
    <>
      <ListSearch query={query} onQuery={setQuery} searchLabel="Search records" />
      <output aria-label="Applied query">{query}</output>
    </>
  );
}

it('keeps every typed character while the controlled list applies each change', async () => {
  const { user } = renderWithProviders(<ControlledSearch />);
  const search = screen.getByRole('searchbox', { name: 'Search records' });
  await user.type(search, 'été vacances');
  expect(search).toHaveValue('été vacances');
  expect(screen.getByLabelText('Applied query')).toHaveTextContent('été vacances');
  await user.keyboard('{Escape}');
  expect(search).toHaveValue('');
  expect(screen.getByLabelText('Applied query')).toBeEmptyDOMElement();
});
