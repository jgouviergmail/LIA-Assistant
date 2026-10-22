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
import { SmsErasureProvider } from '../SmsErasure';
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
it('refreshes names only on explicit request and coalesces double clicks without losing focus', async () => {
  let finish: (() => void) | undefined;
  const pending = new Promise<void>(resolve => {
    finish = resolve;
  });
  render(<SmsArchive lng="en" />);
  await screen.findByText('Alice');
  expect(post).not.toHaveBeenCalled();
  post.mockReturnValueOnce(pending);
  const button = screen.getByRole('button', { name: 'sms.refresh_names' });
  button.focus();
  fireEvent.click(button);
  fireEvent.click(button);
  expect(post).toHaveBeenCalledExactlyOnceWith('/sms/identities/refresh', undefined, undefined);
  expect(button).toHaveFocus();
  expect(button).toHaveAttribute('aria-disabled', 'true');
  const before = get.mock.calls.length;
  await act(async () => {
    finish?.();
    await pending;
  });
  await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before));
  expect(button).toHaveFocus();
});
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
  fireEvent.click(screen.getByRole('button', { name: 'sms.by_day' }));
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
  await screen.findByText('Alice');
  expect(screen.getByRole('button', { name: 'sms.by_sender' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(post).not.toHaveBeenCalled();
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

it('keeps the SMS archive readable when refreshing names fails and allows a retry', async () => {
  const { toast } = await import('sonner');
  const notify = vi.spyOn(toast, 'error').mockImplementation(() => 'sms-refresh-error');
  render(<SmsArchive lng="en" />);
  await screen.findByText('Alice');
  post.mockRejectedValueOnce(new Error('offline'));
  const button = screen.getByRole('button', { name: 'sms.refresh_names' });
  fireEvent.click(button);
  await waitFor(() => expect(notify).toHaveBeenCalledWith('sms.unavailable'));
  expect(screen.getByText('Alice')).toBeInTheDocument();
  expect(button).toHaveAttribute('aria-disabled', 'false');
  post.mockResolvedValueOnce(undefined);
  fireEvent.click(button);
  await waitFor(() =>
    expect(post.mock.calls.filter(call => call[0] === '/sms/identities/refresh')).toHaveLength(2)
  );
  notify.mockRestore();
});

it('proposes a sender scope from its source identifier without deleting directly', async () => {
  const request = vi.fn();
  render(
    <SmsErasureProvider value={{ busy: false, request }}>
      <SmsArchive lng="en" />
    </SmsErasureProvider>
  );
  const details = (await screen.findByText('Alice')).closest('details');
  if (!details) throw new Error('Missing sender disclosure');
  details.open = true;
  fireEvent(details, new Event('toggle'));
  fireEvent.click(await screen.findByRole('button', { name: /sms.erase_sender/ }));
  expect(request).toHaveBeenCalledExactlyOnceWith({ sender_id: message.id });
  expect(post.mock.calls.every(call => call[0] === '/sms/search')).toBe(true);
});

it('returns to the first page after a source change without resubmitting an invalid cursor', async () => {
  const { publishApplicationResources } = await import('@/lib/application-resources');
  post.mockResolvedValue({ ...page, next_cursor: 'old-snapshot' });
  render(<SmsArchive lng="en" />);
  fireEvent.click(screen.getByRole('button', { name: 'sms.by_day' }));
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
  fireEvent.click(screen.getByRole('button', { name: 'sms.by_day' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(label);
});
