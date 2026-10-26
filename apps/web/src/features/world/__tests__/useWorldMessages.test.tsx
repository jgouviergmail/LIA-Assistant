import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useWorldMessages } from '../useWorldMessages';

const mocks = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: mocks.mutate }) }));
const id = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const getScope = () => ({ epoch: id, controller: 'c'.repeat(43) });

it('aborts the old account and refuses its late read and retained callbacks after switching', async () => {
  const first = Promise.withResolvers<unknown>();
  const second = Promise.withResolvers<unknown>();
  mocks.mutate.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const accepted = vi.fn();
  const hook = renderHook(({ owner }) => useWorldMessages(owner, true, getScope, accepted), {
    initialProps: { owner: 'first-owner' },
  });
  const retained = hook.result.current;
  const firstSignal: AbortSignal = mocks.mutate.mock.calls[0][2].signal;
  hook.rerender({ owner: 'second-owner' });
  expect(firstSignal.aborted).toBe(true);
  expect(hook.result.current.state.mailbox).toBeNull();
  await act(async () => {
    first.resolve({ PRIVATE_BODY: 'must never publish' });
    await first.promise;
  });
  expect(hook.result.current.state.mailbox).toBeNull();
  expect(await retained.send(id, 'Private draft', true)).toBe('unavailable');
  expect(mocks.mutate).toHaveBeenCalledTimes(2);
  await act(async () => {
    second.resolve({ server_time: 1000, ttl_seconds: 1800, messages: [], truncated: false });
    await second.promise;
  });
  expect(hook.result.current.state.status).toBe('online');
  expect(accepted).not.toHaveBeenCalled();
  const secondSignal: AbortSignal = mocks.mutate.mock.calls[1][2].signal;
  hook.unmount();
  expect(secondSignal.aborted).toBe(false); // Its read completed before disposal.
});
