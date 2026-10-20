import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
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
  default: { post, get },
}));
import { SmsHubSection } from '../SmsHubSection';
import { SmsPushSettings } from '../SmsPushSettings';
const preferences = { ingestion_enabled: true, assistant_enabled: false, push_enabled: true };
beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ preferences });
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
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
});
it('offers the immediate SMS push setting independently of assistant consent and heartbeat hours', async () => {
  render(<SmsPushSettings lng="en" />);
  expect(get).not.toHaveBeenCalled();
  unfold('sms.push');
  const control = await screen.findByRole('switch', { name: 'sms.push' });
  fireEvent.click(control);
  await waitFor(() => expect(post).toHaveBeenCalled());
  expect(post.mock.calls[0][0]).toBe('/sms/commands');
  expect(post.mock.calls[0][1]).toEqual({
    operation_id: 'sms_preferences.update',
    payload: { ...preferences, push_enabled: false },
  });
});
