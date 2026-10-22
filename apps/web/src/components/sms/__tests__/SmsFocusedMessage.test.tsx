import { act, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { SmsMessage } from '@/types/sms';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { SmsFocusedMessage } from '../SmsFocusedMessage';

const message: SmsMessage = {
  id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  sender: 'Camille',
  display_name: 'Camille',
  identity_source: 'raw',
  identity_state: 'unresolved',
  relation_key: null,
  body: 'Original source text',
  received_at: '2026-10-19T12:00:00Z',
  date_kind: 'received',
  origin: 'iphone',
};
beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  get.mockResolvedValue(message);
});

it('does not take focus from a control used while the initial message is loading', async () => {
  const pending = Promise.withResolvers<SmsMessage>();
  get.mockReturnValueOnce(pending.promise);
  render(
    <>
      <button>Keep focus here</button>
      <SmsFocusedMessage messageId={message.id} lng="en" />
    </>
  );
  const control = screen.getByRole('button', { name: 'Keep focus here' });
  control.focus();
  await act(async () => pending.resolve(message));
  await screen.findByText(message.body);
  expect(control).toHaveFocus();
});

it('re-reads a focused message in place on source changes, without stealing focus', async () => {
  render(
    <>
      <button>Keep focus here</button>
      <SmsFocusedMessage messageId={message.id} lng="en" />
    </>
  );
  await screen.findByText(message.body);
  const next = Promise.withResolvers<SmsMessage>();
  get.mockReturnValueOnce(next.promise);
  const button = screen.getByRole('button', { name: 'Keep focus here' });
  button.focus();
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  // The text stays until the fresh answer replaces it (owner rule 2026-10-21):
  // a refresh is never a visible reload. An erased message still leaves —
  // see the next test.
  expect(screen.getByText(message.body)).toBeInTheDocument();
  await act(async () => next.resolve({ ...message, body: 'Fresh source text' }));
  expect(await screen.findByText('Fresh source text')).toBeVisible();
  expect(screen.queryByText(message.body)).not.toBeInTheDocument();
  expect(button).toHaveFocus();
});

it('does not retain a focused message after its source has been erased', async () => {
  render(<SmsFocusedMessage messageId={message.id} lng="en" />);
  await screen.findByText(message.body);
  get.mockRejectedValueOnce(new Error('not found'));
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  expect(await screen.findByRole('alert')).toHaveTextContent('sms.unavailable');
  expect(screen.queryByText(message.body)).not.toBeInTheDocument();
});
