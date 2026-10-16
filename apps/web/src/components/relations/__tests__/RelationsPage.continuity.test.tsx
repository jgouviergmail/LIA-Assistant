import { beforeEach, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { RelationSummary } from '@/hooks/useRelations';
import RelationsPage from '@/app/[lng]/dashboard/relations/page';

const account = vi.hoisted(() => ({ id: 'owner-a' }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
vi.mock('@/components/relations/RelationDetailPanel', () => ({
  RelationDetailPanel: ({ name, onBack }: { name: string; onBack: () => void }) => (
    <div>
      <h2>{name}</h2>
      <button onClick={onBack}>Return</button>
    </div>
  ),
}));
const rows: RelationSummary[] = Array.from({ length: 12 }, (_, index) => ({
  display_name: `Alice ${index}`,
  identity_confidence: 'exact',
  open_loops_count: 0,
  calls_count: 0,
  peer_messages_count: 0,
  last_interaction_at: null,
  is_favorite: false,
  is_peer: index % 2 === 0,
}));
vi.mock('@/hooks/useRelations', () => ({
  useRelationsOverview: () => ({
    relations: rows,
    relationsTotal: rows.length,
    loading: false,
    initialLoading: false,
    toggleFavorite: vi.fn(),
    refetch: vi.fn(),
    debriefEnabled: false,
    setDebriefEnabled: vi.fn(),
  }),
}));
beforeEach(() => {
  account.id = 'owner-a';
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});
it('returns to the same search, sort, filter, card focus and scroll without persisting names', async () => {
  const { user } = renderWithProviders(<RelationsPage params={Promise.resolve({ lng: 'en' })} />);
  vi.spyOn(window, 'scrollY', 'get').mockReturnValue(430);
  await user.type(screen.getByRole('searchbox'), 'Alice');
  await user.selectOptions(screen.getByRole('combobox'), 'name');
  await user.click(screen.getByRole('button', { name: 'relations.only_peers' }));
  const card = screen.getByRole('button', { name: /^Alice 0.*relations.no_recent_signal/ });
  await user.click(card);
  expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Return' }));
  await waitFor(() => expect(card).toHaveFocus());
  expect(screen.getByRole('searchbox')).toHaveValue('Alice');
  expect(screen.getByRole('combobox')).toHaveValue('name');
  expect(screen.getByRole('button', { name: 'relations.only_peers' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top: 430 });
});
it('clears list state when the account changes', async () => {
  const view = renderWithProviders(<RelationsPage params={Promise.resolve({ lng: 'en' })} />);
  await view.user.type(screen.getByRole('searchbox'), 'Alice');
  account.id = 'owner-b';
  view.rerender(<RelationsPage params={Promise.resolve({ lng: 'en' })} />);
  expect(screen.getByRole('searchbox')).toHaveValue('');
});
