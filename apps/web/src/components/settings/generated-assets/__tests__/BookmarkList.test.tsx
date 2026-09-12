/**
 * The « Bookmarks » tab and its cards (ADR-282).
 *
 * What the tab owes a person:
 * - the EXACT total and the cap the account may reach, from the payload's
 *   aggregates, never from the rows on screen (ADR-185/184);
 * - a card that shows the request as a quotation, or says the answer had
 *   none, and renders the answer's formatting;
 * - a download built from the card itself (the chat's `.md` path), a delete
 *   that asks first, and a share only where the platform offers one;
 * - a first load that draws skeletons and an empty state that distinguishes
 *   « nothing kept yet » from « nothing matches ».
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { Bookmark } from '@/types/bookmarks';

const list = vi.hoisted(() => ({
  items: [] as Bookmark[],
  total: 0,
  maxPerUser: 500,
  page: 1,
  totalPages: 1,
  firstLoad: false,
  loading: false,
  error: null as Error | null,
  calls: [] as unknown[],
  refetch: vi.fn(),
}));
vi.mock('@/hooks/useBookmarks', () => ({
  BOOKMARKS_PAGE_SIZE: 24,
  useBookmarks: (query: string | undefined, enabled: boolean) => {
    list.calls.push({ query, enabled });
    return { ...list, setPage: vi.fn() };
  },
}));

const mutate = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false, error: null }),
}));
const confirmed = vi.hoisted(() => ({ answer: true }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm: async () => confirmed.answer, confirmDialog: null }),
}));
const downloadMarkdown = vi.hoisted(() => vi.fn());
vi.mock('@/lib/utils/download-markdown', () => ({ downloadMarkdown }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { BookmarkList } from '../BookmarkList';

function bookmark(over: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 'b1b2c3d4-0000-4000-8000-000000000001',
    message_id: 'a1b2c3d4-0000-4000-8000-000000000001',
    conversation_id: null,
    content: '**Réservé** : salle B, 14 h.',
    request_content: 'Réserve la salle B à 14 h',
    answered_at: '2026-09-12T08:05:00Z',
    created_at: '2026-09-12T08:06:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  list.items = [];
  list.total = 0;
  list.maxPerUser = 500;
  list.error = null;
  list.firstLoad = false;
  list.calls = [];
  confirmed.answer = true;
  mutate.mockResolvedValue(undefined);
});

describe('what the tab states', () => {
  it('names the exact total against the cap, both from the payload', () => {
    list.items = [bookmark()];
    list.total = 137;

    renderWithProviders(<BookmarkList lng="fr" />);

    expect(screen.getByText(/settings.bookmarks.capacity/)).toBeInTheDocument();
    expect(screen.getAllByTestId('bookmark-card')).toHaveLength(1);
  });

  it('separates « nothing kept yet » from « nothing matches »', async () => {
    const { user } = renderWithProviders(<BookmarkList lng="fr" />);

    expect(screen.getByTestId('empty-state')).toHaveAttribute('data-reason', 'no-data');
    expect(screen.getByText('settings.generated_assets.empty.bookmarks_title')).toBeInTheDocument();

    await user.type(screen.getByRole('searchbox'), 'salle');

    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toHaveAttribute('data-reason', 'no-match')
    );
    // The search reached the hook, debounced, as the needle it will send.
    await waitFor(() => expect(list.calls.at(-1)).toMatchObject({ query: 'salle' }));
  });

  it('draws skeletons on the first load and an error state when the read failed', () => {
    list.firstLoad = true;
    const { unmount } = renderWithProviders(<BookmarkList lng="fr" />);
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
    unmount();

    list.firstLoad = false;
    list.error = new Error('boom');
    renderWithProviders(<BookmarkList lng="fr" />);
    expect(screen.getByText('settings.bookmarks.load_error')).toBeInTheDocument();
  });
});

describe('a card', () => {
  it('quotes the request and renders the answer with its formatting', () => {
    list.items = [bookmark()];
    list.total = 1;

    renderWithProviders(<BookmarkList lng="fr" />);

    expect(screen.getByText('Réserve la salle B à 14 h')).toBeInTheDocument();
    // `**Réservé**` came out as emphasis, not as asterisks.
    expect(screen.getByText('Réservé').tagName).toBe('STRONG');
    expect(screen.getByText(/settings.bookmarks.answered_at/)).toBeInTheDocument();
  });

  it('says when the answer answered no request rather than borrowing older words', () => {
    list.items = [bookmark({ request_content: null })];
    list.total = 1;

    renderWithProviders(<BookmarkList lng="fr" />);

    expect(screen.getByText('settings.bookmarks.no_request')).toBeInTheDocument();
  });

  it('downloads a .md built from the card, with the chat filename convention', async () => {
    list.items = [bookmark()];
    list.total = 1;
    const { user } = renderWithProviders(<BookmarkList lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.bookmarks.download' }));

    expect(downloadMarkdown).toHaveBeenCalledTimes(1);
    const [content, baseName] = downloadMarkdown.mock.calls[0] as [string, string];
    expect(content).toContain('> Réserve la salle B à 14 h');
    expect(content).toContain('**Réservé** : salle B, 14 h.');
    expect(baseName).toMatch(/^lia-bookmark-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}$/);
  });

  it('asks before deleting, then tells the list to re-read', async () => {
    list.items = [bookmark()];
    list.total = 1;
    const { user } = renderWithProviders(<BookmarkList lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.bookmarks.delete' }));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(`/bookmarks/${bookmark().id}`, undefined)
    );
    expect(toast.success).toHaveBeenCalledWith('settings.bookmarks.deleted');
    expect(list.refetch).toHaveBeenCalled();
  });

  it('does nothing when the person declines', async () => {
    list.items = [bookmark()];
    list.total = 1;
    confirmed.answer = false;
    const { user } = renderWithProviders(<BookmarkList lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.bookmarks.delete' }));

    expect(mutate).not.toHaveBeenCalled();
    expect(list.refetch).not.toHaveBeenCalled();
  });

  it('offers a share only where the platform has a share sheet', () => {
    list.items = [bookmark()];
    list.total = 1;
    const original = navigator.share;
    Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
    try {
      const { unmount } = renderWithProviders(<BookmarkList lng="fr" />);
      expect(
        screen.queryByRole('button', { name: 'settings.bookmarks.share' })
      ).not.toBeInTheDocument();
      unmount();

      Object.defineProperty(navigator, 'share', { value: vi.fn(), configurable: true });
      renderWithProviders(<BookmarkList lng="fr" />);
      expect(screen.getByRole('button', { name: 'settings.bookmarks.share' })).toBeInTheDocument();
    } finally {
      Object.defineProperty(navigator, 'share', { value: original, configurable: true });
    }
  });
});
