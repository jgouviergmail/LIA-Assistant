import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { push, info, dismiss } = vi.hoisted(() => ({
  push: vi.fn(),
  dismiss: vi.fn(),
  info: vi.fn<
    (
      text: string,
      options: { id: string; duration: number; action: { label: string; onClick: () => void } }
    ) => void
  >(),
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('sonner', () => ({ toast: { info, dismiss } }));
import { useSmsReceivedToast } from '../useSmsReceivedToast';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
const signal: SmsReceivedSignal = {
  type: 'sms_received',
  user_id: '11111111-1111-4111-8111-111111111111',
  message_id: '22222222-2222-4222-8222-222222222222',
  occurrence_id: '33333333-3333-4333-8333-333333333333',
};
beforeEach(() => vi.clearAllMocks());
it('shows a generic notice and navigates through the localized protected route only on click', () => {
  const { result } = renderHook(() => useSmsReceivedToast(signal.user_id));
  act(() => result.current(signal));
  expect(info.mock.calls[0][0]).toBe('sms.new_received');
  expect(push).not.toHaveBeenCalled();
  info.mock.calls[0][1].action.onClick();
  expect(push).toHaveBeenCalledWith(`/dashboard/sms?message=${signal.message_id}`);
});
it('ignores late notices and stale clicks after an account switch', () => {
  const { result, rerender } = renderHook(({ owner }) => useSmsReceivedToast(owner), {
    initialProps: { owner: signal.user_id },
  });
  const old = result.current;
  act(() => old(signal));
  const action = info.mock.calls[0][1].action;
  rerender({ owner: '44444444-4444-4444-8444-444444444444' });
  act(() => old(signal));
  action.onClick();
  expect(info).toHaveBeenCalledOnce();
  expect(push).not.toHaveBeenCalled();
  expect(dismiss).toHaveBeenCalledWith(`sms:${signal.occurrence_id}`);
});
