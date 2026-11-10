import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { RAGSpace, RAGSpaceListResponse } from '@/types/rag-spaces';

const { get, patch, auth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  auth: { user: { id: 'owner' } },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => auth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch },
}));
import { SpacesManager } from '../SpacesManager';

const empty: RAGSpaceListResponse = { spaces: [], total: 0 };
const space = (overrides: Partial<RAGSpace> = {}): RAGSpace => ({
  id: 'space-1',
  name: 'Research',
  description: null,
  is_active: false,
  is_favorite: false,
  kind: null,
  document_count: 0,
  ready_document_count: 0,
  total_size: 0,
  created_at: '2026-11-01T12:00:00Z',
  updated_at: '2026-11-01T12:00:00Z',
  ...overrides,
});
beforeEach(() => {
  vi.resetAllMocks();
  auth.user = { id: 'owner' };
  get.mockResolvedValue(empty);
});

describe('knowledge-space filtering in both native doors', () => {
  it.each(['page', 'section'] as const)(
    'keeps the managed filter and query when a favorite moves bands in %s',
    async variant => {
      let managed = space({ kind: 'bookmarks', name: 'Saved answers' });
      const personal = space({ id: 'personal', name: 'Personal' });
      get.mockImplementation(async () => ({ spaces: [managed, personal], total: 2 }));
      patch.mockImplementation(async (_path: string, payload: { is_favorite: boolean }) => {
        managed = { ...managed, is_favorite: payload.is_favorite };
        return managed;
      });
      const { user } = renderWithProviders(<SpacesManager variant={variant} />);
      await screen.findByText('Saved answers');
      await user.click(screen.getByRole('button', { name: 'spaces.managed.hint' }));
      expect(screen.queryByText('Personal')).not.toBeInTheDocument();
      await user.type(screen.getByRole('searchbox'), 'saved');
      await waitFor(() =>
        expect(get).toHaveBeenLastCalledWith(
          '/rag-spaces',
          expect.objectContaining({ params: expect.objectContaining({ q: 'saved' }) })
        )
      );
      const star = await screen.findByRole('button', { name: 'spaces.favorite_add' });
      star.focus();
      await user.keyboard(' ');
      const favorites = await screen.findByRole('region', { name: 'spaces.favorites_title' });
      expect(within(favorites).getByText('Saved answers')).toBeInTheDocument();
      expect(patch).toHaveBeenCalledWith('/rag-spaces/space-1', { is_favorite: true }, undefined);
      expect(screen.getByRole('searchbox')).toHaveValue('saved');
      expect(screen.getByRole('button', { name: 'spaces.managed.hint' })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'spaces.favorite_remove' })).toHaveFocus()
      );
      await user.keyboard(' ');
      await waitFor(() =>
        expect(
          screen.queryByRole('region', { name: 'spaces.favorites_title' })
        ).not.toBeInTheDocument()
      );
      expect(
        within(screen.getByRole('region', { name: 'spaces.others_title' })).getByText(
          'Saved answers'
        )
      ).toBeInTheDocument();
    }
  );

  it('keeps the confirmed preference and reports a failed favorite write', async () => {
    const { toast } = await import('sonner');
    const notify = vi.spyOn(toast, 'error');
    get.mockResolvedValue({ spaces: [space()], total: 1 });
    patch.mockRejectedValue(new Error('offline'));
    const { user } = renderWithProviders(<SpacesManager variant="page" />);
    await user.click(await screen.findByRole('button', { name: 'spaces.favorite_add' }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith('spaces.favorite_error'));
    expect(screen.getByRole('button', { name: 'spaces.favorite_add' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(
      screen.queryByRole('region', { name: 'spaces.favorites_title' })
    ).not.toBeInTheDocument();
    notify.mockRestore();
  });
  it.each(['page', 'section'] as const)(
    'keeps filters usable with no matches in %s',
    async variant => {
      const { user } = renderWithProviders(<SpacesManager variant={variant} />);
      const search = screen.getByRole('searchbox', { name: 'spaces.list.search_name' });
      await user.selectOptions(
        screen.getByRole('combobox', { name: 'spaces.list.field' }),
        'filename'
      );
      await user.type(search, 'été');
      await waitFor(() =>
        expect(get).toHaveBeenLastCalledWith(
          '/rag-spaces',
          expect.objectContaining({
            params: { q: 'été', field: 'filename', sort: 'name' },
          })
        )
      );
      expect(await screen.findByText('spaces.list.no_matches')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'spaces.list.clear' }));
      await waitFor(() => expect(screen.getByRole('searchbox')).toHaveValue(''));
      expect(await screen.findByText('spaces.empty_title')).toBeInTheDocument();
    }
  );

  it('states a failed read and lets the person retry without claiming an empty collection', async () => {
    get.mockRejectedValueOnce(new Error('offline'));
    const { user } = renderWithProviders(<SpacesManager variant="section" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('spaces.list.load_error');
    expect(screen.queryByText('spaces.empty_title')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(await screen.findByText('spaces.empty_title')).toBeInTheDocument();
  });

  it('clears search and pending forms when the account changes', async () => {
    const view = renderWithProviders(<SpacesManager variant="page" />);
    await view.user.type(screen.getByRole('searchbox'), 'private');
    auth.user = { id: 'another-owner' };
    view.rerender(<SpacesManager variant="page" />);
    expect(screen.getByRole('searchbox')).toHaveValue('');
    expect(await screen.findByText('spaces.empty_title')).toBeInTheDocument();
  });
});
