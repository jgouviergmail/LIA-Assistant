import { toast } from 'sonner';
import { createRef } from 'react';
import { RelationsWorkspace } from '@/components/relations/RelationsWorkspace';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { RelationSummary } from '@/hooks/useRelations';
import RelationsPage from '@/app/[lng]/dashboard/relations/page';

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { sms_enabled: true } } }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
const overview = vi.hoisted(() => ({
  initialLoading: false,
  hideFirst: false,
  toggleFavorite: vi.fn().mockResolvedValue({ ok: true }),
  setDebriefEnabled: vi.fn(),
}));
const account = vi.hoisted(() => ({ id: 'owner-a' }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
vi.mock('@/components/relations/RelationDetailPanel', () => ({
  RelationDetailPanel: ({
    name,
    onBack,
    onToggleFavorite,
    onDebriefToggle,
    isFavorite,
  }: {
    name: string;
    onBack(): void;
    isFavorite: boolean;
    onToggleFavorite(name: string, next: boolean): void;
    onDebriefToggle(next: boolean): void;
  }) => (
    <div>
      <h2>{name}</h2>
      <button onClick={onBack}>Return</button>
      <button onClick={() => onToggleFavorite(name, !isFavorite)}>Toggle favorite</button>
      <button onClick={() => onDebriefToggle(true)}>Enable debrief</button>
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
    smsAvailable: false,
    relations: overview.hideFirst ? rows.slice(1) : rows,
    relationsTotal: rows.length,
    loading: false,
    initialLoading: overview.initialLoading,
    toggleFavorite: overview.toggleFavorite,
    refetch: vi.fn(),
    debriefEnabled: false,
    setDebriefEnabled: overview.setDebriefEnabled,
  }),
}));
beforeEach(() => {
  vi.clearAllMocks();
  account.id = 'owner-a';
  overview.initialLoading = false;
  overview.hideFirst = false;
  overview.toggleFavorite.mockResolvedValue({ ok: true });
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

it('announces unavailable SMS rather than claiming no relationship activity', () => {
  renderWithProviders(<RelationsPage params={Promise.resolve({ lng: 'en' })} />);
  expect(screen.getByRole('status')).toHaveTextContent('relations.sms_unavailable');
});

it('restores an embedded reader inside its scroll container without moving the world page', async () => {
  const port = createRef<HTMLDivElement>();
  const { user } = renderWithProviders(
    <div ref={port}>
      <RelationsWorkspace
        lng="en"
        scrollPort={{
          read: () => port.current?.scrollTop ?? 0,
          write: top => {
            if (port.current) port.current.scrollTop = top;
          },
        }}
      />
    </div>
  );
  port.current!.scrollTop = 375;
  await user.type(screen.getByRole('searchbox'), 'Alice');
  const card = screen.getByRole('button', { name: /^Alice 0.*relations.no_recent_signal/ });
  await user.click(card);
  expect(port.current!.scrollTop).toBe(0);
  await user.click(screen.getByRole('button', { name: 'Return' }));
  await waitFor(() => expect(card).toHaveFocus());
  expect(port.current!.scrollTop).toBe(375);
  expect(screen.getByRole('searchbox')).toHaveValue('Alice');
  expect(window.scrollTo).not.toHaveBeenCalled();
});

it('surfaces a failed favorite from the embedded detail and keeps debrief preferences on the native hook', async () => {
  overview.toggleFavorite.mockResolvedValueOnce({ ok: false });
  const { user } = renderWithProviders(<RelationsWorkspace lng="en" />);
  await user.click(screen.getByRole('button', { name: /^Alice 0.*relations.no_recent_signal/ }));
  await user.click(screen.getByRole('button', { name: 'Toggle favorite' }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('relations.favorite_error'));
  expect(overview.toggleFavorite).toHaveBeenCalledWith('Alice 0', true);
  await user.click(screen.getByRole('button', { name: 'Enable debrief' }));
  expect(overview.setDebriefEnabled).toHaveBeenCalledWith(true);
});

it('shows the initial loading state before exposing an editable relation list', () => {
  overview.initialLoading = true;
  renderWithProviders(<RelationsWorkspace lng="en" />);
  expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Alice/ })).not.toBeInTheDocument();
});

it('restores focus to list controls when the opened card disappears during a refresh', async () => {
  const view = renderWithProviders(<RelationsWorkspace lng="en" />);
  const opener = screen.getByRole('button', { name: /^Alice 0.*relations.no_recent_signal/ });
  await view.user.click(opener);
  overview.hideFirst = true;
  view.rerender(<RelationsWorkspace lng="en" />);
  expect(opener.isConnected).toBe(false);
  await view.user.click(screen.getByRole('button', { name: 'Return' }));
  await waitFor(() =>
    expect(
      screen.getByRole('button', {
        name: 'relations.only_peers',
      })
    ).toHaveFocus()
  );
});
