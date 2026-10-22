import { act, renderHook, waitFor } from '@testing-library/react';
import { isValidElement, type ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { SmsMessage } from '@/types/sms';
interface NoticeOptions {
  id: string;
  description?: ReactNode;
  duration?: number;
  action: { label: string; onClick: () => void };
}
const { push, info, dismiss, get } = vi.hoisted(() => ({
  push: vi.fn(),
  dismiss: vi.fn(),
  info: vi.fn<(title: ReactNode, options: NoticeOptions) => void>(),
  get: vi.fn<
    (endpoint: string, config: { signal: AbortSignal; timeout: number }) => Promise<SmsMessage>
  >(),
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('sonner', () => ({ toast: { info, dismiss } }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
import {
  SMS_NOTICE_DURATION_MS,
  SMS_NOTICE_READ_TIMEOUT_MS,
  useSmsReceivedToast,
} from '../useSmsReceivedToast';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
const signal: SmsReceivedSignal = {
  type: 'sms_received',
  user_id: '11111111-1111-4111-8111-111111111111',
  message_id: '22222222-2222-4222-8222-222222222222',
  occurrence_id: '33333333-3333-4333-8333-333333333333',
};
const message: SmsMessage = {
  id: signal.message_id,
  sender: '+33600000000',
  display_name: 'Camille Martin',
  identity_source: 'contact',
  identity_state: 'resolved',
  relation_key: null,
  body: 'See you at 7?\nBring the keys.',
  received_at: '2026-10-21T15:00:00Z',
  date_kind: 'source',
  origin: 'sms',
};
function textOf(node: ReactNode): string {
  if (!isValidElement<{ children?: ReactNode }>(node)) return String(node);
  return String(node.props.children);
}
beforeEach(() => vi.clearAllMocks());
it('reads the announced message and shows its sender as the title and its text below', async () => {
  get.mockResolvedValue(message);
  const { result } = renderHook(() => useSmsReceivedToast(signal.user_id));
  act(() => result.current(signal));
  await waitFor(() => expect(info).toHaveBeenCalledOnce());
  expect(get).toHaveBeenCalledWith(
    `/sms/${signal.message_id}`,
    expect.objectContaining({ timeout: SMS_NOTICE_READ_TIMEOUT_MS })
  );
  const [title, options] = info.mock.calls[0];
  expect(title).toBe(message.display_name);
  expect(textOf(options.description)).toBe(message.body);
  expect(options.duration).toBe(SMS_NOTICE_DURATION_MS);
  expect(options.id).toBe(`sms:${signal.occurrence_id}`);
  expect(push).not.toHaveBeenCalled();
  options.action.onClick();
  expect(push).toHaveBeenCalledWith(`/dashboard/sms?message=${signal.message_id}`);
});
it('still announces a new SMS when the message cannot be read', async () => {
  get.mockRejectedValue(new Error('gone'));
  const { result } = renderHook(() => useSmsReceivedToast(signal.user_id));
  act(() => result.current(signal));
  await waitFor(() => expect(info).toHaveBeenCalledOnce());
  const [title, options] = info.mock.calls[0];
  expect(title).toBe('sms.new_received');
  expect(options.description).toBeUndefined();
  expect(options.duration).toBeUndefined();
});
it('aborts a read in flight and shows nothing after an account switch', async () => {
  let resolve: (value: SmsMessage) => void = () => undefined;
  get.mockReturnValue(new Promise<SmsMessage>(done => (resolve = done)));
  const { result, rerender } = renderHook(({ owner }) => useSmsReceivedToast(owner), {
    initialProps: { owner: signal.user_id },
  });
  act(() => result.current(signal));
  const { signal: read } = get.mock.calls[0][1];
  rerender({ owner: '44444444-4444-4444-8444-444444444444' });
  expect(read.aborted).toBe(true);
  await act(async () => resolve(message));
  expect(info).not.toHaveBeenCalled();
  expect(dismiss).toHaveBeenCalledWith(`sms:${signal.occurrence_id}`);
});
it('ignores late notices and stale clicks after an account switch', async () => {
  get.mockResolvedValue(message);
  const { result, rerender } = renderHook(({ owner }) => useSmsReceivedToast(owner), {
    initialProps: { owner: signal.user_id },
  });
  const old = result.current;
  act(() => old(signal));
  await waitFor(() => expect(info).toHaveBeenCalledOnce());
  const { action } = info.mock.calls[0][1];
  rerender({ owner: '44444444-4444-4444-8444-444444444444' });
  act(() => old(signal));
  action.onClick();
  expect(get).toHaveBeenCalledOnce();
  expect(info).toHaveBeenCalledOnce();
  expect(push).not.toHaveBeenCalled();
  expect(dismiss).toHaveBeenCalledWith(`sms:${signal.occurrence_id}`);
});
