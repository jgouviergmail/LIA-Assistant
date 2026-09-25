/**
 * AdminBroadcastHistory — what an administrator reads under the send form
 * (ADR-312): the audience (everyone, or the named selection with the EXACT
 * count of the rest), the expiry chosen and whether it passed, delivery and
 * read receipts, a long message folded, paging by offset, and the three
 * states a list owes its reader (first load, empty, failed) — with a refresh
 * that keeps the list mounted.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { BroadcastHistoryItem, BroadcastHistoryPage } from '@/hooks/useBroadcastHistory';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

// The shared stub renders the bare key; this suite reads the interpolated
// values too, so a key and its parameters are rendered together.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key}${JSON.stringify(params)}` : key,
    i18n: { language: 'en' },
  }),
}));

import { AdminBroadcastHistory } from '../AdminBroadcastHistory';

const refetch = vi.fn();

function item(over: Partial<BroadcastHistoryItem> = {}): BroadcastHistoryItem {
  return {
    id: 'b1',
    message: 'Maintenance tonight',
    sent_at: '2026-09-20T08:00:00Z',
    sender_name: 'Ada Admin',
    audience: 'all',
    recipients: [],
    recipients_total: 0,
    reached_count: 42,
    expires_at: null,
    expires_in_days: null,
    is_expired: false,
    fcm_sent: 40,
    fcm_failed: 2,
    read_count: 17,
    ...over,
  };
}

function serve(
  page: BroadcastHistoryPage | undefined,
  over: { loading?: boolean; error?: Error | null } = {}
) {
  useApiQuery.mockReturnValue({
    data: page,
    loading: over.loading ?? page === undefined,
    error: over.error ?? null,
    refetch,
    setData: vi.fn(),
  });
}

function render(refreshKey = 0) {
  return renderWithProviders(<AdminBroadcastHistory lng="en" refreshKey={refreshKey} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminBroadcastHistory — states', () => {
  it('announces a first load with placeholders and no list', () => {
    serve(undefined, { loading: true });
    render();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('says nothing was sent yet on an empty history', () => {
    serve({ items: [], total: 0 });
    render();

    expect(screen.getByText('settings.admin.broadcast.history.empty')).toBeInTheDocument();
  });

  it('offers a retry when the first read failed', async () => {
    serve(undefined, { loading: false, error: new Error('down') });
    const { user } = render();

    expect(screen.getByText('settings.admin.broadcast.history.load_error')).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'settings.admin.broadcast.history.retry' })
    );

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('keeps the list mounted and busy while a refresh runs', () => {
    serve({ items: [item()], total: 1 }, { loading: true });
    render(1);

    const list = screen.getByRole('list', { name: 'settings.admin.broadcast.history.title' });
    expect(list).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('AdminBroadcastHistory — a row', () => {
  it('names a broadcast to everyone without listing anybody', () => {
    serve({ items: [item()], total: 1 });
    render();
    const row = screen.getByRole('listitem');

    expect(
      within(row).getByText('settings.admin.broadcast.history.to_everyone')
    ).toBeInTheDocument();
    expect(within(row).getByText('settings.admin.broadcast.all_users')).toBeInTheDocument();
    expect(within(row).getByText('Maintenance tonight')).toBeInTheDocument();
    expect(within(row).getByText('Ada Admin')).toBeInTheDocument();
  });

  it('names the first recipients and counts the rest exactly', () => {
    serve({
      items: [
        item({
          audience: 'selected',
          recipients: [
            { id: 'u1', full_name: 'Alice', email: 'alice@example.com' },
            { id: 'u2', full_name: null, email: 'bob@example.com' },
          ],
          recipients_total: 5,
        }),
      ],
      total: 1,
    });
    render();
    const row = screen.getByRole('listitem');

    expect(
      within(row).getByText(
        'settings.admin.broadcast.history.named_and_more{"names":"Alice and bob@example.com","count":3}'
      )
    ).toBeInTheDocument();
    expect(within(row).getByText('settings.admin.broadcast.selected_users')).toBeInTheDocument();
  });

  it('says so when every selected account has since been deleted', () => {
    serve({
      items: [item({ audience: 'selected', recipients: [], recipients_total: 0 })],
      total: 1,
    });
    render();

    expect(
      screen.getByText('settings.admin.broadcast.history.no_recipient_left')
    ).toBeInTheDocument();
  });

  it('states the expiry: never, pending with its delay, or passed', () => {
    serve({
      items: [
        item({ id: 'never' }),
        item({
          id: 'pending',
          expires_at: '2026-09-27T08:00:00Z',
          expires_in_days: 7,
        }),
        item({
          id: 'passed',
          expires_at: '2026-08-01T08:00:00Z',
          expires_in_days: 30,
          is_expired: true,
        }),
      ],
      total: 3,
    });
    render();
    const [never, pending, passed] = screen.getAllByRole('listitem');

    expect(
      within(never).getByText('settings.admin.broadcast.history.never_expires')
    ).toBeInTheDocument();
    expect(within(pending).getByText(/expires_on/)).toHaveTextContent('delay_days{"count":7}');
    expect(within(pending).queryByText('settings.admin.broadcast.history.expired')).toBeNull();
    expect(within(passed).getByText(/expired_on/)).toHaveTextContent('delay_days{"count":30}');
    expect(
      within(passed).getByText('settings.admin.broadcast.history.expired')
    ).toBeInTheDocument();
  });

  it('reports delivery and read receipts from the server figures', () => {
    serve({ items: [item()], total: 1 });
    render();

    expect(
      screen.getByText(
        'settings.admin.broadcast.history.delivery{"reached":42,"sent":40,"failed":2}'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('17')).toBeInTheDocument();
  });

  it('folds a long message behind a toggle that says whether it is open', async () => {
    serve({ items: [item({ message: 'x'.repeat(400) })], total: 1 });
    const { user } = render();
    const toggle = screen.getByRole('button', {
      name: 'settings.admin.broadcast.history.show_more',
    });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);

    expect(
      screen.getByRole('button', { name: 'settings.admin.broadcast.history.show_less' })
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not offer a fold for a short message', () => {
    serve({ items: [item()], total: 1 });
    render();

    expect(
      screen.queryByRole('button', { name: 'settings.admin.broadcast.history.show_more' })
    ).not.toBeInTheDocument();
  });
});

describe('AdminBroadcastHistory — paging', () => {
  it('pages by offset against the admin history endpoint', async () => {
    serve({ items: [item()], total: 25 });
    const { user } = render();

    expect(useApiQuery).toHaveBeenLastCalledWith(
      '/notifications/admin/broadcasts?limit=10&offset=0',
      expect.objectContaining({ enabled: true })
    );
    await user.click(screen.getByRole('button', { name: /^common.next/ }));

    expect(useApiQuery).toHaveBeenLastCalledWith(
      '/notifications/admin/broadcasts?limit=10&offset=10',
      expect.anything()
    );
  });

  it('shows no pager when everything fits on one page', () => {
    serve({ items: [item()], total: 1 });
    render();

    expect(screen.queryByRole('button', { name: /^common.next/ })).not.toBeInTheDocument();
  });
});
