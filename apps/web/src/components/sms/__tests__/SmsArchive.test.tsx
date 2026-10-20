import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post, get },
}));
import { SmsArchive } from '../SmsArchive';
const message = {
  id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  sender: 'Alice',
  display_name: 'Alice',
  identity_source: 'raw',
  identity_state: 'unresolved',
  relation_key: null,
  body: 'Dinner tomorrow',
  received_at: '2026-10-19T12:00:00Z',
  date_kind: 'received',
  origin: 'iphone',
};
const page = {
  items: [message],
  total: 1,
  revision: 1,
  as_of: '2026-10-19T12:00:00Z',
  next_cursor: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue(page);
  get.mockResolvedValue({
    items: [
      {
        id: message.id,
        sender: 'Alice',
        display_name: 'Alice',
        identity_state: 'raw',
        identity_source: 'raw',
        relation_key: null,
        total: 1,
        latest_at: message.received_at,
      },
    ],
    total: 1,
    as_of: page.as_of,
    revision: 1,
    next_cursor: null,
  });
});
it('reads day view, submits a private search, and keeps grouping usable without issuing mutations', async () => {
  render(<SmsArchive lng="en" />);
  await screen.findByText('Dinner tomorrow');
  fireEvent.change(screen.getByRole('searchbox', { name: 'sms.search' }), {
    target: { value: 'private words' },
  });
  fireEvent.submit(screen.getByRole('search'));
  await waitFor(() =>
    expect(post.mock.calls.some(call => call[1]?.query === 'private words')).toBe(true)
  );
  fireEvent.click(screen.getByRole('button', { name: 'sms.by_sender' }));
  await screen.findByText('sms.page_groups');
  expect(post.mock.calls.every(call => call[0] === '/sms/search')).toBe(true);
});
it('opens sender content lazily instead of loading every SMS thread at once', async () => {
  render(<SmsArchive lng="en" />);
  await screen.findByText('Dinner tomorrow');
  fireEvent.click(screen.getByRole('button', { name: 'sms.by_sender' }));
  await screen.findByText('Alice');
  const calls = post.mock.calls.length;
  expect(screen.queryByText('Dinner tomorrow')).not.toBeInTheDocument();
  const summary = screen.getByText('Alice').closest('summary');
  if (!summary) throw new Error('Missing native disclosure');
  const details = summary.closest('details');
  if (!details) throw new Error('Missing native details');
  details.open = true;
  fireEvent(details, new Event('toggle'));
  await screen.findByText('Dinner tomorrow');
  expect(post.mock.calls.length).toBe(calls + 1);
});

it('returns to the first page after a source change without resubmitting an invalid cursor', async () => {
  const { publishApplicationResources } = await import('@/lib/application-resources');
  post.mockResolvedValue({ ...page, next_cursor: 'old-snapshot' });
  render(<SmsArchive lng="en" />);
  await screen.findByText('Dinner tomorrow');
  fireEvent.click(screen.getByRole('button', { name: 'sms.load_more' }));
  await waitFor(() => expect(post.mock.lastCall?.[1].cursor).toBe('old-snapshot'));
  await screen.findByText('Dinner tomorrow');
  const before = post.mock.calls.length;
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  await waitFor(() => expect(post.mock.calls.length).toBeGreaterThan(before));
  expect(post.mock.calls.slice(before).every(call => call[1].cursor === undefined)).toBe(true);
});

it.each([
  [409, 'QUERY_TOO_BROAD', 'sms.too_broad'],
  [503, 'UNAVAILABLE', 'sms.unavailable'],
])('shows the actual read refusal (%s)', async (status, code, label) => {
  const { ApiError } = await import('@/lib/api-client');
  post.mockRejectedValueOnce(
    new ApiError('Request failed', status, { detail: { error_code: code } })
  );
  render(<SmsArchive lng="en" />);
  expect(await screen.findByRole('alert')).toHaveTextContent(label);
});
