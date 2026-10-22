import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { SmsMessage, SmsPage } from '@/types/sms';
const { post, get, patch } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), patch: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { sms_enabled: true }, capabilities: { sms: { enabled: true } } },
  }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post, get, patch },
}));
import { SmsHubSection } from '../SmsHubSection';
const preferences = { ingestion_enabled: true, assistant_enabled: false, push_enabled: true };
beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation(async (path: string) =>
    path === '/sms/senders'
      ? { items: [], total: 0, as_of: '2026-10-19T00:00:00Z', revision: 1, next_cursor: null }
      : { preferences }
  );
  patch.mockImplementation(async () => {
    const changed = { ...preferences, push_enabled: false };
    get.mockResolvedValue({ preferences: changed });
    return changed;
  });
  post.mockResolvedValue({
    items: [],
    total: 0,
    as_of: '2026-10-19T00:00:00Z',
    revision: 1,
    next_cursor: null,
  });
});
function unfold(title: string) {
  const summary = screen.getByText(title).closest('summary');
  const details = summary?.closest('details');
  if (!details) throw new Error('Missing native disclosure');
  details.open = true;
  fireEvent(details, new Event('toggle'));
}
it('keeps the SMS hub body unmounted until opened and does not invent a zero count', async () => {
  const { rerender } = render(<SmsHubSection lng="en" total={null} />);
  expect(screen.getByText('—')).toBeVisible();
  expect(post).not.toHaveBeenCalled();
  rerender(<SmsHubSection lng="en" total={7} />);
  expect(screen.getByText('7')).toBeVisible();
  unfold('sms.title');
  await waitFor(() => expect(post).toHaveBeenCalled());
  expect(post.mock.lastCall?.slice(0, 2)).toEqual(['/sms/search', { limit: 10 }]);
  expect(get).not.toHaveBeenCalled();
  expect(screen.queryByRole('search')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'sms.by_sender' })).not.toBeInTheDocument();
});
it('pages received SMS in server chronology, retains focus during reads, and re-reads in place after erasure', async () => {
  const { publishApplicationResources } = await import('@/lib/application-resources');
  const message = (body: string, received_at: string): SmsMessage => ({
    id: body,
    display_name: 'Alice',
    sender: 'Alice',
    body,
    received_at,
    date_kind: 'received',
    origin: 'iphone',
    identity_source: 'raw',
    identity_state: 'unresolved',
    relation_key: null,
  });
  const first: SmsPage = {
    items: [
      message('<b>newest</b>', '2026-10-20T12:00:00Z'),
      message('older', '2026-10-19T12:00:00Z'),
    ],
    total: 11,
    revision: 1,
    as_of: '2026-10-20T12:00:00Z',
    next_cursor: 'snapshot-page-2',
  };
  let resolveNext: ((data: SmsPage) => void) | undefined;
  post.mockResolvedValueOnce(first).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        resolveNext = resolve;
      })
  );
  render(<SmsHubSection lng="fr" total={11} />);
  unfold('sms.title');
  await screen.findByText('<b>newest</b>');
  expect(screen.getAllByRole('listitem').map(item => item.textContent)).toEqual([
    expect.stringContaining('<b>newest</b>'),
    expect.stringContaining('older'),
  ]);
  const next = screen.getByRole('button', { name: 'common.next' });
  next.focus();
  fireEvent.click(next);
  await waitFor(() => expect(post.mock.lastCall?.[1].cursor).toBe('snapshot-page-2'));
  expect(next).toHaveFocus();
  expect(next).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText('<b>newest</b>')).toBeVisible();
  await act(async () =>
    resolveNext?.({ ...first, items: [message('last', '2026-10-18T12:00:00Z')], next_cursor: null })
  );
  expect(await screen.findByText('last')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'common.previous' }));
  post.mockResolvedValue(first);
  await waitFor(() => expect(post.mock.lastCall?.[1].cursor).toBeUndefined());
  await screen.findByText('<b>newest</b>');
  const reread = Promise.withResolvers<SmsPage>();
  post.mockReturnValueOnce(reread.promise);
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  // Back to the first page, read in place (owner rule 2026-10-21): what is on
  // screen stays until the fresh page replaces it — the erased SMS then goes.
  expect(screen.getByText('<b>newest</b>')).toBeVisible();
  await waitFor(() => expect(post.mock.lastCall?.[1].cursor).toBeUndefined());
  await act(async () =>
    reread.resolve({ ...first, items: [message('older', '2026-10-19T12:00:00Z')], total: 10 })
  );
  await waitFor(() => expect(screen.queryByText('<b>newest</b>')).not.toBeInTheDocument());
});
it('dates each hub SMS on its own line and opens the message with its sender', async () => {
  // Owner request 2026-10-21: the badge sits where the SMS's words begin.
  post.mockResolvedValueOnce({
    items: [
      {
        id: 'sms-1',
        display_name: 'Alice',
        sender: '+33600000000',
        body: 'On se voit demain ?',
        received_at: '2026-10-20T12:00:00Z',
        date_kind: 'received',
        origin: 'iphone',
        identity_source: 'contact',
        identity_state: 'resolved',
        relation_key: null,
      },
    ],
    total: 1,
    revision: 1,
    as_of: '2026-10-20T12:00:00Z',
    next_cursor: null,
  } satisfies SmsPage);
  render(<SmsHubSection lng="fr" total={1} />);
  unfold('sms.title');

  const sender = await screen.findByText('Alice');
  const message = screen.getByText(/On se voit demain/);
  expect(message.tagName).toBe('P');
  expect(message.firstElementChild).toContainElement(sender);
  const row = screen.getByRole('listitem');
  expect(row.querySelector('time')?.parentElement).not.toContainElement(sender);
});
it('reports failed SMS reads before emptiness and retries when reopened', async () => {
  post.mockRejectedValueOnce(new Error('offline'));
  render(<SmsHubSection lng="en" total={11} />);
  unfold('sms.title');
  expect(await screen.findByRole('alert')).toHaveTextContent('sms.unavailable');
  expect(screen.queryByText('sms.empty')).not.toBeInTheDocument();
  const details = screen.getByText('sms.title').closest('details');
  if (!details) throw new Error('Missing disclosure');
  details.open = false;
  fireEvent(details, new Event('toggle'));
  await act(async () => {});
  const before = post.mock.calls.length;
  unfold('sms.title');
  await waitFor(() => expect(post.mock.calls.length).toBeGreaterThan(before));
  expect(await screen.findByText('sms.empty')).toBeVisible();
});
